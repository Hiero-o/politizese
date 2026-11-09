
from pathlib import Path
from typing import TypedDict

import pymupdf

from src.core.config import get_settings


class PageData(TypedDict):
    documento: str
    caminho: str
    pagina: int
    texto: str


def load_pdf(path: Path) -> list[PageData]:
    """
    Extrai o texto de cada página de um PDF.

    Preserva o nome, o caminho e o número original da página.
    Páginas sem texto são ignoradas.
    """

    if not path.is_file():
        raise FileNotFoundError(
            f"Arquivo PDF não encontrado: {path}"
        )

    if path.suffix.lower() != ".pdf":
        raise ValueError(
            f"O arquivo informado não é um PDF: {path}"
        )

    pages: list[PageData] = []

    with pymupdf.open(str(path)) as pdf:
        for page_number, page in enumerate(pdf, start=1):
            text = (page.get_text("text") or "").strip()

            if not text:
                continue

            pages.append(
                {
                    "documento": path.name,
                    "caminho": str(path.resolve()),
                    "pagina": page_number,
                    "texto": text,
                }
            )

    return pages


def load_documents() -> list[PageData]:
    """
    Carrega todos os PDFs encontrados no diretório
    de documentos configurado no projeto.
    """

    documents_directory = get_settings().documents_directory

    if not documents_directory.is_dir():
        raise FileNotFoundError(
            "Diretório de documentos não encontrado: "
            f"{documents_directory}"
        )

    pdf_files = sorted(
        documents_directory.glob("*.pdf")
    )

    if not pdf_files:
        return []

    documents: list[PageData] = []

    for pdf_path in pdf_files:
        print(f"[Loader] Carregando: {pdf_path.name}")

        pages = load_pdf(pdf_path)

        print(
            f"[Loader] Páginas com texto extraído: {len(pages)}"
        )

        documents.extend(pages)

    return documents
