
import hashlib
import json

from langchain_core.documents import Document

from services.rag.document_loader import load_documents

from src.rag.parent_retriever import (
    create_parent_document_retriever,
)


# Configurações dos experimentos.
# Os chunks filhos permanecem iguais para isolar
# o efeito do tamanho dos chunks pais.

CHILD_CHUNK_SIZE = 200
CHILD_CHUNK_OVERLAP = 40

EXPERIMENTS = [
    {
        "parent_chunk_size": 1024,
        "parent_chunk_overlap": 128,
    },
    {
        "parent_chunk_size": 1512,
        "parent_chunk_overlap": 192,
    },
    {
        "parent_chunk_size": 2024,
        "parent_chunk_overlap": 256,
    },
]


def convert_pages_to_documents(pages: list[dict]) -> list[Document]:
    """Converte as páginas extraídas em objetos Document do LangChain."""

    documents = []

    for page in pages:
        documents.append(
            Document(
                page_content=page["texto"],
                metadata={
                    "documento": page["documento"],
                    "source": page["caminho"],
                    "pagina": page["pagina"],
                    "page": page["pagina"],
                },
            )
        )

    return documents


def generate_parent_ids(
    parent_documents: list[Document],
    parent_chunk_size: int,
    parent_chunk_overlap: int,
) -> list[str]:
    """Gera IDs determinísticos para os documentos pais."""

    ids = []

    for index, document in enumerate(parent_documents):
        identity = {
            "source": document.metadata.get("source"),
            "page": document.metadata.get("pagina"),
            "start_index": document.metadata.get("start_index", 0),
            "parent_chunk_size": parent_chunk_size,
            "parent_chunk_overlap": parent_chunk_overlap,
            "index": index,
        }

        serialized = json.dumps(
            identity,
            ensure_ascii=False,
            sort_keys=True,
        )

        parent_id = hashlib.sha256(
            serialized.encode("utf-8")
        ).hexdigest()

        ids.append(parent_id)

    return ids


def run_experiment(
    documents: list[Document],
    parent_chunk_size: int,
    parent_chunk_overlap: int,
) -> dict:
    """Executa a indexação de uma configuração experimental."""

    print("\n" + "=" * 65)
    print(
        f"EXPERIMENTO — PAI {parent_chunk_size} / "
        f"OVERLAP {parent_chunk_overlap}"
    )
    print("=" * 65)

    retriever, provider = create_parent_document_retriever(
        parent_chunk_size=parent_chunk_size,
        parent_chunk_overlap=parent_chunk_overlap,
        child_chunk_size=CHILD_CHUNK_SIZE,
        child_chunk_overlap=CHILD_CHUNK_OVERLAP,
        k=4,
        provider="local",
    )

    vector_store = retriever.vectorstore
    collection = vector_store._collection

    # Não permite adicionar os mesmos documentos novamente.
    existing_children = collection.count()
    existing_parents = list(retriever.docstore.yield_keys())

    if existing_children > 0 or existing_parents:
        raise RuntimeError(
            "A coleção deste experimento já possui registros.\n"
            f"Chunks filhos existentes: {existing_children}\n"
            f"Documentos pais existentes: {len(existing_parents)}\n"
            "A indexação foi interrompida para evitar duplicações."
        )

    # Divide as páginas em documentos pais.
    parent_documents = retriever.parent_splitter.split_documents(
        documents
    )

    if not parent_documents:
        raise RuntimeError(
            "Nenhum documento pai foi gerado."
        )

    # Conta os filhos que serão produzidos.
    expected_children = 0

    for parent in parent_documents:
        children = retriever.child_splitter.split_documents(
            [parent]
        )

        expected_children += len(children)

    if expected_children == 0:
        raise RuntimeError(
            "Nenhum chunk filho foi gerado."
        )

    # Cria identificadores estáveis para os pais.
    parent_ids = generate_parent_ids(
        parent_documents,
        parent_chunk_size,
        parent_chunk_overlap,
    )

    if len(set(parent_ids)) != len(parent_ids):
        raise RuntimeError(
            "Foram encontrados IDs de documentos pais duplicados."
        )

    print(f"\nProvedor de embeddings: {provider}")
    print(f"Documentos originais: {len(documents)}")
    print(f"Documentos pais: {len(parent_documents)}")
    print(f"Chunks filhos esperados: {expected_children}")

    # Indexa os filhos e persiste os pais.
    print("\nIniciando indexação...")

    retriever.add_documents(
        documents,
        ids=parent_ids,
    )

    # Verifica os resultados.
    stored_children = collection.count()
    stored_parent_ids = set(
        retriever.docstore.yield_keys()
    )

    if stored_children != expected_children:
        raise RuntimeError(
            "Quantidade de chunks filhos diferente do esperado.\n"
            f"Esperados: {expected_children}\n"
            f"Persistidos: {stored_children}"
        )

    if stored_parent_ids != set(parent_ids):
        raise RuntimeError(
            "Os documentos pais persistidos não correspondem "
            "aos documentos esperados."
        )

    result = {
        "parent_chunk_size": parent_chunk_size,
        "parent_chunk_overlap": parent_chunk_overlap,
        "child_chunk_size": CHILD_CHUNK_SIZE,
        "child_chunk_overlap": CHILD_CHUNK_OVERLAP,
        "parents": len(parent_documents),
        "children": stored_children,
        "provider": provider,
        "collection": collection.name,
    }

    print("\n[OK] Experimento indexado e validado.")
    print(f"Pais persistidos: {len(stored_parent_ids)}")
    print(f"Filhos persistidos: {stored_children}")
    print(f"Coleção: {collection.name}")

    return result


def main() -> None:
    print("=" * 65)
    print("EXPERIMENTAÇÃO PARENT DOCUMENT RETRIEVER — POLITIZE-SE")
    print("=" * 65)

    # 1. Carrega as páginas uma única vez.
    pages = load_documents()

    if not pages:
        raise RuntimeError(
            "Nenhuma página foi carregada."
        )

    documents = convert_pages_to_documents(pages)

    print(f"\nPáginas carregadas: {len(pages)}")
    print(f"Documentos preparados: {len(documents)}")

    results = []

    # 2. Executa as três configurações.
    for experiment in EXPERIMENTS:
        result = run_experiment(
            documents=documents,
            parent_chunk_size=experiment["parent_chunk_size"],
            parent_chunk_overlap=experiment["parent_chunk_overlap"],
        )

        results.append(result)

    # 3. Exibe o resumo.
    print("\n" + "=" * 65)
    print("RESUMO DOS EXPERIMENTOS")
    print("=" * 65)

    for result in results:
        print(
            f"\nPai: {result['parent_chunk_size']} caracteres"
            f"\nOverlap: {result['parent_chunk_overlap']}"
            f"\nFilhos: {result['children']}"
            f"\nPais: {result['parents']}"
            f"\nColeção: {result['collection']}"
        )

    print("\n[OK] Os três experimentos foram indexados.")
    print("Agora podemos comparar a qualidade da recuperação.")


if __name__ == "__main__":
    main()
