
import type {
  DeputadosResponse,
  FiltrosDeputados,
} from "@/types/deputados";


const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_URL ??
  "http://127.0.0.1:8000"
).replace(/\/$/, "");


interface ListarDeputadosParams {
  filtros: FiltrosDeputados;
  pagina: number;
  itens?: number;
  signal?: AbortSignal;
}


export async function listarDeputados({
  filtros,
  pagina,
  itens = 20,
  signal,
}: ListarDeputadosParams): Promise<DeputadosResponse> {

  const params = new URLSearchParams({
    pagina: String(pagina),
    itens: String(itens),
  });

  if (filtros.nome.trim()) {
    params.set("nome", filtros.nome.trim());
  }

  if (filtros.sigla_uf) {
    params.set("sigla_uf", filtros.sigla_uf);
  }

  if (filtros.sigla_partido.trim()) {
    params.set(
      "sigla_partido",
      filtros.sigla_partido.trim().toUpperCase()
    );
  }

  const response = await fetch(
    `${API_BASE_URL}/api/deputados?${params.toString()}`,
    {
      signal,
    }
  );

  if (!response.ok) {
    const body = await response.json().catch(() => null);

    throw new Error(
      body?.detail ??
      `Erro ao consultar deputados: HTTP ${response.status}`
    );
  }

  return response.json() as Promise<DeputadosResponse>;
}
