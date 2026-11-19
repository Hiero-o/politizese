
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import math
import re

from datetime import datetime
from pathlib import Path
from types import MethodType
from typing import Any

from openai import AsyncOpenAI

from ragas.embeddings.base import embedding_factory
from ragas.llms import llm_factory
from ragas.metrics.collections import (
    Faithfulness,
    AnswerRelevancy,
    ContextPrecision,
    ContextRecall,
)

from src.agents.react_agent import build_react_agent


# ============================================================
# CONFIGURAÇÕES
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]

QUESTIONS_FILE = (
    PROJECT_ROOT
    / "data"
    / "evaluation"
    / "ragas_questions.json"
)
DEFAULT_LEGAL_TREE = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "constituicao_artigos.json"
)
DEFAULT_COLLECTION_NAME = "constituicao_legal_clean_v2"

RESULTS_DIR = (
    PROJECT_ROOT
    / "data"
    / "evaluation"
    / "results"
)

OLLAMA_BASE_URL = "http://localhost:11434/v1"

EVALUATOR_MODEL = "qwen3.5:9b"
EMBEDDING_MODEL = "nomic-embed-text:latest"

METRIC_NAMES = (
    "faithfulness",
    "answer_relevancy",
    "context_precision",
    "context_recall",
)


# ============================================================
# CARREGAMENTO E VALIDAÇÃO DAS PERGUNTAS
# ============================================================

def load_questions(questions_file: Path = QUESTIONS_FILE) -> list[dict[str, Any]]:
    """Carrega e valida o conjunto de avaliação indicado na linha de comando."""

    if not questions_file.exists():
        raise FileNotFoundError(
            f"Arquivo de perguntas não encontrado: {questions_file}"
        )

    with questions_file.open(
        "r",
        encoding="utf-8",
    ) as file:
        questions = json.load(file)

    if not isinstance(questions, list) or not questions:
        raise ValueError(
            "O arquivo de avaliação precisa conter uma lista "
            "não vazia de perguntas."
        )

    required_fields = (
        "id",
        "category",
        "user_input",
        "reference",
    )

    seen_ids = set()

    for index, question in enumerate(questions, start=1):
        if not isinstance(question, dict):
            raise ValueError(
                f"Registro {index} precisa ser um objeto JSON."
            )

        for field in required_fields:
            value = question.get(field)

            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"Campo '{field}' inválido no registro {index}."
                )

        question_id = question["id"]

        if question_id in seen_ids:
            raise ValueError(
                f"ID duplicado no conjunto de avaliação: {question_id}"
            )

        seen_ids.add(question_id)

        # Campo opcional para perguntas sem armadilha.
        question.setdefault("trap_type", None)

    return questions


# ============================================================
# CAPTURA DAS OBSERVAÇÕES COMPLETAS DO AGENTE
# ============================================================

def run_agent_with_capture(
    agent: Any,
    question: str,
) -> tuple[Any, list[dict[str, Any]]]:
    """
    Executa o agente e captura as observações completas das ferramentas.

    O trace normal limita o tamanho das observações.
    Aqui capturamos o retorno antes desse truncamento.
    """

    captured_observations = []

    original_execute = agent._execute_tool

    def capture_execute(
        self,
        tool_name: str,
        arguments: Any,
    ) -> tuple[str, str]:

        observation, status = original_execute(
            tool_name=tool_name,
            arguments=arguments,
        )

        captured_observations.append(
            {
                "tool": tool_name,
                "arguments": arguments,
                "status": status,
                "observation": observation,
            }
        )

        return observation, status

    agent._execute_tool = MethodType(
        capture_execute,
        agent,
    )

    try:
        result = agent.invoke(question)

    finally:
        # Restaura o comportamento original do agente.
        delattr(agent, "_execute_tool")

    return result, captured_observations


# ============================================================
# EXTRAÇÃO DOS DOCUMENTOS RECUPERADOS
# ============================================================

