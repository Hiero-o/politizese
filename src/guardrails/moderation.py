import re


EMAIL_PATTERN = re.compile(
    r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b"
)

CPF_PATTERN = re.compile(
    r"(?<!\d)\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?!\d)"
)

PHONE_PATTERN = re.compile(
    r"(?<!\d)(?:\+?55\s*)?\(?[1-9]\d\)?\s*"
    r"9?\d{4}[-\s]?\d{4}(?!\d)"
)


def personal_data_block_reason(text: str) -> str | None:
    """Identifica CPF, telefone e e-mail na pergunta."""

    if not isinstance(text, str):
        raise TypeError("A entrada precisa ser uma string.")

    if EMAIL_PATTERN.search(text):
        return "A entrada contém um possível endereço de e-mail."

    if CPF_PATTERN.search(text):
        return "A entrada contém um possível CPF."

    if PHONE_PATTERN.search(text):
        return "A entrada contém um possível telefone."

    return None




def pcp_block_reason(text: str) -> str | None:
    """
    Identifica entradas que devem ser bloqueadas
    segundo a regra da disciplina PCP.
    """

    if not isinstance(text, str):
        raise TypeError("A entrada precisa ser uma string.")

    if "@" in text:
        return "A entrada contém o caractere @."

    digit_count = sum(
        character.isdigit()
        for character in text
    )

    if digit_count >= 8:
        return "A entrada contém oito ou mais dígitos."

    return None