import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";

import {
  enviarMensagemAssistente,
  limparSessaoAssistente,
} from "@/services/assistenteService";
import type {
  AssistenteChatResponse,
  AssistenteSource,
  AssistenteToolUse,
} from "@/types/assistente";

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: AssistenteSource[];
  tools?: AssistenteToolUse[];
  duration?: number;
}

const WELCOME_MESSAGE: ChatMessage = {
  id: "welcome",
  role: "assistant",
  content:
    "Olá! Sou o assistente do Politize-se. Posso ajudar a consultar informações da Constituição Federal, entender regras políticas e eleitorais, pesquisar representantes públicos e realizar cálculos de quórum.\n\nMinhas respostas procuram apresentar as referências utilizadas. Quando a base não tiver informação suficiente, vou sinalizar essa limitação.",
};

const SUGGESTIONS = [
  "Quais são os requisitos para concorrer à Presidência?",
  "Quem são os senadores de SP?",
  "Qual é a idade mínima para ser prefeito?",
  "Quantos votos representam três quintos de 513 deputados?",
];

const TOOL_LABELS: Record<string, string> = {
  search_constitution: "Pesquisa na Constituição",
  search_constitution_decomposed: "Pesquisa constitucional composta",
  search_politicos: "Consulta ao catálogo de políticos",
  calculate_voting_threshold: "Cálculo de quórum",
};

function criarId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function SourceCard({ source }: { source: AssistenteSource }) {
  const content = (
    <>
      <div className="flex items-start justify-between gap-3">
        <span className="text-xs font-semibold text-sky-300">
          {source.kind === "politico" ? "Representante consultado" : "Documento consultado"}
        </span>
        {source.kind === "politico" && (
          <span className="text-[10px] text-sky-300">Ver perfil ↗</span>
        )}
      </div>
      <p className="mt-1 text-xs font-semibold text-white">{source.title}</p>
      {source.detail && (
        <p className="mt-1 text-[11px] text-[#aeb7bf]">{source.detail}</p>
      )}
      {source.excerpt && (
        <p className="mt-2 line-clamp-3 text-[11px] leading-relaxed text-[#9ca3af]">
          {source.excerpt}
        </p>
      )}
      {source.kind === "document" && (
        <p className="mt-2 break-all text-[10px] text-[#737d86]">ID: {source.id}</p>
      )}
    </>
  );

  if (source.href) {
    return (
      <a
        href={source.href}
        className="block rounded-xl border border-[#343b40] bg-[#202427] p-3 transition hover:border-sky-500/50"
      >
        {content}
      </a>
    );
  }

  return (
    <div className="rounded-xl border border-[#343b40] bg-[#202427] p-3">
      {content}
    </div>
  );
}

function ToolSummary({ tools }: { tools: AssistenteToolUse[] }) {
  if (!tools.length) return null;

  const uniqueTools = Array.from(
    new Set(tools.map((tool) => tool.name))
  );

  return (
    <div className="mt-3 flex flex-wrap gap-2">
      {uniqueTools.map((tool) => (
        <span
          key={tool}
          className="rounded-full border border-[#3c454c] bg-[#252b30] px-2.5 py-1 text-[10px] text-[#bac4cb]"
        >
          {TOOL_LABELS[tool] || tool}
        </span>
      ))}
    </div>
  );
}

