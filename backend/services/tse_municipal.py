import csv
import io
import unicodedata
import zipfile

from pathlib import PurePosixPath

import requests

from backend.schemas.politicos import PoliticoResumo



# CONFIGURAÇÕES


URL_CANDIDATOS = (
    "https://cdn.tse.jus.br/"
    "estatistica/sead/odsele/consulta_cand/"
    "consulta_cand_2024.zip"
)

FONTE_URL = (
    "https://dadosabertos.tse.jus.br/"
    "dataset/candidatos-2024"
)

TIMEOUT = 90

UFS_MUNICIPAIS = {
    "AC", "AL", "AM", "AP", "BA", "CE",
    "ES", "GO", "MA", "MG", "MS",
    "MT", "PA", "PB", "PE", "PI", "PR",
    "RJ", "RN", "RO", "RR", "RS", "SC",
    "SE", "SP", "TO",
}



# CARGOS E SITUAÇÕES ACEITAS


CARGOS = {
    "PREFEITO": {
        "cargo": "Prefeito",
        "slug": "prefeito",
        "situacoes": {"ELEITO"},
    },

    "VEREADOR": {
        "cargo": "Vereador",
        "slug": "vereador",
        "situacoes": {
            "ELEITO POR QP",
            "ELEITO POR MEDIA",
        },
    },
}



# EXCEÇÃO


class TSEMunicipalAPIError(Exception):
    """Erro ao consultar ou processar os dados municipais do TSE."""



# NORMALIZAÇÃO DE TEXTO


def _normalizar_texto(valor: str | None) -> str:
    if not valor:
        return ""

    texto = unicodedata.normalize(
        "NFKD",
        valor.strip().upper(),
    )

    return "".join(
        caractere
        for caractere in texto
        if not unicodedata.combining(caractere)
    )



# ARQUIVOS REGIONAIS


def _listar_arquivos_regionais(
    arquivo: zipfile.ZipFile,
) -> list[str]:

    arquivos = []

    for nome in arquivo.namelist():
        caminho = PurePosixPath(nome)

        if caminho.suffix.lower() != ".csv":
            continue

        nome_base = caminho.stem.upper()

        if not nome_base.startswith("CONSULTA_CAND_2024_"):
            continue

        uf = nome_base.rsplit("_", 1)[-1]

        if uf in UFS_MUNICIPAIS:
            arquivos.append(nome)

    return sorted(arquivos)



# NORMALIZAÇÃO DO CANDIDATO


def _normalizar_candidato(
    registro: dict[str, str],
    cargo_config: dict,
) -> PoliticoResumo:

    candidato_id = registro.get("SQ_CANDIDATO")

    nome = (
        registro.get("NM_URNA_CANDIDATO")
        or registro.get("NM_CANDIDATO")
    )

    if not candidato_id or not nome:
        raise TSEMunicipalAPIError(
            "Candidato sem identificador ou nome válido."
        )

    turno_original = registro.get("NR_TURNO")

    try:
        turno = (
            int(turno_original)
            if turno_original
            else None
        )
    except (ValueError, TypeError):
        turno = None

    return PoliticoResumo(
        id=f"tse-2024-{candidato_id}",
        id_origem=candidato_id,
        fonte="tse",

        nome=nome.strip(),
        cargo=cargo_config["cargo"],
        cargo_slug=cargo_config["slug"],

        partido=registro.get("SG_PARTIDO") or None,
        uf=registro.get("SG_UF") or None,

        municipio=registro.get("NM_UE") or None,
        codigo_municipio_tse=registro.get("SG_UE") or None,

        situacao=(
            "Eleito em 2024 para o mandato 2025–2028. "
            "Exercício atual não verificado."
        ),

        mandato="2025–2028",
        fase_mandato="mandato_em_andamento",

        numero_candidato=(
            registro.get("NR_CANDIDATO") or None
        ),

        situacao_eleitoral=(
            registro.get("DS_SIT_TOT_TURNO") or None
        ),

        turno_eleitoral=turno,
        ano_eleicao=2024,

        foto_url=None,
        fonte_url=FONTE_URL,
    )



# LISTAR PREFEITOS E VEREADORES ELEITOS


