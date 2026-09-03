"""Monta o agente ReAct (LangChain + LangGraph) ligado ao LM Studio.

Uso como módulo:   from agent import build_agent
REPL de teste:     python agent.py        (precisa do LM Studio rodando)
"""
import sqlite3
import time
import uuid

from langchain_core.messages.utils import count_tokens_approximately, trim_messages
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.prebuilt import create_react_agent

from config import DB_PATH, MAX_HISTORY_TOKENS, MODEL, OPENAI_API_KEY, OPENAI_BASE_URL, log
from prompts import system_prompt
from tools import TOOLS


def _podar(state: dict) -> dict:
    """Poda o histórico que vai para o LLM. O state persistido continua inteiro.

    Sem isso o create_react_agent reenvia a conversa toda a cada turno: com retorno de
    ferramenta de ~1k tokens (consultar_politica devolve até 3 seções), 10-15 turnos
    estouram a janela de um modelo local. `start_on="human"` garante que o corte não
    deixe uma ToolMessage órfã — a API recusa o request se isso acontecer.
    """
    return {"llm_input_messages": trim_messages(
        state["messages"],
        max_tokens=MAX_HISTORY_TOKENS,
        token_counter=count_tokens_approximately,
        strategy="last",
        start_on="human",
        include_system=True,
    )}


def build_agent():
    """Retorna o agente compilado. O histórico é persistido em emporio.db por thread_id."""
    llm = ChatOpenAI(
        base_url=OPENAI_BASE_URL,
        api_key=OPENAI_API_KEY,
        model=MODEL,
        temperature=0,   # eval reproduzível: a variação que sobrar é do modelo, não do sampler
        timeout=120,
    )
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    checkpointer = SqliteSaver(conn)
    checkpointer.setup()
    return create_react_agent(llm, TOOLS, prompt=system_prompt(), checkpointer=checkpointer,
                              pre_model_hook=_podar)


def responder(agente, mensagem: str, thread_id: str) -> str:
    """Uma rodada de conversa. Devolve o texto da última mensagem do assistente."""
    t0 = time.perf_counter()
    estado = agente.invoke(
        {"messages": [("user", mensagem)]},
        config={"configurable": {"thread_id": thread_id}},
    )
    log.info("turno thread=%s %.1fs (%d mensagens no histórico)",
             thread_id, time.perf_counter() - t0, len(estado["messages"]))
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
