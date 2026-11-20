# Estratégia de chunking e recuperação — Politize-se

## Segmentação jurídica principal
A indexação da base jurídico-normativa simulada utiliza parser estrutural: artigo, caput, parágrafo, inciso, alínea e item. Para a base simulada, a execução registrada produziu 19 dispositivos/unidades e 19 chunks preparados; o índice semântico auxiliar registrou 11 seções. A estratégia preserva a unidade normativa e evita cortar uma condição ou exceção no meio.

`src/rag/chunking.py` também contém um splitter genérico com `RecursiveCharacterTextSplitter`, `chunk_size=512` e `chunk_overlap=80`. Ele não deve ser confundido com a segmentação jurídica estrutural do indexador.

## Parent Document Retriever — comparação registrada
Em `data/avaliacoes/resultados/resultado_retrievers.json`, os filhos foram mantidos em 200 caracteres/overlap 40, k=4, variando-se o tamanho dos pais:

| Experimento | Pai / overlap | Filhos | Pais armazenados | Contexto médio | Tempo médio |
|---|---:|---:|---:|---:|---:|
| parent_1024 | 1024 / 128 | 200 / 40 | 814 | 900,77 caracteres | 0,0649 s |
| parent_1512 | 1512 / 192 | 200 / 40 | 566 | 1270,00 caracteres | 0,0512 s |
| parent_2024 | 2024 / 256 | 200 / 40 | 517 | 1690,72 caracteres | 0,0859 s |

A configuração 1024/128 para pais e 200/40 para filhos é o padrão mantido no módulo. Ela fornece contexto mais compacto que 2024, com tempo médio baixo. 1512 foi um pouco mais rápido, mas recuperou contexto maior. O arquivo mede contagem, tamanho de contexto e tempo; não fornece precision/recall para declarar superioridade semântica absoluta entre os tamanhos.

## Semantic Retriever e fusão
O índice auxiliar registra 424 seções e 3360 unidades, com `candidate_k=48`, `section_k=8`, `unit_k=48`, `units_per_section_k=8` e RRF constant 60. O experimento `comparacao_hibrido_semantico_fusao.json` (12/11/2026, oito perguntas) apresenta:

| Estratégia | Recall@48 artigo | Recall@48 unidade jurídica | Tempo médio |
|---|---:|---:|---:|
| Híbrido | 0,3750 | 0,1250 | 0,9045 s |
| Semântico auxiliar | 0,5625 | 0,2917 | 0,6174 s |
| Fusão RRF | 0,6250 | 0,3333 | 1,5224 s |

A fusão obteve maior recall@48 no conjunto experimental, mas também maior latência. Isso demonstra complementaridade, não que o SemanticIndexRetriever esteja conectado ao backend web.

## Caminho realmente instanciado pelo assistente web
`backend/services/assistente.py` chama `build_react_agent` com `enable_reranker=True` e `rerank_top_k=8`. O caminho principal é:
1. Question Decomposer;
2. Query Rewriter;
3. ChromaDB + BM25;
4. RRF com constante 60;
5. Cross-Encoder;
6. fusão/deduplicação de resultados das subperguntas;
7. serialização das evidências com doc_id.

Parâmetros do construtor: `candidate_k=120`, `lexical_candidate_k=120`, `rrf_constant=60`, `rerank_top_k=8`, limite de seis chamadas de ferramenta. A coleção-base declarada é `constituicao_legal_clean_v2`, com nome físico final derivado do perfil de embeddings.

**Distinção técnica:** ParentDocumentRetriever e SemanticIndexRetriever têm módulos/experimentos próprios, mas não são instanciados pelo serviço web principal. O backend usa retriever híbrido iterativo e expansão hierárquica de contexto jurídico. A documentação não deve misturar esses caminhos.

## Justificativa
No domínio jurídico, fragmentos pequenos demais podem separar regra, exceção e contexto do dispositivo; fragmentos grandes demais elevam o contexto enviado ao modelo, o ruído e a latência. A segmentação estrutural preserva o significado normativo; a recuperação híbrida e o reranking equilibram granularidade e cobertura. O grupo informou que testou chunks menores e decidiu manter a estratégia atual. Este documento demonstra os experimentos quantitativos que existem no repositório, sem inventar uma comparação ausente.
