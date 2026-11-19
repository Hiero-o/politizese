"""Indexa a base legislativa simulada do Politize-se a partir de arquivos Markdown.

A coleção criada é independente do índice da Constituição Federal.
O script também gera a árvore jurídica necessária ao índice lexical BM25.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.rag.parsers.legal_parser import (  # noqa: E402
    flatten_legal_nodes,
    parse_constitution_pages,
)

DOCUMENTS_DIR = PROJECT_ROOT / "knowledge" / "base_simulada_politica"
TREE_PATH = PROJECT_ROOT / "data" / "processed" / "base_politica_simulada_artigos.json"
COLLECTION_BASE_NAME = "politizese_politica_simulada_v1"
DOCUMENT_ID = "POLITICA_SIMULADA"

FRONTMATTER_PATTERN = re.compile(r"\A---\s*\n(?P<metadata>.*?)\n---\s*\n(?P<body>.*)\Z", re.DOTALL)
WORD_PATTERN = re.compile(r"\b[\wÀ-ÿºª]+(?:[-–][\wÀ-ÿºª]+)*\b", re.UNICODE)


def parse_frontmatter(path: Path) -> tuple[dict[str, str], str]:
    """Lê o front matter YAML simples utilizado nos arquivos da atividade."""

    raw_text = path.read_text(encoding="utf-8")
    match = FRONTMATTER_PATTERN.match(raw_text)
    if not match:
        raise ValueError(f"Front matter ausente ou inválido em: {path.name}")

    metadata: dict[str, str] = {}
    for line in match.group("metadata").splitlines():
        if not line.strip() or ":" not in line:
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip().strip("\"'")

    required = ("titulo", "data_publicacao", "tema", "tipo_documento")
    missing = [field for field in required if not metadata.get(field)]
    if missing:
        raise ValueError(
            f"Metadados ausentes em {path.name}: {', '.join(missing)}"
        )

    return metadata, match.group("body").strip()


def load_markdown_pages() -> tuple[list[dict[str, Any]], dict[str, dict[str, str]]]:
    """Converte cada Markdown em uma página textual para o parser jurídico."""

    files = sorted(DOCUMENTS_DIR.glob("*.md"))
    if len(files) < 2:
        raise RuntimeError(
            f"A base precisa conter pelo menos dois arquivos .md em {DOCUMENTS_DIR}"
        )

    pages: list[dict[str, Any]] = []
    metadata_by_filename: dict[str, dict[str, str]] = {}

    for path in files:
        metadata, body = parse_frontmatter(path)

        # Normaliza a formatação Markdown dos artigos para o parser jurídico.
        # O arquivo original permanece intacto.
        body = re.sub(
            r"(?m)^\s*\*\*(Art\.\s*\d+(?:-[A-Za-z])?\s*[º°]?)\*\*",
            r"\1",
            body,
        )

        words = WORD_PATTERN.findall(body)

        if len(words) < 100:
            raise ValueError(
                f"{path.name} possui {len(words)} palavras no corpo; "
                "o requisito mínimo é de 100 palavras."
            )

        metadata_by_filename[path.name] = metadata
        pages.append(
            {
                "documento": path.name,
                "caminho": str(path.resolve()),
                "pagina": 1,
                "texto": body,
            }
        )

    return pages, metadata_by_filename


def serialize_node(node: Any, metadata_by_filename: dict[str, dict[str, str]]) -> dict[str, Any]:
    """Serializa o nó jurídico e preserva os metadados de origem."""

    record = node.to_record()
    source_metadata = metadata_by_filename.get(node.document_name, {})
    record.update(source_metadata)
    record["children"] = [
        serialize_node(child, metadata_by_filename)
        for child in node.children
    ]
    return record



def prepare_base() -> tuple[list[Any], list[Any], dict[str, dict[str, str]]]:
    """Valida documentos e executa o parser jurídico sem gerar embeddings."""

    pages, metadata_by_filename = load_markdown_pages()
    
    print("\n=== DIAGNÓSTICO DOS DOCUMENTOS ===")

    for page in pages:
        print("Nome:", page["documento"])
        print("Caminho:", page["caminho"])
        print("Página:", page["pagina"])
        print("-" * 50)

    # Envia todos os documentos juntos.
    # O legal_parser diferencia automaticamente cada arquivo
    # utilizando seu nome como parte do identificador.
    articles = parse_constitution_pages(
        pages,
        document_id=DOCUMENT_ID,
    )

    if not articles:
        raise RuntimeError(
            "O parser não identificou artigos. Confira se os dispositivos "
            "estão em linhas iniciadas por 'Art. 1º', 'Art. 2º' etc."
        )

    nodes = flatten_legal_nodes(articles)

    legal_units = [
        node for node in nodes
        if node.legal_unit != "article"
    ]

    if not legal_units:
        raise RuntimeError(
            "O parser não identificou unidades jurídicas indexáveis."
        )

    # Verifica IDs duplicados antes da indexação.
    node_ids = [node.node_id for node in nodes]

    if len(node_ids) != len(set(node_ids)):
        duplicated = sorted({
            node_id for node_id in node_ids
            if node_ids.count(node_id) > 1
        })

        raise RuntimeError(
            f"IDs jurídicos duplicados: {duplicated}"
        )

    return articles, legal_units, metadata_by_filename



def validate_only() -> None:
    """Executa as validações locais, sem conexão com Ollama ou ChromaDB."""

    articles, legal_units, metadata = prepare_base()
    print("VALIDAÇÃO DA BASE LEGISLATIVA SIMULADA")
    print(f"Documentos: {len(metadata)}")
    for filename, fields in sorted(metadata.items()):
        print(
            f"- {filename}: {fields['titulo']} | "
            f"publicação={fields['data_publicacao']} | tema={fields['tema']}"
        )
    print(f"Artigos identificados: {len(articles)}")
    print(f"Unidades jurídicas indexáveis: {len(legal_units)}")
    print("Validação concluída. Nenhum embedding foi gerado.")


def index_base() -> None:
    """Cria a árvore legal e indexa os dispositivos no ChromaDB."""

    articles, legal_units, metadata_by_filename = prepare_base()

    # Dependências LangChain/Chroma são carregadas somente na indexação real.
    from indexar_base import node_to_documents
    from src.rag.vector_store import create_vector_store, index_chunks

    documents = []
    for node in legal_units:
        node_documents = node_to_documents(node)
        source_metadata = metadata_by_filename.get(node.document_name, {})
        for document in node_documents:
            document.metadata.update(source_metadata)
            document.metadata["source_filename"] = node.document_name
            document.metadata["document_source_type"] = "simulated_legislation"
        documents.extend(node_documents)

    if not documents:
        raise RuntimeError("Nenhum chunk foi preparado para indexação.")

    chunk_ids = [document.metadata.get("chunk_id") for document in documents]
    if any(not isinstance(item, str) or not item for item in chunk_ids):
        raise RuntimeError("Foi encontrado chunk sem chunk_id válido.")
    if len(chunk_ids) != len(set(chunk_ids)):
        raise RuntimeError("Foram encontrados chunk_id duplicados.")

    TREE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tree_payload = {
        "document_id": DOCUMENT_ID,
        "dataset": "base_politica_simulada",
        "article_count": len(articles),
        "documents": [
            {
                "filename": filename,
                **fields,
            }
            for filename, fields in sorted(metadata_by_filename.items())
        ],
        "articles": [
            serialize_node(article, metadata_by_filename)
            for article in articles
        ],
    }
    temporary_tree_path = TREE_PATH.with_suffix(".json.tmp")
    temporary_tree_path.write_text(
        json.dumps(tree_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary_tree_path.replace(TREE_PATH)

    vector_store, provider = create_vector_store(
        provider="local",
        collection_name=COLLECTION_BASE_NAME,
    )
    collection = vector_store._collection

    if collection.count() > 0:
        raise RuntimeError(
            f"A coleção '{collection.name}' já possui {collection.count()} registros. "
            "Para preservar dados, a indexação foi interrompida. Use outro nome de "
            "coleção ou remova a coleção simulada conscientemente antes de reindexar."
        )

    print(f"Coleção: {collection.name}")
    print(f"Provedor de embeddings: {provider}")
    print(f"Dispositivos jurídicos: {len(legal_units)}")
    print(f"Chunks preparados: {len(documents)}")

    stats = index_chunks(vector_store, documents, batch_size=64)
    stored_ids = set(vector_store.get(include=["metadatas"]).get("ids") or [])
    missing_ids = set(chunk_ids) - stored_ids
    if missing_ids:
        raise RuntimeError(
            f"Falha de integridade: {len(missing_ids)} chunks não foram persistidos."
        )

    print("\nINDEXAÇÃO CONCLUÍDA")
    for key, value in stats.items():
        print(f"{key}: {value}")
    print(f"Árvore jurídica: {TREE_PATH}")
    print(f"Coleção-base para o RAGAS: {COLLECTION_BASE_NAME}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Valida ou indexa a base legislativa simulada do Politize-se."
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Valida Markdown e parser jurídico sem gerar embeddings.",
    )
    args = parser.parse_args()

    if args.validate_only:
        validate_only()
    else:
        index_base()


if __name__ == "__main__":
    main()
