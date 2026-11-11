
import json
from pathlib import Path

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from services.rag.document_loader import load_documents
from services.rag.parsers.legal_parser import (
    flatten_legal_nodes,
    parse_constitution_pages,
)

from src.core.config import PROJECT_ROOT
from src.rag.vector_store import (
    DEFAULT_PERSIST_DIRECTORY,
    create_vector_store,
    index_chunks,
)


COLLECTION_NAME = "constituicao_legal"

ARTICLE_STORE_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "constituicao_artigos.json"
)


def serialize_legal_node(node):
    """Serializa recursivamente um nó e toda sua hierarquia."""

    record = node.to_record()

    record["children"] = [
        serialize_legal_node(child)
        for child in node.children
    ]

    return record


MAX_EMBEDDING_CHARS = 1800
EMBEDDING_OVERLAP_CHARS = 120

LEGAL_SPLITTER = RecursiveCharacterTextSplitter(
    chunk_size=MAX_EMBEDDING_CHARS,
    chunk_overlap=EMBEDDING_OVERLAP_CHARS,
    separators=[
        "\n\n",
        "\n",
        ". ",
        "; ",
        ", ",
        " ",
        "",
    ],
    length_function=len,
)


def node_to_documents(node) -> list[Document]:
    """Converte uma unidade jurídica em um ou mais Documents."""

    if not node.text.strip():
        raise ValueError(
            f"Unidade jurídica sem conteúdo: {node.node_id}"
        )

    record = node.to_record()

    metadata = {
        key: value
        for key, value in record.items()
        if key != "texto" and value is not None
    }

    metadata["source_node_id"] = node.node_id

    # Unidades pequenas permanecem intactas.
    if len(node.text) <= MAX_EMBEDDING_CHARS:
        return [
            Document(
                page_content=node.text,
                metadata=metadata,
            )
        ]

    # Divide somente unidades grandes.
    fragments = LEGAL_SPLITTER.split_text(node.text)

    documents = []

    for index, fragment in enumerate(fragments, start=1):
        fragment_metadata = {
            **metadata,
            "chunk_id": (
                f"{node.node_id}-PART-{index:03d}"
            ),
            "fragment_index": index,
            "fragment_count": len(fragments),
            "is_fragment": True,
        }

        documents.append(
            Document(
                page_content=fragment,
                metadata=fragment_metadata,
            )
        )

    return documents



def save_article_store(articles) -> None:
    """Persiste a árvore jurídica completa em JSON."""

    payload = {
        "document_id": "CF1988",
        "article_count": len(articles),
        "articles": [
            serialize_legal_node(article)
            for article in articles
        ],
    }

    ARTICLE_STORE_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_path = ARTICLE_STORE_PATH.with_suffix(
        ".json.tmp"
    )

    temporary_path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    temporary_path.replace(ARTICLE_STORE_PATH)

def main() -> None:
    print("=" * 65)
    print("INDEXAÇÃO JURÍDICA — POLITIZE-SE")
    print("=" * 65)

    # 1. Carrega as páginas originais.
    print("\n[1/6] Carregando Constituição...")

    pages = load_documents()

    if not pages:
        raise RuntimeError(
            "Nenhuma página foi carregada."
        )

    print(f"Páginas carregadas: {len(pages)}")

    # 2. Executa o parser jurídico.
    print("\n[2/6] Executando parser jurídico...")

    articles = parse_constitution_pages(
        pages,
        document_id="CF1988",
    )

    if not articles:
        raise RuntimeError(
            "Nenhum artigo foi identificado."
        )

    nodes = flatten_legal_nodes(articles)

    print(f"Artigos identificados: {len(articles)}")
    print(f"Unidades jurídicas totais: {len(nodes)}")

    # 3. Separa artigos completos das unidades indexáveis.
    article_nodes = [
        node
        for node in nodes
        if node.legal_unit == "article"
    ]

    legal_units = [
        node
        for node in nodes
        if node.legal_unit != "article"
    ]

    if not legal_units:
        raise RuntimeError(
            "Nenhuma unidade jurídica foi encontrada para indexação."
        )

    all_ids = [node.node_id for node in nodes]

    if len(all_ids) != len(set(all_ids)):
        raise ValueError(
            "O parser produziu identificadores duplicados."
        )

    print(f"Artigos completos: {len(article_nodes)}")
    print(f"Unidades para indexação: {len(legal_units)}")

    # 4. Converte as unidades em Documents.
    print("\n[3/6] Preparando documentos para o ChromaDB...")

    documents = []

    split_count = 0

    for node in legal_units:
        node_documents = node_to_documents(node)

        documents.extend(node_documents)

        if len(node_documents) > 1:
            split_count += 1

    print(f"Unidades jurídicas originais: {len(legal_units)}")
    print(f"Unidades divididas: {split_count}")
    print(f"Documentos para embeddings: {len(documents)}")

    expected_ids = {
        document.metadata["chunk_id"]
        for document in documents
    }

    if len(expected_ids) != len(documents):
        raise ValueError(
            "Foram encontrados IDs duplicados na conversão."
        )

    print(f"Documents preparados: {len(documents)}")
    print("[OK] IDs únicos e metadados válidos.")
    # Diagnóstico dos maiores documentos antes dos embeddings.
    
    print("\nMaiores unidades jurídicas:")

    longest_documents = sorted(
        documents,
        key=lambda doc: len(doc.page_content),
        reverse=True,
    )

    for document in longest_documents[:20]:
        metadata = document.metadata

        print(
            f"{len(document.page_content):>7} caracteres | "
            f"{metadata.get('legal_unit')} | "
            f"Art. {metadata.get('article_number')} | "
            f"{metadata.get('chunk_id')}"
        )

    print(
        f"\nMaior unidade: "
        f"{len(longest_documents[0].page_content)} caracteres"
    )

    # 5. Inicializa uma coleção exclusiva.
    print("\n[4/6] Inicializando ChromaDB...")

    vector_store, provider = create_vector_store(
        provider="local",
        collection_name=COLLECTION_NAME,
    )

    print(f"Provedor: {provider}")
    print(f"Diretório: {DEFAULT_PERSIST_DIRECTORY}")
    print(f"Coleção: {vector_store._collection.name}")

    # 6. Indexa e valida a persistência.
    print("\n[5/6] Indexando unidades jurídicas...")

    stats = index_chunks(
        vector_store,
        documents,
        batch_size=64,
    )

    print("\nResultado da indexação:")

    for field, value in stats.items():
        print(f"{field}: {value}")

    print("\n[6/6] Validando persistência...")

    stored_data = vector_store.get(
        include=["metadatas"],
    )

    stored_ids = set(
        stored_data.get("ids") or []
    )

    if stored_ids != expected_ids:
        missing_ids = expected_ids - stored_ids
        unexpected_ids = stored_ids - expected_ids

        raise RuntimeError(
            "A coleção persistida não corresponde à base esperada.\n"
            f"IDs ausentes: {len(missing_ids)}\n"
            f"IDs inesperados: {len(unexpected_ids)}"
        )

    print(f"IDs esperados: {len(expected_ids)}")
    print(f"IDs persistidos: {len(stored_ids)}")

    # Persiste os artigos completos fora do índice vetorial.
    # Eles serão utilizados posteriormente para recuperar contexto.
    save_article_store(article_nodes)

    print(f"\nArtigos completos salvos em:")
    print(ARTICLE_STORE_PATH)

    print("\n" + "=" * 65)
    print("INDEXAÇÃO JURÍDICA CONCLUÍDA COM SUCESSO")
    print("=" * 65)


if __name__ == "__main__":
    main()
