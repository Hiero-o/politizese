import { useState } from "react";
import type { FormEvent } from "react";

import type {
  FiltrosPoliticos,
} from "@/types/politicos";

interface PoliticosFiltersProps {
  onApply: (filtros: FiltrosPoliticos) => void;
  onClear: () => void;
  disabled?: boolean;
}

const ESTADOS = [
  "AC", "AL", "AM", "AP", "BA", "CE",
  "DF", "ES", "GO", "MA", "MG", "MS",
  "MT", "PA", "PB", "PE", "PI", "PR",
  "RJ", "RN", "RO", "RR", "RS", "SC",
  "SE", "SP", "TO",
];

const CARGOS = [
  { value: "presidente", label: "Presidente" },
  { value: "vice_presidente", label: "Vice-presidente" },
  { value: "governador", label: "Governador" },
  { value: "senador", label: "Senador" },
  { value: "deputado_federal", label: "Deputado federal" },
  { value: "deputado_estadual", label: "Deputado estadual" },
  { value: "deputado_distrital", label: "Deputado distrital" },
  { value: "prefeito", label: "Prefeito" },
  { value: "vereador", label: "Vereador" },
];

export default function PoliticosFilters({
  onApply,
  onClear,
  disabled = false,
}: PoliticosFiltersProps) {
  const [nome, setNome] = useState("");
  const [cargo, setCargo] = useState("");
  const [uf, setUf] = useState("");
  const [municipio, setMunicipio] = useState("");
  const [partido, setPartido] = useState("");
  const [faseMandato, setFaseMandato] = useState("");

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    onApply({
      nome: nome.trim(),
      cargo,
      uf,
      municipio: municipio.trim(),
      partido: partido.trim().toUpperCase(),
      fase_mandato: faseMandato,
    });
  }

  function handleClear() {
    setNome("");
    setCargo("");
    setUf("");
    setMunicipio("");
    setPartido("");
    setFaseMandato("");

    onClear();
  }

  const inputClass =
    "h-11 w-full rounded-lg border border-[#41464b] bg-[#242729] px-3 text-sm text-white outline-none transition focus:border-sky-500 disabled:opacity-50";

  const labelClass =
    "mb-2 block text-xs font-medium text-[#cbd5e1]";

  return (
    <section className="mb-8 rounded-2xl border border-[#373a3e] bg-[#1a1b1c] p-5">

      <div className="mb-5">
        <h2 className="text-base font-semibold text-white">
          Encontrar político
        </h2>

        <p className="mt-1 text-xs text-[#9ca3af]">
          Pesquise por nome, cargo, partido ou localização.
        </p>
      </div>

      <form
        onSubmit={handleSubmit}
        className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3"
      >

        {/* NOME */}

        <div>
          <label htmlFor="politico-nome" className={labelClass}>
            Nome
          </label>

          <input
            id="politico-nome"
            type="text"
            value={nome}
            onChange={(event) => setNome(event.target.value)}
            placeholder="Ex.: Erika Hilton"
            disabled={disabled}
            className={inputClass}
          />
        </div>

        {/* CARGO */}

        <div>
          <label htmlFor="politico-cargo" className={labelClass}>
            Cargo
          </label>

          <select
            id="politico-cargo"
            value={cargo}
            onChange={(event) => setCargo(event.target.value)}
            disabled={disabled}
            className={inputClass}
          >
            <option value="">Todos os cargos</option>

            {CARGOS.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
        </div>

        {/* ESTADO */}

        <div>
          <label htmlFor="politico-uf" className={labelClass}>
            Estado
          </label>

          <select
            id="politico-uf"
            value={uf}
            onChange={(event) => setUf(event.target.value)}
            disabled={disabled}
            className={inputClass}
          >
            <option value="">Todos os estados</option>

            {ESTADOS.map((estado) => (
              <option key={estado} value={estado}>
                {estado}
              </option>
            ))}
          </select>
        </div>

        {/* MUNICÍPIO */}

        <div>
          <label htmlFor="politico-municipio" className={labelClass}>
            Município
          </label>

          <input
            id="politico-municipio"
            type="text"
            value={municipio}
            onChange={(event) => setMunicipio(event.target.value)}
            placeholder="Ex.: São Paulo"
            disabled={disabled}
            className={inputClass}
          />
        </div>

        {/* PARTIDO */}

        <div>
          <label htmlFor="politico-partido" className={labelClass}>
            Partido
          </label>

          <input
            id="politico-partido"
            type="text"
            value={partido}
            onChange={(event) => setPartido(event.target.value)}
            placeholder="Ex.: PT"
            maxLength={30}
            disabled={disabled}
            className={inputClass}
          />
        </div>

        {/* FASE DO MANDATO */}

        <div>
          <label htmlFor="politico-fase" className={labelClass}>
            Situação do mandato
          </label>

          <select
            id="politico-fase"
            value={faseMandato}
            onChange={(event) => setFaseMandato(event.target.value)}
            disabled={disabled}
            className={inputClass}
          >
            <option value="">Todas as situações</option>
            <option value="em_exercicio">
              Em exercício
            </option>
            <option value="eleito_futuro">
              Eleitos para 2027
            </option>
            <option value="mandato_em_andamento">
              Mandato 2025–2028
            </option>
          </select>
        </div>

        {/* BOTÕES */}

        <div className="flex flex-wrap items-end gap-2 md:col-span-2 xl:col-span-3">

          <button
            type="submit"
            disabled={disabled}
            className="h-11 rounded-lg bg-sky-600 px-5 text-xs font-semibold text-white transition hover:bg-sky-500 disabled:opacity-50"
          >
            Pesquisar
          </button>

          <button
            type="button"
            onClick={handleClear}
            disabled={disabled}
            className="h-11 rounded-lg border border-[#41464b] px-4 text-xs text-[#cbd5e1] transition hover:bg-[#303438] disabled:opacity-50"
          >
            Limpar filtros
          </button>

        </div>

      </form>
    </section>
  );
}