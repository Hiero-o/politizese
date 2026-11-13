
import json

from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from time import perf_counter
from typing import Any

from src.core.config import PROJECT_ROOT
from src.rag.reranker import create_reranked_retriever


DEFAULT_RERANKER_MODEL = "BAAI/bge-reranker-v2-m3"

SUPPORTED_RETRIEVERS = {"legal_hybrid"}

ARTICLE_ID_PATTERN = (
    r"^(?P<article>.+-ART-\d{4}(?:-[A-Z])?)(?:-|$)"
)

FRAGMENT_SUFFIX = "-PART-"


# ============================================================
# CAMINHOS E ARQUIVOS
# ============================================================

def _resolve_path(path: str | Path) -> Path:
    """Resolve caminhos relativos a partir da raiz do projeto."""

    resolved = Path(path).expanduser()

    if not resolved.is_absolute():
        resolved = PROJECT_ROOT / resolved

    return resolved.resolve()


def _load_json(path: Path) -> dict[str, Any]:
    """Carrega e valida a estrutura básica de um JSON."""

    if not path.is_file():
        raise FileNotFoundError(
            f"Arquivo JSON não encontrado: {path}"
        )

    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)

    except json.JSONDecodeError as error:
        raise ValueError(
            f"JSON inválido em {path}, "
            f"linha {error.lineno}, coluna {error.colno}: "
            f"{error.msg}"
        ) from error

    if not isinstance(data, dict):
        raise ValueError(
            f"O arquivo {path} deve conter um objeto JSON."
        )

    return data


def _to_json_safe(value: Any) -> Any:
    """Converte valores para tipos compatíveis com JSON."""

    if value is None or isinstance(
        value,
        (str, int, float, bool),
    ):
        return value

    if isinstance(value, dict):
        return {
            str(key): _to_json_safe(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple)):
        return [
            _to_json_safe(item)
            for item in value
        ]

    return str(value)


# ============================================================
# VALIDAÇÃO
# ============================================================

def _validate_identifier_list(
    values: Any,
    field_name: str,
    question_id: str,
) -> list[str]:
    """Valida uma lista de identificadores."""

    if values is None:
        return []

    if not isinstance(values, list):
        raise ValueError(
            f"'{field_name}' da pergunta {question_id} "
            "deve ser uma lista."
        )

    identifiers = []

    for identifier in values:

        if (
            not isinstance(identifier, str)
            or not identifier.strip()
        ):
            raise ValueError(
                f"Identificador inválido em '{field_name}' "
                f"da pergunta {question_id}."
            )

        if identifier in identifiers:
            raise ValueError(
                f"Identificador duplicado em '{field_name}' "
                f"da pergunta {question_id}: {identifier}"
            )

        identifiers.append(identifier)

    return identifiers


def _validate_dataset(dataset: dict[str, Any]) -> None:
    """Valida as perguntas e suas referências."""

    questions = dataset.get("questions")

    if not isinstance(questions, list) or not questions:
        raise ValueError(
            "O dataset precisa possuir uma lista "
            "'questions' não vazia."
        )

    question_ids = set()

    for index, item in enumerate(questions):

        if not isinstance(item, dict):
            raise ValueError(
                f"A pergunta na posição {index} "
                "deve ser um objeto."
            )

        question_id = item.get("id")
        question = item.get("question")

        if (
            not isinstance(question_id, str)
            or not question_id.strip()
        ):
            raise ValueError(
                f"Pergunta na posição {index} "
                "sem identificador válido."
            )

        if question_id in question_ids:
            raise ValueError(
                f"Identificador de pergunta duplicado: "
                f"{question_id}"
            )

        question_ids.add(question_id)

        if (
            not isinstance(question, str)
            or not question.strip()
        ):
            raise ValueError(
                f"A pergunta {question_id} "
                "não possui texto válido."
            )

        reference_articles = _validate_identifier_list(
            item.get("reference_articles", []),
            "reference_articles",
            question_id,
        )

        reference_nodes = _validate_identifier_list(
            item.get("reference_nodes", []),
            "reference_nodes",
            question_id,
        )

        if not reference_articles and not reference_nodes:
            raise ValueError(
                f"A pergunta {question_id} não possui "
                "referências para avaliação."
            )

        ground_truth = item.get("ground_truth")

        if ground_truth is not None and not isinstance(
            ground_truth,
            str,
        ):
            raise ValueError(
                f"'ground_truth' da pergunta {question_id} "
                "deve ser um texto ou null."
            )


