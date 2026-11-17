
import json
import math
from collections import Counter
from datetime import datetime
from pathlib import Path

import requests


# ============================================================
# CONFIGURAÇÕES
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

WFS_URL = (
    "https://wfs.geosampa.prefeitura.sp.gov.br/"
    "geoserver/geoportal/wfs"
)

CAMADA = "geoportal:area_risco_geologico"

TAMANHO_PAGINA = 100

OUTPUT_DIR = (
    PROJECT_ROOT
    / "data"
    / "geosampa"
    / "processed"
)

NOME_ARQUIVO = "risco_geologico_wfs.geojson"


# ============================================================
# CONSULTA AO WFS
# ============================================================

def consultar_pagina(inicio):
    params = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeNames": CAMADA,
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
            "O GeoSampa não retornou um JSON válido."
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


# ============================================================
# VALIDAÇÃO DAS COORDENADAS
# ============================================================

def coletar_coordenadas(coordenadas):
    """
    Percorre recursivamente as coordenadas de Polygon
    ou MultiPolygon e retorna os pares longitude/latitude.
    """

    if not isinstance(coordenadas, (list, tuple)):
        return

    if (
        len(coordenadas) >= 2
        and isinstance(coordenadas[0], (int, float))
        and isinstance(coordenadas[1], (int, float))
    ):
        longitude = float(coordenadas[0])
        latitude = float(coordenadas[1])

        yield longitude, latitude
        return

    for item in coordenadas:
        yield from coletar_coordenadas(item)


def validar_geometria(geometria, identificador):
    if not isinstance(geometria, dict):
        raise ValueError(
            f"Geometria ausente no ID {identificador}."
        )

    tipo = geometria.get("type")

    if tipo not in ("Polygon", "MultiPolygon"):
        raise ValueError(
            f"Geometria inesperada no ID {identificador}: {tipo}"
        )

    coordenadas = geometria.get("coordinates")

    if not coordenadas:
        raise ValueError(
            f"Geometria sem coordenadas no ID {identificador}."
        )

    quantidade = 0

    for longitude, latitude in coletar_coordenadas(coordenadas):
        if not math.isfinite(longitude) or not math.isfinite(latitude):
            raise ValueError(
                f"Coordenada não finita no ID {identificador}."
            )

        if not (-180 <= longitude <= 180):
            raise ValueError(
                f"Longitude inválida no ID {identificador}: {longitude}"
            )

        if not (-90 <= latitude <= 90):
            raise ValueError(
                f"Latitude inválida no ID {identificador}: {latitude}"
            )

        quantidade += 1

    if quantidade == 0:
        raise ValueError(
            f"Nenhum par de coordenadas válido no ID {identificador}."
        )

    return tipo, quantidade


# ============================================================
# VALIDAÇÃO DAS FEIÇÕES
# ============================================================

def validar_feicao(feicao):
    if feicao.get("type") != "Feature":
        raise ValueError("Registro não é uma Feature GeoJSON.")

    propriedades = feicao.get("properties") or {}

    identificador = propriedades.get("cd_identificador")

    if identificador is None or not str(identificador).strip():
        raise ValueError("Feição sem cd_identificador.")

    identificador = str(identificador).strip()

    geometria = feicao.get("geometry")

    tipo_geometria, quantidade_coordenadas = validar_geometria(
        geometria,
        identificador,
    )

    return (
        identificador,
        tipo_geometria,
        quantidade_coordenadas,
    )


# ============================================================
# IMPORTAÇÃO COMPLETA
# ============================================================

