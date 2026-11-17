
import requests
from collections import Counter
from math import isfinite

WFS_URL = (
    "https://wfs.geosampa.prefeitura.sp.gov.br/"
    "geoserver/geoportal/wfs"
)

CAMADA = "geoportal:area_risco_geologico"
TAMANHO_PAGINA = 100


def consultar_todas_as_feicoes():
    feicoes = []
    inicio = 0
    pagina = 1
    total_informado = None

    while True:
        print(f"\nConsultando página {pagina}...")

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
        dados = response.json()

        if total_informado is None:
            bruto = (
                dados.get("totalFeatures")
                or dados.get("numberMatched")
            )

            try:
                total_informado = int(bruto)
            except (ValueError, TypeError):
                total_informado = None

        pagina_feicoes = dados.get("features", [])

        print(f"Feições recebidas: {len(pagina_feicoes)}")

        if not pagina_feicoes:
            break

        feicoes.extend(pagina_feicoes)

        inicio += len(pagina_feicoes)
        pagina += 1

        if total_informado is not None:
            if len(feicoes) >= total_informado:
                break

        if len(pagina_feicoes) < TAMANHO_PAGINA:
            break

        if pagina > 100:
            raise RuntimeError("Limite de páginas excedido.")

    return feicoes, total_informado


def valor_legivel(valor):
    if valor is None or str(valor).strip() == "":
        return "(não informado)"

    return str(valor).strip()


def imprimir_distribuicao(titulo, valores):
    print(f"\n{titulo}")

    contador = Counter(
        valor_legivel(valor)
        for valor in valores
    )

    for valor, quantidade in contador.most_common():
        print(f"  {valor}: {quantidade}")


def coletar_coordenadas(coordenadas):
    if not isinstance(coordenadas, (list, tuple)):
        return

    if (
        len(coordenadas) >= 2
        and isinstance(coordenadas[0], (int, float))
        and isinstance(coordenadas[1], (int, float))
    ):
        longitude = float(coordenadas[0])
        latitude = float(coordenadas[1])

        if isfinite(longitude) and isfinite(latitude):
            yield longitude, latitude

        return

    for item in coordenadas:
        yield from coletar_coordenadas(item)


