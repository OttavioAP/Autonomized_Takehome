"""ActivityTool: the common interface JiraTool/GithubTool both implement
(chat.md's Tools section). Framework-agnostic - no FastAPI imports, session/
credentials passed explicitly, never self-fetched.
"""

from abc import ABC, abstractmethod
from typing import Any
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.chat import ActivityItem
from app.services.llm_router import ToolDefinition


class ActivityTool(ABC):
    name: str
    description: str
    Params: type[BaseModel]

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(name=self.name, description=self.description, parameters=self.Params)

    @abstractmethod
    async def execute(
        self,
        session: AsyncSession,
        conversation_id: UUID,
        params: BaseModel,
        **credentials: Any,
    ) -> list[ActivityItem]: ...
