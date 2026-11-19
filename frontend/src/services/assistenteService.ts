import type { AssistenteChatResponse } from "@/types/assistente";

const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000"
).replace(/\/$/, "");

export async function enviarMensagemAssistente(
  sessionId: string,
  message: string
): Promise<AssistenteChatResponse> {
  const response = await fetch(`${API_BASE_URL}/api/assistente/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      session_id: sessionId,
      message,
    }),
  });

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(
      body?.detail || `Não foi possível conversar com o assistente (HTTP ${response.status}).`
    );
  }

  return response.json() as Promise<AssistenteChatResponse>;
}

export async function limparSessaoAssistente(
  sessionId: string
): Promise<void> {
  const response = await fetch(
    `${API_BASE_URL}/api/assistente/sessoes/${encodeURIComponent(sessionId)}`,
    { method: "DELETE" }
  );

  if (!response.ok && response.status !== 404) {
    throw new Error("Não foi possível limpar a conversa anterior.");
  }
}
