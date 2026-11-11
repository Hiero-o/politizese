
import json
import re

from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from time import perf_counter
from typing import Any

from src.core.config import PROJECT_ROOT
from src.rag.retriever import create_retriever


SUPPORTED_RETRIEVERS = {"legal_hybrid"}

ARTICLE_ID_PATTERN = re.compile(
    r"^(?P<article>.+-ART-\d{4}(?:-[A-Z])?)(?:-|$)"
)

FRAGMENT_SUFFIX_PATTERN = re.compile(
    r"-PART-\d+$"
)


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
    candidate_k = retriever_config.get("candidate_k", 24)

    if (
        not isinstance(top_k, int)
        or isinstance(top_k, bool)
        or top_k <= 0
    ):
        raise ValueError("'top_k' precisa ser um inteiro positivo.")

    if (
        not isinstance(candidate_k, int)
        or isinstance(candidate_k, bool)
        or candidate_k < top_k
    ):
        raise ValueError(
            "'candidate_k' precisa ser um inteiro "
            "maior ou igual a 'top_k'."
        )

    provider = retriever_config.get("provider", "local")

    if not isinstance(provider, str) or not provider.strip():
        raise ValueError("'provider' precisa ser um texto válido.")

    collection_name = retriever_config.get(
        "collection_name",
        "constituicao_legal",
    )

    if (
        not isinstance(collection_name, str)
        or not collection_name.strip()
    ):
        raise ValueError(
            "'collection_name' precisa ser um texto válido."
        )

    evaluation_config = config.get("evaluation", {})

    if not isinstance(evaluation_config, dict):
        raise ValueError("'evaluation' deve ser um objeto JSON.")

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
        raise ValueError("'output' deve ser um objeto JSON.")


# ============================================================
# IDENTIFICADORES DOS DOCUMENTOS RECUPERADOS
# ============================================================

def _get_node_id(metadata: dict[str, Any]) -> str | None:
    """
    Recupera o identificador da unidade jurídica original.

    Quando existem fragmentos, utiliza source_node_id para
    evitar que cada fragmento seja contado como um nó diferente.
    """

    node_id = metadata.get("source_node_id")

    if not node_id:
        node_id = metadata.get("chunk_id")

    if not isinstance(node_id, str) or not node_id:
        return None

    return FRAGMENT_SUFFIX_PATTERN.sub("", node_id)


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

    match = ARTICLE_ID_PATTERN.match(node_id)

    if match:
        return match.group("article")

    return None


def _unique_preserving_order(
    identifiers: list[str],
) -> list[str]:
    """Remove duplicados sem alterar a ordem de recuperação."""

    return list(dict.fromkeys(identifiers))


# ============================================================
# MÉTRICAS DE RECUPERAÇÃO
# ============================================================

