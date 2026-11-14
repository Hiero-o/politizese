
import pytest
from langchain_core.messages import AIMessage

from src.agents.react_agent import (
    PolitizeseReActAgent,
)
from src.agents.tools import build_politizese_toolbox


class FakePipeline:
    """Pipeline mínimo para testar as ferramentas."""

    def __init__(self):
        self.base_retriever = object()
        self.rewriter = object()


class FakeLLM:
    """Modelo simulado que devolve mensagens previamente definidas."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.bound_tools = []
        self.received_messages = []

    def bind_tools(self, tools):
        self.bound_tools = tools
        return self

    def invoke(self, messages):
        self.received_messages.append(messages)

        if not self.responses:
            raise RuntimeError(
                "Não existem mais respostas simuladas."
            )

        return self.responses.pop(0)


def calculator_call(
    call_id="call-1",
    total=513,
    numerator=3,
    denominator=5,
):
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": "calculate_voting_threshold",
                "args": {
                    "total_members": total,
                    "numerator": numerator,
                    "denominator": denominator,
                },
                "id": call_id,
            }
        ],
    )


def create_agent(responses, max_tool_calls=6):
    llm = FakeLLM(responses)

    toolbox = build_politizese_toolbox(
        FakePipeline()
    )

    agent = PolitizeseReActAgent(
        llm=llm,
        toolbox=toolbox,
        system_prompt="Prompt de teste do agente.",
        max_tool_calls=max_tool_calls,
    )

    return agent, llm


def test_agent_returns_final_answer_without_tools():
    agent, _ = create_agent(
        [
            AIMessage(
                content="Resposta final simulada."
            )
        ]
    )

    result = agent.invoke(
        "Pergunta de teste."
    )

    assert result.answer == "Resposta final simulada."
    assert result.tool_calls_count == 0
    assert result.trace == []


def test_agent_executes_calculator_and_returns_observation():
    agent, llm = create_agent(
        [
            calculator_call(),
            AIMessage(
                content="São necessários 308 votos."
            ),
        ]
    )

    result = agent.invoke(
        "Quantos votos correspondem a três quintos de 513?"
    )

    assert result.answer == "São necessários 308 votos."
    assert result.tool_calls_count == 1

    assert len(result.trace) == 1

    trace = result.trace[0]

    assert trace.action == "calculate_voting_threshold"
    assert trace.status == "success"
    assert "308" in trace.observation

    assert len(llm.bound_tools) == 3
    
        # Métricas de execução.
    assert result.total_duration_seconds >= 0
    assert result.llm_duration_seconds >= 0
    assert result.tool_duration_seconds >= 0

    assert len(result.timing_events) == 3

    assert result.timing_events[0].stage == "tool_selection"
    assert result.timing_events[1].stage == "tool_execution"
    assert result.timing_events[2].stage == "final_answer"

    assert result.trace[0].duration_seconds >= 0


def test_agent_rejects_unknown_tool_without_crashing():
    invalid_call = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "delete_database",
                "args": {},
                "id": "invalid-1",
            }
        ],
    )

    agent, _ = create_agent(
        [
            invalid_call,
            AIMessage(content="Não foi possível executar a ferramenta."),
        ]
    )

    result = agent.invoke(
        "Pergunta de teste."
    )

    assert result.tool_calls_count == 1
    assert result.trace[0].status == "error"
    assert "não autorizada" in (
        result.trace[0].observation
    )


def test_agent_enforces_six_tool_call_limit():
    seven_calls = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "calculate_voting_threshold",
                "args": {
                    "total_members": 513,
                    "numerator": 3,
                    "denominator": 5,
                },
                "id": f"call-{index}",
            }
            for index in range(7)
        ],
    )

    agent, _ = create_agent(
        [
            seven_calls,
            AIMessage(
                content="Resposta após o limite de ferramentas."
            ),
        ]
    )

    result = agent.invoke(
        "Execute os cálculos necessários."
    )

    assert result.tool_calls_count == 6
    assert result.blocked_tool_calls == 1
    assert result.tool_limit_reached is True

    assert len(result.trace) == 7
    assert result.trace[-1].status == "blocked"


def test_agent_rejects_empty_question():
    agent, _ = create_agent([])

    with pytest.raises(
        ValueError,
        match="não pode estar vazia",
    ):
        agent.invoke("   ")


def test_agent_rejects_more_than_six_calls_in_configuration():
    toolbox = build_politizese_toolbox(
        FakePipeline()
    )

    with pytest.raises(
        ValueError,
        match="entre 1 e 6",
    ):
        PolitizeseReActAgent(
            llm=FakeLLM([]),
            toolbox=toolbox,
            system_prompt="Prompt de teste.",
            max_tool_calls=7,
        )
