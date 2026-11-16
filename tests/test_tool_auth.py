
import pytest

from src.agents.tool_authorization import (
    get_tool_authorization_error,
    is_explicit_voting_calculation_requested,
)


@pytest.mark.parametrize(
    "question",
    [
        "Quantos votos correspondem a três quintos de 513?",
        "Calcule a quantidade de votos para um quórum de 3/5.",
        "Qual é o número de votos necessário?",
        "Quanto é 3/5 de 513 votos?",
        "Execute os cálculos de quórum no Congresso Nacional.",
    ],
)
def test_explicit_calculation_is_authorized(question):
    assert is_explicit_voting_calculation_requested(question)


@pytest.mark.parametrize(
    "question",
    [
        "O que diz a Constituição sobre igualdade?",
        "Qual quórum a Constituição estabelece?",
        "Como funciona o Congresso Nacional?",
        "Não calcule quantos votos são necessários.",
    ],
)
def test_calculation_without_explicit_request_is_not_authorized(question):
    assert not is_explicit_voting_calculation_requested(question)


def test_calculator_is_blocked_without_calculation_intent():
    reason = get_tool_authorization_error(
        user_question=(
            "O que estabelece o artigo 5º sobre igualdade?"
        ),
        tool_name="calculate_voting_threshold",
    )

    assert reason is not None
    assert "não solicitou explicitamente" in reason


def test_calculator_is_authorized_for_explicit_request():
    reason = get_tool_authorization_error(
        user_question=(
            "Quantos votos correspondem a três quintos de 513?"
        ),
        tool_name="calculate_voting_threshold",
    )

    assert reason is None


def test_search_tool_is_not_blocked_by_calculation_policy():
    reason = get_tool_authorization_error(
        user_question="O que diz a Constituição sobre igualdade?",
        tool_name="search_constitution",
    )

    assert reason is None
