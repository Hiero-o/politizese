import re

import unicodedata

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

#Expressões regulares


#Artigos 5º, artigos 5º-A, artigo 22


ARTICLE_PATTERN = re.compile(
    r"^\s*Art\.\s*"
    r"(?P<number>\d+)"
    r"\s*(?:[º°])?"
    r"(?:\s*-\s*(?P<suffix>[A-Za-z]))?"
    r"(?:\s*[\.:]\s*|\s+|$)"
    r"(?P<body>.*)$"
)


# Parágrafos: § 1º, § 2ºA.

PARAGRAPH_PATTERN = re.compile(
    r"^\s*§\s*"
    r"(?P<number>\d+)"
    r"\s*(?:[º°])?"
    r"\s*(?:-\s*(?P<suffix>[A-Za-z]))?"
    r"\s*(?:[.:]\s*)?"
    r"(?P<body>.*)$",
    re.IGNORECASE,
)

UNIQUE_PARAGRAPH_PATTERN = re.compile(
    r"^\s*Parágrafo\s+único\.?\s*(?P<body>.*)$",
    re.IGNORECASE
)

INCISO_PATTERN = re.compile(
    r"^\s*(?P<number>[IVXLCDM]+(?:-[A-Za-z])?)"
    r"\s*[–—−-]\s*"
    r"(?P<body>.*)$",
    re.IGNORECASE,
)

ALINEA_PATTERN = re.compile(
    r"^\s*(?P<number>[a-z])\)\s*(?P<body>.*)$",
    re.IGNORECASE,
)

ITEM_PATTERN = re.compile(
    r"^\s*(?P<number>\d+)[.)]\s*(?P<body>.*)$"
)


ARTICLE_HEADER_UNIT_PATTERN = (
    r"(?:"
    r"§\s*\d+\s*[º°]?(?:\s*-\s*[A-Za-z])?"
    r"|parágrafo\s+único"
    r"|caput"
    r"|inciso\s+[IVXLCDM]+(?:-[A-Za-z])?"
    r"|alínea\s+[a-z]"
    r"|[IVXLCDM]+"
    r"|[a-z]"
    r")"
)

ARTICLE_HEADER_PATTERN = re.compile(
    r"^\s*Art\.\s*\d+\s*[º°]?\s*,\s*"
    + ARTICLE_HEADER_UNIT_PATTERN
    + r"(?:\s*,\s*"
    + ARTICLE_HEADER_UNIT_PATTERN
    + r")*\s*$",
    re.IGNORECASE,
)


SECTION_HEADER_PATTERN = re.compile(
    r"^\s*(?:T[IÍ]TULO|CAP[IÍ]TULO|SE[CÇ][AÃ]O|SUBSE[CÇ][AÃ]O)"
    r"\s+[IVXLCDM0-9]+(?:\s*[º°ª])?\s*$",
    re.IGNORECASE,
)

EDITORIAL_SIGNATURE_START_PATTERN = re.compile(
    r"^\s*Bras[ií]lia,\s*5\s+de\s+outubro\s+de\s+1988\.?\s*$",
    re.IGNORECASE,
)


# Modelos de dados

@dataclass(slots=True)
class LegalNode:
    """Representa uma unidade da estrutura jurídica
    
    Pode representar:
        - Artigo
        - Caput
        - Parágrafo
        - Inciso
        - Alínea
        - Item."""
        
    
    node_id:str
    parent_id:str | None
    
    document_id: str
    document_name: str
    source: str
    
    document_part: str
    article_id: str
    article_number: str
    
    legal_unit: str
    number: str | None
    
    page_start: int
    page_end: int
    
    text: str
    
    children: list["LegalNode"] = field(default_factory=list)

    def to_record(self) -> dict[str, Any]:
        """Converte a unidade jurídica em um dicionário."""

        return {
            "chunk_id": self.node_id,
            "parent_id": self.parent_id,
            "document_id": self.document_id,
            "document_name": self.document_name,
            "source": self.source,
            "document_part": self.document_part,
            "article_id": self.article_id,
            "article_number": self.article_number,
            "legal_unit": self.legal_unit,
            "number": self.number,
            "pagina_inicial": self.page_start,
            "pagina_final": self.page_end,
            "texto": self.text,
        }
        
@dataclass(slots=True)
class _ArticleBuffer:
    """armazena temporariamente o conteúdo de um artigo"""
    
    number: str
    part: str
    heading: str
    first_page: int
    source: str
    document_name: str
    body_lines: list[tuple[str, int]] = field(default_factory=list)

