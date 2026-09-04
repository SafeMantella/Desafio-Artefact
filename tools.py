"""Tools do agente. SQL sempre parametrizado; regras de política vêm do texto de policies.md.

- consultar_politica(topico)                      -> seção(ões) do manual de políticas
- buscar_produtos(...)                            -> catálogo (Parte 3)
- detalhe_produto(nome_ou_id)                     -> ficha de um produto (Parte 3)
- status_pedido(order_id, identificador)          -> pedido, com verificação leve (Parte 3)
"""
import json
import re
import sqlite3
import unicodedata
from contextlib import closing
from datetime import date

from langchain_core.tools import tool

from config import DATA_REFERENCE_DATE, DB_PATH, POLICIES_PATH, log


def _norm(s: str) -> str:
    """minúsculas, sem acento — para casar texto de forma robusta."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower().strip()


def _conn() -> sqlite3.Connection:
    """Sempre usar com `closing()`: o context manager do sqlite3 faz commit/rollback,
    mas NÃO fecha a conexão — sem isso o processo do Streamlit vaza um handle por chamada."""
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def _brl(v) -> str:
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


# ---------------------------------------------------------------------------
# Políticas: policies.md seccionado por "## N. Título"
# ---------------------------------------------------------------------------

def _carregar_secoes() -> dict[str, str]:
    """{ '2': '## 2. Horário de Funcionamento\n...' } — corpo inclui subseções ###."""
    texto = POLICIES_PATH.read_text(encoding="utf-8")
    texto = re.sub(r"<!--.*?-->", "", texto, flags=re.DOTALL)  # tira o cabeçalho de notas
    secoes: dict[str, str] = {}
    atual = None
    for linha in texto.splitlines():
        m = re.match(r"^##\s+\*{0,2}(\d+)\.\s", linha)  # tolera "## **N." do pymupdf4llm
        if m:
            atual = m.group(1)
            secoes[atual] = linha + "\n"
        elif atual is not None:
            secoes[atual] += linha + "\n"
    return {k: v.strip() for k, v in secoes.items()}


# palavra-chave (normalizada, sem acento) -> número da seção
_KEYWORDS: dict[str, str] = {}
for _sec, _palavras in {
    "1": ["sobre a loja", "sobre a empresa", "empresa", "cnpj", "razao social", "endereco",
          "onde fica", "onde e", "localizacao", "local", "catalogo", "missao",
          "acessorio", "acessorios", "corda", "cordas", "palheta", "palhetas", "cabo", "cabos",
          "case", "cases", "pedal", "pedais", "amplificador", "amplificadores", "caixa de som",
          "vende", "vendem", "trabalha com", "tem a venda"],
    "2": ["horario", "hora", "que horas", "abre", "abrem", "fecha", "fecham", "funcionamento",
          "aberto", "domingo", "sabado", "feriado", "expediente"],
    "3": ["pagamento", "forma de pagamento", "pagar", "pix", "cartao", "credito", "debito",
          "boleto", "parcelamento", "parcela", "parcelar", "juros", "a vista", "sem juros"],
    "4": ["troca", "trocar", "devolucao", "devolver", "devolvo", "arrependimento", "arrependi",
          "reembolso", "reembolsar", "estorno", "defeito", "veio com defeito", "venda final",
          "nao elegivel", "prazo de troca", "7 dias", "30 dias"],
    "5": ["frete", "entrega", "entregar", "envio", "enviar", "correios", "sedex", "pac",
          "jadlog", "rastreamento", "rastreio", "rastrear", "codigo de rastreamento", "motoboy",
          "prazo de entrega", "quando chega", "cep", "frete gratis"],
    "6": ["promocao", "promocoes", "promo", "desconto", "black friday", "aniversario da loja",
          "volta as aulas", "queima de estoque", "semana do musico", "cupom", "oferta",
          "liquidacao", "rain check"],
    "7": ["whatsapp", "atendimento", "contato", "falar com atendente", "telefone", "numero da loja",
          "reclamacao", "reclamar", "reclamacao", "fora de estoque", "descontinuado", "sac"],
    "8": ["garantia", "defeito de fabricacao", "90 dias", "fabricante", "cobertura",
          "o que cobre", "nao cobre", "assistencia"],
    "9": ["lgpd", "privacidade", "protecao de dados", "dados pessoais", "excluir meus dados",
          "exclusao de dados", "meus dados"],
    "10": ["disposicoes finais", "gerencia", "atualizacao do manual"],
}.items():
    for _p in _palavras:
        _KEYWORDS[_norm(_p)] = _sec