def extract_retrieved_documents(
    observations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Extrai documentos e contextos superiores das observações JSON.

    Apenas o conteúdo textual será enviado ao RAGAS.
    Os identificadores e metadados serão preservados no resultado.
    """

    documents_by_key = {}

    def add_document(
        doc_id: Any,
        content: Any,
        source: str,
        metadata: Any = None,
    ) -> None:

        if not isinstance(content, str):
            return

        content = content.strip()

        if not content:
            return

        normalized_id = (
            str(doc_id)
            if doc_id is not None
            else ""
        )

        key = (
            normalized_id,
            content,
        )

        if key in documents_by_key:
            return

        selected_metadata = {}

        if isinstance(metadata, dict):
            allowed_fields = (
                "document_part",
                "article_number",
                "legal_unit",
                "number",
            )

            selected_metadata = {
                field: metadata[field]
                for field in allowed_fields
                if field in metadata
            }

        documents_by_key[key] = {
            "doc_id": normalized_id or None,
            "source": source,
            "content": content,
            "metadata": selected_metadata,
        }

    for observation in observations:
        raw_observation = observation.get("observation", "")

        try:
            payload = json.loads(raw_observation)

        except (json.JSONDecodeError, TypeError):
            continue

        if not isinstance(payload, dict):
            continue

        if payload.get("ok") is False:
            continue

        documents = payload.get("documents", [])

        if not isinstance(documents, list):
            continue

        for document in documents:
            if not isinstance(document, dict):
                continue

            metadata = document.get("metadata") or {}

            add_document(
                doc_id=document.get("doc_id"),
                content=document.get("content"),
                source="retrieved_document",
                metadata=metadata,
            )

            # Inclui contexto dos dispositivos superiores,
            # quando ele foi enviado ao modelo pelo agente.
            parent_context = metadata.get(
                "parent_context",
                [],
            )

            if not isinstance(parent_context, list):
                continue

            for parent in parent_context:
                if not isinstance(parent, dict):
                    continue

                add_document(
                    doc_id=parent.get("doc_id"),
                    content=parent.get("content"),
                    source="parent_context",
                    metadata=parent.get("metadata"),
                )

    return list(documents_by_key.values())


def extract_tool_call_diagnostics(
    observations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Extrai consultas, subperguntas e IDs por chamada de ferramenta.

    O conteúdo integral dos documentos continua em ``retrieved_documents``.
    Aqui ficam apenas os metadados necessários para rastrear cada chamada.
    """

    diagnostics = []

    for call_index, observation in enumerate(observations, start=1):
        diagnostic: dict[str, Any] = {
            "call_index": call_index,
            "tool": observation.get("tool"),
            "arguments": observation.get("arguments", {}),
            "status": observation.get("status"),
            "ok": None,
            "strategy": None,
            "original_question": None,
            "semantic_query": None,
            "lexical_query": None,
            "is_compound": None,
            "decomposition_reason": None,
            "subquestions": [],
            "document_count_reported": None,
            "retrieved_document_count_reported": None,
            "document_count_observed": 0,
            "document_ids": [],
            "parent_context_ids": [],
            "documents": [],
        }

        raw_observation = observation.get("observation", "")

        try:
            payload = json.loads(raw_observation)
        except (json.JSONDecodeError, TypeError) as error:
            diagnostic["observation_parse_error"] = (
                f"{type(error).__name__}: {error}"
            )
            diagnostics.append(diagnostic)
            continue

        if not isinstance(payload, dict):
            diagnostic["observation_parse_error"] = (
                "A observação JSON não contém um objeto."
            )
            diagnostics.append(diagnostic)
            continue

        diagnostic.update(
            {
                "ok": payload.get("ok"),
                "strategy": payload.get("strategy"),
                "original_question": payload.get("original_question"),
                "semantic_query": payload.get("semantic_query"),
                "lexical_query": payload.get("lexical_query"),
                "is_compound": payload.get("is_compound"),
                "decomposition_reason": payload.get(
                    "decomposition_reason"
                ),
                "document_count_reported": payload.get("document_count"),
                "retrieved_document_count_reported": payload.get(
                    "retrieved_document_count"
                ),
            }
        )

        raw_subquestions = payload.get("subquestions", [])
        if isinstance(raw_subquestions, list):
            diagnostic["subquestions"] = [
                subquestion
                for subquestion in raw_subquestions
                if isinstance(subquestion, dict)
            ]

        raw_documents = payload.get("documents", [])
        if not isinstance(raw_documents, list):
            raw_documents = []

        document_ids = []
        parent_context_ids = []
        document_summaries = []

        for document in raw_documents:
            if not isinstance(document, dict):
                continue

            raw_doc_id = document.get("doc_id")
            doc_id = str(raw_doc_id) if raw_doc_id is not None else None

            if doc_id and doc_id not in document_ids:
                document_ids.append(doc_id)

            metadata = document.get("metadata") or {}
            if not isinstance(metadata, dict):
                metadata = {}

            raw_parent_context = metadata.get("parent_context", [])
            if isinstance(raw_parent_context, dict):
                parent_items = [raw_parent_context]
            elif isinstance(raw_parent_context, list):
                parent_items = raw_parent_context
            else:
                parent_items = []

            current_parent_ids = []
            for parent in parent_items:
                if not isinstance(parent, dict):
                    continue

                raw_parent_id = parent.get("doc_id")
                if raw_parent_id is None:
                    continue

                parent_id = str(raw_parent_id)
                if parent_id not in parent_context_ids:
                    parent_context_ids.append(parent_id)
                if parent_id not in current_parent_ids:
                    current_parent_ids.append(parent_id)

            document_summaries.append(
                {
                    "doc_id": doc_id,
                    "article_number": metadata.get("article_number"),
                    "legal_unit": metadata.get("legal_unit"),
                    "number": metadata.get("number"),
                    "parent_context_ids": current_parent_ids,
                }
            )

        diagnostic["document_count_observed"] = len(document_ids)
        diagnostic["document_ids"] = document_ids
        diagnostic["parent_context_ids"] = parent_context_ids
        diagnostic["documents"] = document_summaries

        if payload.get("ok") is False:
            diagnostic["tool_error"] = payload.get("error")

        diagnostics.append(diagnostic)

    return diagnostics


def print_tool_call_diagnostics(
    tool_calls: list[dict[str, Any]],
) -> None:
    """Exibe um resumo das consultas e evidências de cada chamada."""

    for call in tool_calls:
        print(
            f"\n[RAG TRACE] Chamada {call['call_index']}: "
            f"{call.get('tool')} | estratégia={call.get('strategy')}"
        )

        if call.get("semantic_query"):
            print(f"  Consulta semântica: {call['semantic_query']}")

        if call.get("lexical_query"):
            print(f"  Consulta lexical: {call['lexical_query']}")

        for subquestion in call.get("subquestions", []):
            print(
                "  Subpergunta "
                f"{subquestion.get('index', '?')}: "
                f"{subquestion.get('question', '')}"
            )
            if subquestion.get("semantic_query"):
                print(
                    "    Semântica: "
                    f"{subquestion['semantic_query']}"
                )
            if subquestion.get("lexical_query"):
                print(
                    "    Lexical: "
                    f"{subquestion['lexical_query']}"
                )

        print(
            "  Documentos diretos: "
            f"{call.get('document_ids', [])}"
        )
        print(
            "  Contextos superiores: "
            f"{call.get('parent_context_ids', [])}"
        )


# ============================================================
# CONFIGURAÇÃO DAS MÉTRICAS
# ============================================================

async def build_evaluator():
    """Inicializa o avaliador RAGAS com modelos locais do Ollama."""

    client = AsyncOpenAI(
        base_url=OLLAMA_BASE_URL,
        api_key="ollama",
        timeout=240.0,
    )

    evaluator_llm = llm_factory(
        EVALUATOR_MODEL,
        provider="openai",
        client=client,
        temperature=0,
        max_tokens=4096,
    )

    # Desativa o raciocínio do Qwen durante a geração estruturada.
    evaluator_llm.model_args["extra_body"] = {
        "reasoning_effort": "none"
    }

    evaluator_embeddings = embedding_factory(
        "openai",
        model=EMBEDDING_MODEL,
        client=client,
    )

    metrics = {
        "faithfulness": Faithfulness(
            llm=evaluator_llm,
        ),
        "answer_relevancy": AnswerRelevancy(
            llm=evaluator_llm,
            embeddings=evaluator_embeddings,
        ),
        "context_precision": ContextPrecision(
            llm=evaluator_llm,
        ),
        "context_recall": ContextRecall(
            llm=evaluator_llm,
        ),
    }

    return client, metrics


# ============================================================
# EXECUÇÃO DAS MÉTRICAS
# ============================================================

def safe_float(value: Any) -> float | None:
    """Converte resultados em números JSON seguros."""

    if value is None:
        return None

    try:
        number = float(value)

    except (TypeError, ValueError):
        return None

    if not math.isfinite(number):
        return None

    return number


async def evaluate_sample(
    question: dict[str, Any],
    response: str,
    contexts: list[str],
    metrics: dict[str, Any],
) -> tuple[dict[str, float | None], dict[str, str]]:
    """Calcula individualmente as quatro métricas."""

    metric_inputs = {
        "faithfulness": {
            "user_input": question["user_input"],
            "response": response,
            "retrieved_contexts": contexts,
        },
        "answer_relevancy": {
            "user_input": question["user_input"],
            "response": response,
        },
        "context_precision": {
            "user_input": question["user_input"],
            "reference": question["reference"],
            "retrieved_contexts": contexts,
        },
        "context_recall": {
            "user_input": question["user_input"],
            "reference": question["reference"],
            "retrieved_contexts": contexts,
        },
    }

    scores = {
        name: None
        for name in METRIC_NAMES
    }

    errors = {}

    # Execução sequencial para evitar sobrecarga do Ollama.
    for name, metric in metrics.items():

        print(f"\nCalculando {name}...")

        try:
            result = await metric.ascore(
                **metric_inputs[name]
            )

            score = safe_float(result.value)

            scores[name] = score

            if score is None:
                errors[name] = (
                    "A métrica retornou um valor não numérico "
                    "ou não finito."
                )

            else:
                print(f"Resultado: {score:.4f}")

        except Exception as error:
            errors[name] = (
                f"{type(error).__name__}: {error}"
            )

            print(f"Falha em {name}: {errors[name]}")

    return scores, errors


# ============================================================
# RESUMO ESTATÍSTICO
# ============================================================

def calculate_averages(
    results: list[dict[str, Any]],
) -> dict[str, float | None]:

    averages = {}

    for metric in METRIC_NAMES:
        values = [
            item["metrics"].get(metric)
            for item in results
            if item.get("metrics", {}).get(metric) is not None
        ]

        averages[metric] = (
            round(sum(values) / len(values), 4)
            if values
            else None
        )

    return averages


def calculate_category_averages(
    results: list[dict[str, Any]],
) -> dict[str, dict[str, float | None]]:

    categories = sorted(
        {
            item["category"]
            for item in results
        }
    )

    return {
        category: calculate_averages(
            [
                item
                for item in results
                if item["category"] == category
            ]
        )
        for category in categories
    }


# ============================================================
# SALVAMENTO DOS RESULTADOS
# ============================================================

def save_results(
    results: list[dict[str, Any]],
    json_path: Path,
    csv_path: Path,
    provider: str,
    label: str,
    total_questions: int,
    questions_file: Path = QUESTIONS_FILE,
    collection_name: str = DEFAULT_COLLECTION_NAME,
    legal_tree_path: Path = DEFAULT_LEGAL_TREE,
    prompt_task: str = "react_agent",
) -> None:
    """Salva resultados completos e uma planilha CSV."""

    payload = {
        "evaluation_label": label,
        "generated_at": datetime.now().astimezone().isoformat(),
        "agent_provider": provider,
        "evaluator_model": EVALUATOR_MODEL,
        "embedding_model": EMBEDDING_MODEL,
        "total_questions": total_questions,
        "completed_questions": len(results),
        "questions_file": str(questions_file),
        "collection_name": collection_name,
        "legal_tree_path": str(legal_tree_path),
        "prompt_task": prompt_task,
        "average_metrics": calculate_averages(results),
        "category_averages": calculate_category_averages(results),
        "results": results,
    }

    with json_path.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            payload,
            file,
            ensure_ascii=False,
            indent=4,
            allow_nan=False,
        )

    csv_fields = [
        "id",
        "category",
        "trap_type",
        "user_input",
        "response",
        "reference",
        "reference_source",
        "retrieved_document_count",
        "retrieved_context_count",
        "tool_calls",
        "agent_total_duration_seconds",
        "agent_tool_calls_count",
        *METRIC_NAMES,
        "agent_error",
    ]

    with csv_path.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=csv_fields,
            extrasaction="ignore",
        )

        writer.writeheader()

        for item in results:
            row = {
                **item,
                **item.get("metrics", {}),
                # CSV não serializa listas/dicionários como JSON sozinho.
                "tool_calls": json.dumps(
                    item.get("tool_calls", []),
                    ensure_ascii=False,
                ),
            }

            writer.writerow(row)


