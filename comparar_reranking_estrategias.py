from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from time import perf_counter
from typing import Any

import torch
from langchain_core.documents import Document
from sentence_transformers import CrossEncoder

from src.core.config import PROJECT_ROOT
from src.rag.retriever import create_retriever
from src.rag.semantic_retriever import create_semantic_retriever
from src.rag.reranker import PolitizeseCrossEncoderRetriever


# ============================================================
# CONFIGURAÇÕES DO EXPERIMENTO
# ============================================================

DATASET_PATH = (
    PROJECT_ROOT
    / "data"
    / "avaliacoes"
    / "perguntas_constituicao.JSON"
)

OUTPUT_DIRECTORY = (
    PROJECT_ROOT
    / "data"
    / "avaliacoes"
    / "resultados"
)

# Arquivo separado: não sobrescreve os experimentos anteriores.
OUTPUT_FILENAME = "comparacao_reranking_estrategias.json"

PROVIDER = "local"
LEGAL_COLLECTION_NAME = "constituicao_legal"
SEMANTIC_COLLECTION_NAME = "politizese_semantic_aux_v1"

# Recuperação inicial.
CANDIDATE_K = 48
SECTION_K = 8
UNITS_PER_SECTION_K = 8
RRF_CONSTANT = 60

# Cross-Encoder.
RERANKER_MODEL_NAME = "BAAI/bge-reranker-v2-m3"
RERANKER_TOP_K = 4
RERANKER_BATCH_SIZE = 8
RERANKER_MAX_LENGTH = 512

# Métricas após reranking: o Cross-Encoder entrega no máximo 4 docs.
FINAL_K_VALUES = (1, 2, 4)

FRAGMENT_SUFFIX_PATTERN = re.compile(r"-PART-\d+$")
ARTICLE_ID_PATTERN = re.compile(
    r"^(?P<article>.+-ART-\d{4}[A-Z]?)(?:-|$)"
)


# ============================================================
# CARREGAMENTO E VALIDAÇÃO DO DATASET
# ============================================================

def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Arquivo não encontrado: {path}")

    try:
        with path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
    except json.JSONDecodeError as error:
        raise ValueError(
            f"JSON inválido em {path}, linha {error.lineno}, "
            f"coluna {error.colno}: {error.msg}"
        ) from error

    if not isinstance(payload, dict):
        raise ValueError("A raiz do dataset precisa ser um objeto JSON.")

    return payload


def _validate_dataset(dataset: dict[str, Any]) -> list[dict[str, Any]]:
    questions = dataset.get("questions")

    if not isinstance(questions, list) or not questions:
        raise ValueError("O dataset precisa conter perguntas válidas.")

    seen_ids: set[str] = set()

    for index, item in enumerate(questions):
        if not isinstance(item, dict):
            raise ValueError(f"Pergunta inválida na posição {index}.")

        question_id = item.get("id")
        question = item.get("question")

        if not isinstance(question_id, str) or not question_id.strip():
            raise ValueError(f"Pergunta na posição {index} sem ID válido.")

        if question_id in seen_ids:
            raise ValueError(f"ID de pergunta duplicado: {question_id}")
        seen_ids.add(question_id)

        if not isinstance(question, str) or not question.strip():
            raise ValueError(f"Pergunta sem texto válido: {question_id}")

        for field in ("reference_articles", "reference_nodes"):
            values = item.get(field, [])
            if not isinstance(values, list):
                raise ValueError(f"{field} precisa ser uma lista: {question_id}")
            if any(not isinstance(value, str) or not value.strip() for value in values):
                raise ValueError(f"Referência inválida em {field}: {question_id}")

        if not (item.get("reference_articles") or item.get("reference_nodes")):
            raise ValueError(f"A pergunta {question_id} não possui referências.")

    return questions


# ============================================================
# IDENTIFICADORES E MÉTRICAS
# ============================================================

def _get_node_id(metadata: dict[str, Any]) -> str:
    node_id = metadata.get("source_node_id") or metadata.get("chunk_id")

    if not isinstance(node_id, str) or not node_id.strip():
        raise ValueError("Documento recuperado sem identificador jurídico.")

    return FRAGMENT_SUFFIX_PATTERN.sub("", node_id)