_SECOES = _carregar_secoes()
_TITULOS = {n: linha.splitlines()[0].lstrip("# ").strip() for n, linha in _SECOES.items()}
TOPICOS = ", ".join(f"{n}={_TITULOS[n]}" for n in sorted(_SECOES, key=int))


@tool
def consultar_politica(topico: str) -> str:
    """Consulta o manual de políticas da loja e retorna a(s) seção(ões) relevante(s).

    Use SEMPRE que a pergunta for sobre regras/procedimentos da loja e não sobre dados de
    catálogo ou de um pedido específico: horário de funcionamento, endereço da loja, formas
    de pagamento e parcelamento, trocas/devoluções/arrependimento, frete e prazos de entrega,
    rastreamento, promoções (regras gerais), garantia, LGPD/privacidade, e o que a loja
    vende ou não vende (escopo — ex.: acessórios).

    topico: o assunto em linguagem natural (ex.: "política de troca", "horário", "formas de
    pagamento", "vocês vendem cordas?").
    """
    log.debug("consultar_politica(topico=%r)", topico)
    q = _norm(topico)
    pontos: dict[str, int] = {}
    for palavra, sec in _KEYWORDS.items():
        if re.search(rf"\b{re.escape(palavra)}\b", q):  # palavra inteira, não "vende" em "vendedor"
            pontos[sec] = pontos.get(sec, 0) + len(palavra)  # match mais específico pesa mais
    # também casa contra o título da seção
    for sec, titulo in _TITULOS.items():
        for token in _norm(titulo).split():
            if len(token) > 3 and token in q:
                pontos[sec] = pontos.get(sec, 0) + 2

    if not pontos:
        return ("Não identifiquei o tópico. Assuntos cobertos pelo manual: "
                f"{TOPICOS}. Reformule com uma dessas palavras.")

    # devolve toda seção com match forte (>=5) — cobre perguntas de 2 assuntos
    # ("endereço e horário"); no pior caso, a melhor seção sozinha.
    ordenadas = sorted(pontos, key=lambda s: pontos[s], reverse=True)
    melhor = pontos[ordenadas[0]]
    escolhidas = [s for s in ordenadas if pontos[s] >= 5 or pontos[s] >= melhor * 0.6][:3]
    return "\n\n---\n\n".join(_SECOES[s] for s in sorted(escolhidas, key=int))


# ---------------------------------------------------------------------------
# Catálogo (emporio.db / view v_produto)
# ---------------------------------------------------------------------------

# sinônimos digitados pelo cliente -> nome da categoria em categories.csv
_CATEGORIAS = {
    "violao": "Violões", "violoes": "Violões", "viola caipira": "Violões",
    "guitarra": "Guitarras", "guitarras": "Guitarras",
    "baixo": "Baixos", "contrabaixo": "Baixos", "baixos": "Baixos",
    "bateria": "Baterias e Percussão", "baterias": "Baterias e Percussão",
    "percussao": "Baterias e Percussão",
    "teclado": "Teclados e Pianos", "teclados": "Teclados e Pianos",
    "piano": "Teclados e Pianos", "sintetizador": "Teclados e Pianos",
    "ukulele": "Ukuleles", "ukuleles": "Ukuleles", "uke": "Ukuleles",
    # Categorias 6, 7 e 8 existem em categories.csv mas hoje estão sem produtos. Mapear
    # mesmo assim: melhor a tool dizer "sem itens no catálogo" do que ignorar o filtro.
    # (chave mais específica primeiro — o casamento pelo `termo` é por substring)
    "saxofone": "Instrumentos de Sopro (Madeiras)", "sax": "Instrumentos de Sopro (Madeiras)",
    "flauta": "Instrumentos de Sopro (Madeiras)", "clarinete": "Instrumentos de Sopro (Madeiras)",
    "sopros": "Instrumentos de Sopro (Madeiras)", "sopro": "Instrumentos de Sopro (Madeiras)",
    "madeiras": "Instrumentos de Sopro (Madeiras)",
    "trompete": "Instrumentos de Sopro (Metais)", "trombone": "Instrumentos de Sopro (Metais)",
    "trompa": "Instrumentos de Sopro (Metais)", "tuba": "Instrumentos de Sopro (Metais)",
    "metais": "Instrumentos de Sopro (Metais)",
    "violoncelo": "Cordas Orquestrais", "violino": "Cordas Orquestrais",
    "cordas orquestrais": "Cordas Orquestrais", "orquestral": "Cordas Orquestrais",
    "cello": "Cordas Orquestrais",
}

