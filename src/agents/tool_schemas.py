
"""Schemas Pydantic para as ferramentas do agente Politizese."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    field_validator,
    model_validator,
)


class ConstitutionSearchInput(BaseModel):
    """Entrada para pesquisa de informações constitucionais."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    question: str = Field(
        min_length=5,
        max_length=2000,
        description="Pergunta que será pesquisada na Constituição Federal.",
    )


class VotingThresholdInput(BaseModel):
    """Entrada para cálculo de um quórum ou fração de votação."""

    model_config = ConfigDict(extra="forbid")

    total_members: StrictInt = Field(
        gt=0,
        le=10_000_000,
        description=(
            "Quantidade total de integrantes considerada no cálculo. "
            "O valor precisa ser fornecido pela pergunta ou pelas evidências."
        ),
    )

    numerator: StrictInt = Field(
        gt=0,
        le=1_000_000,
        description="Numerador da fração do quórum.",
    )

    denominator: StrictInt = Field(
        gt=0,
        le=1_000_000,
        description="Denominador da fração do quórum.",
    )

    strictly_greater: bool = Field(
        default=False,
        description=(
            "Se verdadeiro, calcula o menor inteiro estritamente maior "
            "que a fração. Se falso, calcula o menor inteiro maior ou "
            "igual à fração."
        ),
    )

    @model_validator(mode="after")
    def validate_fraction(self):
        if self.numerator > self.denominator:
            raise ValueError(
                "O numerador não pode ser maior que o denominador."
            )

        return self


class PoliticoSearchInput(BaseModel):
    """Entrada para pesquisa no catálogo público do Politize-se."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    nome: str | None = Field(
        default=None,
        min_length=2,
        max_length=100,
        description="Nome completo ou parte do nome do político.",
    )

    cargo: str | None = Field(
        default=None,
        description=(
            "Cargo: presidente, vice_presidente, governador, senador, "
            "deputado_federal, deputado_estadual, deputado_distrital, "
            "prefeito ou vereador."
        ),
    )

    uf: str | None = Field(
        default=None,
        min_length=2,
        max_length=2,
        description="Sigla da unidade federativa, por exemplo SP ou RJ.",
    )

    municipio: str | None = Field(
        default=None,
        min_length=2,
        max_length=100,
        description="Nome do município, quando aplicável.",
    )

    partido: str | None = Field(
        default=None,
        min_length=2,
        max_length=20,
        description="Sigla do partido político.",
    )

    fase_mandato: str | None = Field(
        default=None,
        description=(
            "em_exercicio, eleito_futuro ou mandato_em_andamento."
        ),
    )

    limite: StrictInt = Field(
        default=5,
        ge=1,
        le=8,
        description="Quantidade máxima de registros a retornar (1 a 8).",
    )

    @field_validator("cargo", mode="before")
    @classmethod
    def normalize_office(cls, value):
        if value is None:
            return value
        import re
        import unicodedata

        raw = str(value).strip().casefold()
        normalized = unicodedata.normalize("NFKD", raw)
        normalized = "".join(
            char for char in normalized
            if not unicodedata.combining(char)
        )
        normalized = re.sub(r"[^a-z0-9]+", " ", normalized).strip()
        normalized = re.sub(r"\s+", " ", normalized)

        aliases = {
            "presidente": "presidente",
            "presidencia": "presidente",
            "vice presidente": "vice_presidente",
            "vice presidencia": "vice_presidente",
            "governador": "governador",
            "governadores": "governador",
            "senador": "senador",
            "senadores": "senador",
            "deputado federal": "deputado_federal",
            "deputados federais": "deputado_federal",
            "deputado_federal": "deputado_federal",
            "deputado estadual": "deputado_estadual",
            "deputados estaduais": "deputado_estadual",
            "deputado_estadual": "deputado_estadual",
            "deputado distrital": "deputado_distrital",
            "deputados distritais": "deputado_distrital",
            "deputado_distrital": "deputado_distrital",
            "prefeito": "prefeito",
            "prefeitos": "prefeito",
            "vereador": "vereador",
            "vereadores": "vereador",
        }
        return aliases.get(normalized, normalized.replace(" ", "_"))

    @field_validator("uf", mode="before")
    @classmethod
    def normalize_state(cls, value):
        if value is None:
            return value
        import re
        import unicodedata

        raw = str(value).strip().casefold()
        normalized = unicodedata.normalize("NFKD", raw)
        normalized = "".join(
            char for char in normalized
            if not unicodedata.combining(char)
        )
        normalized = re.sub(r"[^a-z0-9]+", " ", normalized).strip()

        states = {
            "acre": "AC", "alagoas": "AL", "amapa": "AP",
            "amazonas": "AM", "bahia": "BA", "ceara": "CE",
            "distrito federal": "DF", "espirito santo": "ES",
            "goias": "GO", "maranhao": "MA", "mato grosso": "MT",
            "mato grosso do sul": "MS", "minas gerais": "MG",
            "para": "PA", "paraiba": "PB", "parana": "PR",
            "pernambuco": "PE", "piaui": "PI",
            "rio de janeiro": "RJ", "rio grande do norte": "RN",
            "rio grande do sul": "RS", "rondonia": "RO",
            "roraima": "RR", "santa catarina": "SC",
            "sao paulo": "SP", "sergipe": "SE", "tocantins": "TO",
        }
        return states.get(normalized, normalized.upper())

    @field_validator("fase_mandato", mode="before")
    @classmethod
    def normalize_phase(cls, value):
        if value is None:
            return value
        import re
        import unicodedata

        raw = str(value).strip().casefold()
        normalized = unicodedata.normalize("NFKD", raw)
        normalized = "".join(
            char for char in normalized
            if not unicodedata.combining(char)
        )
        normalized = re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")
        aliases = {
            "em_exercicio": "em_exercicio",
            "atual": "em_exercicio",
            "atuais": "em_exercicio",
            "em_atividade": "em_exercicio",
            "eleito_futuro": "eleito_futuro",
            "eleito_para_proximo_mandato": "eleito_futuro",
            "mandato_em_andamento": "mandato_em_andamento",
        }
        return aliases.get(normalized, normalized)

    @model_validator(mode="after")
    def validate_search_filter(self):
        if not any((self.nome, self.cargo, self.partido)):
            raise ValueError(
                "Informe pelo menos nome, cargo ou partido para limitar a pesquisa."
            )

        if self.uf and len(self.uf.strip()) != 2:
            raise ValueError("A UF deve conter exatamente duas letras.")

        allowed_cargos = {
            "presidente",
            "vice_presidente",
            "governador",
            "senador",
            "deputado_federal",
            "deputado_estadual",
            "deputado_distrital",
            "prefeito",
            "vereador",
        }
        if self.cargo and self.cargo not in allowed_cargos:
            raise ValueError("Cargo inválido para consulta do catálogo.")

        allowed_phases = {
            "em_exercicio",
            "eleito_futuro",
            "mandato_em_andamento",
        }
        if self.fase_mandato and self.fase_mandato not in allowed_phases:
            raise ValueError("Fase de mandato inválida.")

        return self
