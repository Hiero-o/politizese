
"""Agente ReAct do Politizese com métricas de desempenho."""

from __future__ import annotations

import json
import logging
from time import perf_counter
from typing import Any, TYPE_CHECKING

from langchain_core.messages import (
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from src.agents.agent_schemas import (
    AgentRunResult,
    AgentTimingEvent,
    AgentTraceEntry,
)
from src.agents.tools import (
    PolitizeseToolbox,
    build_politizese_toolbox,
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
            tool_limit_reached=True,
            trace=trace,
            timing_events=timing_events,
        )

    def invoke(self, question: str) -> AgentRunResult:
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

        messages = [
            SystemMessage(content=self._system_prompt),
            HumanMessage(content=question),
        ]

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
                answer = self._content_to_text(
                    response.content
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

                if tool_calls_count >= self._max_tool_calls:

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

                    # Toda chamada executada consome o orçamento.
                    tool_calls_count += 1

                    tool_started_at = perf_counter()

                    observation, status = self._execute_tool(
                        tool_name=tool_name,
                        arguments=arguments,
                    )

                    elapsed = (
                        perf_counter() - tool_started_at
                    )
                    

                    tool_duration += elapsed
                    

                    timing_events.append(
                        AgentTimingEvent(
                            step=len(timing_events) + 1,
                            stage="tool_execution",
                            name=tool_name,
                            duration_seconds=round(
                                elapsed,
                                4,
                            ),
                        )
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

                messages.append(
                    ToolMessage(
                        content=observation,
                        tool_call_id=str(tool_call_id),
                        name=tool_name,
                    )
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
    max_tool_calls: int = MAX_TOOL_CALLS,
) -> tuple[PolitizeseReActAgent, str]:
    """Inicializa retriever, ferramentas e modelo do agente."""

    from src.ai.llm_factory import create_chat_model
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
        )
    )
    

    toolbox = build_politizese_toolbox(
        iterative_retriever
    )

    llm = create_chat_model(
        settings=settings
    )

    llm = llm.model_copy(
        update={
            "reasoning": True,
            "num_ctx": 8192,
            "num_predict": 2048,
        }
    )

    system_prompt = load_prompt(
        task="react_agent"
    )

    agent = PolitizeseReActAgent(
        llm=llm,
        toolbox=toolbox,
        system_prompt=system_prompt,
        max_tool_calls=max_tool_calls,
    )

    return agent, selected_provider
