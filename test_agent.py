"""Checks assert-based, sem framework. Rode:  python test_agent.py

Roda contra um banco TEMPORÁRIO, construído dos CSVs a cada execução. Desde que o agente
escreve (compras baixam estoque e criam pedidos), asserts como "20 pedidos" ou "61
disponíveis" não podem depender do banco da demo. EMPORIO_DB precisa estar no ambiente
ANTES de importar config/tools, porque config lê a variável no import.

Cobre a lógica não-trivial: views do ETL, retrieval de política e as tools de dados
(incluindo a verificação leve de identidade). Não exercita o LLM.
"""
import os
import re
import sqlite3
import tempfile
from pathlib import Path
import unicodedata
from datetime import date

os.environ.setdefault("EMPORIO_DB", str(Path(tempfile.gettempdir()) / "emporio_test.db"))

from config import DATA_REFERENCE_DATE, DB_PATH, POLICIES_PATH, ROOT  # noqa: E402
from tools import (buscar_produtos, cancelar_pedido, comprar, consultar_politica,  # noqa: E402
                   detalhe_produto, status_pedido)


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
    ok = status_pedido.invoke({"order_id": 5, "identificador": "rafael.pereira@jmail.com"})
    assert "Pedido 5" in ok
    assert "entregue" in ok and "há 79 dias" in ok  # ref = 2026-03-25

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
    """Pedido + e-mail exato. Nome nunca libera — nem o completo, nem o do cadastro."""
    from tools import _identidade_confere

    conn = sqlite3.connect(DB_PATH)
    clientes = conn.execute("SELECT name, email FROM customers").fetchall()
    pedidos = conn.execute(
        "SELECT o.order_id, c.name, c.email FROM orders o "
        "JOIN customers c USING(customer_id)").fetchall()
    conn.close()

    for oid, nome, email in pedidos:
        ok = status_pedido.invoke({"order_id": oid, "identificador": email})
        assert f"Pedido {oid}" in ok, f"e-mail correto não abriu o pedido {oid}"
        # o nome completo do próprio cliente passou a NÃO servir (era a rota antiga)
        assert "não posso liberar" in status_pedido.invoke(
            {"order_id": oid, "identificador": nome}), f"nome liberou o pedido {oid}"
        # e-mail com um caractere trocado não passa
        typo = email.replace("@", "@x", 1)
        assert "não posso liberar" in status_pedido.invoke(
            {"order_id": oid, "identificador": typo}), f"typo liberou o pedido {oid}"

    # caixa e acento não importam; espaço em volta também não
    assert _identidade_confere("  ANACAROL.FERREIRA@COLDMAIL.COM ",
                               "anacarol.ferreira@coldmail.com")
    assert not _identidade_confere("", "anacarol.ferreira@coldmail.com")

    # ataques que derrubaram as versões anteriores (nome), agora impossíveis por construção
    spray = ("ana maria jose pedro joao lucas rafael bruno gabriel thiago diego marcelo "
             "silva santos costa souza oliveira pereira lima ferreira rodrigues almeida")
    for nome, email in clientes:
        assert not _identidade_confere(spray, email), f"spray burlou {nome}"
        assert not _identidade_confere(nome, email), f"nome burlou {nome}"
        assert not _identidade_confere(email.split("@")[0], email), "usuário sem domínio"