CATEGORIAS_CONHECIDAS = ", ".join(sorted(set(_CATEGORIAS.values())))

# Busca por especificação (o caso do músico que sabe exatamente o que quer).
# `specs` está no banco como JSON cru e com as CHAVES em inglês ({"top": "Spruce Sólido",
# "keys": "61"}), então a palavra do cliente ("tampo", "teclas") nunca aparece no texto
# pesquisado. Esta tabela traduz o substantivo em PT-BR para o token que existe no JSON.
# Os VALORES já casam direto (spruce, mahogany, maple, nylon, sunburst, 650mm) — só "aço"
# precisa de tradução, porque no dado é "steel".
# ponytail: tabela fixa, não sinônimo semântico. O dado mistura idiomas no mesmo campo
# ("Mogno" no Kala, "Mahogany" na Gibson); cobrir isso pede busca semântica, não mais
# entradas aqui — ver "Limitações conhecidas" no README.
_SPECS_PT = {
    "tampo": "top", "fundo": "back_sides", "laterais": "back_sides", "braco": "neck",
    "corpo": "body", "escala": "scale", "cor": "color", "acabamento": "color",
    "teclas": "keys", "polifonia": "polyphony", "pecas": "pieces", "cascos": "shells",
    "ferragens": "hardware", "captacao": "electronics", "eletronica": "electronics",
    "cordas": "strings", "aco": "steel",
}

# conectivos que o cliente escreve e que casariam por substring em qualquer lugar
# ("de" está dentro de "Fender"), esvaziando o filtro em silêncio.
_RUIDO_TERMO = {"de", "da", "do", "dos", "das", "e", "em", "com", "para", "por", "um", "uma"}

_STATUS_PRODUTO = {"active": "à venda", "discontinued": "descontinuado", "coming_soon": "em breve no catálogo"}


def _linha_produto(r: sqlite3.Row) -> str:
    partes = [f"{r['name']} ({r['categoria']})"]
    if r["promo_ativa_pct"]:
        partes.append(f"de {_brl(r['preco_tabela'])} por {_brl(r['preco_promocional'])} "
                      f"(-{r['promo_ativa_pct']}%)")
    else:
        partes.append(_brl(r["preco_tabela"]))
    partes.append(f"à vista no PIX {_brl(r['preco_a_vista_pix'])}")
    if not r["disponivel"]:
        partes.append("SEM ESTOQUE no momento" if r["status"] == "active"
                      else _STATUS_PRODUTO.get(r["status"], r["status"]).upper())
    return " — ".join(partes)


