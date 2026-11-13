
import argparse
import json

from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

from src.ai.llm_factory import create_semantic_index_model
from src.core.config import get_settings

from src.rag.semantic_index_generator import (
    DEFAULT_INPUT_PATH,
    DEFAULT_OUTPUT_PATH,
    PROMPT_VERSION,
    _build_section_hash,
    flatten_section_units,
    generate_section_overview,
    load_document,
)

from src.rag.semantic_index_metrics import (
    DEFAULT_METRICS_DIR,
    SemanticIndexMetrics,
)


# ============================================================
# CONFIGURAÇÕES
# ============================================================

def _resolve_path(path: Path | str) -> Path:
    """Resolve caminhos relativos a partir da raiz do projeto."""

    from src.core.config import PROJECT_ROOT

    path = Path(path)

    if not path.is_absolute():
        path = PROJECT_ROOT / path

    return path.resolve()


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


# ============================================================
# PERSISTÊNCIA
# ============================================================

def _save_index_atomically(
    payload: dict[str, Any],
    path: Path,
) -> None:
    """Salva o índice completo preservando os outros documentos."""

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_path = path.with_suffix(
        path.suffix + ".tmp"
    )

    temporary_path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    temporary_path.replace(path)


# ============================================================
# VALIDAÇÃO DOS DADOS EXISTENTES
# ============================================================

