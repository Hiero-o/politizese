
"""Agente ReAct do Politizese com métricas de desempenho."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
import unicodedata
from time import perf_counter
from typing import Any, TYPE_CHECKING

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from src.agents.agent_schemas import (
    AgentRunResult,
    AgentSource,
    AgentTimingEvent,
    AgentTraceEntry,
)
from src.agents.tools import (
    PolitizeseToolbox,
    build_politizese_toolbox,
)
from src.guardrails.moderation import (
    personal_data_block_reason,
)

from src.guardrails.scope_validator import (
    is_greeting,
    validate_scope,
    is_capabilities_question
)

from src.agents.tool_authorization import (
    get_tool_authorization_error,
)

if TYPE_CHECKING:
    from src.core.config import Settings


logger = logging.getLogger(__name__)

MAX_TOOL_CALLS = 6
MAX_QUESTION_LENGTH = 2000
MAX_TRACE_OBSERVATION_LENGTH = 2500


AGENT_DECISIONS = {
    "search_constitution": (
        "O modelo selecionou uma pesquisa constitucional direta."
    ),
    "search_constitution_decomposed": (
        "O modelo selecionou uma pesquisa com decomposição."
    ),
    "search_politicos": (
        "O modelo consultou o catálogo público de representantes."
    ),
    "calculate_voting_threshold": (
        "O modelo selecionou um cálculo matemático determinístico."
    ),
}


FINAL_SYNTHESIS_INSTRUCTION = (
    "O limite de chamadas de ferramentas foi atingido. "
    "Não solicite novas ferramentas. Produza agora a melhor resposta "
    "possível utilizando exclusivamente as observações já recebidas. "
    "Cite os doc_id disponíveis. Se as evidências forem insuficientes, "
    "informe claramente essa limitação."
)


_STATE_CODES = {
    "acre": "AC", "alagoas": "AL", "amapa": "AP",
    "amazonas": "AM", "bahia": "BA", "ceara": "CE",
    "distrito federal": "DF", "espirito santo": "ES",
    "goias": "GO", "maranhao": "MA", "mato grosso": "MT",
    "mato grosso do sul": "MS", "minas gerais": "MG",
    "para": "PA", "paraiba": "PB", "parana": "PR",
    "pernambuco": "PE", "piaui": "PI",
    "rio de janeiro": "RJ", "rio grande do norte": "RN",
    "rio grande do sul": "RS", "rondonia": "RO", "roraima": "RR",
    "santa catarina": "SC", "sao paulo": "SP", "sergipe": "SE",
    "tocantins": "TO",
}

_ROLE_PATTERNS = (
    ("deputado_distrital", r"\bdeputados? distritais?\b"),
    ("deputado_federal", r"\bdeputados? federais?\b"),
    ("deputado_estadual", r"\bdeputados? estaduais?\b"),
    ("vice_presidente", r"\bvice presidentes?\b"),
    ("senador", r"\bsenadores?\b"),
    ("governador", r"\bgovernadores?\b"),
    ("prefeito", r"\bprefeitos?\b"),
    ("vereador", r"\bvereadores?\b"),
    ("presidente", r"\bpresidentes?\b"),
)


def _normalize_lookup_text(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.casefold())
    value = "".join(
        char for char in value
        if not unicodedata.combining(char)
    )
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def _extract_politico_lookup_filters(question: str) -> dict[str, Any] | None:
    """Extrai filtros simples para consulta factual de representantes.

    É usado apenas como fallback quando o LLM tenta responder sem chamar
    a ferramenta obrigatória de catálogo. Não roteia perguntas conceituais,
    como requisitos, competências ou atribuições dos cargos.
    """
    normalized = _normalize_lookup_text(question)
    if not normalized:
        return None

    conceptual_terms = (
        "requisito", "idade", "atribuicao", "competencia", "funcao",
        "dever", "poderes", "como funciona", "o que faz", "diferenca",
        "conceito", "definicao", "duracao do mandato",
    )
    if any(term in normalized for term in conceptual_terms):
        return None

    cargo = None
    for slug, pattern in _ROLE_PATTERNS:
        if re.search(pattern, normalized):
            cargo = slug
            break
    if cargo is None:
        return None

    lookup_intent = (
        r"\bquem e\b", r"\bquem sao\b", r"\bquais\b",
        r"\bliste\b", r"\blistar\b", r"\blista\b",
        r"\batual(?:mente)?\b", r"\bem exercicio\b",
        r"\bquem ocupa\b", r"\bocupantes?\b",
        r"\brepresentantes?\b", r"\bno catalogo\b",
    )
    if not any(re.search(pattern, normalized) for pattern in lookup_intent):
        # A menção explícita ao cargo com um estado também caracteriza busca.
        if not any(
            re.search(rf"\b{re.escape(state)}\b", normalized)
            for state in _STATE_CODES
        ) and not re.search(r"\b(?:sp|rj|mg|es|pr|sc|rs|ba|go|mt|ms|df|ac|al|ap|am|ce|ma|pa|pb|pe|pi|rn|ro|rr|se|to)\b", normalized):
            return None

    filters: dict[str, Any] = {"cargo": cargo, "limite": 8}

    for state_name, state_code in sorted(
        _STATE_CODES.items(), key=lambda item: len(item[0]), reverse=True
    ):
        if re.search(rf"\b{re.escape(state_name)}\b", normalized):
            filters["uf"] = state_code
            break

    if "uf" not in filters:
        state_codes = (
            "AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO"
        ).split()
        for code in state_codes:
            if re.search(rf"\b{code.casefold()}\b", normalized):
                filters["uf"] = code
                break

    current_terms = (
        "atual", "atualmente", "atuais", "em exercicio", "hoje",
    )
    if any(term in normalized for term in current_terms):
        filters["fase_mandato"] = "em_exercicio"

    return filters


def _format_politicos_answer(payload: dict[str, Any]) -> str:
    """Monta a resposta exclusivamente com campos devolvidos pelo catálogo."""
    politicos = payload.get("politicos") or []
    total = payload.get("total_matches", len(politicos))
    filters = payload.get("filters") or {}

    if not politicos:
        criterios = []
        for key, label in (("cargo", "cargo"), ("uf", "UF"),
                           ("municipio", "município"), ("partido", "partido"),
                           ("fase_mandato", "fase do mandato")):
            if filters.get(key):
                criterios.append(f"{label}: {filters[key]}")
        suffix = f" (" + "; ".join(criterios) + ")" if criterios else ""
        return (
            "Não encontrei registros no catálogo do Politize-se para os filtros "
            f"informados{suffix}. Não vou preencher a lista com informações não confirmadas."
        )

    lines = [
        f"Encontrei **{total} registro(s)** no catálogo do Politize-se. "
        "Abaixo estão os dados retornados pela consulta:"
    ]

    phase_labels = {
        "em_exercicio": "Em exercício",
        "eleito_futuro": "Eleito para o próximo mandato",
        "mandato_em_andamento": "Mandato em andamento; exercício atual não verificado",
    }

    for item in politicos:
        if not isinstance(item, dict):
            continue
        politician_id = str(item.get("id") or "").strip()
        name = str(item.get("nome") or "Nome não informado").strip()
        details = [
            str(item.get("cargo") or "Cargo não informado"),
            f"Partido: {item.get('partido') or 'não informado'}",
        ]
        if item.get("uf"):
            details.append(f"UF: {item['uf']}")
        if item.get("municipio"):
            details.append(f"Município: {item['municipio']}")
        if item.get("situacao"):
            details.append(f"Situação: {item['situacao']}")
        if item.get("titularidade"):
            details.append(f"Titularidade: {item['titularidade']}")
        phase = item.get("fase_mandato")
        if phase:
            details.append(phase_labels.get(str(phase), str(phase)))
        if item.get("mandato"):
            details.append(f"Mandato: {item['mandato']}")

        profile = (
            " · Perfil disponível nas referências abaixo"
            if politician_id else ""
        )
        lines.append(f"- **{name}** — " + " · ".join(details) + profile)

    used_source_names = {
        str(item.get("fonte"))
        for item in politicos
        if isinstance(item, dict) and item.get("fonte")
    }
    source_titles = {
        "senado": "Senado Federal",
        "camara": "Câmara dos Deputados",
        "tse": "TSE — eleições gerais",
        "tse_municipal": "TSE — eleições municipais",
        "planalto": "Presidência da República",
    }
    status_labels = {
        "atualizada": "fonte atualizada",
        "cache_valido": "snapshot local válido",
        "cache_desatualizado": "snapshot local desatualizado",
        "indisponivel": "fonte indisponível",
        "cadastro_local": "cadastro local",
    }
    for source in payload.get("fontes", []):
        if not isinstance(source, dict) or source.get("fonte") not in used_source_names:
            continue
        source_name = source_titles.get(
            str(source.get("fonte")), str(source.get("fonte"))
        )
        source_status = status_labels.get(
            str(source.get("status")), str(source.get("status"))
        )
        lines.append(f"\n**Situação da fonte ({source_name}):** {source_status}.")

    lines.append(
        "\nOs nomes, partidos, mandatos e identificadores acima foram "
        "preservados do resultado estruturado da ferramenta. Não foram "
        "completados por conhecimento do modelo."
    )
    if any(
        isinstance(item, dict) and item.get("id")
        for item in politicos
    ):
        lines.append("\nUse os cartões de referência exibidos abaixo para abrir cada perfil no Politize-se.")
    return "\n".join(lines)


class AgentExecutionError(RuntimeError):
    """Erro controlado durante a execução do agente."""


class PolitizeseReActAgent:
    """Executa um ciclo ReAct com limite de ferramentas e métricas."""

    def __init__(
        self,
        llm: Any,
        toolbox: PolitizeseToolbox,
        system_prompt: str,
        max_tool_calls: int = MAX_TOOL_CALLS,
        prompt_task: str = "react_agent",
    ) -> None:

        if type(max_tool_calls) is not int:
            raise TypeError(
                "max_tool_calls precisa ser um número inteiro."
            )

        if not 1 <= max_tool_calls <= MAX_TOOL_CALLS:
            raise ValueError(
                f"O limite de chamadas precisa estar entre 1 e "
                f"{MAX_TOOL_CALLS}."
            )

        if not system_prompt or not system_prompt.strip():
            raise ValueError("O system prompt não pode estar vazio.")

        self._llm = llm
        self._toolbox = toolbox
        self._tool_map = toolbox.tool_map
        self._system_prompt = system_prompt
        self._max_tool_calls = max_tool_calls
        
        self._force_initial_legal_search = (
            prompt_task == "react_agent_legislativo"
        )
        self._llm_with_tools = self._llm.bind_tools(
            toolbox.tools
        )

    @property
    def available_tools(self) -> tuple[str, ...]:
        """Retorna os nomes das ferramentas autorizadas."""

        return tuple(self._tool_map.keys())

    @staticmethod
    def _content_to_text(content: Any) -> str:
        """Converte o conteúdo de uma mensagem em texto."""

        if isinstance(content, str):
            return content.strip()

        if isinstance(content, list):
            parts = []

            for item in content:
                if isinstance(item, str):
                    parts.append(item)

                elif isinstance(item, dict):
                    text = item.get("text")

                    if isinstance(text, str):
                        parts.append(text)

            return "\n".join(parts).strip()

        return str(content).strip() if content is not None else ""

    @staticmethod
    def _extract_ollama_metrics(response) -> dict[str, int | float]:
        """Extrai métricas do Ollama e converte os tempos para segundos."""
        metadata = getattr(response, "response_metadata", {}) or {}

        nanosecond_fields = {
            "total_duration": "total_duration_seconds",
            "load_duration": "load_duration_seconds",
            "prompt_eval_duration": "prompt_eval_duration_seconds",
            "eval_duration": "eval_duration_seconds",
        }

        metrics = {}

        for source_field, target_field in nanosecond_fields.items():
            value = metadata.get(source_field)

            if isinstance(value, (int, float)):
                metrics[target_field] = round(value / 1_000_000_000, 3)

        prompt_tokens = metadata.get("prompt_eval_count")
        generated_tokens = metadata.get("eval_count")
        eval_duration = metadata.get("eval_duration")

        if isinstance(prompt_tokens, int):
            metrics["prompt_tokens"] = prompt_tokens

        if isinstance(generated_tokens, int):
            metrics["generated_tokens"] = generated_tokens

        if (
            isinstance(generated_tokens, int)
            and isinstance(eval_duration, (int, float))
            and eval_duration > 0
        ):
            metrics["tokens_per_second"] = round(
                generated_tokens / (eval_duration / 1_000_000_000),
                2,
            )

        return metrics

    @staticmethod
    def _controlled_error(
        tool_name: str,
        message: str,
    ) -> str:
        """Cria uma observação de erro em formato JSON."""

        return json.dumps(
            {
                "ok": False,
                "tool": tool_name,
                "error": message[:500],
            },
            ensure_ascii=False,
        )
    
    @staticmethod
    def _wrap_untrusted_observation(
        tool_name: str,
        observation: str,
    ) -> str:
        """
        Identifica a saída de uma ferramenta como
        uma observação não confiável.

        Preserva integralmente o conteúdo original
        dentro do campo payload.
        """

        try:
            payload = json.loads(observation)

        except json.JSONDecodeError:
            payload = observation

        envelope = {
            "observation_type": "untrusted_tool_observation",
            "source_tool": tool_name,
            "payload": payload,
        }

        return json.dumps(
            envelope,
            ensure_ascii=False,
        )

    def _execute_tool(
        self,
        tool_name: str,
        arguments: Any,
    ) -> tuple[str, str]:
        """Executa exclusivamente ferramentas autorizadas."""

        tool = self._tool_map.get(tool_name)

        if tool is None:
            return (
                self._controlled_error(
                    tool_name,
                    "Ferramenta não autorizada ou inexistente.",
                ),
                "error",
            )

        if not isinstance(arguments, dict):
            return (
                self._controlled_error(
                    tool_name,
                    "Os argumentos precisam ser um objeto.",
                ),
                "error",
            )

        try:
            output = tool.invoke(arguments)

            observation = (
                output
                if isinstance(output, str)
                else json.dumps(
                    output,
                    ensure_ascii=False,
                    default=str,
                )
            )

            try:
                parsed = json.loads(observation)

                if isinstance(parsed, dict) and parsed.get("ok") is False:
                    return observation, "error"

            except json.JSONDecodeError:
                pass

            return observation, "success"

        except Exception as error:
            logger.exception(
                "Falha na execução da ferramenta %s.",
                tool_name,
            )

            return (
                self._controlled_error(
                    tool_name,
                    f"{type(error).__name__}: {error}",
                ),
                "error",
            )

    def _build_result(
        self,
        *,
        question: str,
        answer: str,
        started_at: float,
        llm_duration: float,
        tool_duration: float,
        tool_calls_count: int,
        blocked_tool_calls: int,
        tool_limit_reached: bool,
        trace: list[AgentTraceEntry],
        timing_events: list[AgentTimingEvent],
        sources: list[AgentSource],
    ) -> AgentRunResult:
        """Consolida resultado, trace e tempos da execução."""

        total_duration = perf_counter() - started_at

        return AgentRunResult(
            question=question,
            answer=answer,
            tool_calls_count=tool_calls_count,
            max_tool_calls=self._max_tool_calls,
            blocked_tool_calls=blocked_tool_calls,
            tool_limit_reached=tool_limit_reached,
            total_duration_seconds=round(
                total_duration,
                4,
            ),
            llm_duration_seconds=round(
                llm_duration,
                4,
            ),
            tool_duration_seconds=round(
                tool_duration,
                4,
            ),
            trace=trace,
            sources=sources,
            timing_events=timing_events,
        )

    def _make_final_response(
        self,
        *,
        messages: list[Any],
        question: str,
        started_at: float,
        llm_duration: float,
        tool_duration: float,
        tool_calls_count: int,
        blocked_tool_calls: int,
        trace: list[AgentTraceEntry],
        timing_events: list[AgentTimingEvent],
        sources: list[AgentSource],
        tool_limit_reached: bool,
    ) -> AgentRunResult:
        """Gera a síntese final sem disponibilizar novas ferramentas."""

        messages.append(
            HumanMessage(
                content=FINAL_SYNTHESIS_INSTRUCTION
            )
        )

        llm_started_at = perf_counter()

        try:
            response = self._llm.invoke(messages)

        except Exception as error:
            logger.exception(
                "Falha ao gerar a resposta final do agente."
            )

            raise AgentExecutionError(
                "Não foi possível gerar a resposta final do agente."
            ) from error

        elapsed = perf_counter() - llm_started_at
        llm_duration += elapsed

        timing_events.append(
            AgentTimingEvent(
                step=len(timing_events) + 1,
                stage="final_synthesis",
                name="LLM — síntese final",
                duration_seconds=round(elapsed, 4),
                ollama_metrics=self._extract_ollama_metrics(
                    response
                ),
            )
        )

        answer = self._content_to_text(
            response.content
        )

        if not answer:
            answer = (
                "Não consegui elaborar uma resposta final com "
                "as evidências disponíveis."
            )

        return self._build_result(
            question=question,
            answer=answer,
            started_at=started_at,
            llm_duration=llm_duration,
            tool_duration=tool_duration,
            tool_calls_count=tool_calls_count,
            blocked_tool_calls=blocked_tool_calls,
            tool_limit_reached=tool_limit_reached,
            trace=trace,
            sources=sources,
            timing_events=timing_events,
        )

    @staticmethod
    def _capture_sources(
        observation: str,
        sources: dict[str, AgentSource],
    ) -> None:
        """Extrai referências documentais e de políticos da saída das tools."""

        try:
            payload = json.loads(observation)
        except (json.JSONDecodeError, TypeError):
            return

        if not isinstance(payload, dict) or payload.get("ok") is not True:
            return

        for document in payload.get("documents", []):
            if not isinstance(document, dict):
                continue
            metadata = document.get("metadata") or {}
            if not isinstance(metadata, dict):
                metadata = {}
            doc_id = document.get("doc_id")
            if not isinstance(doc_id, str) or not doc_id.strip():
                continue

            article = metadata.get("article_number")
            part = metadata.get("document_part")
            legal_unit = metadata.get("legal_unit")
            title = "Constituição Federal"
            if article:
                title += f" — Art. {article}"
            if part and str(part).casefold() not in {"cf", "constituicao federal"}:
                title += f" ({part})"
            details = []
            if legal_unit:
                details.append(str(legal_unit).replace("_", " ").title())
            if metadata.get("number"):
                details.append(str(metadata["number"]))

            sources.setdefault(
                doc_id,
                AgentSource(
                    kind="document",
                    id=doc_id,
                    title=title,
                    detail=" · ".join(details) or None,
                    excerpt=str(document.get("content") or "")[:420] or None,
                ),
            )

            parent_context = metadata.get("parent_context") or []
            if isinstance(parent_context, dict):
                parent_context = [parent_context]
            if isinstance(parent_context, list):
                for parent in parent_context:
                    if not isinstance(parent, dict):
                        continue
                    parent_id = parent.get("doc_id")
                    if not isinstance(parent_id, str) or not parent_id.strip():
                        continue
                    parent_meta = parent.get("metadata") or {}
                    if not isinstance(parent_meta, dict):
                        parent_meta = {}
                    parent_article = parent_meta.get("article_number")
                    parent_title = "Constituição Federal"
                    if parent_article:
                        parent_title += f" — Art. {parent_article}"
                    sources.setdefault(
                        parent_id,
                        AgentSource(
                            kind="document",
                            id=parent_id,
                            title=parent_title,
                            detail="Contexto complementar",
                            excerpt=str(parent.get("content") or "")[:420] or None,
                        ),
                    )

        for politico in payload.get("politicos", []):
            if not isinstance(politico, dict):
                continue
            politician_id = politico.get("id")
            name = politico.get("nome")
            if not isinstance(politician_id, str) or not isinstance(name, str):
                continue
            details = [
                value for value in (
                    politico.get("cargo"),
                    politico.get("partido"),
                    politico.get("uf"),
                    politico.get("municipio"),
                    politico.get("situacao"),
                    politico.get("titularidade"),
                    politico.get("mandato"),
                ) if value
            ]
            phase = politico.get("fase_mandato")
            if phase == "eleito_futuro":
                details.append("Eleito para próximo mandato")
            elif phase == "mandato_em_andamento":
                details.append("Exercício atual não verificado")
            sources.setdefault(
                politician_id,
                AgentSource(
                    kind="politico",
                    id=politician_id,
                    title=name,
                    detail=" · ".join(details) or None,
                    href=f"/dashboard/politicos/{politician_id}",
                ),
            )

    def invoke(
        self,
        question: str,
        history: list[BaseMessage] | None = None,
    ) -> AgentRunResult:
        """Executa o agente e mede o tempo de cada etapa."""

        if not isinstance(question, str):
            raise TypeError("A pergunta precisa ser uma string.")

        question = question.strip()

        if not question:
            raise ValueError("A pergunta não pode estar vazia.")

        if len(question) > MAX_QUESTION_LENGTH:
            raise ValueError(
                f"A pergunta excede o limite de "
                f"{MAX_QUESTION_LENGTH} caracteres."
            )

        started_at = perf_counter()

        llm_duration = 0.0
        tool_duration = 0.0

        tool_calls_count = 0
        blocked_tool_calls = 0

        trace: list[AgentTraceEntry] = []
        timing_events: list[AgentTimingEvent] = []
        captured_sources: dict[str, AgentSource] = {}
        successful_politico_payload: dict[str, Any] | None = None

        # Saudações isoladas são tratadas sem chamar o LLM nem o RAG.
        # Elas não são perguntas fora do escopo e não precisam de busca.
        if is_greeting(question):
            return self._build_result(
                question=question,
                answer=(
                    "Oiee! 😊 Posso ajudar com a Constituição, regras "
                    "políticas e eleitorais, representantes públicos e "
                    "cálculos de quórum. O que você quer descobrir?"
                ),
                started_at=started_at,
                llm_duration=0.0,
                tool_duration=0.0,
                tool_calls_count=0,
                blocked_tool_calls=0,
                tool_limit_reached=False,
                trace=[],
                timing_events=[],
                sources=[],
            )
        
        if is_capabilities_question(question):
            return self._build_result(
                question=question,
                answer=(
                    "Posso ajudar você a:\n"
                    "- Consultar a Constituição e a legislação "
                    "disponível na base documental.\n"
                    "- Entender regras políticas e eleitorais, "
                    "incluindo candidaturas e direitos do cidadão.\n"
                    "- Pesquisar representantes públicos.\n"
                    "- Calcular quóruns e outros valores previstos "
                    "nas regras consultadas.\n"
                    "- Consultar informações sobre obras públicas "
                    "e intervenções urbanas próximas, quando "
                    "a integração com o mapa estiver disponível.\n\n"
                    "Você pode escrever sua dúvida em linguagem natural."
                ),
                started_at=started_at,
                llm_duration=0.0,
                tool_duration=0.0,
                tool_calls_count=0,
                blocked_tool_calls=0,
                tool_limit_reached=False,
                trace=[],
                timing_events=[],
                sources=[],
            )

        moderation_reason = personal_data_block_reason(question)

        scope_reason = None

        if moderation_reason is None:
            scope_reason = validate_scope(question)

        block_reason = moderation_reason or scope_reason

        if block_reason is not None:

            is_personal_data = moderation_reason is not None

            action = (
                "guardrail_moderation"
                if is_personal_data
                else "guardrail_scope"
            )

            answer = (
                "Por segurança, não envie CPF, telefone ou e-mail. "
                "Remova os dados pessoais e tente novamente."
                if is_personal_data
                else block_reason
            )

            guardrail_trace = AgentTraceEntry(
                step=1,
                decision_summary=(
                    "A entrada foi bloqueada por uma proteção preventiva."
                ),
                action=action,
                arguments={},
                observation=block_reason,
                status="blocked",
                duration_seconds=round(
                    perf_counter() - started_at,
                    4,
                ),
            )

            return self._build_result(
                question=question,
                answer=answer,
                started_at=started_at,
                llm_duration=0.0,
                tool_duration=0.0,
                tool_calls_count=0,
                blocked_tool_calls=0,
                tool_limit_reached=False,
                trace=[guardrail_trace],
                timing_events=[],
                sources=[],
            )

        safe_history = [
            message
            for message in (history or [])[-12:]
            if isinstance(message, (HumanMessage, AIMessage))
        ]

        messages = [
            SystemMessage(content=self._system_prompt),
            *safe_history,
            HumanMessage(content=question),
        ]
        
                # --------------------------------------------------
        # Busca documental obrigatória na tarefa legislativa
        # --------------------------------------------------

        if self._force_initial_legal_search:

            tool_name = "search_constitution"
            arguments = {"question": question}
            tool_call_id = "initial-legal-search"

            authorization_error = get_tool_authorization_error(
                user_question=question,
                tool_name=tool_name,
            )

            if authorization_error is not None:

                blocked_tool_calls += 1

                observation = self._controlled_error(
                    tool_name,
                    authorization_error,
                )

                status = "blocked"
                elapsed = 0.0

            else:

                tool_calls_count += 1

                tool_started_at = perf_counter()

                observation, status = self._execute_tool(
                    tool_name=tool_name,
                    arguments=arguments,
                )

                elapsed = perf_counter() - tool_started_at
                tool_duration += elapsed

            timing_events.append(
                AgentTimingEvent(
                    step=len(timing_events) + 1,
                    stage=(
                        "tool_blocked"
                        if status == "blocked"
                        else "tool_execution"
                    ),
                    name=tool_name,
                    duration_seconds=round(elapsed, 4),
                )
            )

            if status == "success":
                self._capture_sources(
                    observation,
                    captured_sources,
                )

            trace.append(
                AgentTraceEntry(
                    step=len(trace) + 1,
                    decision_summary=(
                        "O backend executou a busca documental inicial "
                        "obrigatória da tarefa legislativa."
                    ),
                    action=tool_name,
                    arguments=arguments,
                    observation=observation[
                        :MAX_TRACE_OBSERVATION_LENGTH
                    ],
                    status=status,
                    duration_seconds=round(elapsed, 4),
                )
            )

            logger.info(
                "[AGENT TOOL] name=%s args=%s status=%s "
                "duration=%.3fs source=mandatory_legal_search",
                tool_name,
                arguments,
                status,
                elapsed,
            )

            # Registra a chamada e sua observação na conversa
            # para que o modelo receba o resultado como ferramenta.
            messages.extend(
                [
                    AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": tool_name,
                                "args": arguments,
                                "id": tool_call_id,
                                "type": "tool_call",
                            }
                        ],
                    ),
                    ToolMessage(
                        content=observation,
                        tool_call_id=tool_call_id,
                    ),
                ]
            )

        for turn in range(1, self._max_tool_calls + 2):

            # --------------------------------------------------
            # 1. Tempo de decisão/resposta do LLM
            # --------------------------------------------------

            llm_started_at = perf_counter()

            try:
                response = self._llm_with_tools.invoke(
                    messages
                )

            except Exception as error:
                logger.exception(
                    "Falha na inferência do agente ReAct."
                )

                raise AgentExecutionError(
                    "Não foi possível executar o agente "
                    "com o modelo configurado."
                ) from error

            llm_elapsed = perf_counter() - llm_started_at
            llm_duration += llm_elapsed

            requested_calls = (
                getattr(response, "tool_calls", None) or []
            )

            # Identifica a finalidade da requisição.
            if requested_calls:
                stage = (
                    "tool_selection"
                    if tool_calls_count == 0
                    else "post_tool_decision"
                )

            elif tool_calls_count == 0:
                stage = "initial_response"

            else:
                stage = "final_answer"

            timing_events.append(
                AgentTimingEvent(
                    step=len(timing_events) + 1,
                    stage=stage,
                    name="LLM — decisão ou geração",
                    duration_seconds=round(
                        llm_elapsed,
                        4,
                    ),
                    ollama_metrics=self._extract_ollama_metrics(
                        response
                    ),
                )
            )

            messages.append(response)

            # --------------------------------------------------
            # 2. Resposta sem necessidade de ferramentas
            # --------------------------------------------------

            if not requested_calls:
                # O modelo não pode substituir uma consulta factual ao catálogo
                # por uma resposta de memória. Se ele omitir a ferramenta em uma
                # pergunta clara de identificação de representantes, o backend
                # executa a mesma ferramenta como fallback determinístico.
                lookup_filters = _extract_politico_lookup_filters(question)
                if lookup_filters is not None:
                    tool_started_at = perf_counter()
                    observation, status = self._execute_tool(
                        tool_name="search_politicos",
                        arguments=lookup_filters,
                    )
                    elapsed = perf_counter() - tool_started_at
                    tool_duration += elapsed
                    tool_calls_count += 1
                    timing_events.append(
                        AgentTimingEvent(
                            step=len(timing_events) + 1,
                            stage="tool_execution",
                            name="search_politicos (fallback de integridade)",
                            duration_seconds=round(elapsed, 4),
                        )
                    )
                    trace.append(
                        AgentTraceEntry(
                            step=len(trace) + 1,
                            decision_summary=(
                                "O backend garantiu a consulta ao catálogo porque "
                                "o modelo tentou responder sem recuperar os registros."
                            ),
                            action="search_politicos",
                            arguments=lookup_filters,
                            observation=observation[:MAX_TRACE_OBSERVATION_LENGTH],
                            status=status,
                            duration_seconds=round(elapsed, 4),
                        )
                    )
                    logger.info(
                        "[AGENT TOOL] name=search_politicos args=%s status=%s duration=%.3fs source=fallback",
                        lookup_filters, status, elapsed,
                    )
                    if status == "success":
                        try:
                            successful_politico_payload = json.loads(observation)
                        except json.JSONDecodeError:
                            successful_politico_payload = None
                        self._capture_sources(observation, captured_sources)
                    if successful_politico_payload is not None:
                        return self._build_result(
                            question=question,
                            answer=_format_politicos_answer(successful_politico_payload),
                            started_at=started_at,
                            llm_duration=llm_duration,
                            tool_duration=tool_duration,
                            tool_calls_count=tool_calls_count,
                            blocked_tool_calls=blocked_tool_calls,
                            tool_limit_reached=False,
                            trace=trace,
                            timing_events=timing_events,
                            sources=list(captured_sources.values()),
                        )

                answer = self._content_to_text(
                    response.content
                )
                
                response_metadata = (
                    getattr(response, "response_metadata", {}) or {}
                )

                usage_metadata = (
                    getattr(response, "usage_metadata", {}) or {}
                )

                additional_kwargs = (
                    getattr(response, "additional_kwargs", {}) or {}
                )

                logger.info(
                    "Diagnóstico da resposta final: "
                    "content_type=%s | "
                    "content_length=%s | "
                    "finish_reason=%s | "
                    "done_reason=%s | "
                    "stop_reason=%s | "
                    "prompt_tokens=%s | "
                    "generated_tokens=%s | "
                    "additional_kwargs_keys=%s",
                    type(response.content).__name__,
                    len(answer),
                    response_metadata.get("finish_reason"),
                    response_metadata.get("done_reason"),
                    response_metadata.get("stop_reason"),
                    response_metadata.get("prompt_eval_count")
                    or usage_metadata.get("input_tokens"),
                    response_metadata.get("eval_count")
                    or usage_metadata.get("output_tokens"),
                    list(additional_kwargs.keys()),
                )

                logger.debug(
                    "Resposta final recebida: %r",
                    answer
                )
            
                if not answer:
                    content = getattr(
                        response,
                        "content",
                        None
                    )

                    additional_kwargs = (
                        getattr(
                            response,
                            "additional_kwargs",
                            {}
                        ) or {}
                    )

                    response_metadata = (
                        getattr(
                            response,
                            "response_metadata",
                            {}
                        ) or {}
                    )

                    content_shape = (
                        [
                            type(item).__name__
                            for item in content
                        ]
                        if isinstance(content, list)
                        else type(content).__name__
                    )

                    invalid_tool_calls = (
                        getattr(
                            response,
                            "invalid_tool_calls",
                            []
                        ) or []
                    )

                    logger.warning(
                        "LLM retornou resposta sem texto: "
                        "content_type=%s | "
                        "content_length=%s | "
                        "content_shape=%s | "
                        "tool_calls=%s | "
                        "invalid_tool_calls=%s | "
                        "additional_kwargs_keys=%s | "
                        "response_metadata_keys=%s | "
                        "finish_reason=%s | "
                        "done_reason=%s",
                        type(content).__name__,
                        len(content) if isinstance(
                            content,
                            (str, list)
                        ) else None,
                        content_shape,
                        len(requested_calls),
                        len(invalid_tool_calls),
                        list(additional_kwargs.keys()),
                        list(response_metadata.keys()),
                        response_metadata.get(
                            "finish_reason"
                        ),
                        response_metadata.get(
                            "done_reason"
                        ),
                    )

                if not answer:
                    answer = (
                        "Não consegui produzir uma resposta "
                        "com as informações disponíveis."
                    )

                return self._build_result(
                    question=question,
                    answer=answer,
                    started_at=started_at,
                    llm_duration=llm_duration,
                    tool_duration=tool_duration,
                    tool_calls_count=tool_calls_count,
                    blocked_tool_calls=blocked_tool_calls,
                    tool_limit_reached=False,
                    trace=trace,
                    timing_events=timing_events,
                    sources=list(captured_sources.values()),
                )

            # --------------------------------------------------
            # 3. Execução das ferramentas
            # --------------------------------------------------

            for call in requested_calls:

                tool_name = str(
                    call.get("name") or "unknown_tool"
                )

                arguments = call.get("args") or {}

                tool_call_id = (
                    call.get("id")
                    or f"react-{turn}-{len(trace) + 1}"
                )

                authorization_error = get_tool_authorization_error(
                    user_question=question,
                    tool_name=tool_name,
                )

                if authorization_error is not None:

                    blocked_tool_calls += 1

                    observation = self._controlled_error(
                        tool_name,
                        authorization_error,
                    )

                    status = "blocked"
                    elapsed = 0.0

                    timing_events.append(
                        AgentTimingEvent(
                            step=len(timing_events) + 1,
                            stage="tool_unauthorized",
                            name=tool_name,
                            duration_seconds=0.0,
                        )
                    )

                elif tool_calls_count >= self._max_tool_calls:

                    blocked_tool_calls += 1

                    observation = self._controlled_error(
                        tool_name,
                        (
                            "Limite máximo de chamadas atingido. "
                            "A ferramenta não foi executada."
                        ),
                    )

                    status = "blocked"
                    elapsed = 0.0

                    timing_events.append(
                        AgentTimingEvent(
                            step=len(timing_events) + 1,
                            stage="tool_blocked",
                            name=tool_name,
                            duration_seconds=0.0,
                        )
                    )

                else:

                    tool_calls_count += 1

                    tool_started_at = perf_counter()

                    observation, status = self._execute_tool(
                        tool_name=tool_name,
                        arguments=arguments,
                    )

                    elapsed = perf_counter() - tool_started_at

                    tool_duration += elapsed

                    timing_events.append(
                        AgentTimingEvent(
                            step=len(timing_events) + 1,
                            stage="tool_execution",
                            name=tool_name,
                            duration_seconds=round(elapsed, 4),
                        )
                    )

                if status == "success":
                    self._capture_sources(
                        observation,
                        captured_sources,
                    )
                    if tool_name == "search_politicos":
                        try:
                            parsed_observation = json.loads(observation)
                            if (
                                isinstance(parsed_observation, dict)
                                and parsed_observation.get("ok") is True
                            ):
                                successful_politico_payload = parsed_observation
                        except json.JSONDecodeError:
                            successful_politico_payload = None

                logger.info(
                    "[AGENT TOOL] name=%s args=%s status=%s duration=%.3fs",
                    tool_name, arguments, status, elapsed,
                )

                decision_summary = AGENT_DECISIONS.get(
                    tool_name,
                    "O modelo solicitou uma ferramenta não reconhecida.",
                )

                trace.append(
                    AgentTraceEntry(
                        step=len(trace) + 1,
                        decision_summary=decision_summary,
                        action=tool_name,
                        arguments=(
                            arguments
                            if isinstance(arguments, dict)
                            else {}
                        ),
                        observation=observation[
                            :MAX_TRACE_OBSERVATION_LENGTH
                        ],
                        status=status,
                        duration_seconds=round(
                            elapsed,
                            4,
                        ),
                    )
                )

                wrapped_observation = self._wrap_untrusted_observation(
                    tool_name=tool_name,
                    observation=observation,
                )

                messages.append(
                    ToolMessage(
                        content=wrapped_observation,
                        tool_call_id=str(tool_call_id),
                        name=tool_name,
                    )
                )

            # Dados de representantes são apresentados a partir do JSON da
            # ferramenta, sem uma segunda geração livre que possa inventar nomes.
            if successful_politico_payload is not None:
                return self._build_result(
                    question=question,
                    answer=_format_politicos_answer(successful_politico_payload),
                    started_at=started_at,
                    llm_duration=llm_duration,
                    tool_duration=tool_duration,
                    tool_calls_count=tool_calls_count,
                    blocked_tool_calls=blocked_tool_calls,
                    tool_limit_reached=False,
                    trace=trace,
                    timing_events=timing_events,
                    sources=list(captured_sources.values()),
                )

            # --------------------------------------------------
            # 4. Verificação do limite de chamadas
            # --------------------------------------------------

            if (
                tool_calls_count >= self._max_tool_calls
                or blocked_tool_calls > 0
            ):
                return self._make_final_response(
                    messages=messages,
                    question=question,
                    started_at=started_at,
                    llm_duration=llm_duration,
                    tool_duration=tool_duration,
                    tool_calls_count=tool_calls_count,
                    blocked_tool_calls=blocked_tool_calls,
                    trace=trace,
                    timing_events=timing_events,
                    sources=list(captured_sources.values()),
                    tool_limit_reached=(
                        tool_calls_count >= self._max_tool_calls
                    ),
                )

        raise AgentExecutionError(
            
            "O agente encerrou o ciclo sem produzir uma resposta."
            
        )


def build_react_agent(
    provider: str = "local",
    settings: "Settings | None" = None,
    top_k: int = 48,
    candidate_k: int = 120,
    lexical_candidate_k: int = 120,
    rrf_constant: int = 60,
    collection_name: str = "constituicao_legal_clean_v2",
    legal_tree_path: str | Path | None = None,
    prompt_task: str = "react_agent",
    max_tool_calls: int = MAX_TOOL_CALLS,
    enable_reranker: bool = True,
    rerank_top_k: int = 8,
) -> tuple[PolitizeseReActAgent, str]:
    """Inicializa retriever, ferramentas e modelo do agente."""

    from src.ai.llm_factory import create_agent_chat_model
    from src.ai.prompt_loader import load_prompt
    from src.rag.iterative_retriever import (
        build_iterative_retriever,
    )

    iterative_retriever, selected_provider = (
        build_iterative_retriever(
            provider=provider,
            top_k=top_k,
            candidate_k=candidate_k,
            lexical_candidate_k=lexical_candidate_k,
            rrf_constant=rrf_constant,
            settings=settings,
            collection_name=collection_name,
            legal_tree_path=legal_tree_path,
            enable_reranker=enable_reranker,
            rerank_top_k=rerank_top_k,
            reranker_device="cpu",
        )
    )
    

    toolbox = build_politizese_toolbox(
        iterative_retriever
    )

    # ChatOpenAI conversa com o endpoint compatível local do Ollama (/v1).
    # A troca é importante para que as definições das ferramentas cheguem
    # corretamente ao Qwen 3.5 e ao restante do agente ReAct.
    llm = create_agent_chat_model(settings=settings)

    system_prompt = load_prompt(
        task=prompt_task
    )

    agent = PolitizeseReActAgent(
        llm=llm,
        toolbox=toolbox,
        system_prompt=system_prompt,
        max_tool_calls=max_tool_calls,
        prompt_task=prompt_task,
    )

    return agent, selected_provider
