import { useState } from "react"
import type { FormEvent } from "react";


import type { FiltrosDeputados } from "@/types/deputados"

interface DeputadosFiltersProps {
    onApply: (filtros: FiltrosDeputados) => void;
    onClear: () => void;
    disabled?: boolean;
}


const ESTADOS = [
    "AC", "AL", "AP", "AM", "BA", "CE",
    "DF", "ES", "GO", "MA", "MT", "MS",
    "MG", "PA", "PB", "PR", "PE", "PI",
    "RJ", "RN", "RS", "RO", "RR", "SC",
    "SP", "SE", "TO",
];

export default function DeputadosFilters({
    onApply,
    onClear,
    disabled = false,

}: DeputadosFiltersProps) {
    const [nome, setNome] = useState("");
    const [partido, setPartido] = useState("");
    const [uf, setUf] = useState("");



    // Aplicar Filtros


    function handleSubmit(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();

        onApply({
            nome: nome.trim(),
            sigla_uf: uf,
            sigla_partido: partido.trim().toUpperCase(),
        });
    }


    // Limpar Filtros


    function handleClear() {

        setNome("");
        setPartido("");
        setUf("");

        onClear();
    }




    return (
        <section className="mb-8 rounded-2xl border border-[#373a3e] bg-[#1a1b1c] p-5">

            <div className="mb-5">

                <h2 className="text-base font-semibold">
                    Encontrar Deputado Federal
                </h2>
                

                <p className="mt-1 text-xs text-[#9ca3af]">
                    Pesquise por nome, partido ou estado.
                </p>

            </div>


            <form
                onSubmit={handleSubmit}
                className="grid grid-cols-1 gap-4 md:grid-cols-[2fr_1fr_1fr_auto]">


                {/* Nome */}

                <div>

                    <label
                        htmlFor="deputado-nome"
                        className="mb-2 block text-xs font-medium text-[#cbd5e1]">
                        Nome
                    </label>


                    <input
                        id="deputado-nome"
                        type="text"
                        value={nome}
                        onChange={(event) => setNome(event.target.value)}
                        placeholder="Ex.: Adriana Ventura"
                        disabled={disabled}
                        className="h-11 w-full rounded-lg border border-[#41464b] bg-[#242729] px-3 text-sm text-white outline-none transition focus:border-sky-500" />

                </div>

                {/* Partido */ }

                    <div>
                        <label
                            htmlFor="deputado-partido"
                            className="mb-2 block text-xs font-medium text-[#cbd5e1]">
                            Partido
                        </label>


                        <input
                            id="deputado-partido"
                            type="text"
                            value={partido}
                            onChange={(event) => setPartido(event.target.value)}
                            placeholder="Ex.: PT"
                            maxLength={20}
                            disabled={disabled}
                            className={"h-11 w-full rounded-lg border border-[#41464b] bg-[#242729] px-3 text-sm uppercase text-white outline-none transition focus:border-sky-500"}
                        />

                    </div>

                {/* Estado */}

                <div>
                    <label htmlFor="deputado-uf" className="mb-2 block text-xs fost-medium text-[#cbd5e1]">
                        Estado
                    </label>

                    <select
                        id="deputado-uf"
                        value={uf}
                        onChange={(event) => setUf(event.target.value)}
                        disabled={disabled}
                        className="h-11 w-full rounded-lg border border-[#41464b] bg-[#242729] px-3 text-sm text-white outline-none transition focus:border-sky-500"
                    >
                        <option value="">
                            Todos os estados
                        </option>

                        {ESTADOS.map((estado) => (
                            <option key={estado} value={estado}>
                                {estado}
                            </option>
                        ))}
                    </select>
                </div>


                {/* Botoes */}

                <div className="flex items-end gap-2">

                    <button
                        type="submit"
                        disabled={disabled}
                        className="h-11 rounded-lg bg-sky-600 px-4 text-xs font-semibold text-white transition hover:bg-sky-500 disabled:opacity-50">
                        Pesquisar
                    </button>


                    <button
                        type="button"
                        onClick={handleClear}
                        disabled={disabled}
                        className="h-11 rounded-lg border border-[#41464b] px-3 text-xs text-[#cbd5e1] transition hover:bg-[#303438] disabled:opacity-50"
                    >
                        Limpar
                    </button>
                </div>
            </form>
        </section>
    );
}