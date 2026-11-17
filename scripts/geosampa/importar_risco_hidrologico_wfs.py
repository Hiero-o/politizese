
import json
import math
import time

from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


# ============================================================
# 1. CONFIGURAÇÃO
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

WFS_URL = (
    "https://wfs.geosampa.prefeitura.sp.gov.br/"
    "geoserver/geoportal/wfs"
)

LAYER_NAME = "geoportal:risco_hidrologico"

PAGE_SIZE = 100

MAX_PAGES = 100

RAW_FILE = (
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
    / "risco_hidrologico_wfs.geojson"
)

METADATA_FILE = OUTPUT_FILE.with_suffix(".meta.json")

USER_AGENT = "Politizese/0.1 (academic project)"


# ============================================================
# 2. REQUISIÇÃO AO WFS
# ============================================================

def request_page(start_index):
    """Obtém uma página de feições do GeoSampa."""

    params = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeNames": LAYER_NAME,
        "outputFormat": "application/json",
        "srsName": "EPSG:4326",
        "count": PAGE_SIZE,
        "startIndex": start_index,
    }

    url = WFS_URL + "?" + urlencode(params)

    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        },
    )

    try:
        with urlopen(request, timeout=90) as response:
            content = response.read().decode("utf-8")

    except Exception as error:
        raise RuntimeError(
            f"Falha ao consultar a página {start_index}: {error}"
        ) from error

    try:
        data = json.loads(content)

    except json.JSONDecodeError as error:
        raise RuntimeError(
            "O servidor retornou conteúdo que não é JSON."
        ) from error

    if data.get("type") != "FeatureCollection":
        raise RuntimeError(
            f"Resposta WFS inválida: {str(data)[:500]}"
        )

    return data


# ============================================================
# 3. IDENTIFICAÇÃO DAS FEIÇÕES
# ============================================================

def get_feature_key(feature):
    """Obtém um identificador estável para evitar duplicações."""

    properties = feature.get("properties", {})

    identifier = properties.get(
        "cd_identificador_risco_hidrologico"
    )

    if identifier is not None:
        return str(identifier)

    feature_id = feature.get("id")

    if feature_id is not None:
        return str(feature_id)

    raise ValueError(
        "Feição recebida sem identificador."
    )


def parse_total(data):
    """Obtém o total de feições informado pelo servidor."""

    total = data.get(
        "numberMatched",
        data.get("totalFeatures"),
    )

    if total is None or str(total).lower() == "unknown":
        return None

    try:
        return int(total)

    except (TypeError, ValueError):
        return None


# ============================================================
# 4. VALIDAÇÃO DAS COORDENADAS
# ============================================================

def iter_positions(coordinates):
    """Percorre recursivamente as posições de uma geometria."""

    if (
        isinstance(coordinates, list)
        and len(coordinates) >= 2
        and isinstance(coordinates[0], (int, float))
        and isinstance(coordinates[1], (int, float))
    ):
        yield coordinates
        return

    if isinstance(coordinates, list):
        for item in coordinates:
            yield from iter_positions(item)


def validate_feature(feature):
    """Valida a geometria e suas coordenadas."""

    geometry = feature.get("geometry")

    if not geometry:
        raise ValueError("Feição sem geometria.")

    geometry_type = geometry.get("type")

    if geometry_type not in {"Polygon", "MultiPolygon"}:
        raise ValueError(
            f"Geometria inesperada: {geometry_type}"
        )

    coordinates = geometry.get("coordinates")

    if not coordinates:
        raise ValueError("Geometria sem coordenadas.")

    positions = list(iter_positions(coordinates))

    if not positions:
        raise ValueError("Nenhuma posição geográfica encontrada.")

    for position in positions:

        longitude = float(position[0])
        latitude = float(position[1])

        if not math.isfinite(longitude):
            raise ValueError("Longitude inválida.")

        if not math.isfinite(latitude):
            raise ValueError("Latitude inválida.")

        if not -180 <= longitude <= 180:
            raise ValueError(
                f"Longitude fora dos limites: {longitude}"
            )

        if not -90 <= latitude <= 90:
            raise ValueError(
                f"Latitude fora dos limites: {latitude}"
            )


# ============================================================
# 5. DOWNLOAD COMPLETO COM PAGINAÇÃO
# ============================================================

