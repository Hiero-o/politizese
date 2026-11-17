
import json
from collections import Counter
from pathlib import Path

from pyproj import Transformer


# ============================================================
# 1. CAMINHOS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

INPUT_FILE = (
    PROJECT_ROOT
    / "data"
    / "geosampa"
    / "raw"
    / "risco_hidrologico.geojson"
)

OUTPUT_FILE = (
    PROJECT_ROOT
    / "data"
    / "geosampa"
    / "processed"
    / "risco_hidrologico.geojson"
)


# ============================================================
# 2. SISTEMAS DE COORDENADAS
# ============================================================

SOURCE_CRS = "EPSG:31983"
TARGET_CRS = "EPSG:4326"

transformer = Transformer.from_crs(
    SOURCE_CRS,
    TARGET_CRS,
    always_xy=True,
)


# ============================================================
# 3. TRANSFORMAÇÃO DAS COORDENADAS
# ============================================================

def transform_coordinates(coordinates):
    """
    Converte recursivamente coordenadas UTM para longitude
    e latitude.

    Funciona com estruturas Polygon e MultiPolygon.
    """

    # Encontramos um par de coordenadas [x, y].
    if (
        isinstance(coordinates, list)
        and len(coordinates) >= 2
        and isinstance(coordinates[0], (int, float))
        and isinstance(coordinates[1], (int, float))
    ):

        x = coordinates[0]
        y = coordinates[1]

        longitude, latitude = transformer.transform(x, y)

        if not (-180 <= longitude <= 180):
            raise ValueError("Longitude inválida após conversão.")

        if not (-90 <= latitude <= 90):
            raise ValueError("Latitude inválida após conversão.")

        result = [
            round(longitude, 7),
            round(latitude, 7),
        ]

        # Preserva dimensões adicionais, se existirem.
        result.extend(coordinates[2:])

        return result

    # Caso seja uma estrutura aninhada, percorremos seus elementos.
    if isinstance(coordinates, list):
        return [
            transform_coordinates(item)
            for item in coordinates
        ]

    raise ValueError("Estrutura de coordenadas inválida.")


# ============================================================
# 4. PROCESSAMENTO DO GEOJSON
# ============================================================

def main():

    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Arquivo não encontrado: {INPUT_FILE}"
        )

    print("Lendo GeoJSON original...")

    with open(INPUT_FILE, encoding="utf-8") as file:
        original = json.load(file)

    if original.get("type") != "FeatureCollection":
        raise ValueError("O arquivo não é uma FeatureCollection.")

    source_crs = (
        original.get("crs", {})
        .get("properties", {})
        .get("name", "")
    )

    if "31983" not in source_crs:
        raise ValueError(
            f"CRS inesperado no arquivo: {source_crs}"
        )

    features = original.get("features", [])

    if not features:
        raise ValueError("Nenhuma feição encontrada.")

    print(f"Feições encontradas: {len(features)}")
    print(f"CRS original: {source_crs}")
    print(f"CRS de destino: {TARGET_CRS}")

    risk_counter = Counter()
    geometry_counter = Counter()

    for feature in features:

        geometry = feature.get("geometry")

        if not geometry:
            raise ValueError(
                f"Feição {feature.get('id')} sem geometria."
            )

        geometry_type = geometry.get("type")

        if geometry_type not in {"Polygon", "MultiPolygon"}:
            raise ValueError(
                f"Geometria inesperada: {geometry_type}"
            )

        geometry_counter[geometry_type] += 1

        geometry["coordinates"] = transform_coordinates(
            geometry["coordinates"]
        )

        properties = feature.get("properties", {})

        risk_grade = properties.get(
            "tx_grau_risco_hidrologico",
            "NÃO INFORMADO",
        )

        risk_counter[risk_grade] += 1

    # ========================================================
    # 5. CONSTRUÇÃO DO NOVO GEOJSON
    # ========================================================

    converted = {
        "type": "FeatureCollection",

        "name": "Risco Hidrológico - GeoSampa",

        "metadata": {
            "source": "GeoSampa - Prefeitura de São Paulo",
            "source_file": INPUT_FILE.name,
            "source_crs": SOURCE_CRS,
            "target_crs": TARGET_CRS,
            "source_timestamp": original.get("timeStamp"),
            "total_features": len(features),
            "geometry_types": dict(geometry_counter),
            "risk_grades": dict(risk_counter),
        },

        "features": features,
    }

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with open(
        OUTPUT_FILE,
        mode="w",
        encoding="utf-8",
    ) as file:

        json.dump(
            converted,
            file,
            ensure_ascii=False,
            indent=2,
        )

    # ========================================================
    # 6. RELATÓRIO
    # ========================================================

    print("\n========== CONVERSÃO FINALIZADA ==========")

    print(f"Polígonos processados: {len(features)}")

    print("\nDistribuição dos graus de risco:")

    for grade, quantity in sorted(risk_counter.items()):
        print(f"  {grade}: {quantity}")

    print("\nTipos de geometria:")

    for geometry_type, quantity in geometry_counter.items():
        print(f"  {geometry_type}: {quantity}")

    print(f"\nArquivo gerado: {OUTPUT_FILE}")

    print("===========================================\n")


if __name__ == "__main__":
    main()
