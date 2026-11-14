
import json
from types import SimpleNamespace

import pytest
from langchain_core.documents import Document
from pydantic import ValidationError

from src.agents.tools import PolitizeseToolbox
from src.agents.tool_schemas import VotingThresholdInput


class FakeRewriter:
    def rewrite(self, question):
        return SimpleNamespace(
            semantic_query=f"semantic::{question}",
            lexical_query=f"lexical::{question}",
        )


class FakeBaseRetriever:
    def __init__(self, documents=None, error=None):
        self.documents = documents or []
        self.error = error
        self.last_queries = None

    def search_with_queries(
        self,
        semantic_query,
        lexical_query,
    ):
        self.last_queries = (
            semantic_query,
            lexical_query,
        )

        if self.error:
            raise self.error

        return self.documents


class FakePipeline:
    def __init__(self, documents=None, error=None):
        self.base_retriever = FakeBaseRetriever(
            documents=documents,
            error=error,
        )

        self.rewriter = FakeRewriter()
        self.error = error

    def retrieve_with_trace(self, question):
        if self.error:
            raise self.error

        return SimpleNamespace(
            trace=SimpleNamespace(
                original_question=question,
                is_compound=True,
                decomposition_reason="Duas necessidades independentes.",
                subqueries=[
                    SimpleNamespace(
                        index=1,
                        question="Qual é a regra geral?",
                        focus="Regra geral",
                        semantic_query="Regra geral",
                        lexical_query="regra; geral",
                        retrieved_count=2,
                    ),
                    SimpleNamespace(
                        index=2,
                        question="Qual é a regra específica?",
                        focus="Regra específica",
                        semantic_query="Regra específica",
                        lexical_query="regra; específica",
                        retrieved_count=2,
                    ),
                ],
            ),
            documents=[
                Document(
                    page_content="Texto constitucional de teste.",
                    metadata={
                        "source_node_id": "CF1988-ART-0001-CAPUT",
                        "retrieval_sources": ["semantic", "lexical"],
                    },
                )
            ],
        )


def create_toolbox(documents=None, error=None):
    pipeline = FakePipeline(
        documents=documents,
        error=error,
    )

    return PolitizeseToolbox(pipeline), pipeline


def test_toolbox_exposes_three_tools():
    toolbox, _ = create_toolbox()

    names = {
        tool.name
        for tool in toolbox.tools
    }

    assert names == {
        "search_constitution",
        "search_constitution_decomposed",
        "calculate_voting_threshold",
    }


def test_search_constitution_uses_rewritten_queries():
    document = Document(
        page_content="O Congresso Nacional é composto por duas Casas.",
        metadata={
            "source_node_id": "CF1988-ART-0044-CAPUT",
            "retrieval_sources": ["semantic", "lexical"],
        },
    )

    toolbox, pipeline = create_toolbox(
        documents=[document]
    )

    tool = toolbox.tool_map["search_constitution"]

    raw = tool.invoke(
        {
            "question": "Como é composto o Congresso Nacional?"
        }
    )

    result = json.loads(raw)

    assert result["ok"] is True
    assert result["strategy"] == "query_rewriter_hybrid"

    assert pipeline.base_retriever.last_queries == (
        "semantic::Como é composto o Congresso Nacional?",
        "lexical::Como é composto o Congresso Nacional?",
    )

    assert result["documents"][0]["doc_id"] == (
        "CF1988-ART-0044-CAPUT"
    )


def test_search_constitution_decomposed_returns_trace():
    toolbox, _ = create_toolbox()

    tool = toolbox.tool_map[
        "search_constitution_decomposed"
    ]

    raw = tool.invoke(
        {
            "question": (
                "Pergunta com duas necessidades informacionais?"
            )
        }
    )

    result = json.loads(raw)

    assert result["ok"] is True
    assert result["is_compound"] is True
    assert len(result["subquestions"]) == 2
    assert result["documents"][0]["doc_id"] == (
        "CF1988-ART-0001-CAPUT"
    )


def test_calculate_voting_threshold_three_fifths_of_513():
    toolbox, _ = create_toolbox()

    tool = toolbox.tool_map[
        "calculate_voting_threshold"
    ]

    raw = tool.invoke(
        {
            "total_members": 513,
            "numerator": 3,
            "denominator": 5,
        }
    )

    result = json.loads(raw)

    assert result["ok"] is True
    assert result["minimum_required"] == 308
    assert result["fraction"] == "3/5"


def test_calculate_strictly_greater_than_half():
    toolbox, _ = create_toolbox()

    tool = toolbox.tool_map[
        "calculate_voting_threshold"
    ]

    raw = tool.invoke(
        {
            "total_members": 513,
            "numerator": 1,
            "denominator": 2,
            "strictly_greater": True,
        }
    )

    result = json.loads(raw)

    assert result["minimum_required"] == 257
    assert result["comparison"] == ">"


def test_calculator_rejects_invalid_fraction():
    with pytest.raises(ValidationError):
        VotingThresholdInput(
            total_members=513,
            numerator=3,
            denominator=0,
        )


def test_search_error_is_returned_as_controlled_observation():
    toolbox, _ = create_toolbox(
        error=RuntimeError("ChromaDB indisponível")
    )

    tool = toolbox.tool_map["search_constitution"]

    raw = tool.invoke(
        {
            "question": "Como é composto o Congresso Nacional?"
        }
    )

    result = json.loads(raw)

    assert result["ok"] is False
    assert result["tool"] == "search_constitution"
    assert result["error"]["type"] == "RuntimeError"


def test_calculator_error_is_controlled():
    toolbox, _ = create_toolbox()

    raw = toolbox.calculate_voting_threshold(
        total_members=513,
        numerator=3,
        denominator=0,
    )

    result = json.loads(raw)

    assert result["ok"] is False
    assert result["tool"] == "calculate_voting_threshold"


def test_search_rejects_invalid_input_schema():
    toolbox, _ = create_toolbox()

    tool = toolbox.tool_map["search_constitution"]

    with pytest.raises(Exception):
        tool.invoke({"question": ""})
