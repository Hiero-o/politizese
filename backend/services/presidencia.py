from backend.schemas.politicos import PoliticoResumo


# FONTES OFICIAIS

FONTE_INSTITUCIONAL = (
    "https://www.gov.br/planalto/pt-br/"
    "acesso-a-informacao/institucional"
)

FONTE_ELEITORAL = (
    "https://www.tse.jus.br/comunicacao/noticias/2026/"
    "Outubro/presidente-do-tse-anuncia-reeleicao-de-lula"
)


# AUTORIDADES DA PRESIDÊNCIA

def listar_autoridades_presidenciais() -> list[PoliticoResumo]:

    autoridades = [
        PoliticoResumo(
            id="planalto-presidente",
            id_origem="presidente-da-republica",
            fonte="planalto",

            nome="Luiz Inácio Lula da Silva",
            cargo="Presidente da República",
            cargo_slug="presidente",

            partido="PT",

            situacao="Em exercício; reeleito para 2027–2030",
            mandato=(
                "2023–2026; próximo mandato 2027–2030"
            ),

            fonte_url=FONTE_INSTITUCIONAL,
        ),

        PoliticoResumo(
            id="planalto-vice-presidente",
            id_origem="vice-presidente-da-republica",
            fonte="planalto",

            nome="Geraldo José Rodrigues Alckmin Filho",
            cargo="Vice-presidente da República",
            cargo_slug="vice_presidente",

            partido="PSB",

            situacao="Em exercício; eleito para 2027–2030",
            mandato=(
                "2023–2026; próximo mandato 2027–2030"
            ),

            fonte_url=FONTE_INSTITUCIONAL,
        ),
    ]

    return autoridades