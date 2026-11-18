
import { useEffect, useState } from "react";

import type {
  Deputado,
  FiltrosDeputados,
} from "@/types/deputados";

import { listarDeputados } from "@/services/deputadosService";


const FILTROS_INICIAIS: FiltrosDeputados = {
  nome: "",
  sigla_uf: "",
  sigla_partido: "",
};


export function useDeputados() {

  const [deputados, setDeputados] = useState<Deputado[]>([]);
  const [pagina, setPagina] = useState(1);
  const [temProxima, setTemProxima] = useState(false);
  const [ultimaPagina, setUltimaPagina] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filtros, setFiltros] = useState<FiltrosDeputados>(
    FILTROS_INICIAIS
  );

  const [reloadKey, setReloadKey] = useState(0);


  
  // CONSULTAR DEPUTADOS
  

  useEffect(() => {

    const controller = new AbortController();

    async function carregarDeputados() {

      try {

        setLoading(true);
        setError(null);

        const resultado = await listarDeputados({
          filtros,
          pagina,
          itens: 20,
          signal: controller.signal,
        });

        setDeputados(resultado.dados);
        setTemProxima(Boolean(resultado.tem_proxima));
        setUltimaPagina(resultado.ultima_pagina);

      } catch (erro) {

        if (
          erro instanceof Error &&
          erro.name !== "AbortError"
        ) {

          setError(erro.message);
          setDeputados([]);
          setTemProxima(false);
          setUltimaPagina(null);

        }

      } finally {

        if (!controller.signal.aborted) {
          setLoading(false);
        }

      }
    }

    void carregarDeputados();

    return () => {
      controller.abort();
    };

  }, [
    pagina,
    filtros.nome,
    filtros.sigla_uf,
    filtros.sigla_partido,
    reloadKey,
  ]);


  
  // APLICAR FILTROS
  

  function aplicarFiltros(novosFiltros: FiltrosDeputados) {

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
    setReloadKey((current) => current + 1);
  }


  
  // RETORNO DO HOOK
  

  return {
    deputados,
    pagina,
    ultimaPagina,
    temProxima,
    loading,
    error,
    filtros,

    setPagina,
    aplicarFiltros,
    limparFiltros,
    recarregar,
  };
}
