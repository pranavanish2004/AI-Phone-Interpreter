"""
RedisStreamBroker: concrete implementation of MessageBroker backed by Redis
Streams (XADD/XREADGROUP/XACK).

Why Redis Streams specifically (vs plain Redis pub/sub):
    Plain Redis pub/sub is fire-and-forget - if no consumer is connected at
    the moment a message is published, it's lost forever. That's dangerous
    for us: if speech_service briefly restarts mid-call, we cannot afford to
    silently drop an audio chunk. Redis Streams persist messages in a log
    (like a lightweight Kafka) and support consumer groups with
    acknowledgement, so a crashed consumer can resume from where it left off.
"""

import json
import logging
from typing import Any, AsyncIterator

import redis.asyncio as redis

from .broker import MessageBroker

logger = logging.getLogger(__name__)


class RedisStreamBroker(MessageBroker):
    def __init__(self, redis_url: str):
        self._redis_url = redis_url
        self._client: redis.Redis | None = None

    async def connect(self) -> None:
        """
        Lazily establish the connection. Called once at service startup
        (see each service's main.py `lifespan` in later phases).
        """
        self._client = redis.from_url(self._redis_url, decode_responses=True)
        await self._client.ping()
        logger.info("Connected to Redis at %s", self._redis_url)

    async def disconnect(self) -> None:
        if self._client:
            await self._client.aclose()

    def _require_client(self) -> redis.Redis:
        if self._client is None:
            raise RuntimeError(
                "RedisStreamBroker.connect() must be called before use. "
                "This is typically done in the service's startup lifespan."
            )
        return self._client

    async def publish(self, stream: str, payload: dict[str, Any]) -> str:
        client = self._require_client()
        # Redis Streams field values must be strings/bytes, so we serialize
        # the whole payload as one JSON string under a single "data" field
        # rather than flattening nested Pydantic objects into Redis fields.
        message_id = await client.xadd(stream, {"data": json.dumps(payload)})
        return message_id

    async def consume(
        self, stream: str, consumer_group: str, consumer_name: str
    ) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        client = self._require_client()

        # Create the consumer group if it doesn't exist yet. mkstream=True
        # means the stream itself will be created if this is the very first
        # consumer to touch it (avoids a "no such stream" race at startup).
        try:
            await client.xgroup_create(stream, consumer_group, id="0", mkstream=True)
        except redis.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise  # group already exists - safe to ignore, anything else re-raise

        while True:
            # ">" means "only new messages I haven't seen", block=5000ms
            # avoids a tight busy-loop while still being responsive.
            response = await client.xreadgroup(
                groupname=consumer_group,
                consumername=consumer_name,
                streams={stream: ">"},
                count=10,
                block=5000,
            )
            if not response:
                continue  # timed out waiting - loop again (keeps stream "live")

            for _stream_name, messages in response:
                for message_id, fields in messages:
                    payload = json.loads(fields["data"])
                    yield message_id, payload

    async def acknowledge(self, stream: str, consumer_group: str, message_id: str) -> None:
        client = self._require_client()
        await client.xack(stream, consumer_group, message_id)
