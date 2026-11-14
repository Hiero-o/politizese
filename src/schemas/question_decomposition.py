
"""Schemas de entrada e saída para decomposição de perguntas do RAG."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


class SubQuestion(BaseModel):
    """Representa uma necessidade independente de recuperação."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    question: str = Field(
        min_length=5,
        max_length=500,
        description=(
            "Subpergunta independente, compreensível sem depender das demais subperguntas."
        ),
    )

    focus: str = Field(
        min_length=3,
        max_length=120,
        description=(
            "Descrição curta do aspecto informacional que essa subpergunta pretende recuperar."
        ),
    )

    @field_validator("question", "focus")
    @classmethod
    def validate_non_empty_text(cls, value: str) -> str:
        cleaned = value.strip()

        if not cleaned:
            raise ValueError("O campo não pode estar vazio.")

        return cleaned


class QuestionDecompositionOutput(BaseModel):
    """Saída estruturada produzida pelo Question Decomposer."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    is_compound: bool = Field(
        description=(
            "Indica se a pergunta exige a investigação de mais de uma necessidade informacional independente."
        ),
    )

    subquestions: list[SubQuestion] = Field(
        min_length=1,
        max_length=5,
        description=(
            "Lista ordenada de subperguntas necessárias para recuperar as evidências da pergunta original."
        ),
    )

    decomposition_reason: str = Field(
        min_length=3,
        max_length=240,
        description=(
            "Justificativa curta para manter a pergunta inteira ou dividi-la em subperguntas."
        ),
    )

    @field_validator("decomposition_reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        cleaned = value.strip()

        if not cleaned:
            raise ValueError(
                "A justificativa não pode estar vazia."
            )

        return cleaned

    @model_validator(mode="after")
    def validate_decomposition_consistency(self):
        count = len(self.subquestions)

        if not self.is_compound and count != 1:
            raise ValueError(
                "Uma pergunta simples precisa ter exatamente uma subpergunta."
            )

        if self.is_compound and count < 2:
            raise ValueError(
                "Uma pergunta composta precisa ter pelo menos duas subperguntas."
            )

        normalized_questions = [
            " ".join(item.question.casefold().split())
            for item in self.subquestions
        ]

        if len(normalized_questions) != len(set(normalized_questions)):
            raise ValueError(
                "A decomposição contém subperguntas duplicadas."
            )

        return self


class QuestionDecompositionResult(QuestionDecompositionOutput):
    """Resultado final com a pergunta original preservada pelo código."""

    original_question: str = Field(
        min_length=1,
        max_length=2000,
        description="Pergunta original do usuário.",
    )
