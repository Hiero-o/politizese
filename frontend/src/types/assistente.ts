export interface AssistenteSource {
  kind: "document" | "politico";
  id: string;
  title: string;
  detail: string | null;
  excerpt: string | null;
  href: string | null;
}

export interface AssistenteToolUse {
  name: string;
  status: "success" | "error" | "blocked";
  duration_seconds: number;
}

export interface AssistenteChatResponse {
  session_id: string;
  answer: string;
  sources: AssistenteSource[];
  tools_used: AssistenteToolUse[];
  tool_calls_count: number;
  total_duration_seconds: number;
}