def analisar(feicoes, total_informado):
    print("\n" + "=" * 65)
    print("DIAGNÓSTICO DE RISCO GEOLÓGICO")
    print("=" * 65)

    identificadores = []
    ids_duplicados = []

    graus = []
    codigos_grau = []

    processos = []
    codigos_processo = []

    areas = []
    setores = []
    fontes = []

    datas_atualizacao = []
    datas_vistoria = []

    moradias = []
    moradias_invalidas = 0

    geometrias = Counter()
    sem_geometria = 0
    sem_identificador = 0

    longitudes = []
    latitudes = []

    # Percorre todas as feições.
    for feicao in feicoes:
        propriedades = feicao.get("properties") or {}

        identificador = propriedades.get("cd_identificador")

        if identificador is None:
            sem_identificador += 1
        else:
            identificadores.append(str(identificador).strip())

        graus.append(
            propriedades.get("tx_grau_de_risco_geologico")
        )

        codigos_grau.append(
            propriedades.get("cd_grau_risco_geologico")
        )

        processos.append(
            propriedades.get("tx_tipo_processo_geologico")
        )

        codigos_processo.append(
            propriedades.get("cd_tipo_processo_geologico")
        )

        areas.append(propriedades.get("sg_area_risco"))
        setores.append(propriedades.get("sg_setor_risco"))
        fontes.append(propriedades.get("sg_fonte_original"))

        datas_atualizacao.append(
            propriedades.get("dt_atualizacao")
        )

        datas_vistoria.append(
            propriedades.get("dt_vistoria")
        )

        valor_moradias = propriedades.get("qt_moradia")

        if valor_moradias is not None:
            try:
                numero = float(valor_moradias)

                if isfinite(numero) and numero >= 0:
                    moradias.append(numero)
                else:
                    moradias_invalidas += 1

            except (ValueError, TypeError):
                moradias_invalidas += 1

        geometria = feicao.get("geometry")

        if not geometria:
            sem_geometria += 1
            geometrias["SEM_GEOMETRIA"] += 1
            continue

        geometrias[geometria.get("type", "DESCONHECIDA")] += 1

        for longitude, latitude in coletar_coordenadas(
            geometria.get("coordinates", [])
        ):
            longitudes.append(longitude)
            latitudes.append(latitude)

    contador_ids = Counter(identificadores)

    ids_duplicados = {
        identificador: quantidade
        for identificador, quantidade in contador_ids.items()
        if quantidade > 1
    }

    # ========================================================
    # RESUMO GERAL
    # ========================================================

    print("\nRESUMO GERAL")

    print(f"Total informado pelo WFS: {total_informado}")
    print(f"Total recebido: {len(feicoes)}")
    print(f"Identificadores encontrados: {len(identificadores)}")
    print(f"Identificadores únicos: {len(set(identificadores))}")
    print(f"Identificadores duplicados: {len(ids_duplicados)}")
    print(f"Registros sem identificador: {sem_identificador}")
    print(f"Geometrias ausentes: {sem_geometria}")

    print("\nTIPOS DE GEOMETRIA")

    for tipo, quantidade in geometrias.items():
        print(f"  {tipo}: {quantidade}")

    # ========================================================
    # CLASSIFICAÇÕES
    # ========================================================

    imprimir_distribuicao(
        "CLASSIFICAÇÃO TEXTUAL DO RISCO",
        graus,
    )

    imprimir_distribuicao(
        "CÓDIGOS DE CLASSIFICAÇÃO DO RISCO",
        codigos_grau,
    )

    imprimir_distribuicao(
        "TIPOS DE PROCESSO GEOLÓGICO",
        processos,
    )

    imprimir_distribuicao(
        "CÓDIGOS DE PROCESSO GEOLÓGICO",
        codigos_processo,
    )

    # ========================================================
    # ÁREAS E SETORES
    # ========================================================

    print("\nAGRUPAMENTO TERRITORIAL")

    print(
        "Áreas de risco distintas: "
        f"{len(set(valor_legivel(v) for v in areas))}"
    )

    print(
        "Setores distintos: "
        f"{len(set(valor_legivel(v) for v in setores))}"
    )

    imprimir_distribuicao(
        "FONTES ORIGINAIS",
        fontes,
    )

    print("\nÁREAS MAIS FREQUENTES")

    for nome, quantidade in Counter(
        valor_legivel(v) for v in areas
    ).most_common(15):
        print(f"  {nome}: {quantidade}")

    # ========================================================
    # MORADIAS
    # ========================================================

    print("\nQUANTIDADE ESTIMADA DE MORADIAS")

    print(f"Registros numéricos: {len(moradias)}")
    print(f"Valores inválidos: {moradias_invalidas}")

    if moradias:
        print(f"Menor valor: {min(moradias):g}")
        print(f"Maior valor: {max(moradias):g}")
        print(f"Registros com zero: {sum(v == 0 for v in moradias)}")

    # ========================================================
    # DATAS
    # ========================================================

    atualizacoes = [
        str(v) for v in datas_atualizacao if v
    ]

    vistorias = [
        str(v) for v in datas_vistoria if v
    ]

    print("\nDATAS")

    if atualizacoes:
        print(f"Atualização mais antiga: {min(atualizacoes)}")
        print(f"Atualização mais recente: {max(atualizacoes)}")

    if vistorias:
        print(f"Vistoria mais antiga: {min(vistorias)}")
        print(f"Vistoria mais recente: {max(vistorias)}")

    # ========================================================
    # COORDENADAS
    # ========================================================

    print("\nCOORDENADAS")

    print(f"Pares encontrados: {len(longitudes)}")

    if longitudes and latitudes:
        print(
            "Longitude: "
            f"{min(longitudes):.6f} até {max(longitudes):.6f}"
        )

        print(
            "Latitude: "
            f"{min(latitudes):.6f} até {max(latitudes):.6f}"
        )

        coordenadas_compatíveis = (
            all(-180 <= v <= 180 for v in longitudes)
            and all(-90 <= v <= 90 for v in latitudes)
        )

        print(
            "Compatíveis com limites de longitude/latitude: "
            f"{coordenadas_compatíveis}"
        )

    # ========================================================
    # IDENTIFICADORES DUPLICADOS
    # ========================================================

    if ids_duplicados:
        print("\nEXEMPLOS DE IDENTIFICADORES DUPLICADOS")

        for identificador, quantidade in list(
            ids_duplicados.items()
        )[:15]:
            print(f"  {identificador}: {quantidade}")

    print("\n" + "=" * 65)
    print("DIAGNÓSTICO FINALIZADO")
    print("=" * 65)


def main():
    print("\nPOLITIZE-SE | DIAGNÓSTICO DE RISCO GEOLÓGICO")
    print("=" * 65)

    feicoes, total = consultar_todas_as_feicoes()

    analisar(feicoes, total)


if __name__ == "__main__":
    main()
