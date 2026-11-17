
import json
import math
from datetime import datetime
from pathlib import Path

import requests



# CONFIGURAÇÕES


PROJECT_ROOT = Path(__file__).resolve().parents[2]

WFS_URL = (
    "https://wfs.geosampa.prefeitura.sp.gov.br/"
    "geoserver/geoportal/wfs"
)

OUTPUT_DIR = (
    PROJECT_ROOT
    / "data"
    / "geosampa"
    / "processed"
)

TAMANHO_PAGINA = 100


CAMADAS = {
    "alagamento": {
        "nome": "geoportal:risco_ocorrencia_alagamento",
        "tipo_esperado": "ALAGAMENTO",
        "arquivo": "ocorrencias_alagamento.geojson",
    },
    "inundacao": {
        "nome": "geoportal:risco_ocorrencia_inundacao",
        "tipo_esperado": "INUNDACAO",
        "arquivo": "ocorrencias_inundacao.geojson",
    },
    "deslizamento": {
        "nome": "geoportal:risco_ocorrencia_deslizamento",
        "tipo_esperado": "DESLIZAMENTO",
        "arquivo": "ocorrencias_deslizamento.geojson",
    },
    "queda_arvore": {
        "nome": "geoportal:risco_ocorrencia_queda_arvore",
        "tipo_esperado": "QUEDA DE ARVORE",
        "arquivo": "ocorrencias_queda_arvore.geojson",
    },
}




# CONSULTA AO WFS


def consultar_pagina(nome_camada, inicio):
    params = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeNames": nome_camada,
        "outputFormat": "application/json",
        "srsName": "EPSG:4326",
        "count": TAMANHO_PAGINA,
        "startIndex": inicio,
    }

    response = requests.get(
        WFS_URL,
        params=params,
        timeout=90,
    )

    response.raise_for_status()

    try:
        return response.json()
    except ValueError as erro:
        raise RuntimeError(
            "O GeoSampa retornou uma resposta que não é JSON."
        ) from erro


def obter_total(dados):
    valor = (
        dados.get("totalFeatures")
        or dados.get("numberMatched")
    )

    if valor is None:
        return None

    try:
        return int(valor)
    except (ValueError, TypeError):
        return None



# VALIDAÇÃO DAS FEIÇÕES


def validar_feicao(feicao, tipo_esperado):
    if feicao.get("type") != "Feature":
        raise ValueError("Registro não é uma Feature GeoJSON.")

    propriedades = feicao.get("properties") or {}

    identificador = propriedades.get("cd_identificador")

    if identificador is None or not str(identificador).strip():
        raise ValueError("Feição sem cd_identificador.")

    tipo = propriedades.get("dc_tipo_ocorrencia")

    if str(tipo).strip().upper() != tipo_esperado:
        raise ValueError(
            f"Tipo de ocorrência inesperado no ID "
            f"{identificador}: {tipo}"
        )

    geometria = feicao.get("geometry")

    if not geometria or geometria.get("type") != "Point":
        raise ValueError(
            f"Geometria inválida no ID {identificador}."
        )

    coordenadas = geometria.get("coordinates")

    if not isinstance(coordenadas, list) or len(coordenadas) < 2:
        raise ValueError(
            f"Coordenadas inválidas no ID {identificador}."
        )

    longitude, latitude = coordenadas[:2]

    if not isinstance(longitude, (int, float)):
        raise ValueError("Longitude não numérica.")

    if not isinstance(latitude, (int, float)):
        raise ValueError("Latitude não numérica.")

    if not math.isfinite(longitude) or not math.isfinite(latitude):
        raise ValueError("Coordenadas não finitas.")

    if not (-180 <= longitude <= 180):
        raise ValueError("Longitude fora do intervalo válido.")

    if not (-90 <= latitude <= 90):
        raise ValueError("Latitude fora do intervalo válido.")

    return str(identificador).strip()



# IMPORTAÇÃO DE UMA CAMADA


