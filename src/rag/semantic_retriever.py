
from collections.abc import Mapping
from functools import lru_cache
import json
from pathlib import Path
from typing import Any

from langchain_core.documents import Document

from src.core.config import PROJECT_ROOT
from src.rag.vector_store import create_vector_store


# ============================================================
# CONFIGURAÇÕES
# ============================================================

DEFAULT_COLLECTION_NAME = "politizese_semantic_aux_v1"

DEFAULT_CANDIDATE_K = 48
DEFAULT_SECTION_K = 8
DEFAULT_UNIT_K = 48
DEFAULT_UNITS_PER_SECTION_K = 8

RRF_CONSTANT = 60

ARTICLE_STORE_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "constituicao_artigos.json"
)


# ============================================================
# CARREGAMENTO DA ÁRVORE JURÍDICA ORIGINAL
# ============================================================

def _flatten_serialized_node(
    node: Mapping[str, Any],
    nodes: dict[str, dict[str, Any]],
) -> None:
    """
    Percorre recursivamente a árvore jurídica original.

    Cada unidade é armazenada utilizando seu chunk_id como chave.
    """

    node_id = node.get("chunk_id")

    if not isinstance(node_id, str) or not node_id.strip():
        raise ValueError(
            "Foi encontrado um nó sem chunk_id na árvore jurídica."
        )

    if node_id in nodes:
        raise ValueError(
            f"ID duplicado na árvore jurídica: {node_id}"
        )

    nodes[node_id] = dict(node)

    children = node.get("children") or []

    if not isinstance(children, list):
        raise TypeError(
            f"Os filhos de {node_id} precisam ser uma lista."
        )

    for child in children:
        if not isinstance(child, Mapping):
            raise TypeError(
                f"Filho inválido encontrado no nó {node_id}."
            )

        _flatten_serialized_node(child, nodes)


@lru_cache(maxsize=1)
def get_legal_node_store() -> dict[str, dict[str, Any]]:
    """
    Carrega a árvore jurídica original e cria um índice por chunk_id.

    A árvore é carregada uma única vez por processo.
    """

    if not ARTICLE_STORE_PATH.is_file():
        raise FileNotFoundError(
            "Árvore jurídica não encontrada: "
            f"{ARTICLE_STORE_PATH}"
        )

    try:
        payload = json.loads(
            ARTICLE_STORE_PATH.read_text(encoding="utf-8")
        )

    except json.JSONDecodeError as error:
        raise ValueError(
            "O arquivo da árvore jurídica contém JSON inválido."
        ) from error

    if not isinstance(payload, dict):
        raise ValueError(
            "A raiz da árvore jurídica precisa ser um objeto JSON."
        )

    articles = payload.get("articles")

    if not isinstance(articles, list) or not articles:
        raise ValueError(
            "O JSON não possui uma lista válida de artigos."
        )

    nodes: dict[str, dict[str, Any]] = {}

    for article in articles:
        if not isinstance(article, Mapping):
            raise TypeError(
                "Foi encontrado um artigo inválido na árvore."
            )

        _flatten_serialized_node(article, nodes)

    # Valida os relacionamentos entre os nós.
    for node_id, node in nodes.items():
        parent_id = node.get("parent_id")

        if parent_id is not None and parent_id not in nodes:
            raise ValueError(
                f"Pai inexistente para {node_id}: {parent_id}"
            )

    print(
        "[SEMANTIC RETRIEVER] "
        f"Árvore jurídica carregada: {len(nodes)} nós."
    )

    return nodes


# ============================================================
# VALIDAÇÃO DOS IDENTIFICADORES
# ============================================================

def _resolve_article_id(
    node_id: str,
    nodes: Mapping[str, dict[str, Any]],
) -> str:
    """
    Localiza o artigo ao qual uma unidade jurídica pertence.
    """

    if node_id not in nodes:
        raise KeyError(
            f"Unidade jurídica não encontrada: {node_id}"
        )

    current = nodes[node_id]
    visited = set()

    while True:
        current_id = current["chunk_id"]

        if current_id in visited:
            raise ValueError(
                f"Ciclo detectado na hierarquia: {current_id}"
            )

        visited.add(current_id)

        if current.get("legal_unit") == "article":
            return current_id

        parent_id = current.get("parent_id")

        if not parent_id or parent_id not in nodes:
            raise ValueError(
                f"Não foi possível localizar o artigo de origem "
                f"da unidade {node_id}."
            )

        current = nodes[parent_id]


