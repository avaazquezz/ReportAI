import uuid
from typing import Any, Generic, Protocol, TypeVar

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession


class _HasId(Protocol):
    id: Any


ModelType = TypeVar("ModelType", bound=_HasId)


class BaseRepository(Generic[ModelType]):
    """Generic CRUD repository. The only layer in the app allowed to touch the DB directly."""

    def __init__(self, model: type[ModelType], db: AsyncSession) -> None:
        self.model = model
        self.db = db

    def _apply_filters(self, query: Select[Any], filters: dict[str, Any] | None) -> Select[Any]:
        if filters:
            for field, value in filters.items():
                query = query.where(getattr(self.model, field) == value)
        return query

    async def get_by_id(self, id_: uuid.UUID) -> ModelType | None:
        result = await self.db.execute(select(self.model).where(self.model.id == id_))
        return result.scalar_one_or_none()

    async def list(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
        filters: dict[str, Any] | None = None,
    ) -> list[ModelType]:
        query = self._apply_filters(select(self.model), filters)
        query = query.offset(skip).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def count(self, *, filters: dict[str, Any] | None = None) -> int:
        query = self._apply_filters(select(func.count()).select_from(self.model), filters)
        result = await self.db.execute(query)
        return int(result.scalar_one())

    async def create(self, **kwargs: Any) -> ModelType:
        obj = self.model(**kwargs)
        self.db.add(obj)
        await self.db.flush()
        await self.db.refresh(obj)
        return obj

    async def update(self, obj: ModelType, **kwargs: Any) -> ModelType:
        for field, value in kwargs.items():
            setattr(obj, field, value)
        await self.db.flush()
        await self.db.refresh(obj)
        return obj

    async def delete(self, obj: ModelType) -> None:
        await self.db.delete(obj)
        await self.db.flush()