@tool
def buscar_produtos(termo: str = "", categoria: str = "", preco_min: float = 0,
                    preco_max: float = 0, apenas_disponiveis: bool = True) -> str:
    """Busca instrumentos no catálogo da loja. Use para perguntas sobre o que a loja tem,
    opções dentro de um preço, disponibilidade de um tipo de instrumento, etc.

    termo: texto livre. Casa no nome E nas ESPECIFICAÇÕES do instrumento — use para o
        cliente que pede por spec, não por modelo. Todas as palavras precisam casar.
        Marca/modelo: "Yamaha", "Takamine GD20", "dreadnought".
        Spec: "tampo spruce", "corpo mahogany", "cascos maple", "61 teclas",
        "cordas de aço", "escala 650mm", "cor sunburst", "7 cordas".
        Passe a spec como o cliente falou; não traduza nem invente termo técnico.
    categoria: tipo de instrumento (violão, guitarra, baixo, bateria, teclado, ukulele).
    preco_min / preco_max: faixa de preço em reais, sobre o preço EFETIVO (o promocional
        quando há promoção ativa, senão o de tabela). Use 0 (padrão) para "sem limite" —
        NUNCA passe None, null ou texto.
    apenas_disponiveis: se True (padrão), só lista o que está em estoque e à venda.

    Retorna uma lista com preço de tabela, preço promocional (se houver promoção ativa) e
    preço à vista no PIX. Não invente itens: use só o que esta ferramenta retornar.
    """
    log.debug("buscar_produtos(termo=%r, categoria=%r, preco=%s-%s, disponiveis=%s)",
             termo, categoria, preco_min, preco_max, apenas_disponiveis)
    cat_alvo = _CATEGORIAS.get(_norm(categoria)) if categoria else None
    if categoria and not cat_alvo:
        # Antes o filtro era descartado em silêncio: categoria="saxofone" devolvia 20 ukuleles.
        return (f"Não conheço a categoria '{categoria}'. As categorias do catálogo são: "
                f"{CATEGORIAS_CONHECIDAS}. Para texto livre (marca, modelo), use o `termo`.")

    # A faixa de preço vale sobre o preço EFETIVO (o promocional quando há promoção ativa):
    # "até R$ 500" tem que trazer o Ohana CK-20, que sai por R$ 439,20 com a tabela em 549.
    efetivo = "COALESCE(preco_promocional, preco_tabela)"

    def _consulta(so_disponiveis: bool) -> list[sqlite3.Row]:
        sql = "SELECT * FROM v_produto WHERE 1=1"
        args: list = []
        if so_disponiveis:
            sql += " AND disponivel = 1"
        if preco_min and preco_min > 0:
            sql += f" AND {efetivo} >= ?"; args.append(preco_min)
        if preco_max and preco_max > 0:
            sql += f" AND {efetivo} <= ?"; args.append(preco_max)
        if cat_alvo:
            sql += " AND categoria = ?"; args.append(cat_alvo)

        with closing(_conn()) as c:
            rows = c.execute(f"{sql} ORDER BY {efetivo}", args).fetchall()

        # termo: casa cada palavra (sem acento) no nome; se não veio categoria explícita,
        # também tenta interpretar o termo como categoria.
        if termo:
            if not cat_alvo:
                cat_do_termo = next((v for k, v in _CATEGORIAS.items() if k in _norm(termo)), None)
                if cat_do_termo:
                    rows = [r for r in rows if r["categoria"] == cat_do_termo]
            palavras = [_SPECS_PT.get(p, p) for p in _norm(termo).split()
                        if p not in _CATEGORIAS and p not in _RUIDO_TERMO]
            for p in palavras:
                # número solto casa por palavra inteira: "7 cordas" não pode trazer o
                # Yamaha C70 nem o Kalani KAL-700T. O resto segue por substring, que é o
                # que faz "spruce" achar "Spruce Sólido".
                casa = ((lambda t: re.search(rf"\b{p}\b", t) is not None) if p.isdigit()
                        else (lambda t: p in t))
                rows = [r for r in rows if casa(_norm(f"{r['name']} {r['specs'] or ''}"))]
        return rows

    rows = _consulta(apenas_disponiveis)

    # "existe mas está indisponível" ≠ "não existe": sem esta distinção o agente diz ao
    # cliente que o produto não está no catálogo, o que é falso (visto ao vivo com o GF-3D).
    if not rows and apenas_disponiveis:
        indisponiveis = _consulta(False)
        if indisponiveis:
            corpo = "\n".join(f"- {_linha_produto(r)}" for r in indisponiveis[:5])
            return ("Nada DISPONÍVEL com esses critérios, mas isto EXISTE no catálogo (só não "
                    f"dá para comprar agora):\n{corpo}\n\n"
                    "Diga ao cliente que o item existe e está indisponível — não diga que não "
                    "está no catálogo — e ofereça alternativas (busque de novo, sem o termo).")

    if not rows:
        if cat_alvo:
            with closing(_conn()) as c:
                na_categoria = c.execute("SELECT COUNT(*) FROM v_produto WHERE categoria = ?",
                                         [cat_alvo]).fetchone()[0]
            if na_categoria == 0:
                return (f"A loja trabalha com {cat_alvo} (o manual cita a categoria), mas não há "
                        "nenhum item dessa categoria no catálogo no momento.")
        return ("Não encontrei nenhum instrumento com esses critérios. "
                "Talvez ajustando a faixa de preço ou a categoria.")

    # lista PRIMEIRO; nota de truncamento por último (senão o modelo comenta a
    # paginação e esquece de repassar os itens).
    corpo = "\n".join(f"- {_linha_produto(r)}" for r in rows[:20])
    if len(rows) <= 20:
        return f"{len(rows)} instrumento(s). Liste estes itens na resposta ao cliente:\n{corpo}"
    return (f"Liste estes 20 itens na resposta ao cliente:\n{corpo}\n\n"
            f"(são os 20 mais baratos de {len(rows)} disponíveis; para ver outros, "
            f"filtre por categoria ou faixa de preço)")


