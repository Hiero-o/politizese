
import math
from typing import Any, Literal

from langchain_core.callbacks.manager import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import ConfigDict, Field

from src.core.config import Settings
from src.rag.retriever import (
    DEFAULT_LEXICAL_CANDIDATE_K,
    DEFAULT_RRF_CONSTANT,
    create_retriever,
)

import logging

logger = logging.getLogger(__name__)

DIAGNOSTIC_TARGET_ID = "CF1988-ART-0005-INC-LI"


# Modelo padrão do Cross-Encoder.
DEFAULT_RERANKER_MODEL = "BAAI/bge-reranker-v2-m3"

# Quantidade de candidatos selecionados pelo retriever original.
DEFAULT_CANDIDATE_K = 48

# Quantidade de documentos encaminhados ao Cross-Encoder.
DEFAULT_RERANK_K = 24

# Quantidade final de documentos enviados ao Context Builder.
DEFAULT_RERANK_TOP_K = 4

# Parâmetros de inferência.
DEFAULT_BATCH_SIZE = 8
DEFAULT_MAX_LENGTH = 512

# Coleção jurídica padrão.
DEFAULT_COLLECTION_NAME = "constituicao_legal_clean_v2"


class PolitizeseCrossEncoderRetriever(BaseRetriever):
    """
    Aplica Cross-Encoder sobre os documentos recuperados
    pelo retriever híbrido do Politize-se.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    base_retriever: Any = Field(
        exclude=True,
        repr=False,
    )

    reranker: Any = Field(
        exclude=True,
        repr=False,
    )

    top_k: int = Field(
        default=DEFAULT_RERANK_TOP_K,
        ge=1,
    )

    batch_size: int = Field(
        default=DEFAULT_BATCH_SIZE,
        ge=1,
    )

    model_name: str = DEFAULT_RERANKER_MODEL

    @staticmethod
    def _format_passage(document: Document) -> str:
        """
        Enriquece o trecho com informações da hierarquia jurídica
        e com o contexto do dispositivo introdutório, quando disponível.
        """

        metadata = document.metadata or {}

        labels = []

        document_part = metadata.get("document_part")

        if document_part == "CF":
            labels.append("Constituição Federal")

        elif document_part == "ADCT":
            labels.append(
                "Ato das Disposições Constitucionais Transitórias"
            )

        article_number = metadata.get("article_number")

        if article_number:
            labels.append(f"Art. {article_number}")

        legal_unit = metadata.get("legal_unit")
        number = metadata.get("number")

        if legal_unit == "caput":
            labels.append("Caput")

        elif legal_unit == "paragraph":
            if number:
                labels.append(f"§ {number}")

        elif legal_unit == "inciso":
            if number:
                labels.append(f"Inciso {number}")

        elif legal_unit == "alinea":
            if number:
                labels.append(f"Alínea {number}")

        elif legal_unit == "item":
            if number:
                labels.append(f"Item {number}")

        hierarchy = " | ".join(labels)

        parent_context = metadata.get("parent_context")

        # Quando existe contexto hierárquico, ele é enviado junto
        # com o texto original para avaliação do Cross-Encoder.
        if parent_context and parent_context.strip():
            sections = []

            if hierarchy:
                sections.append(hierarchy)

            sections.append(
                f"Contexto do caput:\n{parent_context}"
            )

            sections.append(
                f"Texto do dispositivo:\n{document.page_content}"
            )

            return "\n\n".join(sections)

        # Mantém o comportamento anterior para documentos sem contexto.
        if hierarchy:
            return f"{hierarchy}\n{document.page_content}"

        return document.page_content
    
    
    @staticmethod
    def _get_document_id(document: Document) -> str | None:
        """Obtém o identificador estável de uma unidade jurídica."""

        metadata = document.metadata or {}

        document_id = (
            metadata.get("source_node_id")
            or metadata.get("chunk_id")
            or document.id
        )

        return str(document_id) if document_id else None

    @staticmethod
    def _format_passage(document: Document) -> str:
        """Formata uma unidade jurídica com sua hierarquia."""

        metadata = document.metadata or {}
        labels = []

        document_part = metadata.get("document_part")

        if document_part == "CF":
            labels.append("Constituição Federal")
        elif document_part == "ADCT":
            labels.append("Ato das Disposições Constitucionais Transitórias")

        article_number = metadata.get("article_number")

        if article_number:
            labels.append(f"Art. {article_number}")

        legal_unit = metadata.get("legal_unit")
        number = metadata.get("number")

        if legal_unit == "caput":
            labels.append("Caput")
        elif legal_unit == "paragraph" and number:
            labels.append(f"§ {number}")
        elif legal_unit == "inciso" and number:
            labels.append(f"Inciso {number}")
        elif legal_unit == "alinea" and number:
            labels.append(f"Alínea {number}")
        elif legal_unit == "item" and number:
            labels.append(f"Item {number}")

        hierarchy = " | ".join(labels)

        if hierarchy:
            return f"{hierarchy}\n{document.page_content}"

        return document.page_content


    def _format_contextual_passage(
        self,
        document: Document,
        documents_by_id: dict[str, Document],
        max_parent_depth: int = 2,
    ) -> str:
        """Formata o documento incluindo seus dispositivos superiores."""

        ancestors = self._get_parent_documents(
            document=document,
            documents_by_id=documents_by_id,
            max_parent_depth=max_parent_depth,
        )

        sections = []

        if ancestors:
            sections.append(
                "CONTEXTO NORMATIVO SUPERIOR:"
            )

            for ancestor in ancestors:
                sections.append(
                    self._format_passage(ancestor)
                )

        sections.append(
            "DOCUMENTO-ALVO:"
        )

        sections.append(
            self._format_passage(document)
        )

        return "\n\n".join(sections)


    
    def rerank_documents(
        self,
        query: str,
        candidates: list[Document],
    ) -> list[Document]:
        """
        Reordena documentos usando Cross-Encoder com contexto jurídico.

        Documentos pais presentes no conjunto de candidatos são
        incorporados à representação utilizada durante a avaliação.

        O conteúdo e os identificadores originais são preservados.
        """

        if not isinstance(query, str) or not query.strip():
            raise ValueError(
                "A pergunta de busca não pode estar vazia."
            )

        if not candidates:
            return []

        # 1. Indexa os candidatos por identificador.
        documents_by_id = {}

        for candidate in candidates:
            document_id = self._get_document_id(candidate)

            if document_id:
                documents_by_id[document_id] = candidate

        # 2. Prepara pares pergunta-documento contextualizados.
        pairs = [
            (
                query,
                self._format_contextual_passage(
                    document=document,
                    documents_by_id=documents_by_id,
                    max_parent_depth=2,
                ),
            )
            for document in candidates
        ]

        # 3. Executa o Cross-Encoder.
        raw_scores = self.reranker.predict(
            pairs,
            batch_size=self.batch_size,
            show_progress_bar=False,
        )

        # 4. Normaliza o formato dos scores.
        if hasattr(raw_scores, "tolist"):
            raw_scores = raw_scores.tolist()

        if isinstance(raw_scores, (int, float)):
            raw_scores = [raw_scores]

        scores = []

        for raw_score in raw_scores:

            if isinstance(raw_score, (list, tuple)):
                if len(raw_score) != 1:
                    raise RuntimeError(
                        "O Cross-Encoder retornou uma quantidade "
                        "inesperada de scores por documento."
                    )

                raw_score = raw_score[0]

            score = float(raw_score)

            if not math.isfinite(score):
                raise RuntimeError(
                    "O Cross-Encoder retornou um score inválido."
                )

            scores.append(score)

        if len(scores) != len(candidates):
            raise RuntimeError(
                "A quantidade de scores não corresponde "
                "à quantidade de documentos candidatos."
            )

        # 5. Associa scores aos documentos originais.
        ranked_documents = list(zip(scores, candidates))

        # 6. Ordena do mais relevante para o menos relevante.
        ranked_documents.sort(
            key=lambda item: item[0],
            reverse=True,
        )
        
        for rank, (score, document) in enumerate(
            ranked_documents,
            start=1,
        ):
            if self._get_document_id(document) == DIAGNOSTIC_TARGET_ID:
                logger.warning(
                    "[Q09 TRACE] CROSS-ENCODER | rank=%s | "
                    "score=%s | selecionado=%s",
                    rank,
                    score,
                    rank <= self.top_k,
                )
                break
        else:
            logger.warning(
                "[Q09 TRACE] CROSS-ENCODER | DOCUMENTO AUSENTE NOS CANDIDATOS"
            )

        # 7. Seleciona os documentos finais.
        selected_documents = []

        for score, document in ranked_documents[:self.top_k]:

            metadata = dict(document.metadata or {})
            
            parents = self._get_parent_documents(
                document=document,
                documents_by_id=documents_by_id,
                max_parent_depth=2,
            )

            if parents:
                metadata["parent_context"] = [
                    {
                        "doc_id": self._get_document_id(parent),
                        "content": parent.page_content,
                        "metadata": {
                            key: value
                            for key, value in (
                                parent.metadata or {}
                            ).items()
                            if key in {
                                "document_part",
                                "article_number",
                                "legal_unit",
                                "number",
                            }
                        },
                    }
                    for parent in parents
                ]

            metadata["rerank_score"] = round(score, 6)
            metadata["rerank_model"] = self.model_name

            selected_documents.append(
                Document(
                    id=document.id,
                    page_content=document.page_content,
                    metadata=metadata,
                )
            )

        return selected_documents


    def _get_relevant_documents(
        self,
        query: str,
        *,
        run_manager: CallbackManagerForRetrieverRun,
    ) -> list[Document]:
        """
        Recupera candidatos e os reordena pelo Cross-Encoder.
        """

        if not isinstance(query, str) or not query.strip():
            raise ValueError(
                "A pergunta de busca não pode estar vazia."
            )

        # 1. Recuperação inicial:
        # busca semântica + BM25 + combinação de scores.
        candidates = self.base_retriever.invoke(query)

        if not candidates:
            return []

        # 2. Utiliza o mesmo método disponibilizado ao avaliador.
        return self.rerank_documents(
            query=query,
            candidates=candidates,
        )
        
    def _get_parent_documents(
        self,
        document: Document,
        documents_by_id: dict[str, Document],
        max_parent_depth: int = 2,
    ) -> list[Document]:
        """Recupera os ancestrais disponíveis de uma unidade jurídica."""

        ancestors = []
        current_document = document

        document_id = self._get_document_id(document)
        visited = {document_id} if document_id else set()

        for _ in range(max_parent_depth):
            metadata = current_document.metadata or {}
            parent_id = metadata.get("parent_id")

            if not parent_id:
                break

            parent_id = str(parent_id)

            if parent_id in visited:
                break

            parent_document = documents_by_id.get(parent_id)

            if parent_document is None:
                break

            ancestors.append(parent_document)
            visited.add(parent_id)

            current_document = parent_document

        # Apresenta primeiro o ancestral mais amplo.
        return list(reversed(ancestors))


def create_reranked_retriever(
    provider: Literal["local", "cloud", "auto"] | None = None,
    top_k: int = DEFAULT_RERANK_TOP_K,
    rerank_k: int = DEFAULT_RERANK_K,
    candidate_k: int = DEFAULT_CANDIDATE_K,
    lexical_candidate_k: int = DEFAULT_LEXICAL_CANDIDATE_K,
    rrf_constant: int = DEFAULT_RRF_CONSTANT,
    settings: Settings | None = None,
    collection_name: str = DEFAULT_COLLECTION_NAME,
    model_name: str = DEFAULT_RERANKER_MODEL,
    device: str | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_length: int = DEFAULT_MAX_LENGTH,
) -> tuple[PolitizeseCrossEncoderRetriever, str]:
    """
    Cria o retriever híbrido e adiciona o Cross-Encoder.

    O modelo é carregado durante a inicialização, não a cada pergunta.
    """

    if top_k <= 0:
        raise ValueError(
            "top_k precisa ser maior que zero."
        )

    if rerank_k < top_k:
        raise ValueError(
            "rerank_k não pode ser menor que top_k."
        )

    if candidate_k < rerank_k:
        raise ValueError(
            "candidate_k não pode ser menor que rerank_k."
        )

    if batch_size <= 0:
        raise ValueError(
            "batch_size precisa ser maior que zero."
        )

    if max_length <= 0:
        raise ValueError(
            "max_length precisa ser maior que zero."
        )

    if not model_name or not model_name.strip():
        raise ValueError(
            "O nome do modelo não pode estar vazio."
        )

    # Importações tardias:
    # o retriever híbrido continua independente do Cross-Encoder.
    try:
        import torch
        from sentence_transformers import CrossEncoder

    except ImportError as error:
        raise ImportError(
            "Dependências do Cross-Encoder ausentes. "
            "Instale PyTorch e sentence-transformers."
        ) from error

    # 1. Escolhe o dispositivo.
    selected_device = device or (
        "cuda"
        if torch.cuda.is_available()
        else "cpu"
    )

    if (
        selected_device.startswith("cuda")
        and not torch.cuda.is_available()
    ):
        raise RuntimeError(
            "Foi solicitado o uso de CUDA, mas a GPU "
            "não está disponível."
        )

    # 2. Inicializa o retriever híbrido.
    base_retriever, selected_provider = create_retriever(
        provider=provider,
        k=rerank_k,
        candidate_k=candidate_k,
        lexical_candidate_k=lexical_candidate_k,
        rrf_constant=rrf_constant,
        settings=settings,
        collection_name=collection_name,
    )

    # 3. Carrega o Cross-Encoder.
    reranker = CrossEncoder(
        model_name,
        device=selected_device,
        max_length=max_length,
    )

    # 4. Cria o retriever combinado.
    retriever = PolitizeseCrossEncoderRetriever(
        base_retriever=base_retriever,
        reranker=reranker,
        top_k=top_k,
        batch_size=batch_size,
        model_name=model_name,
    )

    return retriever, selected_provider
