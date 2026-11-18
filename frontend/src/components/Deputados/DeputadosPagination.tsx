
interface DeputadosPaginationProps {
  pagina: number;
  temProxima: boolean;
  loading: boolean;
  onPageChange: (pagina: number) => void;
}


export default function DeputadosPagination({
  pagina,
  temProxima,
  loading,
  onPageChange,
}: DeputadosPaginationProps) {

  return (
    <div className="mt-8 flex items-center justify-between border-t border-[#373a3e] pt-5">

      <button
        disabled={pagina <= 1 || loading}
        onClick={() => onPageChange(pagina - 1)}
        className="rounded-lg border border-[#41464b] px-4 py-2 text-xs font-medium text-[#d1d5db] transition hover:bg-[#303438] disabled:cursor-not-allowed disabled:opacity-30"
      >
        ← Anterior
      </button>


      <span className="text-xs text-[#9ca3af]">
        Página {pagina}
      </span>


      <button
        disabled={!temProxima || loading}
        onClick={() => onPageChange(pagina + 1)}
        className="rounded-lg border border-[#41464b] px-4 py-2 text-xs font-medium text-[#d1d5db] transition hover:bg-[#303438] disabled:cursor-not-allowed disabled:opacity-30"
      >
        Próxima →
      </button>

    </div>
  );
}