def importar_camada(chave, configuracao):
    nome_camada = configuracao["nome"]
    tipo_esperado = configuracao["tipo_esperado"]
    nome_arquivo = configuracao["arquivo"]

    print("\n" + "=" * 65)
    print(f"IMPORTANDO: {nome_camada}")
    print("=" * 65)

    feicoes_por_id = {}
    total_informado = None
    paginas = 0
    duplicatas = 0
    inicio = 0

    while True:
        paginas += 1

        if paginas > 100:
            raise RuntimeError(
                "Limite de páginas excedido. "
                "Verifique a paginação do GeoSampa."
            )

        print(
            f"\nConsultando página {paginas} "
            f"(startIndex={inicio})..."
        )

        dados = consultar_pagina(nome_camada, inicio)

        if total_informado is None:
            total_informado = obter_total(dados)

            print(
                "Total informado pelo GeoSampa: "
                f"{total_informado}"
            )

        pagina_feicoes = dados.get("features", [])

        if not pagina_feicoes:
            break

        print(f"Feições recebidas: {len(pagina_feicoes)}")

        for feicao in pagina_feicoes:
            identificador = validar_feicao(
                feicao,
                tipo_esperado,
            )

            if identificador in feicoes_por_id:
                if feicoes_por_id[identificador] != feicao:
                    raise RuntimeError(
                        f"ID {identificador} apareceu com "
                        "informações diferentes na mesma camada."
                    )

                duplicatas += 1
                continue

            feicoes_por_id[identificador] = feicao

        print(
            f"Total acumulado: {len(feicoes_por_id)}"
        )

        inicio += len(pagina_feicoes)

        if total_informado is not None:
            if inicio >= total_informado:
                break

        if len(pagina_feicoes) < TAMANHO_PAGINA:
            break

    feicoes = list(feicoes_por_id.values())

    if total_informado is not None:
        if len(feicoes) != total_informado:
            raise RuntimeError(
                f"Quantidade final diferente da informada pelo WFS: "
                f"{len(feicoes)} recebidas, "
                f"{total_informado} esperadas."
            )

    
    # GERAÇÃO DO GEOJSON
    

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    caminho_geojson = OUTPUT_DIR / nome_arquivo

    geojson = {
        "type": "FeatureCollection",
        "features": feicoes,
    }

    caminho_temporario = caminho_geojson.with_suffix(
        caminho_geojson.suffix + ".tmp"
    )

    with caminho_temporario.open(
        "w",
        encoding="utf-8",
    ) as arquivo:
        json.dump(
            geojson,
            arquivo,
            ensure_ascii=False,
            indent=2,
        )

    caminho_temporario.replace(caminho_geojson)

    
    # METADADOS
    

    metadados = {
        "camada": nome_camada,
        "tipo_esperado": tipo_esperado,
        "fonte": "GeoSampa - Prefeitura de São Paulo",
        "servico": "WFS 2.0.0",
        "crs": "EPSG:4326",
        "data_atualizacao": datetime.now().astimezone().isoformat(
            timespec="seconds"
        ),
        "total_informado": total_informado,
        "total_importado": len(feicoes),
        "identificadores_unicos": len(feicoes_por_id),
        "duplicatas_descartadas": duplicatas,
        "paginas_consultadas": paginas,
        "arquivo": nome_arquivo,
    }

    caminho_metadados = OUTPUT_DIR / (
        caminho_geojson.stem + ".meta.json"
    )

    with caminho_metadados.open(
        "w",
        encoding="utf-8",
    ) as arquivo:
        json.dump(
            metadados,
            arquivo,
            ensure_ascii=False,
            indent=2,
        )

    
    # RESULTADO
    

    print("\n========== IMPORTAÇÃO CONCLUÍDA ==========")
    print(f"Camada: {nome_camada}")
    print(f"Total importado: {len(feicoes)}")
    print(f"Páginas consultadas: {paginas}")
    print(f"Duplicatas descartadas: {duplicatas}")
    print(f"GeoJSON: {caminho_geojson}")
    print(f"Metadados: {caminho_metadados}")
    print("==========================================")

    return metadados



# EXECUÇÃO


def main():
    print("\nPOLITIZE-SE | IMPORTAÇÃO DE OCORRÊNCIAS")
    print("=" * 65)

    resultados = {}

    for chave, configuracao in CAMADAS.items():
        resultados[chave] = importar_camada(
            chave,
            configuracao,
        )

    total_alagamentos = resultados["alagamento"]["total_importado"]
    total_inundacoes = resultados["inundacao"]["total_importado"]

    print("\n" + "=" * 65)
    print("RESUMO DA IMPORTAÇÃO")
    print("=" * 65)
    print(f"Alagamentos: {total_alagamentos}")
    print(f"Inundações: {total_inundacoes}")
    print(
        f"Total de ocorrências: "
        f"{total_alagamentos + total_inundacoes}"
    )
    print("\nTodas as camadas foram importadas com sucesso.")


if __name__ == "__main__":
    main()
