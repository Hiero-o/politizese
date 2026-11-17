
import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path



# 1. CONFIGURAÇÃO DOS CAMINHOS


PROJECT_ROOT = Path(__file__).resolve().parents[2]

INPUT_FILE = PROJECT_ROOT / "data" / "obras" / "raw" / "Obras.csv"
OUTPUT_FILE = PROJECT_ROOT / "data" / "obras" / "processed" / "obras_sp.geojson"



# 2. FUNÇÕES DE NORMALIZAÇÃO


def get_value(row, column):
    """Obtém um campo do CSV, removendo espaços desnecessários."""

    value = row.get(column)

    if value is None:
        return None

    value = value.strip()

    return value if value else None


def parse_coordinate(value):
    """Converte uma coordenada para float."""

    if not value:
        raise ValueError("Coordenada vazia")

    coordinate = float(value.replace(",", "."))

    if not -180 <= coordinate <= 180:
        raise ValueError("Coordenada fora dos limites geográficos")

    return coordinate


def parse_date(value):
    """Converte datas brasileiras para o padrão ISO."""

    if not value:
        return None

    try:
        return datetime.strptime(
            value.strip(),
            "%d/%m/%Y"
        ).date().isoformat()

    except ValueError:
        # Preserva o valor original caso não consiga interpretar.
        return value.strip()


def normalize_status(value):
    """Padroniza o texto dos status."""

    if not value:
        return "NÃO INFORMADO"

    return " ".join(value.upper().split())



# 3. CONVERSÃO DE UMA OBRA PARA GEOJSON


def build_feature(row):
    """Transforma uma linha do CSV em uma Feature GeoJSON."""

    latitude = parse_coordinate(get_value(row, "LATITUDE"))
    longitude = parse_coordinate(get_value(row, "LONGITUDE"))

    # O GeoJSON utiliza longitude primeiro e latitude depois.
    coordinates = [longitude, latitude]

    properties = {
        "origem_dados": get_value(row, "ORIGEM DOS DADOS"),
        "codigo_obra": get_value(row, "CÓDIGO OBRA"),
        "processo": get_value(row, "PROCESSO"),

        "secretaria_contratante": get_value(
            row, "SECRETARIA CONTRATANTE"
        ),

        "secretaria_responsavel": get_value(
            row, "SECRETARIA RESPONSÁVEL"
        ),

        "subprefeitura": get_value(row, "SUBPREFEITURA"),
        "regiao": get_value(row, "REGIÃO"),
        "distrito": get_value(row, "DISTRITO"),
        "endereco": get_value(row, "LOCAL"),

        "nome_obra": get_value(row, "NOME DA OBRA"),
        "escopo_contrato": get_value(row, "ESCOPO DO CONTRATO"),

        "categoria": get_value(row, "CATEGORIA"),
        "subcategoria": get_value(row, "SUBCATEGORIA"),
        "classificacao": get_value(row, "CLASSIFICAÇÃO"),

        "status": normalize_status(
            get_value(row, "STATUS")
        ),

        "fontes_recurso": get_value(row, "FONTES DE RECURSO"),

        "data_inicio": parse_date(
            get_value(row, "DT INÍCIO DA OBRA")
        ),

        "data_termino_prevista": parse_date(
            get_value(row, "DT TÉRMINO DA OBRA")
        ),

        "numero_contrato": get_value(row, "NÚMERO DO CONTRATO"),
        "empresa_contratada": get_value(row, "EMPRESA CONTRATADA"),

        # Mantemos o CNPJ como texto para não perder dígitos.
        "cnpj_contratada": get_value(row, "CNPJ CONTRATADA"),

        "valor_total_contrato": get_value(
            row, "VALOR TOTAL DO CONTRATO"
        )
    }

    return {
        "type": "Feature",
        "id": properties["codigo_obra"],
        "geometry": {
            "type": "Point",
            "coordinates": coordinates
        },
        "properties": properties
    }



# 4. LEITURA E EXPORTAÇÃO DA BASE


def main():

    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Arquivo não encontrado: {INPUT_FILE}\n"
            "Coloque Obras.csv dentro de data/obras/raw/."
        )

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    features = []
    invalid_records = 0
    status_counter = Counter()

    with open(
        INPUT_FILE,
        mode="r",
        encoding="utf-8-sig",
        newline=""
    ) as csv_file:

        reader = csv.DictReader(
            csv_file,
            delimiter=";"
        )

        required_columns = {
            "CÓDIGO OBRA",
            "LOCAL",
            "LATITUDE",
            "LONGITUDE",
            "STATUS"
        }

        missing = required_columns - set(reader.fieldnames or [])

        if missing:
            raise ValueError(
                f"Colunas obrigatórias ausentes: {sorted(missing)}"
            )

        total_records = 0

        for row in reader:

            total_records += 1

            try:
                feature = build_feature(row)

                features.append(feature)

                status_counter[
                    feature["properties"]["status"]
                ] += 1

            except (ValueError, TypeError):
                invalid_records += 1

    geojson = {
        "type": "FeatureCollection",

        "metadata": {
            "source": "Obras Abertas - Prefeitura de São Paulo",
            "source_file": INPUT_FILE.name,
            "generated_at": datetime.now(
                timezone.utc
            ).isoformat(timespec="seconds"),
            "records_read": total_records,
            "features_generated": len(features),
            "invalid_records": invalid_records
        },

        "features": features
    }

    with open(
        OUTPUT_FILE,
        mode="w",
        encoding="utf-8"
    ) as output_file:

        json.dump(
            geojson,
            output_file,
            ensure_ascii=False,
            indent=2
        )

    
    # RELATÓRIO
    

    print("\n========== IMPORTAÇÃO DE OBRAS ==========\n")

    print(f"Registros lidos: {total_records}")
    print(f"Obras exportadas: {len(features)}")
    print(f"Registros inválidos: {invalid_records}")

    print("\nDistribuição por status:")

    for status, quantity in sorted(status_counter.items()):
        print(f"  {status}: {quantity}")

    print(f"\nArquivo gerado: {OUTPUT_FILE}")

    print("\n=========================================\n")


if __name__ == "__main__":
    main()
