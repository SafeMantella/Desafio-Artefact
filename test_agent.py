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


def test_detalhe_produto():
    r = detalhe_produto.invoke({"nome_ou_id": "Takamine GD20"})
    assert "R$ 2.199,00" in r and "PIX" in r and "R$ 2.089,05" in r

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

    nao = status_pedido.invoke({"order_id": 5, "identificador": "Fulano de Tal"})
    assert "não posso liberar" in nao

    assert "Não encontrei" in status_pedido.invoke({"order_id": 999, "identificador": "x"})


def test_agente_compila():
    """O grafo monta, as 4 tools ligam e o checkpointer cria as tabelas. Não chama o LLM."""
    from agent import build_agent
    from tools import TOOLS
    a = build_agent()
    assert a.__class__.__name__ == "CompiledStateGraph"
    assert len(TOOLS) == 4


TESTS = [test_etl_views, test_consultar_politica, test_buscar_produtos,
         test_detalhe_produto, test_status_pedido, test_agente_compila]


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
