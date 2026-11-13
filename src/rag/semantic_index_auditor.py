
import argparse
import json
import re
import uuid

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


from src.core.config import PROJECT_ROOT

from src.rag.semantic_index_generator import (
    DEFAULT_INPUT_PATH,
    DEFAULT_OUTPUT_PATH,
    _build_section_hash,
    flatten_section_units,
    load_document,
)


# ============================================================
# CONFIGURAÇÕES
# ============================================================

DEFAULT_AUDIT_DIR = (
    PROJECT_ROOT
    / "data"
    / "metrics"
    / "semantic_index"
    / "audits"
)

DEFAULT_CALLS_METRICS_PATH = (
    PROJECT_ROOT
    / "data"
    / "metrics"
    / "semantic_index"
    / "llm_calls.jsonl"
)

SUPPORTED_INDEX_FORMAT_VERSION = 2

AUDITOR_VERSION = "1.0"


# ============================================================
# UTILITÁRIOS
# ============================================================

def _resolve_path(path: Path | str) -> Path:
    """Resolve caminhos relativos a partir da raiz do projeto."""

    path = Path(path)

    if not path.is_absolute():
        path = PROJECT_ROOT / path

    return path.resolve()


def _timestamp() -> str:
    """Retorna a data e hora atual em UTC."""

    return datetime.now(timezone.utc).isoformat()


def _parse_datetime(value: Any) -> datetime | None:
    """Converte uma data ISO 8601 em datetime."""

    if not isinstance(value, str) or not value.strip():
        return None

    try:
        return datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )

    except ValueError:
        return None


def _normalize_path(value: Any) -> str | None:
    """Normaliza caminhos para comparação."""

    if not isinstance(value, str) or not value.strip():
        return None

    return (
        value.strip()
        .replace("\\", "/")
        .casefold()
    )


def _safe_filename(value: str) -> str:
    """Remove caracteres inadequados para nomes de arquivos."""

    return re.sub(
        r"[^a-zA-Z0-9_.-]",
        "_",
        value,
    )


def _is_nonempty_string(value: Any) -> bool:
    return (
        isinstance(value, str)
        and bool(value.strip())
    )


def _validate_string_list(
    value: Any,
) -> tuple[bool, bool]:
    """
    Valida uma lista de strings.

    Returns:
        (valid, nonempty)
    """

    if not isinstance(value, list):
        return False, False

    if not all(_is_nonempty_string(item) for item in value):
        return False, bool(value)

    return True, bool(value)


def _read_json(path: Path) -> dict[str, Any]:
    """Carrega um arquivo JSON e valida sua estrutura principal."""

    if not path.is_file():
        raise FileNotFoundError(
            f"Arquivo não encontrado: {path}"
        )

    try:
        payload = json.loads(
            path.read_text(encoding="utf-8")
        )

    except json.JSONDecodeError as error:
        raise ValueError(
            f"JSON inválido em {path}: {error}"
        ) from error

    if not isinstance(payload, dict):
        raise ValueError(
            f"O arquivo {path} precisa conter um objeto JSON."
        )

    return payload


def _save_report(
    report: dict[str, Any],
    path: Path,
) -> None:
    """Salva o relatório de auditoria atomicamente."""

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_path = path.with_suffix(
        path.suffix + ".tmp"
    )

    temporary_path.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    temporary_path.replace(path)


# ============================================================
# AUDITOR
# ============================================================

