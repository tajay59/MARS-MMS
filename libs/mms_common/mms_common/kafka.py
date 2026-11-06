"""Thin aiokafka wrappers with the TRD §8.1 settings. Business logic stays out of here:
the relay is in `outbox` and `relay`, the retry and DLQ rules in `consumer`."""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from mms_common import metrics
from mms_common.consumer import EventProcessor, SendToDlq
from mms_common.logging import get_logger

RESTART_BACKOFF_S = 5.0
BACKLOG_EVERY_S = 15.0

log = get_logger(__name__)


@dataclass(frozen=True)
class KafkaAuth:
    """One service's Kafka user (TRD §15): SASL/SCRAM-SHA-512 on the broker's client listener.
    kafka/users.yml in infra/ gives each user ACLs on its own topics and consumer groups."""

    username: str
    password: str = field(repr=False)

    def options(self) -> dict[str, Any]:
        return {
            "security_protocol": "SASL_PLAINTEXT",
            "sasl_mechanism": "SCRAM-SHA-512",
            "sasl_plain_username": self.username,
            "sasl_plain_password": self.password,
        }


def kafka_auth(environment: str, username: str | None, password: str | None) -> KafkaAuth | None:
    """The service's credentials, or None for an unauthenticated broker (the tests' throwaway
    containers). Staging and production refuse to start without them."""
    if username and password:
        return KafkaAuth(username, password)
    if environment in ("staging", "production"):
        raise ValueError(f"Kafka credentials are required in {environment} (TRD §15)")
    return None


def _options(auth: KafkaAuth | None) -> dict[str, Any]:
    return auth.options() if auth else {}


def topic_for(service: str) -> str:
    return f"mms.{service}.events"


def dlq_topic_for(consumer_service: str) -> str:
    return f"mms.dlq.{consumer_service}"


async def start_producer(
    bootstrap: str, client_id: str, auth: KafkaAuth | None = None
) -> AIOKafkaProducer:
    producer = AIOKafkaProducer(
        bootstrap_servers=bootstrap,
        client_id=client_id,
        enable_idempotence=True,
        acks="all",
        **_options(auth),
    )
    await producer.start()
    return producer


def producer_fn(producer: AIOKafkaProducer) -> Callable[[str, str, bytes], Awaitable[None]]:
    async def produce(topic: str, key: str, value: bytes) -> None:
        await producer.send_and_wait(topic, value=value, key=key.encode())

    return produce


def producer_factory(
    bootstrap: str, client_id: str, auth: KafkaAuth | None = None
) -> Callable[[], Awaitable[tuple[AIOKafkaProducer, Callable[[str, str, bytes], Awaitable[None]]]]]:
    """For `relay.run_relay`: opens a producer when this worker becomes the outbox leader."""

    async def open_producer() -> tuple[
        AIOKafkaProducer, Callable[[str, str, bytes], Awaitable[None]]
    ]:
        producer = await start_producer(bootstrap, client_id, auth)
        return producer, producer_fn(producer)

    return open_producer


def dlq_sender(
    producer: AIOKafkaProducer, consumer_service: str
) -> Callable[[bytes, str], Awaitable[None]]:
    topic = dlq_topic_for(consumer_service)

    async def send(raw: bytes, reason: str) -> None:
        await producer.send_and_wait(topic, value=raw, headers=[("reason", reason.encode()[:1000])])
        metrics.DLQ_MESSAGES.labels(consumer_service).inc()

    return send


async def run_consumer(
    bootstrap: str,
    group: str,
    topics: list[str],
    processor: EventProcessor,
    auth: KafkaAuth | None = None,
    backlog_every_s: float = BACKLOG_EVERY_S,
) -> None:
    """Group ID = consumer name. Manual commit only after the message is handled or
    dead-lettered (`EventProcessor.process` returns)."""
    consumer = AIOKafkaConsumer(
        *topics,
        bootstrap_servers=bootstrap,
        group_id=group,
        enable_auto_commit=False,
        auto_offset_reset="earliest",
        **_options(auth),
    )
    await consumer.start()
    tracker = metrics.LagTracker()
    watcher = asyncio.create_task(_watch_backlog(consumer, group, tracker, backlog_every_s))
    try:
        async for message in consumer:
            if message.value is not None:
                outcome = await processor.process(message.value)
                metrics.EVENTS_CONSUMED.labels(group, outcome.value).inc()
            await consumer.commit()
            tracker.progress(time.monotonic())
    finally:
        watcher.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await watcher
        metrics.CONSUMER_BACKLOG.labels(group).set(0)
        metrics.CONSUMER_LAG.labels(group).set(0)
        await consumer.stop()


async def _watch_backlog(
    consumer: AIOKafkaConsumer, group: str, tracker: metrics.LagTracker, every_s: float
) -> None:
    """How many messages wait for this group, and for how long it has made no progress. Never
    stops the consumer: a failed reading is skipped."""
    while True:
        await asyncio.sleep(every_s)
        try:
            backlog = await _backlog(consumer)
        except Exception:  # noqa: BLE001 - a rebalance in progress: look again next time
            log.warning("backlog_unreadable", group=group)
            continue
        metrics.CONSUMER_BACKLOG.labels(group).set(backlog)
        metrics.CONSUMER_LAG.labels(group).set(tracker.observe(backlog, time.monotonic()))


async def _backlog(consumer: AIOKafkaConsumer) -> int:
    partitions = consumer.assignment()
    if not partitions:
        return 0
    ends = await consumer.end_offsets(partitions)
    return sum([max(0, ends[p] - await consumer.position(p)) for p in partitions])


async def consume_forever(
    bootstrap: str,
    group: str,
    topics: list[str],
    make_processor: Callable[[SendToDlq], EventProcessor],
    stop: asyncio.Event,
    auth: KafkaAuth | None = None,
) -> None:
    """Run a consumer group until `stop`, restarting after broker errors. Uncommitted
    messages are redelivered after a restart and deduplicated by `processed_events`.

    `make_processor` gets the sender for `mms.dlq.<group>`, so services never hold a producer
    (rule 2)."""
    while not stop.is_set():
        dlq: AIOKafkaProducer | None = None
        task: asyncio.Task[None] | None = None
        try:
            dlq = await start_producer(bootstrap, f"{group}-dlq", auth)
            processor = make_processor(dlq_sender(dlq, group))
            task = asyncio.create_task(run_consumer(bootstrap, group, topics, processor, auth))
            stopper = asyncio.create_task(stop.wait())
            done, _ = await asyncio.wait({task, stopper}, return_when=asyncio.FIRST_COMPLETED)
            stopper.cancel()
            if task in done:
                task.result()  # raises the consumer's error, if any
        except Exception:  # noqa: BLE001 - broker unavailable: back off and reconnect
            log.exception("consumer_failed", group=group)
            try:
                await asyncio.wait_for(stop.wait(), timeout=RESTART_BACKOFF_S)
            except TimeoutError:
                pass
        finally:
            if task is not None and not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
            if dlq is not None:
                with contextlib.suppress(Exception):
                    await dlq.stop()