@tool
def detalhe_produto(nome_ou_id: str) -> str:
    """Ficha completa de UM instrumento: preço de tabela, preço à vista no PIX, promoção
    ativa, especificações, disponibilidade e descrição.

    nome_ou_id: o nome (ou parte dele) ou o id numérico do produto. Se houver ambiguidade,
    a ferramenta devolve a lista de candidatos para você pedir mais detalhes ao cliente.
    """
    log.debug("detalhe_produto(nome_ou_id=%r)", nome_ou_id)
    with closing(_conn()) as c:
        if nome_ou_id.strip().isdigit():
            rows = c.execute("SELECT * FROM v_produto WHERE product_id = ?",
                             [int(nome_ou_id)]).fetchall()
        else:
            todos = c.execute("SELECT * FROM v_produto").fetchall()
            alvo = _norm(nome_ou_id)
            palavras = alvo.split()
            rows = [r for r in todos if all(p in _norm(r["name"]) for p in palavras)]

    if not rows:
        return f"Não encontrei nenhum produto para '{nome_ou_id}'."
    if len(rows) > 1:
        return ("Encontrei mais de um produto. Qual deles?\n"
                + "\n".join(f"- {r['name']} ({r['categoria']})" for r in rows[:10]))

    r = rows[0]
    linhas = [f"**{r['name']}**  ·  {r['categoria']}",
              f"Situação no catálogo: {_STATUS_PRODUTO.get(r['status'], r['status'])}",
              f"Disponibilidade: {'em estoque' if r['disponivel'] else 'sem estoque no momento'}",
              f"Preço de tabela: {_brl(r['preco_tabela'])}"]
    if r["promo_ativa_pct"]:
        linhas.append(f"Promoção ativa: -{r['promo_ativa_pct']}% → {_brl(r['preco_promocional'])}")
    else:
        linhas.append("Promoção ativa: nenhuma")
    linhas.append(f"À vista no PIX: {_brl(r['preco_a_vista_pix'])}"
                  + ("" if r["promo_ativa_pct"] else "  (desconto fixo de 5% do PIX, não é promoção)"))
    try:
        specs = json.loads(r["specs"])
        if specs:
            linhas.append("Especificações: " + ", ".join(f"{k}: {v}" for k, v in specs.items()))
    except (json.JSONDecodeError, TypeError):
        pass
    if r["description"]:
        linhas.append(f"\n{r['description']}")
    return "\n".join(linhas)


# ---------------------------------------------------------------------------
# Pagamento e frete — a ÚNICA regra de política que vive em código
# ---------------------------------------------------------------------------
# A convenção do projeto é que regra de política vive no texto (policies.md), não em código.
# Aqui abrimos exceção por um motivo: isto é ARITMÉTICA, e é onde a alucinação do modelo
# aparece — "R$ 549 em 12x" dá parcela de R$ 45,75, abaixo do mínimo da faixa, e o agente
# responde "pode sim" se tiver que calcular de cabeça a partir do texto da política.
#
# Para a exceção não virar dívida escondida, os números ficam TODOS nesta tabela e o
# `test_simular_pagamento` confere cada um contra o texto de policies.md: se o manual mudar
# e isto não, o teste quebra dizendo qual constante divergiu.
_PIX_DESCONTO = 0.05                                          # §3, linha do PIX
_FAIXAS_PARCELAMENTO = ((3, 50.0), (6, 80.0), (12, 100.0))    # §3.1: (até Nx, parcela mínima)
_FRETE_CG = (500.0, 35.0)                                     # §5.1: (grátis acima de, taxa fixa)


