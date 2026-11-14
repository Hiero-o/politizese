
from types import SimpleNamespace

import pytest
from langchain_core.documents import Document

from src.rag.iterative_retriever import (
    PolitizeseIterativeRetriever,
)


class FakeDecomposer:
    def __init__(self, is_compound, subquestions):
        self.is_compound = is_compound
        self.subquestions = subquestions
        self.calls = []

    def decompose(self, question):
        self.calls.append(question)

        return SimpleNamespace(
            original_question=question,
            is_compound=self.is_compound,
            decomposition_reason="Decomposição simulada.",
            subquestions=self.subquestions,
        )


class FakeRewriter:
    def __init__(self):
        self.calls = []

    def rewrite(self, question):
        self.calls.append(question)

        return SimpleNamespace(
            semantic_query=f"semantic::{question}",
            lexical_query=f"lexical::{question}",
        )


class FakeBaseRetriever:
    def __init__(self, results_by_semantic_query):
        self.results_by_semantic_query = results_by_semantic_query
        self.calls = []
        self.k = 48

    def search_with_queries(
        self,
        semantic_query,
        lexical_query,
    ):
        self.calls.append(
            {
                "semantic_query": semantic_query,
                "lexical_query": lexical_query,
            }
        )

        return self.results_by_semantic_query.get(
            semantic_query,
            [],
        )


def make_document(identifier, text):
    return Document(
        page_content=text,
        metadata={
            "source_node_id": identifier,
            "retrieval_sources": ["semantic", "lexical"],
        },
    )


def make_subquestion(question, focus):
    return SimpleNamespace(
        question=question,
        focus=focus,
    )


def test_compound_question_runs_one_search_per_subquestion():
    decomposer = FakeDecomposer(
        is_compound=True,
        subquestions=[
            make_subquestion(
                "Quais são as condições gerais de elegibilidade?",
                "Elegibilidade geral",
            ),
            make_subquestion(
                "Qual é o requisito específico de nacionalidade?",
                "Nacionalidade específica",
            ),
        ],
    )

    rewriter = FakeRewriter()

    retriever = FakeBaseRetriever(
        {
            "semantic::Quais são as condições gerais de elegibilidade?": [
                make_document("DOC-A", "Texto A"),
            ],
            "semantic::Qual é o requisito específico de nacionalidade?": [
                make_document("DOC-B", "Texto B"),
            ],
        }
    )

    pipeline = PolitizeseIterativeRetriever(
        base_retriever=retriever,
        decomposer=decomposer,
        rewriter=rewriter,
        top_k=48,
        rrf_constant=60,
    )

    result = pipeline.retrieve_with_trace(
        "Quais são os requisitos para a Presidência?"
    )

    assert len(retriever.calls) == 2
    assert len(rewriter.calls) == 2
    assert len(result.trace.subqueries) == 2
    assert len(result.documents) == 2


def test_duplicate_documents_are_fused_and_traced():
    decomposer = FakeDecomposer(
        is_compound=True,
        subquestions=[
            make_subquestion("Pergunta A?", "Foco A"),
            make_subquestion("Pergunta B?", "Foco B"),
        ],
    )

    rewriter = FakeRewriter()

    retriever = FakeBaseRetriever(
        {
            "semantic::Pergunta A?": [
                make_document("DOC-A", "Texto A"),
                make_document("DOC-B", "Texto B"),
            ],
            "semantic::Pergunta B?": [
                make_document("DOC-B", "Texto B"),
                make_document("DOC-C", "Texto C"),
            ],
        }
    )

    pipeline = PolitizeseIterativeRetriever(
        base_retriever=retriever,
        decomposer=decomposer,
        rewriter=rewriter,
        top_k=48,
        rrf_constant=60,
    )

    result = pipeline.retrieve_with_trace("Pergunta composta?")

    identifiers = [
        document.metadata["source_node_id"]
        for document in result.documents
    ]

    assert len(identifiers) == 3
    assert len(set(identifiers)) == 3

    # DOC-B apareceu em primeiro lugar em uma busca
    # e também em segundo lugar na outra.
    assert identifiers[0] == "DOC-B"

    document_b = result.documents[0]

    assert document_b.metadata["matched_subquestion_count"] == 2
    assert len(document_b.metadata["matched_subquestions"]) == 2


def test_simple_question_runs_only_one_search():
    question = "Como é composto o Congresso Nacional?"

    decomposer = FakeDecomposer(
        is_compound=False,
        subquestions=[
            make_subquestion(
                question,
                "Composição do Congresso Nacional",
            )
        ],
    )

    rewriter = FakeRewriter()

    retriever = FakeBaseRetriever(
        {
            f"semantic::{question}": [
                make_document("ART-44", "Texto do artigo 44."),
            ]
        }
    )

    pipeline = PolitizeseIterativeRetriever(
        base_retriever=retriever,
        decomposer=decomposer,
        rewriter=rewriter,
    )

    result = pipeline.retrieve_with_trace(question)

    assert len(result.trace.subqueries) == 1
    assert len(retriever.calls) == 1
    assert retriever.calls[0]["lexical_query"] == (
        f"lexical::{question}"
    )


def test_original_question_is_preserved_in_document_metadata():
    question = "Como é composto o Congresso Nacional?"

    pipeline = PolitizeseIterativeRetriever(
        base_retriever=FakeBaseRetriever(
            {
                f"semantic::{question}": [
                    make_document("ART-44", "Texto do artigo 44."),
                ]
            }
        ),
        decomposer=FakeDecomposer(
            is_compound=False,
            subquestions=[
                make_subquestion(question, "Composição")
            ],
        ),
        rewriter=FakeRewriter(),
    )

    result = pipeline.retrieve_with_trace(question)

    assert result.documents[0].metadata["original_question"] == question
    assert (
        result.documents[0].metadata["decomposition_is_compound"]
        is False
    )


def test_rejects_empty_question():
    pipeline = PolitizeseIterativeRetriever(
        base_retriever=FakeBaseRetriever({}),
        decomposer=FakeDecomposer(False, []),
        rewriter=FakeRewriter(),
    )

    with pytest.raises(ValueError, match="não pode estar vazia"):
        pipeline.retrieve_with_trace("   ")


def test_rejects_non_string_question():
    pipeline = PolitizeseIterativeRetriever(
        base_retriever=FakeBaseRetriever({}),
        decomposer=FakeDecomposer(False, []),
        rewriter=FakeRewriter(),
    )

    with pytest.raises(TypeError, match="string"):
        pipeline.retrieve_with_trace(123)
