"""
User ORM model - mirrors the `users` table from database/schema.sql exactly.

Why mirror an existing SQL table instead of letting SQLAlchemy define the
schema from scratch: schema.sql is what actually runs against Postgres
(via docker-entrypoint-initdb.d, Phase 1). This model must match it
field-for-field, or Alembic's autogenerate (used below) will produce a
migration that fights the bootstrap SQL. Going forward, schema changes
should happen via Alembic migrations, with schema.sql treated as the
one-time bootstrap for local dev.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    phone_number: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    preferred_language: Mapped[str] = mapped_column(String(10), nullable=False, default="en")
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
