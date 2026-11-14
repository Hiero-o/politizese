"""Schemas de entrada e saída para reformulação de consultas do RAG."""

from pydantic import BaseModel, ConfigDict, Field, field_validator


class QueryRewriteOutput(BaseModel):
    """Saída estruturada produzida pelo modelo de reformulação."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    semantic_query: str = Field(
        min_length=5,
        max_length=600,
        description=(
            "Uma consulta em linguagem natural, clara e contextualizada, "
            "otimizada para recuperação semântica."
        ),
    )
    lexical_query: str = Field(
        min_length=2,
        max_length=800,
        description=(
            "Termos e expressões jurídicas relevantes, separados por ponto "
            "e vírgula, otimizados para busca lexical BM25."
        ),
    )
    key_terms: list[str] = Field(
        min_length=1,
        max_length=12,
        description=(
            "Lista de termos e expressões importantes que devem ser "
            "preservados durante a recuperação."
        ),
    )
    search_intent: str = Field(
        min_length=3,
        max_length=200,
        description="Descrição curta da intenção informacional da pergunta.",
    )

    @field_validator("semantic_query", "lexical_query", "search_intent")
    @classmethod
    def validate_non_empty_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("O campo não pode estar vazio.")
        return cleaned

    @field_validator("key_terms", mode="before")
    @classmethod
    def normalize_key_terms(cls, value):
        if isinstance(value, str):
            value = [value]

        if not isinstance(value, list):
            return value

        cleaned: list[str] = []
        seen: set[str] = set()

        for item in value:
            if not isinstance(item, str):
                return value

            term = item.strip()
            normalized = term.casefold()

            if term and normalized not in seen:
                cleaned.append(term)
                seen.add(normalized)

        return cleaned


class QueryRewriteResult(QueryRewriteOutput):
    """Resultado final, incluindo a pergunta original preservada pelo código."""

    original_question: str = Field(
        min_length=1,
        max_length=2000,
        description="Pergunta original do usuário, sem reformulação.",
    )
