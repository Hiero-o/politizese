import { useState } from "react";

import type {
  Politico,
} from "@/types/politicos";

interface PoliticoCardProps {
  politico: Politico;
}

const FASES: Record<string, string> = {
  em_exercicio: "Em exercício",
  eleito_futuro: "Eleito para próximo mandato",
  mandato_em_andamento: "Mandato em andamento · exercício não verificado",
};

export default function PoliticoCard({
  politico,
}: PoliticoCardProps) {
  const [imageError, setImageError] = useState(false);

  const iniciais = politico.nome
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((parte) => parte[0])
    .join("")
    .toUpperCase();

  const localizacao = [
    politico.municipio,
    politico.uf,
  ]
    .filter(Boolean)
    .join(" - ");

  return (
    <article className="flex min-w-0 gap-4 rounded-2xl border border-[#373a3e] bg-[#1a1b1c] p-4 transition hover:border-[#59636b] hover:bg-[#202326]">

      {/* FOTO OU INICIAIS */}

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

      {/* INFORMAÇÕES */}

      <div className="min-w-0 flex-1">

        <h3 className="truncate text-sm font-semibold text-white">
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

        {politico.numero_candidato && (
          <p className="mt-1 text-[10px] text-[#808991]">
            Número eleitoral: {politico.numero_candidato}
          </p>
        )}

        {politico.situacao_eleitoral && (
          <p className="mt-1 text-[10px] text-[#808991]">
            Resultado eleitoral: {politico.situacao_eleitoral}
          </p>
        )}

        {politico.fonte_url && (
          <a
            href={politico.fonte_url}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-3 inline-block text-[11px] font-medium text-sky-400 hover:text-sky-300"
          >
            Consultar fonte oficial ↗
          </a>
        )}

      </div>
    </article>
  );
}