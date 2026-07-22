"""
Health check endpoint - upgraded from Phase 1's "am I alive" stub into a
real readiness check.

Why distinguish liveness from readiness:
    - Liveness ("is the process running at all") - Phase 1's version.
    - Readiness ("can this process actually serve requests right now",
      i.e. can it reach Postgres and Redis) - this phase's version.
    A container orchestrator (Docker Compose's healthcheck now, Kubernetes
    later) uses readiness to decide whether to route traffic to this
    instance. A process that's "alive" but can't reach its database should
    NOT receive traffic - reporting healthy anyway would just turn every
    DB outage into a wave of 500 errors instead of a clean "not ready" the
    load balancer can route around.
"""

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.core.database import check_database_connection
from app.core.redis import check_redis_connection

router = APIRouter()


@router.get("/health")
async def health() -> JSONResponse:
    db_ok = await check_database_connection()
    redis_ok = await check_redis_connection()
    overall_ok = db_ok and redis_ok

    payload = {
        "service": "api_gateway",
        "status": "ok" if overall_ok else "degraded",
        "dependencies": {
            "database": "ok" if db_ok else "unreachable",
            "redis": "ok" if redis_ok else "unreachable",
        },
    }

    # 200 when fully healthy, 503 when a dependency is down - this is what
    # lets the docker-compose healthcheck (and later, k8s readiness probes)
    # correctly detect degraded state rather than reading the 200 status
    # code alone and assuming everything is fine regardless of body content.
    status_code = status.HTTP_200_OK if overall_ok else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(status_code=status_code, content=payload)
