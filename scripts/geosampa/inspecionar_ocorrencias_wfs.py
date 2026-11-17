
import json
import requests

WFS_URL = (
    "https://wfs.geosampa.prefeitura.sp.gov.br/"
    "geoserver/geoportal/wfs"
)

CAMADAS = [
    "geoportal:risco_ocorrencia_alagamento",
    "geoportal:risco_ocorrencia_inundacao",
]


def inspecionar_camada(nome_camada):
    print("\n" + "=" * 65)
    print(f"CAMADA: {nome_camada}")
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

    try:
        response = requests.get(
            WFS_URL,
            params=params,
            timeout=60,
        )
        response.raise_for_status()

        dados = response.json()

    except requests.RequestException as erro:
        print(f"Erro na requisição: {erro}")
        return

    except ValueError:
        print("O GeoSampa não retornou um JSON válido.")
        print(response.text[:1000])
        return

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
        print(json.dumps(dados, indent=2, ensure_ascii=False)[:2000])
        return

    geometrias = {
        feicao.get("geometry", {}).get("type", "Sem geometria")
        for feicao in feicoes
    }

    print(f"Tipos de geometria: {', '.join(geometrias)}")

    primeira_feicao = feicoes[0]
    propriedades = primeira_feicao.get("properties", {})

    print("\nCampos encontrados:")

    for campo in propriedades:
        print(f" - {campo}")

    print("\nExemplo de registro:")
    print(
        json.dumps(
            propriedades,
            indent=2,
            ensure_ascii=False,
            default=str,
        )
    )


def main():
    print("INSPEÇÃO DE CAMADAS DO GEOSAMPA")

    for camada in CAMADAS:
        inspecionar_camada(camada)


if __name__ == "__main__":
    main()
