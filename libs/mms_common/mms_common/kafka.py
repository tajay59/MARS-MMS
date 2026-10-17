"""Thin aiokafka wrappers with the TRD §8.1 settings. Business logic stays out of here:
the relay is in `outbox` and `relay`, the retry and DLQ rules in `consumer`."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from mms_common.consumer import EventProcessor
from mms_common.logging import get_logger

RESTART_BACKOFF_S = 5.0

log = get_logger(__name__)


def topic_for(service: str) -> str:
    return f"mms.{service}.events"


def dlq_topic_for(consumer_service: str) -> str:
    return f"mms.dlq.{consumer_service}"


async def start_producer(bootstrap: str, client_id: str) -> AIOKafkaProducer:
    producer = AIOKafkaProducer(
        bootstrap_servers=bootstrap,
        client_id=client_id,
        enable_idempotence=True,
        acks="all",
    )
    await producer.start()
    return producer


def producer_fn(producer: AIOKafkaProducer) -> Callable[[str, str, bytes], Awaitable[None]]:
    async def produce(topic: str, key: str, value: bytes) -> None:
        await producer.send_and_wait(topic, value=value, key=key.encode())

    return produce


def producer_factory(
    bootstrap: str, client_id: str
) -> Callable[[], Awaitable[tuple[AIOKafkaProducer, Callable[[str, str, bytes], Awaitable[None]]]]]:
    """For `relay.run_relay`: opens a producer when this worker becomes the outbox leader."""

    async def open_producer() -> tuple[
        AIOKafkaProducer, Callable[[str, str, bytes], Awaitable[None]]
    ]:
        producer = await start_producer(bootstrap, client_id)
        return producer, producer_fn(producer)

    return open_producer


def dlq_sender(
    producer: AIOKafkaProducer, consumer_service: str
) -> Callable[[bytes, str], Awaitable[None]]:
    topic = dlq_topic_for(consumer_service)

    async def send(raw: bytes, reason: str) -> None:
        await producer.send_and_wait(topic, value=raw, headers=[("reason", reason.encode()[:1000])])

    return send


async def run_consumer(
    bootstrap: str,
    group: str,
    topics: list[str],
    processor: EventProcessor,
) -> None:
    """Group ID = consumer name. Manual commit only after the message is handled or
    dead-lettered (`EventProcessor.process` returns)."""
    consumer = AIOKafkaConsumer(
        *topics,
        bootstrap_servers=bootstrap,
        group_id=group,
        enable_auto_commit=False,
        auto_offset_reset="earliest",
    )
    await consumer.start()
    try:
        async for message in consumer:
            if message.value is not None:
                await processor.process(message.value)
            await consumer.commit()
    finally:
        await consumer.stop()


async def consume_forever(
    bootstrap: str,
    group: str,
    topics: list[str],
    make_processor: Callable[[AIOKafkaProducer], EventProcessor],
    stop: asyncio.Event,
) -> None:
    """Run a consumer group until `stop`, restarting after broker errors. Uncommitted
    messages are redelivered after a restart and deduplicated by `processed_events`."""
    while not stop.is_set():
        dlq: AIOKafkaProducer | None = None
        task: asyncio.Task[None] | None = None
        try:
            dlq = await start_producer(bootstrap, f"{group}-dlq")
            task = asyncio.create_task(run_consumer(bootstrap, group, topics, make_processor(dlq)))
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
