import { useEffect, useState } from "react";

import type {
  FiltrosPoliticos,
  FonteStatus,
  Politico,
} from "@/types/politicos";

import { listarPoliticos } from "@/services/politicosService";

const ITENS_POR_PAGINA = 20;

const FILTROS_INICIAIS: FiltrosPoliticos = {
  nome: "",
  cargo: "",
  uf: "",
  municipio: "",
  partido: "",
  fase_mandato: "",
};

export function usePoliticos() {
  const [politicos, setPoliticos] = useState<Politico[]>([]);

  const [pagina, setPagina] = useState(1);
  const [total, setTotal] = useState(0);
  const [ultimaPagina, setUltimaPagina] = useState(1);

  const [fontes, setFontes] = useState<FonteStatus[]>([]);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [filtros, setFiltros] =
    useState<FiltrosPoliticos>(FILTROS_INICIAIS);

  const [reloadKey, setReloadKey] = useState(0);

  
  // CONSULTAR CATÁLOGO
  

  useEffect(() => {
    const controller = new AbortController();

    async function carregarPoliticos() {
      try {
        setLoading(true);
        setError(null);

        const resultado = await listarPoliticos({
          filtros,
          pagina,
          itens: ITENS_POR_PAGINA,
          signal: controller.signal,
        });

        setPoliticos(resultado.dados);
        setTotal(resultado.total);
        setUltimaPagina(resultado.ultima_pagina);
        setFontes(resultado.fontes ?? []);

      } catch (erro) {
        if (
          erro instanceof Error &&
          erro.name !== "AbortError"
        ) {
          setError(erro.message);
          setPoliticos([]);
          setTotal(0);
          setUltimaPagina(1);
          setFontes([]);
        }
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      }
    }

    void carregarPoliticos();

    return () => {
      controller.abort();
    };
  }, [
    pagina,
    filtros.nome,
    filtros.cargo,
    filtros.uf,
    filtros.municipio,
    filtros.partido,
    filtros.fase_mandato,
    reloadKey,
  ]);

  
  // APLICAR FILTROS
  

  function aplicarFiltros(novosFiltros: FiltrosPoliticos) {
    setPagina(1);
    setFiltros(novosFiltros);
  }

  
  // LIMPAR FILTROS
  

  function limparFiltros() {
    setPagina(1);
    setFiltros(FILTROS_INICIAIS);
  }

  
  // RECARREGAR
  

  function recarregar() {
    setReloadKey((atual) => atual + 1);
  }

  
  // RETORNO
  

  return {
    politicos,
    pagina,
    total,
    ultimaPagina,
    fontes,
    loading,
    error,
    filtros,

    setPagina,
    aplicarFiltros,
    limparFiltros,
    recarregar,
  };
}