def _resolve_section_id(
    section_id: str,
    nodes: Mapping[str, dict[str, Any]],
) -> None:
    """
    Confirma que o identificador semântico corresponde
    a um artigo existente na árvore original.
    """

    section = nodes.get(section_id)

    if section is None:
        raise KeyError(
            "A seção encontrada no índice semântico "
            f"não existe na árvore original: {section_id}"
        )

    if section.get("legal_unit") != "article":
        raise ValueError(
            f"A seção {section_id} não corresponde a um artigo."
        )


def _resolve_unit_id(
    metadata: Mapping[str, Any],
    nodes: Mapping[str, dict[str, Any]],
) -> str:
    """
    Recupera o identificador da unidade jurídica original
    a partir dos metadados do índice semântico.
    """

    node_id = (
        metadata.get("source_node_id")
        or metadata.get("node_id")
    )

    if not isinstance(node_id, str) or not node_id.strip():
        raise ValueError(
            "Registro semântico sem identificador de unidade."
        )

    node = nodes.get(node_id)

    if node is None:
        raise KeyError(
            "Unidade do índice semântico não encontrada "
            f"na árvore original: {node_id}"
        )

    if node.get("legal_unit") == "article":
        raise ValueError(
            "Um registro do tipo unit apontou para uma raiz "
            f"de artigo: {node_id}"
        )

    return node_id


# ============================================================
# CONVERSÃO PARA DOCUMENTOS JURÍDICOS ORIGINAIS
# ============================================================

def _build_legal_document(
    node_id: str,
    nodes: Mapping[str, dict[str, Any]],
    retrieval_data: Mapping[str, Any],
) -> Document:
    """
    Constrói um Document utilizando exclusivamente o texto original.

    Os resumos semânticos não são encaminhados ao LLM.
    """

    node = nodes[node_id]

    original_text = node.get("texto")

    if not isinstance(original_text, str) or not original_text.strip():
        raise ValueError(
            f"A unidade jurídica não possui texto: {node_id}"
        )

    article_id = _resolve_article_id(node_id, nodes)

    # Mantém somente metadados escalares da árvore original.
    metadata = {
        key: value
        for key, value in node.items()
        if (
            isinstance(value, (str, int, float, bool))
            and value is not None
        )
    }

    metadata.update({
        "chunk_id": node_id,
        "source_node_id": node_id,
        "article_id": article_id,
        "retrieval_strategy": "semantic_index",
        "semantic_retrieval_score": round(
            retrieval_data["score"],
            8,
        ),
        "semantic_retrieval_sources": ", ".join(
            sorted(retrieval_data["sources"])
        ),
    })

    if retrieval_data.get("global_unit_rank") is not None:
        metadata["semantic_global_unit_rank"] = (
            retrieval_data["global_unit_rank"]
        )

    if retrieval_data.get("section_unit_rank") is not None:
        metadata["semantic_section_unit_rank"] = (
            retrieval_data["section_unit_rank"]
        )

    return Document(
        page_content=original_text.strip(),
        metadata=metadata,
    )


# ============================================================
# SEMANTIC INDEX RETRIEVER
# ============================================================

