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

    # §4.4 (itens não elegíveis para troca: boquilha e personalização/setup)
    assert call("posso trocar a boquilha do saxofone?").startswith("## 4."), "boquilha -> seção 4"
    assert call("fiz regulagem especial no violão, posso trocar?").startswith("## 4."), "setup/regulagem -> seção 4"

    # "reclamações" (plural) não casava: a palavra-chave só tinha o singular, e o título da
    # seção 7 ("Atendimento via WhatsApp") não contém "reclama" pra salvar pelo fallback de
    # título — ao contrário de "trocas"/"devoluções"/"garantias"/"entregas", que colam no
    # próprio título da seção e por isso nunca quebraram. Achado rodando o agente de verdade:
    # o modelo perguntou "reclamações" (com o plural que ele mesmo escolheu) e caiu no
    # fallback "não identifiquei o tópico", achou que a política não cobria 24h de retorno.
    assert call("quero fazer uma reclamação, em quanto tempo tenho retorno?").startswith("## 7."), \
        "reclamação (singular) -> seção 7"
    assert call("vocês têm um canal de reclamações?").startswith("## 7."), \
        "reclamações (plural) -> seção 7"

    # §5.2 (avaria/extravio no transporte): antes desta rodada TODO esse vocabulário caía
    # no fallback "não identifiquei o tópico" e o modelo reformulava para "defeito" —
    # respondendo com a §4 (troca em 30 dias) uma situação que a §5.2 resolve de outro
    # jeito (recusar o recebimento, acionar o seguro).
    secoes = lambda t: re.findall(r"^## (\d+)\.", call(t), re.M)
    for pergunta in ("o produto veio com avaria", "a caixa chegou amassada",
                     "meu pedido sumiu no correio", "tem seguro no envio?",
                     "quando meu pedido é despachado?"):
        assert secoes(pergunta) == ["5"], f"{pergunta!r} -> {secoes(pergunta)}, esperava só a 5"

    # "quebrado" é ambíguo de verdade (avaria no transporte OU defeito de fábrica) e por
    # isso pontua as DUAS seções: o agente recebe os dois procedimentos e pergunta ao
    # cliente qual é o caso, em vez de escolher um. Já "defeito de fabricação" é só a 4.
    assert secoes("meu violão chegou quebrado") == ["4", "5"], secoes("meu violão chegou quebrado")
    # já "defeito de fabricação" não pode encostar na 5: é troca (4) e garantia (8), e o
    # procedimento de avaria no transporte não se aplica.
    assert "5" not in secoes("veio com defeito de fabricação"), secoes("veio com defeito de fabricação")

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

    # §5.2 (grande porte -> cotação individual): casa pelo NOME, não pela categoria. Os 3
    # kits são "Bateria Acústica"; o baixo da categoria "Baixos" é elétrico (porte de
    # guitarra) e o teclado é sintetizador — marcar os dois mandaria o cliente pedir
    # cotação à toa.
    assert "GRANDE PORTE" in detalhe_produto.invoke({"nome_ou_id": "139"})
    for pid in ("135", "142", "81"):   # baixo elétrico, sintetizador, violão
        assert "GRANDE PORTE" not in detalhe_produto.invoke({"nome_ou_id": pid}), pid

    # a marca tem que sair nos DOIS caminhos até o preço. O eval pegou isso: com ela só na
    # ficha, o agente respondia "quanto custa a bateria X?" pela busca e nunca via o aviso.
    assert "GRANDE PORTE" in buscar_produtos.invoke({"categoria": "bateria"})
    assert "GRANDE PORTE" not in buscar_produtos.invoke({"categoria": "violão", "preco_max": 1000})

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

    sim = lambda v, cg=False, promo=False, pix=0: simular_pagamento.invoke(
        {"preco_de_tabela": v, "entrega_em_campo_grande": cg, "ja_esta_em_promocao": promo,
         "valor_no_pix": pix})

    # 2199/12 = 183,25 >= 100 -> cabe em 12x
    assert "12x sem juros, de R$ 183,25" in sim(2199)
    assert "R$ 2.089,05" in sim(2199)                      # PIX -5%
    # total do cartão vem PRONTO da ferramenta (= preco_de_tabela, "sem juros" é isso por
    # definição) — sem essa conta pra fazer, o modelo não tem como multiplicar parcela × n
    # de cabeça e errar (foi exatamente isso que aconteceu num exemplo real: 183,25 × 12
    # virou "R$ 2.238,00" em vez de R$ 2.199,00).
    assert "total R$ 2.199,00" in sim(2199), sim(2199)
    # 549/12 = 45,75 < 100 e 549/7 = 78,43 < 100; 549/6 = 91,50 >= 80 -> teto é 6x
    assert "6x sem juros, de R$ 91,50" in sim(549), sim(549)
    assert "total R$ 549,00" in sim(549), sim(549)
    # abaixo do mínimo até em 2x
    assert "só à vista" in sim(40)
    # frete metropolitano: a única metade calculável
    from tools import _PRAZO_CG
    assert _PRAZO_CG in politica, f"prazo de entrega em CG ({_PRAZO_CG}) sumiu do manual"
    assert _PRAZO_CG in sim(480, cg=True), "o prazo da §5.1 tem que vir junto com o frete"
    assert "NÃO tenho como calcular" in sim(480), "fora de CG não pode virar número"

    # §5.1, duas suposições registradas no README e no cabeçalho do policies.md:
    # (a) R$ 500,00 redondo PAGA frete — "acima de" é estrito;
    # (b) o limite vale sobre o SUBTOTAL PAGO, depois do desconto.
    assert "R$ 35,00" in sim(480, cg=True)
    assert "R$ 35,00" in sim(500, cg=True), "R$ 500 redondo não é 'acima de R$ 500'"
    assert "grátis" in sim(560, cg=True), "R$ 532 no PIX passa dos 500 nas duas formas"

    # a consequência de (b): entre R$ 500,00 e R$ 526,31 o desconto do PIX derruba o
    # subtotal para baixo do limite e o frete muda conforme a forma de pagamento. A
    # ferramenta tem que devolver as DUAS contas — e, aqui, o cartão sai mais barato.
    borda = sim(520, cg=True)
    assert "DEPENDE da forma de pagamento" in borda, borda
    assert "R$ 494,00 + frete R$ 35,00 = R$ 529,00" in borda, borda
    assert "R$ 520,00 + frete grátis = R$ 520,00" in borda, borda
    assert "mais barato no cartão" in borda, borda

    # preço promocional não leva os 5% (§6.2), então não há divergência entre as formas:
    # o mesmo R$ 520 promocional passa do limite nas duas e o frete sai grátis, sem ramo.
    promo_borda = sim(520, cg=True, promo=True)
    assert "grátis" in promo_borda and "DEPENDE" not in promo_borda, promo_borda

    # §3.1: combinar formas (PIX + cartão) só acima de R$ 2.000. Os 5% incidem apenas
    # sobre a parte paga no PIX, e o parcelamento é recalculado sobre o que sobra no cartão.
    from tools import _COMBINACAO_ACIMA_DE
    assert _brl(_COMBINACAO_ACIMA_DE) in politica, "o limite da combinação sumiu do manual"
    assert "COMBINAR formas" in sim(2500), "acima do limite, a opção tem que ser oferecida"
    assert "COMBINAR formas" not in sim(1500), "abaixo do limite não pode oferecer"
    comb = sim(2500, pix=1000)
    assert "R$ 950,00" in comb, comb          # 1000 no PIX com -5%
    assert "12x sem juros de R$ 125,00" in comb, comb   # 1500 no cartão
    assert "R$ 2.450,00" in comb, comb        # total: 2500 - 50 de desconto
    assert "só é permitido em compras acima" in sim(1500, pix=500)
    assert "MENOR que o total" in sim(2500, pix=2500)
    # promoção: os 5% não incidem nem na parte do PIX (§6.2)
    assert "já é promocional" in sim(2500, pix=1000, promo=True)

    # PIX não acumula com promoção (§6.2), como na view v_produto. O produto 127 sai por
    # R$ 323,10 com a promo de 10%: no PIX continua 323,10, não 306,94.
    promo = sim(323.10, promo=True)
    assert "R$ 323,10" in promo and "R$ 306,94" not in promo, promo


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
    """O grafo monta, as 7 tools ligam e o checkpointer cria as tabelas. Não chama o LLM."""
    from agent import build_agent
    from tools import TOOLS
    a = build_agent()
    assert a.__class__.__name__ == "CompiledStateGraph"
    assert len(TOOLS) == 7


