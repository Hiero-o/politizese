
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import (
    Field,
    SecretStr,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

# Raiz do projeto:
# src/core/config.py -> projeto/

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """
    Centraliza as configurações da aplicação.

    As configurações podem ser definidas no arquivo .env
    ou através de variáveis de ambiente do sistema.
    """

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Aplicação

    app_name: str = "Politize-se AI"

    environment: Literal[
        "development",
        "testing",
        "production",
    ] = "development"

    # Ollama

    ollama_provider: Literal["local", "cloud"] = "local"

    ollama_local_base_url: str = "http://localhost:11434"

    ollama_cloud_base_url: str = "https://ollama.com"

    ollama_api_key: SecretStr | None = None

    # Modelos de linguagem

    llm_model: str = "gemma4:31b"

    llm_temperature: float = Field(
        default=0.3,
        ge=0,
        le=2,
    )

    llm_top_p: float = Field(
        default=0.9,
        gt=0,
        le=1,
    )

    llm_num_predict: int = Field(
        default=1200,
        gt=0,
    )

    # Prompt

    system_prompt_file: str = "system_prompt_v1.md"

    # Embeddings

    rag_embedding_provider: Literal[
        "local",
        "cloud",
        "auto",
    ] = "auto"

    rag_embedding_model: str = "nomic-embed-text"

    # ChromaDB

    chroma_persist_directory: Path = Field(
        default_factory=lambda: PROJECT_ROOT / "data" / "chroma_db"
    )

    chroma_collection_prefix: str = "politizese"

    # Documentos

    documents_directory: Path = Field(
        default_factory=lambda: PROJECT_ROOT / "knowledge"
    )

    # Validadores

    @field_validator("ollama_api_key", mode="before")
    @classmethod
    def empty_api_key_to_none(cls, value):
        if value is None:
            return None

        if isinstance(value, str) and not value.strip():
            return None

        return value

    @model_validator(mode="after")
    def validate_cloud_configuration(self):
        if (
            self.ollama_provider == "cloud"
            and self.ollama_api_key is None
        ):
            raise ValueError(
                "OLLAMA_API_KEY é obrigatória "
                "quando OLLAMA_PROVIDER=cloud."
            )

        return self

    @field_validator(
        "chroma_persist_directory",
        "documents_directory",
        mode="after",
    )
    @classmethod
    def resolve_project_paths(cls, path: Path) -> Path:
        if not path.is_absolute():
            return (PROJECT_ROOT / path).resolve()

        return path.resolve()

    # Propriedades calculadas

    @property
    def ollama_base_url(self) -> str:
        """Retorna a URL correspondente ao provedor selecionado."""

        if self.ollama_provider == "cloud":
            return self.ollama_cloud_base_url

        return self.ollama_local_base_url

    @property
    def system_prompt_path(self) -> Path:
        """Retorna o caminho completo do prompt principal."""

        return PROJECT_ROOT / "prompts" / self.system_prompt_file


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Retorna uma única instância das configurações.

    Evita carregar e validar o arquivo .env
    repetidamente durante a execução.
    """

    return Settings()
