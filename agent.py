"""Monta o agente ReAct (LangChain + LangGraph) ligado ao LM Studio.

Uso como módulo:   from agent import build_agent
REPL de teste:     python agent.py        (precisa do LM Studio rodando)
"""
import sqlite3
import uuid

from langchain_openai import ChatOpenAI
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.prebuilt import create_react_agent

from config import DB_PATH, MODEL, OPENAI_API_KEY, OPENAI_BASE_URL
from prompts import system_prompt
from tools import TOOLS


def build_agent():
    """Retorna o agente compilado. O histórico é persistido em emporio.db por thread_id."""
    llm = ChatOpenAI(
        base_url=OPENAI_BASE_URL,
        api_key=OPENAI_API_KEY,
        model=MODEL,
        temperature=0.3,
        timeout=120,
    )
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    checkpointer = SqliteSaver(conn)
    checkpointer.setup()
    return create_react_agent(llm, TOOLS, prompt=system_prompt(), checkpointer=checkpointer)


def responder(agente, mensagem: str, thread_id: str) -> str:
    """Uma rodada de conversa. Devolve o texto da última mensagem do assistente."""
    estado = agente.invoke(
        {"messages": [("user", mensagem)]},
        config={"configurable": {"thread_id": thread_id}},
    )
    return estado["messages"][-1].content


if __name__ == "__main__":
    print(f"Empório da Música — assistente (modelo: {MODEL} @ {OPENAI_BASE_URL})")
    print("Digite 'sair' para encerrar.\n")
    agente = build_agent()
    thread = f"cli-{uuid.uuid4().hex[:8]}"
    while True:
        try:
            msg = input("você> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if msg.lower() in {"sair", "exit", "quit"}:
            break
        if msg:
            print(f"\nassistente> {responder(agente, msg, thread)}\n")
