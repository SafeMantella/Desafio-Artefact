"""ETL: os 6 CSVs de data/ -> emporio.db (tabelas limpas + views de conveniência).

Rode uma vez antes de usar o agente:  python build_db.py
Idempotente: recria as tabelas de dados a cada execução (não toca nas tabelas do
checkpointer do LangGraph, que ficam no mesmo arquivo).
"""
import sqlite3

import pandas as pd

from config import DATA_DIR, DB_PATH

# nome-no-banco -> sufixo do arquivo "desafio_tecnico_ai_eng - <sufixo>.csv"
CSVS = {
    "categories": "categories",
    "customers": "customers",
    "products": "products",
    "orders": "orders",
    "order_items": "order_items",
    "promotions": "promotions",
}

# Views. A regra de negócio explícita aqui:
#  - promo ativa por produto = MAIOR desconto entre as linhas is_active=1 (promotions.csv
#    tem produtos com várias linhas; política 6.2: não cumulativas).
#  - preço à vista no PIX: 5% sobre a tabela, MAS não incide sobre preço já promocional
#    (política 6.2). Então: se há promo -> preço à vista = preço promocional; senão -> -5%.
#  - disponível = status 'active' E estoque > 0 (há 'active' com estoque 0, ex. produto 96).
VIEWS = {
    "v_produto": """
        CREATE VIEW v_produto AS
        SELECT
            p.product_id,
            p.name,
            p.category_id,
            c.name AS categoria,
            p.status,
            p.stock_quantity,
            p.description,
            p.specs,
            ROUND(p.price_brl, 2)                         AS preco_tabela,
            pr.promo_pct                                  AS promo_ativa_pct,
            CASE WHEN pr.promo_pct IS NOT NULL
                 THEN ROUND(p.price_brl * (1 - pr.promo_pct / 100.0), 2)
            END                                          AS preco_promocional,
            CASE WHEN pr.promo_pct IS NOT NULL
                 THEN ROUND(p.price_brl * (1 - pr.promo_pct / 100.0), 2)
                 ELSE ROUND(p.price_brl * 0.95, 2)
            END                                          AS preco_a_vista_pix,
            CASE WHEN p.status = 'active' AND p.stock_quantity > 0 THEN 1 ELSE 0 END
                                                         AS disponivel
        FROM products p
        LEFT JOIN categories c ON c.category_id = p.category_id
        LEFT JOIN (
            SELECT product_id, MAX(discount_percent) AS promo_pct
            FROM promotions WHERE is_active = 1 GROUP BY product_id
        ) pr ON pr.product_id = p.product_id
    """,
    "v_pedido_item": """
        CREATE VIEW v_pedido_item AS
        SELECT oi.order_id, oi.product_id, oi.quantity,
               p.name AS produto, ROUND(p.price_brl, 2) AS preco_tabela
        FROM order_items oi
        LEFT JOIN products p ON p.product_id = oi.product_id
    """,
}


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    try:
        for view in VIEWS:
            conn.execute(f"DROP VIEW IF EXISTS {view}")

        for table, suffix in CSVS.items():
            path = DATA_DIR / f"desafio_tecnico_ai_eng - {suffix}.csv"
            df = pd.read_csv(path)
            # strings vazias -> NULL (tracking_code, estimated_delivery, notes em orders)
            df = df.replace(r"^\s*$", None, regex=True)
            df.to_sql(table, conn, if_exists="replace", index=False)
            print(f"  {table:12s} {len(df):3d} linhas")

        for view, ddl in VIEWS.items():
            conn.execute(ddl)
        conn.commit()

        n_disp = conn.execute("SELECT COUNT(*) FROM v_produto WHERE disponivel = 1").fetchone()[0]
        n_promo = conn.execute("SELECT COUNT(*) FROM v_produto WHERE promo_ativa_pct IS NOT NULL").fetchone()[0]
        print(f"\n  v_produto: {n_disp} disponíveis, {n_promo} com promoção ativa")
        print(f"\nOK -> {DB_PATH}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
