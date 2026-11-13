
import indexar_base as source

from src.rag.vector_store import (
    create_vector_store,
    index_chunks,
)


NEW_COLLECTION_NAME = "constituicao_legal_clean_v2"


def main():
    print("=" * 70)
    print("REINDEXAÇÃO LIMPA — CONSTITUIÇÃO FEDERAL")
    print("=" * 70)

    # 1. Carrega e interpreta a Constituição utilizando
    # exatamente o mesmo parser da indexação original.
    print("\n[1/5] Carregando documentos...")

    pages = source.load_documents()

    if not pages:
        raise RuntimeError("Nenhuma página foi carregada.")

    articles = source.parse_constitution_pages(
        pages,
        document_id="CF1988",
    )

    nodes = source.flatten_legal_nodes(articles)

    legal_units = [
        node
        for node in nodes
        if node.legal_unit != "article"
    ]

    # 2. Prepara os documentos.
    print("\n[2/5] Preparando unidades jurídicas...")

    documents = []

    for node in legal_units:
        documents.extend(
            source.node_to_documents(node)
        )

    if not documents:
        raise RuntimeError(
            "Nenhum documento foi preparado."
        )

    expected_ids = {
        document.metadata["chunk_id"]
        for document in documents
    }

    if len(expected_ids) != len(documents):
        raise RuntimeError(
            "Foram encontrados IDs duplicados."
        )

    print(f"Artigos identificados: {len(articles)}")
    print(f"Unidades jurídicas: {len(legal_units)}")
    print(f"Documentos para embeddings: {len(documents)}")

    # 3. Cria uma coleção independente.
    print("\n[3/5] Inicializando nova coleção...")

    vector_store, provider = create_vector_store(
        provider="local",
        collection_name=NEW_COLLECTION_NAME,
    )

    collection = vector_store._collection

    print("Provedor:", provider)
    print("Coleção:", collection.name)
    print("Metadados:", collection.metadata)

    # Proteção: não sobrescrever uma coleção existente.
    if collection.count() != 0:
        raise RuntimeError(
            "A coleção de destino já contém registros. "
            "A indexação foi interrompida para preservar "
            "os dados existentes."
        )

    # 4. Gera os embeddings novamente.
    print("\n[4/5] Gerando embeddings...")

    stats = index_chunks(
        vector_store,
        documents,
        batch_size=64,
    )

    for name, value in stats.items():
        print(f"{name}: {value}")

    # 5. Confere a integridade da nova coleção.
    print("\n[5/5] Validando registros...")

    stored = vector_store.get(
        include=["metadatas"],
    )

    stored_ids = set(stored.get("ids") or [])

    missing = expected_ids - stored_ids
    unexpected = stored_ids - expected_ids

    if missing or unexpected:
        raise RuntimeError(
            "A validação da nova coleção falhou.\n"
            f"IDs ausentes: {len(missing)}\n"
            f"IDs inesperados: {len(unexpected)}"
        )

    print("Total esperado:", len(expected_ids))
    print("Total armazenado:", len(stored_ids))

    print("\n" + "=" * 70)
    print("REINDEXAÇÃO CONCLUÍDA")
    print("=" * 70)


if __name__ == "__main__":
    main()
