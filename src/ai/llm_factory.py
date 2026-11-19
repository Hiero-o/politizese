
from typing import Any, Literal

from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

from src.core.config import Settings, get_settings


OllamaProvider = Literal["local", "cloud"]


def _create_ollama_model(
    settings: Settings,
    provider: OllamaProvider,
    model: str,
    temperature: float,
    top_p: float,
    num_predict: int,
    num_ctx: int | None = None,
) -> ChatOllama:
    """
    Cria uma instância do ChatOllama com configurações independentes.

    Permite selecionar:
    - Ollama Local ou Ollama Cloud;
    - Modelo;
    - Temperatura;
    - Top P;
    - Limite de tokens de saída.
    """

    client_kwargs: dict[str, Any] = {}

    # Seleção do endpoint
    if provider == "cloud":
        if settings.ollama_api_key is None:
            raise ValueError(
                "OLLAMA_API_KEY é obrigatória para utilizar o Ollama Cloud."
            )

        api_key = settings.ollama_api_key.get_secret_value()

        if not api_key.strip():
            raise ValueError(
                "OLLAMA_API_KEY está vazia. Informe uma chave válida."
            )

        base_url = settings.ollama_cloud_base_url

        client_kwargs = {
            "headers": {
                "Authorization": f"Bearer {api_key}"
            }
        }

    else:
        base_url = settings.ollama_local_base_url

    # Instancia o modelo
    return ChatOllama(
        model=model,
        base_url=base_url,
        temperature=temperature,
        top_p=top_p,
        num_ctx = num_ctx,
        num_predict=num_predict,
        client_kwargs=client_kwargs,
    )


def create_chat_model(
    settings: Settings | None = None,
) -> ChatOllama:
    """
    Cria o modelo principal utilizado pelo assistente do site.

    Utiliza exclusivamente as configurações LLM_* e OLLAMA_*.
    """

    if settings is None:
        settings = get_settings()

    return _create_ollama_model(
        settings=settings,
        provider=settings.ollama_provider,
        model=settings.llm_model,
        temperature=settings.llm_temperature,
        top_p=settings.llm_top_p,
        num_predict=settings.llm_num_predict,
        num_ctx=None,
    )


def create_semantic_index_model(
    settings: Settings | None = None,
) -> ChatOllama:
    """
    Cria o modelo auxiliar utilizado na geração do índice semântico.

    Utiliza exclusivamente as configurações SEMANTIC_INDEX_*.
    """

    if settings is None:
        settings = get_settings()

    return _create_ollama_model(
        settings=settings,
        provider=settings.semantic_index_provider,
        model=settings.semantic_index_model,
        temperature=settings.semantic_index_temperature,
        top_p=settings.semantic_index_top_p,
        num_predict=settings.semantic_index_num_predict,
        num_ctx=settings.semantic_index_num_ctx,
    )


def create_agent_chat_model(
    settings: Settings | None = None,
) -> ChatOpenAI:
    """Cria o modelo do agente via endpoint OpenAI-compatível local do Ollama.

    O endpoint /v1/chat/completions evita problemas de serialização de
    ferramentas observados em algumas combinações de Ollama + Qwen 3.5
    no endpoint nativo /api/chat. A chamada continua 100% local.
    """

    if settings is None:
        settings = get_settings()

    if settings.ollama_provider != "local":
        raise ValueError(
            "O agente do Politize-se está configurado para usar Ollama local."
        )

    base_url = settings.ollama_local_base_url.rstrip("/")
    if not base_url.endswith("/v1"):
        base_url += "/v1"

    return ChatOpenAI(
        model=settings.llm_model,
        base_url=base_url,
        # O Ollama local não exige uma chave real; o cliente OpenAI exige
        # um valor não vazio para inicializar.
        api_key="ollama-local",
        temperature=settings.llm_temperature,
        top_p=settings.llm_top_p,
        max_tokens=max(settings.llm_num_predict, 2048),
        # Desativa o modo de raciocínio exposto no endpoint compatível,
        # evitando que tokens de thinking ocupem a resposta/ferramentas.
        reasoning_effort="none",
        timeout=180,
    )
