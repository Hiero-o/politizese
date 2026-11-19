
"""Ferramentas de pesquisa e cálculo do agente Politizese."""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.tools import StructuredTool

from src.agents.tool_schemas import (
    ConstitutionSearchInput,
    PoliticoSearchInput,
    VotingThresholdInput,
)


logger = logging.getLogger(__name__)

MAX_TOOL_DOCUMENTS = 6
MAX_COMPOUND_TOOL_DOCUMENTS = 16
MAX_DOCUMENT_CONTENT_LENGTH = 1800
MAX_PARENT_CONTEXT_LENGTH = 600
MAX_PARENT_CONTEXT_DOCUMENTS = 2

def trace_final_documents(stage, documents):
    ids = [
        str(
            (document.metadata or {}).get("source_node_id")
            or (document.metadata or {}).get("chunk_id")
            or document.id
        )
        for document in documents
    ]

    logger.warning(
        "[Q09 TRACE] %s | encontrados=%s | total=%s",
        stage,
        "CF1988-ART-0005-INC-LI" in ids,
        len(ids),
    )


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
                func=self.search_politicos,
                name="search_politicos",
                description=(
                    "Pesquisa o catálogo público de representantes do Politize-se. "
                    "Use para identificar políticos por nome, cargo, partido, UF "
                    "ou município. Exemplos: buscar um senador, listar senadores "
                    "de SP, localizar um prefeito por município. Informe filtros "
                    "suficientes e limite a resposta a no máximo 8 registros. "
                    "Não confunda eleitos para o próximo mandato com pessoas já "
                    "em exercício; explique a fase do mandato retornada."
                ),
                args_schema=PoliticoSearchInput,
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
        
        self._reranker = getattr(
            iterative_retriever,
            "reranker",
            None,
        )

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
        """Converte documentos em evidências serializáveis."""

        is_compound = any(
            (document.metadata or {}).get(
                "decomposition_is_compound",
                False,
            )
            for document in documents
        )

        document_limit = (
            MAX_COMPOUND_TOOL_DOCUMENTS
            if is_compound
            else MAX_TOOL_DOCUMENTS
        )

        serialized = []

        # Apenas os metadados úteis para fundamentação jurídica
        # e rastreabilidade serão enviados ao LLM.
        fields = [
            "document_part",
            "article_number",
            "legal_unit",
            "number",
            "retrieval_sources",
            "matched_subquestions",
        ]

        parent_metadata_fields = [
            "document_part",
            "article_number",
            "legal_unit",
            "number",
        ]

        for document in documents:
            if len(serialized) >= document_limit:
                break

            metadata = dict(document.metadata or {})

            doc_id = (
                metadata.get("source_node_id")
                or metadata.get("chunk_id")
                or document.id
            )

            if not doc_id:
                continue

            selected_metadata = {}

            for field in fields:
                if field in metadata:
                    selected_metadata[field] = metadata[field]

            # Preserva o contexto dos dispositivos superiores,
            # aceitando tanto o formato original quanto o novo formato textual.
            parent_context = metadata.get("parent_context") or []

            # Novo formato: contexto textual simples.
            if isinstance(parent_context, str):
                parent_context_items = [
                    {
                        "doc_id": str(
                            metadata.get("parent_context_id", "")
                        ),
                        "content": parent_context,
                        "metadata": {
                            "document_part": metadata.get("document_part"),
                            "article_number": metadata.get("article_number"),
                            "legal_unit": "caput",
                        },
                    }
                ]

            # Compatibilidade com um único contexto em formato de dicionário.
            elif isinstance(parent_context, dict):
                parent_context_items = [parent_context]

            # Formato original: lista de documentos superiores.
            elif isinstance(parent_context, list):
                parent_context_items = parent_context

            else:
                parent_context_items = []

            if parent_context_items:
                selected_parents = []

                for parent in parent_context_items[
                    :MAX_PARENT_CONTEXT_DOCUMENTS
                ]:
                    if not isinstance(parent, dict):
                        continue

                    parent_metadata = parent.get("metadata") or {}

                    if not isinstance(parent_metadata, dict):
                        parent_metadata = {}

                    selected_parent_metadata = {
                        field: parent_metadata[field]
                        for field in parent_metadata_fields
                        if field in parent_metadata
                    }

                    selected_parents.append(
                        {
                            "doc_id": str(
                                parent.get("doc_id", "")
                            ),
                            "content": str(
                                parent.get("content", "")
                            )[:MAX_PARENT_CONTEXT_LENGTH],
                            "metadata": selected_parent_metadata,
                        }
                    )

                if selected_parents:
                    selected_metadata["parent_context"] = selected_parents

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

            candidates = self._base_retriever.search_with_queries(
                semantic_query=rewritten.semantic_query,
                lexical_query=rewritten.lexical_query,
            )

            documents = candidates

            if self._reranker is not None:
                documents = self._reranker.rerank_documents(
                    query=rewritten.semantic_query,
                    candidates=candidates,
                )
            
            trace_final_documents("POS-RERANKER", documents)
            
            # Expande enumerações quando o retriever oferece esse recurso.
            # Mantém compatibilidade com retrievers de teste e implementações alternativas.
            hierarchical_expansion = getattr(
                self._base_retriever,
                "expand_hierarchical_lists",
                None,
            )
            

            if callable(hierarchical_expansion):
                documents = hierarchical_expansion(
                    documents=documents,
                    query=(
                        f"{question}\n"
                        f"{rewritten.semantic_query}\n"
                        f"{rewritten.lexical_query}"
                    ),
                    max_documents=MAX_TOOL_DOCUMENTS,
                )
            trace_final_documents("POS-EXPANSAO", documents)
            
            serialized_documents = self._serialize_documents(documents)

            logger.warning(
                "[Q09 TRACE] POS-SERIALIZACAO | encontrados=%s | total=%s",
                any(
                    item["doc_id"] == "CF1988-ART-0005-INC-LI"
                    for item in serialized_documents
                ),
                len(serialized_documents),
            )


            return self._json(
                {
                    "ok": True,
                    "strategy": "query_rewriter_hybrid",
                    "original_question": question,
                    "semantic_query": rewritten.semantic_query,
                    "lexical_query": rewritten.lexical_query,
                    "document_count": len(serialized_documents),
                    "documents": serialized_documents,
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
            
            serialized_documents = self._serialize_documents(
                result.documents
            )

            logger.warning(
                "[RAG DEBUG] Documentos enviados ao agente (%s): %s",
                len(serialized_documents),
                [
                    document["doc_id"]
                    for document in serialized_documents
                ],
            )

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
                    "retrieved_document_count": len(result.documents),
                    "document_count": len(serialized_documents),
                    "documents": serialized_documents,
                }
            )

        except Exception as error:
            return self._error(
                "search_constitution_decomposed",
                error,
            )

    def search_politicos(
        self,
        nome: str | None = None,
        cargo: str | None = None,
        uf: str | None = None,
        municipio: str | None = None,
        partido: str | None = None,
        fase_mandato: str | None = None,
        limite: int = 5,
    ) -> str:
        """Pesquisa representantes no catálogo integrado do Politize-se.

        A busca utiliza os snapshots com cache das fontes oficiais.
        Retorna somente os campos necessários para identificar o registro,
        incluindo a fase do mandato e o estado de atualização das fontes.
        """

        try:
            parameters = PoliticoSearchInput.model_validate(
                {
                    "nome": nome,
                    "cargo": cargo,
                    "uf": uf,
                    "municipio": municipio,
                    "partido": partido,
                    "fase_mandato": fase_mandato,
                    "limite": limite,
                }
            )

            # Importação local para evitar acoplamento circular durante
            # a inicialização dos módulos de backend e agente.
            from backend.services.catalogo_politicos import listar_politicos

            resultado = listar_politicos(
                nome=parameters.nome,
                cargo=parameters.cargo,
                uf=parameters.uf,
                municipio=parameters.municipio,
                partido=parameters.partido,
                fase_mandato=parameters.fase_mandato,
                pagina=1,
                itens=parameters.limite,
            )

            politicos = []
            for politico in resultado.dados:
                politicos.append(
                    {
                        "id": politico.id,
                        "nome": politico.nome,
                        "cargo": politico.cargo,
                        "cargo_slug": politico.cargo_slug,
                        "partido": politico.partido,
                        "uf": politico.uf,
                        "municipio": politico.municipio,
                        "fase_mandato": politico.fase_mandato,
                        "titularidade": politico.titularidade,
                        "mandato": politico.mandato,
                        "situacao": politico.situacao,
                        "ano_eleicao": politico.ano_eleicao,
                        "situacao_eleitoral": politico.situacao_eleitoral,
                        "fonte": politico.fonte,
                    }
                )

            fontes = [
                {
                    "fonte": fonte.fonte,
                    "status": fonte.status,
                    "atualizado_em": (
                        fonte.atualizado_em.isoformat()
                        if fonte.atualizado_em else None
                    ),
                    "mensagem": fonte.mensagem,
                }
                for fonte in resultado.fontes
            ]

            logger.info(
                "[TOOL search_politicos] filtros=%s | total=%s | retornados=%s | ids=%s",
                {
                    "nome": parameters.nome,
                    "cargo": parameters.cargo,
                    "uf": parameters.uf,
                    "municipio": parameters.municipio,
                    "partido": parameters.partido,
                    "fase_mandato": parameters.fase_mandato,
                },
                resultado.total,
                len(politicos),
                [item["id"] for item in politicos],
            )

            return self._json(
                {
                    "ok": True,
                    "tool": "search_politicos",
                    "filters": {
                        "nome": parameters.nome,
                        "cargo": parameters.cargo,
                        "uf": parameters.uf,
                        "municipio": parameters.municipio,
                        "partido": parameters.partido,
                        "fase_mandato": parameters.fase_mandato,
                    },
                    "total_matches": resultado.total,
                    "returned": len(politicos),
                    "politicos": politicos,
                    "fontes": fontes,
                }
            )

        except Exception as error:
            return self._error("search_politicos", error)

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
