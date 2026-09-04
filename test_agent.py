"""Checks assert-based, sem framework. Rode:  python test_agent.py

Cobre a lógica não-trivial: views do ETL, retrieval de política e as tools de dados
(incluindo a verificação leve de identidade). Não exercita o LLM.
"""
import re
import sqlite3
import unicodedata
from datetime import date

from config import DATA_REFERENCE_DATE, DB_PATH, POLICIES_PATH, ROOT
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

    # dinheiro normalizado no ETL: o CSV mistura int e decimal, o banco não
    assert all(isinstance(v, float) for (v,) in conn.execute("SELECT price_brl FROM products"))
    assert all(isinstance(v, float) for (v,) in conn.execute("SELECT total_brl FROM orders"))
    assert q("SELECT price_brl FROM products WHERE product_id=95")[0] == 2199.0   # era int
    assert q("SELECT price_brl FROM products WHERE product_id=81")[0] == 599.90   # era decimal

    # ruído do dataset sintético: a descrição não pode citar marca diferente da do nome.
    # O build_db.py corrige as 6 linhas; aqui checamos o resultado, não a regra.
    for pid, marca_certa, marca_errada in ((135, "Music Man", "Fender"),
                                           (137, "Yamaha", "Ibanez"),
                                           (139, "Yamaha", "Pearl"),
                                           (140, "Pearl", "Tama"),
                                           (142, "Korg", "Roland"),
                                           (144, "Roland", "Yamaha")):
        desc = q("SELECT description FROM products WHERE product_id=?", pid)[0]
        assert marca_errada not in desc, f"produto {pid} ainda cita {marca_errada}"
        assert marca_certa in desc, f"produto {pid} perdeu a marca {marca_certa}"

    conn.close()


def test_policies_sem_perda():
    """policies.md é policies_raw.md curado à mão. Este check garante que a curadoria mexeu
    em forma (headings, rodapé, tabelas) e não em conteúdo: todo número, percentual, valor
    e e-mail do bruto tem que sobreviver no curado."""
    def duros(texto: str) -> set[str]:
        t = unicodedata.normalize("NFKD", texto)
        t = "".join(c for c in t if not unicodedata.combining(c)).lower()
        # pontuação de borda fora: "2.1." e "R$ 500,00." são o mesmo dado que "2.1"/"500,00"
        return {tok.strip(".,;:") for tok in
                re.findall(r"\d+[\d.,]*%?|[\w.+-]+@[\w.-]+", t)} - {""}

    bruto = duros((ROOT / "policies_raw.md").read_text(encoding="utf-8"))
    curado = duros(POLICIES_PATH.read_text(encoding="utf-8"))
    assert not (bruto - curado), f"a curadoria perdeu: {sorted(bruto - curado)}"


def test_consultar_politica():
    call = lambda t: consultar_politica.invoke({"topico": t})

    assert call("me arrependi da compra, posso devolver?").startswith("## 4."), "arrependimento -> seção 4"
    assert call("que horas a loja abre no sábado?").startswith("## 2."), "horário -> seção 2"
    assert call("vocês vendem cordas de violão?").startswith("## 1."), "escopo/acessório -> seção 1"
    assert call("quais as formas de pagamento?").startswith("## 3."), "pagamento -> seção 3"
    assert call("como rastreio meu envio?").startswith("## 5."), "rastreamento -> seção 5"
    assert call("qual a garantia do instrumento?").startswith("## 8."), "garantia -> seção 8 (não 4)"

    # as 4 seções que faltavam: sem cobertura, a tabela de palavras-chave regride calada
    assert call("as promoções são cumulativas?").startswith("## 6."), "promoção -> seção 6"
    assert call("qual o whatsapp de vocês?").startswith("## 7."), "contato -> seção 7"
    assert call("como excluo meus dados pessoais?").startswith("## 9."), "LGPD -> seção 9"
    assert call("o que dizem as disposições finais?").startswith("## 10."), "disposições -> seção 10"

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

    # --- busca por especificação (o músico que sabe o que quer) ---
    # valor da spec casa direto; a chave em PT-BR é traduzida para o token do JSON
    r7 = buscar_produtos.invoke({"termo": "61 teclas"})            # specs: "keys": "61"
    assert r7.count("Teclado Sintetizador") == 3, r7
    assert "Bateria" in buscar_produtos.invoke({"termo": "cascos maple"})   # "shells": "Maple"
    assert "Gibson Les Paul" in buscar_produtos.invoke({"termo": "corpo mahogany"})  # "body"
    assert "Yamaha FG800" in buscar_produtos.invoke({"termo": "tampo spruce solido"})

    # conectivos ("de", "em", "com") não podem entrar no E lógico: "de" está dentro de
    # "Fender" e casaria por substring, esvaziando o filtro sem avisar.
    assert "Gibson Les Paul" in buscar_produtos.invoke({"termo": "guitarra com corpo em mahogany"})

    # número solto casa por PALAVRA INTEIRA. Sem isso "7 cordas" trazia o Yamaha C70 e o
    # Kalani KAL-700T, que têm "7" no meio do modelo e não são violões de 7 cordas.
    r8 = buscar_produtos.invoke({"termo": "7 cordas", "apenas_disponiveis": False})
    assert "C70" not in r8 and "KAL-700T" not in r8, r8
    for nome in ("SN-7C", "TW-7", "GWNE-7", "RV-174", "RV-175"):
        assert nome in r8, f"{nome} sumiu da busca por 7 cordas"


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


def test_total_do_pedido_diverge_da_soma():
    """order_items.csv não tem preço unitário. Nos pedidos 3 e 20 a soma a preço de tabela
    não fecha com o total (desconto na venda) — a tool tem que avisar em vez de deixar o
    agente recalcular e contradizer o próprio total."""
    conn = sqlite3.connect(DB_PATH)
    email = lambda oid: conn.execute(
        "SELECT c.email FROM orders o JOIN customers c USING(customer_id) "
        "WHERE o.order_id = ?", [oid]).fetchone()[0]

    for oid, soma in ((3, "R$ 3.498,00"), (20, "R$ 1.488,00")):
        r = status_pedido.invoke({"order_id": oid, "identificador": email(oid)})
        assert "Atenção ao valor" in r and soma in r, r
    # pedido que fecha não pode ganhar o aviso
    assert "Atenção ao valor" not in status_pedido.invoke(
        {"order_id": 1, "identificador": email(1)})
    conn.close()


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


TESTS = [test_etl_views, test_policies_sem_perda, test_consultar_politica,
         test_buscar_produtos, test_total_do_pedido_diverge_da_soma,
         test_detalhe_produto, test_status_pedido, test_identidade_nao_burlavel,
         test_poda_historico, test_agente_compila]


def main():
    # Os asserts de prazo ("há 79 dias") são calibrados nesta data. Sem esta guarda,
    # um .env com outra data faz o teste falhar com cara de bug de código.
    assert DATA_REFERENCE_DATE == date(2026, 3, 25), (
        f"testes calibrados para DATA_REFERENCE_DATE=2026-03-25; seu .env tem "
        f"{DATA_REFERENCE_DATE}")

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
