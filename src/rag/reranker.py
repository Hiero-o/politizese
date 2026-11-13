
import math
from typing import Any, Literal

from langchain_core.callbacks.manager import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import ConfigDict, Field

from src.core.config import Settings
from src.rag.retriever import create_retriever


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
DEFAULT_COLLECTION_NAME = "constituicao_legal"


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
        Enriquece o trecho com informações da hierarquia jurídica.

        Exemplo:
        Constituição Federal | Art. 22 | Inciso I

        O texto original continua preservado no documento.
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

        if hierarchy:
            return f"{hierarchy}\n{document.page_content}"

        return document.page_content

    def rerank_documents(
        self,
        query: str,
        candidates: list[Document],
    ) -> list[Document]:
        """
        Reordena uma lista de documentos usando o Cross-Encoder.

        Este método também pode ser utilizado pelo avaliador
        para comparar o ranking híbrido e o ranking reranked
        sobre exatamente o mesmo conjunto de candidatos.
        """

        if not isinstance(query, str) or not query.strip():
            raise ValueError(
                "A pergunta de busca não pode estar vazia."
            )

        if not candidates:
            return []

        # 1. Preparação dos pares pergunta-documento.
        pairs = [
            (
                query,
                self._format_passage(document),
            )
            for document in candidates
        ]

        # 2. Inferência do Cross-Encoder.
        raw_scores = self.reranker.predict(
            pairs,
            batch_size=self.batch_size,
            show_progress_bar=False,
        )

        # 3. Normalização do formato dos scores.
        if hasattr(raw_scores, "tolist"):
            raw_scores = raw_scores.tolist()

        if isinstance(raw_scores, (int, float)):
            raw_scores = [raw_scores]

        scores = []

        for raw_score in raw_scores:

            # Alguns modelos retornam uma lista por documento.
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

        # 4. Associa scores e documentos.
        ranked_documents = list(
            zip(scores, candidates)
        )

        # 5. Ordena do mais relevante para o menos relevante.
        ranked_documents.sort(
            key=lambda item: item[0],
            reverse=True,
        )

        # 6. Seleciona os documentos finais.
        selected_documents = []

        for score, document in ranked_documents[:self.top_k]:

            metadata = dict(document.metadata or {})

            metadata["rerank_score"] = round(
                score,
                6,
            )

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


def create_reranked_retriever(
    provider: Literal["local", "cloud", "auto"] | None = None,
    top_k: int = DEFAULT_RERANK_TOP_K,
    rerank_k: int = DEFAULT_RERANK_K,
    candidate_k: int = DEFAULT_CANDIDATE_K,
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
