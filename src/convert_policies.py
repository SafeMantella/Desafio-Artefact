"""Converte data/políticas_da_loja.pdf -> policies_raw.md com pymupdf4llm.

policies_raw.md é o artefato bruto (versionado, reproduzível). A versão usada pelo agente
é policies.md, que parte deste resultado e recebe uma curadoria leve: headings sem **bold**,
rodapés de página removidos e as duas divergências do PDF resolvidas (ver cabeçalho de
policies.md). Rode:  python convert_policies.py
"""
import re

import pymupdf4llm

from config import DATA_DIR, ROOT

PDF = DATA_DIR / "políticas_da_loja.pdf"
OUT = ROOT / "docs" / "policies_raw.md"

_LIXO = re.compile(r"^(Página \d+|\*\*Empório da Música\*\* Manual de Políticas e Procedimentos)\s*$")


def _limpar(md: str) -> str:
    linhas = [ln.rstrip() for ln in md.splitlines() if not _LIXO.match(ln.strip())]
    md = "\n".join(linhas)
    md = re.sub(r"^(#{1,6})\s*\*\*(.+?)\*\*\s*$", r"\1 \2", md, flags=re.MULTILINE)  # de-bold headings
    md = re.sub(r"\n{3,}", "\n\n", md)
    return md.strip() + "\n"


def main() -> None:
    raw = pymupdf4llm.to_markdown(str(PDF))
    OUT.write_text(_limpar(raw), encoding="utf-8")
    print(f"OK -> {OUT}  ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