def _max_parcelas(valor: float) -> tuple[int, float]:
    """(nº máximo de parcelas, valor da parcela), respeitando o mínimo de cada faixa."""
    minimo = lambda n: next((m for ate, m in _FAIXAS_PARCELAMENTO if n <= ate), None)
    for n in range(_FAIXAS_PARCELAMENTO[-1][0], 1, -1):
        if valor / n >= minimo(n):
            return n, valor / n
    return 1, valor


@tool
def simular_pagamento(valor: float, entrega_em_campo_grande: bool = False) -> str:
    """Calcula as formas de pagamento para um valor: preço à vista no PIX, em quantas vezes
    dá para parcelar e quanto fica cada parcela. Opcionalmente, o frete metropolitano.

    Use SEMPRE que a pergunta envolver CONTA sobre um valor concreto: "dá pra parcelar em
    12x?", "quanto fica a parcela?", "em quantas vezes posso dividir?", "quanto sai no PIX?",
    "pago frete nessa compra?". NUNCA faça essa conta de cabeça.
    Para as regras gerais de pagamento, sem um valor na mesa, use consultar_politica.

    valor: o total em reais (ex.: o preço do instrumento que o cliente escolheu).
    entrega_em_campo_grande: True só se o cliente disse que é em Campo Grande ou região
        metropolitana. Se ele não disse, deixe False e pergunte a cidade.
    """
    log.debug("simular_pagamento(valor=%s, cg=%s)", valor, entrega_em_campo_grande)
    if not valor or valor <= 0:
        return "Preciso do valor da compra para calcular. Confirme o produto com o cliente."

    n, parcela = _max_parcelas(valor)
    linhas = [
        f"Simulação para {_brl(valor)}:",
        f"- À vista no PIX: {_brl(valor * (1 - _PIX_DESCONTO))} "
        f"({int(_PIX_DESCONTO * 100)}% de desconto). Esse desconto NÃO se aplica sobre preço "
        "que já está promocional.",
    ]
    if n == 1:
        linhas.append("- Cartão de crédito: só à vista. Nesse valor, mesmo em 2x a parcela "
                      "ficaria abaixo do mínimo permitido pela política.")
    else:
        linhas.append(f"- Cartão de crédito: até {n}x sem juros, de {_brl(parcela)} cada. "
                      f"Acima de {n}x a parcela cairia abaixo do mínimo da faixa.")

    gratis_acima, taxa = _FRETE_CG
    if entrega_em_campo_grande:
        linhas.append(f"- Frete em Campo Grande e região: grátis (acima de {_brl(gratis_acima)})"
                      if valor > gratis_acima else
                      f"- Frete em Campo Grande e região: {_brl(taxa)} "
                      f"(seria grátis acima de {_brl(gratis_acima)})")
    else:
        linhas.append(
            "- Frete: para fora de Campo Grande NÃO tenho como calcular — depende do CEP, do "
            "peso e das dimensões. Diga isso ao cliente com franqueza, informe as modalidades "
            "e prazos (consultar_politica sobre frete) e ofereça falar com a equipe para uma "
            "cotação, passando o contato que a política de atendimento traz.")
    return "\n".join(linhas)


# ---------------------------------------------------------------------------
# Pedidos (emporio.db) — com verificação leve de identidade (LGPD, política 9)
# ---------------------------------------------------------------------------

_STATUS_PEDIDO = {
    "pending": "pagamento pendente",
    "confirmed": "confirmado, em preparação",
    "shipped": "enviado, a caminho",
    "delivered": "entregue",
    "cancelled": "cancelado",
}


def _pagamento(m: str) -> str:
    if m == "pix": return "PIX"
    if m == "boleto": return "boleto"
    if m == "debit": return "cartão de débito"
    mx = re.match(r"credit_(\d+)x", m or "")
    return f"cartão de crédito em {mx.group(1)}x" if mx else (m or "não informado")


def _identidade_confere(identificador: str, email: str) -> bool:
    """Libera o pedido só com o e-mail EXATO do cadastro (normalizado: caixa e acento).

    Antes valia também nome+sobrenome. Era mais amigável e menos seguro: exigia três
    versões de heurística contra spray de nomes comuns e ainda deixava colidir clientes
    cujo nome é subconjunto do outro. Pedido + e-mail é o par que um e-commerce real pede,
    e cabe numa linha que não tem como regredir.
    """
    return bool(identificador.strip()) and _norm(identificador) == _norm(email)


