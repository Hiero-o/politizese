import HeaderDashboard from "@/components/HeaderDashboard";

import PoliticoCard from "@/components/Politicos/PoliticoCard";

import PoliticosFilters from "@/components/Politicos/PoliticosFilters";

import PoliticosPagination from "@/components/Politicos/PoliticosPagination";

import { usePoliticos } from "@/hooks/usePoliticos";

import type { FonteStatus } from "@/types/politicos";


const NOMES_FONTES: Record<string, string> = {
  camara: "Câmara dos Deputados",
  senado: "Senado Federal",
  tse: "TSE — Eleições 2026",
  tse_municipal: "TSE — Eleições municipais 2024",
  planalto: "Presidência da República",
};

const STATUS_FONTES: Record<string, string> = {
  atualizada: "Atualizada",
  cache_valido: "Cache válido",
  cache_desatualizado: "Cache desatualizado",
  indisponivel: "Indisponível",
  cadastro_local: "Cadastro local",
};


function formatarData(data: string | null) {
  if (!data) {
    return null;
  }

  return new Date(data).toLocaleString("pt-BR");
}


function FonteStatusCard({
  fonte,
}: {
  fonte: FonteStatus;
}) {
  const statusClass =
    fonte.status === "atualizada" ||
    fonte.status === "cache_valido"
      ? "text-emerald-400"
      : fonte.status === "cache_desatualizado"
        ? "text-amber-400"
        : fonte.status === "indisponivel"
          ? "text-red-400"
          : "text-sky-400";

  return (
    <div className="rounded-xl border border-[#373a3e] bg-[#1a1b1c] p-3">

      <h3 className="text-xs font-semibold text-white">
        {NOMES_FONTES[fonte.fonte] ?? fonte.fonte}
      </h3>

      <p className={`mt-2 text-[11px] font-semibold ${statusClass}`}>
        {STATUS_FONTES[fonte.status] ?? fonte.status}
      </p>

      <p className="mt-1 text-[10px] text-[#808991]">
        {fonte.registros.toLocaleString("pt-BR")} registros
      </p>

      {fonte.atualizado_em && (
        <p className="mt-1 text-[10px] text-[#808991]">
          Atualização: {formatarData(fonte.atualizado_em)}
        </p>
      )}

      {fonte.mensagem && (
        <p className="mt-2 text-[10px] leading-relaxed text-[#9ca3af]">
          {fonte.mensagem}
        </p>
      )}

    </div>
  );
}


export default function PoliticosPage() {
  const {
    politicos,
    pagina,
    total,
    ultimaPagina,
    fontes,
    loading,
    error,
    setPagina,
    aplicarFiltros,
    limparFiltros,
    recarregar,
  } = usePoliticos();

  return (
    <main className="min-h-screen bg-[#111213] text-white">

      <HeaderDashboard />

      <section className="mx-auto w-[90%] max-w-[1200px] py-10">

        {/* ================================================= */}
        {/* CABEÇALHO */}
        {/* ================================================= */}

        <div className="mb-8">

          <h1 className="text-2xl font-semibold">
            Políticos
          </h1>

          <p className="mt-2 text-sm text-[#a1a1aa]">
            Explore representantes políticos, conheça seus mandatos
            e consulte informações de fontes oficiais.
          </p>

          <div className="mt-5 flex flex-wrap gap-2">

            <span className="rounded-lg bg-[#1a1b1c] px-3 py-2 text-xs text-[#d1d5db]">
              {total.toLocaleString("pt-BR")} registros encontrados
            </span>

            <span className="rounded-lg bg-[#1a1b1c] px-3 py-2 text-xs text-[#d1d5db]">
              {politicos.length} nesta página
            </span>

          </div>

        </div>


        {/* ================================================= */}
        {/* FILTROS */}
        {/* ================================================= */}

        <PoliticosFilters
          onApply={aplicarFiltros}
          onClear={limparFiltros}
          disabled={loading}
        />


        {/* ================================================= */}
        {/* ERRO */}
        {/* ================================================= */}

        {error && (
          <div className="mb-6 rounded-xl border border-red-500/30 bg-red-500/10 p-5">

            <h2 className="text-sm font-semibold text-red-300">
              Não foi possível carregar o catálogo
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


        {/* ================================================= */}
        {/* CARREGAMENTO */}
        {/* ================================================= */}

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


        {/* ================================================= */}
        {/* RESULTADOS */}
        {/* ================================================= */}

        {!loading && !error && (
          <>

            {politicos.length > 0 ? (
              <>

                <div className="mb-4 flex items-center justify-between">

                  <p className="text-xs text-[#9ca3af]">
                    Exibindo resultados da página {pagina}
                  </p>

                  <p className="text-xs text-[#808991]">
                    Total: {total.toLocaleString("pt-BR")}
                  </p>

                </div>


                {/* CARDS */}

                <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">

                  {politicos.map((politico) => (
                    <PoliticoCard
                      key={politico.id}
                      politico={politico}
                    />
                  ))}

                </div>


                {/* PAGINAÇÃO */}

                <PoliticosPagination
                  pagina={pagina}
                  ultimaPagina={ultimaPagina}
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
                  Tente alterar os filtros ou pesquisar por outro nome.
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


        {/* ================================================= */}
        {/* DISPONIBILIDADE DAS FONTES */}
        {/* ================================================= */}

        {!loading && fontes.length > 0 && (
          <section className="mt-12 border-t border-[#373a3e] pt-6">

            <h2 className="mb-2 text-base font-semibold text-white">
              Origem dos dados
            </h2>

            <p className="mb-5 text-xs text-[#9ca3af]">
              Consulte a origem e a situação de atualização das fontes
              utilizadas pelo Politize-se.
            </p>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">

              {fontes.map((fonte) => (
                <FonteStatusCard
                  key={fonte.fonte}
                  fonte={fonte}
                />
              ))}

            </div>

          </section>
        )}

      </section>
    </main>
  );
}