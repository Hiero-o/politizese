
"""Ferramentas de pesquisa e cálculo do agente Politizese."""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.tools import StructuredTool

from src.agents.tool_schemas import (
    ConstitutionSearchInput,
    VotingThresholdInput,
)


logger = logging.getLogger(__name__)

MAX_TOOL_DOCUMENTS = 8
MAX_DOCUMENT_CONTENT_LENGTH = 1800


class PolitizeseToolbox:
    """
    Disponibiliza as ferramentas utilizadas pelo agente.

    Recebe uma instância já inicializada de PolitizeseIterativeRetriever,
    reutilizando seus componentes e evitando instâncias duplicadas
    de ChromaDB, BM25, Query Rewriter e Question Decomposer.
    """

    def __init__(self, iterative_retriever: Any) -> None:
        self._pipeline = iterative_retriever
        self._base_retriever = iterative_retriever.base_retriever
        self._rewriter = iterative_retriever.rewriter

        self._tools = [
            StructuredTool.from_function(
                func=self.search_constitution,
                name="search_constitution",
                description=(
                    "Pesquisa informações na Constituição Federal usando "
                    "Query Rewriter, ChromaDB, BM25 e RRF. Utilize para "
                    "perguntas simples ou com uma necessidade principal "
                    "de informação. Retorna documentos com doc_id, conteúdo "
                    "e metadados para fundamentar a resposta."
                ),
                args_schema=ConstitutionSearchInput,
            ),
            StructuredTool.from_function(
                func=self.search_constitution_decomposed,
                name="search_constitution_decomposed",
                description=(
                    "Pesquisa perguntas que envolvem várias necessidades "
                    "informacionais independentes. Utiliza Question "
                    "Decomposer, Query Rewriter, ChromaDB, BM25 e RRF "
                    "iterativo. Retorna subperguntas, consultas e documentos "
                    "com doc_id e rastreabilidade. Prefira esta ferramenta "
                    "quando a pergunta exigir investigar diferentes critérios, "
                    "condições ou dispositivos."
                ),
                args_schema=ConstitutionSearchInput,
            ),
            StructuredTool.from_function(
                func=self.calculate_voting_threshold,
                name="calculate_voting_threshold",
                description=(
                    "Calcula deterministicamente a quantidade mínima inteira "
                    "de votos correspondente a uma fração informada. Utilize "
                    "quando já tiver o total de integrantes, numerador e "
                    "denominador, extraídos da pergunta ou de uma evidência "
                    "confiável. Não invente esses parâmetros. Use "
                    "strictly_greater=true quando a regra exigir um valor "
                    "estritamente superior à fração."
                ),
                args_schema=VotingThresholdInput,
            ),
        ]

        self._tool_map = {
            tool.name: tool
            for tool in self._tools
        }

    @property
    def tools(self) -> list[StructuredTool]:
        """Retorna as ferramentas disponíveis para o agente."""

        return list(self._tools)

    @property
    def tool_map(self) -> dict[str, StructuredTool]:
        """Retorna as ferramentas indexadas pelo nome."""

        return dict(self._tool_map)

    @staticmethod
    def _json(data: dict[str, Any]) -> str:
        """Serializa dados da ferramenta em JSON legível."""

        return json.dumps(
            data,
            ensure_ascii=False,
            default=str,
        )

    @staticmethod
    def _error(tool_name: str, error: Exception) -> str:
        """
        Produz uma observação de erro controlado.

        O erro não interrompe diretamente o agente. Ele poderá avaliar
        a observação e decidir como continuar.
        """

        logger.exception(
            "Falha na ferramenta %s.",
            tool_name,
        )

        return PolitizeseToolbox._json(
            {
                "ok": False,
                "tool": tool_name,
                "error": {
                    "type": type(error).__name__,
                    "message": str(error)[:300],
                },
            }
        )

    @staticmethod
    def _serialize_documents(
        documents: list[Any],
    ) -> list[dict[str, Any]]:
        """
        Converte documentos LangChain em evidências serializáveis.

        Preserva o identificador documental necessário para as citações.
        """

        serialized = []

        for document in documents[:MAX_TOOL_DOCUMENTS]:
            metadata = dict(document.metadata or {})

            doc_id = (
                metadata.get("source_node_id")
                or metadata.get("chunk_id")
                or document.id
            )

            if not doc_id:
                continue

            selected_metadata = {}

            fields = [
                "document_part",
                "article_number",
                "legal_unit",
                "number",
                "retrieval_sources",
                "semantic_rank",
                "lexical_rank",
                "rrf_score",
                "rerank_score",
                "matched_subquestions",
            ]

            for field in fields:
                if field in metadata:
                    selected_metadata[field] = metadata[field]

            serialized.append(
                {
                    "doc_id": str(doc_id),
                    "content": document.page_content[
                        :MAX_DOCUMENT_CONTENT_LENGTH
                    ],
                    "metadata": selected_metadata,
                }
            )

        return serialized

    def search_constitution(self, question: str) -> str:
        """
        Pesquisa uma pergunta constitucional usando consultas reformuladas.

        Executa o Query Rewriter e utiliza consultas independentes
        para a recuperação semântica e lexical.

        Retorna uma observação JSON contendo as consultas utilizadas
        e as evidências recuperadas com seus identificadores documentais.
        """

        try:
            rewritten = self._rewriter.rewrite(question)

            documents = self._base_retriever.search_with_queries(
                semantic_query=rewritten.semantic_query,
                lexical_query=rewritten.lexical_query,
            )

            return self._json(
                {
                    "ok": True,
                    "strategy": "query_rewriter_hybrid",
                    "original_question": question,
                    "semantic_query": rewritten.semantic_query,
                    "lexical_query": rewritten.lexical_query,
                    "document_count": len(documents),
                    "documents": self._serialize_documents(documents),
                }
            )

        except Exception as error:
            return self._error(
                "search_constitution",
                error,
            )

    def search_constitution_decomposed(
        self,
        question: str,
    ) -> str:
        """
        Pesquisa uma pergunta composta por meio de subperguntas.

        Executa decomposição, reformulação individual e recuperação
        híbrida iterativa. Consolida as evidências e preserva a origem
        de cada documento em relação às subperguntas.

        Retorna observações JSON com a decomposição e as evidências.
        """

        try:
            result = self._pipeline.retrieve_with_trace(question)

            subquestions = [
                {
                    "index": item.index,
                    "question": item.question,
                    "focus": item.focus,
                    "semantic_query": item.semantic_query,
                    "lexical_query": item.lexical_query,
                    "retrieved_count": item.retrieved_count,
                }
                for item in result.trace.subqueries
            ]

            return self._json(
                {
                    "ok": True,
                    "strategy": "decomposition_hybrid",
                    "original_question": result.trace.original_question,
                    "is_compound": result.trace.is_compound,
                    "decomposition_reason": (
                        result.trace.decomposition_reason
                    ),
                    "subquestions": subquestions,
                    "document_count": len(result.documents),
                    "documents": self._serialize_documents(
                        result.documents
                    ),
                }
            )

        except Exception as error:
            return self._error(
                "search_constitution_decomposed",
                error,
            )

    def calculate_voting_threshold(
        self,
        total_members: int,
        numerator: int,
        denominator: int,
        strictly_greater: bool = False,
    ) -> str:
        """
        Calcula deterministicamente uma quantidade mínima de votos.

        Para uma exigência maior ou igual à fração, utiliza o teto
        matemático. Para uma exigência estritamente maior, utiliza
        o menor inteiro superior ao resultado da divisão.

        A ferramenta não determina qual quórum é juridicamente aplicável.
        A fração e a quantidade total precisam vir da pergunta ou de
        evidências previamente recuperadas.

        Retorna o resultado, a fração e a operação aritmética realizada.
        """

        try:
            parameters = VotingThresholdInput.model_validate(
                {
                    "total_members": total_members,
                    "numerator": numerator,
                    "denominator": denominator,
                    "strictly_greater": strictly_greater,
                }
            )

            product = (
                parameters.total_members
                * parameters.numerator
            )

            if parameters.strictly_greater:
                minimum_required = (
                    product // parameters.denominator
                ) + 1

                comparison = ">"

            else:
                minimum_required = (
                    product + parameters.denominator - 1
                ) // parameters.denominator

                comparison = ">="

            return self._json(
                {
                    "ok": True,
                    "tool": "calculate_voting_threshold",
                    "total_members": parameters.total_members,
                    "fraction": (
                        f"{parameters.numerator}/"
                        f"{parameters.denominator}"
                    ),
                    "strictly_greater": (
                        parameters.strictly_greater
                    ),
                    "comparison": comparison,
                    "calculation": (
                        f"{parameters.total_members} * "
                        f"{parameters.numerator} / "
                        f"{parameters.denominator}"
                    ),
                    "minimum_required": minimum_required,
                    "percentage": round(
                        (
                            parameters.numerator
                            / parameters.denominator
                        ) * 100,
                        4,
                    ),
                }
            )

        except Exception as error:
            return self._error(
                "calculate_voting_threshold",
                error,
            )


def build_politizese_toolbox(
    iterative_retriever: Any,
) -> PolitizeseToolbox:
    """Constrói o conjunto de ferramentas a partir do pipeline existente."""

    return PolitizeseToolbox(iterative_retriever)
