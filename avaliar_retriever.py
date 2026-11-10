
import argparse
import sys

from src.evaluation.retriever_evaluator import evaluate_retrievers


DEFAULT_CONFIG = "configs/avaliacoes/retrievers.json"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Executa avaliações de retrievers do Politize-se."
    )

    parser.add_argument(
        "--config",
        default=DEFAULT_CONFIG,
        help="Caminho do arquivo JSON de configuração.",
    )

    args = parser.parse_args()

    try:
        result_path = evaluate_retrievers(args.config)

        print("\nAvaliação executada com sucesso!")
        print(f"Resultado: {result_path}")

    except (ValueError, FileNotFoundError, RuntimeError) as error:
        print(f"\n[ERRO] {error}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