def test_identificar_cliente():
    """Personaliza, não autentica: os 4 estados e o limite do que ela pode revelar."""
    from tools import identificar_cliente
    ic = lambda e: identificar_cliente.invoke({"email": e})

    # cadastrado COM pedido em trânsito (pedido 8, shipped)
    r = ic("anacarol.ferreira@coldmail.com")
    assert "Ana" in r and "Campo Grande" in r and "pedido 8" in r, r
    # o NÚMERO do pedido pode aparecer (order_id é sequencial 1-20, então quem tem o
    # e-mail já podia enumerar no status_pedido — o e-mail sempre foi o fator único).
    # O CONTEÚDO do pedido, não: isso continua exclusivo do status_pedido.
    for sigilo in ("BRJL5544332BR", "349,90", "Kala KA-C", "28/02/2026"):
        assert sigilo not in r, f"identificar_cliente vazou {sigilo!r}"

    # cadastrado SEM pedido — 32 dos 50 clientes; não pode inventar histórico
    r2 = ic("amanda.lima@coldmail.com")
    assert "Amanda" in r2 and "NÃO tem nenhum pedido" in r2 and "Dourados" in r2, r2

    # não cadastrado -> cliente novo, e a tool proíbe prometer cadastro
    r3 = ic("naoexiste@exemplo.com")
    assert "CLIENTE NOVO" in r3 and "não cadastra" in r3, r3

    # não é e-mail -> não insiste (a identificação é opcional)
    assert "opcional" in ic("Letícia Gonçalves Rocha")

    # e-mail sozinho continua NÃO abrindo pedido de outra pessoa
    assert "não posso liberar" in status_pedido.invoke(
        {"order_id": 8, "identificador": "leticia.rocha@jmail.com"})


def test_simular_pagamento():
    """Duas coisas: a conta, e a DUPLICAÇÃO.

    A tabela de constantes em tools.py é a única regra de política que vive em código
    (é aritmética, e o modelo erra). A primeira metade deste teste é o guard-rail dessa
    exceção: cada número tem que existir literalmente no texto de policies.md. Se o
    manual mudar e o código não, quebra aqui apontando qual constante divergiu.
    """
    from tools import _brl, _FAIXAS_PARCELAMENTO, _FRETE_CG, _PIX_DESCONTO, simular_pagamento

    politica = POLICIES_PATH.read_text(encoding="utf-8")
    pct = f"{int(_PIX_DESCONTO * 100)}%"
    assert pct in politica, f"desconto do PIX ({pct}) não está mais no manual"
    for ate, minimo in _FAIXAS_PARCELAMENTO:
        assert f"{ate}x" in politica, f"faixa de {ate}x sumiu do manual"
        assert _brl(minimo) in politica, f"parcela mínima {_brl(minimo)} sumiu do manual"
    for v in _FRETE_CG:
        assert _brl(v) in politica, f"valor de frete {_brl(v)} sumiu do manual"

    sim = lambda v, cg=False, promo=False: simular_pagamento.invoke(
        {"preco_de_tabela": v, "entrega_em_campo_grande": cg, "ja_esta_em_promocao": promo})

    # 2199/12 = 183,25 >= 100 -> cabe em 12x
    assert "12x sem juros, de R$ 183,25" in sim(2199)
    assert "R$ 2.089,05" in sim(2199)                      # PIX -5%
    # 549/12 = 45,75 < 100 e 549/7 = 78,43 < 100; 549/6 = 91,50 >= 80 -> teto é 6x
    assert "6x sem juros, de R$ 91,50" in sim(549), sim(549)
    # abaixo do mínimo até em 2x
    assert "só à vista" in sim(40)
    # frete metropolitano: a única metade calculável
    assert "R$ 35,00" in sim(480, cg=True) and "grátis" in sim(520, cg=True)
    assert "NÃO tenho como calcular" in sim(480), "fora de CG não pode virar número"

    # PIX não acumula com promoção (§6.2), como na view v_produto. O produto 127 sai por
    # R$ 323,10 com a promo de 10%: no PIX continua 323,10, não 306,94.
    promo = sim(323.10, promo=True)
    assert "R$ 323,10" in promo and "R$ 306,94" not in promo, promo