# Normalização

def _normalize_heading(text:str) -> str:
    
    """normaliza titúlos para facilitar a identificação de seções."""
    
    normalized = unicodedata.normalize("NFKD", text.casefold())
    
    return "".join(
        character
        for character in normalized
        if not unicodedata.combining(character)
    ).strip()
    



def _clean_line(text:str) -> str:
    
    """Realiza uma limpeza consevadora das linhas extraídas. Não remove palavras, pontuação jurídica ou conteúdo normativo."""
    
    text = text.replace("\u00ad", "")
    text = text.replace("\xa0", " ")
    text = text.replace("\ufeff", "")
    text = text.replace("\u200e", "")
    text = text.replace("\u200f", "")
    
    return text.strip()


def _join_soft_hyphenated_line_breaks(text: str) -> str:
    """
    Une palavras separadas por um hífen condicional
    no final de uma linha extraída do PDF.

    Exemplo:
        ques\\xad\\ntões -> questões

    Não altera quebras de linha comuns.
    """
    return re.sub(
        r"\u00ad[ \t]*\r?\n[ \t]*",
        "",
        text,
    )


def _is_noise_line(text: str) -> bool:
    """Identifica ruídos editoriais comuns na extração dos PDFs."""
    
    normalized = _normalize_heading(text)
    
    if not normalized:
        return True
    #numero isolado de página
    if re.fullmatch(r"\d{1,4}", normalized):
        return True
    #palavra de navegação editorial.
    if normalized in {"sumario", "sumário"}:
        return True
    #Cabeçalho editorial que referencia um dispositivo.
    if ARTICLE_HEADER_PATTERN.match(text):
        return True
    
    return False


def _is_adct_heading(text: str) -> bool:
    """Identifica o titulo do ato das disposicoes constitucionais transitorias."""
    
    normalized = _normalize_heading(text)
    
    return normalized == (
        "Ato das disposicoes constitucionais transitorias."
    )
    

#Identificadores

def _format_article_number(number:str) -> str:
    """Formata o numero de um artigo para gerar um identificador estável."""
    
    match = re.fullmatch(
        r"(?P<number>\d+)(?P<suffix>[A-Za-z]?)",
        number.strip(),
    )
    
    if not match:
        raise ValueError(f"Numero de artigo inválido: {number}")
    
    
    numeric_part = match.group("number").zfill(4)
    suffix = match.group("suffix").upper()
    
    return f"{numeric_part}{suffix}"

def _create_article_id(
    document_id: str,
    document_part: str,
    article_number : str,
) -> str:
    """Gera o identificador de um artigo"""
    
    formatted_number = _format_article_number(article_number)
    
    if document_part == "ADCT" or document_part == "adct":
        return (f"{document_id}-ADC-ART-{formatted_number}")
    
    return f"{document_id}-ART-{formatted_number}"

def _create_unit_id(
    parent_id: str,
    legal_unit: str,
    number: str | None,
) -> str:
    """Gera identificadores hierárquicos para as unidades jurídicas."""

    if legal_unit == "caput":
        suffix = "CAPUT"

    elif legal_unit == "paragraph":
        if number == "unico":
            suffix = "PAR-UNICO"
        else:
            match = re.fullmatch(r"(\d+)([A-Za-z]?)", number or "")

            if not match:
                raise ValueError(
                    f"Identificador de parágrafo inválido: {number}"
                )

            suffix = (
                f"PAR-{match.group(1).zfill(4)}"
                f"{match.group(2).upper()}"
            )

    elif legal_unit == "inciso":
        suffix = f"INC-{number.upper()}"

    elif legal_unit == "alinea":
        suffix = f"ALI-{number.upper()}"

    elif legal_unit == "item":
        suffix = f"ITEM-{str(number).zfill(4)}"

    else:
        raise ValueError(
            f"Tipo de unidade jurídica não suportado: {legal_unit}"
        )

    return f"{parent_id}-{suffix}"

#Criacao das unidades juridicas

def _append_text(
    node: LegalNode,
    text: str,
    page_number: int,
) -> None:
    """Acrescenta texto a uma unidade sem perder sua paginação."""

    text = text.strip()

    if not text:
        return

    if node.text:
        node.text += "\n" + text
    else:
        node.text = text

    node.page_end = page_number

