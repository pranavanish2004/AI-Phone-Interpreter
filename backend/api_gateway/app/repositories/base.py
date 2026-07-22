"""
Generic base repository.

Why a base class now, with no concrete repository yet:
    Phase 4 introduces `UserRepository`, and later phases introduce
    `CallRepository`, `ConversationRepository`. All of them share the same
    basic CRUD shape (get by id, create, delete) on top of a SQLAlchemy
    async session. Defining that shared shape ONCE here means each concrete
    repository only implements what's actually specific to it (e.g.
    `UserRepository.get_by_phone_number`), rather than every repository
    reimplementing `get_by_id` slightly differently.

    This is the Repository pattern: route handlers and service-layer code
    depend on repository methods, never on raw SQLAlchemy queries directly.
    That keeps SQL/ORM specifics out of business logic and makes business
    logic testable with a fake/in-memory repository instead of a real DB.
"""

from typing import Generic, TypeVar
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    def __init__(self, session: AsyncSession, model: type[ModelType]):
        self._session = session
        self._model = model

    async def get_by_id(self, id_: UUID) -> ModelType | None:
        result = await self._session.execute(
            select(self._model).where(self._model.id == id_)  # type: ignore[attr-defined]
        )
        return result.scalar_one_or_none()

    async def add(self, entity: ModelType) -> ModelType:
        self._session.add(entity)
        await self._session.flush()  # assigns DB-generated fields (id, created_at)
        # without committing yet - lets the calling service layer control
        # transaction boundaries, e.g. wrapping multiple repository calls
        # in one atomic commit.
        return entity

    async def delete(self, entity: ModelType) -> None:
        await self._session.delete(entity)
        await self._session.flush()
