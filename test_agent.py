"""Checks assert-based, sem framework. Rode:  python test_agent.py

Cobre a lógica não-trivial: views do ETL, retrieval de política e as tools de dados
(incluindo a verificação leve de identidade). Não exercita o LLM.
"""
import sqlite3

from config import DB_PATH
from tools import buscar_produtos, consultar_politica, detalhe_produto, status_pedido


def test_etl_views():
    conn = sqlite3.connect(DB_PATH)
    q = lambda sql, *a: conn.execute(sql, a).fetchone()

    assert q("SELECT COUNT(*) FROM products")[0] == 65
    assert q("SELECT COUNT(*) FROM orders")[0] == 20
    assert q("SELECT COUNT(*) FROM customers")[0] == 50

    # Takamine GD20 = R$ 2199 tabela, sem promo, PIX = -5%
    row = q("SELECT preco_tabela, promo_ativa_pct, preco_a_vista_pix FROM v_produto WHERE product_id=95")
    assert row == (2199.0, None, 2089.05), row

    # Produto 96: active mas estoque 0 -> indisponível
    assert q("SELECT disponivel FROM v_produto WHERE product_id=96")[0] == 0

    # Produto 127: promo 10% ativa. Preço promocional aplicado e PIX NÃO acumula os 5%.
    row = q("SELECT preco_tabela, promo_ativa_pct, preco_promocional, preco_a_vista_pix "
            "FROM v_produto WHERE product_id=127")
    assert row == (359.0, 10, 323.1, 323.1), row

    # discontinued / coming_soon não contam como disponíveis
    assert q("SELECT disponivel FROM v_produto WHERE product_id=113")[0] == 0  # discontinued
    assert q("SELECT disponivel FROM v_produto WHERE product_id=130")[0] == 0  # coming_soon

    assert q("SELECT COUNT(*) FROM v_produto WHERE disponivel=1")[0] == 61
    assert q("SELECT COUNT(*) FROM v_produto WHERE promo_ativa_pct IS NOT NULL")[0] == 4

    conn.close()


def test_consultar_politica():
    call = lambda t: consultar_politica.invoke({"topico": t})

    assert call("me arrependi da compra, posso devolver?").startswith("## 4."), "arrependimento -> seção 4"
    assert call("que horas a loja abre no sábado?").startswith("## 2."), "horário -> seção 2"
    assert call("vocês vendem cordas de violão?").startswith("## 1."), "escopo/acessório -> seção 1"
    assert call("quais as formas de pagamento?").startswith("## 3."), "pagamento -> seção 3"
    assert call("como rastreio meu envio?").startswith("## 5."), "rastreamento -> seção 5"
    assert call("qual a garantia do instrumento?").startswith("## 8."), "garantia -> seção 8 (não 4)"

    # tópico não reconhecido -> mensagem de ajuda, não exceção
    assert "Assuntos cobertos" in call("qual a cor favorita do vendedor?")


def test_buscar_produtos():
    r = buscar_produtos.invoke({"categoria": "violão", "preco_max": 1000})
    assert "Tagima Memphis AC-39" in r          # 429,90 disponível
    assert "Martin D-28" not in r               # 11.499 fora da faixa
    assert "Giannini GF-3D Dreadnought" not in r  # produto 96: sem estoque

    # sem o filtro de disponibilidade, o item sem estoque aparece marcado
    r2 = buscar_produtos.invoke({"termo": "Giannini GF-3D", "apenas_disponiveis": False})
    assert "GF-3D" in r2 and "SEM ESTOQUE" in r2

    r3 = buscar_produtos.invoke({"termo": "nylon", "categoria": "ukulele", "preco_max": 300})
    assert "Kala KA-15S" in r3

    # "existe mas indisponível" não pode virar "não existe" (o agente dizia "não está no
    # catálogo", o que é falso) — e o inexistente continua sendo inexistente.
    r4 = buscar_produtos.invoke({"termo": "Giannini GF-3D Dreadnought Sunburst"})
    assert "EXISTE no catálogo" in r4 and "SEM ESTOQUE" in r4
    assert "Não encontrei" in buscar_produtos.invoke({"termo": "Xurupita"})

    # a faixa de preço vale sobre o preço EFETIVO: o Ohana CK-20 (tabela 549, -20% = 439,20)
    # tem que caber em "até R$ 500"
    r5 = buscar_produtos.invoke({"categoria": "ukulele", "preco_max": 500})
    assert "Ohana CK-20" in r5 and "439,20" in r5

    # categoria que o manual cita mas está sem produtos (6/7/8): dizer isso, não listar outra
    r6 = buscar_produtos.invoke({"categoria": "saxofone"})
    assert "Sopro" in r6 and "Ukulele" not in r6 and "Violão" not in r6

    # categoria desconhecida: recusar em vez de descartar o filtro em silêncio (dava 20 ukuleles)
    assert "Não conheço a categoria" in buscar_produtos.invoke({"categoria": "fender"})


def test_detalhe_produto():
    r = detalhe_produto.invoke({"nome_ou_id": "Takamine GD20"})
    assert "R$ 2.199,00" in r and "PIX" in r and "R$ 2.089,05" in r
    assert "Promoção ativa: nenhuma" in r  # GD20 não tem promo — não confundir com PIX

    # promoção ativa (produto 127) mostra preço promocional
    r2 = detalhe_produto.invoke({"nome_ou_id": "127"})
    assert "-10%" in r2 and "R$ 323,10" in r2

    # ambiguidade -> lista de candidatos, não uma ficha
    r3 = detalhe_produto.invoke({"nome_ou_id": "Yamaha"})
    assert "mais de um produto" in r3