def _validate_config(config: dict[str, Any]) -> None:
    """Valida a configuração da avaliação."""

    retriever_config = config.get("retriever")

    if not isinstance(retriever_config, dict):
        raise ValueError(
            "A configuração precisa possuir um objeto 'retriever'."
        )

    retriever_type = retriever_config.get("type")

    if retriever_type not in SUPPORTED_RETRIEVERS:
        raise ValueError(
            f"Tipo de retriever não suportado: {retriever_type}. "
            f"Tipos disponíveis: {sorted(SUPPORTED_RETRIEVERS)}"
        )

    top_k = retriever_config.get("top_k", 4)
    rerank_k = retriever_config.get("rerank_k", 24)
    candidate_k = retriever_config.get("candidate_k", 48)
    lexical_candidate_k = retriever_config.get("lexical_candidate_k", 120)
    rrf_constant = retriever_config.get("rrf_constant", 60)

    for name, value in (
        ("top_k", top_k),
        ("rerank_k", rerank_k),
        ("candidate_k", candidate_k),
        ("lexical_candidate_k", lexical_candidate_k),
        ("rrf_constant", rrf_constant),
    ):
        if (
            not isinstance(value, int)
            or isinstance(value, bool)
            or value <= 0
        ):
            raise ValueError(
                f"'{name}' precisa ser um inteiro positivo."
            )

    if rerank_k < top_k:
        raise ValueError(
            "'rerank_k' não pode ser menor que 'top_k'."
        )

    if candidate_k < rerank_k:
        raise ValueError(
            "'candidate_k' não pode ser menor que 'rerank_k'."
        )

    provider = retriever_config.get("provider", "local")

    if not isinstance(provider, str) or not provider.strip():
        raise ValueError(
            "'provider' precisa ser um texto válido."
        )

    collection_name = retriever_config.get(
        "collection_name",
        "constituicao_legal_clean_v2",
    )

    if (
        not isinstance(collection_name, str)
        or not collection_name.strip()
    ):
        raise ValueError(
            "'collection_name' precisa ser um texto válido."
        )

    reranker_config = config.get("reranker", {})

    if not isinstance(reranker_config, dict):
        raise ValueError(
            "'reranker' precisa ser um objeto JSON."
        )

    model_name = reranker_config.get(
        "model_name",
        DEFAULT_RERANKER_MODEL,
    )

    if not isinstance(model_name, str) or not model_name.strip():
        raise ValueError(
            "'model_name' precisa ser um texto válido."
        )

    device = reranker_config.get("device")

    if device is not None and (
        not isinstance(device, str)
        or not device.strip()
    ):
        raise ValueError(
            "'device' precisa ser um texto válido ou null."
        )

    batch_size = reranker_config.get("batch_size", 8)
    max_length = reranker_config.get("max_length", 512)

    for name, value in (
        ("batch_size", batch_size),
        ("max_length", max_length),
    ):
        if (
            not isinstance(value, int)
            or isinstance(value, bool)
            or value <= 0
        ):
            raise ValueError(
                f"'{name}' precisa ser um inteiro positivo."
            )

    evaluation_config = config.get("evaluation", {})

    if not isinstance(evaluation_config, dict):
        raise ValueError(
            "'evaluation' deve ser um objeto JSON."
        )

    k_values = evaluation_config.get(
        "k_values",
        [1, 2, 4],
    )

    if not isinstance(k_values, list) or not k_values:
        raise ValueError(
            "'k_values' precisa ser uma lista não vazia."
        )

    if len(k_values) != len(set(k_values)):
        raise ValueError(
            "'k_values' não pode possuir valores duplicados."
        )

    for value in k_values:
        if (
            not isinstance(value, int)
            or isinstance(value, bool)
            or value <= 0
        ):
            raise ValueError(
                "Todos os valores de 'k_values' "
                "precisam ser inteiros positivos."
            )

    if max(k_values) > top_k:
        raise ValueError(
            "O maior valor de 'k_values' não pode "
            "ser maior que 'top_k'."
        )

    output_config = config.get("output", {})

    if not isinstance(output_config, dict):
        raise ValueError(
            "'output' deve ser um objeto JSON."
        )


