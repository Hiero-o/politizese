import csv
import io
import unicodedata
import zipfile

from pathlib import PurePosixPath
from time import monotonic

import requests

from backend.schemas.politicos import PoliticoResumo


# ============================================================
# CONFIGURAÇÕES
# ============================================================

BASE_URL = (
    "https://cdn.tse.jus.br/"
    "estatistica/sead/odsele/consulta_cand/"
)

URL_CANDIDATOS = (
    BASE_URL + "consulta_cand_2026.zip"
)

FONTE_URL = (
    "https://dadosabertos.tse.jus.br/"
    "dataset/candidatos-2026"
)

TIMEOUT = 90

CACHE_TTL = 21600  # 6 horas

UFS = {
    "AC", "AL", "AM", "AP", "BA", "CE",
    "DF", "ES", "GO", "MA", "MG", "MS",
    "MT", "PA", "PB", "PE", "PI", "PR",
    "RJ", "RN", "RO", "RR", "RS", "SC",
    "SE", "SP", "TO",
}


# ============================================================
# CARGOS E SITUAÇÕES ACEITAS
# ============================================================

CARGOS = {
    "GOVERNADOR": {
        "cargo": "Governador",
        "slug": "governador",
        "situacoes": {"ELEITO"},
        "mandato": "2027–2030",
    },

    "DEPUTADO ESTADUAL": {
        "cargo": "Deputado estadual",
        "slug": "deputado_estadual",
        "situacoes": {
            "ELEITO POR QP",
            "ELEITO POR MEDIA",
        },
        "mandato": "2027–2031",
    },

    "DEPUTADO DISTRITAL": {
        "cargo": "Deputado distrital",
        "slug": "deputado_distrital",
        "situacoes": {
            "ELEITO POR QP",
            "ELEITO POR MEDIA",
        },
        "mandato": "2027–2031",
    },
}


# ============================================================
# CACHE
# ============================================================

_cache_eleitos: list[PoliticoResumo] | None = None
_cache_atualizado_em = 0.0


# ============================================================
# EXCEÇÃO
# ============================================================

class TSEAPIError(Exception):
    """Erro ao consultar ou processar os dados do TSE."""


# ============================================================
# NORMALIZAÇÃO DE TEXTO
# ============================================================

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


# ============================================================
# NORMALIZAÇÃO DE REGISTROS
# ============================================================

def _normalizar_registro(
    registro: dict[str, str],
    cargo_config: dict,
) -> PoliticoResumo:

    id_candidato = registro.get("SQ_CANDIDATO")
    nome = (
        registro.get("NM_URNA_CANDIDATO")
        or registro.get("NM_CANDIDATO")
    )

    if not id_candidato or not nome:
        raise TSEAPIError(
            "Candidato sem identificador ou nome válido."
        )

    numero_turno = registro.get("NR_TURNO")

    try:
        turno = int(numero_turno) if numero_turno else None
    except (TypeError, ValueError):
        turno = None

    situacao_eleitoral = registro.get(
        "DS_SIT_TOT_TURNO"
    )

    return PoliticoResumo(
        id=f"tse-2026-{id_candidato}",
        id_origem=id_candidato,
        fonte="tse",

        nome=nome.strip(),
        cargo=cargo_config["cargo"],
        cargo_slug=cargo_config["slug"],

        partido=registro.get("SG_PARTIDO") or None,
        uf=registro.get("SG_UF") or None,

        foto_url=None,

        situacao=(
            f"Eleito para o mandato "
            f"{cargo_config['mandato']}"
        ),

        mandato=cargo_config["mandato"],
        fase_mandato="eleito_futuro",

        numero_candidato=(
            registro.get("NR_CANDIDATO") or None
        ),

        situacao_eleitoral=situacao_eleitoral,
        turno_eleitoral=turno,
        ano_eleicao=2026,

        fonte_url=FONTE_URL,
    )


# ============================================================
# IDENTIFICAÇÃO DOS ARQUIVOS REGIONAIS
# ============================================================