class SemanticIndexRetriever:
    """
    Recuperador do índice semântico auxiliar do Politize-se.

    Estratégias utilizadas:

    1. Busca global por unidades jurídicas.
    2. Busca por artigos.
    3. Busca direcionada às unidades dos artigos encontrados.
    4. Fusão dos resultados usando Reciprocal Rank Fusion.

    O retorno sempre contém textos da árvore jurídica original.
    """

    def __init__(
        self,
        vector_store,
        *,
        candidate_k: int = DEFAULT_CANDIDATE_K,
        section_k: int = DEFAULT_SECTION_K,
        unit_k: int = DEFAULT_UNIT_K,
        units_per_section_k: int = DEFAULT_UNITS_PER_SECTION_K,
    ) -> None:

        parameters = {
            "candidate_k": candidate_k,
            "section_k": section_k,
            "unit_k": unit_k,
            "units_per_section_k": units_per_section_k,
        }

        for name, value in parameters.items():
            if (
                not isinstance(value, int)
                or isinstance(value, bool)
                or value < 1
            ):
                raise ValueError(
                    f"{name} precisa ser um inteiro positivo."
                )

        self.vector_store = vector_store

        self.candidate_k = candidate_k
        self.section_k = section_k
        self.unit_k = unit_k
        self.units_per_section_k = units_per_section_k

        collection = getattr(
            vector_store,
            "_collection",
            None,
        )

        if collection is None:
            raise RuntimeError(
                "Não foi possível acessar a coleção semântica."
            )

        self.collection_name = collection.name

                # Conta os registros de cada tipo separadamente.
        section_records = collection.get(
            where={"record_type": "section"},
            include=[],
        )

        unit_records = collection.get(
            where={"record_type": "unit"},
            include=[],
        )

        self.section_count = len(
            section_records.get("ids") or []
        )

        self.unit_count = len(
            unit_records.get("ids") or []
        )

        if self.section_count == 0 or self.unit_count == 0:
            raise RuntimeError(
                "A coleção semântica precisa possuir "
                "registros section e unit. "
                f"Sections: {self.section_count}; "
                f"units: {self.unit_count}."
            )

        print(
            "[SEMANTIC RETRIEVER] Inicializado.\n"
            f"Coleção: {self.collection_name}\n"
            f"Sections: {self.section_count}\n"
            f"Units: {self.unit_count}\n"
            f"Candidatos finais: {self.candidate_k}"
        )

    # --------------------------------------------------------
    # BUSCA NO CHROMADB
    # --------------------------------------------------------

    def _search(
        self,
        query: str,
        *,
        k: int,
        metadata_filter: dict[str, Any],
    ) -> list[tuple[Document, float]]:
        """
        Executa uma busca semântica com filtro de metadados.
        """

        results = self.vector_store.similarity_search_with_score(
            query,
            k=k,
            filter=metadata_filter,
        )

        return results

    # --------------------------------------------------------
    # FUSÃO DOS RESULTADOS
    # --------------------------------------------------------

    def _register_result(
        self,
        candidates: dict[str, dict[str, Any]],
        document: Document,
        *,
        rank: int,
        source: str,
        weight: float = 1.0,
    ) -> None:
        """
        Registra um candidato e acumula sua pontuação RRF.
        """

        metadata = document.metadata or {}

        nodes = get_legal_node_store()

        node_id = _resolve_unit_id(metadata, nodes)

        entry = candidates.setdefault(
            node_id,
            {
                "score": 0.0,
                "sources": set(),
                "global_unit_rank": None,
                "section_unit_rank": None,
            },
        )

        entry["score"] += (
            weight / (RRF_CONSTANT + rank)
        )

        entry["sources"].add(source)

    # --------------------------------------------------------
    # RECUPERAÇÃO
    # --------------------------------------------------------

    def invoke(self, query: str) -> list[Document]:
        """
        Recebe uma pergunta e retorna os dispositivos
        constitucionais originais mais relevantes.
        """

        if not isinstance(query, str) or not query.strip():
            raise ValueError(
                "A consulta semântica não pode estar vazia."
            )

        query = query.strip()

        nodes = get_legal_node_store()

        candidates: dict[str, dict[str, Any]] = {}

        # ====================================================
        # 1. BUSCA GLOBAL POR UNIDADES JURÍDICAS
        # ====================================================

        global_unit_results = self._search(
            query,
            k=self.unit_k,
            metadata_filter={
                "record_type": "unit",
            },
        )

        for rank, (document, distance) in enumerate(
            global_unit_results,
            start=1,
        ):
            self._register_result(
                candidates,
                document,
                rank=rank,
                source="global_unit_search",
            )

            metadata = document.metadata or {}

            node_id = _resolve_unit_id(metadata, nodes)

            candidates[node_id]["global_unit_rank"] = rank

        # ====================================================
        # 2. BUSCA GLOBAL POR ARTIGOS
        # ====================================================

        section_results = self._search(
            query,
            k=self.section_k,
            metadata_filter={
                "record_type": "section",
            },
        )

        # ====================================================
        # 3. BUSCAS DIRECIONADAS DENTRO DOS ARTIGOS
        # ====================================================

        section_unit_results = []

        visited_sections = set()

        for section_rank, (section_document, distance) in enumerate(
            section_results,
            start=1,
        ):
            metadata = section_document.metadata or {}

            section_id = metadata.get("section_id")

            if not isinstance(section_id, str) or not section_id.strip():
                raise ValueError(
                    "Registro section sem section_id."
                )

            if section_id in visited_sections:
                continue

            visited_sections.add(section_id)

            # Confirma que a seção corresponde a um artigo original.
            _resolve_section_id(section_id, nodes)

            # Busca somente unidades pertencentes a esse artigo.
            section_filter = {
                "$and": [
                    {
                        "record_type": "unit",
                    },
                    {
                        "section_id": section_id,
                    },
                ]
            }

            local_results = self._search(
                query,
                k=self.units_per_section_k,
                metadata_filter=section_filter,
            )

            for local_rank, (unit_document, unit_distance) in enumerate(
                local_results,
                start=1,
            ):
                section_unit_results.append({
                    "document": unit_document,
                    "section_rank": section_rank,
                    "local_rank": local_rank,
                    "section_id": section_id,
                })

        # Ordena os resultados direcionados:
        # primeiro a seção mais relevante, depois a unidade.
        section_unit_results.sort(
            key=lambda item: (
                item["section_rank"],
                item["local_rank"],
            )
        )

        for effective_rank, item in enumerate(
            section_unit_results,
            start=1,
        ):
            document = item["document"]

            self._register_result(
                candidates,
                document,
                rank=effective_rank,
                source=f"section_search:{item['section_id']}",
                weight=0.8,
            )

            metadata = document.metadata or {}

            node_id = _resolve_unit_id(metadata, nodes)

            previous_rank = candidates[node_id]["section_unit_rank"]

            if (
                previous_rank is None
                or effective_rank < previous_rank
            ):
                candidates[node_id]["section_unit_rank"] = (
                    effective_rank
                )

        # ====================================================
        # 4. ORDENAÇÃO FINAL
        # ====================================================

        if not candidates:
            return []

        ordered_candidates = sorted(
            candidates.items(),
            key=lambda item: (
                -item[1]["score"],
                item[0],
            ),
        )

        # ====================================================
        # 5. RECUPERAÇÃO DOS TEXTOS JURÍDICOS ORIGINAIS
        # ====================================================

        documents = []

        for node_id, retrieval_data in ordered_candidates[
            :self.candidate_k
        ]:
            legal_document = _build_legal_document(
                node_id,
                nodes,
                retrieval_data,
            )

            documents.append(legal_document)

        return documents


