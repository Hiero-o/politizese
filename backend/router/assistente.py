import logging

from fastapi import APIRouter, HTTPException

from backend.schemas.assistente import (
    AssistenteChatRequest,
    AssistenteChatResponse,
    AssistenteStatusResponse,
    AssistenteToolUse,
)
from backend.services.assistente import (
    AssistenteConfigurationError,
    limpar_sessao,
    responder_mensagem,
    status_assistente,
)
from src.agents.react_agent import AgentExecutionError


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/assistente",
    tags=["Assistente virtual"],
)


@router.get(
    "/status",
    response_model=AssistenteStatusResponse,
    summary="Verificar a configuração do assistente",
)
def verificar_status():
    return status_assistente()


@router.post(
    "/chat",
    response_model=AssistenteChatResponse,
    summary="Enviar uma mensagem ao assistente do Politize-se",
)
def conversar(request: AssistenteChatRequest):
    try:
        result = responder_mensagem(
            session_id=request.session_id,
            message=request.message,
        )

        return AssistenteChatResponse(
            session_id=request.session_id,
            answer=result.answer,
            sources=result.sources,
            tools_used=[
                AssistenteToolUse(
                    name=entry.action,
                    status=entry.status,
                    duration_seconds=entry.duration_seconds,
                )
                for entry in result.trace
                if entry.action not in {
                    "guardrail_scope",
                    "guardrail_moderation",
                }
            ],
            tool_calls_count=result.tool_calls_count,
            total_duration_seconds=result.total_duration_seconds,
        )

    except (AssistenteConfigurationError, AgentExecutionError) as error:
        logger.exception("Falha ao executar o assistente.")
        raise HTTPException(
            status_code=503,
            detail=str(error),
        ) from error

    except ValueError as error:
        raise HTTPException(
            status_code=422,
            detail=str(error),
        ) from error

    except Exception as error:
        logger.exception("Erro inesperado na conversa com o assistente.")
        raise HTTPException(
            status_code=500,
            detail="Ocorreu um erro inesperado ao processar sua mensagem.",
        ) from error


@router.delete(
    "/sessoes/{session_id}",
    status_code=204,
    summary="Limpar o histórico de uma conversa",
)
def excluir_sessao(session_id: str):
    from uuid import UUID

    try:
        parsed_id = UUID(session_id)
    except ValueError as error:
        raise HTTPException(
            status_code=422,
            detail="Identificador de sessão inválido.",
        ) from error

    limpar_sessao(parsed_id)
    return None
