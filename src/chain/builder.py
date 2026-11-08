
from typing import Any

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables.history import RunnableWithMessageHistory

from src.ai.llm_factory import create_chat_model
from src.chain.memory import get_session_history
from src.core.config import Settings, get_settings


def load_system_prompt(
    settings: Settings | None = None,
) -> str:
    """
    Carrega o prompt principal utilizando o caminho
    definido nas configurações centralizadas.

    Args:
        settings: configurações opcionais da aplicação.

    Returns:
        Conteúdo textual do prompt.
    """

    if settings is None:
        settings = get_settings()

    prompt_path = settings.system_prompt_path

    if not prompt_path.is_file():
        raise FileNotFoundError(
            f"Arquivo de prompt não encontrado: {prompt_path}"
        )

    with prompt_path.open(
        "r",
        encoding="utf-8",
    ) as file:
        system_prompt = file.read().strip()

    if not system_prompt:
        raise ValueError(
            f"O arquivo de prompt está vazio: {prompt_path}"
        )

    return system_prompt


def build_chain(
    settings: Settings | None = None,
):
    """
    Constrói as chains conversacionais com histórico.

    Returns:
        Tuple contendo:
        - Chain com saída textual.
        - Chain com resposta original do modelo (AIMessage).
    """

    if settings is None:
        settings = get_settings()

    # Carrega o prompt principal.
    system_prompt = load_system_prompt(settings)

    # Monta o template de mensagens.
    prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            system_prompt,
        ),
        (
            "placeholder",
            "{history}",
        ),
        (
            "human",
            """
            Contexto dos dados:
            {context}

            Pergunta do usuário:
            {question}
            """,
        ),
    ])

    # Instancia o modelo através da factory.
    llm = create_chat_model(settings=settings)

    # Chain original: retorna AIMessage.
    chain_completa = prompt | llm

    # Chain textual: retorna apenas o conteúdo da resposta.
    parser = StrOutputParser()

    chain = chain_completa | parser

    # Adiciona histórico à chain textual.
    chain_com_memoria = RunnableWithMessageHistory(
        chain,
        get_session_history,
        input_messages_key="question",
        history_messages_key="history",
    )

    # Adiciona histórico à chain original.
    chain_completa_com_memoria = RunnableWithMessageHistory(
        chain_completa,
        get_session_history,
        input_messages_key="question",
        history_messages_key="history",
    )

    return (
        chain_com_memoria,
        chain_completa_com_memoria,
    )


def build_structured_chain(
    schema: Any,
    instrucoes: str,
    settings: Settings | None = None,
):
    """
    Constrói uma chain com saída estruturada.

    Args:
        schema: schema utilizado para validar a saída.
        instrucoes: instruções específicas da tarefa.
        settings: configurações opcionais da aplicação.

    Returns:
        Chain com saída estruturada.
    """

    if settings is None:
        settings = get_settings()

    if not instrucoes or not instrucoes.strip():
        raise ValueError(
            "As instruções da chain estruturada não podem estar vazias."
        )

    # Monta o prompt específico da tarefa.
    prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            f"""
            Siga rigorosamente as instruções abaixo
            ao analisar o contexto e responder.

            Instruções da tarefa:
            {instrucoes}
            """,
        ),
        (
            "human",
            """
            Contexto dos dados:
            {context}

            Pergunta do usuário:
            {question}
            """,
        ),
    ])

    # Reutiliza a mesma factory de modelos.
    llm = create_chat_model(settings=settings)

    # Solicita saída estruturada ao modelo.
    structured_llm = llm.with_structured_output(schema)

    chain = prompt | structured_llm

    return chain
