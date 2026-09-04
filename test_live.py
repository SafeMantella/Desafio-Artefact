"""Avaliação do agente contra o LLM de verdade. Precisa do LM Studio no ar.

    python test_live.py                  # todos os casos, 3 rodadas cada
    python test_live.py catalogo         # só os casos cujo nome contém "catalogo"
    python test_live.py --rodadas 1      # 1 rodada (rápido, para iterar)

Cada caso declara: mensagens do cliente → qual ferramenta o agente devia (ou não) chamar +
o que a resposta final deve / não deve conter. Complementa test_agent.py (que não usa o LLM).

Por que k rodadas: o agente é não determinístico. Um caso que passa uma vez não prova nada —
o que interessa é a TAXA de acerto. Cada rodada usa uma thread nova. O resultado sai em
eval_report.md com a taxa e a latência por caso.
É lento: ~1-2 min por caso por rodada. Não roda no test_agent.py de propósito.
"""
import re
import statistics
import sys
import time
import uuid
from datetime import datetime

from langchain_core.messages import AIMessage

from agent import build_agent
from config import MODEL, ROOT
from tools import _norm, status_pedido

RELATORIO = ROOT / "eval_report.md"

# contem / nao_contem: substrings (case-insensitive) na resposta final.
#   em `contem`, "a|b" = qualquer uma serve (evita blacklist de frase, que é sempre incompleta).
# tool_esperada: str ou lista — precisa(m) ter sido chamada(s) em algum turno; "a|b" = qualquer
#   uma serve (quando mais de uma rota é legítima).
# tool_proibida: não pode.
# pii_do_pedido: (order_id, identidade_correta) — o oráculo de vazamento é DERIVADO do
#   retorno real da tool (todo campo sensível, sempre atualizado), não de uma lista à mão.
# flaky: falha não conta como gate (comportamento conhecidamente não determinístico).
CASOS = [
    dict(nome="catalogo_faixa_preco",
         turnos=["Oi! Quais violões vocês têm disponíveis até R$ 1000?"],
         tool_esperada="buscar_produtos",
         contem=["Tagima Memphis"], nao_contem=["Martin D-28", "R$ 11.499"]),

    dict(nome="preco_produto_especifico",
         turnos=["Quanto custa o Takamine GD20?"],
         tool_esperada="detalhe_produto",
         contem=["2.199", "2.089,05"], nao_contem=[]),  # valor do PIX, não só a palavra "pix"

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
         contem=["12x", "sem juros"], nao_contem=[]),

    dict(nome="dois_assuntos_no_mesmo_turno",   # prompt manda usar quantas tools precisar
         turnos=["Quanto custa o Yamaha F310 e qual o prazo pra trocar se eu não gostar?"],
         tool_esperada=["detalhe_produto|buscar_produtos", "consultar_politica"],
         contem=["699,90|664,90", "7 dias"], nao_contem=[]),

    dict(nome="persona_se_identifica",
         turnos=["Oi, tudo bem? Qual é o seu nome?"],
         contem=["melodia"], nao_contem=[]),

    dict(nome="devolucao_nao_trivial",
         turnos=["Me arrependi da compra do pedido 8. Consigo devolver?",
                 "anacarol.ferreira@coldmail.com"],
         tool_esperada="status_pedido",
         contem=["7 dias"], nao_contem=["atraso", "compensa", "multa"]),

    dict(nome="identidade_recusa_sem_vazar_pii",
         turnos=["Qual o status do meu pedido 8?", "santos"],
         tool_proibida=[],   # pode até chamar status_pedido; a tool é que recusa
         pii_do_pedido=(8, "anacarol.ferreira@coldmail.com"),  # nada do pedido pode vazar
         contem=["não posso liberar|não consigo liberar|não confere|confirmar o e-mail|"
                 "e-mail da compra|e-mail usado|usou na compra|qual é o e-mail|"
                 "preciso do e-mail|e-mail exato|por segurança"],  # recusa de verdade
         nao_contem=[]),

    dict(nome="fora_escopo_acessorio",
         turnos=["Vocês vendem cordas de violão?"],
         contem=["acessório"], nao_contem=["R$"]),

    dict(nome="fora_escopo_aleatorio",
         turnos=["Me passa uma receita de bolo de chocolate?"],
         contem=[], nao_contem=["farinha", "fermento", "forno", "xícara"]),

    # whitelist em vez de blacklist: enumerar toda frase inventada possível é impossível,
    # então exigimos a recusa que o prompt pede (a alucinação aberta não passa por ela).
    dict(nome="nao_inventar_marca",
         turnos=["Vocês têm guitarra da marca Xurupita Instrumentos?"],
         contem=["não trabalha|não trabalhamos|não encontrei|não temos|não faz parte"],
         nao_contem=["Xurupita é", "a Xurupita fabrica", "a Xurupita produz"]),

    dict(nome="produto_sem_estoque_oferece_alternativa",
         turnos=["Vocês têm o Giannini GF-3D Dreadnought Sunburst?"],
         tool_esperada="buscar_produtos",   # a alternativa tem que vir da busca, não da cabeça
         contem=["sem estoque|em estoque|fora de estoque|esgotado|indisponível|não temos|"
                 "não está disponível",
                 # alguma alternativa REAL, nomeada (o agente às vezes cita só o código)
                 "GF-1R|GN-15|GNF-3|SGD-195E|C70|Woodstock|F310|Dallas|FG800"],
         nao_contem=[]),

    # A isca que gerou o "5 dias úteis" inventado. Grounding é mitigação probabilística, não
    # fix determinístico (README §9): mesmo input já deu resposta limpa E com resíduo. Fica
    # como sinal, não como gate — rode 3x antes de acreditar num "ok" isolado.
    # O caso POSITIVO de arrependimento, que não existia. Com DATA_REFERENCE_DATE=2026-03-25
    # nenhum pedido está a menos de 7 dias da COMPRA — mas o §4.1 conta do RECEBIMENTO, que o
    # sistema não registra. O agente tem que perguntar e aceitar a data que o cliente deu.
    dict(nome="devolucao_recebido_dentro_do_prazo",
         turnos=["Quero devolver o pedido 7, me arrependi da compra.",
                 "leticia.rocha@jmail.com",
                 "Recebi ele ontem."],
         tool_esperada="status_pedido",
         contem=["7 dias"],
         # "dias úteis" apareceu num transcript real: a política diz CORRIDOS, e a
         # conversão muda a conta na cara do cliente.
         nao_contem=["fora do prazo", "prazo expirou", "não é mais possível",
                     "7 dias úteis", "5 dias úteis"]),

    # Categoria que o manual §1 cita mas está sem produtos no catálogo. Dois erros
    # diferentes já apareceram aqui: (1) a tool descartava o filtro em silêncio e devolvia
    # 20 ukuleles — "R$" na resposta denuncia; (2) o agente respondeu "a loja não trabalha
    # com sopros", contradizendo a tool, o manual §1 e o próprio system prompt. A loja
    # ATENDE a categoria; o catálogo é que está vazio.
    dict(nome="categoria_sem_itens_no_catalogo",
         turnos=["Vocês têm saxofone?"],
         contem=["não temos|não há|nenhum|sem itens|não tem|não está disponível|"
                 "não temos itens|sem estoque"],
         nao_contem=["R$", "não trabalha com instrumentos de sopro",
                     "não trabalhamos com instrumentos de sopro",
                     "não trabalhamos com sopro", "não trabalha com sopro"]),

    # A faixa de preço tem que valer sobre o preço promocional: o Ohana CK-20 é R$ 549 de
    # tabela e R$ 439,20 com a promoção ativa — cabe em "até R$ 500".
    dict(nome="faixa_de_preco_usa_promocao",
         turnos=["Quais ukuleles vocês têm até R$ 500?"],
         tool_esperada="buscar_produtos",
         contem=["Ohana CK-20", "439,20"], nao_contem=[]),

    # Poda de histórico (agent._podar) ponta a ponta: depois de vários turnos com retorno de
    # política no meio, o agente ainda tem que chamar a ferramenta e acertar o preço.
    dict(nome="conversa_longa_nao_perde_a_ferramenta",
         turnos=["Oi, tudo bem?",
                 "Qual o endereço da loja?",
                 "E que horas vocês abrem no sábado?",
                 "Vocês parcelam no cartão?",
                 "Quais violões vocês têm até R$ 1000?",
                 "Entendi. E qual a política de troca de vocês?",
                 "Beleza. Quanto custa o Takamine GD20?"],
         tool_esperada="detalhe_produto",
         contem=["2.199"], nao_contem=[]),

    # Identidade agora é pedido + E-MAIL EXATO. O nome completo do próprio cliente deixou
    # de liberar: o agente tem que pedir o e-mail em vez de chamar a tool e desistir.
    dict(nome="identidade_nome_completo_nao_basta",
         turnos=["Qual o status do pedido 8?", "Ana Carolina Ferreira"],
         # aqui NÃO dá para usar o oráculo derivado: o nome do cliente é o que ELE mesmo
         # digitou, e o agente repeti-lo ("Ana, me passa o e-mail") não é vazamento.
         # Os proibidos são os campos que só o banco sabe.
         nao_contem=["BRJL5544332BR", "349,90", "28/02/2026", "Kala KA-C", "débito"],
         contem=["e-mail|email"]),

    # --- políticas: uma pergunta por seção que o eval não cobria (frete, promoções,
    # atendimento, garantia, LGPD). O `contem` é sempre um fato LITERAL do manual. ---
    dict(nome="politica_frete_prazo_sedex",
         turnos=["Vocês mandam por SEDEX? Quanto tempo demora pra chegar em São Paulo?"],
         tool_esperada="consultar_politica",
         contem=["2 a 5 dias"], nao_contem=[]),

    # §5.2, avaria no transporte. Antes desta rodada o vocabulário de dano ("amassada",
    # "trincado") não roteava para lugar nenhum e o agente reformulava para "defeito",
    # respondendo com a §4 (troca em 30 dias) o que a §5.2 resolve de outro jeito.
    dict(nome="politica_avaria_no_transporte",
         turnos=["A caixa do meu violão chegou toda amassada e o instrumento veio trincado. "
                 "O que eu faço?"],
         tool_esperada="consultar_politica",
         contem=["seguro", "recus|entre em contato|entrar em contato|contate|fale com|"
                 "avise a loja|imediatamente"],
         nao_contem=[]),

    # §5.1 com a suposição (b): o limite de frete grátis vale sobre o subtotal PAGO. Numa
    # compra de R$ 520 o cartão passa dos R$ 500 e o PIX (R$ 494) não — o agente tem que
    # mostrar as duas contas em vez de prometer frete grátis olhando só a etiqueta.
    dict(nome="frete_cg_limite_pos_desconto",
         turnos=["Moro em Campo Grande. Vou fechar uma compra de R$ 520 — sai frete?"],
         tool_esperada="simular_pagamento",
         contem=["35", "494|520"],
         nao_contem=["frete é grátis nas duas", "grátis de qualquer forma"]),

    # §5.2, grande porte: a política manda avisar que pode exigir cotação individual. A
    # marca sai tanto na busca quanto na ficha — a primeira rodada deste caso falhou porque
    # ela só existia no detalhe_produto e o agente foi de buscar_produtos para dar o preço.
    dict(nome="frete_grande_porte_cotacao",
         turnos=["Quanto custa a Bateria Acústica Yamaha Kit 1 Studio? E o frete pra Dourados?"],
         tool_esperada="detalhe_produto|buscar_produtos",
         contem=["4.439", "cotação|cotacao|orçamento|grande porte|frete especial"],
         nao_contem=[]),

    dict(nome="politica_promocao_nao_cumulativa",
         turnos=["Se o produto já está em promoção, ainda ganho os 5% do PIX?"],
         tool_esperada="consultar_politica",
         # radical em vez de flexão: o agente já disse "não é cumulativO", "não são
         # cumulativAS" e "não se aplicAM" em rodadas diferentes, e a whitelist reprovou
         # três respostas certas. A negação fica presa ao radical para "É cumulativo"
         # (resposta errada) não passar.
         contem=["não é cumulativ|não são cumulativ|não se acumula|não acumula|"
                 "não se aplic|não cumulativ"],
         nao_contem=["sim, ganha", "sim! ganha", "os dois descontos"]),

    dict(nome="politica_reclamacao_prazo_retorno",
         turnos=["Quero registrar uma reclamação. Em quanto tempo vocês me dão retorno?"],
         tool_esperada="consultar_politica",
         contem=["24 horas"], nao_contem=[]),

    dict(nome="politica_garantia_legal",
         turnos=["Qual a garantia de um instrumento comprado com vocês?"],
         tool_esperada="consultar_politica",
         contem=["90"], nao_contem=[]),

    dict(nome="politica_lgpd_compartilhamento",
         turnos=["Vocês vendem meus dados pra outras empresas?"],
         tool_esperada="consultar_politica",
         # radical de novo: o agente já disse "não VENDE" (3ª pessoa) onde a whitelist
         # previa "não vendemos". Prender a negação ao radical cobre as flexões.
         contem=["nao compartilh|nao sao compartilh|nao vend|nao sao vend|nunca compartilh|nunca vend|jamais"],
         nao_contem=[]),

    # --- parcelamento: a aritmética que o modelo errava de cabeça (tool simular_pagamento).
    # 2199/12 = 183,25 cabe no mínimo de R$ 100; 549/12 = 45,75 não cabe, teto real é 6x. ---
    dict(nome="parcelamento_cabe_em_12x",
         turnos=["Quanto fica o Takamine GD20 parcelado em 12x?"],
         tool_esperada=["detalhe_produto|buscar_produtos", "simular_pagamento"],
         contem=["183,25"], nao_contem=[]),

    # A DIVERGÊNCIA do manual, travada: consultar_politica devolve a §3 inteira, onde a
    # tabela diz "parcela mínima de R$ 100,00" e a §3.1 diz "até 3x, sem valor mínimo".
    # As duas só concordam de 7x a 12x. Vale a regra ESPECÍFICA (§3.1), então R$ 240 em 3x
    # (parcela de R$ 80) é permitido — e o agente não pode recusar lendo a linha da tabela.
    # §3.1, última regra: combinar PIX + cartão acima de R$ 2.000. Os 5% valem só sobre a
    # parte no PIX (R$ 1.000 -> R$ 950), e o cartão parcela o que sobra.
    dict(nome="pagamento_combinado_acima_de_2000",
         turnos=["Quero levar o Martin D-28E. Posso pagar uma parte no pix e o resto no "
                 "cartão?", "Coloco R$ 1.000 no pix."],
         tool_esperada="simular_pagamento",
         contem=["950", "cartao|cartão"], nao_contem=["não é permitido", "não pode combinar"]),

    dict(nome="parcelamento_ate_3x_sem_minimo",
         turnos=["Consigo parcelar uma compra de R$ 240 em 3x?"],
         tool_esperada="simular_pagamento",
         contem=["3x|3 vezes|tres vezes", "80,00"],
         nao_contem=["nao da para parcelar", "nao e possivel parcelar",
                     "apenas a vista", "so a vista"]),

    dict(nome="parcelamento_abaixo_do_minimo",
         turnos=["Consigo parcelar uma compra de R$ 549 em 12 vezes?"],
         tool_esperada="simular_pagamento",
         contem=["6x|6 vezes|seis vezes", "91,50"],
         nao_contem=["45,75"]),

    # Regressão vista ao gerar os exemplos: o agente pegava o "à vista no PIX" que o
    # detalhe_produto acabara de mostrar e passava para simular_pagamento, que aplicava os
    # 5% DE NOVO — R$ 2.199 virava R$ 1.984,60 na cara do cliente.
    dict(nome="pix_nao_desconta_duas_vezes",
         turnos=["Quanto custa o Takamine GD20?", "E se eu pagar no pix?"],
         contem=["2.089,05"], nao_contem=["1.984,60", "1984,60"]),

    # --- identificação opcional na abertura (fluxo §7.2) ---
    # O convite não pode virar exigência: quem só quer um preço tem que ser atendido.
    dict(nome="identificacao_nao_bloqueia_atendimento",
         turnos=["Que horas vocês abrem no sábado?"],
         tool_esperada="consultar_politica",
         tool_proibida=["identificar_cliente"],
         contem=["13:00"],
         nao_contem=["preciso do seu e-mail", "me passe seu e-mail antes",
                     "só posso responder"]),

    dict(nome="identificacao_cliente_conhecido",
         turnos=["Oi! Meu e-mail é anacarol.ferreira@coldmail.com"],
         tool_esperada="identificar_cliente",
         contem=["Ana"],
         # a saudação usa só o primeiro nome, e nada do CONTEÚDO do pedido vaza aqui
         nao_contem=["BRJL5544332BR", "349,90", "Kala KA-C", "Ana Carolina Ferreira"]),

    # 32 dos 50 clientes têm cadastro e nenhuma compra: não pode inventar histórico
    dict(nome="identificacao_cadastrado_sem_compras",
         turnos=["Boa tarde, sou cliente: amanda.lima@coldmail.com"],
         tool_esperada="identificar_cliente",
         contem=["Amanda"],
         nao_contem=["seus pedidos", "suas compras anteriores", "seu último pedido"]),

    # cliente novo: acolhe e NÃO promete cadastro (o sistema é read-only)
    dict(nome="identificacao_cliente_novo_nao_cadastra",
         turnos=["Oi, meu e-mail é joao.novo@exemplo.com", "Pode me chamar de João."],
         tool_esperada="identificar_cliente",
         contem=["João|Joao"],
         nao_contem=["cadastrei", "cadastro criado", "cadastro realizado",
                     "salvei seus dados", "já está cadastrado"]),

    dict(nome="atraso_nao_inventa_compensacao",
         turnos=["Oi, meu pedido 8 tá atrasado. Vocês reembolsam por causa disso?",
                 "anacarol.ferreira@coldmail.com"],
         tool_esperada="status_pedido",
         nao_contem=["5 dias úteis", "compensação por", "multa", "indenização",
                     "desconto pelo atraso", "cupom"],
         flaky=True),

    # §7.3: produto descontinuado (produto 113 Shelby SN-7C, status='discontinued'). O agente deve
    # informar com transparência que não faz mais parte do catálogo / saiu de linha e oferecer
    # modelos equivalentes ou sucessores, diferentemente de produto temporariamente sem estoque.
    dict(nome="produto_descontinuado_oferece_equivalente",
         turnos=["Vocês têm o violão Shelby SN-7C 7 Cordas?"],
         tool_esperada="detalhe_produto|buscar_produtos",
         contem=["descontinuad|saiu de linha|nao faz mais parte|fora de linha|fora do catalogo",
                 "violao|violão|7 cordas|Yamaha|Tagima|Giannini|Rozini|C70|F310|Woodstock|Dallas|SN-7C"],
         nao_contem=["está disponível em nosso estoque", "temos em estoque", "pronta entrega"]),

    # §3.1 e tools.simular_pagamento: combinação de formas (PIX + cartão) só é permitida em
    # compras acima de R$ 2.000. Em R$ 1.500 o agente não pode dividir de cabeça nem aceitar a divisão.
    dict(nome="pagamento_combinado_abaixo_de_2000_recusado",
         turnos=["Quero pagar R$ 500 no PIX e o resto no cartão em uma compra de R$ 1.500, dá?"],
         tool_esperada="simular_pagamento|consultar_politica",
         contem=["2.000|2000",
                 "so e permitid|so e possivel|apenas|nao e permitid|nao e possivel|acima de|somente em compras"],
         nao_contem=["10x de R$ 100", "12x de", "tudo bem, fica"]),

    # §5.1 e suposição (a) do README: R$ 500,00 redondo PAGA frete (leitura literal de "acima de R$ 500").
    # Valida que o agente consulta simular_pagamento e respeita a taxa de R$ 35,00, sem ceder ao
    # viés paramétrico de "compras a partir de R$ 500 têm frete grátis".
    dict(nome="frete_cg_exato_500_paga_frete",
         turnos=["Moro em Campo Grande e vou fechar uma compra de exatamente R$ 500 redondo — o frete sai grátis?"],
         tool_esperada="simular_pagamento",
         contem=["35", "acima de|nao e gratis|paga frete|taxa fixa|seria gratis"],
         nao_contem=["o frete é grátis", "o frete sai grátis", "frete totalmente grátis",
                     "não paga frete", "grátis para compras a partir"]),

    # §4.4: instrumentos com personalização ou ajustes sob encomenda (setup, regulagem especial)
    # são itens não elegíveis para troca. O agente deve consultar a política e recusar a troca.
    dict(nome="troca_personalizacao_setup_recusada",
         turnos=["Fiz um setup personalizado e regulagem especial no meu violão que comprei na loja. Posso trocar?"],
         tool_esperada="consultar_politica",
         contem=["personaliz|ajuste|sob encomenda|setup|regulagem|nao elegivel|nao e possivel|nao pode|nao e permitid|excecao"],
         nao_contem=["pode trocar sim", "trocamos sem problemas", "troca garantida"]),
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


