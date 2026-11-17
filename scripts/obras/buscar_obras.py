
import argparse
import json
import math
import re
import time
import unicodedata

from datetime import date, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen



# 1. CONFIGURAÇÃO


PROJECT_ROOT = Path(__file__).resolve().parents[2]

GEOJSON_FILE = (
    PROJECT_ROOT
    / "data"
    / "obras"
    / "processed"
    / "obras_sp.geojson"
)

OUTPUT_FILE = (
    PROJECT_ROOT
    / "data"
    / "obras"
    / "processed"
    / "resultado_busca.json"
)

CACHE_FILE = (
    PROJECT_ROOT
    / "data"
    / "obras"
    / "cache"
    / "geocoding_cache.json"
)

USER_AGENT = (
    "Politizese/0.1 "
    "(consulta de enderecos iniciada pelo usuario)"
)

# Obras que queremos destacar na pesquisa.
PRIORITY_STATUSES = {
    "EM ANDAMENTO",
    "SUSPENSA",
    "NAO INICIADA",
    "NAO INICIADO",
}

COMPLETED_STATUS = "CONCLUIDA"

EARTH_RADIUS_KM = 6371.0088



# 2. UTILITÁRIOS HTTP


def request_json(url, timeout=20):
    """Executa uma requisição HTTP e interpreta a resposta JSON."""

    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        },
    )

    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    except HTTPError as error:
        raise RuntimeError(
            f"Erro HTTP {error.code} ao acessar {url}"
        ) from error

    except URLError as error:
        raise RuntimeError(
            f"Não foi possível acessar o serviço: {error.reason}"
        ) from error

    except TimeoutError as error:
        raise RuntimeError(
            "A conexão demorou demais para responder."
        ) from error



# 3. CONSULTA DE CEP


def get_address_from_cep(cep):
    """Consulta o ViaCEP e retorna um endereço formatado."""

    digits = re.sub(r"\D", "", cep)

    if len(digits) != 8:
        raise ValueError("O CEP precisa possuir 8 dígitos.")

    url = f"https://viacep.com.br/ws/{digits}/json/"

    data = request_json(url)

    if data.get("erro"):
        raise ValueError("CEP não encontrado no ViaCEP.")

    logradouro = (data.get("logradouro") or "").strip()
    bairro = (data.get("bairro") or "").strip()

    # Remove complementos regionais entre parênteses.
    # Exemplo: Jardim Paulistano (Zona Norte)
    # passa a ser Jardim Paulistano.
    bairro = re.sub(r"\s*\([^)]*\)", "", bairro).strip()

    parts = [
        logradouro,
        bairro,
        data.get("localidade"),
        data.get("uf"),
        "Brasil",
    ]

    if not logradouro:
        parts.insert(0, f"CEP {digits}")

    return ", ".join(
        part.strip()
        for part in parts
        if part and part.strip()
    )



# 4. CACHE DE GEOCODIFICAÇÃO


def load_cache():
    """Carrega os endereços já geocodificados."""

    if not CACHE_FILE.exists():
        return {
            "last_request_at": 0,
            "queries": {},
        }

    with open(CACHE_FILE, encoding="utf-8") as file:
        cache = json.load(file)

    cache.setdefault("last_request_at", 0)
    cache.setdefault("queries", {})

    return cache


def save_cache(cache):
    CACHE_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with open(
        CACHE_FILE,
        mode="w",
        encoding="utf-8",
    ) as file:
        json.dump(
            cache,
            file,
            ensure_ascii=False,
            indent=2,
        )


def normalize_query(query):
    """Normaliza o endereço utilizado como chave do cache."""

    return " ".join(query.lower().split())



# 5. GEOCODIFICAÇÃO COM NOMINATIM


def geocode_address(address):
    """Geocodifica um endereço com tentativas alternativas e cache."""

    cache = load_cache()
    query_key = normalize_query(address)

    if query_key in cache["queries"]:
        print("Endereço encontrado no cache.")
        return cache["queries"][query_key]

    # Remove complementos entre parênteses.
    clean_address = re.sub(
        r"\s*\([^)]*\)",
        "",
        address
    )

    parts = [
        part.strip()
        for part in clean_address.split(",")
        if part.strip()
    ]

    # Tentativas:
    # 1. Endereço completo.
    # 2. Endereço sem complementos.
    # 3. Apenas logradouro e município.
    queries = [
        address,
        clean_address,
    ]

    if parts:
        street_query = (
            f"{parts[0]}, São Paulo, SP, Brasil"
        )
        queries.append(street_query)

    # Remove tentativas repetidas.
    queries = list(dict.fromkeys(queries))

    result = None

    for query in queries:

        print(f"Geocodificando: {query}")

        # Respeita o intervalo mínimo entre consultas.
        elapsed = time.time() - float(
            cache["last_request_at"]
        )

        if elapsed < 1.1:
            time.sleep(1.1 - elapsed)

        parameters = {
            "q": query,
            "format": "jsonv2",
            "limit": 1,
            "countrycodes": "br",
        }

        url = (
            "https://nominatim.openstreetmap.org/search?"
            + urlencode(parameters)
        )

        try:
            results = request_json(url)

        finally:
            cache["last_request_at"] = time.time()
            save_cache(cache)

        if results:
            result = {
                "latitude": float(results[0]["lat"]),
                "longitude": float(results[0]["lon"]),
                "display_name": results[0].get("display_name"),
                "matched_query": query,
            }

            break

    if not result:
        raise ValueError(
            "Não foi possível localizar esse endereço. "
            "Tente informar um ponto de referência ou "
            "o nome de um estabelecimento próximo."
        )

    cache["queries"][query_key] = result
    save_cache(cache)

    return result