# ============================================================
# IDENTIFICADORES DOS DOCUMENTOS
# ============================================================

def _get_node_id(metadata: dict[str, Any]) -> str | None:
    """
    Recupera a unidade jurídica original.

    Quando existem fragmentos, utiliza source_node_id
    para evitar que cada fragmento seja contado como
    um nó diferente.
    """

    node_id = metadata.get("source_node_id")

    if not node_id:
        node_id = metadata.get("chunk_id")

    if not isinstance(node_id, str) or not node_id:
        return None

    if FRAGMENT_SUFFIX in node_id:
        node_id = node_id.rsplit(FRAGMENT_SUFFIX, 1)[0]

    return node_id


def _get_article_id(
    metadata: dict[str, Any],
    node_id: str | None,
) -> str | None:
    """Recupera o identificador do artigo de origem."""

    article_id = metadata.get("article_id")

    if isinstance(article_id, str) and article_id:
        return article_id

    if not node_id:
        return None

    import re

    match = re.match(
        ARTICLE_ID_PATTERN,
        node_id,
    )

    if match:
        return match.group("article")

    return None


def _unique_preserving_order(
    identifiers: list[str],
) -> list[str]:
    """Remove duplicados sem alterar a ordem de recuperação."""

    return list(dict.fromkeys(identifiers))


def _extract_identifiers(
    documents: list[Any],
) -> tuple[list[str], list[str]]:
    """
    Extrai artigos e unidades jurídicas dos documentos,
    preservando a ordem do ranking.
    """

    article_ids = []
    node_ids = []

    for document in documents:

        metadata = _to_json_safe(
            dict(document.metadata or {})
        )

        node_id = _get_node_id(metadata)

        article_id = _get_article_id(
            metadata,
            node_id,
        )

        if node_id:
            node_ids.append(node_id)

        if article_id:
            article_ids.append(article_id)

    return (
        _unique_preserving_order(article_ids),
        _unique_preserving_order(node_ids),
    )


# ============================================================
# MÉTRICAS
# ============================================================

def _calculate_metrics_at_k(
    retrieved_ids: list[str],
    reference_ids: list[str],
    k: int,
) -> dict[str, float | None]:
    """
    Calcula Precision@K, Recall@K, MRR@K e Hit Rate@K.

    A precisão utiliza K como denominador, mesmo quando
    são recuperados menos de K resultados.
    """

    if not reference_ids:
        return {
            "precision": None,
            "recall": None,
            "mrr": None,
            "hit_rate": None,
        }

    relevant_ids = set(reference_ids)
    ranked_ids = retrieved_ids[:k]

    hits = [
        identifier
        for identifier in ranked_ids
        if identifier in relevant_ids
    ]

    first_relevant_rank = next(
        (
            rank
            for rank, identifier in enumerate(
                ranked_ids,
                start=1,
            )
            if identifier in relevant_ids
        ),
        None,
    )

    precision = len(hits) / k
    recall = len(hits) / len(relevant_ids)

    mrr = (
        1 / first_relevant_rank
        if first_relevant_rank is not None
        else 0.0
    )

    hit_rate = 1.0 if hits else 0.0

    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "mrr": round(mrr, 4),
        "hit_rate": round(hit_rate, 4),
    }


