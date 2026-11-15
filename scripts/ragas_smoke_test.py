
import asyncio

from openai import AsyncOpenAI

from ragas.embeddings.base import embedding_factory
from ragas.llms import llm_factory
from ragas.metrics.collections import (
    Faithfulness,
    AnswerRelevancy,
    ContextPrecision,
    ContextRecall,
)


OLLAMA_BASE_URL = "http://localhost:11434/v1"

LLM_MODEL = "qwen3.5:9b"
EMBEDDING_MODEL = "nomic-embed-text:latest"


async def main():
    client = AsyncOpenAI(
        base_url=OLLAMA_BASE_URL,
        api_key="ollama",
        timeout=240.0,
    )

    try:
        # Inicializa o modelo avaliador
        evaluator_llm = llm_factory(
            LLM_MODEL,
            provider="openai",
            client=client,
            temperature=0,
            max_tokens=4096,
        )
        # Desativa o modo de raciocínio do Qwen no Ollama
        evaluator_llm.model_args["extra_body"] = {
            "reasoning_effort": "none"
        }

        # Inicializa o modelo de embeddings
        evaluator_embeddings = embedding_factory(
            "openai",
            model=EMBEDDING_MODEL,
            client=client,
        )

        # Amostra controlada para validar o funcionamento
        sample = {
            "user_input": (
                "Em que data foi promulgada a "
                "Constituição Federal de 1988?"
            ),
            "response": (
                "A Constituição Federal de 1988 foi "
                "promulgada em 5 de outubro de 1988."
            ),
            "retrieved_contexts": [
                (
                    "A Constituição da República Federativa "
                    "do Brasil foi promulgada em 5 de outubro de 1988."
                )
            ],
            "reference": (
                "A Constituição Federal de 1988 foi "
                "promulgada em 5 de outubro de 1988."
            ),
        }

        # Configuração das quatro métricas
        metrics = {
            "faithfulness": Faithfulness(
                llm=evaluator_llm,
            ),
            "answer_relevancy": AnswerRelevancy(
                llm=evaluator_llm,
                embeddings=evaluator_embeddings,
            ),
            "context_precision": ContextPrecision(
                llm=evaluator_llm,
            ),
            "context_recall": ContextRecall(
                llm=evaluator_llm,
            ),
        }

        # Argumentos específicos de cada métrica
        metric_inputs = {
            "faithfulness": {
                "user_input": sample["user_input"],
                "response": sample["response"],
                "retrieved_contexts": sample["retrieved_contexts"],
            },
            "answer_relevancy": {
                "user_input": sample["user_input"],
                "response": sample["response"],
            },
            "context_precision": {
                "user_input": sample["user_input"],
                "reference": sample["reference"],
                "retrieved_contexts": sample["retrieved_contexts"],
            },
            "context_recall": {
                "user_input": sample["user_input"],
                "reference": sample["reference"],
                "retrieved_contexts": sample["retrieved_contexts"],
            },
        }

        print("\n" + "=" * 55)
        print("POLITIZE-SE | TESTE DE AVALIAÇÃO RAGAS")
        print("=" * 55)

        results = {}

        # Execução sequencial para evitar sobrecarga do Ollama
        for name, metric in metrics.items():
            print(f"\nCalculando {name}...")

            result = await metric.ascore(
                **metric_inputs[name]
            )

            score = float(result.value)
            results[name] = score

            print(f"Resultado: {score:.4f}")

            if result.reason:
                print(f"Justificativa: {result.reason}")

        print("\n" + "=" * 55)
        print("RESUMO DOS RESULTADOS")
        print("=" * 55)

        for name, score in results.items():
            print(f"{name:<22} {score:.4f}")

        print("\nAvaliação concluída com sucesso.")

    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
