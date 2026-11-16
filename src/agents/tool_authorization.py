
import re
import unicodedata


CALCULATION_PATTERNS = (
    r"\bquantos\s+votos\b",
    r"\bquantidade\s+(?:minima\s+)?de\s+votos\b",
    r"\bnumero\s+de\s+votos\b",
    r"\bvotos\s+necessarios\b",
    r"\bquanto\s+(?:e|da|corresponde)\b.{0,60}\bvotos\b",
    (
        r"\b(?:calcule|calcular|calculo)\b.{0,60}"
        r"\b(?:quorum|votos|votacao|fracao)\b"
    ),
    (
        r"\b(?:calcule|calcular|calculos?)\b.{0,60}"
        r"\b(?:quorum|votos|votacao|fracao)\b"
    ),
)

NEGATION_PATTERNS = (
    r"\bnao\s+(?:calcule|calcular)\b",
    r"\bnao\s+(?:quero|preciso|necessito)\s+"
    r"(?:que\s+)?(?:voce\s+)?(?:calcule|calcular)\b",
    r"\bnao\s+quero\s+saber\s+quantos\s+votos\b",
)


def normalize_question(question: str) -> str:
    """Normaliza a pergunta para comparação lexical."""

    normalized = unicodedata.normalize(
        "NFKD",
        question.casefold(),
    )

    normalized = "".join(
        character
        for character in normalized
        if not unicodedata.combining(character)
    )

    return " ".join(normalized.split())


def is_explicit_voting_calculation_requested(
    question: str,
) -> bool:
    """
    Verifica se o usuário solicitou explicitamente
    um cálculo de votação ou quórum.
    """

    if not isinstance(question, str):
        raise TypeError("A pergunta precisa ser uma string.")

    normalized = normalize_question(question)

    if not normalized:
        return False

    if any(
        re.search(pattern, normalized)
        for pattern in NEGATION_PATTERNS
    ):
        return False

    return any(
        re.search(pattern, normalized)
        for pattern in CALCULATION_PATTERNS
    )


def get_tool_authorization_error(
    user_question: str,
    tool_name: str,
) -> str | None:
    """
    Retorna o motivo de bloqueio quando uma ferramenta
    não está autorizada pela intenção original do usuário.
    """

    if tool_name != "calculate_voting_threshold":
        return None

    if is_explicit_voting_calculation_requested(user_question):
        return None

    return (
        "A ferramenta de cálculo não está autorizada: "
        "a pergunta original não solicitou explicitamente "
        "um cálculo de votos ou quórum."
    )