def _create_unit(
    *,
    article: LegalNode,
    parent: LegalNode,
    legal_unit: str,
    number: str,
    page_number: int,
)-> LegalNode:
    """Cria uma unidade juridica e a conecta ao seu pai."""
    
    node_id = _create_unit_id(
        parent.node_id,
        legal_unit,
        number,
    )
    
    node = LegalNode(
        node_id=node_id,
        parent_id=parent.node_id,
        document_id=article.document_id,
        document_name=article.document_name,
        source=article.source,
        document_part=article.document_part,
        article_id=article.node_id,
        article_number=article.article_number,
        legal_unit=legal_unit,
        number=number,
        page_start=page_number,
        page_end=page_number,
        text="",
    )

    parent.children.append(node)

    return node

def _parse_article_units(
    article: LegalNode,
    body_lines: Sequence[tuple[str, int]],
) -> None:
    
    """Identifica caput, pargrafos, incisos, alineas e itens. Os relacionamentos seguem a hierarquia juridica:
    artigo -> paragrado -> inciso -> alinea -> item.
    Unidades que não possuam nivel intermediariopodem ser diretamente filhas do artigo."""
    
    current_unit: LegalNode | None = None

    current_paragraph: LegalNode | None = None
    current_inciso: LegalNode | None = None
    current_alinea: LegalNode | None = None

    for line, page_number in body_lines:
        line = line.strip()

        if not line:
            continue
            
                # 1. Parágrafo numerado.

        match = PARAGRAPH_PATTERN.match(line)

        if match:
            number = match.group("number")
            suffix = match.group("suffix")
            body_text = match.group("body").strip()

            if suffix:
                number += suffix.upper()

            # Verifica se a linha é uma anotação legislativa isolada.
            is_amendment_note = bool(
                re.match(
                    r"^\(\s*(?:Inclu[ií]d[oa]s?|Reda[cç][aã]o|"
                    r"Revogad[oa]s?|Acrescentad[oa]s?|Alterad[oa]s?)\b",
                    body_text,
                    re.IGNORECASE,
                )
            )

            if is_amendment_note:
                existing_paragraph = next(
                    (
                        child
                        for child in article.children
                        if (
                            child.legal_unit == "paragraph"
                            and child.number == number
                        )
                    ),
                    None,
                )

                # Anexa a anotação ao parágrafo já existente.
                if existing_paragraph is not None:
                    _append_text(
                        existing_paragraph,
                        body_text,
                        page_number,
                    )
                    continue

            # Identifica referências a parágrafos,
            # em vez de confundi-las com novos dispositivos.
            starts_with_reference = (
                body_text.startswith((",", ";", ":"))
                or (
                    bool(body_text)
                    and body_text[0].islower()
                )
            )

            if starts_with_reference:
                # Preserva o fragmento na unidade atualmente aberta.
                if current_unit is None:
                    current_unit = _create_unit(
                        article=article,
                        parent=article,
                        legal_unit="caput",
                        number=None,
                        page_number=page_number,
                    )

                _append_text(
                    current_unit,
                    line,
                    page_number,
                )

                continue

            # Cria um novo parágrafo legítimo.
            current_unit = _create_unit(
                article=article,
                parent=article,
                legal_unit="paragraph",
                number=number,
                page_number=page_number,
            )

            current_paragraph = current_unit
            current_inciso = None
            current_alinea = None

            _append_text(
                current_unit,
                body_text,
                page_number,
            )

            continue
        
        # 2. Paragrafo unico.
        
        match = UNIQUE_PARAGRAPH_PATTERN.match(line)
        if match:
            current_unit = _create_unit(
                article=article,
                parent=article,
                legal_unit="paragraph",
                number="unico",
                page_number=page_number,
            )

            current_paragraph = current_unit
            current_inciso = None
            current_alinea = None

            _append_text(
                current_unit,
                match.group("body"),
                page_number,
            )

            continue

        # 3. Incisos.
        
        match = INCISO_PATTERN.match(line)
            
        if match:
            parent = current_paragraph or article

            current_unit = _create_unit(
                article=article,
                parent=parent,
                legal_unit="inciso",
                number=match.group("number").upper(),
                page_number=page_number,
            )

            current_inciso = current_unit
            current_alinea = None

            _append_text(
                current_unit,
                match.group("body"),
                page_number,
            )

            continue

        # 4. Alíneas.
        match = ALINEA_PATTERN.match(line)

        if match:
            parent = (
                current_inciso
                or current_paragraph
                or article
            )

            current_unit = _create_unit(
                article=article,
                parent=parent,
                legal_unit="alinea",
                number=match.group("number").lower(),
                page_number=page_number,
            )

            current_alinea = current_unit

            _append_text(
                current_unit,
                match.group("body"),
                page_number,
            )

            continue

        # 5. Itens numerados.
        match = ITEM_PATTERN.match(line)

        if match:
            parent = (
                current_alinea
                or current_inciso
                or current_paragraph
                or article
            )

            current_unit = _create_unit(
                article=article,
                parent=parent,
                legal_unit="item",
                number=match.group("number"),
                page_number=page_number,
            )

            _append_text(
                current_unit,
                match.group("body"),
                page_number,
            )

            continue
            
        # TExto comum: Pertence à unidade atualmente aberta.
        
        if current_unit is None:
            current_unit = _create_unit(
                article=article,
                parent=article,
                legal_unit="caput",
                number=None,
                page_number=page_number,
            )

        _append_text(
            current_unit,
            line,
            page_number,
        )