class SemanticIndexAuditor:
    """
    Audita índices semânticos de documentos estruturados.

    Não possui regras específicas de Constituição, leis
    ou decretos.

    Utiliza o mesmo contrato documental do gerador:
    - articles
    - sections
    - nodes

    O documento original é normalizado através de load_document().
    """

    def __init__(
        self,
        input_path: Path,
        index_path: Path,
        document_id: str | None = None,
        calls_metrics_path: Path | None = None,
        strict_keywords: bool = False,
    ) -> None:

        self.input_path = _resolve_path(input_path)
        self.index_path = _resolve_path(index_path)

        self.document_id = document_id

        self.calls_metrics_path = (
            _resolve_path(calls_metrics_path)
            if calls_metrics_path is not None
            else DEFAULT_CALLS_METRICS_PATH
        )

        self.strict_keywords = strict_keywords

        self.errors: list[str] = []
        self.warnings: list[str] = []

        self.sections_valid = 0
        self.sections_with_issues = 0

        self.total_source_units = 0
        self.total_indexed_units = 0

        self.missing_units = 0
        self.extra_units = 0
        self.duplicate_units = 0

        self.empty_keywords = 0

        self.truncated_calls = 0
        self.metrics_lines_invalid = 0

    # ========================================================
    # REGISTRO DE PROBLEMAS
    # ========================================================

    def _error(self, message: str) -> None:
        self.errors.append(message)

    def _warning(self, message: str) -> None:
        self.warnings.append(message)

    def _keyword_issue(self, message: str) -> None:
        self.empty_keywords += 1

        if self.strict_keywords:
            self._error(message)

        else:
            self._warning(message)

    # ========================================================
    # LOCALIZAÇÃO DO DOCUMENTO
    # ========================================================

    def _select_index_document(
        self,
        documents: list[Any],
        expected_document_id: str,
    ) -> dict[str, Any]:

        if not isinstance(documents, list):
            raise ValueError(
                "O campo documents do índice precisa ser uma lista."
            )

        document_ids = [
            item.get("document_id")
            for item in documents
            if isinstance(item, dict)
        ]

        duplicates = [
            document_id
            for document_id, count in Counter(document_ids).items()
            if count > 1
        ]

        for duplicate in duplicates:
            self._error(
                f"Documento duplicado no índice: {duplicate}"
            )

        matching = [
            item
            for item in documents
            if isinstance(item, dict)
            and item.get("document_id") == expected_document_id
        ]

        if not matching:
            raise ValueError(
                "Documento não encontrado no índice semântico: "
                f"{expected_document_id}"
            )

        if len(matching) > 1:
            raise ValueError(
                "Existem múltiplos registros para o documento: "
                f"{expected_document_id}"
            )

        return matching[0]

    # ========================================================
    # AUDITORIA DE METADADOS
    # ========================================================

    def _audit_document_metadata(
        self,
        index_payload: dict[str, Any],
        indexed_document: dict[str, Any],
        source_document: dict[str, Any],
        indexed_documents: list[Any],
    ) -> None:

        # Versão do formato.
        if (
            index_payload.get("format_version")
            != SUPPORTED_INDEX_FORMAT_VERSION
        ):
            self._error(
                "Versão incompatível do índice: "
                f"{index_payload.get('format_version')}. "
                f"Esperada: {SUPPORTED_INDEX_FORMAT_VERSION}."
            )

        # Quantidade de documentos.
        declared_count = index_payload.get("document_count")

        if declared_count != len(indexed_documents):
            self._error(
                "document_count não corresponde à quantidade "
                "real de documentos no índice."
            )

        # Identificação.
        if (
            indexed_document.get("document_id")
            != source_document["document_id"]
        ):
            self._error(
                "O document_id do índice diverge do documento original."
            )

        # Título.
        if (
            indexed_document.get("document_title")
            != source_document["document_title"]
        ):
            self._warning(
                "O título do documento original diverge "
                "do título registrado no índice."
            )

        # Origem.
        indexed_source = _normalize_path(
            indexed_document.get("source_file")
        )

        expected_source = _normalize_path(
            str(self.input_path.relative_to(PROJECT_ROOT))
            if self.input_path.is_relative_to(PROJECT_ROOT)
            else str(self.input_path)
        )

        if (
            indexed_source is not None
            and indexed_source != expected_source
        ):
            self._warning(
                "O caminho da fonte registrado no índice "
                "é diferente do caminho utilizado na auditoria."
            )

        # Modelo.
        if not _is_nonempty_string(
            indexed_document.get("model_name")
        ):
            self._error(
                "O modelo utilizado não está registrado no documento."
            )

        if indexed_document.get("model_provider") not in {
            "local",
            "cloud",
        }:
            self._error(
                "Provider ausente ou inválido no documento."
            )

        if not _is_nonempty_string(
            indexed_document.get("prompt_version")
        ):
            self._error(
                "Versão do prompt não registrada no documento."
            )

        if _parse_datetime(
            indexed_document.get("generated_at")
        ) is None:
            self._error(
                "Data de geração ausente ou inválida no documento."
            )

        declared_section_count = indexed_document.get(
            "section_count"
        )

        actual_section_count = len(
            indexed_document.get("sections", [])
        )

        if declared_section_count != actual_section_count:
            self._error(
                "section_count não corresponde à quantidade "
                "de seções armazenadas no documento."
            )

    # ========================================================
    # AUDITORIA DE UMA SEÇÃO
    # ========================================================

    def _audit_section(
        self,
        source_section: dict[str, Any],
        indexed_section: dict[str, Any],
        global_indexed_unit_ids: set[str],
    ) -> None:

        errors_before = len(self.errors)

        section_id = source_section["node_id"]

        # Identificação.
        if indexed_section.get("section_id") != section_id:
            self._error(
                f"section_id divergente: {section_id}"
            )

        if indexed_section.get("node_id") != section_id:
            self._error(
                f"node_id da seção divergente: {section_id}"
            )

        # Integridade do hash.
        source_units = flatten_section_units(
            source_section
        )

        expected_hash = _build_section_hash(
            source_section,
            source_units,
        )

        if indexed_section.get("content_hash") != expected_hash:
            self._error(
                f"Hash de conteúdo divergente: {section_id}"
            )

        # Metadados estruturais.
        structural_fields = (
            "parent_id",
            "node_type",
            "label",
            "number",
        )

        for field in structural_fields:

            if indexed_section.get(field) != source_section.get(field):
                self._error(
                    f"{field} divergente na seção {section_id}."
                )

        # Resumo.
        if not _is_nonempty_string(
            indexed_section.get("summary")
        ):
            self._error(
                f"Resumo geral ausente ou vazio: {section_id}"
            )

        # Assuntos.
        subjects_valid, subjects_nonempty = _validate_string_list(
            indexed_section.get("subjects")
        )

        if not subjects_valid:
            self._error(
                f"Lista de assuntos inválida: {section_id}"
            )

        elif not subjects_nonempty:
            self._error(
                f"Seção sem assuntos: {section_id}"
            )

        # Palavras-chave da seção.
        keywords_valid, keywords_nonempty = _validate_string_list(
            indexed_section.get("keywords")
        )

        if not keywords_valid:
            self._error(
                f"Lista de palavras-chave inválida: {section_id}"
            )

        elif not keywords_nonempty:
            self._keyword_issue(
                f"Seção sem palavras-chave: {section_id}"
            )

        # Rastreabilidade da seção.
        self._audit_record_metadata(
            record=indexed_section,
            record_id=section_id,
        )

        # Unidades.
        generated_units = indexed_section.get("units")

        if not isinstance(generated_units, list):
            self._error(
                f"Lista de unidades inválida: {section_id}"
            )

            generated_units = []

        self.total_source_units += len(source_units)
        self.total_indexed_units += len(generated_units)

        expected_map = {
            unit["node_id"]: unit
            for unit in source_units
        }

        generated_ids = [
            unit.get("node_id")
            for unit in generated_units
            if isinstance(unit, dict)
        ]

        duplicate_ids = [
            node_id
            for node_id, count in Counter(generated_ids).items()
            if count > 1
        ]

        for node_id in duplicate_ids:
            self.duplicate_units += 1

            self._error(
                f"Unidade duplicada em {section_id}: {node_id}"
            )

        actual_map = {
            unit["node_id"]: unit
            for unit in generated_units
            if isinstance(unit, dict)
            and isinstance(unit.get("node_id"), str)
        }

        expected_ids = set(expected_map)
        actual_ids = set(actual_map)

        missing_ids = expected_ids - actual_ids
        extra_ids = actual_ids - expected_ids

        self.missing_units += len(missing_ids)
        self.extra_units += len(extra_ids)

        for node_id in sorted(missing_ids):
            self._error(
                f"Unidade ausente: {section_id} -> {node_id}"
            )

        for node_id in sorted(extra_ids):
            self._error(
                f"Unidade desconhecida: {section_id} -> {node_id}"
            )

        # Verifica cada unidade conhecida.
        for node_id, generated_unit in actual_map.items():

            if node_id in global_indexed_unit_ids:
                self._error(
                    f"ID de unidade repetido em diferentes seções: {node_id}"
                )

            global_indexed_unit_ids.add(node_id)

            original = expected_map.get(node_id)

            if original is None:
                continue

            for field in (
                "parent_id",
                "node_type",
                "label",
                "number",
                "path",
            ):
                if generated_unit.get(field) != original.get(field):
                    self._error(
                        f"{field} divergente em {node_id}."
                    )

            if not _is_nonempty_string(
                generated_unit.get("summary")
            ):
                self._error(
                    f"Resumo ausente ou vazio: {node_id}"
                )

            unit_keywords_valid, unit_keywords_nonempty = (
                _validate_string_list(
                    generated_unit.get("keywords")
                )
            )

            if not unit_keywords_valid:
                self._error(
                    f"Palavras-chave inválidas: {node_id}"
                )

            elif not unit_keywords_nonempty:
                self._keyword_issue(
                    f"Unidade sem palavras-chave: {node_id}"
                )

        # Metadados gerais.
        if len(self.errors) == errors_before:
            self.sections_valid += 1

        else:
            self.sections_with_issues += 1

    # ========================================================
    # AUDITORIA DE METADADOS DOS REGISTROS
    # ========================================================

    def _audit_record_metadata(
        self,
        record: dict[str, Any],
        record_id: str,
    ) -> None:

        if record.get("format_version") != SUPPORTED_INDEX_FORMAT_VERSION:
            self._error(
                f"Versão de formato inválida em {record_id}."
            )

        if record.get("model_provider") not in {
            "local",
            "cloud",
        }:
            self._error(
                f"Provider ausente ou inválido em {record_id}."
            )

        if not _is_nonempty_string(
            record.get("model_name")
        ):
            self._error(
                f"Modelo não identificado em {record_id}."
            )

        if not _is_nonempty_string(
            record.get("prompt_version")
        ):
            self._error(
                f"Versão do prompt ausente em {record_id}."
            )

        if _parse_datetime(
            record.get("generated_at")
        ) is None:
            self._error(
                f"Data de geração inválida em {record_id}."
            )

    # ========================================================
    # AUDITORIA DAS MÉTRICAS DO OLLAMA
    # ========================================================

    
    def _audit_call_metrics(
        self,
        indexed_sections: dict[str, dict[str, Any]],
    ) -> None:
        """
        Identifica chamadas concluídas por limite de geração.

        Para resumos gerais, considera a última chamada bem-sucedida
        anterior à geração do registro atualmente armazenado.

        Para lotes, sinaliza chamadas truncadas que participaram
        da geração do registro atual.
        """

        if not self.calls_metrics_path.is_file():
            self._warning(
                "Arquivo de métricas das chamadas ao LLM "
                "não encontrado. Auditoria histórica não realizada."
            )
            return

        latest_overview_calls = {}

        with self.calls_metrics_path.open(
            "r",
            encoding="utf-8",
        ) as file:

            for line_number, line in enumerate(file, start=1):

                if not line.strip():
                    continue

                try:
                    record = json.loads(line)

                except json.JSONDecodeError:
                    self.metrics_lines_invalid += 1
                    self._warning(
                        f"Linha JSON inválida nas métricas: {line_number}."
                    )
                    continue

                if not isinstance(record, dict):
                    continue

                context = record.get("context") or {}

                if not isinstance(context, dict):
                    continue

                section_id = context.get("section_id")

                if section_id not in indexed_sections:
                    continue

                if record.get("status") != "success":
                    continue

                operation = record.get("operation")

                call_timestamp = _parse_datetime(
                    record.get("timestamp")
                )

                generated_at = _parse_datetime(
                    indexed_sections[section_id].get("generated_at")
                )

                if (
                    call_timestamp is None
                    or generated_at is None
                    or call_timestamp > generated_at
                ):
                    continue

                if operation == "unit_batch":

                    if record.get("done_reason") == "length":
                        self.truncated_calls += 1

                        self._warning(
                            f"Chamada de lote encerrada por limite "
                            f"de geração em {section_id}. "
                            "Revisar a completude da saída."
                        )

                elif operation == "section_overview":

                    previous = latest_overview_calls.get(section_id)

                    if (
                        previous is None
                        or call_timestamp > previous[0]
                    ):
                        latest_overview_calls[section_id] = (
                            call_timestamp,
                            record,
                        )

        for section_id, (_, record) in latest_overview_calls.items():

            if record.get("done_reason") == "length":
                self.truncated_calls += 1

                self._warning(
                    f"Último resumo geral de {section_id} terminou "
                    "por limite de geração. Revisar a completude."
                )


    # ========================================================
    # EXECUÇÃO COMPLETA
    # ========================================================

    def audit(
        self,
        report_path: Path | None = None,
    ) -> dict[str, Any]:

        print("=" * 70)
        print("AUDITORIA DO ÍNDICE SEMÂNTICO — POLITIZE-SE")
        print("=" * 70)

        source_document = load_document(
            self.input_path
        )

        expected_document_id = (
            self.document_id
            or source_document["document_id"]
        )

        if expected_document_id != source_document["document_id"]:
            raise ValueError(
                "O document_id informado não corresponde "
                "ao documento original."
            )

        index_payload = _read_json(
            self.index_path
        )

        indexed_documents = index_payload.get("documents")

        if not isinstance(indexed_documents, list):
            raise ValueError(
                "O índice semântico não contém uma lista documents válida."
            )

        indexed_document = self._select_index_document(
            indexed_documents,
            expected_document_id,
        )

        source_sections = source_document["sections"]

        indexed_sections_list = indexed_document.get("sections")

        if not isinstance(indexed_sections_list, list):
            raise ValueError(
                "O documento no índice não possui uma lista sections válida."
            )

        self._audit_document_metadata(
            index_payload=index_payload,
            indexed_document=indexed_document,
            source_document=source_document,
            indexed_documents=indexed_documents,
        )

        source_map = {
            section["node_id"]: section
            for section in source_sections
        }

        indexed_ids = [
            section.get("section_id")
            for section in indexed_sections_list
            if isinstance(section, dict)
        ]

        duplicate_sections = [
            section_id
            for section_id, count in Counter(indexed_ids).items()
            if count > 1
        ]

        for section_id in duplicate_sections:
            self._error(
                f"Seção duplicada no índice: {section_id}"
            )

        indexed_map = {
            section["section_id"]: section
            for section in indexed_sections_list
            if isinstance(section, dict)
            and isinstance(section.get("section_id"), str)
        }

        expected_section_ids = set(source_map)
        actual_section_ids = set(indexed_map)

        missing_sections = expected_section_ids - actual_section_ids
        extra_sections = actual_section_ids - expected_section_ids

        for section_id in sorted(missing_sections):
            self._error(
                f"Seção ausente no índice: {section_id}"
            )

        for section_id in sorted(extra_sections):
            self._error(
                f"Seção inexistente na fonte: {section_id}"
            )

        global_indexed_unit_ids = set()

        for section_id, source_section in source_map.items():

            indexed_section = indexed_map.get(section_id)

            if indexed_section is None:
                self.sections_with_issues += 1
                continue

            self._audit_section(
                source_section=source_section,
                indexed_section=indexed_section,
                global_indexed_unit_ids=global_indexed_unit_ids,
            )

        self._audit_call_metrics(
            indexed_sections=indexed_map
        )

        source_unit_count = sum(
            len(flatten_section_units(section))
            for section in source_sections
        )

        total_source_sections = len(source_sections)

        indexed_unit_count = sum(
            len(section.get("units", []))
            for section in indexed_sections_list
            if isinstance(section, dict)
            and isinstance(section.get("units"), list)
        )

        section_coverage = (
            len(actual_section_ids & expected_section_ids)
            / total_source_sections
            if total_source_sections
            else 0
        )

        unit_coverage = (
            1 - (self.missing_units / source_unit_count)
            if source_unit_count
            else 1
        )

        if self.errors:
            status = "failed"

        elif self.warnings:
            status = "passed_with_warnings"

        else:
            status = "passed"

        report = {
            "audit_id": uuid.uuid4().hex,
            "auditor_version": AUDITOR_VERSION,
            "generated_at": _timestamp(),
            "status": status,

            "document": {
                "document_id": expected_document_id,
                "document_title": source_document["document_title"],
                "source_path": str(self.input_path),
            },

            "index": {
                "path": str(self.index_path),
                "format_version": index_payload.get("format_version"),
                "section_count": len(indexed_sections_list),
                "unit_count": indexed_unit_count,
            },

            "source": {
                "section_count": total_source_sections,
                "unit_count": source_unit_count,
            },

            "coverage": {
                "section_coverage": round(
                    section_coverage * 100,
                    2,
                ),
                "unit_coverage": round(
                    max(0, unit_coverage) * 100,
                    2,
                ),
            },

            "statistics": {
                "sections_valid": self.sections_valid,
                "sections_with_issues": self.sections_with_issues,
                "missing_units": self.missing_units,
                "extra_units": self.extra_units,
                "duplicate_units": self.duplicate_units,
                "records_without_keywords": self.empty_keywords,
                "historical_truncated_calls": self.truncated_calls,
                "invalid_metrics_lines": self.metrics_lines_invalid,
            },

            "checks": {
                "structure": "failed" if self.errors else "passed",
                "keywords": (
                    "warning"
                    if self.empty_keywords
                    else "passed"
                ),
                "truncation_history": (
                    "warning"
                    if self.truncated_calls
                    else "passed"
                ),
            },

            "errors": self.errors,
            "warnings": self.warnings,
        }

        if report_path is None:

            timestamp = datetime.now(
                timezone.utc
            ).strftime("%Y%m%dT%H%M%SZ")

            report_path = (
                DEFAULT_AUDIT_DIR
                / (
                    f"{_safe_filename(expected_document_id)}_"
                    f"{timestamp}.json"
                )
            )

        report_path = _resolve_path(report_path)

        _save_report(
            report=report,
            path=report_path,
        )

        self._print_summary(report, report_path)

        return report

    # ========================================================
    # RELATÓRIO NO TERMINAL
    # ========================================================

    @staticmethod
    def _print_summary(
        report: dict[str, Any],
        report_path: Path,
    ) -> None:

        print("\n" + "=" * 70)
        print("RESULTADO DA AUDITORIA")
        print("=" * 70)

        print(
            f"Documento: "
            f"{report['document']['document_title']}"
        )

        print(
            f"Identificador: "
            f"{report['document']['document_id']}"
        )

        print(
            f"Seções na fonte: "
            f"{report['source']['section_count']}"
        )

        print(
            f"Seções no índice: "
            f"{report['index']['section_count']}"
        )

        print(
            f"Unidades na fonte: "
            f"{report['source']['unit_count']}"
        )

        print(
            f"Unidades no índice: "
            f"{report['index']['unit_count']}"
        )

        print("\nCOBERTURA")

        print(
            f"Seções: "
            f"{report['coverage']['section_coverage']}%"
        )

        print(
            f"Unidades: "
            f"{report['coverage']['unit_coverage']}%"
        )

        print("\nINTEGRIDADE")

        for key, value in report["statistics"].items():
            print(f"{key}: {value}")

        print(f"\nErros: {len(report['errors'])}")
        print(f"Avisos: {len(report['warnings'])}")

        if report["errors"]:
            print("\nERROS ENCONTRADOS")

            for error in report["errors"][:100]:
                print(f"[ERRO] {error}")

        if report["warnings"]:
            print("\nAVISOS")

            for warning in report["warnings"][:100]:
                print(f"[AVISO] {warning}")

        print("\nSTATUS:", report["status"])

        print(f"\nRelatório: {report_path}")


