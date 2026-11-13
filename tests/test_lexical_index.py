from langchain_core.documents import Document

from src.rag.lexical_index import LegalBM25Index, tokenize
from src.rag.retriever import _reciprocal_rank_fusion


def test_tokenize_preserves_negation_and_removes_accents():
    tokens = tokenize("Não é possível votar sem identificação!")
    assert "nao" in tokens
    assert "possivel" in tokens
    assert "sem" in tokens
    assert "identificacao" in tokens


def test_bm25_searches_the_whole_corpus():
    documents = [
        Document(
            page_content="O Congresso Nacional é composto pela Câmara e pelo Senado.",
            metadata={"chunk_id": "ART-44", "source_node_id": "ART-44"},
        ),
        Document(
            page_content="O salário mínimo deve atender às necessidades básicas.",
            metadata={"chunk_id": "ART-7", "source_node_id": "ART-7"},
        ),
        Document(
            page_content="A Constituição define direitos políticos e cidadania.",
            metadata={"chunk_id": "ART-14", "source_node_id": "ART-14"},
        ),
    ]
    index = LegalBM25Index(documents)

    results = index.search("Congresso Nacional Câmara Senado", top_k=3)

    assert results
    assert results[0][1].metadata["source_node_id"] == "ART-44"


def test_rrf_merges_independent_rankings_and_deduplicates_nodes():
    semantic = [
        Document(
            page_content="Trecho semântico do Art. 44.",
            metadata={"source_node_id": "ART-44", "chunk_id": "ART-44-PART-1"},
        ),
        Document(
            page_content="Trecho semântico do Art. 58.",
            metadata={"source_node_id": "ART-58", "chunk_id": "ART-58"},
        ),
    ]
    lexical = [
        (
            12.0,
            Document(
                page_content="Texto integral do Art. 44, mais completo.",
                metadata={"source_node_id": "ART-44", "chunk_id": "ART-44"},
            ),
        ),
        (
            8.0,
            Document(
                page_content="Texto lexical do Art. 7º.",
                metadata={"source_node_id": "ART-7", "chunk_id": "ART-7"},
            ),
        ),
    ]

    results = _reciprocal_rank_fusion(
        semantic,
        lexical,
        top_k=3,
        rrf_constant=60,
    )

    ids = [document.metadata["source_node_id"] for document in results]
    assert len(ids) == len(set(ids))
    assert ids[0] == "ART-44"
    assert results[0].page_content == "Texto integral do Art. 44, mais completo."
    assert results[0].metadata["retrieval_sources"] == ["lexical", "semantic"]
