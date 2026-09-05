"""Configuração central. Lida uma vez; importada por build_db.py, tools.py e agent.py."""
import logging
import os
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
DB_PATH = ROOT / "emporio.db"
POLICIES_PATH = ROOT / "docs" / "policies.md"

# LM Studio expõe uma API compatível com a da OpenAI; o cliente da OpenAI/LangChain
# só precisa da base_url e de uma api_key qualquer (não vazia).
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "http://localhost:1234/v1")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "lm-studio")
MODEL = os.getenv("MODEL", "qwen/qwen3.5-9b")

# "Hoje" do agente — ver .env.example. O dataset é um snapshot (pedidos até 2026-03-22).
DATA_REFERENCE_DATE = date.fromisoformat(os.getenv("DATA_REFERENCE_DATE", "2026-03-25"))

# Teto do histórico enviado ao modelo a cada turno. O checkpointer guarda a conversa
# inteira; o que vai pro LLM é podado (ver agent._podar). Modelo local recomendado tem
# janela de 40k+ — o custo fixo do system prompt + schema das 7 tools já soma ~5,5k.
MAX_HISTORY_TOKENS = int(os.getenv("MAX_HISTORY_TOKENS", "32000"))

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"),
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("emporio")
