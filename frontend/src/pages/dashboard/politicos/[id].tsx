import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import Link from "next/link";
import { useRouter } from "next/router";

import HeaderDashboard from "@/components/HeaderDashboard";
import { obterPoliticoPorId } from "@/services/politicosService";
import type { Politico } from "@/types/politicos";

const FASES: Record<string, string> = {
  em_exercicio: "Em exercício",
  eleito_futuro: "Eleito para o próximo mandato",
  mandato_em_andamento: "Mandato em andamento · exercício não verificado",
};

const NOMES_FONTES: Record<string, string> = {
  camara: "Câmara dos Deputados",
  senado: "Senado Federal",
  tse: "Tribunal Superior Eleitoral",
  planalto: "Cadastro local da Presidência",
};

function Campo({
  titulo,
  valor,
}: {
  titulo: string;
  valor: string | number | null | undefined;
}) {
  if (valor === null || valor === undefined || valor === "") {
    return null;
  }

  return (
    <div className="border-b border-[#303438] py-3 last:border-0">
      <dt className="text-[11px] font-medium uppercase tracking-wide text-[#808991]">
        {titulo}
      </dt>
      <dd className="mt-1 break-words text-sm text-[#e5e7eb]">
        {valor}
      </dd>
    </div>
  );
}

function CartaoInformacoes({
  titulo,
  children,
}: {
  titulo: string;
  children: ReactNode;
}) {
  return (
    <section className="rounded-2xl border border-[#373a3e] bg-[#1a1b1c] p-5">
      <h2 className="mb-2 text-sm font-semibold text-white">{titulo}</h2>
      <dl>{children}</dl>
    </section>
  );
}

