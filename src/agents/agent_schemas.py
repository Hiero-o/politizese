
"""Schemas de entrada, saída e rastreabilidade do agente ReAct."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class AgentTraceEntry(BaseModel):
    """Registro observável de uma ação do agente."""

    model_config = ConfigDict(extra="forbid")

    step: int = Field(ge=1)
    decision_summary: str
    action: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    observation: str
    status: Literal["success", "error", "blocked"]
    duration_seconds: float = Field(ge=0)


class AgentTimingEvent(BaseModel):
    """Medição individual de uma etapa da execução."""

    model_config = ConfigDict(extra="forbid")

    step: int = Field(ge=1)

    stage: Literal[
        "tool_selection",
        "post_tool_decision",
        "tool_execution",
        "initial_response",
        "final_answer",
        "final_synthesis",
        "tool_blocked",
    ]

    name: str

    duration_seconds: float = Field(ge=0)

    # Métricas disponibilizadas pelo Ollama, quando presentes.
    ollama_metrics: dict[str, int | float] = Field(
        default_factory=dict
    )


class AgentRunResult(BaseModel):
    """Resultado completo de uma execução do agente."""

    model_config = ConfigDict(extra="forbid")

    question: str
    answer: str

    tool_calls_count: int = Field(ge=0, le=6)
    max_tool_calls: int = Field(default=6, ge=1, le=6)
    blocked_tool_calls: int = Field(default=0, ge=0)

    tool_limit_reached: bool = False

    # Tempos acumulados.
    total_duration_seconds: float = Field(ge=0)
    llm_duration_seconds: float = Field(ge=0)
    tool_duration_seconds: float = Field(ge=0)

    trace: list[AgentTraceEntry] = Field(default_factory=list)

    timing_events: list[AgentTimingEvent] = Field(
        default_factory=list
    )