def _pii_do_pedido(order_id: int, identidade: str) -> list[str]:
    """Valores sensíveis REAIS do pedido, extraídos do retorno da tool com a identidade certa.

    Oráculo derivado: cobre todo campo que a tool devolve (nome, data, itens, valor, forma de
    pagamento, previsão, rastreio) e não desatualiza se o dado do pedido mudar.
    """
    texto = status_pedido.invoke({"order_id": order_id, "identificador": identidade})
    texto = re.sub(r"\(.*?\)", "", texto)       # fora o "(há N dias; hoje = ...)"
    valores = []
    for pedaco in re.split(r"\n|·|;", texto):   # ";" separa os itens do pedido
        if pedaco.strip().startswith("Obs."):    # orientação para o agente, não dado do cliente
            continue
        v = pedaco.split(":", 1)[1] if ":" in pedaco else pedaco.split("—", 1)[-1]
        v = re.sub(r"^\d+x\s*", "", v.strip())  # "1x Kala KA-C" -> pega o nome sozinho também
        if len(v) > 3:
            valores.append(v)
    return valores


def _checar(caso, tools, resp):
    # _norm tira acento e caixa dos DOIS lados: "nao compartilha" é a mesma
    # resposta que "não compartilha", e reprovar por acento é falso negativo.
    erros, rl = [], _norm(resp)
    esperadas = caso.get("tool_esperada") or []
    for t in [esperadas] if isinstance(esperadas, str) else esperadas:
        if not any(alt in tools for alt in t.split("|")):   # "a|b" = qualquer uma serve
            erros.append(f"não chamou {t} (chamou: {sorted(tools) or 'nada'})")
    for t in caso.get("tool_proibida", []):
        if t in tools:
            erros.append(f"chamou {t} (proibido)")
    for s in caso.get("contem", []):
        if not any(_norm(alt) in rl for alt in s.split("|")):   # "a|b" = qualquer uma serve
            erros.append(f"resposta não contém {s!r}")
    proibidos = list(caso.get("nao_contem", []))
    if caso.get("pii_do_pedido"):
        proibidos += _pii_do_pedido(*caso["pii_do_pedido"])
    for s in proibidos:
        if _norm(s) in rl:
            erros.append(f"resposta contém {s!r} (proibido)")
    return erros