def test_status_pedido():
    # pedido 5: cliente 5 = Rafael Augusto Pereira / rafael.pereira@jmail.com, feito em 2026-01-05
    ok = status_pedido.invoke({"order_id": 5, "identificador": "Rafael Pereira"})
    assert "entregue" in ok and "há 79 dias" in ok  # ref = 2026-03-25

    ok_email = status_pedido.invoke({"order_id": 5, "identificador": "rafael.pereira@jmail.com"})
    assert "Pedido 5" in ok_email

    # policies.md §4.1 conta os 7 dias do RECEBIMENTO, não da compra, e o dataset não tem
    # essa data. A tool precisa dizer isso — senão o agente compara com o relógio errado.
    assert "dias da compra" in ok and "não registra a data de recebimento" in ok.lower()

    nao = status_pedido.invoke({"order_id": 5, "identificador": "Fulano de Tal"})
    assert "não posso liberar" in nao

    assert "Não encontrei" in status_pedido.invoke({"order_id": 999, "identificador": "x"})


def test_identidade_nao_burlavel():
    from tools import _identidade_confere

    # token isolado (substring / 1 palavra) não libera
    assert "não posso liberar" in status_pedido.invoke({"order_id": 6, "identificador": "santos"})
    assert "não posso liberar" in status_pedido.invoke({"order_id": 11, "identificador": "ana"})
    # nome + sobrenome reais continuam liberando (por nome e por e-mail)
    assert "Pedido 6" in status_pedido.invoke({"order_id": 6, "identificador": "Gabriel Santos"})
    assert "Pedido 5" in status_pedido.invoke({"order_id": 5, "identificador": "Rafael Pereira"})

    conn = sqlite3.connect(DB_PATH)
    clientes = conn.execute("SELECT name, email FROM customers").fetchall()
    conn.close()

    # ataque 1: primeiro nome repetido ("Ana Ana")
    for nome, email in clientes:
        p = nome.split()[0]
        assert not _identidade_confere(f"{p} {p}", nome, email), f"'{p} {p}' burlou {nome}"

    # ataque 2: string única com dezenas de nomes/sobrenomes comuns, conhecimento zero
    spray = ("ana maria jose pedro joao lucas rafael bruno gabriel thiago diego marcelo "
             "felipe mariana juliana camila fernanda patricia leticia amanda beatriz larissa "
             "silva santos costa souza oliveira pereira lima ferreira rodrigues almeida araujo "
             "carvalho ribeiro martins gomes dias nunes cardoso mendes barbosa")
    for nome, email in clientes:
        assert not _identidade_confere(spray, nome, email), f"spray burlou {nome}"

    # ataque 3: sobrenomes isolados, cada pedido
    for sobren in "santos silva costa souza oliveira pereira lima ferreira".split():
        for oid in range(1, 21):
            assert "não posso liberar" in status_pedido.invoke({"order_id": oid, "identificador": sobren})

    # resíduo conhecido e LIMITADO: nome real de um cliente pode ser subconjunto do de
    # outro ("Bruno Carvalho" ⊂ "Bruno Carvalho Martins"). Não é ataque cego. O teste
    # garante que não passa de um punhado — se disparar, algum bug de agregação voltou.
    cruzadas = sum(
        1 for a in clientes for b in clientes
        if a[0] != b[0] and _identidade_confere(a[0], b[0], b[1])
    )
    assert cruzadas <= 3, f"colisões cruzadas subiram para {cruzadas} — regressão de agregação"


def test_poda_historico():
    """Conversa longa não pode estourar a janela nem deixar ToolMessage órfã (a API recusa)."""
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

    from agent import _podar

    msgs = []
    for i in range(60):
        msgs.append(HumanMessage(f"pergunta {i} " + "blablabla " * 40))
        msgs.append(AIMessage("", tool_calls=[
            {"name": "buscar_produtos", "args": {"termo": "violao"}, "id": f"call{i}"}]))
        msgs.append(ToolMessage("resultado " * 200, tool_call_id=f"call{i}"))
        msgs.append(AIMessage("resposta ao cliente " * 40))

    podadas = _podar({"messages": msgs})["llm_input_messages"]
    assert 0 < len(podadas) < len(msgs), f"não podou: {len(podadas)} de {len(msgs)}"
    assert isinstance(podadas[0], HumanMessage), f"começa em {type(podadas[0]).__name__}"

    pedidas = {tc["id"] for m in podadas if isinstance(m, AIMessage) for tc in (m.tool_calls or [])}
    respondidas = {m.tool_call_id for m in podadas if isinstance(m, ToolMessage)}
    assert respondidas <= pedidas, f"ToolMessage órfã: {respondidas - pedidas}"


def test_agente_compila():
    """O grafo monta, as 4 tools ligam e o checkpointer cria as tabelas. Não chama o LLM."""
    from agent import build_agent
    from tools import TOOLS
    a = build_agent()
    assert a.__class__.__name__ == "CompiledStateGraph"
    assert len(TOOLS) == 4


TESTS = [test_etl_views, test_consultar_politica, test_buscar_produtos,
         test_detalhe_produto, test_status_pedido, test_identidade_nao_burlavel,
         test_poda_historico, test_agente_compila]


def main():
    failed = 0
    for t in TESTS:
        try:
            t()
            print(f"ok   {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} passaram")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