def download_all_features():

    all_features = []
    seen_ids = set()

    start_index = 0
    expected_total = None
    page_number = 0
    duplicate_count = 0

    while True:

        page_number += 1

        if page_number > MAX_PAGES:
            raise RuntimeError(
                "Limite de páginas atingido. "
                "Verifique o comportamento do WFS."
            )

        print(
            f"\nConsultando página {page_number} "
            f"(startIndex={start_index})..."
        )

        data = request_page(start_index)

        page_features = data.get("features", [])

        if expected_total is None:
            expected_total = parse_total(data)

            if expected_total is not None:
                print(
                    f"Total informado pelo GeoSampa: "
                    f"{expected_total}"
                )

        if not page_features:
            print("Nenhuma feição adicional retornada.")
            break

        new_features = 0

        for feature in page_features:

            feature_key = get_feature_key(feature)

            if feature_key in seen_ids:
                duplicate_count += 1
                continue

            validate_feature(feature)

            seen_ids.add(feature_key)
            all_features.append(feature)

            new_features += 1

        print(f"Feições recebidas: {len(page_features)}")
        print(f"Novas feições adicionadas: {new_features}")
        print(f"Total acumulado: {len(all_features)}")

        if new_features == 0:
            raise RuntimeError(
                "O servidor retornou uma página sem novas feições. "
                "Possível problema na paginação."
            )

        start_index += len(page_features)

        if (
            expected_total is not None
            and start_index >= expected_total
        ):
            break

        # Pequena pausa entre requisições.
        time.sleep(0.25)

    if expected_total is not None:
        if len(all_features) != expected_total:
            raise RuntimeError(
                "Quantidade final diferente do total informado. "
                f"Esperado: {expected_total}; "
                f"Recebido: {len(all_features)}."
            )

    return {
        "features": all_features,
        "expected_total": expected_total,
        "pages": page_number,
        "duplicates": duplicate_count,
    }


# ============================================================
# 6. COMPARAÇÃO COM O GEOJSON ORIGINAL
# ============================================================

def compare_with_original(wfs_features):
    """Compara os atributos da camada WFS com o arquivo baixado."""

    if not RAW_FILE.exists():
        print(
            "\nArquivo original não encontrado. "
            "Comparação ignorada."
        )
        return None

    with open(RAW_FILE, encoding="utf-8") as file:
        original = json.load(file)

    original_features = original.get("features", [])

    def create_index(features):

        index = {}

        for feature in features:
            key = get_feature_key(feature)
            index[key] = feature.get("properties", {})

        return index

    original_index = create_index(original_features)
    wfs_index = create_index(wfs_features)

    original_ids = set(original_index)
    wfs_ids = set(wfs_index)

    common_ids = original_ids & wfs_ids

    identical_properties = 0
    different_properties = 0

    for key in common_ids:

        if original_index[key] == wfs_index[key]:
            identical_properties += 1

        else:
            different_properties += 1

    comparison = {
        "original_total": len(original_features),
        "wfs_total": len(wfs_features),
        "common_identifiers": len(common_ids),
        "only_in_original": len(original_ids - wfs_ids),
        "only_in_wfs": len(wfs_ids - original_ids),
        "identical_properties": identical_properties,
        "different_properties": different_properties,
    }

    print("\n========== COMPARAÇÃO DE FONTES ==========")

    for field, value in comparison.items():
        print(f"{field}: {value}")

    print("==========================================")

    return comparison


# ============================================================
# 7. SALVAMENTO
# ============================================================

def save_results(features, download_info, comparison):

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    geojson = {
        "type": "FeatureCollection",
        "name": "Risco Hidrologico - GeoSampa WFS",
        "features": features,
    }

    metadata = {
        "source": "GeoSampa - Prefeitura de São Paulo",
        "service": "WFS 2.0.0",
        "layer": LAYER_NAME,
        "requested_crs": "EPSG:4326",
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "total_features": len(features),
        "pages_downloaded": download_info["pages"],
        "duplicates_discarded": download_info["duplicates"],
        "comparison_with_original": comparison,
    }

    with open(
        OUTPUT_FILE,
        mode="w",
        encoding="utf-8",
    ) as file:

        json.dump(
            geojson,
            file,
            ensure_ascii=False,
            indent=2,
        )

    with open(
        METADATA_FILE,
        mode="w",
        encoding="utf-8",
    ) as file:

        json.dump(
            metadata,
            file,
            ensure_ascii=False,
            indent=2,
        )

    print(f"\nGeoJSON salvo em: {OUTPUT_FILE}")
    print(f"Metadados salvos em: {METADATA_FILE}")


# ============================================================
# 8. EXECUÇÃO
# ============================================================

def main():

    print("\n========== IMPORTAÇÃO GEO SAMPA ==========\n")

    print(f"Camada: {LAYER_NAME}")
    print(f"Tamanho de cada página: {PAGE_SIZE}")

    download_info = download_all_features()

    features = download_info["features"]

    comparison = compare_with_original(features)

    save_results(
        features,
        download_info,
        comparison,
    )

    print("\n========== IMPORTAÇÃO CONCLUÍDA ==========")

    print(f"Total de polígonos: {len(features)}")
    print(f"Páginas consultadas: {download_info['pages']}")
    print(
        f"Duplicatas descartadas: "
        f"{download_info['duplicates']}"
    )

    print("===========================================\n")


if __name__ == "__main__":

    try:
        main()

    except (RuntimeError, ValueError, OSError) as error:
        raise SystemExit(f"\nERRO: {error}")
