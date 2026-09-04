"""Interface de chat do assistente da Empório da Música.  Rode:  streamlit run app.py"""
import socket
import uuid
from urllib.parse import urlparse

import streamlit as st
from langchain_core.messages import AIMessage, HumanMessage

from agent import build_agent, responder
from config import MODEL, OPENAI_BASE_URL

st.set_page_config(page_title="melodIA — Empório da Música", page_icon="🎸")


def _md(texto: str) -> str:
    """Escapa o cifrão antes de renderizar. O markdown do Streamlit trata `$...$` como
    LaTeX, e um preço por linha já basta para engolir o texto ("R$ 2.199 ... R$ 2.089"
    vira fórmula). Escapar em `_brl()` não serve: o `\\$` iria junto para o modelo."""
    return texto.replace("$", "\\$")


@st.cache_resource
def _agente():
    return build_agent()


def _lm_studio_no_ar() -> bool:
    u = urlparse(OPENAI_BASE_URL)
    try:
        with socket.create_connection((u.hostname, u.port or 80), timeout=1):
            return True
    except OSError:
        return False


def _historico(agente, thread_id: str) -> list:
    """Mensagens já persistidas para este thread (para retomar conversa após reabrir o app)."""
    estado = agente.get_state({"configurable": {"thread_id": thread_id}})
    msgs = estado.values.get("messages", []) if estado.values else []
    return [("user" if isinstance(m, HumanMessage) else "assistant", m.content)
            for m in msgs if isinstance(m, (HumanMessage, AIMessage)) and m.content]


st.title("🎸 melodIA · Empório da Música")
st.caption("Sua música começa aqui. — assistente virtual de atendimento")

if "thread_id" not in st.session_state:
    st.session_state.thread_id = "streamlit-demo"

with st.sidebar:
    st.subheader("Sessão")
    st.text(f"modelo: {MODEL}")
    st.text(f"servidor: {OPENAI_BASE_URL}")
    novo = st.text_input("thread_id (reabra o mesmo id para retomar a conversa)",
                         value=st.session_state.thread_id)
    if novo != st.session_state.thread_id:
        st.session_state.thread_id = novo
        st.session_state.pop("messages", None)
        st.rerun()
    if st.button("Nova conversa"):
        st.session_state.thread_id = f"chat-{uuid.uuid4().hex[:8]}"
        st.session_state.pop("messages", None)
        st.rerun()

if not _lm_studio_no_ar():
    st.warning(
        f"Não consegui falar com o LM Studio em {OPENAI_BASE_URL}. "
        "Abra o LM Studio, carregue um modelo com suporte a *tool use* e clique em "
        "**Start Server**. Ajuste `MODEL` no `.env` para o id do modelo carregado."
    )

agente = _agente()

if "messages" not in st.session_state:
    st.session_state.messages = _historico(agente, st.session_state.thread_id)

for papel, texto in st.session_state.messages:
    st.chat_message(papel).write(_md(texto))

if pergunta := st.chat_input("Como podemos ajudar?"):
    st.session_state.messages.append(("user", pergunta))
    st.chat_message("user").write(_md(pergunta))
    with st.chat_message("assistant"), st.spinner("consultando..."):
        try:
            resposta = responder(agente, pergunta, st.session_state.thread_id)
        except Exception as e:  # LM Studio caiu no meio, modelo sem tool use, etc.
            resposta = f"Ops, tive um problema para responder agora ({type(e).__name__}). Tente de novo."
        st.write(_md(resposta))
    st.session_state.messages.append(("assistant", resposta))
