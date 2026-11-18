import HeaderDashboard from "@/components/HeaderDashboard";

import DeputadoCard from "@/components/Politicos/DeputadoCard";
import DeputadosFilters from "@/components/Politicos/DeputadosFilters";
import DeputadosPagination from "@/components/Politicos/DeputadosPagination";

import { useDeputados } from "@/hooks/useDeputados";

export default function PoliticosPage() {
  const {
    deputados,
    pagina,
    ultimaPagina,
    temProxima,
    loading,
    error,
    setPagina,
    aplicarFiltros,
    limparFiltros,
    recarregar,
  } = useDeputados();

  return (
    <main className="min-h-screen bg-[#111213] text-white">
      <HeaderDashboard />

      <section className="mx-auto w-[90%] max-w-[1200px] py-10">
        {/* CABEÇALHO */}
        <div className="mb-8">
          <h1 className="text-2xl font-semibold">
            Políticos
          </h1>

          <p className="mt-2 text-sm text-[#a1a1aa]">
            Explore representantes políticos e consulte informações
            sobre seus mandatos e atividades públicas.
          </p>

          <p className="mt-2 text-xs text-[#808991]">
            Catálogo inicial: deputados federais da Câmara dos Deputados.
          </p>
        </div>

        {/* FILTROS */}
        <DeputadosFilters
          onApply={aplicarFiltros}
          onClear={limparFiltros}
          disabled={loading}
        />

        {/* ERRO */}
        {error && (
          <div className="mb-6 rounded-xl border border-red-500/30 bg-red-500/10 p-5">
            <h2 className="text-sm font-semibold text-red-300">
              Não foi possível carregar os políticos
            </h2>

            <p className="mt-2 text-xs text-red-200">
              {error}
            </p>

            <button
              type="button"
              onClick={recarregar}
              className="mt-4 rounded-lg bg-red-500/20 px-4 py-2 text-xs font-semibold text-red-200 transition hover:bg-red-500/30"
            >
              Tentar novamente
            </button>
          </div>
        )}

        {/* CARREGAMENTO */}
        {loading && (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
            {Array.from({ length: 6 }).map((_, index) => (
              <div
                key={index}
                className="flex animate-pulse items-center gap-4 rounded-2xl border border-[#373a3e] bg-[#1a1b1c] p-4"
              >
                <div className="h-[76px] w-[76px] shrink-0 rounded-xl bg-[#303438]" />

                <div className="flex-1 space-y-3">
                  <div className="h-4 w-3/4 rounded bg-[#303438]" />
                  <div className="h-3 w-1/2 rounded bg-[#303438]" />
                  <div className="h-3 w-1/3 rounded bg-[#303438]" />
                </div>
              </div>
            ))}
          </div>
        )}

        {/* RESULTADOS */}
        {!loading && !error && (
          <>
            {deputados.length > 0 ? (
              <>
                <div className="mb-4 flex items-center justify-between">
                  <p className="text-xs text-[#9ca3af]">
                    {deputados.length} resultado(s) nesta página
                  </p>

                  <span className="text-xs text-[#808991]">
                    Página {pagina}
                  </span>
                </div>

                <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
                  {deputados.map((deputado) => (
                    <DeputadoCard
                      key={deputado.id}
                      deputado={deputado}
                    />
                  ))}
                </div>

                <DeputadosPagination
                  pagina={pagina}
                  ultimaPagina={ultimaPagina}
                  temProxima={temProxima}
                  loading={loading}
                  onPageChange={setPagina}
                />
              </>
            ) : (
              <div className="rounded-2xl border border-[#373a3e] bg-[#1a1b1c] px-6 py-12 text-center">
                <h2 className="text-base font-semibold text-white">
                  Nenhum político encontrado
                </h2>

                <p className="mt-2 text-sm text-[#9ca3af]">
                  Tente alterar os filtros de busca ou pesquisar por
                  outro nome.
                </p>

                <button
                  type="button"
                  onClick={limparFiltros}
                  className="mt-5 rounded-lg bg-sky-600 px-4 py-2 text-xs font-semibold text-white transition hover:bg-sky-500"
                >
                  Limpar filtros
                </button>
              </div>
            )}
          </>
        )}
      </section>
    </main>
  );
}