# 6. CÁLCULO DE DISTÂNCIA - HAVERSINE


def calculate_distance(
    latitude_1,
    longitude_1,
    latitude_2,
    longitude_2,
):
    """
    Calcula a distância em quilômetros entre dois pontos
    geográficos utilizando a fórmula de Haversine.
    """

    lat1 = math.radians(latitude_1)
    lon1 = math.radians(longitude_1)

    lat2 = math.radians(latitude_2)
    lon2 = math.radians(longitude_2)

    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1

    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1)
        * math.cos(lat2)
        * math.sin(delta_lon / 2) ** 2
    )

    c = 2 * math.atan2(
        math.sqrt(a),
        math.sqrt(1 - a),
    )

    return EARTH_RADIUS_KM * c



# 7. NORMALIZAÇÃO DOS STATUS


def normalize_status(status):
    """Remove acentos e espaços desnecessários."""

    if not status:
        return ""

    normalized = unicodedata.normalize(
        "NFKD",
        status,
    )

    normalized = "".join(
        character
        for character in normalized
        if not unicodedata.combining(character)
    )

    return " ".join(normalized.upper().split())



# 8. TRATAMENTO DE DATAS


def parse_date(value):
    """Converte datas conhecidas para date."""

    if not value:
        return date.min

    formats = [
        "%Y-%m-%d",
        "%d/%m/%Y",
    ]

    for format_string in formats:
        try:
            return datetime.strptime(
                value,
                format_string,
            ).date()

        except ValueError:
            continue

    return date.min



# 9. LEITURA DAS OBRAS


def load_works():
    """Carrega a base GeoJSON de obras."""

    if not GEOJSON_FILE.exists():
        raise FileNotFoundError(
            f"Base GeoJSON não encontrada: {GEOJSON_FILE}\n"
            "Execute atualizar_base.py primeiro."
        )

    with open(
        GEOJSON_FILE,
        encoding="utf-8",
    ) as file:
        data = json.load(file)

    return data["features"]



# 10. BUSCA DAS OBRAS PRÓXIMAS


def find_nearby_works(
    latitude,
    longitude,
    radius_km,
    active_limit,
    completed_limit,
):
    """Localiza e organiza as obras dentro do raio informado."""

    features = load_works()

    priority_works = []
    completed_works = []

    for feature in features:

        geometry = feature.get("geometry")

        if not geometry or geometry.get("type") != "Point":
            continue

        coordinates = geometry.get("coordinates", [])

        if len(coordinates) != 2:
            continue

        work_longitude = float(coordinates[0])
        work_latitude = float(coordinates[1])

        distance = calculate_distance(
            latitude,
            longitude,
            work_latitude,
            work_longitude,
        )

        if distance > radius_km:
            continue

        properties = feature.get("properties", {})

        work = dict(properties)

        work["codigo_obra"] = (
            work.get("codigo_obra")
            or feature.get("id")
        )

        work["distancia_km"] = round(distance, 2)

        status = normalize_status(work.get("status"))

        if status in PRIORITY_STATUSES:
            priority_works.append(work)

        elif status == COMPLETED_STATUS:
            completed_works.append(work)

    # Obras em andamento, suspensas ou não iniciadas:
    # priorizamos as que estão fisicamente mais próximas.
    priority_works.sort(
        key=lambda work: work["distancia_km"]
    )

    priority_works = priority_works[:active_limit]

    # Concluídas:
    # ordenamos pela data informada pela Prefeitura.
    # Essa data não representa necessariamente a confirmaçãoda conclusão física da obra.
    completed_works.sort(
        key=lambda work: (
            parse_date(work.get("data_termino_prevista")),
            -work["distancia_km"],
        ),
        reverse=True,
    )

    completed_works = completed_works[:completed_limit]

    return priority_works, completed_works



# 11. EXIBIÇÃO DOS RESULTADOS


