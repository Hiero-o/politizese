
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET


WFS_URL = (
    "https://wfs.geosampa.prefeitura.sp.gov.br/"
    "geoserver/geoportal/wfs"
)

USER_AGENT = "Politizese/0.1 (academic project)"


def local_name(tag):
    """Remove o namespace XML e retorna o nome da tag."""

    return tag.split("}")[-1]


def get_child_text(element, names):
    """Obtém o texto de uma tag filha, independentemente do namespace."""

    for child in element:
        if local_name(child.tag) in names:
            return (child.text or "").strip()

    return None


def request_capabilities(version):
    """Consulta as capacidades do serviço WFS."""

    params = {
        "service": "WFS",
        "version": version,
        "request": "GetCapabilities",
    }

    url = WFS_URL + "?" + urllib.parse.urlencode(params)

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/xml",
        },
    )

    with urllib.request.urlopen(request, timeout=40) as response:
        content = response.read()

    return ET.fromstring(content)


def main():

    versions = ["2.0.0", "1.1.0", "1.0.0"]

    root = None

    for version in versions:

        print(f"Consultando WFS versão {version}...")

        try:
            root = request_capabilities(version)
            print(f"Conexão estabelecida com WFS {version}.\n")
            break

        except Exception as error:
            print(f"Não foi possível utilizar essa versão: {error}\n")

    if root is None:
        raise RuntimeError(
            "Não foi possível consultar o serviço WFS."
        )

    if local_name(root.tag) == "ExceptionReport":
        raise RuntimeError(
            "O GeoSampa retornou uma exceção: "
            + " ".join(root.itertext())
        )

    feature_types = [
        element
        for element in root.iter()
        if local_name(element.tag) == "FeatureType"
    ]

    if not feature_types:
        raise RuntimeError(
            "Nenhuma camada vetorial foi encontrada na resposta."
        )

    search_terms = (
        "alagamento",
        "inundacao",
        "inundação",
        "ocorrencia",
        "ocorrência",
        "hidrologico",
        "hidrológico",
        "hidrologia",
    )

    matches = []

    for feature in feature_types:

        name = get_child_text(feature, {"Name"})
        title = get_child_text(feature, {"Title"})
        crs = get_child_text(
            feature,
            {"DefaultCRS", "DefaultSRS", "SRS"},
        )

        searchable = f"{name or ''} {title or ''}".lower()

        if any(term in searchable for term in search_terms):

            matches.append({
                "name": name,
                "title": title,
                "crs": crs,
            })

    print(f"Total de camadas WFS disponíveis: {len(feature_types)}")
    print(f"Camadas relacionadas à pesquisa: {len(matches)}")

    print("\n========== CAMADAS ENCONTRADAS ==========\n")

    if not matches:
        print("Nenhuma camada correspondente aos termos pesquisados.")
        print("\nAlgumas camadas disponíveis:")

        for feature in feature_types[:20]:
            print(
                get_child_text(feature, {"Name"}),
                "-",
                get_child_text(feature, {"Title"}),
            )

        return

    for index, item in enumerate(matches, start=1):

        print(f"{index}. {item['title'] or 'Sem título'}")
        print(f"   Identificador: {item['name']}")
        print(f"   Sistema de coordenadas: {item['crs']}")
        print()

    print("=========================================")


if __name__ == "__main__":
    main()
