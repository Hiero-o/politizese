
import re
import unicodedata
from collections import Counter
from math import isfinite, log
from typing import Any, Literal

from langchain_core.callbacks.manager import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import ConfigDict, Field

from src.core.config import Settings
from src.rag.vector_store import create_vector_store


DEFAULT_TOP_K = 4
DEFAULT_CANDIDATE_K = 24

# Parâmetros do BM25.
BM25_K1 = 1.5
BM25_B = 0.75

# Peso da busca semântica na combinação final.
DEFAULT_SEMANTIC_WEIGHT = 0.75


STOPWORDS = {
    "",
    "a", "as", "o", "os",
    "um", "uma", "uns", "umas",
    "de", "da", "das", "do", "dos",
    "em", "no", "na", "nos", "nas",
    "ao", "aos", "à", "às",
    "e", "ou",
    "com", "por", "para", "pelo", "pela",
    "pelos", "pelas",
    "que", "qual", "quais",
    "quem", "quando", "onde",
    "como", "quanto", "quanta", "quantos", "quantas",
    "se", "sua", "suas", "seu", "seus",
    "meu", "minha", "meus", "minhas",
    "esse", "essa", "esses", "essas",
    "este", "esta", "estes", "estas",
    "aquele", "aquela", "aqueles", "aquelas",
    "ele", "ela", "eles", "elas",
    "eu", "tu", "nos", "vos",
    "tambem", "ja", "ainda", "muito", "muita",
    "muitos", "muitas",
}

# Não removemos palavras como "não", "nunca", "sem" e "exceto".
# Elas podem alterar completamente o sentido de uma pergunta.


def _normalize_text(text: str) -> str:
    """Normaliza texto, removendo acentos e diferenças entre maiúsculas/minúsculas."""

    normalized = unicodedata.normalize("NFKD", text.casefold())

    return "".join(
        char
        for char in normalized
        if not unicodedata.combining(char)
    )


def _tokenize(text: str) -> list[str]:
    """Divide um texto normalizado em tokens."""

    normalized = _normalize_text(text)
    tokens = re.findall(r"[a-z0-9]+", normalized)

    return [
        token
        for token in tokens
        if token not in STOPWORDS
    ]


def _calculate_bm25_scores(
    query: str,
    documents: list[Document],
) -> list[float]:
    """Calcula a relevância lexical dos documentos usando BM25."""

    query_tokens = set(_tokenize(query))

    if not query_tokens or not documents:
        return [0.0] * len(documents)

    tokenized_documents = [
        _tokenize(document.page_content)
        for document in documents
    ]

    document_lengths = [
        len(tokens)
        for tokens in tokenized_documents
    ]

    total_documents = len(documents)
    average_length = (
        sum(document_lengths) / total_documents
        if total_documents > 0
        else 0.0
    )

    average_length = max(average_length, 1.0)

    term_frequencies = [
        Counter(tokens)
        for tokens in tokenized_documents
    ]

    document_frequencies = Counter(
        token
        for tokens in tokenized_documents
        for token in set(tokens)
    )

    scores = [0.0] * total_documents

    for term in query_tokens:
        document_frequency = document_frequencies.get(term, 0)

        if document_frequency == 0:
            continue

        inverse_document_frequency = log(
            1
            + (
                total_documents - document_frequency + 0.5
            )
            / (
                document_frequency + 0.5
            )
        )

        for index in range(total_documents):
            term_frequency = term_frequencies[index].get(term, 0)

            if term_frequency == 0:
                continue

            document_length = document_lengths[index]

            denominator = term_frequency + BM25_K1 * (
                1
                - BM25_B
                + BM25_B * (document_length / average_length)
            )

            score = inverse_document_frequency * (
                (term_frequency * (BM25_K1 + 1))
                / denominator
            )

            scores[index] += score

    return scores


class PolitizeseRetriever(BaseRetriever):
    """Retriever híbrido que combina busca semântica e lexical."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    vector_store: Any = Field(exclude=True, repr=False)

    k: int = DEFAULT_TOP_K
    candidate_k: int = DEFAULT_CANDIDATE_K

    semantic_weight: float = Field(
        default=DEFAULT_SEMANTIC_WEIGHT,
        ge=0.0,
        le=1.0,
    )

    def _get_relevant_documents(
        self,
        query: str,
        *,
        run_manager: CallbackManagerForRetrieverRun,
    ) -> list[Document]:
        """Recupera candidatos no ChromaDB e os reordena usando BM25."""

        if not isinstance(query, str) or not query.strip():
            raise ValueError("A pergunta de busca não pode estar vazia.")

        # 1. Recupera candidatos pela similaridade semântica.
        candidates = self.vector_store.similarity_search_with_relevance_scores(
            query,
            k=self.candidate_k,
        )

        if not candidates:
            return []

        documents: list[Document] = []
        semantic_scores: list[float] = []

        for document, score in candidates:
            if not document.page_content.strip():
                continue

            try:
                semantic_score = float(score)
            except (TypeError, ValueError):
                semantic_score = 0.0

            if not isfinite(semantic_score):
                semantic_score = 0.0

            # Mantém a pontuação no intervalo esperado de relevância.
            semantic_score = max(0.0, min(1.0, semantic_score))

            documents.append(document)
            semantic_scores.append(semantic_score)

        if not documents:
            return []

        # 2. Calcula a relevância lexical dos mesmos candidatos.
        lexical_scores = _calculate_bm25_scores(query, documents)

        maximum_lexical_score = max(lexical_scores, default=0.0)

        if maximum_lexical_score > 0:
            normalized_lexical_scores = [
                score / maximum_lexical_score
                for score in lexical_scores
            ]
        else:
            normalized_lexical_scores = [
                0.0
                for _ in lexical_scores
            ]

        # 3. Combina as pontuações semânticas e lexicais.
        lexical_weight = 1.0 - self.semantic_weight

        ranked_documents = []

        for index, document in enumerate(documents):
            combined_score = (
                self.semantic_weight * semantic_scores[index]
                + lexical_weight * normalized_lexical_scores[index]
            )

            ranked_documents.append(
                (combined_score, document)
            )

        ranked_documents.sort(
            key=lambda item: item[0],
            reverse=True,
        )

        # 4. Retorna somente os K documentos mais relevantes.
        return [
            document
            for _, document in ranked_documents[:self.k]
        ]


def create_retriever(
    provider: Literal["local", "cloud", "auto"] | None = None,
    k: int = DEFAULT_TOP_K,
    candidate_k: int = DEFAULT_CANDIDATE_K,
    settings: Settings | None = None,
) -> tuple[PolitizeseRetriever, str]:
    """Cria o retriever e inicializa o acesso ao ChromaDB."""

    if k <= 0:
        raise ValueError("O parâmetro k precisa ser maior que zero.")

    if candidate_k <= 0:
        raise ValueError("O parâmetro candidate_k precisa ser maior que zero.")

    if candidate_k < k:
        raise ValueError(
            "candidate_k não pode ser menor que k."
        )

    vector_store, selected_provider = create_vector_store(
        provider=provider,
        settings=settings,
    )

    retriever = PolitizeseRetriever(
        vector_store=vector_store,
        k=k,
        candidate_k=candidate_k,
    )

    return retriever, selected_provider