def _listar_arquivos_regionais(
    arquivo: zipfile.ZipFile,
) -> list[str]:

    arquivos = []

    for nome in arquivo.namelist():
        caminho = PurePosixPath(nome)

        if caminho.suffix.lower() != ".csv":
            continue

        nome_base = caminho.stem.upper()

        if not nome_base.startswith("CONSULTA_CAND_2026_"):
            continue

        uf = nome_base.rsplit("_", 1)[-1]

        if uf in UFS:
            arquivos.append(nome)

    return sorted(arquivos)


# ============================================================
# LEITURA DOS CANDIDATOS ELEITOS
# ============================================================

def _processar_arquivo(
    arquivo: zipfile.ZipFile,
    nome_arquivo: str,
    eleitos_por_id: dict[str, PoliticoResumo],
) -> None:

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
            raise TSEAPIError(
                f"Arquivo sem cabeçalho: {nome_arquivo}"
            )

        colunas = {
            coluna.strip().lstrip("\ufeff")
            for coluna in leitor.fieldnames
        }

        obrigatorias = {
            "SQ_CANDIDATO",
            "DS_CARGO",
            "DS_SIT_TOT_TURNO",
            "NR_TURNO",
            "NM_URNA_CANDIDATO",
            "SG_PARTIDO",
            "SG_UF",
            "NR_CANDIDATO",
        }

        if not obrigatorias.issubset(colunas):
            faltantes = obrigatorias - colunas

            raise TSEAPIError(
                f"Colunas ausentes em {nome_arquivo}: "
                f"{', '.join(sorted(faltantes))}"
            )

        for registro_original in leitor:
            registro = {
                (chave or "").strip().lstrip("\ufeff"):
                (valor or "").strip()
                for chave, valor in registro_original.items()
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

            id_candidato = registro.get("SQ_CANDIDATO")

            if not id_candidato:
                continue

            politico = _normalizar_registro(
                registro,
                cargo_config,
            )

            # Um candidato pode aparecer nos dois turnos.
            # Entre registros selecionados, preservamos o turno
            # mais recente para o mesmo identificador.
            existente = eleitos_por_id.get(id_candidato)

            if existente is None:
                eleitos_por_id[id_candidato] = politico

            elif (
                (politico.turno_eleitoral or 0)
                > (existente.turno_eleitoral or 0)
            ):
                eleitos_por_id[id_candidato] = politico


# ============================================================
# SERVIÇO PRINCIPAL
# ============================================================

def listar_eleitos_2026(
    forcar_atualizacao: bool = False,
) -> list[PoliticoResumo]:

    global _cache_eleitos
    global _cache_atualizado_em

    agora = monotonic()

    if (
        not forcar_atualizacao
        and _cache_eleitos is not None
        and agora - _cache_atualizado_em < CACHE_TTL
    ):
        return list(_cache_eleitos)

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
        raise TSEAPIError(
            "Tempo esgotado ao consultar os dados do TSE."
        ) from erro

    except requests.exceptions.RequestException as erro:
        raise TSEAPIError(
            "Não foi possível baixar os dados do TSE."
        ) from erro

    try:
        arquivo = zipfile.ZipFile(
            io.BytesIO(response.content)
        )

    except zipfile.BadZipFile as erro:
        raise TSEAPIError(
            "O TSE retornou um arquivo ZIP inválido."
        ) from erro

    eleitos_por_id: dict[str, PoliticoResumo] = {}

    try:
        arquivos = _listar_arquivos_regionais(arquivo)

        if len(arquivos) != 27:
            raise TSEAPIError(
                "Esperados 27 arquivos regionais do TSE, "
                f"mas foram encontrados {len(arquivos)}."
            )

        for nome_arquivo in arquivos:
            _processar_arquivo(
                arquivo,
                nome_arquivo,
                eleitos_por_id,
            )

    except (csv.Error, UnicodeError, OSError) as erro:
        raise TSEAPIError(
            "Erro ao processar os arquivos eleitorais do TSE."
        ) from erro

    finally:
        arquivo.close()

    politicos = list(eleitos_por_id.values())

    if not politicos:
        raise TSEAPIError(
            "Nenhum candidato eleito foi encontrado nos dados do TSE."
        )

    politicos.sort(
        key=lambda politico: (
            politico.cargo_slug,
            politico.uf or "",
            politico.nome.casefold(),
        )
    )

    # Atualizar cache somente após processamento completo.
    _cache_eleitos = politicos
    _cache_atualizado_em = monotonic()

    return list(_cache_eleitos)