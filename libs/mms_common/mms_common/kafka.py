"""Thin aiokafka wrappers with the TRD §8.1 settings. Business logic stays out of here:
the relay is in `outbox`, the retry and DLQ rules in `consumer`."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from mms_common.consumer import EventProcessor


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
