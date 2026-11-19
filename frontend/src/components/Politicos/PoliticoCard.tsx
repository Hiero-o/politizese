import { useState } from "react";
import Link from "next/link";

import type { Politico } from "@/types/politicos";

interface PoliticoCardProps {
  politico: Politico;
}

const FASES: Record<string, string> = {
  em_exercicio: "Em exercício",
  eleito_futuro: "Eleito para próximo mandato",
  mandato_em_andamento: "Mandato em andamento · exercício não verificado",
};

export default function PoliticoCard({ politico }: PoliticoCardProps) {
  const [imageError, setImageError] = useState(false);

  const iniciais = politico.nome
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((parte) => parte[0])
    .join("")
    .toUpperCase();

  const localizacao = [politico.municipio, politico.uf]
    .filter(Boolean)
    .join(" - ");

  return (
    <Link
      href={`/dashboard/politicos/${encodeURIComponent(politico.id)}`}
      aria-label={`Ver perfil de ${politico.nome}`}
      className="group block h-full rounded-2xl outline-none focus-visible:ring-2 focus-visible:ring-sky-400 focus-visible:ring-offset-2 focus-visible:ring-offset-[#111213]"
    >
      <article className="flex h-full min-w-0 gap-4 rounded-2xl border border-[#373a3e] bg-[#1a1b1c] p-4 transition group-hover:border-[#59636b] group-hover:bg-[#202326]">
        <div className="flex h-[76px] w-[76px] shrink-0 items-center justify-center overflow-hidden rounded-xl border border-[#41464b] bg-[#303438]">
          {politico.foto_url && !imageError ? (
            <img
              src={politico.foto_url}
              alt={`Foto de ${politico.nome}`}
              loading="lazy"
              className="h-full w-full object-cover"
              onError={() => setImageError(true)}
            />
          ) : (
            <span className="text-xl font-bold text-[#9ca3af]">
              {iniciais}
            </span>
          )}
        </div>

        <div className="min-w-0 flex-1">
          <h3 className="truncate text-sm font-semibold text-white group-hover:text-sky-300">
            {politico.nome}
          </h3>

          <p className="mt-1 text-xs text-[#9ca3af]">
            {politico.cargo}
            {localizacao && ` · ${localizacao}`}
          </p>

          <div className="mt-3 flex flex-wrap gap-2">
            {politico.partido && (
              <span className="rounded-md bg-sky-500/10 px-2 py-1 text-[11px] font-semibold text-sky-300">
                {politico.partido}
              </span>
            )}

            {politico.fase_mandato && (
              <span className="rounded-md bg-[#303438] px-2 py-1 text-[11px] font-medium text-[#d1d5db]">
                {FASES[politico.fase_mandato] ?? politico.fase_mandato}
              </span>
            )}
          </div>

          {politico.mandato && (
            <p className="mt-2 text-[11px] text-[#9ca3af]">
              Mandato: {politico.mandato}
            </p>
          )}

          <p className="mt-3 text-[11px] font-medium text-sky-400 transition group-hover:text-sky-300">
            Ver perfil <span aria-hidden="true">→</span>
          </p>
        </div>
      </article>
    </Link>
  );
}
