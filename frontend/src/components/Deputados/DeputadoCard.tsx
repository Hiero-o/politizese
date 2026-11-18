import { useState } from "react";

import type { Deputado } from "@/types/deputados";

interface DeputadoCardProps{
    deputado: Deputado;
}


export default function DeputadoCard({
    deputado: Deputado
}: DeputadoCardProps) {
    const [ imageError, setImageError] = useState(false);

    const iniciais = Deputado.nome
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((parte) => parte[0])
    .join("");

    return (
        <article className="flex min-w-0 items-center gap-4 rounded-2x1 border border-[#373a3e] bg-[#1a1b1c] p-4 transition hover:border-[#59636b] hover:bg-[#202326]">
            {/* FOTO */}

            <div className="flex h-[76px] w-[76px] shrink-0 items-center justify-center overflow rounded-x1 border-[#41464b] bg-[#303438]"> 
                {Deputado.foto_url && !imageError ? (
                    <img
                        src={Deputado.foto_url}
                        alt={`foto de ${Deputado.nome}`}
                        loading="lazy"
                        className="h-full w-full object-cover"
                        onError={() => setImageError(true)}    
                        
                    />
                ): (

                    <span className="text-x1 font-bold text-[#9ca3af]">
                        {iniciais}
                    </span>
                )}
            </div>

            {/* informações */}

            <div className="min-w-0 flex-1">

                <h3 className="truncate text-sm font-semibold text-white">
                    {Deputado.nome}
                </h3>

                <div className="mt-2 flex-wrap gap-2">

                    {Deputado.partido && (
                        <span className="rounded-md bg-sky-500/10 px-2 py-1 text-[11px] font-semibold text-sky-300">
                            {Deputado.partido}
                        </span>
                    )}

                    {Deputado.uf && (
                        <span className="rounded-md bg-[#303438] px-2 py-1 text-[11px] font-medium text-[#d1d5db]">
                            {Deputado.uf}
                        </span>
                    )}

                </div>

                <p className="mt-2 text-[10px] text-[#808991]">
                    ID: {Deputado.id}
                </p>

                {Deputado.fonte_url && (
                    <a
                    href={Deputado.fonte_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="mt-2 inline-block text-[11px] font-medium text-sky-400 hover:text-sky-300">
                        Fonte Oficial ↗
                    </a>
                )}
    
            </div>

        </article>
    );

}