def listar_eleitos_municipais_2024() -> list[PoliticoResumo]:

    try:
        response = requests.get(
            URL_CANDIDATOS,
            timeout=TIMEOUT,
            headers={
                "User-Agent": "Politize-se/1.0",
                "Accept": "application/zip",
            },
        )

        response.raise_for_status()

    except requests.exceptions.Timeout as erro:
        raise TSEMunicipalAPIError(
            "Tempo esgotado ao consultar os dados municipais do TSE."
        ) from erro

    except requests.exceptions.RequestException as erro:
        raise TSEMunicipalAPIError(
            "Não foi possível baixar os dados municipais do TSE."
        ) from erro

    try:
        arquivo = zipfile.ZipFile(
            io.BytesIO(response.content)
        )

    except zipfile.BadZipFile as erro:
        raise TSEMunicipalAPIError(
            "O TSE retornou um arquivo ZIP inválido."
        ) from erro

    eleitos_por_id: dict[str, PoliticoResumo] = {}

    campos_obrigatorios = {
        "SQ_CANDIDATO",
        "DS_CARGO",
        "DS_SIT_TOT_TURNO",
        "NR_TURNO",
        "NM_URNA_CANDIDATO",
        "SG_PARTIDO",
        "SG_UF",
        "SG_UE",
        "NM_UE",
        "NR_CANDIDATO",
    }

    try:
        arquivos = _listar_arquivos_regionais(arquivo)

        if len(arquivos) != 26:
            raise TSEMunicipalAPIError(
                "Esperados 26 arquivos regionais, "
                f"mas foram encontrados {len(arquivos)}."
            )

        for nome_arquivo in arquivos:

            with arquivo.open(nome_arquivo) as dados:

                texto = io.TextIOWrapper(
                    dados,
                    encoding="latin-1",
                    newline="",
                )

                leitor = csv.DictReader(
                    texto,
                    delimiter=";",
                )

                if not leitor.fieldnames:
                    raise TSEMunicipalAPIError(
                        f"Arquivo sem cabeçalho: {nome_arquivo}"
                    )

                colunas = {
                    coluna.strip().lstrip("\ufeff")
                    for coluna in leitor.fieldnames
                }

                faltantes = campos_obrigatorios - colunas

                if faltantes:
                    raise TSEMunicipalAPIError(
                        f"Campos ausentes em {nome_arquivo}: "
                        f"{', '.join(sorted(faltantes))}"
                    )

                for original in leitor:

                    registro = {
                        (chave or "").strip().lstrip("\ufeff"):
                        (valor or "").strip()
                        for chave, valor in original.items()
                        if chave is not None
                    }

                    cargo_original = _normalizar_texto(
                        registro.get("DS_CARGO")
                    )

                    cargo_config = CARGOS.get(cargo_original)

                    if not cargo_config:
                        continue

                    situacao = _normalizar_texto(
                        registro.get("DS_SIT_TOT_TURNO")
                    )

                    if situacao not in cargo_config["situacoes"]:
                        continue

                    candidato_id = registro.get("SQ_CANDIDATO")

                    if not candidato_id:
                        continue

                    politico = _normalizar_candidato(
                        registro,
                        cargo_config,
                    )

                    # Mantém somente um registro por candidato.
                    # Caso apareça em mais de um turno, preserva
                    # o registro do turno mais recente.

                    existente = eleitos_por_id.get(candidato_id)

                    if existente is None:
                        eleitos_por_id[candidato_id] = politico

                    elif (
                        (politico.turno_eleitoral or 0)
                        > (existente.turno_eleitoral or 0)
                    ):
                        eleitos_por_id[candidato_id] = politico

    except TSEMunicipalAPIError:
        raise

    except (
        csv.Error,
        UnicodeError,
        OSError,
        ValueError,
        TypeError,
    ) as erro:
        raise TSEMunicipalAPIError(
            "Erro ao processar os dados municipais do TSE."
        ) from erro

    finally:
        arquivo.close()

    eleitos = list(eleitos_por_id.values())

    if not eleitos:
        raise TSEMunicipalAPIError(
            "Nenhum prefeito ou vereador eleito foi encontrado."
        )

    eleitos.sort(
        key=lambda politico: (
            politico.cargo_slug,
            politico.uf or "",
            politico.municipio or "",
            politico.nome.casefold(),
        )
    )

    return eleitos