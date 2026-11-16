import re
import unicodedata


SCOPE_TERMS = (
    # Política e administração pública
    "politica",
    "politico",
    "politica publica",
    "administracao publica",
    "governo",
    "governo federal",
    "governo estadual",
    "governo municipal",

    # Constituição e direitos
    "constituicao",
    "constitucional",
    "direito",
    "direitos fundamentais",
    "direitos sociais",
    "cidadania",
    "soberania",
    "nacionalidade",
    "extradicao",
    "extraditado",
    "brasileiros natos",
    "emenda constitucional",

    # Eleições e representantes
    "eleicao",
    "eleitoral",
    "voto",
    "titulo de eleitor",
    "candidato",
    "candidatura",
    "partido",
    "mandato",
    "presidente",
    "governador",
    "prefeito",
    "vereador",
    "deputado",
    "senador",
    "voto",
    "votos",

    # Instituições e poderes
    "congresso nacional",
    "camara dos deputados",
    "camara municipal",
    "senado federal",
    "poder executivo",
    "poder legislativo",
    "poder judiciario",
    "stf",
    "supremo tribunal federal",
    "tse",
    "justica eleitoral",
    "ministerio publico",
    "defensoria publica",

    # Serviços e interesse público
    "servico publico",
    "prefeitura",
    "servidor publico",
    "licitacao",
    "orcamento publico",
    "imposto",
    "tributo",
    "saude publica",
    "sus",
    "educacao publica",
    "transporte publico",
    "mobilidade urbana",
    "seguranca publica",
    "assistencia social",
    "beneficio social",
    "obra publica",
    "infraestrutura publica",
    "corrupcao",
    "transparencia publica",
)


def normalizar(texto: str) -> str:
    """Normaliza texto para comparação lexical."""

    texto = unicodedata.normalize("NFKD", texto.lower())

    texto = "".join(
        caractere
        for caractere in texto
        if not unicodedata.combining(caractere)
    )

    texto = re.sub(r"[^a-z0-9]+", " ", texto)

    return " ".join(texto.split())


def validate_scope(question: str) -> str | None:
    """
    Verifica se a pergunta apresenta algum indicador
    do domínio de atuação do Politizese.

    Retorna uma justificativa caso não identifique
    termos relacionados ao escopo.
    """

    if not isinstance(question, str):
        raise TypeError("A pergunta precisa ser uma string.")

    normalized_question = normalizar(question)

    if not normalized_question:
        return "A pergunta está vazia."

    padded_question = f" {normalized_question} "

    for term in SCOPE_TERMS:
        normalized_term = normalizar(term)

        if f" {normalized_term} " in padded_question:
            return None

    return (
        "A pergunta aparentemente está fora do escopo do Politizese. O assistente é dedicado a política, administração pública e assuntos de interesse coletivo."
    )