import os

from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables.history import RunnableWithMessageHistory
from src.chain.memoria import get_session_history
from langchain_ollama import ChatOllama


load_dotenv()


def load_system_prompt():
    nome_arquivo = os.getenv(
        "GURAI_SYSTEM_PROMPT",
        "system_prompt_v3.md",
    )

    caminho = os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "prompts",
        nome_arquivo,
    )

    with open(caminho, "r", encoding="utf-8") as arquivo:
        return arquivo.read()



def build_chain():

    system_prompt = load_system_prompt()

    prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            system_prompt
        ),
        (
            "placeholder",
            "{history}"
        ),
        (
            "human",
            """
            Contexto dos dados:
            {context}

            Pergunta do usuario:
            {question}
            """
        )
    ])

    llm = ChatOllama(
        model="gemma4:31b",
        base_url="https://ollama.com",
        client_kwargs={
            "headers": {
                "Authorization": f"Bearer {os.getenv('OLLAMA_API_KEY')}"
            }
        },
        temperature=0.3,
        num_predict=1200,
        top_p=0.9
    )

    parser = StrOutputParser()

    chain_completa = prompt | llm

    chain = prompt | llm | parser

    chain_com_memoria = RunnableWithMessageHistory(
        chain,
        get_session_history,
        input_messages_key="question",
        history_messages_key="history"
    )

    chain_completa_com_memoria = RunnableWithMessageHistory(
            chain_completa,
            get_session_history,
            input_messages_key="question",
            history_messages_key="history"
        )

    return chain_com_memoria, chain_completa_com_memoria


def build_structured_chain(schema, instrucoes):


    prompt = ChatPromptTemplate.from_messages([
        ("system", f"""
       ...........
        {instrucoes}
        """),
        (
            "human",
            """
            Contexto dos dados:
            {context}

            Pergunta do usuário:
            {question}
            """
        )
    ])

    llm = ChatOllama(
        model="gemma4:31b",
        base_url="https://ollama.com",
        client_kwargs={
            "headers": {
                "Authorization": f"Bearer {os.getenv('OLLAMA_API_KEY')}"
            }
        },
        temperature=0.3,
        num_predict=1200,
        top_p=0.9
    )

    structured_llm = llm.with_structured_output(schema)

    chain = prompt | structured_llm

    return chain