def _calculate_metrics_at_k(
    retrieved_ids: list[str],
    reference_ids: list[str],
    k: int,
) -> dict[str, float | None]:
    """
    Calcula Precision@K, Recall@K, MRR@K e Hit Rate@K.

    A ordem de retrieved_ids corresponde à ordem real
    de recuperação, após remover identificadores repetidos.
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
    level: str,
    k_values: list[int],
) -> dict[str, Any]:
    """Calcula a média das métricas de um nível de avaliação."""

    evaluated_questions = [
        item
        for item in question_results
        if item["metrics"][level][str(k_values[0])]["precision"]
        is not None
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
                item["metrics"][level][str(k)][metric_name]
                for item in evaluated_questions
                if (
                    item["metrics"][level][str(k)][metric_name]
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
# AVALIAÇÃO DO RETRIEVER
# ============================================================

def _run_legal_hybrid_evaluation(
    retriever_config: dict[str, Any],
    questions: list[dict[str, Any]],
    k_values: list[int],
) -> dict[str, Any]:
    """Executa a avaliação usando o recuperador jurídico híbrido."""

    print("\n" + "=" * 65)
    print("INICIALIZANDO RETRIEVER JURÍDICO")
    print("=" * 65)

    retriever, provider = create_retriever(
        provider=retriever_config.get("provider", "local"),
        k=retriever_config.get("top_k", 4),
        candidate_k=retriever_config.get("candidate_k", 24),
        collection_name=retriever_config.get(
            "collection_name",
            "constituicao_legal",
        ),
    )

    vector_store = retriever.vector_store
    collection = vector_store._collection

    collection_name = collection.name
    indexed_count = collection.count()

    if indexed_count <= 0:
        raise RuntimeError(
            f"A coleção '{collection_name}' está vazia."
        )

    print(f"Provedor: {provider}")
    print(f"Coleção: {collection_name}")
    print(f"Documentos indexados: {indexed_count}")
    print(f"Top K: {retriever_config.get('top_k', 4)}")
    print(
        f"Candidatos: "
        f"{retriever_config.get('candidate_k', 24)}"
    )

    question_results = []

    for item in questions:

        question_id = item["id"]
        question_text = item["question"]

        print(f"\n[{question_id}] {question_text}")

        # A busca recebe SOMENTE a pergunta.
        # As referências não participam da recuperação.
        start_time = perf_counter()

        documents = retriever.invoke(question_text)

        elapsed_seconds = perf_counter() - start_time

        retrieved_documents = []
        retrieved_article_ids = []
        retrieved_node_ids = []

        for rank, document in enumerate(documents, start=1):

            metadata = _to_json_safe(
                dict(document.metadata or {})
            )

            node_id = _get_node_id(metadata)

            article_id = _get_article_id(
                metadata,
                node_id,
            )

            if node_id:
                retrieved_node_ids.append(node_id)

            if article_id:
                retrieved_article_ids.append(article_id)

            retrieved_documents.append({
                "rank": rank,
                "node_id": node_id,
                "article_id": article_id,
                "metadata": metadata,
                "page_content": document.page_content,
                "characters": len(document.page_content),
            })

        retrieved_article_ids = _unique_preserving_order(
            retrieved_article_ids
        )

        retrieved_node_ids = _unique_preserving_order(
            retrieved_node_ids
        )

        # O gabarito somente é consultado depois da recuperação.
        reference_articles = item.get(
            "reference_articles",
            [],
        )

        reference_nodes = item.get(
            "reference_nodes",
            [],
        )

        metrics = _calculate_question_metrics(
            retrieved_articles=retrieved_article_ids,
            retrieved_nodes=retrieved_node_ids,
            reference_articles=reference_articles,
            reference_nodes=reference_nodes,
            k_values=k_values,
        )

        question_result = {
            "id": question_id,
            "category": item.get("category"),
            "question": question_text,
            "ground_truth": item.get("ground_truth"),
            "reference_articles": reference_articles,
            "reference_nodes": reference_nodes,
            "retrieved_count": len(documents),
            "retrieved_article_ids": retrieved_article_ids,
            "retrieved_node_ids": retrieved_node_ids,
            "elapsed_seconds": round(elapsed_seconds, 6),
            "metrics": metrics,
            "retrieved_documents": retrieved_documents,
        }

        question_results.append(question_result)

        print(
            f"  Documentos recuperados: {len(documents)}"
        )

        print(
            f"  Artigos distintos: "
            f"{len(retrieved_article_ids)}"
        )

        print(
            f"  Unidades jurídicas distintas: "
            f"{len(retrieved_node_ids)}"
        )

        print(
            f"  Tempo: {elapsed_seconds:.4f} segundos"
        )

        for k in k_values:

            article_metric = metrics["article_level"][str(k)]
            node_metric = metrics["legal_unit_level"][str(k)]

            print(
                f"  Artigos — P@{k}: "
                f"{article_metric['precision']} | "
                f"R@{k}: {article_metric['recall']}"
            )

            print(
                f"  Unidades — P@{k}: "
                f"{node_metric['precision']} | "
                f"R@{k}: {node_metric['recall']}"
            )

    # --------------------------------------------------------
    # RESUMO
    # --------------------------------------------------------

    summary = {
        "questions_evaluated": len(question_results),

        "average_retrieved_documents": round(
            mean(
                item["retrieved_count"]
                for item in question_results
            ),
            2,
        ),

        "average_query_seconds": round(
            mean(
                item["elapsed_seconds"]
                for item in question_results
            ),
            6,
        ),

        "article_level": _aggregate_level_metrics(
            question_results,
            "article_level",
            k_values,
        ),

        "legal_unit_level": _aggregate_level_metrics(
            question_results,
            "legal_unit_level",
            k_values,
        ),
    }

    return {
        "configuration": {
            "retriever_type": "legal_hybrid",
            "provider": provider,
            "collection_name": collection_name,
            "indexed_documents": indexed_count,
            "top_k": retriever_config.get("top_k", 4),
            "candidate_k": retriever_config.get(
                "candidate_k",
                24,
            ),
            "k_values": k_values,
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
    Executa a avaliação do recuperador jurídico.

    Os parâmetros são carregados do arquivo JSON de configuração.
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

    evaluation_config = config.get("evaluation", {})

    k_values = sorted(
        evaluation_config.get("k_values", [1, 2, 4])
    )

    questions = dataset["questions"]

    print("=" * 65)
    print("AVALIAÇÃO RAG JURÍDICO — POLITIZE-SE")
    print("=" * 65)

    print(
        f"Dataset: "
        f"{dataset.get('dataset_id', dataset_path.stem)}"
    )

    print(f"Versão: {dataset.get('version', 'não informada')}")
    print(f"Perguntas: {len(questions)}")
    print(f"Retriever: {retriever_config['type']}")
    print(f"K avaliados: {k_values}")

    result = _run_legal_hybrid_evaluation(
        retriever_config=retriever_config,
        questions=questions,
        k_values=k_values,
    )

    output_config = config.get("output", {})

    output_directory = _resolve_path(
        output_config.get(
            "directory",
            "data/avaliacoes/resultados",
        )
    )

    output_filename = output_config.get(
        "filename",
        "resultado_rag_juridico.json",
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

    results_payload = {
        "evaluation": {
            "name": config.get(
                "name",
                "Avaliação do RAG Jurídico",
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
            },
        },
        "results": result,
    }

    with output_path.open("w", encoding="utf-8") as file:
        json.dump(
            results_payload,
            file,
            ensure_ascii=False,
            indent=4,
        )

    summary = result["summary"]

    print("\n" + "=" * 65)
    print("AVALIAÇÃO CONCLUÍDA")
    print("=" * 65)

    print(
        f"\nTempo médio de busca: "
        f"{summary['average_query_seconds']} segundos"
    )

    print("\nRESULTADOS — NÍVEL DE ARTIGO")

    for k, metrics in summary["article_level"]["metrics"].items():
        print(f"\nK = {k}")

        for metric, value in metrics.items():
            print(f"  {metric}: {value}")

    print("\nRESULTADOS — UNIDADES JURÍDICAS")

    for k, metrics in summary["legal_unit_level"]["metrics"].items():
        print(f"\nK = {k}")

        for metric, value in metrics.items():
            print(f"  {metric}: {value}")

    print(f"\nResultado salvo em: {output_path}")

    return output_path
