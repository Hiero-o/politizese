
from services.rag.document_loader import load_documents

from src.rag.chunking import (
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
    split_pages_into_chunks,
)

from src.rag.vector_store import (
    DEFAULT_PERSIST_DIRECTORY,
    create_vector_store,
    index_chunks,
)


def main() -> None:
    print("=" * 60)
    print("INDEXAÇÃO DOCUMENTAL — POLITIZE-SE")
    print("=" * 60)

    # 1. Carrega os documentos originais.
    pages = load_documents()

    if not pages:
        raise RuntimeError(
            "Nenhuma página foi carregada. "
            "A indexação foi interrompida."
        )

    print(f"\nPáginas carregadas: {len(pages)}")

    # 2. Divide as páginas em chunks.
    print("\nConfigurando chunking...")

    print(f"Chunk size: {DEFAULT_CHUNK_SIZE}")
    print(f"Chunk overlap: {DEFAULT_CHUNK_OVERLAP}")

    chunks = split_pages_into_chunks(
        pages,
        chunk_size=DEFAULT_CHUNK_SIZE,
        chunk_overlap=DEFAULT_CHUNK_OVERLAP,
    )

    if not chunks:
        raise RuntimeError(
            "Nenhum chunk foi gerado. "
            "A indexação foi interrompida."
        )

    print(f"Chunks gerados: {len(chunks)}")

    # 3. Valida os identificadores dos chunks.
    expected_ids = set()

    for chunk in chunks:
        chunk_id = chunk.metadata.get("chunk_id")

        if not chunk_id:
            raise ValueError(
                "Foi encontrado um chunk sem chunk_id."
            )

        expected_ids.add(str(chunk_id))

    if len(expected_ids) != len(chunks):
        raise ValueError(
            "Foram encontrados identificadores de chunks duplicados."
        )

    print("[OK] Todos os chunks possuem IDs únicos.")

    # 4. Inicializa o ChromaDB.
    print("\nInicializando ChromaDB...")

    vector_store, provider = create_vector_store(
        provider="local",
    )

    print(f"Provedor de embeddings: {provider}")
    print(f"Diretório do ChromaDB: {DEFAULT_PERSIST_DIRECTORY}")
    print(f"Coleção: {vector_store._collection.name}")

    # 5. Indexa e sincroniza os chunks.
    print("\nIniciando indexação...")

    stats = index_chunks(
        vector_store,
        chunks,
    )

    print("\nResultado da indexação:")

    for field, value in stats.items():
        print(f"{field}: {value}")

    # 6. Confirma os registros persistidos.
    print("\nValidando persistência...")

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

    print("[OK] Todos os chunks estão persistidos.")
    print("[OK] Não existem IDs extras na coleção.")

    print("\n" + "=" * 60)
    print("indexação válida com sucesso")
    print("=" * 60)


if __name__ == "__main__":
    main()
