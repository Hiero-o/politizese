
"""Orquestra decomposição, reformulação e recuperação híbrida."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, TYPE_CHECKING

from langchain_core.callbacks.manager import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import ConfigDict, Field

if TYPE_CHECKING:
    from src.core.config import Settings


@dataclass(frozen=True)
class SubqueryRetrievalTrace:
    """Registra o processamento de uma subpergunta."""

    index: int
    question: str
    focus: str
    semantic_query: str
    lexical_query: str
    retrieved_count: int


@dataclass(frozen=True)
class IterativeRetrievalTrace:
    """Registra as decisões tomadas durante a recuperação."""

    original_question: str
    is_compound: bool
    decomposition_reason: str
    subqueries: tuple[SubqueryRetrievalTrace, ...]


@dataclass
class IterativeRetrievalResult:
    """Resultado da recuperação acompanhado de sua rastreabilidade."""

    trace: IterativeRetrievalTrace
    documents: list[Document]


def _document_identifier(document: Document) -> str:
    """Obtém o identificador estável de uma unidade jurídica."""

    metadata = document.metadata or {}

    identifier = (
        metadata.get("source_node_id")
        or metadata.get("chunk_id")
        or document.id
    )

    if not identifier:
        raise ValueError(
            "Documento recuperado sem identificador estável."
        )

    return str(identifier)


def _fuse_subquestion_results(
    results: list[tuple[SubqueryRetrievalTrace, list[Document]]],
    *,
    original_question: str,
    is_compound: bool,
    decomposition_reason: str,
    top_k: int,
    rrf_constant: int,
) -> list[Document]:
    """
    Combina os rankings produzidos pelas subperguntas usando RRF.

    Cada subpergunta representa um ranking independente.
    Documentos encontrados em mais de uma subpergunta acumulam
    contribuições, sem duplicação no resultado final.
    """

    if top_k <= 0:
        raise ValueError("top_k precisa ser maior que zero.")

    if rrf_constant <= 0:
        raise ValueError("rrf_constant precisa ser maior que zero.")

    fused: dict[str, dict[str, Any]] = {}

    for trace, documents in results:
        seen_in_ranking: set[str] = set()

        for rank, document in enumerate(documents, start=1):
            identifier = _document_identifier(document)

            # Uma unidade só pode contribuir uma vez
            # dentro do ranking de uma mesma subpergunta.
            if identifier in seen_in_ranking:
                continue

            seen_in_ranking.add(identifier)

            entry = fused.get(identifier)

            if entry is None:
                entry = {
                    "document": document,
                    "score": 0.0,
                    "best_rank": rank,
                    "matches": [],
                    "retrieval_sources": set(),
                }
                fused[identifier] = entry

            entry["score"] += 1.0 / (rrf_constant + rank)

            entry["best_rank"] = min(
                entry["best_rank"],
                rank,
            )

            entry["matches"].append(
                {
                    "index": trace.index,
                    "question": trace.question,
                    "focus": trace.focus,
                    "rank": rank,
                }
            )

            sources = (
                document.metadata.get("retrieval_sources") or []
            )

            entry["retrieval_sources"].update(sources)

            # Prefere preservar o documento com texto mais completo.
            current_document = entry["document"]

            if len(document.page_content) > len(
                current_document.page_content
            ):
                entry["document"] = document

    ranked_entries = sorted(
        fused.items(),
        key=lambda item: (
            -item[1]["score"],
            item[1]["best_rank"],
            item[0],
        ),
    )

    final_documents: list[Document] = []

    for identifier, entry in ranked_entries[:top_k]:
        original = entry["document"]
        metadata = dict(original.metadata or {})

        metadata["source_node_id"] = identifier

        metadata["original_question"] = original_question
        metadata["decomposition_is_compound"] = is_compound
        metadata["decomposition_reason"] = decomposition_reason

        metadata["matched_subquestions"] = entry["matches"]
        metadata["matched_subquestion_count"] = len(
            entry["matches"]
        )

        metadata["subquestion_rrf_score"] = round(
            entry["score"],
            8,
        )

        if entry["retrieval_sources"]:
            metadata["retrieval_sources"] = sorted(
                entry["retrieval_sources"]
            )

        final_documents.append(
            Document(
                page_content=original.page_content,
                metadata=metadata,
            )
        )

    return final_documents


class PolitizeseIterativeRetriever(BaseRetriever):
    """
    Integra Question Decomposer, Query Rewriter e retriever híbrido.

    O resultado é uma lista deduplicada de documentos jurídicos,
    com rastreabilidade das subperguntas que recuperaram cada unidade.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    base_retriever: Any = Field(
        exclude=True,
        repr=False,
    )

    decomposer: Any = Field(
        exclude=True,
        repr=False,
    )

    rewriter: Any = Field(
        exclude=True,
        repr=False,
    )

    top_k: int = Field(
        default=48,
        ge=1,
    )

    rrf_constant: int = Field(
        default=60,
        ge=1,
    )

    def retrieve_with_trace(
        self,
        question: str,
    ) -> IterativeRetrievalResult:
        """
        Executa a recuperação completa e retorna também o rastreamento.

        A decomposição e a reformulação são feitas uma vez
        por pergunta/subpergunta, respectivamente.
        """

        if not isinstance(question, str):
            raise TypeError("A pergunta precisa ser uma string.")

        original_question = question.strip()

        if not original_question:
            raise ValueError("A pergunta não pode estar vazia.")

        decomposition = self.decomposer.decompose(
            original_question
        )

        if not decomposition.subquestions:
            raise RuntimeError(
                "O Question Decomposer não produziu subperguntas."
            )

        subquery_results = []
        traces = []

        for index, subquestion in enumerate(
            decomposition.subquestions,
            start=1,
        ):
            # 1. Reformula a subpergunta.
            rewritten = self.rewriter.rewrite(
                subquestion.question
            )

            # 2. Busca semântica e lexical independentes.
            documents = self.base_retriever.search_with_queries(
                semantic_query=rewritten.semantic_query,
                lexical_query=rewritten.lexical_query,
            )

            trace = SubqueryRetrievalTrace(
                index=index,
                question=subquestion.question,
                focus=subquestion.focus,
                semantic_query=rewritten.semantic_query,
                lexical_query=rewritten.lexical_query,
                retrieved_count=len(documents),
            )

            traces.append(trace)
            subquery_results.append(
                (trace, documents)
            )

        # 3. Consolida os rankings das subperguntas.
        final_documents = _fuse_subquestion_results(
            subquery_results,
            original_question=original_question,
            is_compound=decomposition.is_compound,
            decomposition_reason=decomposition.decomposition_reason,
            top_k=self.top_k,
            rrf_constant=self.rrf_constant,
        )

        return IterativeRetrievalResult(
            trace=IterativeRetrievalTrace(
                original_question=original_question,
                is_compound=decomposition.is_compound,
                decomposition_reason=(
                    decomposition.decomposition_reason
                ),
                subqueries=tuple(traces),
            ),
            documents=final_documents,
        )

    def _get_relevant_documents(
        self,
        query: str,
        *,
        run_manager: CallbackManagerForRetrieverRun,
    ) -> list[Document]:
        """Interface padrão de recuperação do LangChain."""

        del run_manager

        result = self.retrieve_with_trace(query)

        return result.documents


