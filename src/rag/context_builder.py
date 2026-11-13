
import json
from functools import lru_cache
from collections.abc import Mapping, Sequence
from typing import Any

from langchain_core.documents import Document

from src.core.config import PROJECT_ROOT
from src.rag.reranker import (
    PolitizeseCrossEncoderRetriever,
    create_reranked_retriever,
)


DEFAULT_TOP_K = 4
DEFAULT_RERANK_K = 24

DEFAULT_CANDIDATE_K = 48

DEFAULT_COLLECTION_NAME = "constituicao_legal_clean_v2"

MAX_DESCENDANT_CONTEXT_CHARS = 5000

MAX_CAPUT_SIBLING_CONTEXT_CHARS = 6000

ARTICLE_STORE_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "constituicao_artigos.json"
)



@lru_cache(maxsize=1)
def get_documentation_retriever() -> PolitizeseCrossEncoderRetriever:
    """
    Inicializa o retriever jurídico híbrido com Cross-Encoder.

    A instância e o modelo são carregados uma única vez por processo.
    """

    retriever, provider = create_reranked_retriever(
        provider="local",
        top_k=DEFAULT_TOP_K,
        rerank_k=DEFAULT_RERANK_K,
        candidate_k=DEFAULT_CANDIDATE_K,
        collection_name=DEFAULT_COLLECTION_NAME,
    )

    print(
        "[RAG] Retriever jurídico inicializado.\n"
        f"Provedor de embeddings: {provider}\n"
        f"Cross-Encoder: {retriever.model_name}\n"
        f"Dispositivo: {retriever.reranker.device}\n"
        f"Candidatos: {DEFAULT_CANDIDATE_K}\n"
        f"Documentos para reranking: {DEFAULT_RERANK_K}\n"
        f"Documentos finais: {DEFAULT_TOP_K}"
    )

    return retriever


