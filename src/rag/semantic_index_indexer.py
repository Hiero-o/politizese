
import argparse
import json

from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from langchain_core.documents import Document

from src.core.config import PROJECT_ROOT, get_settings
from src.rag.vector_store import create_vector_store, index_chunks


# ============================================================
# CONFIGURAÇÕES
# ============================================================

DEFAULT_INPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "indice_semantico.json"
)

# Nome-base exclusivo. create_vector_store acrescentará
# o perfil, o provedor e o modelo de embeddings ao nome final.
SEMANTIC_COLLECTION_NAME = "politizese_semantic_aux_v1"

DEFAULT_BATCH_SIZE = 64

# Metadados de execução que não devem provocar reindexação
# desnecessária em toda execução do indexador.
VOLATILE_METADATA_KEYS = {
    "generated_at",
    "updated_at",
    "indexed_at",
}


# ============================================================
# VALIDAÇÃO E NORMALIZAÇÃO
# ============================================================

def _require_mapping(
    value: Any,
    description: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(
            f"{description} precisa ser um objeto JSON."
        )

    return value


def _require_string(
    value: Any,
    field_name: str,
    owner: str,
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"Campo obrigatório '{field_name}' ausente ou inválido "
            f"em {owner}."
        )

    return value.strip()


def _string_list(
    value: Any,
    field_name: str,
    owner: str,
) -> list[str]:
    """
    Valida listas de assuntos e palavras-chave.

    Não converte objetos ou números silenciosamente em texto.
    """

    if value is None:
        return []

    if not isinstance(value, list):
        raise TypeError(
            f"'{field_name}' precisa ser uma lista em {owner}."
        )

    result = []

    for item in value:
        if not isinstance(item, str):
            raise TypeError(
                f"Elemento inválido em '{field_name}' de {owner}."
            )

        item = item.strip()

        if item and item not in result:
            result.append(item)

    return result


def _normalize_path(value: Any) -> str:
    """
    Converte o caminho hierárquico para texto.

    Aceita tanto uma string quanto uma lista de elementos.
    """

    if value is None:
        return ""

    if isinstance(value, str):
        return value.strip()

    if isinstance(value, list):
        parts = []

        for item in value:
            if isinstance(item, str):
                part = item.strip()

            elif isinstance(item, Mapping):
                part = str(
                    item.get("label")
                    or item.get("name")
                    or item.get("node_id")
                    or ""
                ).strip()

            else:
                part = str(item).strip()

            if part:
                parts.append(part)

        return " > ".join(parts)

    return str(value).strip()


def _add_scalar_metadata(
    target: dict[str, Any],
    source: Any,
) -> None:
    """
    Copia apenas metadados escalares compatíveis com o Chroma.

    Valores nulos, listas, objetos e campos temporais são ignorados.
    """

    if not isinstance(source, Mapping):
        return

    for key, value in source.items():
        normalized_key = str(key).strip()

        if not normalized_key:
            continue

        if normalized_key.lower() in VOLATILE_METADATA_KEYS:
            continue

        if value is None:
            continue

        if isinstance(value, (str, int, float, bool)):
            target[normalized_key] = value


# ============================================================
# CONTEÚDO DOS DOCUMENTOS
# ============================================================

def _format_section_content(
    *,
    document_title: str,
    document_id: str,
    section_id: str,
    section_label: str,
    summary: str,
    subjects: list[str],
    keywords: list[str],
) -> str:
    """
    Monta o texto utilizado para gerar o embedding da seção.

    Este conteúdo é exclusivamente auxiliar.
    """

    lines = [
        "TIPO: resumo semântico geral de seção.",
        "FINALIDADE: localização auxiliar de conteúdo documental.",
        f"DOCUMENTO: {document_title}",
        f"IDENTIFICADOR DO DOCUMENTO: {document_id}",
        f"SEÇÃO: {section_label}",
        f"IDENTIFICADOR DA SEÇÃO: {section_id}",
        "",
        "RESUMO:",
        summary,
    ]

    if subjects:
        lines.extend([
            "",
            "ASSUNTOS:",
            "; ".join(subjects),
        ])

    if keywords:
        lines.extend([
            "",
            "PALAVRAS-CHAVE:",
            "; ".join(keywords),
        ])

    return "\n".join(lines)


def _format_unit_content(
    *,
    document_title: str,
    document_id: str,
    section_label: str,
    section_id: str,
    node_id: str,
    node_type: str,
    label: str,
    number: str,
    path: str,
    summary: str,
    keywords: list[str],
) -> str:
    """
    Monta o texto utilizado para gerar o embedding da unidade.

    O texto constitucional original não é incluído.
    """

    lines = [
        "TIPO: resumo semântico de unidade documental.",
        "FINALIDADE: localização auxiliar de conteúdo documental.",
        f"DOCUMENTO: {document_title}",
        f"IDENTIFICADOR DO DOCUMENTO: {document_id}",
        f"SEÇÃO: {section_label}",
        f"IDENTIFICADOR DA SEÇÃO: {section_id}",
        f"IDENTIFICADOR DA UNIDADE: {node_id}",
        f"TIPO DA UNIDADE: {node_type or 'não informado'}",
    ]

    if label:
        lines.append(f"RÓTULO: {label}")

    if number:
        lines.append(f"NUMERAÇÃO: {number}")

    if path:
        lines.extend([
            "",
            f"HIERARQUIA: {path}",
        ])

    lines.extend([
        "",
        "RESUMO:",
        summary,
    ])

    if keywords:
        lines.extend([
            "",
            "PALAVRAS-CHAVE:",
            "; ".join(keywords),
        ])

    return "\n".join(lines)


# ============================================================
# CONSTRUÇÃO DOS DOCUMENTS
# ============================================================

def _build_section_document(
    *,
    document_id: str,
    document_title: str,
    section: Mapping[str, Any],
    index_metadata: Mapping[str, Any],
) -> Document:
    section_id = _require_string(
        section.get("section_id"),
        "section_id",
        f"documento {document_id}",
    )

    summary = _require_string(
        section.get("summary"),
        "summary",
        f"seção {section_id}",
    )

    section_label = str(
        section.get("label")
        or section.get("section_label")
        or section.get("title")
        or section_id
    ).strip()

    subjects = _string_list(
        section.get("subjects"),
        "subjects",
        f"seção {section_id}",
    )

    keywords = _string_list(
        section.get("keywords"),
        "keywords",
        f"seção {section_id}",
    )

    if not keywords:
        raise ValueError(
            f"A seção {section_id} não possui palavras-chave."
        )

    content_hash = section.get("content_hash")

    page_content = _format_section_content(
        document_title=document_title,
        document_id=document_id,
        section_id=section_id,
        section_label=section_label,
        summary=summary,
        subjects=subjects,
        keywords=keywords,
    )

    metadata: dict[str, Any] = {}

    # Metadados estáveis do índice/documento.
    _add_scalar_metadata(metadata, index_metadata)
    _add_scalar_metadata(metadata, section.get("metadata"))

    metadata.update({
        "chunk_id": (
            f"semidx::{document_id}::section::{section_id}"
        ),
        "record_type": "section",
        "is_auxiliary": True,
        "document_id": document_id,
        "document_title": document_title,
        "section_id": section_id,
        "section_label": section_label,
        "node_id": section_id,
    })

    if isinstance(content_hash, str) and content_hash:
        metadata["content_hash"] = content_hash

    return Document(
        page_content=page_content,
        metadata=metadata,
    )


def _build_unit_document(
    *,
    document_id: str,
    document_title: str,
    section_id: str,
    section_label: str,
    unit: Mapping[str, Any],
    section_metadata: Mapping[str, Any],
    index_metadata: Mapping[str, Any],
) -> Document:
    node_id = _require_string(
        unit.get("node_id"),
        "node_id",
        f"seção {section_id}",
    )

    summary = _require_string(
        unit.get("summary"),
        "summary",
        f"unidade {node_id}",
    )

    node_type = str(
        unit.get("node_type") or ""
    ).strip()

    label = str(
        unit.get("label") or ""
    ).strip()

    number_value = unit.get("number")
    number = (
        str(number_value).strip()
        if number_value is not None
        else ""
    )

    path = _normalize_path(
        unit.get("path")
    )

    keywords = _string_list(
        unit.get("keywords"),
        "keywords",
        f"unidade {node_id}",
    )

    if not keywords:
        raise ValueError(
            f"A unidade {node_id} não possui palavras-chave."
        )

    page_content = _format_unit_content(
        document_title=document_title,
        document_id=document_id,
        section_label=section_label,
        section_id=section_id,
        node_id=node_id,
        node_type=node_type,
        label=label,
        number=number,
        path=path,
        summary=summary,
        keywords=keywords,
    )

    metadata: dict[str, Any] = {}

    _add_scalar_metadata(metadata, index_metadata)
    _add_scalar_metadata(
        metadata,
        section_metadata.get("metadata"),
    )
    _add_scalar_metadata(metadata, unit.get("metadata"))

    metadata.update({
        "chunk_id": (
            f"semidx::{document_id}::unit::{node_id}"
        ),
        "record_type": "unit",
        "is_auxiliary": True,
        "document_id": document_id,
        "document_title": document_title,
        "section_id": section_id,
        "section_label": section_label,
        "node_id": node_id,
        "source_node_id": node_id,
    })

    if node_type:
        metadata["node_type"] = node_type

    if label:
        metadata["label"] = label

    if number:
        metadata["number"] = number

    if path:
        metadata["path"] = path

    parent_id = unit.get("parent_id")

    if isinstance(parent_id, str) and parent_id.strip():
        metadata["parent_id"] = parent_id.strip()

    content_hash = section_metadata.get("content_hash")

    if isinstance(content_hash, str) and content_hash:
        metadata["content_hash"] = content_hash

    return Document(
        page_content=page_content,
        metadata=metadata,
    )


# ============================================================
# LEITURA DO ÍNDICE SEMÂNTICO
# ============================================================

def load_semantic_documents(
    input_path: Path,
) -> tuple[list[Document], dict[str, int]]:
    """
    Lê o índice semântico completo e converte seus registros
    em Documents do LangChain.

    A função não acessa o Chroma nem gera embeddings.
    """

    if not input_path.exists():
        raise FileNotFoundError(
            f"Índice semântico não encontrado: {input_path}"
        )

    try:
        payload = json.loads(
            input_path.read_text(encoding="utf-8")
        )

    except json.JSONDecodeError as error:
        raise ValueError(
            "O arquivo do índice semântico contém JSON inválido."
        ) from error

    payload = _require_mapping(
        payload,
        "Raiz do índice semântico",
    )

    documents_payload = payload.get("documents")

    if (
        not isinstance(documents_payload, list)
        or not documents_payload
    ):
        raise ValueError(
            "O índice semântico precisa possuir uma lista "
            "'documents' não vazia."
        )

    index_metadata = {
        "index_id": str(payload.get("index_id") or ""),
        "index_format_version": int(
            payload.get("format_version") or 0
        ),
        "index_model_name": str(
            payload.get("model_name") or ""
        ),
        "index_prompt_version": str(
            payload.get("prompt_version") or ""
        ),
    }

    result: list[Document] = []

    seen_document_ids: set[str] = set()
    seen_section_ids: set[tuple[str, str]] = set()
    seen_unit_ids: set[tuple[str, str]] = set()

    section_count = 0
    unit_count = 0

    for document_position, raw_document in enumerate(
        documents_payload,
        start=1,
    ):
        document = _require_mapping(
            raw_document,
            f"Documento na posição {document_position}",
        )

        document_id = _require_string(
            document.get("document_id"),
            "document_id",
            f"documento na posição {document_position}",
        )

        document_title = str(
            document.get("document_title")
            or document.get("title")
            or document_id
        ).strip()

        if document_id in seen_document_ids:
            raise ValueError(
                f"document_id duplicado: {document_id}"
            )

        seen_document_ids.add(document_id)

        sections = document.get("sections")

        if not isinstance(sections, list) or not sections:
            raise ValueError(
                f"O documento {document_id} não possui seções."
            )

        for section_position, raw_section in enumerate(
            sections,
            start=1,
        ):
            section = _require_mapping(
                raw_section,
                f"Seção {section_position} do documento {document_id}",
            )

            section_id = _require_string(
                section.get("section_id"),
                "section_id",
                f"documento {document_id}",
            )

            section_key = (document_id, section_id)

            if section_key in seen_section_ids:
                raise ValueError(
                    f"Seção duplicada: {document_id}/{section_id}"
                )

            seen_section_ids.add(section_key)

            section_label = str(
                section.get("label")
                or section.get("section_label")
                or section.get("title")
                or section_id
            ).strip()

            result.append(
                _build_section_document(
                    document_id=document_id,
                    document_title=document_title,
                    section=section,
                    index_metadata=index_metadata,
                )
            )

            section_count += 1

            units = section.get("units")

            if not isinstance(units, list):
                raise TypeError(
                    f"'units' precisa ser uma lista na seção "
                    f"{section_id}."
                )

            for raw_unit in units:
                unit = _require_mapping(
                    raw_unit,
                    f"Unidade da seção {section_id}",
                )

                node_id = _require_string(
                    unit.get("node_id"),
                    "node_id",
                    f"seção {section_id}",
                )

                unit_key = (document_id, node_id)

                if unit_key in seen_unit_ids:
                    raise ValueError(
                        f"Unidade duplicada: {document_id}/{node_id}"
                    )

                seen_unit_ids.add(unit_key)

                result.append(
                    _build_unit_document(
                        document_id=document_id,
                        document_title=document_title,
                        section_id=section_id,
                        section_label=section_label,
                        unit=unit,
                        section_metadata=section,
                        index_metadata=index_metadata,
                    )
                )

                unit_count += 1

    # Confirma também a unicidade dos IDs que serão usados pelo Chroma.
    chunk_ids = [
        document.metadata["chunk_id"]
        for document in result
    ]

    if len(chunk_ids) != len(set(chunk_ids)):
        raise ValueError(
            "Foram encontrados IDs de indexação duplicados."
        )

    stats = {
        "documents": len(seen_document_ids),
        "sections": section_count,
        "units": unit_count,
        "total_records": len(result),
    }

    return result, stats


# ============================================================
# INDEXAÇÃO
# ============================================================

def index_semantic_records(
    *,
    input_path: Path,
    batch_size: int = DEFAULT_BATCH_SIZE,
    provider: str = "local",
    dry_run: bool = False,
) -> dict[str, Any]:
    if batch_size <= 0:
        raise ValueError(
            "batch_size precisa ser maior que zero."
        )

    settings = get_settings()

    documents, stats = load_semantic_documents(
        input_path=input_path,
    )

    print("=" * 65)
    print("INDEXAÇÃO DO ÍNDICE SEMÂNTICO — POLITIZE-SE")
    print("=" * 65)

    print(f"Arquivo: {input_path}")
    print(f"Provedor de embeddings: {provider}")
    print(f"Modelo de embeddings: {settings.rag_embedding_model}")
    print(f"Coleção-base: {SEMANTIC_COLLECTION_NAME}")

    print("\nREGISTROS PREPARADOS")

    print(f"Documentos: {stats['documents']}")
    print(f"Seções: {stats['sections']}")
    print(f"Unidades: {stats['units']}")
    print(f"Total: {stats['total_records']}")

    type_counts = Counter(
        document.metadata["record_type"]
        for document in documents
    )

    print("\nDISTRIBUIÇÃO")

    for record_type, count in sorted(type_counts.items()):
        print(f"{record_type}: {count}")

    if dry_run:
        print("\n[DRY-RUN] Nenhuma conexão com o Chroma foi aberta.")
        print("[DRY-RUN] Nenhum embedding foi gerado.")
        print("[DRY-RUN] Nenhum registro foi alterado.")
        return {
            **stats,
            "dry_run": True,
        }

    # Cria/abre uma coleção separada da coleção jurídica original.
    vector_store, selected_provider = create_vector_store(
        provider=provider,
        persist_directory=settings.chroma_persist_directory,
        collection_name=SEMANTIC_COLLECTION_NAME,
        settings=settings,
    )

    print(
        "\nIniciando sincronização incremental..."
    )

    sync_result = index_chunks(
        vector_store,
        documents,
        batch_size=batch_size,
    )

    print("\n" + "=" * 65)
    print("INDEXAÇÃO CONCLUÍDA")
    print("=" * 65)

    print(f"Provedor selecionado: {selected_provider}")
    print(f"Total esperado: {sync_result['total_chunks']}")
    print(
        "Inseridos/atualizados: "
        f"{sync_result['inseridos_ou_atualizados']}"
    )
    print(f"Inalterados: {sync_result['inalterados']}")
    print(
        "Removidos por obsolescência: "
        f"{sync_result['removidos_obsoletos']}"
    )

    return {
        **stats,
        **sync_result,
        "provider": selected_provider,
        "dry_run": False,
    }


# ============================================================
# CLI
# ============================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Indexa os resumos semânticos em uma coleção "
            "Chroma exclusiva."
        )
    )

    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT_PATH,
        help="Caminho do indice_semantico.json.",
    )

    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help="Quantidade de documentos por lote de indexação.",
    )

    parser.add_argument(
        "--provider",
        choices=["local", "cloud", "auto"],
        default="local",
        help="Provedor dos embeddings. Padrão: local.",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Valida e contabiliza os registros sem indexar.",
    )

    args = parser.parse_args()

    input_path = args.input.expanduser()

    if not input_path.is_absolute():
        input_path = PROJECT_ROOT / input_path

    input_path = input_path.resolve()

    index_semantic_records(
        input_path=input_path,
        batch_size=args.batch_size,
        provider=args.provider,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
