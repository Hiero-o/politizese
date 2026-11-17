
import argparse
import subprocess
import sys

from pathlib import Path



# 1. CONFIGURAÇÃO


PROJECT_ROOT = Path(__file__).resolve().parent


# Cada módulo representa uma fonte de dados independente.
# Para adicionar uma nova fonte, basta incluir uma entrada aqui.

# Siga esse formato:
#   "name": {
#       "name": "XXXXXX",
#       "script": Path(
#           "scripts/xxxxxx/xxx_xxx.py"
#       ),
#   },


TASKS = {
    "obras": {
        "name": "Obras públicas",
        "script": Path(
            "scripts/obras/atualizar_base.py"
        ),
    },

    "risco_hidrologico": {
        "name": "Risco hidrológico - GeoSampa",
        "script": Path(
            "scripts/geosampa/importar_risco_hidrologico_wfs.py"
        ),
    },
    
    "ocorrencias": {
        "name": "Ocorrencias de alagamento e inundação - GeoSampa",
        "script": Path(
            "scripts/geosampa/importar_ocorrencias_wfs.py"
        ),
    },
    
    "risco_geologico": {
        "name": "Risco geológico - GeoSampa",
        "script": Path(
            "scripts/geosampa/importar_risco_geologico_wfs.py"
        ),
    },
    
    # CONFIRA o caminhoi correto do script
    
    #  Basta adicionar o caminho do arquivo para fazer a atualização, como está acima. 
    
}



# 2. EXECUÇÃO DE UM MÓDULO


def run_task(task_key):
    """Executa um módulo de atualização individualmente."""

    task = TASKS[task_key]

    script_path = PROJECT_ROOT / task["script"]

    print("\n" + "=" * 60)
    print(f"ATUALIZANDO: {task['name']}")
    print("=" * 60)

    if not script_path.exists():
        print(f"ERRO: Script não encontrado: {script_path}")
        return False

    command = [
        sys.executable,
        str(script_path),
    ]

    result = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        check=False,
    )

    if result.returncode != 0:
        print(f"\nFALHA: {task['name']}")
        print("A execução foi interrompida.")
        return False

    print(f"\nSUCESSO: {task['name']} atualizado.")

    return True



# 3. EXECUÇÃO DA ROTINA


def update_data(selected_tasks):
    """Executa os módulos selecionados em sequência."""

    total = len(selected_tasks)
    successful = 0

    print("\nPOLITIZE-SE | ATUALIZAÇÃO DE DADOS")
    print(f"Módulos selecionados: {total}")

    for task_key in selected_tasks:

        success = run_task(task_key)

        if not success:
            print("\nATUALIZAÇÃO INTERROMPIDA.")
            print(
                f"Módulos concluídos antes da falha: "
                f"{successful}/{total}"
            )

            return False

        successful += 1

    print("\n" + "=" * 60)
    print("ATUALIZAÇÃO FINALIZADA COM SUCESSO")
    print("=" * 60)

    print(f"Módulos executados: {successful}/{total}")

    return True



# 4. INTERFACE DE LINHA DE COMANDO


def main():

    parser = argparse.ArgumentParser(
        description=(
            "Orquestrador de atualização das bases "
            "geográficas do Politizese."
        )
    )

    selection = parser.add_mutually_exclusive_group(
        required=True
    )

    selection.add_argument(
        "--tudo",
        action="store_true",
        help="Atualiza todas as bases cadastradas.",
    )

    selection.add_argument(
        "--obras",
        action="store_true",
        help="Atualiza somente a base de obras.",
    )

    selection.add_argument(
        "--risco-hidrologico",
        action="store_true",
        help="Atualiza somente o risco hidrológico.",
    )
    
    selection.add_argument(
        "--ocorrencias",
        action="store_true",
        help="Atualiza ocorrências de alagamento e inundação"
    )
    selection.add_argument(
        "--risco-geologico",
        action="store_true",
        help="Atualiza áreas de risco geológico",
    )

    args = parser.parse_args()

    # Seleciona os módulos que serão executados.

    if args.tudo:
        selected_tasks = list(TASKS.keys())

    elif args.obras:
        selected_tasks = ["obras"]

    elif args.risco_hidrologico:
        selected_tasks = ["risco_hidrologico"]
    
    elif args.ocorrencias:
        selected_tasks = ["ocorrencias"]
        
    elif args.risco_geologico:
        selected_tasks = ["risco_geologico"]

    else:
        parser.error("Nenhum módulo selecionado.")

    success = update_data(selected_tasks)

    if not success:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
