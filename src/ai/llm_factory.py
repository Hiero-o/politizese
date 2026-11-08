from typing import Any
from langchain_ollama import ChatOllama

from src.core.config import Settings, get_settings


def create_chat_model(settings: Settings | None = None) -> ChatOllama:
    """Cria Instância do llm utilizando as configurações centralizadas da aplicação. Permite utilizar Ollama local ou Ollama Cloud. 
    ARGS:
        settings: Configurações opcionais da aplicação.
        Caso não sejam  fornecidas, utiliza get_settings().
        
    Returns:
        Instância configurada de ChatOllama."""
        
    if settings is None:
        settings = get_settings()
        
    #Configs adicionais do cliente http.
    #dicionário novo é criado para cada instância.
    client_kwargs: dict[str, Any] = {}
    
    #autenticação exclusiva para Ollama Cloud.
    
    if settings.ollama_provider == "cloud":
        if settings.ollama_api_key is None:
            raise ValueError("OLLAMA_API_KEY é obrigatória para utilizar o Ollama Cloud.")
        api_key = settings.ollama_api_key.get_secret_value()
        
        client_kwargs = {
            "headers": {
                "Authorization": f"Bearer {api_key}"
            }
        }
    #Instânciando o modelo.
    
    llm = ChatOllama(
        model=settings.llm_model,
        base_url=settings.ollama_base_url,
        temperature=settings.llm_temperature,
        top_p=settings.llm_top_p,
        num_predict=settings.llm_num_predict,
        client_kwargs=client_kwargs
    )
    
    return llm