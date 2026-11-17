
import json
from pathlib import Path
from collections import defaultdict


PROJECT_ROOT = Path(__file__).resolve().parents[2]

ARQUIVOS = {
    "Obras públicas": (
        PROJECT_ROOT / "data/obras/processed/obras_sp.geojson"
    ),
    "Risco hidrológico": (
        PROJECT_ROOT / "data/geosampa/processed/risco_hidrologico_wfs.geojson"
    ),
    "Risco geológico": (
        PROJECT_ROOT / "data/geosampa/processed/risco_geologico_wfs.geojson"
    ),
    "Alagamentos": (
        PROJECT_ROOT / "data/geosampa/processed/ocorrencias_alagamento.geojson"
    ),
    "Inundações": (
        PROJECT_ROOT / "data/geosampa/processed/ocorrencias_inundacao.geojson"
    ),
    "Deslizamentos": (
        PROJECT_ROOT / "data/geosampa/processed/ocorrencias_deslizamento.geojson"
    ),
    "Quedas de árvores": (
        PROJECT_ROOT / "data/geosampa/processed/ocorrencias_queda_arvore.geojson"
    ),
}

TERMOS_DATA = (
    "dt_",
    "data",
    "date",
    "inicio",
    "fim",
    "termino",
    "vistoria",
    "atualizacao",
    "ocorrencia",
    "carga",
    "prazo",
    "previsao",
)


def e_campo_de_data(nome):
    nome = nome.lower()

    return any(
        termo in nome
        for termo in TERMOS_DATA
    )


def auditar(identificacao, caminho):
    print("\n" + "=" * 65)
    print(f"BASE: {identificacao}")
    print("=" * 65)

    if not caminho.exists():
        print(f"Arquivo não encontrado: {caminho}")
        return

    with caminho.open("r", encoding="utf-8") as arquivo:
        dados = json.load(arquivo)

    feicoes = dados.get("features", [])
    total = len(feicoes)

    campos = set()

    for feicao in feicoes:
        propriedades = feicao.get("properties") or {}

        for nome in propriedades:
            if e_campo_de_data(nome):
                campos.add(nome)

    print(f"Total de registros: {total}")

    if not campos:
        print("Nenhum campo com aparência de data encontrado.")
        return

    for campo in sorted(campos):
        preenchidos = 0
        ausentes = 0
        exemplos = []

        for feicao in feicoes:
            propriedades = feicao.get("properties") or {}
            valor = propriedades.get(campo)

            if valor is None or (
                isinstance(valor, str) and not valor.strip()
            ):
                ausentes += 1
                continue

            preenchidos += 1

            if len(exemplos) < 3 and valor not in exemplos:
                exemplos.append(valor)

        percentual = (
            preenchidos / total * 100
            if total else 0
        )

        print(f"\nCampo: {campo}")
        print(f"  Preenchidos: {preenchidos}")
        print(f"  Ausentes: {ausentes}")
        print(f"  Cobertura: {percentual:.1f}%")
        print(f"  Exemplos: {exemplos}")


def main():
    print("\nPOLITIZE-SE | AUDITORIA DE DATAS")
    print("Verificando os GeoJSONs processados.")

    for identificacao, caminho in ARQUIVOS.items():
        auditar(identificacao, caminho)

    print("\n" + "=" * 65)
    print("AUDITORIA FINALIZADA")
    print("=" * 65)


if __name__ == "__main__":
    main()