def test_ciclo_de_compra():
    """Venda ponta a ponta: prévia -> confirmação -> pedido rastreável -> cancelamento.

    É o único caminho que ESCREVE no banco, então o teste cobre as duas coisas: que a
    venda acontece por inteiro, e que ela NÃO acontece sem passar pela confirmação.
    """
    conn = sqlite3.connect(DB_PATH)
    estoque = lambda pid: conn.execute(
        "SELECT stock_quantity FROM products WHERE product_id=?", [pid]).fetchone()[0]
    n_pedidos = lambda: conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    F310, EMAIL = 87, "leticia.rocha@jmail.com"
    estoque0, pedidos0 = estoque(F310), n_pedidos()

    cmp = lambda **kw: comprar.invoke({"produto": "Yamaha F310", "quantidade": 2,
                                       "email": EMAIL, "forma_de_pagamento": "pix", **kw})

    # dado de pagamento nunca entra: nem cartão, nem chave, nem CPF
    assert "não me passe" in cmp(forma_de_pagamento="cartao 4111 1111 1111 1111")
    # guardas de negócio
    assert "Estoque insuficiente" in cmp(quantidade=9999) or "fora do permitido" in cmp(quantidade=9999)
    assert "não pode ser vendido" in cmp(produto="113")            # discontinued
    assert "não confere" in cmp(codigo_de_confirmacao="DEADBEEF")  # código inventado
    assert (estoque(F310), n_pedidos()) == (estoque0, pedidos0), "algo gravou sem confirmar"

    # forma de pagamento: parser, não lista de frases. A §3.1 permite QUALQUER parcelamento
    # até 12x — a primeira versão só aceitava 3x/6x/12x (os valores do dataset) e recusava
    # 5x, que é legítimo. Quem recusa é a parcela mínima da faixa, não a lista.
    from tools import _forma_de_pagamento as fp
    assert fp("crédito em 5x") == fp("cartão 5x") == fp("parcelado em 5 vezes") == "credit_5x"
    assert fp("cartão de débito") == "debit" and fp("pix") == "pix"
    assert fp("em 13x") is None and fp("dinheiro vivo") is None   # acima do teto da §3.1
    assert "PRÉVIA" in cmp(forma_de_pagamento="crédito em 5x")     # 1399,80/5 = 279,96 >= 80
    # parcela abaixo do mínimo é recusada com o teto REAL, não com um 'não'
    baixo = comprar.invoke({"produto": "Kala KA-15S", "quantidade": 1, "email": EMAIL,
                            "forma_de_pagamento": "12x"})
    assert "o máximo é 3x" in baixo, baixo

    # prévia: mostra o preço, COMPARA as formas e NÃO grava
    previa = cmp()
    assert "PRÉVIA" in previa and "R$ 1.329,81" in previa, previa   # 2x699,90 -5% PIX
    # o cliente não escolhe a forma de pagamento no escuro: a prévia traz a alternativa
    assert "Outras formas" in previa and "12x sem juros" in previa, previa
    assert (estoque(F310), n_pedidos()) == (estoque0, pedidos0), "a prévia gravou"
    codigo = re.search(r"codigo_de_confirmacao='([A-Z0-9]+)'", previa).group(1)

    # confirmação: grava tudo numa vez só
    ok = cmp(codigo_de_confirmacao=codigo)
    pedido = int(re.search(r"Número do pedido: (\d+)", ok).group(1))
    assert estoque(F310) == estoque0 - 2, "estoque não baixou pela quantidade exata"
    assert n_pedidos() == pedidos0 + 1
    rastreio = re.search(r"rastreio: (\S+)", ok).group(1)
    assert re.fullmatch(r"BR[A-Z0-9]{9}BR", rastreio), f"formato §5.3 quebrado: {rastreio}"

    # o pedido novo se comporta como os 20 do dataset
    achado = status_pedido.invoke({"order_id": pedido, "identificador": EMAIL})
    assert f"Pedido {pedido}" in achado and rastreio in achado and "1.329,81" in achado
    assert "não posso liberar" in status_pedido.invoke(
        {"order_id": pedido, "identificador": "outro@email.com"})

    # cliente conhecido não vira cadastro duplicado
    assert conn.execute("SELECT COUNT(*) FROM customers WHERE LOWER(email)=?",
                        [EMAIL]).fetchone()[0] == 1

    # cliente novo: a tool diz exatamente o que falta, e só cadastra na compra confirmada
    novo = dict(produto="Yamaha C40", quantidade=1, email="zezinho@exemplo.com",
                forma_de_pagamento="boleto")
    faltam = comprar.invoke(novo)
    assert "nome completo" in faltam and "telefone" in faltam and "cidade" in faltam
    novo |= dict(nome="Zezinho da Silva", telefone="(67) 99999-0000", cidade="Dourados")
    prev2 = comprar.invoke(novo)
    assert "PRÉVIA" in prev2
    assert conn.execute("SELECT COUNT(*) FROM customers WHERE email=?",
                        ["zezinho@exemplo.com"]).fetchone()[0] == 0, "prévia criou cadastro"
    comprar.invoke(novo | {"codigo_de_confirmacao":
                           re.search(r"codigo_de_confirmacao='([A-Z0-9]+)'", prev2).group(1)})
    assert conn.execute("SELECT COUNT(*) FROM customers WHERE email=?",
                        ["zezinho@exemplo.com"]).fetchone()[0] == 1

    # cancelamento devolve o estoque ao valor de antes da compra
    assert "não confere" in cancelar_pedido.invoke(
        {"order_id": pedido, "email": "outro@email.com"})
    assert "cancelado" in cancelar_pedido.invoke(
        {"order_id": pedido, "email": EMAIL, "motivo": "desistiu"})
    assert estoque(F310) == estoque0, "cancelar não devolveu o estoque"
    assert "já está cancelado" in cancelar_pedido.invoke({"order_id": pedido, "email": EMAIL})
    # pedido entregue não é cancelamento, é devolução — e o prazo conta do recebimento
    r = cancelar_pedido.invoke({"order_id": 1, "email": "pedro.oliveira@jmail.com"})
    assert "devolução" in r and "recebeu" in r, r

    # o build preserva o que o agente criou e é IDEMPOTENTE. O estoque é recomputado a
    # partir dos pedidos vivos: descontar de novo um pedido CANCELADO encolhia o estoque
    # a cada build (bug real, visto aqui).
    import build_db
    conn.close()
    build_db.main()
    conn = sqlite3.connect(DB_PATH)
    assert n_pedidos() == pedidos0 + 2, "o build não preservou os pedidos criados"
    assert estoque(F310) == estoque0, "build descontou pedido cancelado"
    depois = (n_pedidos(), estoque(F310))
    conn.close()
    build_db.main()
    conn = sqlite3.connect(DB_PATH)
    assert (n_pedidos(), estoque(F310)) == depois, "dois builds seguidos divergiram"

    build_db.main(reset=True)
    conn = sqlite3.connect(DB_PATH)
    assert n_pedidos() == pedidos0 and estoque(F310) == estoque0, "--reset não limpou"
    conn.close()


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
    """O grafo monta, as 8 tools ligam e o checkpointer cria as tabelas. Não chama o LLM."""
    from agent import build_agent
    from tools import TOOLS
    a = build_agent()
    assert a.__class__.__name__ == "CompiledStateGraph"
    assert len(TOOLS) == 8


TESTS = [test_etl_views, test_policies_sem_perda, test_consultar_politica,
         test_buscar_produtos, test_total_do_pedido_diverge_da_soma,
         test_detalhe_produto, test_status_pedido, test_identidade_nao_burlavel,
         test_simular_pagamento, test_identificar_cliente,
         test_ciclo_de_compra, test_poda_historico, test_agente_compila]


def main():
    # banco limpo dos CSVs a cada execução: os testes de compra escrevem, e o resto
    # afirma contagens que só valem no estado canônico.
    import build_db
    Path(DB_PATH).unlink(missing_ok=True)
    build_db.main(reset=True)
    print(f"(banco de teste: {DB_PATH})\n")

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
