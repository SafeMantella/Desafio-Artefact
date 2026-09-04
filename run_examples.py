"""Gera as conversas de exemplo em examples/ rodando o agente de verdade.

Precisa do LM Studio no ar. Rode:  python run_examples.py
Cada cenário roda numa thread nova; o transcript mostra as chamadas de ferramenta.
"""
import uuid

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agent import build_agent
from config import MODEL, ROOT

EXEMPLOS = [
    ("01_catalogo_violoes", "Busca no catálogo com filtro de preço", [
        "Oi! Quais opções de violão vocês têm disponíveis até R$ 1000?",
        "O Yamaha F310 tem alguma promoção?",
    ]),
    ("02_preco_produto", "Consulta de preço de um produto específico", [
        "Quanto custa o Takamine GD20?",
        "E se eu pagar no pix?",
    ]),
    ("03_info_loja", "Informações gerais da loja (políticas)", [
        "Qual o endereço da loja e que horas vocês abrem no sábado?",
        "Vocês parcelam no cartão?",
    ]),
    # O cenário não trivial, em quatro atos: o prazo de arrependimento (§4.1) conta do
    # RECEBIMENTO, e o sistema não tem essa data. O agente precisa recusar a identificação
    # por nome (só e-mail exato libera PII), conferir a identidade, ler a política, perceber
    # qual relógio usar e PERGUNTAR ao cliente quando ele recebeu.
    ("04_devolucao_pedido", "NÃO TRIVIAL: devolução aplicando política + dados do pedido", [
        "Comprei um ukulele aí e me arrependi. É o pedido 7, consigo devolver?",
        "Letícia Gonçalves Rocha",          # nome não libera: a tool exige o e-mail
        "leticia.rocha@jmail.com",
        "Recebi ele ontem.",
    ]),
    # O fluxo de abertura da §7.2: convida a identificação sem exigir, reconhece o cliente
    # pelo primeiro nome, usa a cidade dele para o frete e oferece o pedido em trânsito.
    ("06_cliente_identificado", "Identificação opcional na abertura + atendimento personalizado", [
        "Oi! Meu e-mail é anacarol.ferreira@coldmail.com",
        "Queria ver uma bateria acústica.",
        "Quanto fica a mais barata parcelada, com frete?",
    ]),
    ("05_fora_de_escopo", "Fora do escopo: acessório e pergunta aleatória", [
        "Vocês vendem cordas de violão?",
        "Beleza. E me passa uma receita de bolo de chocolate?",
    ]),
]


def _rotulo(m) -> str:
    if isinstance(m, HumanMessage):
        return f"**Cliente:** {m.content.strip()}"
    if isinstance(m, ToolMessage):
        corpo = m.content if len(m.content) <= 1000 else m.content[:1000] + " […]"
        return f"> 🔧 `{m.name}` →\n>\n> " + corpo.strip().replace("\n", "\n> ")
    if isinstance(m, AIMessage):
        linhas = [
            f"> 🔧 chama `{tc['name']}({', '.join(f'{k}={v!r}' for k, v in tc['args'].items())})`"
            for tc in (m.tool_calls or [])
        ]
        conteudo = (m.content or "").strip()
        if conteudo:
            linhas.append(f"**Assistente:** {conteudo}")
        return "\n\n".join(linhas)
    return ""


def main() -> None:
    agente = build_agent()
    out = ROOT / "examples"
    out.mkdir(exist_ok=True)
    for slug, descricao, turnos in EXEMPLOS:
        thread = f"ex-{slug}-{uuid.uuid4().hex[:6]}"
        vistas = 0
        blocos = [f"# {descricao}\n", f"_Modelo: {MODEL}. Gerado por `run_examples.py`._\n"]
        for turno in turnos:
            estado = agente.invoke({"messages": [("user", turno)]},
                                   config={"configurable": {"thread_id": thread}})
            msgs = estado["messages"]
            for m in msgs[vistas:]:
                # `$` escapado: o GitHub e o Streamlit leem `$...$` como LaTeX, e os
                # transcripts têm dois preços por linha. Vale para o texto do assistente
                # e para o retorno das ferramentas, que também vem com "R$".
                bloco = _rotulo(m).replace("$", "\\$")
                if bloco:
                    blocos.append(bloco)
            vistas = len(msgs)
        (out / f"{slug}.md").write_text("\n\n".join(blocos) + "\n", encoding="utf-8")
        print(f"  examples/{slug}.md")
    print("\nOK — revise os transcripts antes de commitar.")


if __name__ == "__main__":
    main()
