"""Configuração central. Lida uma vez; importada por build_db.py, tools.py e agent.py."""
import os
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
DB_PATH = ROOT / "emporio.db"
POLICIES_PATH = ROOT / "policies.md"

# LM Studio expõe uma API compatível com a da OpenAI; o cliente da OpenAI/LangChain
# só precisa da base_url e de uma api_key qualquer (não vazia).
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "http://localhost:1234/v1")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "lm-studio")
MODEL = os.getenv("MODEL", "qwen2.5-7b-instruct")

# "Hoje" do agente — ver .env.example. O dataset é um snapshot (pedidos até 2026-03-22).
DATA_REFERENCE_DATE = date.fromisoformat(os.getenv("DATA_REFERENCE_DATE", "2026-03-25"))
