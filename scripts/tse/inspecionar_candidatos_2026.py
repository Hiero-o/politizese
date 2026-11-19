import csv
import io
import sys
import zipfile

from pathlib import PurePosixPath

from collections import Counter, defaultdict

import requests


URL_TSE = (
    "https://cdn.tse.jus.br/"
    "estatistica/sead/odsele/consulta_cand/"
    "consulta_cand_2026.zip"
)

TIMEOUT = 90

CARGOS_INTERESSE = {
    "GOVERNADOR",
    "DEPUTADO ESTADUAL",
    "DEPUTADO DISTRITAL",
}


def baixar_dados():
    print("Baixando dados oficiais do TSE...")

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

    except requests.RequestException as erro:
        raise RuntimeError(
            f"Falha ao baixar os dados do TSE: {erro}"
        ) from erro

    try:
        arquivo = zipfile.ZipFile(
            io.BytesIO(response.content)
        )
    except zipfile.BadZipFile as erro:
        raise RuntimeError(
            "O TSE não retornou um arquivo ZIP válido."
        ) from erro

    return arquivo


def inspecionar():
    arquivo = baixar_dados()

    UFS = {
    "AC", "AL", "AM", "AP", "BA", "CE",
    "DF", "ES", "GO", "MA", "MG", "MS",
    "MT", "PA", "PB", "PE", "PI", "PR",
    "RJ", "RN", "RO", "RR", "RS", "SC",
    "SE", "SP", "TO",
    }

    arquivos_csv = [
        nome
        for nome in arquivo.namelist()
        if PurePosixPath(nome).suffix.lower() == ".csv"
        and PurePosixPath(nome).stem.lower().startswith(
            "consulta_cand_2026_"
        )
        and PurePosixPath(nome).stem.rsplit("_", 1)[-1].upper() in UFS
    ]

    arquivos_csv.sort()

    if not arquivos_csv:
        raise RuntimeError(
            "Não foram encontrados CSVs de candidaturas no ZIP."
        )

    print(f"\nArquivos encontrados: {len(arquivos_csv)}")

    contagem = Counter()
    exemplos = defaultdict(list)
    colunas_encontradas = set()
    
    # identificadores unicos de candidatos
    
    registros_unicos = {}
    duplicados = 0

    for nome_arquivo in arquivos_csv:
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

            colunas = {
                coluna.strip().lstrip("\ufeff")
                for coluna in leitor.fieldnames
            }

            colunas_encontradas.update(colunas)

            obrigatorias = {
                "DS_CARGO",
                "DS_SIT_TOT_TURNO",
                "SQ_CANDIDATO",
            }

            if not obrigatorias.issubset(colunas):
                print(
                    "Aviso: arquivo sem todas as colunas esperadas."
                )
                continue

            for registro_original in leitor:
                registro = {
                    (chave or "").strip().lstrip("\ufeff"):
                    (valor or "").strip()
                    for chave, valor in registro_original.items()
                }

                cargo = registro.get("DS_CARGO", "").upper()

                if cargo not in CARGOS_INTERESSE:
                    continue
                
                # Identificador único fornecido pelo TSE
                id_candidato = registro.get("SQ_CANDIDATO")
                turno = registro.get("NR_TURNO")

                if not id_candidato:
                    continue

                if turno is None:
                    print(
                        f"Aviso: candidato {id_candidato} sem NR_TURNO."
                    )
                    continue

                # Um candidato pode aparecer em mais de um turno.
                # Só consideramos duplicado quando o ID e o turno coincidem.
                chave = (id_candidato, turno)

                if chave in registros_unicos:
                    duplicados += 1
                    continue

                registros_unicos[chave] = registro

                situacao = (
                    registro.get("DS_SIT_TOT_TURNO")
                    or "SEM INFORMAÇÃO"
                ).upper()

                contagem[(cargo, situacao)] += 1

                if (
                    situacao.startswith("ELEITO")
                    and len(exemplos[cargo]) < 5
                ):
                    exemplos[cargo].append({
                        "nome": registro.get("NM_URNA_CANDIDATO"),
                        "uf": registro.get("SG_UF"),
                        "partido": registro.get("SG_PARTIDO"),
                        "situacao": situacao,
                        "id": registro.get("SQ_CANDIDATO"),
                    })

    print("\n========== RESULTADO ==========")

    print("\nColunas relevantes:")
    for coluna in sorted(
        colunas_encontradas.intersection({
            "DS_CARGO",
            "SQ_CANDIDATO",
            "NR_CANDIDATO",
            "NM_CANDIDATO",
            "NM_URNA_CANDIDATO",
            "SG_UF",
            "SG_PARTIDO",
            "DS_SIT_CANDIDATURA",
            "DS_SIT_TOT_TURNO",
            "CD_SIT_TOT_TURNO",
            "NR_TURNO",
        })
    ):
        print(f"- {coluna}")

    print("\nQuantidade por cargo e situação:")
    ids_unicos = {
        registro["SQ_CANDIDATO"]
        for registro in registros_unicos.values()
    }

    print(
        f"Candidatos distintos: {len(ids_unicos)}"
    )

    print(
        f"Registros distintos por candidato/turno: "
        f"{len(registros_unicos)}"
    )

    print(
        f"Duplicações do mesmo candidato e turno ignoradas: "
        f"{duplicados}"
    )
    for (cargo, situacao), quantidade in sorted(contagem.items()):
        print(
            f"{cargo} | {situacao} | {quantidade}"
        )

    print("\nExemplos de candidatos com situação ELEITO:")

    for cargo, registros in sorted(exemplos.items()):
        print(f"\n{cargo}")

        for registro in registros:
            print(
                f"  {registro['nome']} | "
                f"{registro['uf']} | "
                f"{registro['partido']} | "
                f"{registro['situacao']} | "
                f"ID: {registro['id']}"
            )

    if not contagem:
        print(
            "\nATENÇÃO: nenhum registro dos cargos esperados "
            "foi encontrado."
        )
    
    
    print("\n========== GOVERNADORES — SEGUNDO TURNO ==========")

    candidatos_segundo_turno = [
        registro
        for registro in registros_unicos.values()
        if registro.get("DS_CARGO", "").upper() == "GOVERNADOR"
        and registro.get("DS_SIT_TOT_TURNO", "").upper() == "2º TURNO"
    ]

    candidatos_segundo_turno.sort(
        key=lambda registro: (
            registro.get("SG_UF", ""),
            registro.get("NM_URNA_CANDIDATO", ""),
        )
    )

    for candidato in candidatos_segundo_turno:
        print(
            f"UF: {candidato.get('SG_UF')} | "
            f"Nome: {candidato.get('NM_URNA_CANDIDATO')} | "
            f"Partido: {candidato.get('SG_PARTIDO')} | "
            f"Número: {candidato.get('NR_CANDIDATO')} | "
            f"ID: {candidato.get('SQ_CANDIDATO')}"
        )
    print("\n========== HISTÓRICO DOS GOVERNADORES ==========")

    governadores = [
        registro
        for registro in registros_unicos.values()
        if registro.get("DS_CARGO", "").upper() == "GOVERNADOR"
    ]

    governadores.sort(
        key=lambda registro: (
            registro.get("SG_UF", ""),
            str(registro.get("NR_TURNO", "")),
            registro.get("NM_URNA_CANDIDATO", ""),
        )
    )

    for governador in governadores:
        print(
            f"UF: {governador.get('SG_UF')} | "
            f"Turno: {governador.get('NR_TURNO')} | "
            f"Nome: {governador.get('NM_URNA_CANDIDATO')} | "
            f"Partido: {governador.get('SG_PARTIDO')} | "
            f"Situação: {governador.get('DS_SIT_TOT_TURNO')} | "
            f"ID: {governador.get('SQ_CANDIDATO')}"
        )


if __name__ == "__main__":
    try:
        inspecionar()
    except Exception as erro:
        print(f"\nERRO: {erro}")
        sys.exit(1)