def build_iterative_retriever(
    provider: Literal["local", "cloud", "auto"] | None = "local",
    top_k: int = 48,
    candidate_k: int = 120,
    lexical_candidate_k: int = 120,
    rrf_constant: int = 60,
    settings: "Settings | None" = None,
    collection_name: str = "constituicao_legal_clean_v2",
) -> tuple[PolitizeseIterativeRetriever, str]:
    """
    Inicializa o pipeline integrado do Politizese.

    Os componentes de IA utilizam as configurações do modelo principal.
    O retriever híbrido mantém sua própria configuração de recuperação.
    """

    from src.rag.query_rewriter import build_query_rewriter
    from src.rag.question_decomposer import (
        build_question_decomposer,
    )
    from src.rag.retriever import create_retriever

    base_retriever, selected_provider = create_retriever(
        provider=provider,
        k=top_k,
        candidate_k=candidate_k,
        lexical_candidate_k=lexical_candidate_k,
        rrf_constant=rrf_constant,
        settings=settings,
        collection_name=collection_name,
    )

    decomposer = build_question_decomposer(
        settings=settings
    )

    rewriter = build_query_rewriter(
        settings=settings
    )

    pipeline = PolitizeseIterativeRetriever(
        base_retriever=base_retriever,
        decomposer=decomposer,
        rewriter=rewriter,
        top_k=top_k,
        rrf_constant=rrf_constant,
    )

    return pipeline, selected_provider