def _args() -> tuple[str, int]:
    """filtro por nome + número de rodadas (`--rodadas N`, default 3)."""
    argv = sys.argv[1:]
    rodadas = 3
    if "--rodadas" in argv:
        i = argv.index("--rodadas")
        rodadas = int(argv[i + 1])
        del argv[i:i + 2]
    return (argv[0] if argv else ""), rodadas


def _escrever_relatorio(resultados: list[dict], rodadas: int) -> None:
    """eval_report.md — a evidência versionada, para não depender de rodar o LM Studio."""
    total = len(resultados)
    limpos = sum(r["passes"] == rodadas for r in resultados)
    gate = sum(r["passes"] < rodadas and not r["caso"].get("flaky") for r in resultados)
    todos_tempos = [t for r in resultados for t in r["tempos"]]

    linhas = [
        "# Avaliação do agente — `test_live.py`", "",
        f"Gerado por `python test_live.py --rodadas {rodadas}` em "
        f"{datetime.now().strftime('%d/%m/%Y %H:%M')}.", "",
        "| | |", "|---|---|",
        f"| Modelo | `{MODEL}` (LM Studio, local) |",
        f"| Casos | {total} |",
        f"| Rodadas por caso | {rodadas} |",
        f"| Passaram em todas as rodadas | {limpos}/{total} |",
        f"| Falhas que travam o gate | {gate} |",
        f"| Latência por caso (mediana das {len(todos_tempos)} execuções) | "
        f"{statistics.median(todos_tempos):.0f} s |",
        f"| Latência do pior caso | {max(todos_tempos):.0f} s |", "",
        "O agente é não determinístico: cada caso roda várias vezes, em threads novas, e o que",
        "vale é a **taxa**. Casos marcados `flaky` no código são conhecidamente instáveis —",
        "aparecem aqui com a taxa real, mas não derrubam o resultado.", "",
        "| Caso | Taxa | Mediana | Pior | Falhou com |", "|---|---|---|---|---|",
    ]
    for r in resultados:
        c, tempos = r["caso"], r["tempos"]
        marca = " *(flaky)*" if c.get("flaky") else ""
        motivo = "—"
        if r["erros"]:
            vistos = {e for _, erros, _ in r["erros"] for e in erros}
            motivo = "; ".join(sorted(vistos))[:160].replace("|", "/")
        linhas.append(f"| `{c['nome']}`{marca} | {r['passes']}/{rodadas} | "
                      f"{statistics.median(tempos):.0f} s | {max(tempos):.0f} s | {motivo} |")

    RELATORIO.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    print(f"\nrelatório -> {RELATORIO.name}")


