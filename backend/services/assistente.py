"""Serviço de aplicação para o assistente conversacional do Politize-se."""

from __future__ import annotations

from threading import Lock
from uuid import UUID

from langchain_core.messages import BaseMessage

from src.agents.react_agent import (
    AgentExecutionError,
    PolitizeseReActAgent,
    build_react_agent,
)
from src.chain.memory import get_session_history
from src.core.config import get_settings


_AGENT: PolitizeseReActAgent | None = None
_AGENT_LOCK = Lock()
_MAX_HISTORY_MESSAGES = 12
_MAX_STORED_MESSAGES = 20


class AssistenteConfigurationError(RuntimeError):
    """Configuração local do assistente inválida ou indisponível."""


def obter_agente() -> PolitizeseReActAgent:
    """Inicializa o agente uma única vez, na primeira solicitação."""

    global _AGENT

    if _AGENT is not None:
        return _AGENT

    with _AGENT_LOCK:
        if _AGENT is not None:
            return _AGENT

        settings = get_settings()

        if settings.ollama_provider != "local":
            raise AssistenteConfigurationError(
                "O assistente do Politize-se está configurado para modelos locais. "
                "Defina OLLAMA_PROVIDER=local no arquivo .env."
            )

        try:
            agent, _selected_provider = build_react_agent(
                provider="local",
                settings=settings,
                max_tool_calls=6,
                enable_reranker=True,
                rerank_top_k=8,
            )
        except Exception as error:
            raise AssistenteConfigurationError(
                "Não foi possível inicializar o agente. Verifique se o Ollama "
                "está ativo, se os modelos configurados estão instalados e se "
                "a coleção ChromaDB esperada existe."
            ) from error

        _AGENT = agent
        return _AGENT


def responder_mensagem(
    session_id: UUID,
    message: str,
):
    """Executa uma pergunta com o histórico de sua sessão."""

    agent = obter_agente()
    history = get_session_history(str(session_id))

    previous_messages: list[BaseMessage] = list(
        history.messages[-_MAX_HISTORY_MESSAGES:]
    )

    try:
        result = agent.invoke(
            message,
            history=previous_messages,
        )
    except AgentExecutionError:
        # Não registra uma interação que terminou em erro técnico.
        raise

    # Não persiste entradas bloqueadas: isso evita manter CPF, telefone
    # ou e-mail no histórico depois que o guardrail sinaliza a ocorrência.
    was_blocked = any(
        entry.action.startswith("guardrail_")
        for entry in result.trace
    )

    # Persiste apenas mensagens de usuário e assistente. As mensagens
    # internas de tool call permanecem no trace, não no histórico conversacional.
    if not was_blocked:
        history.add_user_message(message)
        history.add_ai_message(result.answer)

    if len(history.messages) > _MAX_STORED_MESSAGES:
        recent_messages = list(history.messages[-_MAX_STORED_MESSAGES:])
        history.clear()
        for chat_message in recent_messages:
            history.add_message(chat_message)

    return result


def limpar_sessao(session_id: UUID) -> None:
    """Remove a memória em processo de uma conversa."""

    from src.chain.memory import historicos

    historicos.pop(str(session_id), None)


def status_assistente() -> dict[str, str]:
    """Retorna informações de configuração sem iniciar modelos pesados."""

    settings = get_settings()
    initialized = _AGENT is not None

    return {
        "status": "ready" if initialized else "not_initialized",
        "provider": settings.ollama_provider,
        "model": settings.llm_model,
        "message": (
            "Assistente inicializado e pronto para conversar."
            if initialized
            else "O agente será inicializado na primeira mensagem."
        ),
    }
