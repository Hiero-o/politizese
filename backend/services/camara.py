
from typing import Any

import requests
from pydantic import ValidationError

from backend.schemas.deputados import (
    DeputadoPerfil,
    DeputadoResumo,
    GabineteDeputado,
    ListaDeputadosResponse,
)


# ============================================================
# CONFIGURAÇÕES
# ============================================================

BASE_URL = "https://dadosabertos.camara.leg.br/api/v2"

TIMEOUT = 20

HEADERS = {
    "Accept": "application/json",
}


# ============================================================
# EXCEÇÕES DO SERVIÇO
# ============================================================

class CamaraAPIError(Exception):
    """Erro na comunicação ou resposta da API da Câmara."""


class DeputadoNotFoundError(Exception):
    """Deputado não encontrado na Câmara."""


# ============================================================
# CLIENTE HTTP
# ============================================================

def _request(
    endpoint: str,
    params: dict[str, Any] | None = None,
) -> dict:
    """
    Realiza uma requisição GET à API da Câmara.
    """

    url = f"{BASE_URL}/{endpoint.lstrip('/')}"

    try:
        response = requests.get(
            url,
            params=params,
            headers=HEADERS,
            timeout=TIMEOUT,
        )

        if response.status_code == 404:
            raise DeputadoNotFoundError(
                "Deputado não encontrado na API da Câmara."
            )

        response.raise_for_status()

        dados = response.json()

        if not isinstance(dados, dict):
            raise CamaraAPIError(
                "A Câmara retornou uma resposta em formato inesperado."
            )

        return dados

    except DeputadoNotFoundError:
        raise

    except requests.Timeout as erro:
        raise CamaraAPIError(
            "A API da Câmara demorou para responder."
        ) from erro

    except ValueError as erro:
        raise CamaraAPIError(
            "A Câmara retornou um JSON inválido."
        ) from erro

    except requests.RequestException as erro:
        raise CamaraAPIError(
            "Não foi possível consultar a API da Câmara."
        ) from erro


# ============================================================
# NORMALIZAÇÃO: LISTAGEM
# ============================================================

def _normalizar_resumo(
    dados: dict[str, Any],
) -> DeputadoResumo:
    """
    Converte o objeto original da Câmara
    para o schema DeputadoResumo.
    """

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


# ============================================================
# LISTAR E PESQUISAR DEPUTADOS
# ============================================================

def listar_deputados(
    nome: str | None = None,
    sigla_uf: str | None = None,
    sigla_partido: str | None = None,
    pagina: int = 1,
    itens: int = 20,
) -> ListaDeputadosResponse:
    """
    Consulta deputados em exercício na Câmara.

    Permite filtrar por nome, UF e partido.
    """

    if pagina < 1:
        raise ValueError("A página deve ser maior que zero.")

    if not 1 <= itens <= 100:
        raise ValueError(
            "A quantidade de itens deve estar entre 1 e 100."
        )

    params: dict[str, Any] = {
        "pagina": pagina,
        "itens": itens,
        "ordem": "ASC",
        "ordenarPor": "nome",
    }

    if nome and nome.strip():
        params["nome"] = nome.strip()

    if sigla_uf and sigla_uf.strip():
        params["siglaUf"] = sigla_uf.strip().upper()

    if sigla_partido and sigla_partido.strip():
        params["siglaPartido"] = sigla_partido.strip().upper()

    resposta = _request(
        "deputados",
        params=params,
    )

    registros = resposta.get("dados", [])
    links = resposta.get("links", [])

    if not isinstance(registros, list):
        raise CamaraAPIError(
            "A estrutura da listagem de deputados é inválida."
        )

    if not isinstance(links, list):
        raise CamaraAPIError(
            "A estrutura dos links de paginação é inválida."
        )

    tem_proxima = any(
        link.get("rel") == "next"
        for link in links
        if isinstance(link, dict)
    )

    try:
        deputados = [
            _normalizar_resumo(deputado)
            for deputado in registros
        ]

        return ListaDeputadosResponse(
            dados=deputados,
            pagina=pagina,
            itens=itens,
            tem_proxima=tem_proxima,
        )

    except (ValidationError, KeyError, TypeError) as erro:
        raise CamaraAPIError(
            "Não foi possível normalizar os dados dos deputados."
        ) from erro


# ============================================================
# CONSULTAR PERFIL INDIVIDUAL
# ============================================================

def obter_deputado(
    deputado_id: int,
) -> DeputadoPerfil:
    """
    Consulta os dados de um deputado específico.

    Utiliza o objeto 'ultimoStatus' para obter
    as informações atuais do exercício parlamentar.
    """

    if deputado_id <= 0:
        raise ValueError("O ID do deputado deve ser positivo.")

    resposta = _request(
        f"deputados/{deputado_id}"
    )

    dados = resposta.get("dados")

    if not isinstance(dados, dict):
        raise CamaraAPIError(
            "A Câmara retornou um perfil inválido."
        )

    ultimo_status = dados.get("ultimoStatus") or {}

    if not isinstance(ultimo_status, dict):
        raise CamaraAPIError(
            "Os dados do último status do deputado são inválidos."
        )

    # --------------------------------------------------------
    # GABINETE
    # --------------------------------------------------------

    gabinete_original = ultimo_status.get("gabinete")

    gabinete = None

    if isinstance(gabinete_original, dict):
        try:
            gabinete = GabineteDeputado.model_validate(
                gabinete_original
            )

        except ValidationError as erro:
            raise CamaraAPIError(
                "Os dados do gabinete possuem formato inválido."
            ) from erro

    # --------------------------------------------------------
    # REDES SOCIAIS
    # --------------------------------------------------------

    redes_sociais = dados.get("redeSocial") or []

    if not isinstance(redes_sociais, list):
        redes_sociais = []

    redes_sociais = [
        link
        for link in redes_sociais
        if isinstance(link, str) and link.strip()
    ]

    # --------------------------------------------------------
    # NORMALIZAÇÃO DO PERFIL
    # --------------------------------------------------------

    dados_normalizados = {
        "id": dados.get("id") or ultimo_status.get("id"),

        "nome": (
            ultimo_status.get("nome")
            or ultimo_status.get("nomeEleitoral")
        ),

        "partido": ultimo_status.get("siglaPartido"),
        "uf": ultimo_status.get("siglaUf"),
        "id_legislatura": ultimo_status.get("idLegislatura"),

        "foto_url": ultimo_status.get("urlFoto"),
        "email": ultimo_status.get("email"),
        "fonte_url": dados.get("uri"),

        "nome_eleitoral": ultimo_status.get("nomeEleitoral"),
        "situacao": ultimo_status.get("situacao"),

        "condicao_eleitoral": ultimo_status.get(
            "condicaoEleitoral"
        ),

        "data_inicio_exercicio": ultimo_status.get("data"),

        "gabinete": gabinete,
        "redes_sociais": redes_sociais,
        "website": dados.get("urlWebsite"),
    }

    # --------------------------------------------------------
    # VALIDAÇÃO FINAL COM PYDANTIC
    # --------------------------------------------------------

    try:
        return DeputadoPerfil.model_validate(
            dados_normalizados
        )

    except ValidationError as erro:
        raise CamaraAPIError(
            "Não foi possível validar o perfil do deputado."
        ) from erro
