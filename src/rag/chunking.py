
from collections.abc import Mapping, Sequence
from typing import Any

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter


# Valores provisórios para o primeiro experimento.
# Serão comparados com outras configurações na avaliação do RAG.
DEFAULT_CHUNK_SIZE = 512
DEFAULT_CHUNK_OVERLAP = 80


def split_pages_into_chunks(
    pages: Sequence[Mapping[str, Any]],
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    excluded_pages_by_document: Mapping[str, set[int]] | None = None,
) -> list[Document]:
    """
    Divide as páginas em chunks e preserva os metadados de origem.

    O chunk_size e o chunk_overlap são medidos em caracteres, não em tokens.

    excluded_pages_by_document permite ignorar páginas específicas. A chave deve ser o nome do documento, por exemplo: {"Constituicao.pdf": {1, 2}}.
    """

    if not isinstance(chunk_size, int) or isinstance(chunk_size, bool):
        raise TypeError("chunk_size deve ser um número inteiro.")

    if chunk_size <= 0:
        raise ValueError("chunk_size deve ser maior que zero.")

    if not isinstance(chunk_overlap, int) or isinstance(chunk_overlap, bool):
        raise TypeError("chunk_overlap deve ser um número inteiro.")

    if chunk_overlap < 0:
        raise ValueError("chunk_overlap não pode ser negativo.")

    if chunk_overlap >= chunk_size:
        raise ValueError(
            "chunk_overlap deve ser menor que chunk_size."
        )

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        separators=["\n\n", "\n", " ", ""],
        add_start_index=True,
        strip_whitespace=True,
    )

    chunks: list[Document] = []

    excluded_pages = excluded_pages_by_document or {}

    for page in pages:
        page_text = page.get("texto", "")

        if not isinstance(page_text, str):
            raise TypeError(
                "O campo 'texto' de cada página deve ser uma string."
            )

        page_text = page_text.strip()

        if not page_text:
            continue

        document_name = str(
            page.get("documento") or "documento_desconhecido"
        )

        source_path = page.get("caminho")

        if not isinstance(source_path, str) or not source_path.strip():
            source_path = document_name
        else:
            source_path = source_path.strip()

        try:
            page_number = int(page.get("pagina", 1))
        except (TypeError, ValueError) as error:
            raise ValueError(
                f"Número de página inválido para {document_name}."
            ) from error

        if page_number < 1:
            raise ValueError(
                f"O número de página deve ser positivo: {page_number}."
            )

        # Permite ignorar páginas específicas de um documento.
        if page_number in excluded_pages.get(document_name, set()):
            continue

        base_metadata = {
            "documento": document_name,
            "source": source_path,
            "pagina": page_number,
            "page": page_number,
        }

        page_chunks = splitter.create_documents(
            texts=[page_text],
            metadatas=[base_metadata],
        )

        for chunk_index, split_document in enumerate(page_chunks):
            metadata = dict(split_document.metadata)

            metadata["chunk_index"] = chunk_index
            metadata["chunk_id"] = (
                f"{document_name}|p{page_number}|c{chunk_index:04d}"
            )
            metadata["chunk_chars"] = len(
                split_document.page_content
            )

            chunks.append(
                Document(
                    page_content=split_document.page_content,
                    metadata=metadata,
                )
            )

    return chunks
