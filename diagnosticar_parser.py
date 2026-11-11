from services.rag.document_loader import load_documents

from services.rag.parsers.legal_parser import (
    ARTICLE_PATTERN,
    _clean_line,
    _is_noise_line,
)

from services.rag.parsers.legal_parser import (
    _parse_single_document,
    parse_constitution_pages,
)


def main():
    pages = load_documents()

    print("=" * 70)
    print("DIAGNÓSTICO DO RECONHECIMENTO DE ARTIGOS")
    print("=" * 70)

    print("\nExpressão regular utilizada:")
    print(repr(ARTICLE_PATTERN.pattern))

    print("\nTeste com texto artificial:")

    examples = [
        "Art. 1º A República Federativa do Brasil...",
        "Art. 5º Todos são iguais perante a lei...",
        "Art. 5º-A Exemplo de artigo com letra.",
        "Art. 22. Compete privativamente à União...",
        "Art. 6º São direitos sociais...",
    ]

    for example in examples:
        match = ARTICLE_PATTERN.match(example)

        print(f"\nTexto: {example}")
        print(f"Reconhecido: {bool(match)}")

        if match:
            print(f"Número: {match.group('number')}")
            print(f"Conteúdo: {match.group('body')[:100]}")

    print("\n" + "=" * 70)
    print("ANÁLISE DO TEXTO EXTRAÍDO DO PDF")
    print("=" * 70)

    candidates = []
    recognized = []
    discarded = []

    for page in pages:
        for raw_line in page["texto"].splitlines():
            line = _clean_line(raw_line)

            if "art." not in line.casefold():
                continue

            match = ARTICLE_PATTERN.match(line)
            noise = _is_noise_line(line)

            if match:
                recognized.append((page["pagina"], line))

            if not noise and not match:
                candidates.append((page["pagina"], line))

            if noise:
                discarded.append((page["pagina"], line))

    print(f"\nLinhas contendo 'Art.': {len(recognized) + len(candidates) + len(discarded)}")
    print(f"Artigos reconhecidos: {len(recognized)}")
    print(f"Candidatos não reconhecidos: {len(candidates)}")
    print(f"Linhas descartadas: {len(discarded)}")

    print("\n--- PRIMEIRAS LINHAS RECONHECIDAS ---")

    for page, line in recognized[:15]:
        print(f"[Página {page}] {line[:180]!r}")

    print("\n--- PRIMEIROS CANDIDATOS NÃO RECONHECIDOS ---")

    for page, line in candidates[:30]:
        print(f"[Página {page}] {line[:180]!r}")

    print("\n--- PRIMEIRAS LINHAS DESCARTADAS ---")

    for page, line in discarded[:15]:
        print(f"[Página {page}] {line[:180]!r}")

    print("\n" + "=" * 70)
    print("DIAGNÓSTICO FINAL — FILTRAGEM DE ARTIGOS")
    print("=" * 70)

    valid_articles = []
    rejected_articles = []

    for page in pages:
        for raw_line in page["texto"].splitlines():
            line = _clean_line(raw_line)

            match = ARTICLE_PATTERN.match(line)

            if not match:
                continue

            if _is_noise_line(line):
                rejected_articles.append(
                    (page["pagina"], line)
                )
            else:
                valid_articles.append(
                    (page["pagina"], line)
                )

    print(f"\nReconhecidos pela regex: {len(valid_articles) + len(rejected_articles)}")
    print(f"Aprovados pela filtragem: {len(valid_articles)}")
    print(f"Rejeitados como ruído: {len(rejected_articles)}")

    print("\n--- PRIMEIROS ARTIGOS APROVADOS ---")

    for page, line in valid_articles[:15]:
        print(f"[Página {page}] {line[:150]}")

    print("\n--- PRIMEIROS ARTIGOS REJEITADOS ---")

    for page, line in rejected_articles[:15]:
        print(f"[Página {page}] {line[:150]}")
    print("\n" + "=" * 70)
    print("DIAGNÓSTICO DO PROCESSAMENTO INTERNO")
    print("=" * 70)

    print(f"Total de páginas: {len(pages)}")
    print(f"Primeira página: {pages[0].keys()}")

    direct_result = _parse_single_document(
        pages,
        document_id="CF1988",
    )

    print(
        "\nArtigos retornados por _parse_single_document:",
        len(direct_result),
    )

    wrapped_result = parse_constitution_pages(pages)

    print(
        "Artigos retornados por parse_constitution_pages:",
        len(wrapped_result),
    )

    if direct_result:
        print("\nPrimeiros artigos encontrados:")

        for article in direct_result[:10]:
            print(
                article.node_id,
                article.legal_unit,
                article.text[:100],
            )
            

if __name__ == "__main__":
    main()