"""Recuperador híbrido do Politizese: ChromaDB + BM25 global + RRF."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any, Literal

from langchain_core.callbacks.manager import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import ConfigDict, Field

from src.core.config import Settings
from src.rag.lexical_index import (
    DEFAULT_LEGAL_TREE_PATH,
    LegalBM25Index,
    load_legal_bm25_index,
)
from src.rag.vector_store import create_vector_store


DEFAULT_TOP_K = 4
DEFAULT_CANDIDATE_K = 48
DEFAULT_LEXICAL_CANDIDATE_K = 120
DEFAULT_RRF_CONSTANT = 60

# A coleção limpa foi criada e validada separadamente da coleção anterior.
DEFAULT_COLLECTION_NAME = "constituicao_legal_clean_v2"


def _get_source_node_id(document: Document) -> str:
    """Retorna o identificador estável da unidade jurídica."""

    metadata = document.metadata or {}
    source_node_id = metadata.get("source_node_id") or metadata.get("chunk_id")

    if not source_node_id:
        raise ValueError(
            "Documento recuperado sem source_node_id ou chunk_id."
        )

    return str(source_node_id)


def _reciprocal_rank_fusion(
    semantic_documents: list[Document],
    lexical_results: list[tuple[float, Document]],
    *,
    top_k: int,
    rrf_constant: int = DEFAULT_RRF_CONSTANT,
) -> list[Document]:
    """Combina rankings independentes usando Reciprocal Rank Fusion.

    Cada unidade jurídica contribui no máximo uma vez por estratégia. Quando
    uma unidade aparece nos dois rankings, seus votos são somados. O documento
    lexical (texto integral da unidade) é preferido em caso de duplicidade com
    um fragmento semântico, pois mantém o texto jurídico completo.
    """

    if top_k <= 0:
        raise ValueError("top_k precisa ser maior que zero.")
    if rrf_constant <= 0:
        raise ValueError("rrf_constant precisa ser maior que zero.")

    fused: dict[str, dict[str, Any]] = {}

    def add_result(
        document: Document,
        *,
        source: str,
        rank: int,
        raw_score: float | None = None,
    ) -> None:
        if not document.page_content.strip():
            return

        node_id = _get_source_node_id(document)
        entry = fused.get(node_id)

        if entry is None:
            entry = {
                "document": document,
                "rrf_score": 0.0,
                "sources": set(),
                "semantic_rank": None,
                "lexical_rank": None,
                "bm25_score": None,
                "best_rank": rank,
            }
            fused[node_id] = entry

        # Um mesmo nó pode aparecer em vários fragmentos do ChromaDB.
        # Contabilizamos somente sua primeira ocorrência em cada ranking.
        rank_key = f"{source}_rank"
        if entry[rank_key] is not None:
            return

        entry[rank_key] = rank
        entry["rrf_score"] += 1.0 / (rrf_constant + rank)
        entry["sources"].add(source)
        entry["best_rank"] = min(entry["best_rank"], rank)

        if source == "lexical":
            entry["bm25_score"] = raw_score
            # BM25 contém a unidade completa; substitui eventual fragmento.
            if len(document.page_content) > len(entry["document"].page_content):
                entry["document"] = document

    for rank, document in enumerate(semantic_documents, start=1):
        add_result(
            document,
            source="semantic",
            rank=rank,
        )

    for rank, (score, document) in enumerate(lexical_results, start=1):
        add_result(
            document,
            source="lexical",
            rank=rank,
            raw_score=float(score),
        )

    ranked_entries = sorted(
        fused.items(),
        key=lambda item: (
            -item[1]["rrf_score"],
            item[1]["best_rank"],
            item[0],
        ),
    )

    results: list[Document] = []

    for node_id, entry in ranked_entries[:top_k]:
        original = entry["document"]
        metadata = dict(original.metadata or {})
        metadata["source_node_id"] = node_id
        metadata["retrieval_sources"] = sorted(entry["sources"])
        metadata["semantic_rank"] = entry["semantic_rank"]
        metadata["lexical_rank"] = entry["lexical_rank"]
        metadata["bm25_score"] = (
            round(entry["bm25_score"], 6)
            if entry["bm25_score"] is not None
            else None
        )
        metadata["rrf_score"] = round(entry["rrf_score"], 8)

        results.append(
            Document(
                page_content=original.page_content,
                metadata=metadata,
            )
        )

    return results


class PolitizeseRetriever(BaseRetriever):
    """Retriever que une busca vetorial e BM25 independente via RRF."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    vector_store: Any = Field(exclude=True, repr=False)
    lexical_index: LegalBM25Index = Field(exclude=True, repr=False)

    k: int = Field(default=DEFAULT_TOP_K, ge=1)
    candidate_k: int = Field(default=DEFAULT_CANDIDATE_K, ge=1)
    lexical_candidate_k: int = Field(
        default=DEFAULT_LEXICAL_CANDIDATE_K,
        ge=1,
    )
    rrf_constant: int = Field(default=DEFAULT_RRF_CONSTANT, ge=1)

    def search_with_queries(
    self,
    semantic_query: str,
    lexical_query: str,
) -> list[Document]:
        """
        Executa busca semântica e lexical usando consultas independentes.

        Args:
            semantic_query: consulta enviada ao ChromaDB.
            lexical_query: consulta enviada ao BM25.

        Returns:
            Documentos combinados por Reciprocal Rank Fusion.
        """

        if not isinstance(semantic_query, str) or not semantic_query.strip():
            raise ValueError("A consulta semântica não pode estar vazia.")

        if not isinstance(lexical_query, str) or not lexical_query.strip():
            raise ValueError("A consulta lexical não pode estar vazia.")

        semantic_documents = self.vector_store.similarity_search(
            semantic_query,
            k=self.candidate_k,
        )

        lexical_results = self.lexical_index.search(
            lexical_query,
            top_k=self.lexical_candidate_k,
        )

        return _reciprocal_rank_fusion(
            semantic_documents,
            lexical_results,
            top_k=self.k,
            rrf_constant=self.rrf_constant,
        )

    def _get_relevant_documents(
        self,
        query: str,
        *,
        run_manager: CallbackManagerForRetrieverRun,
    ) -> list[Document]:
        """
        Mantém compatibilidade com a interface padrão do LangChain.

        Quando recebe uma única consulta, utiliza-a nas duas estratégias.
        """

        del run_manager

        return self.search_with_queries(
            semantic_query=query,
            lexical_query=query,
        )