def importar_camada():
    print("\n" + "=" * 65)
    print("POLITIZE-SE | IMPORTAÇÃO DE RISCO GEOLÓGICO")
    print("=" * 65)

    print(f"Camada: {CAMADA}")
    print(f"Tamanho de cada página: {TAMANHO_PAGINA}")

    feicoes_por_id = {}

    total_informado = None
    paginas = 0
    duplicatas = 0
    total_coordenadas = 0

    geometrias = Counter()

    inicio = 0

    while True:
        paginas += 1

        if paginas > 100:
            raise RuntimeError(
                "Limite de páginas excedido."
            )

        print(
            f"\nConsultando página {paginas} "
            f"(startIndex={inicio})..."
        )

        dados = consultar_pagina(inicio)

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
            (
                identificador,
                tipo_geometria,
                quantidade_coordenadas,
            ) = validar_feicao(feicao)

            if identificador in feicoes_por_id:
                if feicoes_por_id[identificador] != feicao:
                    raise RuntimeError(
                        f"O ID {identificador} apareceu "
                        "com propriedades ou geometria diferentes."
                    )

                duplicatas += 1
                continue

            feicoes_por_id[identificador] = feicao

            geometrias[tipo_geometria] += 1
            total_coordenadas += quantidade_coordenadas

        print(
            f"Total acumulado: {len(feicoes_por_id)}"
        )

        inicio += len(pagina_feicoes)

        if total_informado is not None:
            if inicio >= total_informado:
                break

        if len(pagina_feicoes) < TAMANHO_PAGINA:
            break

    # ========================================================
    # VERIFICAÇÃO FINAL
    # ========================================================

    feicoes = list(feicoes_por_id.values())

    if total_informado is not None:
        if len(feicoes) != total_informado:
            raise RuntimeError(
                "Quantidade final diferente da informada pelo WFS. "
                f"Recebidas: {len(feicoes)}. "
                f"Esperadas: {total_informado}."
            )

    if not feicoes:
        raise RuntimeError(
            "Nenhuma feição foi importada."
        )

    # ========================================================
    # ESTATÍSTICAS DOS ATRIBUTOS
    # ========================================================

    graus_risco = Counter()
    codigos_grau = Counter()
    processos_geologicos = Counter()
    codigos_processo = Counter()

    datas_vistoria = Counter()
    datas_atualizacao = Counter()

    moradias_zero = 0
    moradias_nao_zero = 0
    moradias_invalidas = 0

    for feicao in feicoes:
        propriedades = feicao.get("properties") or {}

        grau = propriedades.get(
            "tx_grau_de_risco_geologico"
        )

        codigo_grau = propriedades.get(
            "cd_grau_risco_geologico"
        )

        processo = propriedades.get(
            "tx_tipo_processo_geologico"
        )

        codigo_processo = propriedades.get(
            "cd_tipo_processo_geologico"
        )

        vistoria = propriedades.get("dt_vistoria")
        atualizacao = propriedades.get("dt_atualizacao")

        if grau is not None:
            graus_risco[str(grau).strip()] += 1

        if codigo_grau is not None:
            codigos_grau[str(codigo_grau).strip()] += 1

        if processo is not None:
            processos_geologicos[str(processo).strip()] += 1

        if codigo_processo is not None:
            codigos_processo[str(codigo_processo).strip()] += 1

        if vistoria:
            datas_vistoria[str(vistoria)] += 1

        if atualizacao:
            datas_atualizacao[str(atualizacao)] += 1

        moradias = propriedades.get("qt_moradia")

        try:
            valor = float(moradias)

            if not math.isfinite(valor) or valor < 0:
                moradias_invalidas += 1

            elif valor == 0:
                moradias_zero += 1

            else:
                moradias_nao_zero += 1

        except (ValueError, TypeError):
            moradias_invalidas += 1

    # ========================================================
    # GERAÇÃO DO GEOJSON
    # ========================================================

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    caminho_geojson = OUTPUT_DIR / NOME_ARQUIVO

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

    # ========================================================
    # METADADOS
    # ========================================================

    metadados = {
        "camada": CAMADA,
        "fonte": "GeoSampa - Prefeitura de São Paulo",
        "servico": "WFS 2.0.0",
        "crs_solicitado": "EPSG:4326",
        "data_importacao": datetime.now().astimezone().isoformat(
            timespec="seconds"
        ),
        "total_informado": total_informado,
        "total_importado": len(feicoes),
        "identificadores_unicos": len(feicoes_por_id),
        "duplicatas_descartadas": duplicatas,
        "paginas_consultadas": paginas,
        "total_pares_coordenadas": total_coordenadas,
        "tipos_geometria": dict(geometrias),
        "distribuicao_grau_risco": dict(graus_risco),
        "distribuicao_codigo_grau": dict(codigos_grau),
        "distribuicao_processo_geologico": dict(
            processos_geologicos
        ),
        "distribuicao_codigo_processo": dict(
            codigos_processo
        ),
        "datas_vistoria": dict(datas_vistoria),
        "datas_atualizacao_fonte": dict(datas_atualizacao),
        "moradias": {
            "registros_com_zero": moradias_zero,
            "registros_com_valor_positivo": moradias_nao_zero,
            "registros_com_valor_invalido": moradias_invalidas,
            "total_estimado_nao_calculado": True,
        },
        "arquivo": NOME_ARQUIVO,
    }

    caminho_metadados = OUTPUT_DIR / (
        caminho_geojson.stem + ".meta.json"
    )

    caminho_meta_temporario = caminho_metadados.with_suffix(
        caminho_metadados.suffix + ".tmp"
    )

    with caminho_meta_temporario.open(
        "w",
        encoding="utf-8",
    ) as arquivo:
        json.dump(
            metadados,
            arquivo,
            ensure_ascii=False,
            indent=2,
        )

    caminho_meta_temporario.replace(caminho_metadados)

    # ========================================================
    # RESULTADO FINAL
    # ========================================================

    print("\n========== IMPORTAÇÃO CONCLUÍDA ==========")

    print(f"Total de polígonos: {len(feicoes)}")
    print(f"Identificadores únicos: {len(feicoes_por_id)}")
    print(f"Páginas consultadas: {paginas}")
    print(f"Duplicatas descartadas: {duplicatas}")

    print("\nDistribuição de risco:")

    for grau, quantidade in graus_risco.items():
        print(f"  {grau}: {quantidade}")

    print("\nDistribuição de processos:")

    for processo, quantidade in processos_geologicos.items():
        print(f"  {processo}: {quantidade}")

    print(f"\nPares de coordenadas: {total_coordenadas}")

    print(f"\nGeoJSON: {caminho_geojson}")
    print(f"Metadados: {caminho_metadados}")

    print("==========================================")

    return metadados


def main():
    importar_camada()


if __name__ == "__main__":
    main()
