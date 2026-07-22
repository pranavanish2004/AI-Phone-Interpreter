from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, User)

    async def get_by_phone_number(self, phone_number: str) -> User | None:
        result = await self._session.execute(
            select(User).where(User.phone_number == phone_number)
        )
        return result.scalar_one_or_none()
