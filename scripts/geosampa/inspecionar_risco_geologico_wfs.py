
import unicodedata
import requests
import xml.etree.ElementTree as ET

WFS_URL = (
    "https://wfs.geosampa.prefeitura.sp.gov.br/"
    "geoserver/geoportal/wfs"
)


def normalizar(texto):
    texto = texto.lower()

    return "".join(
        caractere
        for caractere in unicodedata.normalize("NFD", texto)
        if unicodedata.category(caractere) != "Mn"
    )


def obter_camadas():
    print("Consultando catálogo WFS do GeoSampa...")

    params = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetCapabilities",
    }

    response = requests.get(
        WFS_URL,
        params=params,
        timeout=90,
    )

    response.raise_for_status()

    raiz = ET.fromstring(response.content)

    camadas = []

    for elemento in raiz.iter():
        if elemento.tag.split("}")[-1] != "FeatureType":
            continue

        dados = {}

        for filho in elemento:
            nome = filho.tag.split("}")[-1]

            if nome in ("Name", "Title", "DefaultCRS", "DefaultSRS"):
                dados[nome] = filho.text

        nome_tecnico = dados.get("Name", "")
        titulo = dados.get("Title", "")

        texto = normalizar(
            f"{nome_tecnico} {titulo}"
        )

        if "risco" in texto and "geolog" in texto:
            camadas.append(dados)

    return camadas


def inspecionar_feicoes(nome_camada):
    print("\n" + "=" * 65)
    print(f"INSPECIONANDO: {nome_camada}")
    print("=" * 65)

    params = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeNames": nome_camada,
        "outputFormat": "application/json",
        "srsName": "EPSG:4326",
        "count": 5,
        "startIndex": 0,
    }

    response = requests.get(
        WFS_URL,
        params=params,
        timeout=90,
    )

    response.raise_for_status()

    dados = response.json()

    feicoes = dados.get("features", [])

    total = (
        dados.get("totalFeatures")
        or dados.get("numberMatched")
        or "Não informado"
    )

    print(f"Total informado: {total}")
    print(f"Feições recebidas: {len(feicoes)}")

    if not feicoes:
        print("Nenhuma feição retornada.")
        return

    geometrias = {
        (feicao.get("geometry") or {}).get(
            "type",
            "Sem geometria",
        )
        for feicao in feicoes
    }

    print("\nTipos de geometria:")

    for geometria in geometrias:
        print(f" - {geometria}")

    propriedades = feicoes[0].get("properties") or {}

    print("\nCampos encontrados:")

    for campo in propriedades:
        print(f" - {campo}")

    print("\nExemplo de registro:")

    for campo, valor in propriedades.items():
        print(f"{campo}: {valor}")


def main():
    print("\nPOLITIZE-SE | DESCOBERTA DE RISCO GEOLÓGICO")
    print("=" * 65)

    camadas = obter_camadas()

    if not camadas:
        print("\nNenhuma camada correspondente encontrada.")
        return

    print(f"\nCamadas encontradas: {len(camadas)}")

    for camada in camadas:
        print("\nNome técnico:", camada.get("Name"))
        print("Título:", camada.get("Title"))
        print("CRS:", camada.get("DefaultCRS") or camada.get("DefaultSRS"))

    for camada in camadas:
        nome = camada.get("Name")

        if nome:
            try:
                inspecionar_feicoes(nome)
            except (requests.RequestException, ValueError) as erro:
                print(f"\nErro ao consultar {nome}: {erro}")


if __name__ == "__main__":
    main()