# ============================================================
# FACTORY
# ============================================================

def create_semantic_retriever(
    *,
    provider: str = "local",
    candidate_k: int = DEFAULT_CANDIDATE_K,
    section_k: int = DEFAULT_SECTION_K,
    unit_k: int = DEFAULT_UNIT_K,
    units_per_section_k: int = DEFAULT_UNITS_PER_SECTION_K,
    persist_directory: str | Path | None = None,
) -> tuple[SemanticIndexRetriever, str]:
    """
    Inicializa o recuperador utilizando a coleção semântica auxiliar.
    """

    vector_store, selected_provider = create_vector_store(
        provider=provider,
        persist_directory=persist_directory,
        collection_name=DEFAULT_COLLECTION_NAME,
    )

    retriever = SemanticIndexRetriever(
        vector_store,
        candidate_k=candidate_k,
        section_k=section_k,
        unit_k=unit_k,
        units_per_section_k=units_per_section_k,
    )

    return retriever, selected_provider


@lru_cache(maxsize=1)
def get_semantic_retriever() -> SemanticIndexRetriever:
    """
    Retorna uma instância reutilizável do Semantic Retriever.
    """

    retriever, provider = create_semantic_retriever(
        provider="local",
    )

    print(
        "[SEMANTIC RETRIEVER] "
        f"Provedor de embeddings: {provider}"
    )

    return retriever
