"""
MessageBroker: abstract interface for publishing/consuming events between
services.

Why an interface instead of using redis.asyncio directly everywhere:
    This is the Dependency Inversion Principle (the "D" in SOLID) in action.
    Every service's business logic will depend on THIS abstract class, not on
    Redis specifically. Today the concrete implementation is
    RedisStreamBroker. If we later need to migrate to Kafka or NATS for
    higher throughput, we write a new KafkaBroker class that implements the
    same interface, swap it in via dependency injection (see each service's
    `core/config.py` in later phases), and none of the business logic
    changes. Without this abstraction, "redis.xadd(...)" calls would be
    scattered across 7 services, and a broker migration would touch all of
    them.
"""

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator


class MessageBroker(ABC):
    """Abstract contract for a streaming pub/sub message broker."""

    @abstractmethod
    async def publish(self, stream: str, payload: dict[str, Any]) -> str:
        """
        Publish a message onto a named stream.

        Args:
            stream: logical channel name, e.g. "audio.chunks.raw"
            payload: JSON-serializable dict (typically a Pydantic model's
                     .model_dump())

        Returns:
            The broker-assigned message ID (useful for acknowledgement/retry
            logic).
        """
        raise NotImplementedError

    @abstractmethod
    async def consume(
        self, stream: str, consumer_group: str, consumer_name: str
    ) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        """
        Consume messages from a stream as an async generator, yielding
        (message_id, payload) tuples.

        Using a consumer_group means multiple instances of the same service
        (e.g. 3 replicas of speech_service under load) can split the work of
        consuming a stream without processing the same message twice - this
        is essential for horizontal scaling (a functional requirement: low
        latency under load).
        """
        raise NotImplementedError

    @abstractmethod
    async def acknowledge(self, stream: str, consumer_group: str, message_id: str) -> None:
        """
        Mark a message as successfully processed. Unacknowledged messages
        can be reclaimed and retried if a consumer crashes mid-processing -
        this gives us at-least-once delivery guarantees.
        """
        raise NotImplementedError