export default function PerfilPoliticoPage() {
  const router = useRouter();
  const [politico, setPolitico] = useState<Politico | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [imageError, setImageError] = useState(false);

  const id = router.query.id;

  useEffect(() => {
    // Aguarda o Next.js carregar os parâmetros da URL
    if (!router.isReady) return;

    // Garante que o ID seja uma string válida
    if (typeof id !== "string" || !id.trim()) {
      setLoading(false);
      setError("Identificador do político inválido.");
      return;
    }

    const politicoId = id;
    const controller = new AbortController();

    async function carregarPolitico() {
      try {
        setLoading(true);
        setError(null);

        const resultado = await obterPoliticoPorId(
          politicoId,
          controller.signal
        );

        setPolitico(resultado);
      } catch (erro) {
        if (erro instanceof Error && erro.name !== "AbortError") {
          setError(erro.message);
        }
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      }
    }

    void carregarPolitico();

    return () => controller.abort();
  }, [router.isReady, id]);

  const iniciais = politico?.nome
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((parte) => parte[0])
    .join("")
    .toUpperCase();

  return (
    <main className="min-h-screen bg-[#111213] text-white">
      <HeaderDashboard />

      <section className="mx-auto w-[90%] max-w-[1000px] py-8 md:py-10">
        <Link
          href="/dashboard/politicos"
          className="mb-6 inline-flex items-center gap-2 text-sm text-sky-400 transition hover:text-sky-300"
        >
          <span aria-hidden="true">←</span> Voltar para políticos
        </Link>

        {loading && (
          <div className="animate-pulse rounded-2xl border border-[#373a3e] bg-[#1a1b1c] p-6">
            <div className="h-6 w-2/5 rounded bg-[#303438]" />
            <div className="mt-4 h-4 w-1/3 rounded bg-[#303438]" />
            <div className="mt-8 h-24 rounded bg-[#303438]" />
          </div>
        )}

        {!loading && error && (
          <div className="rounded-2xl border border-red-500/30 bg-red-500/10 p-6">
            <h1 className="text-lg font-semibold text-red-200">
              Não foi possível carregar este perfil
            </h1>
            <p className="mt-2 text-sm text-red-200/90">{error}</p>
            <Link
              href="/dashboard/politicos"
              className="mt-5 inline-block rounded-lg bg-[#303438] px-4 py-2 text-xs font-semibold text-white transition hover:bg-[#3b4146]"
            >
              Voltar ao catálogo
            </Link>
          </div>
        )}

        {!loading && politico && (
          <>
            <header className="flex flex-col gap-5 rounded-2xl border border-[#373a3e] bg-[#1a1b1c] p-5 sm:flex-row sm:items-center sm:p-7">
              <div className="flex h-28 w-28 shrink-0 items-center justify-center overflow-hidden rounded-2xl border border-[#41464b] bg-[#303438] sm:h-32 sm:w-32">
                {politico.foto_url && !imageError ? (
                  <img
                    src={politico.foto_url}
                    alt={`Foto de ${politico.nome}`}
                    className="h-full w-full object-cover"
                    onError={() => setImageError(true)}
                  />
                ) : (
                  <span className="text-3xl font-bold text-[#9ca3af]">
                    {iniciais}
                  </span>
                )}
              </div>

              <div className="min-w-0">
                <p className="text-xs font-semibold uppercase tracking-wide text-sky-400">
                  {politico.cargo}
                </p>
                <h1 className="mt-2 break-words text-2xl font-bold text-white md:text-3xl">
                  {politico.nome}
                </h1>
                <p className="mt-2 text-sm text-[#9ca3af]">
                  {[politico.municipio, politico.uf].filter(Boolean).join(" · ") || "Representação nacional"}
                </p>

                <div className="mt-4 flex flex-wrap gap-2">
                  {politico.partido && (
                    <span className="rounded-md bg-sky-500/10 px-3 py-1.5 text-xs font-semibold text-sky-300">
                      {politico.partido}
                    </span>
                  )}
                  <span className="rounded-md bg-[#303438] px-3 py-1.5 text-xs font-medium text-[#d1d5db]">
                    {FASES[politico.fase_mandato] ?? politico.fase_mandato}
                  </span>
                </div>
              </div>
            </header>

            <div className="mt-5 grid grid-cols-1 gap-5 md:grid-cols-2">
              <CartaoInformacoes titulo="Mandato e representação">
                <Campo titulo="Cargo" valor={politico.cargo} />
                <Campo titulo="Partido" valor={politico.partido} />
                <Campo titulo="Estado" valor={politico.uf} />
                <Campo titulo="Município" valor={politico.municipio} />
                <Campo titulo="Mandato" valor={politico.mandato} />
                <Campo titulo="Situação" valor={politico.situacao} />
                <Campo titulo="Titularidade" valor={politico.titularidade} />
                <Campo titulo="Fase do mandato" valor={FASES[politico.fase_mandato] ?? politico.fase_mandato} />
              </CartaoInformacoes>

              <div className="space-y-5">
                <CartaoInformacoes titulo="Informações eleitorais">
                  <Campo titulo="Número de candidatura" valor={politico.numero_candidato} />
                  <Campo titulo="Ano da eleição" valor={politico.ano_eleicao} />
                  <Campo titulo="Turno" valor={politico.turno_eleitoral} />
                  <Campo titulo="Resultado eleitoral" valor={politico.situacao_eleitoral} />
                </CartaoInformacoes>

                <CartaoInformacoes titulo="Contato e origem dos dados">
                  <Campo titulo="E-mail" valor={politico.email} />
                  <Campo titulo="Telefone" valor={politico.telefone} />
                  <Campo titulo="Fonte dos dados" valor={NOMES_FONTES[politico.fonte] ?? politico.fonte} />
                  <Campo titulo="Identificador de origem" valor={politico.id_origem} />
                </CartaoInformacoes>
              </div>
            </div>

            <p className="mt-6 text-xs leading-relaxed text-[#808991]">
              As informações exibidas dependem dos dados disponibilizados pela fonte de origem. Campos sem informação disponível não são exibidos.
            </p>
          </>
        )}
      </section>
    </main>
  );
}
