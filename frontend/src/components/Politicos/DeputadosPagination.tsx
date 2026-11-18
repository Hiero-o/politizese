
interface DeputadosPaginationProps {
  pagina: number;
  ultimaPagina: number | null;
  temProxima: boolean;
  loading: boolean;
  onPageChange: (pagina: number) => void;
}

function gerarPaginas(paginaAtual: number, totalPaginas: number) {
  if (totalPaginas <= 7) {
    return Array.from(
      { length: totalPaginas },
      (_, index) => index + 1
    );
  }

  const paginas = new Set<number>([1, totalPaginas]);

  if (paginaAtual <= 2) {
    paginas.add(2);
    paginas.add(3);
  } else if (paginaAtual >= totalPaginas - 1) {
    paginas.add(totalPaginas - 2);
    paginas.add(totalPaginas - 1);
  } else {
    paginas.add(paginaAtual - 1);
    paginas.add(paginaAtual);
    paginas.add(paginaAtual + 1);
  }

  return Array.from(paginas).sort((a, b) => a - b);
}


export default function DeputadosPagination({
  pagina,
  ultimaPagina,
  temProxima,
  loading,
  onPageChange,
}: DeputadosPaginationProps) {
  const total = Math.max(
    pagina,
    ultimaPagina ?? pagina + (temProxima ? 1 : 0)
  );

  const paginas = gerarPaginas(pagina, total);

  const estiloBotao = "flex h-10 min-w-10 items-center justify-center rounded-md px-3 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-40";

  const estiloInativo = "bg-[#192536] text-[#d1d5db] hover:bg-[#263b55]";

  const estiloAtivo = "bg-sky-600 text-white";

  return (

    <nav
      aria-label="Paginação de deputados"
      className="mt-8 flex flex-wrap items-center justify-center gap-1.5 border-t border-[#373a3e] pt-6"
    >

      {/* Anterior */}



      <button
        type="button"
        aria-label="Página anterior"
        disabled={pagina <= 1 || loading}
        onClick={() => onPageChange(pagina - 1)}
        className={`${estiloBotao} ${estiloInativo}`}
      >
        ‹
      </button>


      {/* Numero das Páginas */}
      {paginas.map((numero, index) => {
        const paginaAnterior = paginas[index - 1];

        const mostrarReticencias =
          paginaAnterior == undefined &&
          numero - paginaAnterior > 1;

        return (
          <div key={numero} className="flex items-center gap-1.5">
            {mostrarReticencias && (
              <span className="flex h-10 min-w-6 items-center justify-center text-sm text-[#9ca3af]">
                ...
              </span>

            )}
          <button
            type="button"
            aria-label={`IR para página ${numero}`}
            aria-current={pagina === numero ? "page" : undefined}
            disabled={loading || pagina === numero}
            onClick={() => onPageChange(numero)}
            className={`${estiloBotao} ${
              pagina === numero
              ? estiloAtivo
              : estiloInativo
              }`}
            >
              {numero}
            </button>
          </div>
        );

      })}

      {/* proxima */}

      <button
        type="button"
        aria-label="Próxima página"
        disabled={!temProxima || loading}
        onClick={() => onPageChange(pagina + 1)}
        className={`${estiloBotao} ${estiloInativo}`}
      >
        ›
      </button>
    </nav >
  );
}