def print_works(title, works):

    print(f"\n{'=' * 60}")
    print(title)
    print(f"{'=' * 60}")

    if not works:
        print("Nenhuma obra encontrada nessa categoria.")
        return

    for index, work in enumerate(works, start=1):

        print(f"\n{index}. {work.get('nome_obra') or 'Obra sem nome'}")

        print(f"   Status: {work.get('status')}")
        print(f"   Distância: {work['distancia_km']} km")

        print(f"   Endereço: {work.get('endereco') or 'Não informado'}")

        print(f"   Distrito: {work.get('distrito') or 'Não informado'}")

        print(
            "   Subprefeitura: "
            f"{work.get('subprefeitura') or 'Não informado'}"
        )

        if work.get("data_termino_prevista"):
            print(
                "   Término informado: "
                f"{work['data_termino_prevista']}"
            )

        if work.get("valor_total_contrato"):
            print(
                "   Valor: "
                f"R$ {work['valor_total_contrato']}"
            )



# 12. EXECUÇÃO PRINCIPAL


def main():

    parser = argparse.ArgumentParser(
        description="Busca obras públicas próximas de um endereço."
    )

    location_group = parser.add_mutually_exclusive_group(
        required=True
    )

    location_group.add_argument(
        "--cep",
        help="CEP de referência.",
    )

    location_group.add_argument(
        "--endereco",
        help="Endereço de referência.",
    )

    parser.add_argument(
        "--raio",
        type=float,
        default=3,
        help="Raio da pesquisa em quilômetros. Padrão: 3.",
    )

    parser.add_argument(
        "--limite",
        type=int,
        default=20,
        help="Quantidade máxima de obras prioritárias. Padrão: 20.",
    )

    parser.add_argument(
        "--concluidas",
        type=int,
        default=10,
        help="Quantidade de obras concluídas recentes. Padrão: 10.",
    )

    args = parser.parse_args()

    if args.raio <= 0:
        parser.error("--raio precisa ser maior que zero.")

    if args.limite <= 0:
        parser.error("--limite precisa ser maior que zero.")

    if args.concluidas < 0:
        parser.error("--concluidas não pode ser negativo.")

    
    # RESOLVE O ENDEREÇO
    

    if args.cep:

        print("\nConsultando CEP...")

        address = get_address_from_cep(args.cep)

    else:

        address = args.endereco.strip()

        if not address:
            parser.error("Informe um endereço válido.")

        # A base de obras é da cidade de São Paulo.
        if "sao paulo" not in normalize_status(address).lower():
            address += ", São Paulo, SP, Brasil"

    print(f"\nEndereço utilizado: {address}")

    
    # GEOCODIFICAÇÃO
    

    location = geocode_address(address)

    latitude = location["latitude"]
    longitude = location["longitude"]

    print(f"\nLatitude: {latitude}")
    print(f"Longitude: {longitude}")

    print(
        f"Localização encontrada: "
        f"{location.get('display_name') or address}"
    )

    
    # BUSCA DAS OBRAS
    

    print(f"\nPesquisando obras em um raio de {args.raio} km...")

    priority_works, completed_works = find_nearby_works(
        latitude=latitude,
        longitude=longitude,
        radius_km=args.raio,
        active_limit=args.limite,
        completed_limit=args.concluidas,
    )

    print_works(
        "OBRAS EM ANDAMENTO, SUSPENSAS OU NÃO INICIADAS",
        priority_works,
    )

    print_works(
        "OBRAS CONCLUÍDAS MAIS RECENTES",
        completed_works,
    )

    
    # EXPORTAÇÃO DO RESULTADO
    

    result = {
        "consulta": {
            "endereco": address,
            "latitude": latitude,
            "longitude": longitude,
            "raio_km": args.raio,
            "data_consulta": datetime.now().astimezone().isoformat(
                timespec="seconds"
            ),
        },

        "obras_prioritarias": priority_works,
        "obras_concluidas_recentes": completed_works,

        "metadata": {
            "total_obras_prioritarias": len(priority_works),
            "total_obras_concluidas": len(completed_works),
            "fonte": "Obras Abertas - Prefeitura de São Paulo",
            "geocodificacao": "OpenStreetMap / Nominatim",
        },
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
            result,
            file,
            ensure_ascii=False,
            indent=2,
        )

    print("\n" + "=" * 60)
    print("PESQUISA FINALIZADA")
    print("=" * 60)

    print(f"Obras prioritárias: {len(priority_works)}")
    print(f"Obras concluídas: {len(completed_works)}")
    print(f"\nResultado salvo em: {OUTPUT_FILE}")

    print(
        "\nGeocodificação: © OpenStreetMap contributors "
        "(Nominatim)."
    )


if __name__ == "__main__":

    try:
        main()

    except (ValueError, RuntimeError, FileNotFoundError) as error:
        raise SystemExit(f"\nERRO: {error}")
