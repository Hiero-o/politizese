"""Pipeline RAG em LCEL com recuperação híbrida e histórico opcional."""

from __future__ import annotations

from operator import itemgetter
from typing import Literal

from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda, RunnableWithMessageHistory

from src.ai.llm_factory import create_chat_model
from src.ai.prompt_loader import load_prompt
from src.chain.memory import get_session_history
from src.core.config import Settings, get_settings
from src.rag.iterative_retriever import build_iterative_retriever


def format_retrieved_documents(documents: list[Document]) -> str:
    """Formata os trechos recuperados com doc_id explícito para citação."""

    formatted = []
    for document in documents:
        metadata = document.metadata or {}
        doc_id = (
            metadata.get("source_node_id")
            or metadata.get("chunk_id")
            or document.id
        )
        if not doc_id:
            continue

        article = metadata.get("article_number")
        part = metadata.get("document_part")
        header = f"[doc_id: {doc_id}]"
        if part:
            header += f" [parte: {part}]"
        if article:
            header += f" [artigo: {article}]"
        formatted.append(f"{header}\n{document.page_content.strip()}")

    if not formatted:
        return "Nenhuma evidência foi recuperada para esta pergunta."

    return "\n\n---\n\n".join(formatted)


def build_lcel_rag_pipeline(
    settings: Settings | None = None,
    *,
    provider: Literal["local", "cloud", "auto"] = "local",
    collection_name: str = "constituicao_legal_clean_v2",
    top_k: int = 8,
    enable_reranker: bool = False,
):
    """Monta retriever → prompt com contexto → ChatOllama → parser (LCEL).

    A saída contém os doc_id do contexto para que o modelo cite as evidências.
    O histórico é associado pelo ``session_id`` passado em ``configurable``.
    """

    if settings is None:
        settings = get_settings()

    retriever, selected_provider = build_iterative_retriever(
        provider=provider,
        top_k=top_k,
        candidate_k=max(top_k * 8, 48),
        lexical_candidate_k=max(top_k * 12, 80),
        settings=settings,
        collection_name=collection_name,
        enable_reranker=enable_reranker,
        rerank_top_k=top_k,
        reranker_device="cpu",
    )

    system_prompt = load_prompt(task="rag_answer")
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            ("placeholder", "{history}"),
            (
                "human",
                "Pergunta do cidadão:\n{question}\n\n"
                "Evidências recuperadas:\n<context>\n{context}\n</context>\n\n"
                "Responda somente com base nas evidências. Cite os doc_id "
                "entre colchetes e informe quando o contexto não for suficiente.",
            ),
        ]
    )

    llm = create_chat_model(settings=settings)

    # LCEL: pergunta → retriever híbrido → contexto formatado → prompt → LLM → texto.
    rag_chain = (
        {
            "question": itemgetter("question"),
            "history": itemgetter("history"),
            "context": (
                itemgetter("question")
                | retriever
                | RunnableLambda(format_retrieved_documents)
            ),
        }
        | prompt
        | llm
        | StrOutputParser()
    )

    chain_with_history = RunnableWithMessageHistory(
        rag_chain,
        get_session_history,
        input_messages_key="question",
        history_messages_key="history",
    )

    return chain_with_history, selected_provider