def _calculate_question_metrics(
    retrieved_articles: list[str],
    retrieved_nodes: list[str],
    reference_articles: list[str],
    reference_nodes: list[str],
    k_values: list[int],
) -> dict[str, Any]:
    """Calcula métricas nos níveis documental e jurídico."""

    metrics = {
        "article_level": {},
        "legal_unit_level": {},
    }

    for k in k_values:

        metrics["article_level"][str(k)] = (
            _calculate_metrics_at_k(
                retrieved_ids=retrieved_articles,
                reference_ids=reference_articles,
                k=k,
            )
        )

        metrics["legal_unit_level"][str(k)] = (
            _calculate_metrics_at_k(
                retrieved_ids=retrieved_nodes,
                reference_ids=reference_nodes,
                k=k,
            )
        )

    return metrics


def _aggregate_level_metrics(
    question_results: list[dict[str, Any]],
    result_key: str,
    level: str,
    k_values: list[int],
) -> dict[str, Any]:
    """Calcula a média das métricas de um nível de avaliação."""

    evaluated_questions = [
        item
        for item in question_results
        if (
            item[result_key]["metrics"][level][str(k_values[0])]
            ["precision"]
            is not None
        )
    ]

    summary = {
        "questions_with_references": len(evaluated_questions),
        "metrics": {},
    }

    metric_names = (
        "precision",
        "recall",
        "mrr",
        "hit_rate",
    )

    for k in k_values:

        metric_summary = {}

        for metric_name in metric_names:

            values = [
                item[result_key]["metrics"][level][str(k)][metric_name]
                for item in evaluated_questions
                if (
                    item[result_key]["metrics"][level][str(k)]
                    [metric_name]
                    is not None
                )
            ]

            metric_summary[f"{metric_name}@{k}"] = (
                round(mean(values), 4)
                if values
                else None
            )

        summary["metrics"][str(k)] = metric_summary

    return summary


# ============================================================
# SERIALIZAÇÃO DOS RESULTADOS
# ============================================================

def _build_run_result(
    documents: list[Any],
    reference_articles: list[str],
    reference_nodes: list[str],
    k_values: list[int],
    elapsed_seconds: float,
) -> dict[str, Any]:
    """Monta o resultado e as métricas de um ranking."""

    retrieved_articles, retrieved_nodes = (
        _extract_identifiers(documents)
    )

    retrieved_documents = []

    for rank, document in enumerate(documents, start=1):

        metadata = _to_json_safe(
            dict(document.metadata or {})
        )

        node_id = _get_node_id(metadata)

        article_id = _get_article_id(
            metadata,
            node_id,
        )

        retrieved_documents.append({
            "rank": rank,
            "node_id": node_id,
            "article_id": article_id,
            "metadata": metadata,
            "page_content": document.page_content,
            "characters": len(document.page_content),
        })

    metrics = _calculate_question_metrics(
        retrieved_articles=retrieved_articles,
        retrieved_nodes=retrieved_nodes,
        reference_articles=reference_articles,
        reference_nodes=reference_nodes,
        k_values=k_values,
    )

    return {
        "retrieved_count": len(documents),
        "retrieved_article_ids": retrieved_articles,
        "retrieved_node_ids": retrieved_nodes,
        "elapsed_seconds": round(elapsed_seconds, 6),
        "metrics": metrics,
        "retrieved_documents": retrieved_documents,
    }


# ============================================================
# AVALIAÇÃO COMPARATIVA
# ============================================================

