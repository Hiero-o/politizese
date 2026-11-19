import pytest

from src.guardrails.scope_validator import is_greeting, validate_scope


@pytest.mark.parametrize(
    "question",
    [
        "Quais são os senadores do estado de São Paulo?",
        "Quais são os fundamentos da República Federativa do Brasil?",
        "Quem é o atual presidente do Brasil?",
        "Quem são os vereadores de São Paulo?",
        "Como funciona a Constituição Federal?",
    ],
)
def test_accepts_politics_and_constitution_questions(question):
    assert validate_scope(question) is None


@pytest.mark.parametrize("question", ["oiee", "Olá!", "Bom dia", "e aí, tudo bem?"])
def test_accepts_greetings(question):
    assert is_greeting(question) is True
    assert validate_scope(question) is None


def test_rejects_unrelated_question():
    assert validate_scope("Me ensina uma receita de bolo?") is not None


def test_greeting_with_real_question_is_not_only_greeting():
    assert is_greeting("Oi, quem são os senadores de SP?") is False
