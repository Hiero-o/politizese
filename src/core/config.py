
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

    Permite configurar independentemente:
    - Assistente principal;
    - Gerador de índice semântico.
    """

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ==========================================
    # Aplicação
    # ==========================================

    app_name: str = "Politize-se AI"

    environment: Literal[
        "development",
        "testing",
        "production",
    ] = "development"

    # ==========================================
    # Ollama — conexão e autenticação
    # ==========================================

    ollama_provider: Literal["local", "cloud"] = "local"

    ollama_local_base_url: str = "http://localhost:11434"

    ollama_cloud_base_url: str = "https://ollama.com"

    ollama_api_key: SecretStr | None = None

    # ==========================================
    # Modelo principal — assistente
    # ==========================================

    llm_model: str = "gemma4:12b"

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
    
    semantic_index_num_ctx: int = Field(
        default=8192,
        gt=0,
    )   

    # ==========================================
    # Modelo auxiliar — índice semântico
    # ==========================================

    semantic_index_provider: Literal[
        "local",
        "cloud",
    ] = "local"

    semantic_index_model: str = "gemma4:12b"

    semantic_index_temperature: float = Field(
        default=0.1,
        ge=0,
        le=2,
    )

    semantic_index_top_p: float = Field(
        default=0.9,
        gt=0,
        le=1,
    )

    semantic_index_num_predict: int = Field(
        default=2048,
        gt=0,
    )

    # ==========================================
    # Prompt
    # ==========================================

    system_prompt_file: str = "system_prompt_v1.md"

    # ==========================================
    # Embeddings
    # ==========================================

    rag_embedding_provider: Literal[
        "local",
        "cloud",
        "auto",
    ] = "auto"

    rag_embedding_model: str = "nomic-embed-text"

    # ==========================================
    # ChromaDB
    # ==========================================

    chroma_persist_directory: Path = Field(
        default_factory=lambda: PROJECT_ROOT / "data" / "chroma_db"
    )

    chroma_collection_prefix: str = "politizese"

    # ==========================================
    # Documentos
    # ==========================================

    documents_directory: Path = Field(
        default_factory=lambda: PROJECT_ROOT / "knowledge"
    )

    # ==========================================
    # Validadores
    # ==========================================

    @field_validator("ollama_api_key", mode="before")
    @classmethod
    def empty_api_key_to_none(cls, value):
        """
        Converte uma chave vazia em None.

        Isso permite manter OLLAMA_API_KEY=
        quando nenhum modelo utiliza Cloud.
        """

        if value is None:
            return None

        if isinstance(value, str) and not value.strip():
            return None

        return value

    @model_validator(mode="after")
    def validate_cloud_configuration(self):
        """
        Exige a chave de API caso qualquer um dos
        modelos utilize Ollama Cloud.
        """

        cloud_is_used = (
            self.ollama_provider == "cloud"
            or self.semantic_index_provider == "cloud"
        )

        if cloud_is_used and self.ollama_api_key is None:
            raise ValueError(
                "OLLAMA_API_KEY é obrigatória quando "
                "OLLAMA_PROVIDER=cloud ou "
                "SEMANTIC_INDEX_PROVIDER=cloud."
            )

        return self

    @field_validator(
        "chroma_persist_directory",
        "documents_directory",
        mode="after",
    )
    @classmethod
    def resolve_project_paths(cls, path: Path) -> Path:
        """
        Converte caminhos relativos em caminhos absolutos
        a partir da raiz do projeto.
        """

        if not path.is_absolute():
            return (PROJECT_ROOT / path).resolve()

        return path.resolve()

    # ==========================================
    # Propriedades calculadas
    # ==========================================

    @property
    def ollama_base_url(self) -> str:
        """
        Retorna a URL correspondente ao provider
        do assistente principal.
        """

        if self.ollama_provider == "cloud":
            return self.ollama_cloud_base_url

        return self.ollama_local_base_url

    @property
    def semantic_index_base_url(self) -> str:
        """
        Retorna a URL correspondente ao provider
        do gerador de índice semântico.
        """

        if self.semantic_index_provider == "cloud":
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
