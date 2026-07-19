"""
conversation_service: Phase 1 skeleton.

Right now this service only proves the skeleton wires up correctly:
container builds, starts, joins the docker network, and responds to a
health check. Real business logic for this service arrives in its
dedicated phase (see docs/phase-notes/).
"""

import logging

from fastapi import FastAPI

from shared.logging import configure_logging

SERVICE_NAME = "conversation_service"
configure_logging(service_name=SERVICE_NAME)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="conversation_service",
    description="Part of the AI Phone Interpreter microservices backend",
    version="0.1.0",
)


@app.get("/health")
async def health() -> dict:
    """
    Liveness/readiness probe.

    Docker Compose's healthcheck (see docker-compose.yml) polls this so that
    dependent services only start once their dependencies report healthy -
    this avoids race conditions like api_gateway trying to reach Postgres
    before Postgres has finished initializing.
    """
    logger.info("health check ok")
    return {"service": SERVICE_NAME, "status": "ok"}
