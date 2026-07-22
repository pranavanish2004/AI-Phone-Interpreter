"""
Aggregates every BUSINESS route module under API version 1 (auth, profile,
calls, etc. in later phases).

Health checks are deliberately NOT included here - they're mounted at the
root path in main.py instead. Readiness/liveness probes are infrastructure
concerns, not part of the versioned public API, and existing consumers
(the Phase 1 docker-compose healthcheck, the Flutter app's
HealthCheckService from Phase 2) already call `GET /health` directly. If
health checks lived under `/api/v1/health`, every one of those would need
to change every time we bump the API version - infra checks should be
version-independent.
"""

from fastapi import APIRouter

from app.api.v1.auth import routes as auth_routes

api_router = APIRouter()
api_router.include_router(auth_routes.router, prefix="/auth", tags=["auth"])

# Later phases add: profile, calls, etc.
