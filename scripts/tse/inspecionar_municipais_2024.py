import csv
import io
import sys
import unicodedata
import zipfile

from collections import Counter, defaultdict
from pathlib import PurePosixPath

import requests


URL_TSE = (
    "https://cdn.tse.jus.br/"
    "estatistica/sead/odsele/consulta_cand/"
    "consulta_cand_2024.zip"
)

TIMEOUT = 90

UFS_MUNICIPAIS = {
    "AC", "AL", "AM", "AP", "BA", "CE",
    "ES", "GO", "MA", "MG", "MS",
    "MT", "PA", "PB", "PE", "PI", "PR",
    "RJ", "RN", "RO", "RR", "RS", "SC",
    "SE", "SP", "TO",
}

CARGOS_INTERESSE = {
    "PREFEITO",
    "VEREADOR",
}


def normalizar_texto(valor):
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


def baixar_dados():
    print("Baixando dados municipais de 2024 do TSE...")

    try:
        response = requests.get(
            URL_TSE,
            timeout=TIMEOUT,
            headers={
                "User-Agent": "Politize-se/1.0",
                "Accept": "application/zip",
            },
        )

        response.raise_for_status()

        return zipfile.ZipFile(
            io.BytesIO(response.content)
        )

    except requests.RequestException as erro:
        raise RuntimeError(
            f"Erro ao baixar dados do TSE: {erro}"
        ) from erro

    except zipfile.BadZipFile as erro:
        raise RuntimeError(
            "O TSE retornou um ZIP inválido."
        ) from erro


def listar_arquivos_regionais(arquivo):
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