def _flatten_serialized_node(
    node: Mapping[str, Any],
    nodes: dict[str, dict[str, Any]],
) -> None:
    """
    Percorre recursivamente a árvore jurídica serializada.
    """

    node_id = node.get("chunk_id")

    if not isinstance(node_id, str) or not node_id.strip():
        raise ValueError(
            "Foi encontrado um nó sem chunk_id no armazenamento jurídico."
        )

    if node_id in nodes:
        raise ValueError(
            f"ID duplicado no armazenamento jurídico: {node_id}"
        )

    nodes[node_id] = dict(node)

    children = node.get("children") or []

    if not isinstance(children, list):
        raise TypeError(
            f"Os filhos do nó {node_id} precisam ser uma lista."
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
    Carrega a árvore jurídica completa e cria um índice por node_id.

    O JSON é carregado uma única vez por processo.
    """

    if not ARTICLE_STORE_PATH.exists():
        raise FileNotFoundError(
            "Armazenamento jurídico não encontrado: "
            f"{ARTICLE_STORE_PATH}\n"
            "Execute py indexar_base.py para gerar os dados."
        )

    try:
        payload = json.loads(
            ARTICLE_STORE_PATH.read_text(
                encoding="utf-8"
            )
        )
    except json.JSONDecodeError as error:
        raise ValueError(
            "O arquivo da árvore jurídica contém JSON inválido."
        ) from error

    articles = payload.get("articles")

    if not isinstance(articles, list) or not articles:
        raise ValueError(
            "O arquivo JSON não possui artigos válidos."
        )

    nodes: dict[str, dict[str, Any]] = {}

    for article in articles:
        if not isinstance(article, Mapping):
            raise TypeError(
                "Foi encontrado um artigo inválido no JSON."
            )

        _flatten_serialized_node(article, nodes)

    # Confirma que todos os relacionamentos possuem um destino.
    for node_id, node in nodes.items():
        parent_id = node.get("parent_id")

        if parent_id is not None and parent_id not in nodes:
            raise ValueError(
                f"Pai inexistente para {node_id}: {parent_id}"
            )

    print(
        f"[RAG] Árvore jurídica carregada: "
        f"{len(nodes)} unidades."
    )

    return nodes


def _get_node_ancestry(
    node_id: str,
    nodes: Mapping[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Recupera a cadeia hierárquica entre o artigo e a unidade jurídica.
    """

    if node_id not in nodes:
        raise KeyError(
            f"Unidade jurídica não encontrada no JSON: {node_id}"
        )

    ancestry = []
    visited = set()

    current = nodes[node_id]

    while current is not None:
        current_id = current["chunk_id"]

        if current_id in visited:
            raise ValueError(
                f"Ciclo detectado na hierarquia: {current_id}"
            )

        visited.add(current_id)
        ancestry.append(current)

        parent_id = current.get("parent_id")

        if parent_id is None:
            break

        current = nodes.get(parent_id)

        if current is None:
            raise ValueError(
                f"Pai não encontrado durante a recuperação: {parent_id}"
            )

    ancestry.reverse()

    return ancestry


def _collect_descendant_context(
    node: Mapping[str, Any],
    hierarchy: list[str],
    included_node_ids: set[str],
    max_chars: int = MAX_DESCENDANT_CONTEXT_CHARS,
) -> tuple[list[str], int]:
    """
    Recupera os descendentes do dispositivo selecionado.

    Preserva os textos completos das unidades incluídas,
    respeitando um limite de caracteres para o contexto.
    """

    sections = []
    remaining_chars = max_chars
    omitted_count = 0

    def visit(
        parent: Mapping[str, Any],
        parent_hierarchy: list[str],
    ) -> None:
        nonlocal remaining_chars
        nonlocal omitted_count

        children = parent.get("children") or []

        for child in children:
            child_id = child.get("chunk_id")

            if not child_id or child_id in included_node_ids:
                continue

            label = _format_legal_label(child)

            child_hierarchy = parent_hierarchy + [label]

            content = str(
                child.get("texto") or ""
            ).strip()

            block = (
                f"[{' > '.join(child_hierarchy)}]\n"
                f"{content}"
            )

            # Só inclui a unidade se seu conteúdo completo couber.
            if content and len(block) <= remaining_chars:
                sections.append(block)

                included_node_ids.add(child_id)
                remaining_chars -= len(block)

            elif content:
                omitted_count += 1

            # Continua percorrendo a hierarquia,
            # mesmo quando uma unidade intermediária não couber.
            visit(
                child,
                child_hierarchy,
            )

    visit(node, hierarchy)

    return sections, omitted_count


def _collect_caput_sibling_context(
    root: Mapping[str, Any],
    selected_node: Mapping[str, Any],
    hierarchy: list[str],
    included_node_ids: set[str],
    max_chars: int = MAX_CAPUT_SIBLING_CONTEXT_CHARS,
) -> tuple[list[str], int]:
    """
    Recupera os incisos que são irmãos de um caput.

    Aplica-se quando o caput termina com dois-pontos,
    indicando que introduz uma enumeração de dispositivos.

    Exemplo:
        Art. 22
        ├── Caput
        ├── Inciso I
        ├── Inciso II
        └── Inciso III
    """

    # A expansão só se aplica a caputs.
    if selected_node.get("legal_unit") != "caput":
        return [], 0

    caput_text = str(
        selected_node.get("texto") or ""
    ).strip()

    # Dois-pontos indicam que o caput introduz uma lista.
    if not caput_text.endswith(":"):
        return [], 0

    article_children = root.get("children") or []

    # Seleciona os incisos diretamente subordinados ao artigo.
    sibling_incisos = [
        child
        for child in article_children
        if (
            child.get("legal_unit") == "inciso"
            and child.get("chunk_id")
            != selected_node.get("chunk_id")
        )
    ]

    if not sibling_incisos:
        return [], 0

    sections = []
    remaining_chars = max_chars
    omitted_count = 0

    # Remove o Caput da hierarquia para construir a identificação
    # dos incisos irmãos corretamente.
    article_hierarchy = hierarchy[:-1]

    for sibling in sibling_incisos:
        sibling_id = sibling.get("chunk_id")

        if not sibling_id or sibling_id in included_node_ids:
            continue

        label = _format_legal_label(sibling)

        sibling_hierarchy = (
            article_hierarchy + [label]
        )

        content = str(
            sibling.get("texto") or ""
        ).strip()

        if not content:
            continue

        block = (
            f"[{' > '.join(sibling_hierarchy)}]\n"
            f"{content}"
        )

        # Inclui somente dispositivos cujo texto completo caiba.
        if len(block) <= remaining_chars:
            sections.append(block)

            included_node_ids.add(sibling_id)

            remaining_chars -= len(block)

        else:
            omitted_count += 1

    return sections, omitted_count



def _format_legal_label(node: Mapping[str, Any]) -> str:
    """Converte uma unidade jurídica em uma identificação legível."""

    legal_unit = node.get("legal_unit")
    number = node.get("number")

    if legal_unit == "article":
        return f"Art. {node.get('article_number', number)}"

    if legal_unit == "caput":
        return "Caput"

    if legal_unit == "paragraph":
        if number == "unico":
            return "Parágrafo único"

        return f"§ {number}"

    if legal_unit == "inciso":
        return f"Inciso {number}"

    if legal_unit == "alinea":
        return f"Alínea {number}"

    if legal_unit == "item":
        return f"Item {number}"

    return str(legal_unit or "Unidade jurídica")


def _format_source_name(
    node: Mapping[str, Any],
) -> str:
    """Identifica o documento de origem."""

    document_name = node.get("document_name")

    if document_name:
        return str(document_name)

    source = node.get("source")

    if source:
        return str(source).replace("\\", "/").rsplit("/", 1)[-1]

    return "Documento não identificado"



def format_documentation_context(
    documents: Sequence[Document],
) -> str:
    """
    Reconstrói o contexto jurídico a partir dos resultados do retriever.

    Inclui:
    - Ancestrais da unidade encontrada.
    - Texto integral da unidade original.
    - Descendentes juridicamente subordinados.
    """

    nodes = get_legal_node_store()

    sections = []

    included_node_ids = set()
    seen_source_nodes = set()

    for document in documents:
        metadata = document.metadata or {}

        source_node_id = (
            metadata.get("source_node_id")
            or metadata.get("chunk_id")
        )

        if not source_node_id:
            raise ValueError(
                "Resultado do retriever sem source_node_id."
            )

        source_node_id = str(source_node_id)

        if (source_node_id in seen_source_nodes or source_node_id in included_node_ids):
            continue

        seen_source_nodes.add(source_node_id)

        ancestry = _get_node_ancestry(
            source_node_id,
            nodes,
        )

        root = ancestry[0]
        selected_node = ancestry[-1]

        if root.get("legal_unit") != "article":
            raise ValueError(
                f"A raiz da hierarquia não é um artigo: "
                f"{source_node_id}"
            )

        hierarchy_labels = [
            _format_legal_label(node)
            for node in ancestry
        ]

        hierarchy = " > ".join(hierarchy_labels)

        page_start = selected_node.get("pagina_inicial")
        page_end = selected_node.get("pagina_final")

        if page_start == page_end:
            page_label = str(
                page_start or "não identificada"
            )
        else:
            page_label = (
                f"{page_start or 'não identificada'}"
                f"-{page_end or 'não identificada'}"
            )

        section_lines = [
            f"[Dispositivo {len(sections) + 1}]",
            f"Documento: {_format_source_name(root)}",
            f"Parte documental: {root.get('document_part')}",
            f"Localização: {hierarchy}",
            f"Páginas: {page_label}",
        ]
        
        # Inclui o caput do artigo como contexto geral.
        caput_node = next(
            (
                child
                for child in root.get("children", [])
                if child.get("legal_unit") == "caput"
            ),
            None,
        )

        if (
            caput_node
            and selected_node.get("legal_unit") != "caput"
            and caput_node["chunk_id"] not in included_node_ids
        ):
            caput_text = str(
                caput_node.get("texto") or ""
            ).strip()

            if caput_text:
                section_lines.extend(
                    [
                        "\nContexto geral do artigo (caput):",
                        caput_text,
                    ]
                )

                included_node_ids.add(caput_node["chunk_id"])

        # Recupera os ancestrais intermediários.
        ancestor_contexts = []

        for ancestor in ancestry[1:-1]:
            ancestor_id = ancestor["chunk_id"]

            ancestor_text = str(
                ancestor.get("texto") or ""
            ).strip()

            if (
                ancestor_text
                and ancestor_id not in included_node_ids
            ):
                ancestor_contexts.append(
                    (
                        _format_legal_label(ancestor),
                        ancestor_text,
                    )
                )

                included_node_ids.add(ancestor_id)

        if ancestor_contexts:
            section_lines.append(
                "\nContexto hierárquico:"
            )

            for label, content in ancestor_contexts:
                section_lines.append(
                    f"[{label}]\n{content}"
                )

        # Recupera o conteúdo integral da unidade original.
        original_text = str(
            selected_node.get("texto") or ""
        ).strip()

        if not original_text:
            raise ValueError(
                f"Unidade jurídica sem texto: {source_node_id}"
            )

        section_lines.extend(
            [
                "\nTexto integral do dispositivo:",
                original_text,
            ]
        )

        included_node_ids.add(source_node_id)

        
        # Recupera incisos irmãos quando o caput introduz uma enumeração.
        sibling_sections, omitted_sibling_count = (
            _collect_caput_sibling_context(
                root=root,
                selected_node=selected_node,
                hierarchy=hierarchy_labels,
                included_node_ids=included_node_ids,
            )
        )

        if sibling_sections:
            section_lines.append(
                "\nDispositivos do mesmo artigo "
                "(incisos introduzidos pelo caput):"
            )

            section_lines.extend(sibling_sections)

        if omitted_sibling_count:
            section_lines.append(
                f"\n[ATENÇÃO: {omitted_sibling_count} "
                "inciso(s) não incluído(s) "
                "devido ao limite de contexto.]"
            )

        # Recupera os descendentes do dispositivo selecionado.
        descendants, omitted_count = (
            _collect_descendant_context(
                selected_node,
                hierarchy_labels,
                included_node_ids,
            )
        )

        if descendants:
            section_lines.append(
                "\nDispositivos subordinados:"
            )

            section_lines.extend(descendants)

        if omitted_count:
            section_lines.append(
                f"\n[ATENÇÃO: {omitted_count} "
                "subdispositivo(s) não incluído(s) "
                "devido ao limite de contexto.]"
            )

        sections.append(
            "\n".join(section_lines)
        )

    return "\n\n---\n\n".join(sections)


def build_documentation_context(
    question: str,
) -> str | None:
    """
    Recupera os dispositivos relevantes e reconstrói
    o contexto jurídico que será enviado ao LLM.
    """

    if not isinstance(question, str) or not question.strip():
        raise ValueError(
            "A pergunta não pode estar vazia."
        )

    retriever = get_documentation_retriever()

    documents = retriever.invoke(question)

    if not documents:
        return None

    context = format_documentation_context(documents)

    if not context.strip():
        return None

    return context
