
import HeaderDashboard from "@/components/HeaderDashboard";
import DeputadoCard from "@/components/Deputados/DeputadoCard";
import DeputadosFilters from "@/components/Deputados/DeputadosFilters";
import DeputadosPagination from "@/components/Deputados/DeputadosPagination";

import { useDeputados } from "@/hooks/useDeputados";

import type { FiltrosDeputados } from "@/types/deputados";


export default function DeputadosPage() {

  const {
    deputados,
    pagina,
    temProxima,
    loading,
    error,
    aplicarFiltros,
    limparFiltros,
    recarregar,
    setPagina,
  } = useDeputados();


  // ========================================================
  // INTERFACE
  // ========================================================

  return (
    <>

      <HeaderDashboard />

      <main className="min-h-screen bg-[#111315] text-white">

        <div className="mx-auto w-[90%] max-w-[1200px] py-8">


          {/* CABEÇALHO */}

          <section className="mb-8">

            <p className="mb-2 text-xs font-semibold uppercase tracking-widest text-sky-400">
              Transparência política
            </p>

            <h1 className="text-3xl font-bold tracking-tight">
              Deputados federais
            </h1>

            <p className="mt-2 max-w-2xl text-sm leading-6 text-[#a1a1aa]">
              Conheça os parlamentares da Câmara dos Deputados,
              consulte seus partidos e acompanhe suas informações
              públicas.
            </p>

          </section>


          {/* FILTROS */}

          <DeputadosFilters
            onApply={(filtros: FiltrosDeputados) => {
              aplicarFiltros(filtros);
            }}
            onClear={limparFiltros}
            disabled={loading}
          />


          {/* RESULTADOS */}

          <section>

            <div className="mb-5 flex items-center justify-between">

              <div>

                <h2 className="text-base font-semibold">
                  Parlamentares
                </h2>

                <p className="mt-1 text-xs text-[#9ca3af]">

                  {loading
                    ? "Consultando a Câmara..."
                    : `${deputados.length} deputados nesta página`}

                </p>

              </div>


              <span className="rounded-lg border border-[#373a3e] bg-[#1a1b1c] px-3 py-2 text-xs text-[#a1a1aa]">
                Página {pagina}
              </span>

            </div>


            {/* ERRO */}

            {error && (

              <div
                role="alert"
                className="mb-5 rounded-xl border border-red-500/30 bg-red-500/10 p-4"
              >

                <p className="text-sm font-semibold text-red-300">
                  Não foi possível carregar os deputados.
                </p>

                <p className="mt-1 text-xs text-red-200">
                  {error}
                </p>

                <button
                  onClick={recarregar}
                  className="mt-3 text-xs font-semibold text-red-200 underline"
                >
                  Tentar novamente
                </button>

              </div>

            )}


            {/* CARREGAMENTO */}

            {loading && (

              <div
                className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3"
                aria-label="Carregando deputados"
              >

                {Array.from({ length: 6 }).map((_, index) => (

                  <div
                    key={index}
                    className="h-36 animate-pulse rounded-2xl border border-[#373a3e] bg-[#1a1b1c]"
                  />

                ))}

              </div>

            )}


            {/* LISTAGEM */}

            {!loading && !error && (

              <>

                {deputados.length > 0 ? (

                  <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">

                    {deputados.map((deputado) => (

                      <DeputadoCard
                        key={deputado.id}
                        deputado={deputado}
                      />

                    ))}

                  </div>

                ) : (

                  <div className="rounded-2xl border border-[#373a3e] bg-[#1a1b1c] p-10 text-center">

                    <h3 className="text-base font-semibold">
                      Nenhum deputado encontrado
                    </h3>

                    <p className="mt-2 text-sm text-[#9ca3af]">
                      Tente alterar os filtros ou pesquisar outro nome.
                    </p>

                  </div>

                )}

              </>

            )}


            {/* PAGINAÇÃO */}

            {!loading && !error && (

              <DeputadosPagination
                pagina={pagina}
                temProxima={temProxima}
                loading={loading}
                onPageChange={setPagina}
              />

            )}

          </section>


          {/* FONTE */}

          <footer className="mt-10 border-t border-[#373a3e] pt-5">

            <p className="text-xs text-[#777f87]">
              Fonte dos dados: Câmara dos Deputados.
              Informações consultadas diretamente na API de Dados Abertos.
            </p>

            <a
              href="https://dadosabertos.camara.leg.br/"
              target="_blank"
              rel="noopener noreferrer"
              className="mt-2 inline-block text-xs text-sky-400 hover:text-sky-300"
            >
              Consultar portal oficial ↗
            </a>

          </footer>

        </div>

      </main>

    </>
  );
}
