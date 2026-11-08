
import math
import warnings
from typing import Literal

from langchain_core.embeddings import Embeddings
from langchain_ollama import OllamaEmbeddings

from src.core.config import Settings, get_settings


PROBE_TEXT = "Teste de geração de embeddings do Politize-se."


class NomicTaskPrefixEmbeddings(Embeddings):
    """
    Adiciona os prefixos recomendados pelo Nomic.

    Documentos recebem:
        search_document:

    Consultas recebem:
        search_query:
    """

    def __init__(self, underlying: Embeddings) -> None:
        self._underlying = underlying

    def embed_documents(
        self,
        texts: list[str],
    ) -> list[list[float]]:

        prefixed_texts = [
            f"search_document: {text}"
            for text in texts
        ]

        return self._underlying.embed_documents(prefixed_texts)

    def embed_query(self, text: str) -> list[float]:
        prefixed_text = f"search_query: {text}"

        return self._underlying.embed_query(prefixed_text)


def _uses_nomic_prefixes(model_name: str) -> bool:
    """Verifica se o modelo utiliza os prefixos do Nomic."""

    base_name = model_name.lower().split(":")[0]

    return base_name in {
        "nomic-embed-text",
        "nomic-embed-text-v2-moe",
    }


def _create_and_validate(
    provider: Literal["local", "cloud"],
    settings: Settings,
) -> tuple[Embeddings, int]:
    """
    Cria os embeddings para o provedor selecionado
    e verifica se a geração de vetores funciona.

    Returns:
        Tupla contendo a instância de embeddings
        e a dimensão do vetor gerado.
    """

    # Seleciona o endereço do provedor.
    if provider == "cloud":
        base_url = settings.ollama_cloud_base_url
    else:
        base_url = settings.ollama_local_base_url

    # Configura os cabeçalhos de autenticação.
    client_kwargs = {}

    if provider == "cloud":

        if settings.ollama_api_key is None:
            raise ValueError(
                "OLLAMA_API_KEY é obrigatória "
                "para utilizar o Ollama Cloud."
            )

        api_key = settings.ollama_api_key.get_secret_value()

        client_kwargs = {
            "headers": {
                "Authorization": f"Bearer {api_key}"
            }
        }

    # Cria o cliente de embeddings.
    underlying = OllamaEmbeddings(
        model=settings.rag_embedding_model,
        base_url=base_url,
        client_kwargs=client_kwargs,
    )

    # Aplica a estratégia específica do modelo.
    if _uses_nomic_prefixes(settings.rag_embedding_model):

        embeddings: Embeddings = NomicTaskPrefixEmbeddings(
            underlying
        )

    else:
        embeddings = underlying

    # Testa a geração de um vetor.
    vector = embeddings.embed_query(PROBE_TEXT)

    if not vector:
        raise RuntimeError(
            f"O provedor {provider} retornou um vetor vazio."
        )

    if not all(
        isinstance(value, (int, float))
        and math.isfinite(value)
        for value in vector
    ):
        raise RuntimeError(
            f"O provedor {provider} retornou valores inválidos."
        )

    return embeddings, len(vector)


def create_embeddings(
    provider: Literal["local", "cloud", "auto"] | None = None,
    *,
    settings: Settings | None = None,
) -> tuple[Embeddings, str]:
    """
    Inicializa os embeddings utilizando as configurações centrais.

    Opções:
        local: utiliza o Ollama local.
        cloud: utiliza o Ollama Cloud.
        auto: tenta Cloud e utiliza local como fallback.

    Args:
        provider: permite sobrescrever o provedor definido no .env.
        settings: permite fornecer configurações específicas.

    Returns:
        Tupla contendo (embeddings, provedor selecionado).
    """

    if settings is None:
        settings = get_settings()

    selected_provider = (
        provider or settings.rag_embedding_provider
    ).strip().lower()

    if selected_provider not in {"local", "cloud", "auto"}:
        raise ValueError(
            "O provedor deve ser 'local', 'cloud' ou 'auto'."
        )

    if not settings.rag_embedding_model.strip():
        raise ValueError(
            "RAG_EMBEDDING_MODEL não pode estar vazio."
        )

    # Execução exclusivamente local.
    if selected_provider == "local":

        try:
            embeddings, dimension = _create_and_validate(
                "local",
                settings,
            )

        except Exception as error:
            raise RuntimeError(
                "Não foi possível inicializar os embeddings "
                "no Ollama local. Verifique o servidor e o modelo."
            ) from error

        return embeddings, "local"

    # Execução exclusivamente Cloud.
    if selected_provider == "cloud":

        if settings.ollama_api_key is None:
            raise RuntimeError(
                "OLLAMA_API_KEY não está configurada."
            )

        try:
            embeddings, dimension = _create_and_validate(
                "cloud",
                settings,
            )

        except Exception as error:
            raise RuntimeError(
                "Não foi possível inicializar os embeddings "
                "no Ollama Cloud."
            ) from error

        return embeddings, "cloud"

    # Modo automático.
    if settings.ollama_api_key is not None:

        try:
            embeddings, dimension = _create_and_validate(
                "cloud",
                settings,
            )

            return embeddings, "cloud"

        except Exception as error:
            warnings.warn(
                "Ollama Cloud indisponivel para embeddings "
                f"({type(error).__name__}); utilizando o local.",
                RuntimeWarning,
                stacklevel=2,
            )

    else:
        warnings.warn(
            "OLLAMA_API_KEY não configurada; "
            "utilizando embeddings locais.",
            RuntimeWarning,
            stacklevel=2,
        )

    # Fallback local.
    try:
        embeddings, dimension = _create_and_validate(
            "local",
            settings,
        )

    except Exception as error:
        raise RuntimeError(
            "Não foi possível inicializar os embeddings "
            "nem pelo Cloud nem pelo Ollama local."
        ) from error

    return embeddings, "local"
