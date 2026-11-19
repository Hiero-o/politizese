from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.agents.agent_schemas import AgentSource


class AssistenteChatRequest(BaseModel):
    """Mensagem enviada à conversa do assistente."""

    model_config = ConfigDict(extra="forbid")

    session_id: UUID
    message: str = Field(min_length=1, max_length=2000)

    @field_validator("message")
    @classmethod
    def normalize_message(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("A mensagem não pode estar vazia.")
        return value


class AssistenteToolUse(BaseModel):
    """Resumo de uma ferramenta utilizada durante a resposta."""

    name: str
    status: Literal["success", "error", "blocked"]
    duration_seconds: float = Field(ge=0)


class AssistenteChatResponse(BaseModel):
    """Resposta do assistente com referências rastreáveis."""

    session_id: UUID
    answer: str
    sources: list[AgentSource] = Field(default_factory=list)
    tools_used: list[AssistenteToolUse] = Field(default_factory=list)
    tool_calls_count: int = Field(ge=0, le=6)
    total_duration_seconds: float = Field(ge=0)


class AssistenteStatusResponse(BaseModel):
    status: Literal["ready", "not_initialized"]
    provider: str
    model: str
    message: str
