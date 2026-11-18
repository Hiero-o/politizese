export interface Deputado {
    id: number;
    nome: string;
    partido: string | null;
    uf: string | null;
    id_legislatura: number | null;
    foto_url: string | null;
    email: string | null;
    fonte_url: string | null;

}




export interface DeputadosResponse {
    dados: Deputado[];
    pagina: number;
    itens:number;
    tem_proxima:boolean;
    ultima_pagina: number | null;
}

export interface FiltrosDeputados {
    nome: string;
    sigla_uf: string;
    sigla_partido: string;
}