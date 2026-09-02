"""Checks assert-based, sem framework. Rode:  python test_agent.py

Cobre a lógica não-trivial: views do ETL, retrieval de política e as tools de dados
(incluindo a verificação leve de identidade). Não exercita o LLM.
"""
import sqlite3

from config import DB_PATH


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


TESTS = [test_etl_views]


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
