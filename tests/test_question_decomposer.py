
import pytest

from src.rag.question_decomposer import (
    QuestionDecomposer,
    QuestionDecompositionError,
)
from src.schemas.question_decomposition import (
    QuestionDecompositionOutput,
    QuestionDecompositionResult,
)


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


def simple_payload():
    return {
        "is_compound": False,
        "subquestions": [
            {
                "question": "Como é composto o Congresso Nacional?",
                "focus": "Composição institucional.",
            }
        ],
        "decomposition_reason": (
            "A pergunta apresenta uma única necessidade informacional."
        ),
    }


def compound_payload():
    return {
        "is_compound": True,
        "subquestions": [
            {
                "question": (
                    "Quais são as condições gerais de elegibilidade "
                    "previstas na Constituição?"
                ),
                "focus": "Condições gerais de elegibilidade.",
            },
            {
                "question": (
                    "Quais requisitos de nacionalidade se aplicam "
                    "à candidatura à Presidência da República?"
                ),
                "focus": "Nacionalidade para candidatura presidencial.",
            },
            {
                "question": (
                    "Qual é a idade mínima exigida para concorrer "
                    "à Presidência da República?"
                ),
                "focus": "Idade mínima para candidatura presidencial.",
            },
        ],
        "decomposition_reason": (
            "A pergunta envolve condições gerais e requisitos "
            "específicos que exigem evidências distintas."
        ),
    }


def test_decompose_preserves_original_question():
    question = "Como é composto o Congresso Nacional?"

    decomposer = QuestionDecomposer(
        FakeChain(simple_payload())
    )

    result = decomposer.decompose(question)

    assert isinstance(result, QuestionDecompositionResult)
    assert result.original_question == question
    assert result.is_compound is False
    assert len(result.subquestions) == 1
    assert result.subquestions[0].question == question


def test_decompose_identifies_multiple_information_needs():
    question = (
        "Quais são os requisitos para se candidatar à Presidência "
        "e qual é a duração do mandato presidencial?"
    )

    decomposer = QuestionDecomposer(
        FakeChain(compound_payload())
    )

    result = decomposer.decompose(question)

    assert result.is_compound is True
    assert len(result.subquestions) == 3
    assert result.subquestions[0].focus
    assert result.subquestions[1].focus
    assert result.subquestions[2].focus


def test_decompose_rejects_empty_question():
    decomposer = QuestionDecomposer(
        FakeChain(simple_payload())
    )

    with pytest.raises(
        ValueError,
        match="não pode estar vazia",
    ):
        decomposer.decompose("   ")


def test_decompose_rejects_non_string_question():
    decomposer = QuestionDecomposer(
        FakeChain(simple_payload())
    )

    with pytest.raises(
        TypeError,
        match="string",
    ):
        decomposer.decompose(123)


def test_decompose_rejects_oversized_question():
    decomposer = QuestionDecomposer(
        FakeChain(simple_payload())
    )

    with pytest.raises(
        ValueError,
        match="excede o limite",
    ):
        decomposer.decompose("a" * 2001)


def test_decompose_rejects_invalid_model_output():
    decomposer = QuestionDecomposer(
        FakeChain(
            {
                "is_compound": True,
                "subquestions": [],
                "decomposition_reason": "Inválido.",
            }
        )
    )

    with pytest.raises(
        QuestionDecompositionError,
        match="schema esperado",
    ):
        decomposer.decompose(
            "Como é composto o Congresso Nacional?"
        )


def test_decompose_wraps_model_errors():
    decomposer = QuestionDecomposer(
        FakeChain(
            error=RuntimeError("Ollama indisponível")
        )
    )

    with pytest.raises(
        QuestionDecompositionError,
        match="modelo configurado",
    ):
        decomposer.decompose(
            "Como é composto o Congresso Nacional?"
        )


def test_schema_rejects_duplicate_subquestions():
    payload = compound_payload()

    payload["subquestions"][1]["question"] = (
        payload["subquestions"][0]["question"]
    )

    with pytest.raises(ValueError, match="duplicadas"):
        QuestionDecompositionOutput.model_validate(payload)


def test_schema_rejects_simple_question_with_multiple_parts():
    payload = simple_payload()

    payload["subquestions"].append(
        {
            "question": "Qual é a duração do mandato presidencial?",
            "focus": "Duração do mandato.",
        }
    )

    with pytest.raises(
        ValueError,
        match="pergunta simples",
    ):
        QuestionDecompositionOutput.model_validate(payload)