#Processamento de um documento

def _parse_single_document(
    pages: Sequence[Mapping[str, Any]],
    document_id: str,
) -> list[LegalNode]:
    """Processa as páginas de um único documento constitucional."""

    if not pages:
        return []

    source = str(
        pages[0].get("caminho")
        or pages[0].get("documento")
        or "origem_desconhecida"
    )

    document_name = str(
        pages[0].get("documento")
        or Path(source).name
    )

    articles: list[LegalNode] = []

    current_article: _ArticleBuffer | None = None
    current_part = "CF"

    last_main_article_number = 0
    
    skip_section_title = False
    
    skip_editorial_block = False
    
    def finalize_article() -> None:
        nonlocal current_article
        nonlocal last_main_article_number

        if current_article is None:
            return

        article_id = _create_article_id(
            document_id=document_id,
            document_part=current_article.part,
            article_number=current_article.number,
        )

        all_body_text = [
            line
            for line, _ in current_article.body_lines
            if line
        ]

        article_text = current_article.heading

        if all_body_text:
            article_text += "\n" + "\n".join(all_body_text)

        page_end = max(
            [current_article.first_page]
            + [page for _, page in current_article.body_lines]
        )

        article = LegalNode(
            node_id=article_id,
            parent_id=None,
            document_id=document_id,
            document_name=current_article.document_name,
            source=current_article.source,
            document_part=current_article.part,
            article_id=article_id,
            article_number=current_article.number,
            legal_unit="article",
            number=current_article.number,
            page_start=current_article.first_page,
            page_end=page_end,
            text=article_text.strip(),
        )

        _parse_article_units(
            article,
            current_article.body_lines,
        )
        existing_article = next(
            (
                existing
                for existing in articles
                if existing.node_id == article.node_id
            ),
            None,
        )

        if existing_article:
            print("\n[DUPLICAÇÃO DE ARTIGO DETECTADA]")
            print(f"ID: {article.node_id}")
            print(f"Parte documental: {article.document_part}")

            print(
                f"Primeira ocorrência: páginas "
                f"{existing_article.page_start}-{existing_article.page_end}"
            )

            print(
                f"Segunda ocorrência: páginas "
                f"{article.page_start}-{article.page_end}"
            )

            print(
                f"Primeiro conteúdo: {existing_article.text[:200]!r}"
            )

            print(
                f"Segundo conteúdo: {article.text[:200]!r}"
            )

        articles.append(article)

        if current_article.part == "CF":
            numeric_match = re.match(
                r"\d+",
                current_article.number,
            )

            if numeric_match:
                last_main_article_number = int(
                    numeric_match.group()
                )

        current_article = None

    ordered_pages = sorted(
        pages,
        key=lambda item: int(item.get("pagina", 0)),
    )

    for page in ordered_pages:
        text = page.get("texto", "")

        if not isinstance(text, str):
            raise TypeError(
                "O campo 'texto' de cada página deve ser uma string."
            )

        try:
            page_number = int(page.get("pagina", 0))
        except (TypeError, ValueError) as error:
            raise ValueError(
                "Página com numeração inválida."
            ) from error

        if page_number < 1:
            raise ValueError(
                "A numeração das páginas precisa ser positiva."
            )
        
        text = _join_soft_hyphenated_line_breaks(text)

        for raw_line in text.splitlines():
            line = _clean_line(raw_line)

            if not line:
                continue

            # Identifica o encerramento do texto normativo
            # e finaliza o artigo antes das assinaturas.
            if EDITORIAL_SIGNATURE_START_PATTERN.match(line):
                finalize_article()
                skip_editorial_block = True
                continue

            # Ignora assinaturas e créditos editoriais até
            # encontrar o próximo artigo constitucional.
            if skip_editorial_block:
                if _is_noise_line(line):
                    continue

                if not ARTICLE_PATTERN.match(line):
                    continue

                # Encontramos um novo artigo.
                skip_editorial_block = False

            if _is_noise_line(line):
                continue

            # Identifica cabeçalhos estruturais editoriais.
            if SECTION_HEADER_PATTERN.match(line):
                skip_section_title = True
                continue

            # Descarta o título posterior, mas preserva
            # possíveis inícios de conteúdo jurídico.
            if skip_section_title:
                skip_section_title = False

                if (
                    not ARTICLE_PATTERN.match(line)
                    and not _is_adct_heading(line)
                ):
                    continue

            if (
                _is_adct_heading(line)
                and last_main_article_number >= 200
            ):
                finalize_article()
                current_part = "ADCT"
                continue

            article_match = ARTICLE_PATTERN.match(line)

            if article_match:
                finalize_article()

                number = article_match.group("number")
                suffix = article_match.group("suffix")

                if suffix:
                    number += suffix.upper()

                numeric_number = int(
                    article_match.group("number")
                )

                #Segunda forma de detectar a transicao para o ADCT:
                #Reinicio da numeraacao após o ultimo artigo constitucional.
                
                if (
                    current_part == "CF"
                    and last_main_article_number >= 200
                    and numeric_number <= 5
                ):
                    current_part = "ADCT"

                heading = line[
                    :article_match.start("body")
                ].strip()

                current_article = _ArticleBuffer(
                    number=number,
                    part=current_part,
                    heading=heading,
                    first_page=page_number,
                    source=source,
                    document_name=document_name,
                )

                initial_body = article_match.group("body").strip()

                if initial_body:
                    current_article.body_lines.append(
                        (initial_body, page_number)
                    )

                continue

            # Ignora material anterior ao primeiro artigo.
            if current_article is None:
                continue

            current_article.body_lines.append(
                (line, page_number)
            ) 

    finalize_article()

    return articles