def _run_comparative_evaluation(
    retriever_config: dict[str, Any],
    reranker_config: dict[str, Any],
    questions: list[dict[str, Any]],
    k_values: list[int],
) -> dict[str, Any]:
    """
    Compara o retriever híbrido com o híbrido + CrossEncoder.

    Os dois rankings utilizam exatamente o mesmo conjunto
    de candidatos recuperados pelo retriever híbrido.
    """

    top_k = retriever_config.get("top_k", 4)
    rerank_k = retriever_config.get("rerank_k", 24)
    candidate_k = retriever_config.get("candidate_k", 48)
    lexical_candidate_k = retriever_config.get("lexical_candidate_k", 120)
    rrf_constant = retriever_config.get("rrf_constant", 60)

    model_name = reranker_config.get(
        "model_name",
        DEFAULT_RERANKER_MODEL,
    )

    print("\n" + "=" * 65)
    print("INICIALIZANDO PIPELINE COM CROSS-ENCODER")
    print("=" * 65)

    reranked_retriever, provider = create_reranked_retriever(
        provider=retriever_config.get("provider", "local"),
        top_k=top_k,
        rerank_k=rerank_k,
        candidate_k=candidate_k,
        lexical_candidate_k=lexical_candidate_k,
        rrf_constant=rrf_constant,
        collection_name=retriever_config.get(
            "collection_name",
            "constituicao_legal_clean_v2",
        ),
        model_name=model_name,
        device=reranker_config.get("device"),
        batch_size=reranker_config.get("batch_size", 8),
        max_length=reranker_config.get("max_length", 512),
    )

    # O baseline utilizará o mesmo retriever híbrido
    # que fornece os candidatos ao CrossEncoder.
    base_retriever = reranked_retriever.base_retriever

    vector_store = base_retriever.vector_store
    collection = vector_store._collection

    collection_name = collection.name
    indexed_count = collection.count()

    if indexed_count <= 0:
        raise RuntimeError(
            f"A coleção '{collection_name}' está vazia."
        )

    selected_device = str(
        reranked_retriever.reranker.device
    )

    print(f"Provedor de embeddings: {provider}")
    print(f"Coleção: {collection_name}")
    print(f"Documentos indexados: {indexed_count}")
    print(f"Dispositivo do CrossEncoder: {selected_device}")
    print(f"Modelo: {reranked_retriever.model_name}")
    print(f"Candidatos semânticos: {candidate_k}")
    print(f"Candidatos híbridos: {rerank_k}")
    print(f"Documentos finais: {top_k}")

    question_results = []

    for item in questions:

        question_id = item["id"]
        question_text = item["question"]

        print("\n" + "-" * 65)
        print(f"[{question_id}] {question_text}")
        print("-" * 65)

        # ----------------------------------------------------
        # 1. RECUPERAÇÃO COMPARTILHADA
        # ----------------------------------------------------
        # A busca recebe somente a pergunta.
        # As referências não participam da recuperação.

        retrieval_start = perf_counter()

        candidates = base_retriever.invoke(question_text)

        retrieval_seconds = (
            perf_counter() - retrieval_start
        )

        if not candidates:
            print("  Nenhum candidato recuperado.")

        # ----------------------------------------------------
        # 2. BASELINE: HÍBRIDO SEM CROSS-ENCODER
        # ----------------------------------------------------
        # Como os candidatos já estão na ordem híbrida,
        # o baseline utiliza os primeiros top_k.

        baseline_documents = candidates[:top_k]

        # ----------------------------------------------------
        # 3. RERANKING: CROSS-ENCODER
        # ----------------------------------------------------

        rerank_start = perf_counter()

        reranked_documents = (
            reranked_retriever.rerank_documents(
                query=question_text,
                candidates=candidates,
            )
        )

        rerank_seconds = perf_counter() - rerank_start

        # ----------------------------------------------------
        # 4. REFERÊNCIAS DO DATASET
        # ----------------------------------------------------
        # O gabarito só é consultado depois das recuperações.

        reference_articles = item.get(
            "reference_articles",
            [],
        )

        reference_nodes = item.get(
            "reference_nodes",
            [],
        )

        # ----------------------------------------------------
        # 5. MÉTRICAS DO CONJUNTO DE CANDIDATOS
        # ----------------------------------------------------
        # Mede se o retriever híbrido encontrou as referências
        # antes do reranking.

        candidate_articles, candidate_nodes = (
            _extract_identifiers(candidates)
        )

        candidate_metrics = _calculate_question_metrics(
            retrieved_articles=candidate_articles,
            retrieved_nodes=candidate_nodes,
            reference_articles=reference_articles,
            reference_nodes=reference_nodes,
            k_values=[rerank_k],
        )

        # ----------------------------------------------------
        # 6. MÉTRICAS DOS DOIS RANKINGS FINAIS
        # ----------------------------------------------------

        baseline_result = _build_run_result(
            documents=baseline_documents,
            reference_articles=reference_articles,
            reference_nodes=reference_nodes,
            k_values=k_values,
            elapsed_seconds=retrieval_seconds,
        )

        reranked_result = _build_run_result(
            documents=reranked_documents,
            reference_articles=reference_articles,
            reference_nodes=reference_nodes,
            k_values=k_values,
            elapsed_seconds=retrieval_seconds + rerank_seconds,
        )

        candidate_generation_result = {
            "retrieved_count": len(candidates),
            "retrieved_article_ids": candidate_articles,
            "retrieved_node_ids": candidate_nodes,
            "metrics": candidate_metrics,
        }

        # ----------------------------------------------------
        # 7. RESULTADO DA PERGUNTA
        # ----------------------------------------------------

        question_result = {
            "id": question_id,
            "category": item.get("category"),
            "question": question_text,
            "ground_truth": item.get("ground_truth"),
            "reference_articles": reference_articles,
            "reference_nodes": reference_nodes,

            "candidate_generation": candidate_generation_result,

            "baseline": baseline_result,

            "reranked": reranked_result,

            "timing": {
                "candidate_retrieval_seconds": round(
                    retrieval_seconds,
                    6,
                ),
                "reranking_seconds": round(
                    rerank_seconds,
                    6,
                ),
                "baseline_total_seconds": round(
                    retrieval_seconds,
                    6,
                ),
                "reranked_total_seconds": round(
                    retrieval_seconds + rerank_seconds,
                    6,
                ),
            },
        }

        question_results.append(question_result)

        print(
            f"  Candidatos híbridos: {len(candidates)}"
        )

        print(
            f"  Baseline: {len(baseline_documents)} documentos"
        )

        print(
            f"  Reranked: {len(reranked_documents)} documentos"
        )

        print(
            f"  Recuperação: {retrieval_seconds:.4f}s"
        )

        print(
            f"  CrossEncoder: {rerank_seconds:.4f}s"
        )

        print(
            f"  Total reranked: "
            f"{retrieval_seconds + rerank_seconds:.4f}s"
        )

        for k in k_values:

            baseline_node_metric = (
                baseline_result["metrics"]
                ["legal_unit_level"][str(k)]
            )

            reranked_node_metric = (
                reranked_result["metrics"]
                ["legal_unit_level"][str(k)]
            )

            print(
                f"  Unidades @ {k} — "
                f"Baseline Recall: "
                f"{baseline_node_metric['recall']} | "
                f"Reranked Recall: "
                f"{reranked_node_metric['recall']}"
            )

    # ========================================================
    # RESUMO AGREGADO
    # ========================================================

    average_retrieval_seconds = mean(
        item["timing"]["candidate_retrieval_seconds"]
        for item in question_results
    )

    average_reranking_seconds = mean(
        item["timing"]["reranking_seconds"]
        for item in question_results
    )

    average_baseline_seconds = mean(
        item["timing"]["baseline_total_seconds"]
        for item in question_results
    )

    average_reranked_seconds = mean(
        item["timing"]["reranked_total_seconds"]
        for item in question_results
    )

    candidate_k_metrics = {
        "article_level": _aggregate_level_metrics(
            question_results,
            "candidate_generation",
            "article_level",
            [rerank_k],
        ),
        "legal_unit_level": _aggregate_level_metrics(
            question_results,
            "candidate_generation",
            "legal_unit_level",
            [rerank_k],
        ),
    }

    baseline_metrics = {
        "article_level": _aggregate_level_metrics(
            question_results,
            "baseline",
            "article_level",
            k_values,
        ),
        "legal_unit_level": _aggregate_level_metrics(
            question_results,
            "baseline",
            "legal_unit_level",
            k_values,
        ),
    }

    reranked_metrics = {
        "article_level": _aggregate_level_metrics(
            question_results,
            "reranked",
            "article_level",
            k_values,
        ),
        "legal_unit_level": _aggregate_level_metrics(
            question_results,
            "reranked",
            "legal_unit_level",
            k_values,
        ),
    }

    summary = {
        "questions_evaluated": len(question_results),

        "average_candidate_retrieval_seconds": round(
            average_retrieval_seconds,
            6,
        ),

        "average_reranking_seconds": round(
            average_reranking_seconds,
            6,
        ),

        "average_baseline_seconds": round(
            average_baseline_seconds,
            6,
        ),

        "average_reranked_seconds": round(
            average_reranked_seconds,
            6,
        ),

        "candidate_generation": candidate_k_metrics,

        "baseline": baseline_metrics,

        "reranked": reranked_metrics,
    }

    return {
        "configuration": {
            "retriever_type": "legal_hybrid",
            "provider": provider,
            "collection_name": collection_name,
            "indexed_documents": indexed_count,
            "lexical_candidate_k": lexical_candidate_k,
            "rrf_constant": rrf_constant,
            "top_k": top_k,
            "rerank_k": rerank_k,
            "candidate_k": candidate_k,
            "k_values": k_values,
            "reranker_model": reranked_retriever.model_name,
            "reranker_device": selected_device,
            "reranker_batch_size": reranked_retriever.batch_size,
        },

        "questions": question_results,

        "summary": summary,
    }