def inspecionar():
    arquivo = baixar_dados()

    registros_unicos = {}
    duplicados = 0

    contagem = Counter()
    exemplos = defaultdict(list)

    colunas_encontradas = set()
    municipios_por_cargo = defaultdict(set)

    arquivos = listar_arquivos_regionais(arquivo)

    print(f"\nArquivos regionais encontrados: {len(arquivos)}")

    if len(arquivos) != 26:
        raise RuntimeError(
            f"Esperados 27 arquivos regionais, "
            f"mas foram encontrados {len(arquivos)}."
        )

    try:
        for nome_arquivo in arquivos:
            print(f"Lendo: {nome_arquivo}")

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
                    continue

                for coluna in leitor.fieldnames:
                    colunas_encontradas.add(
                        coluna.strip().lstrip("\ufeff")
                    )

                for original in leitor:
                    registro = {
                        (chave or "").strip().lstrip("\ufeff"):
                        (valor or "").strip()
                        for chave, valor in original.items()
                        if chave is not None
                    }

                    cargo = normalizar_texto(
                        registro.get("DS_CARGO")
                    )

                    if cargo not in CARGOS_INTERESSE:
                        continue

                    candidato_id = registro.get("SQ_CANDIDATO")
                    turno = registro.get("NR_TURNO")

                    if not candidato_id or not turno:
                        continue

                    # Um candidato pode aparecer em dois turnos.
                    chave = (candidato_id, turno)

                    if chave in registros_unicos:
                        duplicados += 1
                        continue

                    registros_unicos[chave] = registro

                    situacao = normalizar_texto(
                        registro.get("DS_SIT_TOT_TURNO")
                    ) or "SEM INFORMACAO"

                    contagem[(cargo, situacao)] += 1

                    codigo_municipio = registro.get("SG_UE")
                    nome_municipio = registro.get("NM_UE")

                    if codigo_municipio:
                        municipios_por_cargo[cargo].add(
                            codigo_municipio
                        )

                    if (
                        situacao.startswith("ELEITO")
                        and len(exemplos[cargo]) < 8
                    ):
                        exemplos[cargo].append({
                            "nome": registro.get(
                                "NM_URNA_CANDIDATO"
                            ),
                            "uf": registro.get("SG_UF"),
                            "municipio": nome_municipio,
                            "codigo_municipio": codigo_municipio,
                            "partido": registro.get("SG_PARTIDO"),
                            "situacao": registro.get("DS_SIT_TOT_TURNO"),
                            "turno": turno,
                            "id": candidato_id,
                        })
    

    finally:
        arquivo.close()

    # ========================================================
    # RELATÓRIO
    # ========================================================

    print("\n========== RESULTADO ==========")

    print("\nColunas municipais disponíveis:")

    relevantes = {
        "DS_CARGO",
        "SQ_CANDIDATO",
        "NM_CANDIDATO",
        "NM_URNA_CANDIDATO",
        "SG_UF",
        "CD_MUNICIPIO",
        "CD_MUNICIPIO_TSE",
        "NM_MUNICIPIO",
        "NM_UE",
        "NR_TURNO",
        "NR_CANDIDATO",
        "SG_PARTIDO",
        "DS_SIT_TOT_TURNO",
        "DS_SIT_CANDIDATURA",
        "DS_DETALHE_SIT_CAND",
        "DS_MOTIVO_CASSACAO",
        "SG_UE",
        "NM_UE",
    }

    for coluna in sorted(
        colunas_encontradas.intersection(relevantes)
    ):
        print(f"- {coluna}")

    ids_distintos = {
        registro["SQ_CANDIDATO"]
        for registro in registros_unicos.values()
    }

    print("\nCandidatos distintos:", len(ids_distintos))
    print("Registros candidato/turno:", len(registros_unicos))
    print("Duplicações ignoradas:", duplicados)

    print("\nMunicípios identificados:")

    for cargo, municipios in sorted(municipios_por_cargo.items()):
        print(f"{cargo}: {len(municipios)}")

    print("\nQuantidade por cargo e situação:")

    for (cargo, situacao), quantidade in sorted(contagem.items()):
        print(f"{cargo} | {situacao} | {quantidade}")

    print("\nExemplos de candidatos classificados como eleitos:")

    for cargo, registros in sorted(exemplos.items()):
        print(f"\n{cargo}")

        for registro in registros:
            print(
                f"{registro['nome']} | "
                f"{registro['municipio']} | "
                f"{registro['uf']} | "
                f"{registro['partido']} | "
                f"{registro['situacao']} | "
                f"Turno: {registro['turno']} | "
                f"ID: {registro['id']}"
            )

    print("\n========== PREFEITOS — SEGUNDO TURNO ==========")

    segundo_turno = [
        registro
        for registro in registros_unicos.values()
        if normalizar_texto(registro.get("DS_CARGO")) == "PREFEITO"
        and registro.get("NR_TURNO") == "2"
    ]

    for registro in segundo_turno:
        print(
            f"{registro.get('NM_URNA_CANDIDATO')} | "
            f"{registro.get('NM_MUNICIPIO') or registro.get('NM_UE')} | "
            f"{registro.get('SG_UF')} | "
            f"{registro.get('DS_SIT_TOT_TURNO')} | "
            f"ID: {registro.get('SQ_CANDIDATO')}"
        )
        
    municipios_com_prefeito_eleito = set()
    municipios_com_vereador_eleito = set()

    for registro in registros_unicos.values():
        cargo = normalizar_texto(
            registro.get("DS_CARGO")
        )

        situacao = normalizar_texto(
            registro.get("DS_SIT_TOT_TURNO")
        )

        uf = registro.get("SG_UF")
        codigo = registro.get("SG_UE")

        if not uf or not codigo:
            continue

        identificador = (uf, codigo)

        if cargo == "PREFEITO" and situacao == "ELEITO":
            municipios_com_prefeito_eleito.add(identificador)

        elif cargo == "VEREADOR" and situacao in {
            "ELEITO POR QP",
            "ELEITO POR MEDIA",
        }:
            municipios_com_vereador_eleito.add(identificador)

    print("\n========== MUNICÍPIOS COM ELEITOS ==========")

    print(
        "Municípios com prefeito eleito:",
        len(municipios_com_prefeito_eleito),
    )

    print(
        "Municípios com vereadores eleitos:",
        len(municipios_com_vereador_eleito),
    )


if __name__ == "__main__":
    try:
        inspecionar()
    except Exception as erro:
        print(f"\nERRO: {erro}")
        sys.exit(1)