interface PoliticosPaginationProps {
  pagina: number;
  ultimaPagina: number;
  loading: boolean;
  onPageChange: (pagina: number) => void;
}

function gerarPaginas(
  paginaAtual: number,
  totalPaginas: number
): number[] {
  const paginas = new Set<number>([
    1,
    totalPaginas,
    paginaAtual - 1,
    paginaAtual,
    paginaAtual + 1,
  ]);

  return Array.from(paginas)
    .filter((numero) => numero >= 1 && numero <= totalPaginas)
    .sort((a, b) => a - b);
}

export default function PoliticosPagination({
  pagina,
  ultimaPagina,
  loading,
  onPageChange,
}: PoliticosPaginationProps) {
  const paginas = gerarPaginas(pagina, ultimaPagina);

  const botaoClass =
    "flex h-10 min-w-10 items-center justify-center rounded-md px-3 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-40";

  const inativo =
    "bg-[#192536] text-[#d1d5db] hover:bg-[#263b55]";

  const ativo =
    "bg-sky-600 text-white";

  if (ultimaPagina <= 1) {
    return null;
  }

  return (
    <nav
      aria-label="Paginação do catálogo de políticos"
      className="mt-8 flex flex-wrap items-center justify-center gap-1.5 border-t border-[#373a3e] pt-6"
    >
      {/* ANTERIOR */}

      <button
        type="button"
        aria-label="Página anterior"
        disabled={pagina <= 1 || loading}
        onClick={() => onPageChange(pagina - 1)}
        className={`${botaoClass} ${inativo}`}
      >
        ‹
      </button>

      {/* NÚMEROS */}

      {paginas.map((numero, index) => {
        const anterior = paginas[index - 1];

        const mostrarReticencias =
          anterior !== undefined &&
          numero - anterior > 1;

        return (
          <div key={numero} className="flex items-center gap-1.5">

            {mostrarReticencias && (
              <span className="flex h-10 min-w-6 items-center justify-center text-sm text-[#9ca3af]">
                ...
              </span>
            )}

            <button
              type="button"
              aria-label={`Ir para página ${numero}`}
              aria-current={pagina === numero ? "page" : undefined}
              disabled={loading || pagina === numero}
              onClick={() => onPageChange(numero)}
              className={`${botaoClass} ${
                pagina === numero ? ativo : inativo
              }`}
            >
              {numero}
            </button>

          </div>
        );
      })}

      {/* PRÓXIMA */}

      <button
        type="button"
        aria-label="Próxima página"
        disabled={pagina >= ultimaPagina || loading}
        onClick={() => onPageChange(pagina + 1)}
        className={`${botaoClass} ${inativo}`}
      >
        ›
      </button>

    </nav>
  );
}