# ============================================================
# EXECUÇÃO PRINCIPAL
# ============================================================

def evaluate_retrievers(
    config_path: str | Path,
) -> Path:
    """
    Executa a comparação entre o retriever híbrido
    e o retriever híbrido com CrossEncoder.

    Os parâmetros são carregados do JSON de configuração.
    """

    resolved_config_path = _resolve_path(config_path)

    config = _load_json(resolved_config_path)

    _validate_config(config)

    dataset_path_value = config.get("dataset")

    if (
        not isinstance(dataset_path_value, str)
        or not dataset_path_value.strip()
    ):
        raise ValueError(
            "O campo 'dataset' precisa indicar "
            "um caminho válido."
        )

    dataset_path = _resolve_path(dataset_path_value)

    dataset = _load_json(dataset_path)

    _validate_dataset(dataset)

    retriever_config = config["retriever"]

    reranker_config = config.get("reranker", {})

    evaluation_config = config.get("evaluation", {})

    k_values = sorted(
        evaluation_config.get("k_values", [1, 2, 4])
    )

    questions = dataset["questions"]

    print("=" * 65)
    print("AVALIAÇÃO COMPARATIVA RAG — POLITIZE-SE")
    print("=" * 65)

    print(
        f"Dataset: "
        f"{dataset.get('dataset_id', dataset_path.stem)}"
    )

    print(
        f"Versão: {dataset.get('version', 'não informada')}"
    )

    print(f"Perguntas: {len(questions)}")
    print(f"Top K: {retriever_config.get('top_k', 4)}")
    print(f"K avaliados: {k_values}")

    result = _run_comparative_evaluation(
        retriever_config=retriever_config,
        reranker_config=reranker_config,
        questions=questions,
        k_values=k_values,
    )

    # --------------------------------------------------------
    # CAMINHO DE SAÍDA
    # --------------------------------------------------------

    output_config = config.get("output", {})

    output_directory = _resolve_path(
        output_config.get(
            "directory",
            "data/avaliacoes/resultados",
        )
    )

    output_filename = output_config.get(
        "filename",
        "resultado_comparacao_retrievers.json",
    )

    if (
        not isinstance(output_filename, str)
        or not output_filename.strip()
    ):
        raise ValueError(
            "O nome do arquivo de resultados é inválido."
        )

    output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path = (
        output_directory / Path(output_filename).name
    )

    try:
        dataset_relative_path = str(
            dataset_path.relative_to(PROJECT_ROOT)
        )

    except ValueError:
        dataset_relative_path = str(dataset_path)

    # --------------------------------------------------------
    # METODOLOGIA REGISTRADA
    # --------------------------------------------------------

    results_payload = {
        "evaluation": {
            "name": config.get(
                "name",
                "Comparação entre retriever híbrido e reranked",
            ),

            "dataset_id": dataset.get("dataset_id"),
            "dataset_name": dataset.get("name"),
            "dataset_version": dataset.get("version"),
            "dataset_source": dataset.get("source"),
            "dataset_path": dataset_relative_path,

            "executed_at": datetime.now(
                timezone.utc
            ).isoformat(),

            "methodology": {
                "retrieval_uses_ground_truth": False,

                "comparison": (
                    "Os dois experimentos utilizam o mesmo "
                    "conjunto de candidatos produzido pelo "
                    "retriever híbrido."
                ),

                "baseline": (
                    "Seleciona os primeiros top_k documentos "
                    "na ordem do retriever híbrido."
                ),

                "reranked": (
                    "Aplica o CrossEncoder sobre os mesmos "
                    "candidatos e seleciona os primeiros top_k."
                ),

                "candidate_generation": (
                    "Mede a cobertura das referências no "
                    "conjunto de rerank_k candidatos, antes "
                    "da aplicação do CrossEncoder."
                ),

                "article_level": (
                    "Identificadores distintos de artigos "
                    "na ordem de recuperação."
                ),

                "legal_unit_level": (
                    "Identificadores source_node_id distintos "
                    "na ordem de recuperação."
                ),

                "precision_denominator": (
                    "Valor de K, mesmo quando menos de K "
                    "resultados são recuperados."
                ),

                "latency": (
                    "O tempo de recuperação é medido uma vez "
                    "e compartilhado pelos dois experimentos. "
                    "O tempo do reranking é medido separadamente."
                ),
            },
        },

        "results": result,
    }

    with output_path.open(
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            results_payload,
            file,
            ensure_ascii=False,
            indent=4,
        )

    # --------------------------------------------------------
    # RESUMO NO TERMINAL
    # --------------------------------------------------------

    summary = result["summary"]

    print("\n" + "=" * 65)
    print("AVALIAÇÃO CONCLUÍDA")
    print("=" * 65)

    print(
        "\nTempo médio de recuperação: "
        f"{summary['average_candidate_retrieval_seconds']}s"
    )

    print(
        "Tempo médio de reranking: "
        f"{summary['average_reranking_seconds']}s"
    )

    print(
        "Tempo médio total — Baseline: "
        f"{summary['average_baseline_seconds']}s"
    )

    print(
        "Tempo médio total — Reranked: "
        f"{summary['average_reranked_seconds']}s"
    )

    print("\nRECALL DOS CANDIDATOS")

    candidate_node_metrics = (
        summary["candidate_generation"]
        ["legal_unit_level"]["metrics"]
    )

    for k, metrics in candidate_node_metrics.items():

        print(f"\nK = {k}")

        for metric, value in metrics.items():
            print(f"  {metric}: {value}")

    for result_name, title in (
        ("baseline", "BASELINE — UNIDADES JURÍDICAS"),
        ("reranked", "RERANKED — UNIDADES JURÍDICAS"),
    ):

        print(f"\n{title}")

        node_metrics = (
            summary[result_name]
            ["legal_unit_level"]["metrics"]
        )

        for k, metrics in node_metrics.items():

            print(f"\nK = {k}")

            for metric, value in metrics.items():
                print(f"  {metric}: {value}")

    print(f"\nResultado salvo em: {output_path}")

    return output_path