def _prepare_existing_unit_summaries(
    source_section: dict[str, Any],
    indexed_section: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Recupera os resumos individuais já existentes.

    Não realiza chamadas ao LLM nesta etapa.
    """

    source_units = flatten_section_units(
        source_section
    )

    expected_hash = _build_section_hash(
        source_section,
        source_units,
    )

    if indexed_section.get("content_hash") != expected_hash:
        raise ValueError(
            f"Hash divergente em {source_section['node_id']}. "
            "O resumo geral não será atualizado."
        )

    stored_units = indexed_section.get("units")

    if not isinstance(stored_units, list):
        raise ValueError(
            "Lista de unidades inválida no índice existente."
        )

    stored_map = {}

    for unit in stored_units:

        if not isinstance(unit, dict):
            raise ValueError(
                "Foi encontrado um registro de unidade inválido."
            )

        node_id = unit.get("node_id")

        if not isinstance(node_id, str) or not node_id.strip():
            raise ValueError(
                "Unidade sem identificador válido no índice."
            )

        if node_id in stored_map:
            raise ValueError(
                f"Unidade duplicada no índice: {node_id}"
            )

        if not isinstance(unit.get("summary"), str) or not unit["summary"].strip():
            raise ValueError(
                f"Resumo ausente para {node_id}."
            )

        keywords = unit.get("keywords")

        if (
            not isinstance(keywords, list)
            or not keywords
            or not all(
                isinstance(value, str) and value.strip()
                for value in keywords
            )
        ):
            raise ValueError(
                f"Palavras-chave inválidas para {node_id}."
            )

        stored_map[node_id] = unit

    expected_ids = {
        unit["node_id"]
        for unit in source_units
    }

    actual_ids = set(stored_map)

    missing_ids = expected_ids - actual_ids
    extra_ids = actual_ids - expected_ids

    if missing_ids or extra_ids:
        raise ValueError(
            "As unidades do índice não correspondem à fonte. "
            f"Ausentes: {sorted(missing_ids)}. "
            f"Extras: {sorted(extra_ids)}."
        )

    # Mantém a ordem original das unidades.
    return [
        {
            "node_id": source_unit["node_id"],
            "summary": stored_map[source_unit["node_id"]]["summary"],
            "keywords": stored_map[source_unit["node_id"]]["keywords"],
        }
        for source_unit in source_units
    ]


# ============================================================
# ATUALIZAÇÃO DOS RESUMOS GERAIS
# ============================================================

def refresh_section_overviews(
    *,
    input_path: Path = DEFAULT_INPUT_PATH,
    index_path: Path = DEFAULT_OUTPUT_PATH,
    document_id: str | None = None,
    section_ids: list[str],
    metrics_dir: Path = DEFAULT_METRICS_DIR,
) -> dict[str, int]:
    """
    Regenera somente os resumos gerais das seções selecionadas.

    Os resumos individuais não são processados novamente.

    A função preserva:
    - Identificadores originais.
    - Hashes de conteúdo.
    - Resumos individuais.
    - Palavras-chave das unidades.
    - Outros documentos presentes no índice.
    """

    input_path = _resolve_path(input_path)
    index_path = _resolve_path(index_path)
    metrics_dir = _resolve_path(metrics_dir)

    if not section_ids:
        raise ValueError(
            "Informe pelo menos um identificador de seção."
        )

    if len(section_ids) != len(set(section_ids)):
        raise ValueError(
            "A lista de seções contém identificadores duplicados."
        )

    settings = get_settings()

    metrics = SemanticIndexMetrics(
        metrics_dir=metrics_dir
    )

    document = load_document(input_path)

    current_document_id = (
        document_id or document["document_id"]
    )

    if current_document_id != document["document_id"]:
        raise ValueError(
            "O document_id informado não corresponde "
            "ao documento original."
        )

    if not index_path.is_file():
        raise FileNotFoundError(
            f"Índice semântico não encontrado: {index_path}"
        )

    payload = json.loads(
        index_path.read_text(encoding="utf-8")
    )

    documents = payload.get("documents")

    if not isinstance(documents, list):
        raise ValueError(
            "O índice semântico não possui uma lista documents válida."
        )

    matching_documents = [
        item for item in documents
        if isinstance(item, dict)
        and item.get("document_id") == current_document_id
    ]

    if len(matching_documents) != 1:
        raise ValueError(
            "O documento precisa aparecer exatamente uma vez no índice."
        )

    indexed_document = matching_documents[0]

    source_sections = {
        section["node_id"]: section
        for section in document["sections"]
    }

    indexed_sections = {
        section["section_id"]: section
        for section in indexed_document.get("sections", [])
        if isinstance(section, dict)
        and isinstance(section.get("section_id"), str)
    }

    for section_id in section_ids:

        if section_id not in source_sections:
            raise ValueError(
                f"Seção não encontrada na fonte: {section_id}"
            )

        if section_id not in indexed_sections:
            raise ValueError(
                f"Seção não encontrada no índice: {section_id}"
            )

    provider = settings.semantic_index_provider
    model_name = settings.semantic_index_model

    generation_config = {
        "temperature": settings.semantic_index_temperature,
        "top_p": settings.semantic_index_top_p,
        "num_predict": settings.semantic_index_num_predict,
    }

    print("=" * 70)
    print("ATUALIZAÇÃO DE RESUMOS GERAIS — POLITIZE-SE")
    print("=" * 70)

    print(f"Documento: {current_document_id}")
    print(f"Provider: {provider}")
    print(f"Modelo: {model_name}")
    print(f"Seções selecionadas: {len(section_ids)}")
    print(f"Run ID: {metrics.run_id}")

    print("\nMétricas:", metrics.metrics_dir)

    # Uma única instância do modelo para todas as seções.
    llm = create_semantic_index_model(
        settings=settings
    )

    processed_count = 0
    failed_count = 0

    for index, section_id in enumerate(
        section_ids,
        start=1,
    ):

        source_section = source_sections[section_id]
        indexed_section = indexed_sections[section_id]

        started = perf_counter()
        error = None
        unit_count = 0

        print(
            f"\n[{index}/{len(section_ids)}] "
            f"Atualizando {section_id}"
        )

        try:
            # Recupera somente os resumos existentes.
            unit_summaries = _prepare_existing_unit_summaries(
                source_section,
                indexed_section,
            )

            unit_count = len(unit_summaries)

            print(
                f"  Resumos individuais preservados: {unit_count}"
            )

            # Gera somente o resumo geral.
            overview = generate_section_overview(
                section=source_section,
                unit_summaries=unit_summaries,
                llm=llm,
                metrics=metrics,
            )

            generated_at = _timestamp()

            # Atualiza somente os campos gerais da seção.
            indexed_section.update({
                "summary": overview.summary,
                "subjects": overview.subjects,
                "keywords": overview.keywords,
                "generated_at": generated_at,
                "overview_generation": {
                    "model_provider": provider,
                    "model_name": model_name,
                    "prompt_version": PROMPT_VERSION,
                    "generation_config": generation_config,
                    "generated_at": generated_at,
                },
            })

            # Registra também os metadados do documento.
            indexed_document["generated_at"] = generated_at
            indexed_document["model_provider"] = provider
            indexed_document["model_name"] = model_name
            indexed_document["prompt_version"] = PROMPT_VERSION

            payload["generated_at"] = generated_at

            # Persiste cada seção concluída imediatamente.
            _save_index_atomically(
                payload=payload,
                path=index_path,
            )

            processed_count += 1

            print(
                f"[OK] {section_id} — "
                f"resumo geral atualizado."
            )

        except Exception as exception:

            error = exception
            failed_count += 1

            print(
                f"[ERRO] {section_id}: "
                f"{type(exception).__name__}: {exception}"
            )

        finally:

            metrics.record_section(
                section_id=section_id,
                status="error" if error else "success",
                elapsed_seconds=perf_counter() - started,
                unit_count=unit_count,
                error=error,
            )

    # Resume a execução.
    summary = metrics.finish(
        status="partial" if failed_count else "completed",
        document_id=current_document_id,
        sections_total=len(section_ids),
        sections_processed=processed_count,
        sections_reused=0,
        failures=failed_count,
        model_provider=provider,
        model_name=model_name,
    )

    print("\n" + "=" * 70)
    print("MÉTRICAS DA ATUALIZAÇÃO")
    print("=" * 70)

    print(f"Chamadas ao LLM: {summary['llm_calls_total']}")
    print(f"Chamadas bem-sucedidas: {summary['llm_calls_successful']}")
    print(f"Chamadas com falha: {summary['llm_calls_failed']}")
    print(f"Tokens de entrada: {summary['total_prompt_tokens']}")
    print(f"Tokens de saída: {summary['total_output_tokens']}")
    print(f"Total de tokens: {summary['total_tokens']}")
    print(f"Tempo total: {summary['total_elapsed_seconds']} s")

    print(f"\nSeções atualizadas: {processed_count}")
    print(f"Falhas: {failed_count}")
    print(f"Índice: {index_path}")

    return {
        "processados": processed_count,
        "falhas": failed_count,
    }


# ============================================================
# INTERFACE CLI
# ============================================================

def main() -> None:

    parser = argparse.ArgumentParser(
        description=(
            "Regenera exclusivamente os resumos gerais "
            "de seções já indexadas."
        )
    )

    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT_PATH,
        help="Documento original estruturado.",
    )

    parser.add_argument(
        "--index",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="Índice semântico consolidado.",
    )

    parser.add_argument(
        "--document-id",
        type=str,
        default=None,
        help="Identificador do documento.",
    )

    parser.add_argument(
        "--section-ids",
        nargs="+",
        required=True,
        help="Identificadores das seções que terão o resumo geral atualizado.",
    )

    parser.add_argument(
        "--metrics-dir",
        type=Path,
        default=DEFAULT_METRICS_DIR,
        help="Diretório para salvar as métricas.",
    )

    args = parser.parse_args()

    try:
        result = refresh_section_overviews(
            input_path=args.input,
            index_path=args.index,
            document_id=args.document_id,
            section_ids=args.section_ids,
            metrics_dir=args.metrics_dir,
        )

    except Exception as error:

        print(
            f"\nFalha na atualização: "
            f"{type(error).__name__}: {error}"
        )

        raise SystemExit(1) from error

    if result["falhas"] > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
