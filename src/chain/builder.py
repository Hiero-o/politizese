
from typing import Any

from langchain_core.messages import SystemMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables.history import RunnableWithMessageHistory

from src.ai.llm_factory import create_chat_model
from src.ai.prompt_loader import load_prompt
from src.chain.memory import get_session_history
from src.core.config import Settings, get_settings


def build_chain(
    settings: Settings | None = None,
    *,
    task: str = "rag_answer",
    style: str | None = None,
):
    """
    Constrói uma chain conversacional utilizando os prompts
    modulares do Politize-se.

    A composição do prompt é feita pelo Prompt Loader:

        Core + Task + Style (opcional)

    Args:
        settings: configurações opcionais da aplicação.
        task: nome do arquivo XML da tarefa.
        style: nome do arquivo XML do estilo.

    Returns:
        Tupla contendo:
        - Chain com saída textual.
        - Chain com resposta original do modelo (AIMessage).
    """

    if settings is None:
        settings = get_settings()

    # 1. Carrega e combina os prompts.
    system_prompt = load_prompt(
        task=task,
        style=style,
    )

    # 2. Cria a mensagem de sistema.
    # SystemMessage evita que o conteúdo XML seja
    # interpretado como um template de variáveis.
    system_message = SystemMessage(
        content=system_prompt
    )

    # 3. Monta o template conversacional.
    prompt = ChatPromptTemplate.from_messages([
        system_message,

        ("placeholder", "{history}"),

        (
            "human",
            """
            <user_context>
                <retrieved_documents>
                    {context}
                </retrieved_documents>

                <user_question>
                    {question}
                </user_question>
            </user_context>
            """,
        ),
    ])

    # 4. Instancia o modelo centralizado.
    llm = create_chat_model(
        settings=settings
    )

    # 5. Constrói as chains.
    chain_completa = prompt | llm

    chain = chain_completa | StrOutputParser()

    # 6. Adiciona histórico à chain textual.
    chain_com_memoria = RunnableWithMessageHistory(
        chain,
        get_session_history,
        input_messages_key="question",
        history_messages_key="history",
    )

    # 7. Adiciona histórico à chain original.
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
    *,
    task: str = "information_extraction",
):
    """
    Constrói uma chain com saída estruturada.

    Utiliza o Core e a Task informada, permitindo
    complementar as instruções específicas da aplicação.

    Args:
        schema: schema Pydantic ou formato estruturado.
        instrucoes: instruções complementares da tarefa.
        settings: configurações opcionais.
        task: nome da Task XML.

    Returns:
        Chain com saída estruturada.
    """

    if settings is None:
        settings = get_settings()

    if not instrucoes or not instrucoes.strip():
        raise ValueError(
            "As instruções complementares não podem estar vazias."
        )

    # 1. Carrega Core + Task.
    system_prompt = load_prompt(
        task=task
    )

    # 2. Separa as instruções complementares.
    messages = [
        SystemMessage(content=system_prompt),

        SystemMessage(
            content=(
                "Instruções complementares da aplicação:\n"
                f"{instrucoes}"
            )
        ),

        (
            "human",
            """
            <user_context>
                <retrieved_documents>
                    {context}
                </retrieved_documents>

                <user_question>
                    {question}
                </user_question>
            </user_context>
            """,
        ),
    ]

    # 3. Cria o template.
    prompt = ChatPromptTemplate.from_messages(
        messages
    )

    # 4. Instancia o modelo.
    llm = create_chat_model(
        settings=settings
    )

    # 5. Configura a saída estruturada.
    structured_llm = llm.with_structured_output(
        schema
    )

    # 6. Constrói a chain.
    return prompt | structured_llm
