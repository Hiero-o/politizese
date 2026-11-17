from typing import Any

import requests

from pydantic import ValidationError

from backend.schemas.deputados import(
    DeputadoPerfil,
    DeputadoResumo,
    GabineteDeputado,
    ListaDeputadosResponse,
)


#Configurações


BASE_URL = "https://dadosabertos.camara.leg.br/api/v2"


TIMEOUT = 20


HEADERS = {
    "accept": "application/json",
}


# Excessões do serviço


class CamaraAPIError(Exception):
    """ Erro na comunicação ou resposta da API da Câmara."""
    

class DeputadoNotFoundError(Exception):
    """Deputado Não encontrado na câmara."""
    
    
    
#Cliente HTTP

def _request(endpoint: str, params: dict | None = None) -> dict:
    """Realiza uma requisição GET à API da Câmara."""
    
    url = f"{BASE_URL}/{endpoint.lstrip('/")')}"
    
    try:
        response = requests.get(
            url,
            params=params,
            headers=HEADERS,
            timeout=TIMEOUT,
        )
        
        if response.status_code ==404:
            raise DeputadoNotFoundError("Deputado não encontrado na API da Câmara.")
        
        response.raise_for_status()
        
        dados = response.json()
        
        
        if not isinstance(dados, dict):
            raise CamaraAPIError("A Câmara retornou uma resposta em formato inesperado.")

        return dados
        
        
    except DeputadoNotFoundError:
        raise
    
    
    except requests.Timeout as erro:
        raise CamaraAPIError("A API da Câmara demorou para responder.") from erro
        
    except requests.RequestException as erro:
        raise CamaraAPIError("Não foi possível consultar a API da Câmara")
    except ValueError as erro:
        raise CamaraAPIError("A Câmara retornou um JSON inválido") from erro
        


#Normalização: Listagem

def _normalizar_resumo(
    dados: dict[str, any],
) -> DeputadoResumo:
    """Converte o objeto original da Câmara para o schema DeputadoResumo."""
    
    
    return DeputadoResumo(
        id=dados["id"],
        nome=dados["nome"],
        partido=dados.get("siglaPartido"),
        uf=dados.get("siglaUf"),
        id_legislatura=dados.get("idLegislatura"),
        foto_url=dados.get("urlFoto"),
        email=dados.get("email"),
        fonte_url=dados.get("uri"),
        
    )
    
    
# Listar E Pesquisar dEputadod


def listar_deputados(
    nome:str | None = None,       
    sigla_uf:str | None = None,
    sigla_partido:str | None = None,
    pagina:int = 1,
    itens:int = 20,

) -> ListaDeputadosResponse:
    """Consulta deputados em exercício na câmara. Permite filtrar por nomes, UF e partido"""
    
    
    params = {
        "pagina": pagina,
        "itens": itens,
        "ordem": "ASC",
        "ordenarPor": "nome",
    }
    
    if nome and nome.strip():
        params["nome"] = nome.strip()
        
    if sigla_uf:
        params["siglaPartido"] = sigla_partido.strip().upper()
    resposta = _request(
        "deputados",
        params=params,
    )
    
    registro = resposta.get("dados", [])
    links = resposta.get("links", [])