# ============================================================
# EXECUÇÃO PRINCIPAL
# ============================================================

async def main():
    parser = argparse.ArgumentParser(
        description="Avaliação do Politizese com RAGAS."
    )

    parser.add_argument(
        "--ids",
        nargs="+",
        help="Executa somente os IDs informados. Exemplo: --ids Q03 Q05",
    )

    parser.add_argument(
        "--limit",
        type=int,
        help="Limita a quantidade de perguntas executadas.",
    )

    parser.add_argument(
        "--label",
        default="baseline",
        help="Identificador da avaliação. Padrão: baseline.",
    )

    parser.add_argument(
        "--questions-file",
        default=str(QUESTIONS_FILE),
        help="JSON com perguntas e referências preenchidas. Caminhos relativos usam a raiz do projeto.",
    )
    parser.add_argument(
        "--collection",
        default=DEFAULT_COLLECTION_NAME,
        help="Nome-base da coleção ChromaDB que contém a base a avaliar.",
    )
    parser.add_argument(
        "--legal-tree",
        default=str(DEFAULT_LEGAL_TREE),
        help="JSON da árvore jurídica usada pelo índice lexical BM25.",
    )
    parser.add_argument(
        "--prompt-task",
        default="react_agent",
        help="Task XML do agente. Use react_agent_legislativo na base simulada.",
    )

    args = parser.parse_args()

    if args.limit is not None and args.limit < 1:
        parser.error("--limit precisa ser maior que zero.")

    label = re.sub(
        r"[^a-zA-Z0-9_-]",
        "_",
        args.label,
    )

    questions_path = Path(args.questions_file).expanduser()
    if not questions_path.is_absolute():
        questions_path = (PROJECT_ROOT / questions_path).resolve()

    legal_tree_path = Path(args.legal_tree).expanduser()
    if not legal_tree_path.is_absolute():
        legal_tree_path = (PROJECT_ROOT / legal_tree_path).resolve()

    questions = load_questions(questions_path)

    if args.ids:
        available_ids = {
            question["id"]
            for question in questions
        }

        unknown_ids = set(args.ids) - available_ids

        if unknown_ids:
            raise ValueError(
                f"IDs não encontrados: {sorted(unknown_ids)}"
            )

        selected_ids = set(args.ids)

        questions = [
            question
            for question in questions
            if question["id"] in selected_ids
        ]

    if args.limit:
        questions = questions[:args.limit]

    if not questions:
        raise ValueError(
            "Nenhuma pergunta foi selecionada."
        )

    RESULTS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    json_path = RESULTS_DIR / (
        f"ragas_{label}_{timestamp}.json"
    )

    csv_path = RESULTS_DIR / (
        f"ragas_{label}_{timestamp}.csv"
    )

    print("=" * 60)
    print("POLITIZE-SE | AVALIAÇÃO OFICIAL RAGAS")
    print("=" * 60)

    print(f"Perguntas selecionadas: {len(questions)}")
    print(f"Modelo avaliador: {EVALUATOR_MODEL}")
    print(f"Embeddings: {EMBEDDING_MODEL}")
    print(f"Identificação: {label}")
    print(f"Arquivo de perguntas: {questions_path}")
    print(f"Coleção: {args.collection}")
    print(f"Árvore BM25: {legal_tree_path}")
    print(f"Prompt task: {args.prompt_task}")

    print("\nInicializando avaliador...")

    client, metrics = await build_evaluator()

    try:
        print("Inicializando agente do Politizese...")

        agent, selected_provider = build_react_agent(
            provider="local",
            collection_name=args.collection,
            legal_tree_path=legal_tree_path,
            prompt_task=args.prompt_task,
        )

        print(f"Provider: {selected_provider}")

        results = []

        for index, question in enumerate(
            questions,
            start=1,
        ):
            question_id = question["id"]

            print("\n" + "=" * 60)
            print(
                f"PERGUNTA {index}/{len(questions)} "
                f"| {question_id}"
            )
            print("=" * 60)

            print(f"Categoria: {question['category']}")
            print(f"Tipo: {question.get('trap_type')}")
            print(f"Pergunta: {question['user_input']}")

            record = {
                "id": question_id,
                "category": question["category"],
                "trap_type": question.get("trap_type"),
                "user_input": question["user_input"],
                "reference": question["reference"],
                "reference_source": question.get(
                    "reference_source"
                ),
                "response": "",
                "retrieved_documents": [],
                "retrieved_document_count": 0,
                "retrieved_contexts": [],
                "retrieved_context_count": 0,
                "tool_calls": [],
                "metrics": {
                    name: None
                    for name in METRIC_NAMES
                },
                "metric_errors": {},
                "agent_error": None,
                "agent_total_duration_seconds": None,
                "agent_tool_calls_count": None,
            }

            captured_observations = []

            try:
                # 1. Executa o agente real.
                agent_result, captured_observations = (
                    run_agent_with_capture(
                        agent,
                        question["user_input"],
                    )
                )

                record["response"] = agent_result.answer

                record["agent_total_duration_seconds"] = getattr(
                    agent_result,
                    "total_duration_seconds",
                    None,
                )

                record["agent_tool_calls_count"] = getattr(
                    agent_result,
                    "tool_calls_count",
                    None,
                )

                # 2. Extrai os documentos recuperados.
                retrieved_documents = (
                    extract_retrieved_documents(
                        captured_observations
                    )
                )

                record["retrieved_documents"] = retrieved_documents
                record["retrieved_document_count"] = sum(
                    document.get("source") == "retrieved_document"
                    for document in retrieved_documents
                )

                record["retrieved_contexts"] = [
                    document["content"]
                    for document in retrieved_documents
                ]
                record["retrieved_context_count"] = len(
                    record["retrieved_contexts"]
                )

                record["tool_calls"] = extract_tool_call_diagnostics(
                    captured_observations
                )
                print_tool_call_diagnostics(record["tool_calls"])

                print(
                    "\nDocumentos recuperados: "
                    f"{len(retrieved_documents)}"
                )

                print(
                    "Chamadas de ferramentas: "
                    f"{len(captured_observations)}"
                )

                # 3. Calcula as quatro métricas.
                scores, metric_errors = await evaluate_sample(
                    question=question,
                    response=record["response"],
                    contexts=record["retrieved_contexts"],
                    metrics=metrics,
                )

                record["metrics"] = scores
                record["metric_errors"] = metric_errors

            except Exception as error:
                record["agent_error"] = (
                    f"{type(error).__name__}: {error}"
                )

                # Preserva eventuais documentos coletados.
                retrieved_documents = (
                    extract_retrieved_documents(
                        captured_observations
                    )
                )

                record["retrieved_documents"] = retrieved_documents
                record["retrieved_document_count"] = sum(
                    document.get("source") == "retrieved_document"
                    for document in retrieved_documents
                )

                record["retrieved_contexts"] = [
                    document["content"]
                    for document in retrieved_documents
                ]
                record["retrieved_context_count"] = len(
                    record["retrieved_contexts"]
                )
                record["tool_calls"] = extract_tool_call_diagnostics(
                    captured_observations
                )

                print(
                    f"\nERRO na pergunta {question_id}: "
                    f"{record['agent_error']}"
                )

            results.append(record)

            # Checkpoint após cada pergunta.
            save_results(
                results=results,
                json_path=json_path,
                csv_path=csv_path,
                provider=selected_provider,
                label=label,
                total_questions=len(questions),
                questions_file=questions_path,
                collection_name=args.collection,
                legal_tree_path=legal_tree_path,
                prompt_task=args.prompt_task,
            )

            print(
                f"\nProgresso: {len(results)}/{len(questions)}"
            )

            print(
                f"Resultados salvos em: {json_path}"
            )

        # ----------------------------------------------------
        # RESUMO FINAL
        # ----------------------------------------------------

        print("\n" + "=" * 60)
        print("RESUMO DA AVALIAÇÃO")
        print("=" * 60)

        averages = calculate_averages(results)

        for metric, score in averages.items():
            formatted = (
                f"{score:.4f}"
                if score is not None
                else "N/A"
            )

            print(f"{metric:<22} {formatted}")

        print("\n" + "-" * 60)
        print("MÉDIAS POR CATEGORIA")
        print("-" * 60)

        category_averages = calculate_category_averages(
            results
        )

        for category, category_scores in category_averages.items():
            print(f"\n{category.upper()}")

            for metric, score in category_scores.items():
                formatted = (
                    f"{score:.4f}"
                    if score is not None
                    else "N/A"
                )

                print(f"  {metric:<20} {formatted}")

        print("\n" + "=" * 60)
        print("AVALIAÇÃO CONCLUÍDA")
        print("=" * 60)

        print(f"JSON: {json_path}")
        print(f"CSV:  {csv_path}")

    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
