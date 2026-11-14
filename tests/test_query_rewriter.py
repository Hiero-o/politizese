import pytest

from src.rag.query_rewriter import QueryRewriteError, QueryRewriter
from src.schemas.query_rewrite import QueryRewriteOutput, QueryRewriteResult


class FakeChain:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.last_input = None

    def invoke(self, payload):
        self.last_input = payload
        if self.error is not None:
            raise self.error
        return self.result


def valid_payload():
    return {
        "semantic_query": (
            "Quais são as condições constitucionais de elegibilidade "
            "para Presidente da República?"
        ),
        "lexical_query": (
            "condições de elegibilidade; nacionalidade brasileira; "
            "idade mínima; Presidente da República"
        ),
        "key_terms": [
            "nacionalidade brasileira",
            "idade mínima",
            "Presidente da República",
        ],
        "search_intent": "Condições de elegibilidade presidencial.",
    }


def test_rewrite_preserves_original_question_and_returns_structured_result():
    chain = FakeChain(valid_payload())
    rewriter = QueryRewriter(chain)

    result = rewriter.rewrite(
        "  Quais são os requisitos para ser presidente?  "
    )

    assert result.original_question == (
        "Quais são os requisitos para ser presidente?"
    )
    assert result.semantic_query.startswith("Quais são as condições")
    assert "nacionalidade brasileira" in result.lexical_query
    assert isinstance(result, QueryRewriteResult)
    assert chain.last_input is not None
    assert "question_json" in chain.last_input


def test_rewrite_rejects_empty_question():
    rewriter = QueryRewriter(FakeChain(valid_payload()))

    with pytest.raises(ValueError, match="não pode estar vazia"):
        rewriter.rewrite("   ")


def test_rewrite_rejects_non_string_question():
    rewriter = QueryRewriter(FakeChain(valid_payload()))

    with pytest.raises(TypeError, match="string"):
        rewriter.rewrite(123)


def test_rewrite_rejects_invalid_model_output():
    rewriter = QueryRewriter(FakeChain({"semantic_query": "incompleto"}))

    with pytest.raises(QueryRewriteError, match="schema esperado"):
        rewriter.rewrite("Como é composto o Congresso Nacional?")


def test_rewrite_wraps_model_errors():
    rewriter = QueryRewriter(
        FakeChain(error=RuntimeError("Ollama indisponível"))
    )

    with pytest.raises(QueryRewriteError, match="modelo configurado"):
        rewriter.rewrite("Como é composto o Congresso Nacional?")


def test_key_terms_are_deduplicated_case_insensitively():
    payload = valid_payload()
    payload["key_terms"] = [
        "Senado Federal",
        "senado federal",
        "Câmara dos Deputados",
    ]

    result = QueryRewriteOutput.model_validate(payload)

    assert result.key_terms == [
        "Senado Federal",
        "Câmara dos Deputados",
    ]
