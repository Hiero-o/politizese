
import requests
from collections import Counter

WFS_URL = (
    "https://wfs.geosampa.prefeitura.sp.gov.br/"
    "geoserver/geoportal/wfs"
)

TAMANHO_PAGINA = 100

CAMADAS = {
    "alagamento": {
        "nome": "geoportal:risco_ocorrencia_alagamento",
        "tipo_esperado": "ALAGAMENTO",
    },
    "inundacao": {
        "nome": "geoportal:risco_ocorrencia_inundacao",
        "tipo_esperado": "INUNDACAO",
    },
}


def buscar_todas_as_feicoes(nome_camada):
    feicoes = []
    inicio = 0
    total_informado = None
    pagina = 1

    while True:
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
            timeout=60,
        )
        response.raise_for_status()

        dados = response.json()
        pagina_feicoes = dados.get("features", [])

        if total_informado is None:
            total_bruto = (
                dados.get("totalFeatures")
                or dados.get("numberMatched")
            )

            try:
                total_informado = int(total_bruto)
            except (ValueError, TypeError):
                total_informado = None

        print(
            f"Página {pagina}: "
            f"{len(pagina_feicoes)} feições recebidas"
        )

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
            raise RuntimeError(
                "Limite de páginas excedido. "
                "Verifique a paginação do WFS."
            )

    return feicoes, total_informado


def analisar_camada(chave, configuracao):
    nome = configuracao["nome"]
    tipo_esperado = configuracao["tipo_esperado"]

    print("\n" + "=" * 65)
    print(f"ANALISANDO: {nome}")
    print("=" * 65)

    feicoes, total_informado = buscar_todas_as_feicoes(nome)

    propriedades = [
        feicao.get("properties") or {}
        for feicao in feicoes
    ]

    identificadores = [
        str(prop["cd_identificador"]).strip()
        for prop in propriedades
        if prop.get("cd_identificador") is not None
    ]

    contador_ids = Counter(identificadores)
    ids_duplicados = {
        identificador: quantidade
        for identificador, quantidade in contador_ids.items()
        if quantidade > 1
    }

    tipos = Counter(
        prop.get("dc_tipo_ocorrencia")
        for prop in propriedades
    )

    geometrias = Counter(
        (feicao.get("geometry") or {}).get("type", "SEM_GEOMETRIA")
        for feicao in feicoes
    )

    tipos_incorretos = [
        prop.get("cd_identificador")
        for prop in propriedades
        if prop.get("dc_tipo_ocorrencia") != tipo_esperado
    ]

    datas = [
        prop.get("dt_ocorrencia")
        for prop in propriedades
        if prop.get("dt_ocorrencia")
    ]

    distritos_nulos = sum(
        prop.get("nm_distrito") is None
        for prop in propriedades
    )

    subprefeituras_nulas = sum(
        prop.get("nm_subprefeitura") is None
        for prop in propriedades
    )

    ids_validos = set(identificadores)

    print("\nRESUMO")
    print(f"Total informado pelo WFS: {total_informado}")
    print(f"Total recebido: {len(feicoes)}")
    print(f"Identificadores válidos: {len(identificadores)}")
    print(f"Identificadores únicos: {len(ids_validos)}")
    print(f"Identificadores duplicados: {len(ids_duplicados)}")

    print("\nDistribuição dos tipos:")
    for tipo, quantidade in tipos.items():
        print(f"  {tipo}: {quantidade}")

    print("\nGeometrias:")
    for geometria, quantidade in geometrias.items():
        print(f"  {geometria}: {quantidade}")

    print(f"\nRegistros com tipo diferente do esperado: {len(tipos_incorretos)}")
    print(f"Registros sem distrito: {distritos_nulos}")
    print(f"Registros sem subprefeitura: {subprefeituras_nulas}")

    if datas:
        print(f"Data mais antiga: {min(datas)}")
        print(f"Data mais recente: {max(datas)}")

    if ids_duplicados:
        print("\nExemplos de IDs duplicados:")
        for identificador, quantidade in list(ids_duplicados.items())[:10]:
            print(f"  {identificador}: {quantidade} ocorrências")

    return {
        "feicoes": feicoes,
        "ids": ids_validos,
        "total_informado": total_informado,
    }


def main():
    resultados = {}

    for chave, configuracao in CAMADAS.items():
        resultados[chave] = analisar_camada(
            chave,
            configuracao,
        )

    ids_alagamento = resultados["alagamento"]["ids"]
    ids_inundacao = resultados["inundacao"]["ids"]

    ids_em_comum = ids_alagamento.intersection(ids_inundacao)

    print("\n" + "=" * 65)
    print("COMPARAÇÃO ENTRE AS CAMADAS")
    print("=" * 65)

    print(f"IDs de alagamento: {len(ids_alagamento)}")
    print(f"IDs de inundação: {len(ids_inundacao)}")
    print(f"IDs em comum: {len(ids_em_comum)}")

    if ids_em_comum:
        print("\nExemplos de identificadores compartilhados:")
        for identificador in sorted(ids_em_comum)[:20]:
            print(f"  {identificador}")
    else:
        print("\nNenhum identificador compartilhado.")

    print("\nDiagnóstico finalizado.")


if __name__ == "__main__":
    main()
