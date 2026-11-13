"""Índice lexical BM25 independente para unidades da Constituição.

A coleção lexical é construída a partir da árvore jurídica produzida por
``indexar_base.py``. Ela é independente dos candidatos retornados pelo ChromaDB.
O texto original é preservado como page_content e os identificadores jurídicos
são mantidos nos metadados.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter, defaultdict
from functools import lru_cache
from math import log
from pathlib import Path
from typing import Any, Iterable

from langchain_core.documents import Document

from src.core.config import PROJECT_ROOT


DEFAULT_LEGAL_TREE_PATH = (
    PROJECT_ROOT / "data" / "processed" / "constituicao_artigos.json"
)

BM25_K1 = 1.5
BM25_B = 0.75

# Mantém compatibilidade geral com o diagnóstico lexical, mas preserva
# negações e exceções jurídicas ("não", "sem", "nunca", "exceto").
STOPWORDS = {
    "a", "o", "os", "as", "um", "uma", "uns", "umas",
    "de", "do", "da", "dos", "das", "em", "no", "na", "nos", "nas",
    "e", "ou", "que", "se", "para", "por", "com", "ao", "aos",
    "à", "às", "é", "são", "ser", "foi", "será", "como", "qual", "quais",
    "quem", "sua", "suas", "seu", "seus", "este", "esta", "isso", "aquele",
    "aquela", "sobre", "entre", "até", "também", "mais", "menos", "pelo", "pela",
}


def normalize_text(text: str) -> str:
    """Remove acentos e uniformiza maiúsculas/minúsculas."""

    normalized = unicodedata.normalize("NFKD", text.casefold())
    return "".join(
        character
        for character in normalized
        if not unicodedata.combining(character)
    )


def tokenize(text: str) -> list[str]:
    """Tokeniza texto jurídico usando as mesmas regras do teste BM25."""

    return [
        token
        for token in re.findall(r"[a-z0-9]+", normalize_text(text))
        if token not in STOPWORDS and len(token) > 1
    ]


def _flatten_nodes(node: dict[str, Any]) -> Iterable[dict[str, Any]]:
    """Percorre recursivamente os nós da árvore jurídica serializada."""

    yield node
    children = node.get("children") or []
    if not isinstance(children, list):
        raise ValueError("O campo 'children' de um nó precisa ser uma lista.")

    for child in children:
        if not isinstance(child, dict):
            raise ValueError("A árvore jurídica contém um filho inválido.")
        yield from _flatten_nodes(child)


def load_legal_documents(tree_path: str | Path) -> list[Document]:
    """Carrega as unidades jurídicas originais como Documents do LangChain.

    O JSON é lido pelo programa durante a inicialização do índice lexical.
    Este módulo não altera o arquivo nem a coleção ChromaDB.
    """

    path = Path(tree_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(
            f"Árvore jurídica não encontrada: {path}. "
            "Execute a etapa de indexação da Constituição para gerá-la."
        )

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(
            f"A árvore jurídica contém JSON inválido: {path} "
            f"(linha {error.lineno}, coluna {error.colno})."
        ) from error

    if not isinstance(payload, dict):
        raise ValueError("A raiz da árvore jurídica precisa ser um objeto.")

    articles = payload.get("articles")
    if not isinstance(articles, list) or not articles:
        raise ValueError("A árvore jurídica não contém uma lista 'articles' válida.")

    documents: list[Document] = []
    seen_ids: set[str] = set()

    for article in articles:
        if not isinstance(article, dict):
            raise ValueError("A árvore contém um artigo com formato inválido.")

        for node in _flatten_nodes(article):
            node_id = node.get("chunk_id")
            text = node.get("texto")
            legal_unit = node.get("legal_unit")

            if legal_unit == "article":
                continue
            if not isinstance(node_id, str) or not node_id.strip():
                continue
            if not isinstance(text, str) or not text.strip():
                continue
            if node_id in seen_ids:
                raise ValueError(f"Identificador jurídico duplicado: {node_id}")

            seen_ids.add(node_id)

            # Mantém apenas metadados escalares para compatibilidade com
            # Document e para evitar carregar a árvore inteira em cada item.
            metadata = {
                key: value
                for key, value in node.items()
                if key not in {"children", "texto"}
                and isinstance(value, (str, int, float, bool))
            }
            metadata["chunk_id"] = node_id
            metadata["source_node_id"] = node_id

            documents.append(
                Document(
                    page_content=text.strip(),
                    metadata=metadata,
                )
            )

    if not documents:
        raise ValueError("Nenhuma unidade jurídica válida foi encontrada.")

    return documents


class LegalBM25Index:
    """Índice BM25 global sobre todas as unidades jurídicas originais."""

    def __init__(
        self,
        documents: list[Document],
        *,
        k1: float = BM25_K1,
        b: float = BM25_B,
    ) -> None:
        if not documents:
            raise ValueError("O índice BM25 não pode ser criado sem documentos.")
        if k1 <= 0:
            raise ValueError("BM25 k1 precisa ser maior que zero.")
        if not 0 <= b <= 1:
            raise ValueError("BM25 b precisa estar entre zero e um.")

        self.documents = documents
        self.k1 = float(k1)
        self.b = float(b)
        self.doc_count = len(documents)

        self.tokenized_documents = [
            tokenize(document.page_content)
            for document in documents
        ]
        self.document_lengths = [
            len(tokens)
            for tokens in self.tokenized_documents
        ]
        self.average_length = (
            sum(self.document_lengths) / self.doc_count
            if self.doc_count
            else 0.0
        )
        self.average_length = max(self.average_length, 1.0)

        self.document_frequencies: Counter[str] = Counter()
        self.postings: dict[str, list[tuple[int, int]]] = defaultdict(list)

        for document_index, tokens in enumerate(self.tokenized_documents):
            frequencies = Counter(tokens)
            self.document_frequencies.update(frequencies.keys())

            for term, term_frequency in frequencies.items():
                self.postings[term].append(
                    (document_index, term_frequency)
                )

    @classmethod
    def from_json(
        cls,
        tree_path: str | Path = DEFAULT_LEGAL_TREE_PATH,
    ) -> "LegalBM25Index":
        """Cria o índice lendo a árvore jurídica original."""

        return cls(load_legal_documents(tree_path))

    def search(
        self,
        query: str,
        *,
        top_k: int = 120,
    ) -> list[tuple[float, Document]]:
        """Retorna os documentos lexicalmente mais relevantes.

        A estatística IDF, o comprimento médio e as frequências são calculados
        sobre todo o corpus (e não somente sobre candidatos semânticos).
        """

        if not isinstance(query, str) or not query.strip():
            raise ValueError("A consulta BM25 não pode estar vazia.")
        if top_k <= 0:
            raise ValueError("top_k precisa ser maior que zero.")

        query_terms = set(tokenize(query))
        if not query_terms:
            return []

        scores: dict[int, float] = defaultdict(float)

        for term in query_terms:
            postings = self.postings.get(term)
            if not postings:
                continue

            document_frequency = self.document_frequencies[term]
            inverse_document_frequency = log(
                1.0
                + (self.doc_count - document_frequency + 0.5)
                / (document_frequency + 0.5)
            )

            for document_index, term_frequency in postings:
                document_length = self.document_lengths[document_index]
                denominator = term_frequency + self.k1 * (
                    1.0
                    - self.b
                    + self.b * document_length / self.average_length
                )
                scores[document_index] += inverse_document_frequency * (
                    term_frequency * (self.k1 + 1.0)
                ) / denominator

        ranked = sorted(
            scores.items(),
            key=lambda item: (-item[1], item[0]),
        )

        return [
            (score, self.documents[index])
            for index, score in ranked[:top_k]
            if score > 0
        ]


@lru_cache(maxsize=4)
def _load_cached_index(
    path_string: str,
    modified_ns: int,
    file_size: int,
) -> LegalBM25Index:
    """Cacheia o índice por caminho e versão do arquivo."""

    del modified_ns, file_size  # fazem parte da chave de cache
    return LegalBM25Index.from_json(path_string)


def load_legal_bm25_index(
    tree_path: str | Path = DEFAULT_LEGAL_TREE_PATH,
) -> LegalBM25Index:
    """Carrega o índice uma vez por versão da árvore jurídica."""

    path = Path(tree_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(
            f"Árvore jurídica não encontrada: {path}. "
            "Execute a indexação da Constituição antes de iniciar o retriever."
        )

    stat = path.stat()
    return _load_cached_index(
        str(path),
        stat.st_mtime_ns,
        stat.st_size,
    )
