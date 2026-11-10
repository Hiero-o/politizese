import json
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

from src.core.config import PROJECT_ROOT
from src.rag.parent_retriever import create_parent_document_retriever

SUPPORTED_RETRIEVERS = {"parent_document"}

def _resolve_path(path:str | Path) -> Path:
    """resolve caminhos relativos a partir da raiz do projeto (project root)"""
    
    resolved = Path(path).expanduser()
    
    if not resolved.is_absolute():
        resolved = PROJECT_ROOT / resolved
    
    return resolved.resolve()


def _validate_dataset(dataset: dict[str, Any]) -> None:
    """Valida as perguntas do conjunto de avaliação"""
    
    questions = dataset.get("questions")
    
    if not isinstance(questions, list) or not questions:
        raise ValueError("O dataset precisa possuir uma lista 'question' não vazia.")
    
    question_ids = set()
    
    for index, item in enumerate(questions):
        if not isinstance(item,dict):
            raise ValueError(f"A pergunta na posição {index} deve ser um objeto!")
        
        question_id = item.get("id")
        question = item.get("question")
        
        if not isinstance(question_id, str) or not question_id.strip():
            raise ValueError(f"pergunta na posição {index} sem identificador válido")
        
        if question_id in question_ids:
            raise ValueError(f"Identificador de perguntas dupliucado: {question_id} !!" )
        
        question_ids.add(question_id)
        
        if not isinstance(question, str) or not question.strip():
            raise ValueError(f"A pergunta {question_id} não possui texto válido!")
        
def _validate_config(config: dict[str, Any]) -> None:
    """Valida as configs dos experimentos."""
    
    retriever_config = config.get("retriever")
    
    if not isinstance(retriever_config, dict):
        raise ValueError("a configuração precisa possuir um objeto 'retriever'")
    
    retriever_type = retriever_config.get("type")
    
    if retriever_type not in SUPPORTED_RETRIEVERS:
        raise ValueError(f"Tipo de retriever não suportado {retriever_type} -- Tipos disponíveis: {sorted(SUPPORTED_RETRIEVERS)} !" )
    
    experiments = config.get("experiments")
    
    if not isinstance(experiments, list) or not experiments:
        raise ValueError("A configuração precisa possuir uma lista 'experiments' NÃO vazia!")
    
    experiment_ids = set()
    
    for index, experiment in enumerate(experiments):
        if not isinstance(experiment, dict):
            raise ValueError(f"Experimento na posição {index} DEVE ser um objeto.")
        
        experiment_id = experiment.get("id")
        
        if not isinstance(experiment_id, str) or not experiment_id.strip():
            raise ValueError(f"Experimento na posição {index} Deve possuir um indentificador válido")
        
        if experiment_id in experiment_ids:
            raise ValueError(f" ID de experimento duplicado: {experiment_id}")
        
        experiment_ids.add(experiment_id)
        
        parent_size = experiment.get("parent_chunk_size")
        parent_overlap = experiment.get("parent_chunk_overlap")
        
        if not isinstance(parent_size, int) or isinstance(parent_size, bool):
            raise ValueError(f"Tamanho do chunk pai inválido: {experiment_id}")
        
        if not isinstance(parent_overlap, int) or isinstance(parent_overlap, bool):
            raise ValueError(f"Ovelap do chunk pai inválido: {experiment_id}")
        
    output_config = config.get("output", {})
    
    if not isinstance(output_config, dict):
        raise ValueError("'output' deve ser um objeto JSON.")
        
def _to_json_safe(value: Any) -> Any:
    """Converte valores para tipos compatíveis com JSON."""

    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    
    if isinstance(value, dict):
        return {
            str(key): _to_json_safe(item)
            for key, item in value.items()
        }
        
    if isinstance (value, (list, tuple)):
        return [
            _to_json_safe(item)
            for item in value
        ]
        
    return str(value)

