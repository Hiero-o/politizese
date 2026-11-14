
"""Schemas Pydantic para as ferramentas do agente Politizese."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
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
