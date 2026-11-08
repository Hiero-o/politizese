
import hashlib
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal

from langchain_core.documents import Document
from langchain_chroma import Chroma

from src.core.config import (
    PROJECT_ROOT,
    Settings,
    get_settings,
)
from src.rag.embeddings import create_embeddings, _uses_nomic_prefixes


# Compatibilidade temporária com indexar_base.py.
# Será removida quando adaptarmos o script de indexação.
DEFAULT_PERSIST_DIRECTORY = get_settings().chroma_persist_directory


def _model_fragment(model_name: str) -> str:
    """
    Converte o nome do modelo em um fragmento
    válido para o nome da coleção.
    """

    fragment = re.sub(
        r"[^a-zA-Z0-9_-]",
        "_",
        model_name.lower(),
    ).strip("_-")

    return fragment or "default"


def _embedding_profile(model_name: str) -> str:
    """
    Identifica a estratégia utilizada para gerar os embeddings.

    Modelos Nomic utilizam prefixos específicos.
    Outros modelos utilizam a estratégia padrão.
    """

    if _uses_nomic_prefixes(model_name):
        return "nomic_search_prefix_v1"

    return "default_v1"


def _build_collection_name(
    base_name: str,
    profile: str,
    provider: str,
    model_name: str,
) -> str:
    """
    Gera um nome de coleção identificando a configuração
    utilizada para produzir os embeddings.

    Evita misturar vetores gerados por modelos,
    provedores ou estratégias diferentes.
    """

    parts = [
        _model_fragment(base_name),
        profile,
        provider,
        _model_fragment(model_name),
    ]

    name = "_".join(parts)

    # O ChromaDB limita o tamanho do nome da coleção.
    if len(name) > 63:
        suffix = hashlib.sha256(
            name.encode("utf-8")
        ).hexdigest()[:8]

        name = f"{name[:54].rstrip('_-')}_{suffix}"

    return name


def create_vector_store(
    *,
    provider: Literal["local", "cloud", "auto"] | None = None,
    persist_directory: str | Path | None = None,
    collection_name: str | None = None,
    settings: Settings | None = None,
) -> tuple[Chroma, str]:
    """
    Cria ou abre uma coleção persistente no ChromaDB.

    As configurações são obtidas centralmente através
    do Settings.

    Args:
        provider: permite sobrescrever o provedor de embeddings.
        persist_directory: permite sobrescrever o diretório.
        collection_name: nome-base opcional da coleção.
        settings: configurações opcionais da aplicação.

    Returns:
        Tupla contendo (vector_store, provedor selecionado).
    """

    if settings is None:
        settings = get_settings()

    # Inicializa os embeddings utilizando as configurações centrais.
    embeddings, selected_provider = create_embeddings(
        provider=provider,
        settings=settings,
    )

    model_name = settings.rag_embedding_model

    profile = _embedding_profile(model_name)

    # Define o diretório persistente.
    if persist_directory is None:
        db_path = settings.chroma_persist_directory

    else:
        db_path = Path(
            persist_directory
        ).expanduser()

        if not db_path.is_absolute():
            db_path = PROJECT_ROOT / db_path

        db_path = db_path.resolve()

    db_path.mkdir(
        parents=True,
        exist_ok=True,
    )

    # Define o nome da coleção.
    base_name = (
        collection_name
        or settings.chroma_collection_prefix
    )

    final_collection_name = _build_collection_name(
        base_name=base_name,
        profile=profile,
        provider=selected_provider,
        model_name=model_name,
    )

    # Metadados que documentam a configuração do índice.
    collection_metadata = {
        "hnsw:space": "cosine",
        "embedding_provider": selected_provider,
        "embedding_model": model_name,
        "embedding_profile": profile,
    }

    vector_store = Chroma(
        collection_name=final_collection_name,
        embedding_function=embeddings,
        persist_directory=str(db_path),
        collection_metadata=collection_metadata,
    )

    return vector_store, selected_provider


def _read_existing_records(
    vector_store: Chroma,
) -> dict[str, tuple[str, dict[str, Any]]]:
    """
    Lê os IDs, textos e metadados já armazenados.

    Permite identificar documentos que foram modificados
    sem precisar gerar embeddings novamente para todos.
    """

    data = vector_store.get(
        include=["documents", "metadatas"],
    )

    ids = data.get("ids") or []
    texts = data.get("documents") or []
    metadatas = data.get("metadatas") or []

    existing: dict[
        str,
        tuple[str, dict[str, Any]]
    ] = {}

    for index, record_id in enumerate(ids):

        text = (
            texts[index]
            if index < len(texts)
            else ""
        )

        metadata = (
            metadatas[index]
            if index < len(metadatas)
            and metadatas[index]
            else {}
        )

        existing[record_id] = (
            text or "",
            dict(metadata),
        )

    return existing


def index_chunks(
    vector_store: Chroma,
    chunks: Sequence[Document],
    *,
    batch_size: int = 64,
) -> dict[str, int]:
    """
    Sincroniza os chunks com a coleção persistente.

    - Insere chunks novos.
    - Atualiza chunks cujo texto ou metadados mudaram.
    - Preserva chunks inalterados.
    - Remove chunks obsoletos.

    Cada documento precisa possuir um chunk_id único.
    """

    if batch_size <= 0:
        raise ValueError(
            "batch_size deve ser maior que zero."
        )

    documents = list(chunks)

    if not documents:
        raise ValueError(
            "A lista de chunks está vazia. "
            "A indexação foi interrompida para evitar "
            "uma remoção acidental de toda a coleção."
        )

    ids: list[str] = []

    for document in documents:

        chunk_id = document.metadata.get("chunk_id")

        if (
            not isinstance(chunk_id, str)
            or not chunk_id.strip()
        ):
            raise ValueError(
                "Todo chunk precisa de um chunk_id válido."
            )

        ids.append(chunk_id)

    if len(ids) != len(set(ids)):
        raise ValueError(
            "Foram encontrados chunk_id duplicados."
        )

    existing = _read_existing_records(vector_store)

    expected_ids = set(ids)

    # Seleciona apenas documentos novos ou modificados.
    to_upsert: list[Document] = []

    for document, chunk_id in zip(documents, ids):

        existing_record = existing.get(chunk_id)

        if existing_record is None:
            to_upsert.append(document)
            continue

        existing_text, existing_metadata = existing_record

        if (
            existing_text != document.page_content
            or existing_metadata != document.metadata
        ):
            to_upsert.append(document)

    # Insere ou atualiza documentos em lotes.
    for start in range(0, len(to_upsert), batch_size):

        batch = to_upsert[start:start + batch_size]

        batch_ids = [
            document.metadata["chunk_id"]
            for document in batch
        ]

        vector_store.add_documents(
            documents=batch,
            ids=batch_ids,
        )

    # Remove somente os registros que não existem mais
    # na nova base documental.
    stale_ids = sorted(
        set(existing) - expected_ids
    )

    if stale_ids:
        vector_store.delete(
            ids=stale_ids,
        )

    unchanged_count = (
        len(documents) - len(to_upsert)
    )

    return {
        "total_chunks": len(documents),
        "inseridos_ou_atualizados": len(to_upsert),
        "inalterados": unchanged_count,
        "removidos_obsoletos": len(stale_ids),
    }
