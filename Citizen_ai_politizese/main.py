
from pathlib import Path

from assistente import Assistente
from base_conhecimento import BaseConhecimento


def main():
    pasta = Path(__file__).resolve().parent
    base = BaseConhecimento(pasta / "data" / "base_conhecimento.json")
    base.carregar()

    assistente = Assistente("Citizen Assist AI — Politize-se", base,
                            pasta / "data")

    while True:
        print("\n" + "=" * 58)
        print(" CITIZEN ASSIST AI | POLITIZE-SE")
        print(" Orientação sobre título de eleitor e serviços eleitorais")
        print("=" * 58)
        print("1. Fazer uma pergunta")
        print("2. Navegar por categorias")
        print("3. Gerenciar orientações (DSA)")
        print("4. Ver indicadores")
        print("5. Exportar atendimentos para CSV")
        print("0. Encerrar")
        opcao = input("Escolha: ").strip()

        if opcao == "1":
            assistente.perguntar()
        elif opcao == "2":
            assistente.navegar()
        elif opcao == "3":
            assistente.menu_dsa()
        elif opcao == "4":
            assistente.indicadores()
        elif opcao == "5":
            assistente.exportar_csv()
        elif opcao == "0":
            assistente.coletar_nota_facilidade()
            assistente.exportar_csv()
            print("Obrigado por utilizar o Citizen Assist AI!")
            break
        else:
            print("Opção inválida. Escolha uma opção do menu.")


if __name__ == "__main__":
    main()
