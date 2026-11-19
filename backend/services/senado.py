import requests

from backend.schemas.politicos import PoliticoResumo


BASE_URL = (
    "https://adm.senado.gov.br/adm-dadosabertos/api/v1/senadores"
)

FONTE_URL = (
    "https://www12.senado.leg.br/dados-abertos/legislativo/parlamentares/senadores-em-exercicio"
)


TIMEOUT = 20


class SenadoAPIError(Exception):
    """Erro ao consultar API do Senado."""


def listar_senadores() -> list[PoliticoResumo]:
    try:
        response = requests.get(
            BASE_URL,
            params={"formato": "json"},
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        resultado = response.json()

    except requests.exceptions.Timeout as erro:
        raise SenadoAPIError(f"Tempo esgotado ao consultar o Senado Federal: {erro}") from erro

    except requests.exceptions.RequestException as erro:
        raise SenadoAPIError("Não foi possível conectar à API do Senado Federal.") from erro

    except ValueError as erro:
        raise SenadoAPIError("A API do Senado retornou um JSON inválido.") from erro

    if not isinstance(resultado, dict):
        raise SenadoAPIError("Formato inesperado na resposta do Senado.")

    registros = resultado.get("data")

    if not isinstance(registros, list):
        raise SenadoAPIError("A resposta do Senado não contém uma lista de parlamentares.")

    senadores = []

    for registro in registros:
        if not isinstance(registro, dict):
            continue

        codigo = registro.get("codigoParlamentar")
        nome = registro.get("nomeParlamentar")

        if codigo is None or not nome:
            continue

        senador = PoliticoResumo(
            id=f"senado-{codigo}",
            id_origem=codigo,
            fonte="senado",
            nome=str(nome).strip(),
            
            cargo="Senador",
            cargo_slug="senador",
            partido=registro.get("partido"),
            
            uf=registro.get("uf"),
            foto_url=(
                registro.get("urlFoto")
                or registro.get("urlFotoParlamentar")
            ),
            
            email=registro.get("email"),
            telefone=registro.get("telefones"),
            
            situacao="Em exercício",
            titularidade=registro.get("titularSuplente"),
            mandato=registro.get("mandato"),
            
            fonte_url=(
                registro.get("urlPagina")
                or registro.get("urlPaginaParlamentar")
                or FONTE_URL
            ),
        )

        senadores.append(senador)

    return senadores