def _load_json(path: Path) -> dict[str, Any]:
    """carrega um arquivo json e valida sua estrutura básica"""
    
    if not path.is_file():
        raise FileNotFoundError(f"Arquivo JSON não encontrado: {path}")
    
    try:
        with path.open("r", encoding="utf-8") as file:
            data =json.load(file)
    
    except json.JSONDecodeError as error:
        raise ValueError(f"JSON inválid em {path}, linha {error.lineno}, coluna {error.colno}: {error.msg}") from error
    
    if not isinstance(data, dict):
        raise ValueError(f"O arquivo {path} deve conter um objeto JSON.")
    
    return data

def _run_parent_document_experiment(
    experiment: dict[str, Any],
    retriever_config: dict[str, Any],
    questions: list[dict[str, Any]],
) -> dict[str, Any]:
    """Executa um experimento com ParentDocumentRetriever."""

    experiment_id = experiment["id"]

    print("\n" + "=" * 65)
    print(f"EXPERIMENTO: {experiment_id}")
    print("=" * 65)

    retriever, provider = create_parent_document_retriever(
        parent_chunk_size=experiment["parent_chunk_size"],
        parent_chunk_overlap=experiment["parent_chunk_overlap"],
        child_chunk_size=retriever_config["child_chunk_size"],
        child_chunk_overlap=retriever_config["child_chunk_overlap"],
        k=retriever_config["top_k"],
        provider=retriever_config["provider"],
    )

    vector_store = retriever.vectorstore
    collection = vector_store._collection
    collection_name = collection.name

    # Verifica se a coleção experimental já foi indexada.
    child_count = collection.count()
    parent_count = sum(
        1 for _ in retriever.docstore.yield_keys()
    )

    if child_count == 0 or parent_count == 0:
        raise RuntimeError(
            f"A coleção do experimento '{experiment_id}' "
            "não possui filhos ou documentos pais persistidos.\n"
            f"Coleção: {collection_name}\n"
            f"Filhos: {child_count}\n"
            f"Pais: {parent_count}"
        )

    print(f"Coleção: {collection_name}")
    print(f"Provedor: {provider}")
    print(f"Chunks filhos indexados: {child_count}")
    print(f"Documentos pais armazenados: {parent_count}")

    experiment_results = {
        "experiment_id": experiment_id,
        "configuration": {
            **experiment,
            "retriever_type": retriever_config["type"],
            "provider": provider,
            "child_chunk_size": retriever_config["child_chunk_size"],
            "child_chunk_overlap": retriever_config["child_chunk_overlap"],
            "top_k": retriever_config["top_k"],
        },
        "collection": collection_name,
        "indexed_children": child_count,
        "stored_parents": parent_count,
        "questions": [],
    }
    for item in questions:
        question_id = item["id"]
        question_text = item["question"]

        print(f"\n[{question_id}] {question_text}")

        start_time = perf_counter()

        documents = retriever.invoke(question_text)

        elapsed_seconds = perf_counter() - start_time

        retrieved_documents = []

        for rank, document in enumerate(documents, start=1):
            metadata = _to_json_safe(document.metadata or {})

            document_result = {
                "rank": rank,
                "metadata": metadata,
                "page_content": document.page_content,
                "characters": len(document.page_content),
            }

            retrieved_documents.append(document_result)

            page = metadata.get(
                "pagina",
                metadata.get("page", "não identificada"),
            )

            print(
                f"  Documento {rank}: página {page} | "
                f"{len(document.page_content)} caracteres"
            )

        print(f"  Pais recuperados: {len(documents)}")
        print(f"  Tempo: {elapsed_seconds:.4f} segundos")

        experiment_results["questions"].append(
            {
                "id": question_id,
                "category": item.get("category"),
                "question": question_text,
                "ground_truth": item.get("ground_truth"),
                "reference_articles": item.get("reference_articles", []),
                "retrieved_count": len(documents),
                "elapsed_seconds": round(elapsed_seconds, 6),
                "retrieved_documents": retrieved_documents,
            }
        )

    # Estatísticas descritivas, sem atribuir nota de qualidade.
    question_results = experiment_results["questions"]

    experiment_results["summary"] = {
        "questions_evaluated": len(question_results),
        "total_parents_retrieved": sum(
            item["retrieved_count"]
            for item in question_results
        ),
        "average_parents_per_question": round(
            sum(item["retrieved_count"] for item in question_results)
            / len(question_results),
            2,
        ),
        "average_context_characters": round(
            sum(
                document["characters"]
                for item in question_results
                for document in item["retrieved_documents"]
            )
            / max(
                sum(item["retrieved_count"] for item in question_results),
                1,
            ),
            2,
        ),
        "average_query_seconds": round(
            sum(item["elapsed_seconds"] for item in question_results)
            / len(question_results),
            6,
        ),
    }

    return experiment_results