def _get_article_id(metadata: dict[str, Any], node_id: str) -> str:
    article_id = metadata.get("article_id")

    if isinstance(article_id, str) and article_id.strip():
        return article_id

    match = ARTICLE_ID_PATTERN.match(node_id)
    if match:
        return match.group("article")

    raise ValueError(f"Não foi possível identificar o artigo de {node_id}.")


def _unique_preserving_order(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _extract_ranked_identifiers(
    documents: list[Document],
) -> tuple[list[str], list[str]]:
    node_ids: list[str] = []
    article_ids: list[str] = []

    for document in documents:
        metadata = dict(document.metadata or {})
        node_id = _get_node_id(metadata)
        article_id = _get_article_id(metadata, node_id)
        node_ids.append(node_id)
        article_ids.append(article_id)

    return (
        _unique_preserving_order(node_ids),
        _unique_preserving_order(article_ids),
    )


def _calculate_metrics_at_k(
    retrieved_ids: list[str],
    reference_ids: list[str],
    k: int,
) -> dict[str, float | None]:
    if not reference_ids:
        return {
            "precision": None,
            "recall": None,
            "mrr": None,
            "hit_rate": None,
        }

    ranked_ids = retrieved_ids[:k]
    relevant_ids = set(reference_ids)
    hits = [identifier for identifier in ranked_ids if identifier in relevant_ids]

    first_relevant_rank = next(
        (
            rank
            for rank, identifier in enumerate(ranked_ids, start=1)
            if identifier in relevant_ids
        ),
        None,
    )

    return {
        "precision": round(len(hits) / k, 4),
        "recall": round(len(hits) / len(relevant_ids), 4),
        "mrr": round(1 / first_relevant_rank, 4) if first_relevant_rank else 0.0,
        "hit_rate": 1.0 if hits else 0.0,
    }


def _normalize_reference_nodes(item: dict[str, Any]) -> list[str]:
    return [
        FRAGMENT_SUFFIX_PATTERN.sub("", node_id)
        for node_id in item.get("reference_nodes", [])
    ]


def _calculate_document_metrics(
    documents: list[Document],
    reference_articles: list[str],
    reference_nodes: list[str],
    k_values: tuple[int, ...],
) -> dict[str, Any]:
    node_ids, article_ids = _extract_ranked_identifiers(documents)

    return {
        "article_level": {
            str(k): _calculate_metrics_at_k(article_ids, reference_articles, k)
            for k in k_values
        },
        "legal_unit_level": {
            str(k): _calculate_metrics_at_k(node_ids, reference_nodes, k)
            for k in k_values
        },
    }


def _calculate_full_pool_metrics(
    documents: list[Document],
    reference_articles: list[str],
    reference_nodes: list[str],
) -> dict[str, Any]:
    """Mede a cobertura de todo o conjunto, mesmo quando ele tem 96 docs."""
    node_ids, article_ids = _extract_ranked_identifiers(documents)

    article_k = max(1, len(article_ids))
    node_k = max(1, len(node_ids))

    return {
        "article_level": {
            "unique_retrieved": len(article_ids),
            **_calculate_metrics_at_k(article_ids, reference_articles, article_k),
        },
        "legal_unit_level": {
            "unique_retrieved": len(node_ids),
            **_calculate_metrics_at_k(node_ids, reference_nodes, node_k),
        },
    }


# ============================================================
# FUSÃO E UNIÃO DOS CONJUNTOS
# ============================================================

def _fuse_rankings(
    hybrid_documents: list[Document],
    semantic_documents: list[Document],
    top_k: int = CANDIDATE_K,
) -> list[Document]:
    scores: dict[str, float] = {}
    sources: dict[str, set[str]] = {}
    documents_by_id: dict[str, Document] = {}

    rankings = (
        ("legal_hybrid", hybrid_documents),
        ("semantic", semantic_documents),
    )

    for source_name, documents in rankings:
        seen_in_ranking: set[str] = set()

        for rank, document in enumerate(documents, start=1):
            node_id = _get_node_id(dict(document.metadata or {}))
            if node_id in seen_in_ranking:
                continue
            seen_in_ranking.add(node_id)

            scores[node_id] = scores.get(node_id, 0.0) + (
                1 / (RRF_CONSTANT + rank)
            )
            sources.setdefault(node_id, set()).add(source_name)

            # Quando duplicado, mantém o documento do híbrido como representante.
            if node_id not in documents_by_id or source_name == "legal_hybrid":
                documents_by_id[node_id] = document

    ordered_ids = sorted(
        scores,
        key=lambda node_id: (-scores[node_id], node_id),
    )

    fused_documents: list[Document] = []

    for node_id in ordered_ids[:top_k]:
        original = documents_by_id[node_id]
        metadata = dict(original.metadata or {})
        metadata.update(
            {
                "retrieval_strategy": "rrf_fusion",
                "fusion_rrf_score": round(scores[node_id], 8),
                "retrieved_by": ", ".join(sorted(sources[node_id])),
            }
        )
        fused_documents.append(
            Document(
                id=original.id,
                page_content=original.page_content,
                metadata=metadata,
            )
        )

    return fused_documents


def _union_rankings(
    hybrid_documents: list[Document],
    semantic_documents: list[Document],
) -> list[Document]:
    """Une os dois conjuntos, preservando a ordem híbrido e depois semântico."""
    documents_by_id: dict[str, Document] = {}
    sources_by_id: dict[str, set[str]] = {}

    for source_name, documents in (
        ("legal_hybrid", hybrid_documents),
        ("semantic", semantic_documents),
    ):
        for document in documents:
            node_id = _get_node_id(dict(document.metadata or {}))
            sources_by_id.setdefault(node_id, set()).add(source_name)
            if node_id not in documents_by_id:
                documents_by_id[node_id] = document

    union_documents: list[Document] = []

    for node_id, original in documents_by_id.items():
        metadata = dict(original.metadata or {})
        metadata.update(
            {
                "retrieval_strategy": "hybrid_semantic_union",
                "retrieved_by": ", ".join(sorted(sources_by_id[node_id])),
            }
        )
        union_documents.append(
            Document(
                id=original.id,
                page_content=original.page_content,
                metadata=metadata,
            )
        )

    return union_documents


# ============================================================
# AVALIAÇÃO DE CADA CONJUNTO
# ============================================================

def _evaluate_candidate_set(
    *,
    item: dict[str, Any],
    strategy_name: str,
    candidates: list[Document],
    reranked_documents: list[Document],
    timing: dict[str, float],
) -> dict[str, Any]:
    reference_articles = item.get("reference_articles", [])
    reference_nodes = _normalize_reference_nodes(item)

    candidate_node_ids, candidate_article_ids = _extract_ranked_identifiers(
        candidates
    )
    reranked_node_ids, reranked_article_ids = _extract_ranked_identifiers(
        reranked_documents
    )

    ranked_documents = []
    for rank, document in enumerate(reranked_documents, start=1):
        metadata = dict(document.metadata or {})
        node_id = _get_node_id(metadata)
        article_id = _get_article_id(metadata, node_id)
        ranked_documents.append(
            {
                "rank": rank,
                "node_id": node_id,
                "article_id": article_id,
                "legal_unit": metadata.get("legal_unit"),
                "rerank_score": metadata.get("rerank_score"),
                "retrieved_by": metadata.get("retrieved_by"),
            }
        )

    total_seconds = (
        timing["retrieval_seconds"]
        + timing["pool_construction_seconds"]
        + timing["reranking_seconds"]
    )

    return {
        "id": item["id"],
        "category": item.get("category"),
        "question": item["question"],
        "strategy": strategy_name,
        "reference_articles": reference_articles,
        "reference_nodes": reference_nodes,
        "candidate_count": len(candidates),
        "candidate_article_ids": candidate_article_ids,
        "candidate_node_ids": candidate_node_ids,
        "candidate_pool_metrics": _calculate_full_pool_metrics(
            candidates,
            reference_articles,
            reference_nodes,
        ),
        "reranked_count": len(reranked_documents),
        "reranked_article_ids": reranked_article_ids,
        "reranked_node_ids": reranked_node_ids,
        "reranked_metrics": _calculate_document_metrics(
            reranked_documents,
            reference_articles,
            reference_nodes,
            FINAL_K_VALUES,
        ),
        "reranked_documents": ranked_documents,
        "timing": {
            **{key: round(value, 6) for key, value in timing.items()},
            "total_seconds": round(total_seconds, 6),
        },
    }


def _average(values: list[float]) -> float | None:
    return round(mean(values), 4) if values else None


def _build_strategy_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "questions_evaluated": len(results),
        "average_candidate_count": round(
            mean(item["candidate_count"] for item in results), 2
        ),
        "average_retrieval_seconds": round(
            mean(item["timing"]["retrieval_seconds"] for item in results), 6
        ),
        "average_pool_construction_seconds": round(
            mean(item["timing"]["pool_construction_seconds"] for item in results), 6
        ),
        "average_reranking_seconds": round(
            mean(item["timing"]["reranking_seconds"] for item in results), 6
        ),
        "average_total_seconds": round(
            mean(item["timing"]["total_seconds"] for item in results), 6
        ),
        "candidate_pool_coverage": {},
        "reranked_metrics": {},
    }

    for level in ("article_level", "legal_unit_level"):
        summary["candidate_pool_coverage"][level] = {
            metric: _average(
                [item["candidate_pool_metrics"][level][metric] for item in results]
            )
            for metric in ("recall", "mrr", "hit_rate")
        }

        summary["reranked_metrics"][level] = {}
        for k in FINAL_K_VALUES:
            summary["reranked_metrics"][level][str(k)] = {
                metric: _average(
                    [
                        item["reranked_metrics"][level][str(k)][metric]
                        for item in results
                    ]
                )
                for metric in ("precision", "recall", "mrr", "hit_rate")
            }

    return summary