def create_retriever(
    provider: Literal["local", "cloud", "auto"] | None = None,
    k: int = DEFAULT_TOP_K,
    candidate_k: int = DEFAULT_CANDIDATE_K,
    lexical_candidate_k: int = DEFAULT_LEXICAL_CANDIDATE_K,
    rrf_constant: int = DEFAULT_RRF_CONSTANT,
    settings: Settings | None = None,
    collection_name: str = DEFAULT_COLLECTION_NAME,
    legal_tree_path: str | Path = DEFAULT_LEGAL_TREE_PATH,
) -> tuple[PolitizeseRetriever, str]:
    """Inicializa ChromaDB e o índice BM25 global do Politizese."""

    if k <= 0:
        raise ValueError("O parâmetro k precisa ser maior que zero.")
    if candidate_k <= 0:
        raise ValueError("candidate_k precisa ser maior que zero.")
    if lexical_candidate_k <= 0:
        raise ValueError("lexical_candidate_k precisa ser maior que zero.")
    if rrf_constant <= 0:
        raise ValueError("rrf_constant precisa ser maior que zero.")
    if not collection_name or not collection_name.strip():
        raise ValueError("O nome da coleção não pode estar vazio.")

    vector_store, selected_provider = create_vector_store(
        provider=provider,
        collection_name=collection_name,
        settings=settings,
    )

    collection_count = vector_store._collection.count()
    if collection_count <= 0:
        raise RuntimeError(
            f"A coleção ChromaDB '{vector_store._collection.name}' está vazia. "
            "Confira o collection_name e execute a indexação correta."
        )

    lexical_index = load_legal_bm25_index(legal_tree_path)

    retriever = PolitizeseRetriever(
        vector_store=vector_store,
        lexical_index=lexical_index,
        k=k,
        candidate_k=candidate_k,
        lexical_candidate_k=lexical_candidate_k,
        rrf_constant=rrf_constant,
    )

    print(
        "[RETRIEVER] Recuperação híbrida inicializada.\n"
        f"Coleção vetorial: {vector_store._collection.name}\n"
        f"Documentos semânticos: {collection_count}\n"
        f"Unidades no BM25 global: {lexical_index.doc_count}\n"
        f"Candidatos semânticos: {candidate_k}\n"
        f"Candidatos lexicais: {lexical_candidate_k}\n"
        f"RRF constant: {rrf_constant}\n"
        f"Candidatos finais: {k}"
    )

    return retriever, selected_provider