# ============================================================
# FUNÇÃO PÚBLICA
# ============================================================

def audit_semantic_index(
    *,
    input_path: Path,
    index_path: Path,
    document_id: str | None = None,
    report_path: Path | None = None,
    calls_metrics_path: Path | None = None,
    strict_keywords: bool = False,
) -> dict[str, Any]:
    """
    Interface pública para auditoria programática.

    Pode ser importada por scripts, pipelines e futuras ferramentas.
    """

    auditor = SemanticIndexAuditor(
        input_path=input_path,
        index_path=index_path,
        document_id=document_id,
        calls_metrics_path=calls_metrics_path,
        strict_keywords=strict_keywords,
    )

    return auditor.audit(
        report_path=report_path
    )


# ============================================================
# INTERFACE CLI
# ============================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Audita a integridade de índices semânticos "
            "de documentos estruturados."
        )
    )

    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT_PATH,
        help="Documento original estruturado em JSON.",
    )

    parser.add_argument(
        "--index",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="Índice semântico consolidado em JSON.",
    )

    parser.add_argument(
        "--document-id",
        type=str,
        default=None,
        help="Identificador do documento que será auditado.",
    )

    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Caminho do relatório de auditoria.",
    )

    parser.add_argument(
        "--calls-metrics",
        type=Path,
        default=DEFAULT_CALLS_METRICS_PATH,
        help="Arquivo JSONL das chamadas ao LLM.",
    )

    parser.add_argument(
        "--strict-keywords",
        action="store_true",
        help="Trata ausência de palavras-chave como erro.",
    )

    args = parser.parse_args()

    try:
        report = audit_semantic_index(
            input_path=args.input,
            index_path=args.index,
            document_id=args.document_id,
            report_path=args.report,
            calls_metrics_path=args.calls_metrics,
            strict_keywords=args.strict_keywords,
        )

    except Exception as error:

        print(
            f"\nFalha na auditoria: "
            f"{type(error).__name__}: {error}"
        )

        raise SystemExit(2) from error

    if report["status"] == "failed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
