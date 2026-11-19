"""Guardrail lexical de escopo do assistente Politize-se."""

from __future__ import annotations

import re
import unicodedata


SCOPE_TERMS = (
    # Política e administração pública
    "politica", "politico", "politica publica", "administracao publica",
    "governo", "governo federal", "governo estadual", "governo municipal",
    "estado brasileiro", "republica", "republica federativa",
    "fundamento", "democracia", "federacao",

    # Constituição, direitos e legislação
    "constituicao", "constitucional", "direito", "direitos fundamentais",
    "direitos sociais", "cidadania", "soberania", "nacionalidade",
    "extradicao", "extraditado", "brasileiros natos",
    "emenda constitucional", "artigo", "artigos", "poder constituinte",
    "fundamento da republica", "fundamentos da republica",

    # Eleições e representantes
    "eleicao", "eleitoral", "voto", "titulo de eleitor", "candidato",
    "candidatura", "partido", "parlamentar", "representante politico",
    "representante publico", "mandatario", "mandato", "presidente",
    "vice presidente", "governador", "prefeito", "vereador", "deputado",
    "senador", "ministro", "congresso nacional", "camara dos deputados",
    "camara municipal", "senado federal",

    # Instituições e poderes
    "poder executivo", "poder legislativo", "poder judiciario", "stf",
    "supremo tribunal federal", "tse", "justica eleitoral",
    "ministerio publico", "defensoria publica",

    # Serviços e interesse público
    "servico publico", "prefeitura", "servidor publico", "licitacao",
    "orcamento publico", "imposto", "tributo", "saude publica", "sus",
    "educacao publica", "transporte publico", "mobilidade urbana",
    "seguranca publica", "assistencia social", "beneficio social",
    "obra publica", "infraestrutura publica", "corrupcao",
    "transparencia publica",
)

GREETINGS = {
    "oi", "ola", "oie", "oiee", "oieee", "opa", "e ai",
    "bom dia", "boa tarde", "boa noite", "tudo bem", "tudo bom",
    "oi tudo bem", "ola tudo bem", "oie tudo bem", "e ai tudo bem",
}


def normalizar(texto: str) -> str:
    """Remove acentos e pontuação e uniformiza espaços."""
    texto = unicodedata.normalize("NFKD", texto.casefold())
    texto = "".join(
        caractere for caractere in texto
        if not unicodedata.combining(caractere)
    )
    texto = re.sub(r"[^a-z0-9]+", " ", texto)
    return " ".join(texto.split())


def is_greeting(question: str) -> bool:
    """Identifica apenas saudações isoladas (não mensagens com pergunta)."""
    normalized = normalizar(question)
    if not normalized:
        return False
    if normalized in GREETINGS:
        return True
    # Permite saudações com pequenas interjeições, mas não uma pergunta
    # substantiva que venha depois da saudação.
    return bool(
        re.fullmatch(
            r"(?:oi+|ola+|oie+|opa+)(?: tudo bem| tudo bom)?[!.?]*",
            normalized,
        )
    )


def _matches_term(question_tokens: list[str], term: str) -> bool:
    """Compara termos aceitando plural e flexões simples no último token."""
    term_tokens = term.split()
    width = len(term_tokens)
    if width > len(question_tokens):
        return False

    for start in range(len(question_tokens) - width + 1):
        window = question_tokens[start:start + width]
        matched = True
        for index, (word, expected) in enumerate(zip(window, term_tokens)):
            # Flexão simples é aceita via prefixo (senador -> senadores;
            # deputado -> deputados; fundamento -> fundamentos).
            if index == width - 1:
                if not word.startswith(expected):
                    matched = False
                    break
            elif word != expected:
                matched = False
                break
        if matched:
            return True
    return False


def validate_scope(question: str) -> str | None:
    """Retorna None quando a pergunta pertence ao domínio do Politize-se."""
    if not isinstance(question, str):
        raise TypeError("A pergunta precisa ser uma string.")

    normalized_question = normalizar(question)
    if not normalized_question:
        return "A pergunta está vazia."

    if is_greeting(normalized_question):
        return None

    # Perguntas de identificação podem citar apenas o nome da pessoa.
    # A resposta ainda precisa ser confirmada pelo catálogo.
    if normalized_question.startswith(("quem e ", "quem foi ")):
        return None

    tokens = normalized_question.split()
    if any(_matches_term(tokens, normalizar(term)) for term in SCOPE_TERMS):
        return None

    return (
        "A pergunta aparentemente está fora do escopo do Politizese. "
        "O assistente é dedicado a política, administração pública e "
        "assuntos de interesse coletivo."
    )