export default function ChatAssistente() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([WELCOME_MESSAGE]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const storageKey = "politizese_assistant_session_id";
    let currentId = window.localStorage.getItem(storageKey);

    if (!currentId) {
      currentId = criarId();
      window.localStorage.setItem(storageKey, currentId);
    }

    setSessionId(currentId);
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, loading]);

  async function enviar(
    event?: FormEvent<HTMLFormElement>,
    suggestedMessage?: string
  ) {
    event?.preventDefault();

    const question = (suggestedMessage ?? input).trim();
    if (!question || !sessionId || loading) return;

    const userMessage: ChatMessage = {
      id: criarId(),
      role: "user",
      content: question,
    };

    setMessages((current) => [...current, userMessage]);
    setInput("");
    setError(null);
    setLoading(true);

    try {
      const result: AssistenteChatResponse = await enviarMensagemAssistente(
        sessionId,
        question
      );

      setMessages((current) => [
        ...current,
        {
          id: criarId(),
          role: "assistant",
          content: result.answer,
          sources: result.sources,
          tools: result.tools_used,
          duration: result.total_duration_seconds,
        },
      ]);
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Não foi possível enviar a mensagem."
      );
    } finally {
      setLoading(false);
    }
  }

  async function novaConversa() {
    if (loading) return;

    if (sessionId) {
      try {
        await limparSessaoAssistente(sessionId);
      } catch {
        // A nova sessão continua podendo ser criada mesmo se a limpeza falhar.
      }
    }

    const nextId = criarId();
    window.localStorage.setItem("politizese_assistant_session_id", nextId);
    setSessionId(nextId);
    setMessages([WELCOME_MESSAGE]);
    setInput("");
    setError(null);
  }

  return (
    <section className="mx-auto flex w-[92%] max-w-[1100px] flex-col py-8">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-sky-300">
            Politize-se · Inteligência pública
          </p>
          <h1 className="mt-2 text-2xl font-bold text-white md:text-3xl">
            Assistente virtual
          </h1>
          <p className="mt-2 max-w-2xl text-sm leading-relaxed text-[#aeb7bf]">
            Pergunte sobre política, Constituição e representantes. As respostas
            podem incluir documentos e registros consultados durante a pesquisa.
          </p>
        </div>
        <button
          type="button"
          onClick={novaConversa}
          disabled={loading}
          className="rounded-lg border border-[#3d454b] px-4 py-2 text-xs font-semibold text-[#d4d9dd] transition hover:bg-[#272c30] disabled:cursor-not-allowed disabled:opacity-50"
        >
          Nova conversa
        </button>
      </div>

      <div className="overflow-hidden rounded-2xl border border-[#373a3e] bg-[#17191b] shadow-xl">
        <div className="flex items-center justify-between border-b border-[#30363a] bg-[#1c2023] px-5 py-3">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-sky-500/15 text-sm font-bold text-sky-300">
              P
            </div>
            <div>
              <p className="text-sm font-semibold text-white">Politize-se AI</p>
              <p className="text-[11px] text-[#89949c]">Modelo local · respostas com evidências</p>
            </div>
          </div>
          <span className="rounded-full border border-emerald-500/20 bg-emerald-500/10 px-2.5 py-1 text-[10px] text-emerald-300">
            Sessão ativa
          </span>
        </div>

        <div className="max-h-[62vh] min-h-[420px] space-y-5 overflow-y-auto px-4 py-6 md:px-6">
          {messages.map((message) => (
            <div
              key={message.id}
              className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`w-full max-w-[88%] rounded-2xl px-4 py-3 md:max-w-[82%] ${
                  message.role === "user"
                    ? "rounded-br-md bg-sky-600 text-white"
                    : "rounded-bl-md border border-[#343a3f] bg-[#202427] text-[#e5e9ec]"
                }`}
              >
                <p className="whitespace-pre-wrap break-words text-sm leading-relaxed">
                  {message.content}
                </p>

                {message.role === "assistant" && message.sources && message.sources.length > 0 && (
                  <div className="mt-4 border-t border-[#3a4146] pt-3">
                    <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-[#aeb7bf]">
                      Referências consultadas
                    </p>
                    <div className="grid gap-2 sm:grid-cols-2">
                      {message.sources.map((source) => (
                        <SourceCard key={`${source.kind}-${source.id}`} source={source} />
                      ))}
                    </div>
                  </div>
                )}

                {message.role === "assistant" && message.tools && (
                  <ToolSummary tools={message.tools} />
                )}

                {message.role === "assistant" && message.duration !== undefined && (
                  <p className="mt-2 text-right text-[10px] text-[#78838b]">
                    Processado em {message.duration.toFixed(1)}s
                  </p>
                )}
              </div>
            </div>
          ))}

          {loading && (
            <div className="flex justify-start">
              <div className="rounded-2xl rounded-bl-md border border-[#343a3f] bg-[#202427] px-4 py-3 text-sm text-[#aeb7bf]">
                Consultando as fontes e preparando a resposta…
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        {error && (
          <div className="mx-4 mb-3 rounded-lg border border-red-500/25 bg-red-500/10 px-4 py-3 text-xs text-red-200 md:mx-6">
            {error}
          </div>
        )}

        <div className="border-t border-[#30363a] bg-[#1c2023] p-4 md:p-5">
          {messages.length === 1 && (
            <div className="mb-4 flex flex-wrap gap-2">
              {SUGGESTIONS.map((suggestion) => (
                <button
                  key={suggestion}
                  type="button"
                  onClick={() => void enviar(undefined, suggestion)}
                  disabled={!sessionId || loading}
                  className="rounded-full border border-[#3b454c] px-3 py-2 text-left text-[11px] text-[#c6d0d6] transition hover:border-sky-500/50 hover:bg-sky-500/5 disabled:opacity-50"
                >
                  {suggestion}
                </button>
              ))}
            </div>
          )}

          <form onSubmit={(event) => void enviar(event)} className="flex items-end gap-3">
            <textarea
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  void enviar();
                }
              }}
              rows={2}
              maxLength={2000}
              placeholder="Pergunte algo sobre política, Constituição ou representantes…"
              className="max-h-36 min-h-[54px] flex-1 resize-y rounded-xl border border-[#3b4247] bg-[#111416] px-4 py-3 text-sm text-white outline-none placeholder:text-[#737d85] focus:border-sky-500/60"
              disabled={!sessionId || loading}
            />
            <button
              type="submit"
              disabled={!sessionId || loading || !input.trim()}
              className="h-[54px] rounded-xl bg-sky-600 px-5 text-sm font-semibold text-white transition hover:bg-sky-500 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Enviar
            </button>
          </form>
          <p className="mt-2 text-[10px] text-[#737d85]">
            Não envie CPF, telefone ou e-mail. A memória desta conversa é mantida enquanto o backend estiver ativo.
          </p>
        </div>
      </div>
    </section>
  );
}
