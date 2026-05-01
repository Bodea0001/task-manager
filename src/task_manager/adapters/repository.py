from abc import ABC
from sqlalchemy.ext.asyncio import AsyncSession


class SQLAlchemyRepository(ABC):
    def __init__(self, session: AsyncSession):
        self.session = session
