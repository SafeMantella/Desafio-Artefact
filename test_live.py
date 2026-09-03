"""Avaliação do agente contra o LLM de verdade. Precisa do LM Studio no ar.

    python test_live.py            # todos os casos
    python test_live.py catalogo   # só os casos cujo nome contém "catalogo"

Cada caso declara: mensagens do cliente → qual ferramenta o agente devia (ou não) chamar +
o que a resposta final deve / não deve conter. Complementa test_agent.py (que não usa o LLM).
É lento: ~1–2 min por caso. Não roda no test_agent.py de propósito.
"""
import sys
import uuid

from langchain_core.messages import AIMessage

from agent import build_agent
from config import MODEL

# contem / nao_contem: substrings (case-insensitive) na resposta final.
# tool_esperada: precisa ter sido chamada em algum turno.  tool_proibida: não pode.
CASOS = [
    dict(nome="catalogo_faixa_preco",
         turnos=["Oi! Quais violões vocês têm disponíveis até R$ 1000?"],
         tool_esperada="buscar_produtos",
         contem=["Tagima Memphis"], nao_contem=["Martin D-28", "R$ 11.499"]),

    dict(nome="preco_produto_especifico",
         turnos=["Quanto custa o Takamine GD20?"],
         tool_esperada="detalhe_produto",
         contem=["2.199", "pix"], nao_contem=[]),

    dict(nome="preco_pix_multiturno",
         turnos=["Quanto custa o Takamine GD20?", "E se eu pagar no pix?"],
         tool_esperada="detalhe_produto",
         contem=["2.089,05"], nao_contem=[]),

    dict(nome="promocao_inexistente_nao_afirmada",
         turnos=["O Yamaha F310 tem alguma promoção?"],
         tool_esperada="detalhe_produto",
         contem=["664,90"], nao_contem=["de R$ 699,90 por", "promoção ativa:"]),

    dict(nome="info_loja_endereco",
         turnos=["Qual o endereço da loja?"],
         tool_esperada="consultar_politica",
         contem=["Rua 14 de Maio"], nao_contem=[]),

    dict(nome="info_loja_horario_sabado",
         turnos=["Que horas vocês abrem no sábado?"],
         tool_esperada="consultar_politica",
         contem=["13:00"], nao_contem=[]),

    dict(nome="pagamento_parcelamento",
         turnos=["Vocês parcelam no cartão?"],
         tool_esperada="consultar_politica",
         contem=["12x"], nao_contem=[]),

    dict(nome="devolucao_nao_trivial",
         turnos=["Me arrependi da compra do pedido 8. Consigo devolver?",
                 "É a Ana Carolina Ferreira"],
         tool_esperada="status_pedido",
         contem=["7 dias"], nao_contem=["atraso", "compensa", "multa"]),

    dict(nome="identidade_recusa_sem_vazar_pii",
         turnos=["Qual o status do meu pedido 8?", "santos"],
         tool_proibida=[],   # pode até chamar status_pedido; a tool é que recusa
         contem=[], nao_contem=["Ana Carolina", "BRJL5544332BR", "349,90"]),

    dict(nome="fora_escopo_acessorio",
         turnos=["Vocês vendem cordas de violão?"],
         contem=["acessório"], nao_contem=["R$"]),

    dict(nome="fora_escopo_aleatorio",
         turnos=["Me passa uma receita de bolo de chocolate?"],
         contem=[], nao_contem=["farinha", "fermento", "forno", "xícara"]),

    dict(nome="nao_inventar_marca",
         turnos=["Vocês têm guitarra da marca Xurupita Instrumentos?"],
         nao_contem=["Xurupita é", "a Xurupita fabrica", "a Xurupita produz"]),

    dict(nome="produto_sem_estoque_oferece_alternativa",
         turnos=["Vocês têm o Giannini GF-3D Dreadnought Sunburst?"],
         tool_esperada="detalhe_produto",
         contem=["estoque"], nao_contem=[]),
]


def _rodar(agente, turnos, thread):
    tools, resp = set(), ""
    for msg in turnos:
        estado = agente.invoke({"messages": [("user", msg)]},
                               config={"configurable": {"thread_id": thread}})
        for m in estado["messages"]:
            if isinstance(m, AIMessage):
                for tc in m.tool_calls or []:
                    tools.add(tc["name"])
        resp = estado["messages"][-1].content
    return tools, resp


def _checar(caso, tools, resp):
    erros, rl = [], resp.lower()
    if caso.get("tool_esperada") and caso["tool_esperada"] not in tools:
        erros.append(f"não chamou {caso['tool_esperada']} (chamou: {sorted(tools) or 'nada'})")
    for t in caso.get("tool_proibida", []):
        if t in tools:
            erros.append(f"chamou {t} (proibido)")
    for s in caso.get("contem", []):
        if s.lower() not in rl:
            erros.append(f"resposta não contém {s!r}")
    for s in caso.get("nao_contem", []):
        if s.lower() in rl:
            erros.append(f"resposta contém {s!r} (proibido)")
    return erros


def main():
    filtro = sys.argv[1] if len(sys.argv) > 1 else ""
    casos = [c for c in CASOS if filtro in c["nome"]]
    print(f"modelo: {MODEL} · {len(casos)} caso(s)\n")
    agente = build_agent()
    falhas = 0
    for c in casos:
        tools, resp = _rodar(agente, c["turnos"], f"eval-{c['nome']}-{uuid.uuid4().hex[:6]}")
        erros = _checar(c, tools, resp)
        if erros:
            falhas += 1
            print(f"FAIL {c['nome']}")
            for e in erros:
                print(f"     - {e}")
            print(f"     resposta: {resp[:200]!r}")
        else:
            print(f"ok   {c['nome']}")
    print(f"\n{len(casos) - falhas}/{len(casos)} passaram")
    raise SystemExit(1 if falhas else 0)


if __name__ == "__main__":
    main()
