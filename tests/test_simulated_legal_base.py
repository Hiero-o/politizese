
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.indexar_base_simulada import (
    DOCUMENTS_DIR,
    WORD_PATTERN,
    parse_frontmatter,
    prepare_base,
)


def test_simulated_markdown_documents_meet_word_count_and_metadata_requirements():
    """
    Verifica se todos os documentos possuem:
    - Pelo menos 100 palavras;
    - Metadados obrigatórios;
    - Arquivos Markdown separados.
    """

    documents = sorted(DOCUMENTS_DIR.glob("*.md"))

    assert len(documents) >= 2

    for path in documents:
        metadata, body = parse_frontmatter(path)

        assert metadata.get("titulo"), f"Título ausente em {path.name}"
        assert metadata.get("data_publicacao"), f"Data ausente em {path.name}"
        assert metadata.get("tema"), f"Tema ausente em {path.name}"
        assert metadata.get("tipo_documento"), (
            f"Tipo de documento ausente em {path.name}"
        )

        word_count = len(WORD_PATTERN.findall(body))

        assert word_count >= 100, (
            f"{path.name} possui apenas {word_count} palavras. "
            "O mínimo exigido é 100."
        )


def test_parser_identifies_normative_units_in_all_documents():
    """
    Verifica se o parser jurídico consegue identificar
    artigos e unidades normativas dos documentos.
    """

    articles, legal_units, metadata = prepare_base()

    assert len(metadata) >= 2
    assert len(articles) >= 10
    assert len(legal_units) >= 10


def test_original_law_contains_participatory_budget_rules():
    """
    Verifica o conteúdo da Lei Municipal nº 2.140/2026,
    conforme o documento enviado pelo grupo.
    """

    path = DOCUMENTS_DIR / "lei_organica_santa_marcelina.md"

    assert path.exists()

    text = path.read_text(encoding="utf-8")

    assert "Lei Municipal nº 2.140/2026" in text
    metadata, _ = parse_frontmatter(path)
    assert metadata.get("data_publicacao") == "2026-02-30"
    assert "Programa Municipal de Orçamento Participativo" in text

    # Regras de participação
    assert "16 (dezesseis) anos" in text
    assert "Art. 3º" in text
    assert "Art. 4º" in text

    # Requisitos das propostas
    assert "20 (vinte) manifestações de apoio" in text

    # Condições específicas presentes no documento original
    assert "primeiro dia de Lua cheia" in text
    assert "18h às 23:55h" in text


def test_later_law_contains_amended_participation_conditions():
    """
    Verifica a Lei Municipal nº 2.196/2026,
    que modifica as regras de participação da lei original.
    """

    path = DOCUMENTS_DIR / "lei_organica_santa_marcelina_alteracao.md"

    assert path.exists()

    text = path.read_text(encoding="utf-8")

    assert "Lei Municipal nº 2.196/2026" in text
    metadata, _ = parse_frontmatter(path)
    assert metadata.get("data_publicacao") == "2026-10-03"

    # Alteração do público participante
    assert "16 (dezesseis) anos" in text
    assert "18 (dezoito) anos" in text

    # Restrição do direito de voto
    assert "vedado o registro de seus votos" in text

    # Vigência da alteração
    assert "entra em vigor na data de sua publicação" in text

    # Preservação das demais disposições
    assert "Permanecem inalterados os demais dispositivos" in text


def test_original_and_amending_laws_create_age_requirement_contrast():
    """
    Confirma que os documentos apresentam informações
    diferentes sobre o direito de voto, exigindo recuperação
    e interpretação conjunta.
    """

    original_path = (
        DOCUMENTS_DIR / "lei_organica_santa_marcelina.md"
    )

    amended_path = (
        DOCUMENTS_DIR / "lei_organica_santa_marcelina_alteracao.md"
    )

    original = original_path.read_text(encoding="utf-8")
    amended = amended_path.read_text(encoding="utf-8")

    assert "votar nas prioridades de investimento" in original
    assert "16 (dezesseis) anos" in original

    assert "18 (dezoito) anos" in amended
    assert "vedado o registro de seus votos" in amended