def test_calcular_frete():
    from tools import _brl, _FRETE_CG, _GRANDE_PORTE_FRETE, _PRAZO_CG, calcular_frete

    # 1. Campo Grande
    r_cg = calcular_frete.invoke({"cep": "79002-000", "produto_ou_categoria": "violão"})
    assert "Região Metropolitana de Campo Grande" in r_cg
    assert "motoboy" in r_cg
    # o texto vem das MESMAS constantes que simular_pagamento usa (test_simular_pagamento já
    # confere elas contra policies.md) — sem isso, esta string podia divergir em silêncio.
    gratis_acima, taxa = _FRETE_CG
    assert _brl(taxa) in r_cg and _brl(gratis_acima) in r_cg and _PRAZO_CG in r_cg, r_cg

    # 1.1 Região Metropolitana (prefixo 791x)
    r_rm = calcular_frete.invoke({"cep": "79110-000", "produto_ou_categoria": "violão"})
    assert "Região Metropolitana de Campo Grande" in r_rm
    assert "motoboy" in r_rm

    # 2. Outras cidades (São Paulo)
    r_sp = calcular_frete.invoke({"cep": "01310-100", "produto_ou_categoria": "violão"})
    assert "PAC (Correios)" in r_sp
    assert "SEDEX (Correios)" in r_sp
    assert "Jadlog (.package)" in r_sp
    assert "Seguro: Incluído" in r_sp
    assert "Pacote: Violão" in r_sp
    assert "105×45×15 cm" in r_sp

    # 2.1 Resolução via catálogo para modelo sem categoria no nome
    r_prod = calcular_frete.invoke({"cep": "01310-100", "produto_ou_categoria": "Yamaha C40"})
    assert "Pacote: Violão" in r_prod

    # 3. Grande porte (baterias acústicas, pianos digitais, contrabaixos) -> cotação humana
    for grande in ("bateria acústica", "piano digital", "contrabaixo"):
        r_gp = calcular_frete.invoke({"cep": "01310-100", "produto_ou_categoria": grande})
        assert "Instrumento de grande porte" in r_gp
        assert "(67) 3341-4444" in r_gp
        assert "contato@emporiodamusica.com.br" in r_gp

    # 3.1 REGRESSÃO: _GRANDE_PORTE_FRETE não pode reincidir no shadowing do _GRANDE_PORTE
    # específico (o de _e_grande_porte, em buscar_produtos/detalhe_produto). Baixo elétrico
    # e sintetizador são porte de guitarra/teclado comum — não devem exigir cotação humana,
    # nem pelo nome de categoria nem pelo nome de produto real do catálogo.
    assert "baixo" not in _GRANDE_PORTE_FRETE and "piano" not in _GRANDE_PORTE_FRETE, (
        "termo solto demais em _GRANDE_PORTE_FRETE: casa baixo elétrico/sintetizador à toa")
    for nao_grande in ("baixo elétrico", "Yamaha Bass 3X", "Korg Synth 1 Pro"):
        r_ng = calcular_frete.invoke({"cep": "01310-100", "produto_ou_categoria": nao_grande})
        assert "Instrumento de grande porte" not in r_ng, f"{nao_grande!r} virou grande porte: {r_ng}"
        assert "PAC (Correios)" in r_ng, f"{nao_grande!r} devia dar cotação normal: {r_ng}"


TESTS = [test_etl_views, test_policies_sem_perda, test_consultar_politica,
         test_buscar_produtos, test_total_do_pedido_diverge_da_soma,
         test_detalhe_produto, test_status_pedido, test_identidade_nao_burlavel,
         test_simular_pagamento, test_calcular_frete, test_identificar_cliente,
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
