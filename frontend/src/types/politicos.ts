export type FaseMandato =
  | "em_exercicio"
  | "eleito_futuro"
  | "mandato_em_andamento";

export interface Politico {
  id: string;
  id_origem: string | number;
  fonte: string;

  nome: string;
  cargo: string;
  cargo_slug: string;

  partido: string | null;
  uf: string | null;
  municipio: string | null;
  codigo_municipio_tse: string | null;

  foto_url: string | null;
  email: string | null;
  telefone: string | null;

  situacao: string | null;
  titularidade: string | null;
  mandato: string | null;

  fase_mandato: FaseMandato;

  numero_candidato: string | null;
  situacao_eleitoral: string | null;
  turno_eleitoral: number | null;
  ano_eleicao: number | null;

  fonte_url: string | null;
}

export interface FonteStatus {
  fonte: string;

  status:
    | "atualizada"
    | "cache_valido"
    | "cache_desatualizado"
    | "indisponivel"
    | "cadastro_local";

  atualizado_em: string | null;
  registros: number;
  mensagem: string | null;
}

export interface PoliticosResponse {
  dados: Politico[];

  pagina: number;
  itens: number;

  total: number;
  total_paginas: number;

  tem_proxima: boolean;
  ultima_pagina: number;

  fontes: FonteStatus[];
}

export interface FiltrosPoliticos {
  nome: string;
  cargo: string;
  uf: string;
  municipio: string;
  partido: string;
  fase_mandato: string;
}