# ============================================================
# EXECUÇÃO DO EXPERIMENTO
# ============================================================

def compare_reranking_strategies() -> Path:
    dataset = _load_json(DATASET_PATH)
    questions = _validate_dataset(dataset)

    print("=" * 72)
    print("COMPARAÇÃO DE ESTRATÉGIAS + CROSS-ENCODER — POLITIZE-SE")
    print("=" * 72)
    print(f"Dataset: {dataset.get('dataset_id', DATASET_PATH.stem)}")
    print(f"Versão: {dataset.get('version', 'não informada')}")
    print(f"Perguntas: {len(questions)}")
    print(f"Candidatos iniciais por recuperador: {CANDIDATE_K}")
    print(f"Modelo Cross-Encoder: {RERANKER_MODEL_NAME}")
    print(f"Top-K final: {RERANKER_TOP_K}")

    # --------------------------------------------------------
    # 1. Inicializa os recuperadores
    # --------------------------------------------------------
    print("\nInicializando recuperador híbrido...")
    hybrid_retriever, hybrid_provider = create_retriever(
        provider=PROVIDER,
        k=CANDIDATE_K,
        candidate_k=CANDIDATE_K,
        collection_name=LEGAL_COLLECTION_NAME,
    )
    hybrid_collection = hybrid_retriever.vector_store._collection
    hybrid_collection_name = hybrid_collection.name
    hybrid_indexed_count = hybrid_collection.count()

    if hybrid_indexed_count <= 0:
        raise RuntimeError(f"A coleção jurídica '{hybrid_collection_name}' está vazia.")

    print("Inicializando recuperador semântico...")
    semantic_retriever, semantic_provider = create_semantic_retriever(
        provider=PROVIDER,
        candidate_k=CANDIDATE_K,
        section_k=SECTION_K,
        unit_k=CANDIDATE_K,
        units_per_section_k=UNITS_PER_SECTION_K,
    )
    semantic_collection = semantic_retriever.vector_store._collection
    semantic_collection_name = semantic_collection.name

    # --------------------------------------------------------
    # 2. Carrega um único modelo Cross-Encoder
    # --------------------------------------------------------
    selected_device = "cuda" if torch.cuda.is_available() else "cpu"
    print("\nCarregando Cross-Encoder...")
    print(f"Dispositivo selecionado: {selected_device}")

    cross_encoder_model = CrossEncoder(
        RERANKER_MODEL_NAME,
        device=selected_device,
        max_length=RERANKER_MAX_LENGTH,
    )

    reranker = PolitizeseCrossEncoderRetriever(
        base_retriever=hybrid_retriever,
        reranker=cross_encoder_model,
        top_k=RERANKER_TOP_K,
        batch_size=RERANKER_BATCH_SIZE,
        model_name=RERANKER_MODEL_NAME,
    )

    # Aquecimento fora das medições para reduzir o impacto da primeira inferência.
    print("Aquecendo o modelo (essa inferência não entra nas métricas)...")
    reranker.rerank_documents(
        query="A Constituição Federal estabelece direitos fundamentais.",
        candidates=[
            Document(
                page_content=(
                    "São direitos sociais a educação, a saúde, "
                    "a alimentação, o trabalho e a moradia."
                ),
                metadata={
                    "document_part": "CF",
                    "article_number": "6",
                    "legal_unit": "caput",
                },
            )
        ],
    )

    print("\nModelo carregado e aquecido.")
    print(f"Provedor híbrido: {hybrid_provider}")
    print(f"Provedor semântico: {semantic_provider}")
    print(f"Coleção híbrida: {hybrid_collection_name} ({hybrid_indexed_count} docs)")
    print(f"Coleção semântica: {semantic_collection_name}")
    print(f"Dispositivo efetivo: {cross_encoder_model.model.device}")

    # --------------------------------------------------------
    # 3. Estratégias
    # --------------------------------------------------------
    strategy_results: dict[str, list[dict[str, Any]]] = {
        "hybrid_48_reranked": [],
        "rrf_48_reranked": [],
        "hybrid_semantic_union_reranked": [],
    }

    for question_index, item in enumerate(questions, start=1):
        question_id = item["id"]
        query = item["question"]

        print("\n" + "-" * 72)
        print(f"[{question_index}/{len(questions)}] {question_id}: {query}")
        print("-" * 72)

        # Busca executada uma vez por pergunta e reutilizada pelas três estratégias.
        start = perf_counter()
        hybrid_documents = hybrid_retriever.invoke(query)
        hybrid_elapsed = perf_counter() - start

        start = perf_counter()
        semantic_documents = semantic_retriever.invoke(query)
        semantic_elapsed = perf_counter() - start

        # A: conjunto híbrido de 48 documentos.
        hybrid_candidates = hybrid_documents

        # B: fusão RRF limitada a 48 documentos.
        start = perf_counter()
        fused_candidates = _fuse_rankings(
            hybrid_documents,
            semantic_documents,
            top_k=CANDIDATE_K,
        )
        fusion_elapsed = perf_counter() - start

        # C: união sem truncamento, limitada apenas pela deduplicação (máx. 96).
        start = perf_counter()
        union_candidates = _union_rankings(
            hybrid_documents,
            semantic_documents,
        )
        union_elapsed = perf_counter() - start

        scenarios = (
            (
                "hybrid_48_reranked",
                hybrid_candidates,
                hybrid_elapsed,
                0.0,
            ),
            (
                "rrf_48_reranked",
                fused_candidates,
                hybrid_elapsed + semantic_elapsed,
                fusion_elapsed,
            ),
            (
                "hybrid_semantic_union_reranked",
                union_candidates,
                hybrid_elapsed + semantic_elapsed,
                union_elapsed,
            ),
        )

        for strategy_name, candidates, retrieval_seconds, pool_seconds in scenarios:
            start = perf_counter()
            reranked_documents = reranker.rerank_documents(
                query=query,
                candidates=candidates,
            )
            reranking_elapsed = perf_counter() - start

            timing = {
                "retrieval_seconds": retrieval_seconds,
                "pool_construction_seconds": pool_seconds,
                "reranking_seconds": reranking_elapsed,
            }

            result = _evaluate_candidate_set(
                item=item,
                strategy_name=strategy_name,
                candidates=candidates,
                reranked_documents=reranked_documents,
                timing=timing,
            )
            strategy_results[strategy_name].append(result)

            article_recall = result["reranked_metrics"]["article_level"]["4"]["recall"]
            unit_recall = result["reranked_metrics"]["legal_unit_level"]["4"]["recall"]

            print(
                f"{strategy_name}: candidatos={len(candidates)} | "
                f"top4={len(reranked_documents)} | "
                f"Recall artigos@4={article_recall} | "
                f"Recall unidades@4={unit_recall} | "
                f"tempo total={result['timing']['total_seconds']:.4f}s"
            )

    # --------------------------------------------------------
    # 4. Sumários e metadados
    # --------------------------------------------------------
    summaries = {
        strategy_name: _build_strategy_summary(results)
        for strategy_name, results in strategy_results.items()
    }

    results_payload = {
        "evaluation": {
            "name": "Comparação de conjuntos de candidatos com Cross-Encoder",
            "dataset_id": dataset.get("dataset_id"),
            "dataset_name": dataset.get("name"),
            "dataset_version": dataset.get("version"),
            "dataset_source": dataset.get("source"),
            "dataset_path": str(DATASET_PATH.relative_to(PROJECT_ROOT)),
            "executed_at": datetime.now(timezone.utc).isoformat(),
            "methodology": {
                "retrieval_uses_ground_truth": False,
                "same_question_and_dataset": True,
                "hybrid_candidates": CANDIDATE_K,
                "rrf_candidates": CANDIDATE_K,
                "union_max_candidates": CANDIDATE_K * 2,
                "reranker_scores_all_candidates": True,
                "reranker_final_documents": RERANKER_TOP_K,
                "candidate_pool_coverage": (
                    "Recall, MRR e Hit Rate medidos sobre todo o conjunto "
                    "de candidatos únicos de cada estratégia."
                ),
                "reranked_metrics": (
                    "Precision, Recall, MRR e Hit Rate calculados em @1, @2 e @4."
                ),
                "union_order_before_reranking": (
                    "Ordem híbrida seguida dos documentos semânticos ainda não vistos; "
                    "essa ordem não determina o ranking final, pois todos os candidatos "
                    "são pontuados individualmente pelo Cross-Encoder."
                ),
                "timing": (
                    "Tempo total inclui recuperação necessária para formar o conjunto, "
                    "construção/fusão e inferência do Cross-Encoder. Inicialização e "
                    "aquecimento do modelo ficam fora das medições."
                ),
            },
        },
        "configuration": {
            "provider": PROVIDER,
            "hybrid_provider": hybrid_provider,
            "semantic_provider": semantic_provider,
            "hybrid_collection": hybrid_collection_name,
            "hybrid_indexed_documents": hybrid_indexed_count,
            "semantic_collection": semantic_collection_name,
            "semantic_sections": semantic_retriever.section_count,
            "semantic_units": semantic_retriever.unit_count,
            "candidate_k_per_retriever": CANDIDATE_K,
            "section_k": SECTION_K,
            "units_per_section_k": UNITS_PER_SECTION_K,
            "rrf_constant": RRF_CONSTANT,
            "reranker_model": RERANKER_MODEL_NAME,
            "reranker_device": str(cross_encoder_model.model.device),
            "reranker_batch_size": RERANKER_BATCH_SIZE,
            "reranker_max_length": RERANKER_MAX_LENGTH,
            "reranker_top_k": RERANKER_TOP_K,
        },
        "results": {
            strategy_name: {
                "summary": summaries[strategy_name],
                "questions": results,
            }
            for strategy_name, results in strategy_results.items()
        },
    }

    OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIRECTORY / OUTPUT_FILENAME

    with output_path.open("w", encoding="utf-8") as file:
        json.dump(results_payload, file, ensure_ascii=False, indent=4)

    # --------------------------------------------------------
    # 5. Resumo final
    # --------------------------------------------------------
    print("\n" + "=" * 72)
    print("EXPERIMENTO CONCLUÍDO")
    print("=" * 72)

    for strategy_name, summary in summaries.items():
        print(f"\n{strategy_name.upper()}")
        print(f"Candidatos médios: {summary['average_candidate_count']}")
        print(f"Tempo médio total: {summary['average_total_seconds']:.4f}s")

        for level, label in (
            ("article_level", "ARTIGOS"),
            ("legal_unit_level", "UNIDADES JURÍDICAS"),
        ):
            pool_recall = summary["candidate_pool_coverage"][level]["recall"]
            final_4 = summary["reranked_metrics"][level]["4"]
            print(
                f"  {label}: Recall pool={pool_recall} | "
                f"Recall@4={final_4['recall']} | "
                f"MRR@4={final_4['mrr']} | "
                f"HitRate@4={final_4['hit_rate']}"
            )

    print(f"\nResultado salvo em: {output_path}")
    return output_path


if __name__ == "__main__":
    compare_reranking_strategies()
