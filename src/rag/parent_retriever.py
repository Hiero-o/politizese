
from pathlib import Path
from typing import Literal

from langchain_classic.retrievers import ParentDocumentRetriever
from langchain_classic.storage import LocalFileStore
from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.core.config import Settings, get_settings
from src.rag.vector_store import create_vector_store


# Configuração inicial para os experimentos.
DEFAULT_CHILD_CHUNK_SIZE = 200
DEFAULT_CHILD_CHUNK_OVERLAP = 40

DEFAULT_PARENT_CHUNK_SIZE = 1024
DEFAULT_PARENT_CHUNK_OVERLAP = 128

DEFAULT_TOP_K = 4


def create_parent_document_retriever(
    *,
    parent_chunk_size: int = DEFAULT_PARENT_CHUNK_SIZE,
    parent_chunk_overlap: int = DEFAULT_PARENT_CHUNK_OVERLAP,
    child_chunk_size: int = DEFAULT_CHILD_CHUNK_SIZE,
    child_chunk_overlap: int = DEFAULT_CHILD_CHUNK_OVERLAP,
    k: int = DEFAULT_TOP_K,
    provider: Literal["local", "cloud", "auto"] = "local",
    settings: Settings | None = None,
) -> tuple[ParentDocumentRetriever, str]:
    """
    Cria um ParentDocumentRetriever.

    Chunks filhos:
        São indexados no ChromaDB e utilizados na busca semântica.

    Chunks pais:
        São armazenados no LocalFileStore e recuperados
        quando seus respectivos filhos são encontrados.
    """

    if settings is None:
        settings = get_settings()

    # 1. Valida os parâmetros.
    if parent_chunk_size <= 0 or child_chunk_size <= 0:
        raise ValueError(
            "Os tamanhos dos chunks devem ser maiores que zero."
        )

    if parent_chunk_overlap < 0 or child_chunk_overlap < 0:
        raise ValueError(
            "Os overlaps não podem ser negativos."
        )

    if parent_chunk_overlap >= parent_chunk_size:
        raise ValueError(
            "O overlap do pai deve ser menor que seu tamanho."
        )

    if child_chunk_overlap >= child_chunk_size:
        raise ValueError(
            "O overlap do filho deve ser menor que seu tamanho."
        )

    if child_chunk_size >= parent_chunk_size:
        raise ValueError(
            "O chunk filho deve ser menor que o chunk pai."
        )

    if k <= 0:
        raise ValueError("k deve ser maior que zero.")

    # 2. Identifica a coleção do experimento.
    collection_name = (
        f"politizese_parent_c{child_chunk_size}"
        f"_p{parent_chunk_size}"
    )

    # 3. Cria os splitters.
    parent_splitter = RecursiveCharacterTextSplitter(
        chunk_size=parent_chunk_size,
        chunk_overlap=parent_chunk_overlap,
        length_function=len,
        separators=["\n\n", "\n", " ", ""],
        add_start_index=True,
        strip_whitespace=True,
    )

    child_splitter = RecursiveCharacterTextSplitter(
        chunk_size=child_chunk_size,
        chunk_overlap=child_chunk_overlap,
        length_function=len,
        separators=["\n\n", "\n", " ", ""],
        add_start_index=True,
        strip_whitespace=True,
    )

    # 4. Inicializa o ChromaDB.
    vector_store, selected_provider = create_vector_store(
        provider=provider,
        collection_name=collection_name,
        settings=settings,
    )

    # 5. Define armazenamento persistente dos pais.
    parent_store_directory = (
        settings.chroma_persist_directory.parent
        / "parent_documents"
        / collection_name
    )

    parent_store_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    parent_store = LocalFileStore(
        root_path=parent_store_directory,
    )

    # 6. Monta o ParentDocumentRetriever.
    retriever = ParentDocumentRetriever(
        vectorstore=vector_store,
        byte_store=parent_store,
        parent_splitter=parent_splitter,
        child_splitter=child_splitter,
        search_kwargs={"k": k},
    )

    print("[RAG] ParentDocumentRetriever inicializado.")
    print(f"[RAG] Coleção: {collection_name}")
    print(f"[RAG] Provedor: {selected_provider}")
    print(
        "[RAG] Chunk filho: "
        f"{child_chunk_size} caracteres / "
        f"overlap {child_chunk_overlap}"
    )
    print(
        "[RAG] Chunk pai: "
        f"{parent_chunk_size} caracteres / "
        f"overlap {parent_chunk_overlap}"
    )
    print(
        "[RAG] Diretório dos pais: "
        f"{parent_store_directory}"
    )

    return retriever, selected_provider