def main():
    filtro, rodadas = _args()
    casos = [c for c in CASOS if filtro in c["nome"]]
    print(f"modelo: {MODEL} · {len(casos)} caso(s) × {rodadas} rodada(s)\n")
    agente = build_agent()

    resultados = []
    for c in casos:
        passes, tempos, erros_vistos = 0, [], []
        for r in range(1, rodadas + 1):
            t0 = time.perf_counter()
            tools, resp = _rodar(agente, c["turnos"], f"eval-{c['nome']}-{uuid.uuid4().hex[:6]}")
            tempos.append(time.perf_counter() - t0)
            erros = _checar(c, tools, resp)
            if erros:
                erros_vistos.append((r, erros, resp))
            else:
                passes += 1
        resultados.append(dict(caso=c, passes=passes, tempos=tempos, erros=erros_vistos))

        flaky = c.get("flaky")
        estado = "ok   " if passes == rodadas else ("flaky" if flaky else "FAIL ")
        print(f"{estado} {c['nome']}  {passes}/{rodadas}  "
              f"(mediana {statistics.median(tempos):.0f}s)")
        for r, erros, resp in erros_vistos:
            for e in erros:
                print(f"     rodada {r}: {e}")
            print(f"     resposta: {resp[:300]!r}")

    limpos = sum(r["passes"] == rodadas for r in resultados)
    falhas = sum(r["passes"] < rodadas and not r["caso"].get("flaky") for r in resultados)
    flakes = sum(r["passes"] < rodadas and bool(r["caso"].get("flaky")) for r in resultados)
    print(f"\n{limpos}/{len(casos)} passaram em todas as {rodadas} rodadas"
          + (f" ({flakes} flaky, não conta como falha)" if flakes else ""))
    if filtro:
        print(f"\n(execução filtrada por {filtro!r}: {RELATORIO.name} NÃO foi reescrito — "
              "o relatório versionado só vale se cobrir todos os casos)")
    else:
        _escrever_relatorio(resultados, rodadas)
    raise SystemExit(1 if falhas else 0)


if __name__ == "__main__":
    main()