@tool
def status_pedido(order_id: int, identificador: str) -> str:
    """Consulta o andamento de um pedido. Exige verificação de identidade (LGPD): só retorna
    os dados se `identificador` for o E-MAIL EXATO do cadastro daquele pedido. Nome, mesmo
    completo, NÃO é aceito.

    order_id: número do pedido.
    identificador: o e-mail que o cliente usou na compra, exatamente como ele informou. Se
    o cliente ainda não deu o e-mail, PEÇA antes de chamar esta ferramenta — e não tente
    adivinhar nem montar o e-mail a partir do nome.

    Retorna status, itens, valor, forma de pagamento, previsão de entrega, código de
    rastreio e há quantos dias a COMPRA foi feita. Atenção: o sistema não guarda data de
    recebimento — prazos que a política conta a partir do recebimento exigem perguntar ao
    cliente quando ele recebeu.
    """
    log.debug("status_pedido(order_id=%s)", order_id)   # identificador tem PII: não logar
    with closing(_conn()) as c:
        o = c.execute("SELECT * FROM orders WHERE order_id = ?", [order_id]).fetchone()
        if not o:
            return f"Não encontrei nenhum pedido com o número {order_id}."
        cli = c.execute("SELECT * FROM customers WHERE customer_id = ?",
                        [o["customer_id"]]).fetchone()
        itens = c.execute("SELECT quantity, produto, preco_tabela FROM v_pedido_item "
                          "WHERE order_id = ?", [order_id]).fetchall()

    if not _identidade_confere(identificador, cli["email"] if cli else ""):
        return (f"Por segurança, não posso liberar os dados do pedido {order_id}: o e-mail "
                "informado não confere com o cadastro. Pode confirmar o e-mail usado na "
                "compra? Só com ele eu consigo abrir o pedido.")

    d = date.fromisoformat(o["order_date"])
    dias = (DATA_REFERENCE_DATE - d).days
    linhas = [
        f"Pedido {order_id} — {_STATUS_PEDIDO.get(o['status'], o['status'])}",
        f"Cliente: {cli['name']}",
        f"Data do pedido: {d.strftime('%d/%m/%Y')} (há {dias} dias da compra; hoje = "
        f"{DATA_REFERENCE_DATE.strftime('%d/%m/%Y')})",
        "Itens: " + "; ".join(f"{it['quantity']}x {it['produto']}" for it in itens),
        f"Valor total: {_brl(o['total_brl'])}  ·  Pagamento: {_pagamento(o['payment_method'])}",
    ]
    # order_items.csv não guarda o preço unitário pago — v_pedido_item mostra o preço de
    # TABELA de hoje. Em 2 dos 20 pedidos a soma não fecha com o total (houve desconto na
    # venda). Sem este aviso o agente "confere" a conta e contradiz o próprio total.
    soma_tabela = sum(it["quantity"] * it["preco_tabela"] for it in itens)
    if abs(soma_tabela - o["total_brl"]) > 0.01:
        linhas.append(
            f"Atenção ao valor: a soma dos itens pelo preço de tabela de hoje daria "
            f"{_brl(soma_tabela)}, mas o pedido foi fechado em {_brl(o['total_brl'])}. "
            "Houve desconto aplicado na venda e o sistema não registra o preço unitário "
            "pago — informe o VALOR TOTAL do pedido e não tente recalcular item a item.")
    if o["status"] == "cancelled":
        linhas.append(f"Motivo do cancelamento: {o['notes'] or 'não informado'}")
    if o["estimated_delivery"]:
        linhas.append(f"Previsão de entrega: {date.fromisoformat(o['estimated_delivery']).strftime('%d/%m/%Y')}")
    if o["tracking_code"]:
        linhas.append(f"Código de rastreio: {o['tracking_code']}")
    elif o["status"] in ("pending", "confirmed"):
        linhas.append("Ainda sem código de rastreio (só é gerado no despacho).")
    linhas.append(
        "Obs.: o sistema NÃO registra a data de recebimento, só a da compra. Se o prazo da "
        "política contar a partir do recebimento, pergunte ao cliente quando ele recebeu "
        "antes de dizer se está dentro ou fora do prazo.")
    return "\n".join(linhas)


TOOLS = [buscar_produtos, detalhe_produto, status_pedido, consultar_politica,
         simular_pagamento]
