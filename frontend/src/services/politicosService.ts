import type {
  FiltrosPoliticos,
  Politico,
  PoliticosResponse,
} from "@/types/politicos";

const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_URL ||
  "http://127.0.0.1:8000"
).replace(/\/$/, "");

interface ListarPoliticosParams {
  filtros: FiltrosPoliticos;
  pagina: number;
  itens?: number;
  signal?: AbortSignal;
}

export async function listarPoliticos({
  filtros,
  pagina,
  itens = 20,
  signal,
}: ListarPoliticosParams): Promise<PoliticosResponse> {
  const params = new URLSearchParams({
    pagina: String(pagina),
    itens: String(itens),
  });

  if (filtros.nome.trim()) {
    params.set("nome", filtros.nome.trim());
  }

  if (filtros.cargo) {
    params.set("cargo", filtros.cargo);
  }

  if (filtros.uf) {
    params.set("uf", filtros.uf);
  }

  if (filtros.municipio.trim()) {
    params.set("municipio", filtros.municipio.trim());
  }

  if (filtros.partido.trim()) {
    params.set("partido", filtros.partido.trim().toUpperCase());
  }

  if (filtros.fase_mandato) {
    params.set("fase_mandato", filtros.fase_mandato);
  }

  const response = await fetch(
    `${API_BASE_URL}/api/politicos?${params.toString()}`,
    { signal }
  );

  if (!response.ok) {
    const body = await response.json().catch(() => null);

    throw new Error(
      body?.detail ??
      `Erro ao consultar políticos: HTTP ${response.status}`
    );
  }

  return response.json() as Promise<PoliticosResponse>;
}

export async function obterPoliticoPorId(
  id: string,
  signal?: AbortSignal,
): Promise<Politico> {
  const response = await fetch(
    `${API_BASE_URL}/api/politicos/${encodeURIComponent(id)}`,
    { signal },
  );

  if (!response.ok) {
    const body = await response.json().catch(() => null);

    throw new Error(
      body?.detail ??
      `Erro ao consultar perfil do político: HTTP ${response.status}`,
    );
  }

  return response.json() as Promise<Politico>;
}