#Interface pública

def parse_constitution_pages(
    pages: Sequence[Mapping[str, Any]],
    *,
    document_id: str = "CF1988",
) ->list[LegalNode]:
    
    """Converte páginas extraidas da constituicao em uma arvore juridica.
    Cada artigo é um nós raiz.
    Seus Caputs, paragráfos, incisos, alíneas e itens são registrados como unidades relacionadas."""
    
    if not pages:
        raise ValueError("A lista de páginas não pode estar vazia")
    
    if not document_id or not document_id.strip():
        raise ValueError("document_id não pode estar vazio")
    
    # Agrupa páginas por arquivo de origem.
    
    grouped_pages: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    
    for page in pages:
        if not isinstance(page, Mapping):
            raise TypeError("Cada página precisa ser um objeto compatível com Mapping")
        
        source = str(
            page.get("caminho")
            or page.get("documento")
            or "origem_desconhecida"
        )
        
        grouped_pages[source].append(page)
    
    articles: list[LegalNode] = []
    
    for index, (source, source_pages) in enumerate(sorted(grouped_pages.items()), start=1):
        current_document_id = document_id
        
        #Evita colisoes caso sejam carregados varios pdfs.
        
        if len(grouped_pages)> 1:
            filename = Path(source).stem
            safe_name = re.sub(r"[^A-Za-z0-9]+", "-", filename).strip("-").upper()
            
            current_document_id = (f"{document_id}-{safe_name or index}")
            
        articles.extend(
            _parse_single_document(
                source_pages,
                current_document_id
            )
        )
    return articles

def flatten_legal_nodes(
    articles: Sequence[LegalNode],
) -> list[LegalNode]:
    """Transforma a árvore jurídica em uma lista hierárquica ordenada."""

    flattened = []

    def visit(node: LegalNode) -> None:
        flattened.append(node)

        for child in node.children:
            visit(child)

    for article in articles:
        visit(article)

    return flattened

def flatten_legal_nodes(
    articles: Sequence[LegalNode],
) -> list[LegalNode]:
    """Transforma a árvore jurídica em uma lista hierárquica ordenada."""

    flattened = []

    def visit(node: LegalNode) -> None:
        flattened.append(node)

        for child in node.children:
            visit(child)

    for article in articles:
        visit(article)

    return flattened
