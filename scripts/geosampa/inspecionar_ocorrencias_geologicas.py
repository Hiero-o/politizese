
import json
import requests

WFS_URL = (
    "https://wfs.geosampa.prefeitura.sp.gov.br/"
    "geoserver/geoportal/wfs"
)

CAMADAS = {
    "deslizamento": {
        "nome": "geoportal:risco_ocorrencia_deslizamento",
        "descricao": "Deslizamentos",
    },
    "risco_deslizamento": {
        "nome": "geoportal:risco_ocorrencia_risco_deslizamento",
        "descricao": "Risco de deslizamento",
    },
    "queda_arvore": {
        "nome": "geoportal:risco_ocorrencia_queda_arvore",
        "descricao": "Queda de árvores",
    },
}


def inspecionar_camada(chave, configuracao):
    nome_camada = configuracao["nome"]

    print("\n" + "=" * 65)
    print(f"CAMADA: {configuracao['descricao']}")
    print(f"Nome WFS: {nome_camada}")
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
        print("Resposta inválida: o servidor não retornou JSON.")
        print(response.text[:1000])
        return

    feicoes = dados.get("features", [])

    total = (
        dados.get("totalFeatures")
        or dados.get("numberMatched")
        or "Não informado"
    )

    print(f"\nTotal informado pelo GeoSampa: {total}")
    print(f"Feições recebidas: {len(feicoes)}")

    if not feicoes:
        print("\nNenhuma feição retornada.")
        print(json.dumps(dados, indent=2, ensure_ascii=False)[:2000])
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

    primeira_feicao = feicoes[0]
    propriedades = primeira_feicao.get("properties") or {}

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
    print("POLITIZE-SE | INSPEÇÃO DE OCORRÊNCIAS GEOLÓGICAS")

    for chave, configuracao in CAMADAS.items():
        inspecionar_camada(chave, configuracao)

    print("\nInspeção finalizada.")


if __name__ == "__main__":
    main()