def evaluate_retrievers(
    config_path: str | Path,
) -> Path:
    """
    Executa os experimentos definidos em um arquivo de configuração.

    O dataset, os parâmetros, os experimentos e o destino dos
    resultados são determinados pelos arquivos JSON.
    """

    resolved_config_path = _resolve_path(config_path)
    config = _load_json(resolved_config_path)

    _validate_config(config)

    dataset_path_value = config.get("dataset")

    if not isinstance(dataset_path_value, str) or not dataset_path_value.strip():
        raise ValueError(
            "O campo 'dataset' precisa indicar um caminho válido."
        )

    dataset_path = _resolve_path(dataset_path_value)
    dataset = _load_json(dataset_path)

    _validate_dataset(dataset)

    retriever_config = config["retriever"]
    questions = dataset["questions"]

    print("=" * 65)
    print("AVALIAÇÃO DE RECUPERADORES — POLITIZE-SE")
    print("=" * 65)

    print(f"Dataset: {dataset.get('dataset_id', dataset_path.stem)}")
    print(f"Perguntas: {len(questions)}")
    print(f"Tipo de retriever: {retriever_config['type']}")
    print(f"Experimentos: {len(config['experiments'])}")

    all_results = []

    for experiment in config["experiments"]:
        if retriever_config["type"] == "parent_document":
            result = _run_parent_document_experiment(
                experiment=experiment,
                retriever_config=retriever_config,
                questions=questions,
            )
        else:
            raise ValueError(
                "Tipo de retriever ainda não implementado: "
                f"{retriever_config['type']}"
            )
            

        all_results.append(result)

    output_config = config.get("output", {})

    output_directory = _resolve_path(
        output_config.get(
            "directory",
            "data/avaliacoes/resultados",
        )
    )

    output_filename = output_config.get(
        "filename",
        "resultado_retrievers.json",
    )

    if not isinstance(output_filename, str) or not output_filename.strip():
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

    results_payload = {
        "evaluation": {
            "name": config.get("name", "Avaliação de retrievers"),
            "dataset_id": dataset.get("dataset_id"),
            "dataset_name": dataset.get("name"),
            "dataset_version": dataset.get("version"),
            "dataset_source": dataset.get("source"),
            "dataset_path": str(dataset_path.relative_to(PROJECT_ROOT)),
            "executed_at": datetime.now(timezone.utc).isoformat(),
        },
        "experiments": all_results,
    }

    with output_path.open("w", encoding="utf-8") as file:
        json.dump(
            results_payload,
            file,
            ensure_ascii=False,
            indent=4,
        )

    print("\n" + "=" * 65)
    print("AVALIAÇÃO CONCLUÍDA")
    print("=" * 65)

    for result in all_results:
        summary = result["summary"]

        print(f"\n{result['experiment_id']}")
        print(
            "Média de pais recuperados: "
            f"{summary['average_parents_per_question']}"
        )
        print(
            "Média de caracteres por contexto: "
            f"{summary['average_context_characters']}"
        )
        print(
            "Tempo médio por pergunta: "
            f"{summary['average_query_seconds']} segundos"
        )

    print(f"\nResultados salvos em: {output_path}")

    return output_path