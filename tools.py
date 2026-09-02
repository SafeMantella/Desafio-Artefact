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
from datetime import date

from langchain_core.tools import tool

from config import DATA_REFERENCE_DATE, DB_PATH, POLICIES_PATH


def _norm(s: str) -> str:
    """minúsculas, sem acento — para casar texto de forma robusta."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower().strip()


def _conn() -> sqlite3.Connection:
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

    ordenadas = sorted(pontos, key=lambda s: pontos[s], reverse=True)
    escolhidas = ordenadas[:2] if len(ordenadas) > 1 and pontos[ordenadas[1]] >= pontos[ordenadas[0]] * 0.6 else ordenadas[:1]
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
}

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
def buscar_produtos(termo: str = "", categoria: str = "", preco_min: float | None = None,
                    preco_max: float | None = None, apenas_disponiveis: bool = True) -> str:
    """Busca instrumentos no catálogo da loja. Use para perguntas sobre o que a loja tem,
    opções dentro de um preço, disponibilidade de um tipo de instrumento, etc.

    termo: texto livre para casar no nome (ex.: "Yamaha", "dreadnought", "nylon").
    categoria: tipo de instrumento (violão, guitarra, baixo, bateria, teclado, ukulele).
    preco_min / preco_max: faixa de preço em reais (preço de tabela).
    apenas_disponiveis: se True (padrão), só lista o que está em estoque e à venda.

    Retorna uma lista com preço de tabela, preço promocional (se houver promoção ativa) e
    preço à vista no PIX. Não invente itens: use só o que esta ferramenta retornar.
    """
    sql = "SELECT * FROM v_produto WHERE 1=1"
    args: list = []
    if apenas_disponiveis:
        sql += " AND disponivel = 1"
    if preco_min is not None:
        sql += " AND preco_tabela >= ?"; args.append(preco_min)
    if preco_max is not None:
        sql += " AND preco_tabela <= ?"; args.append(preco_max)

    cat_alvo = _CATEGORIAS.get(_norm(categoria)) if categoria else None
    if cat_alvo:
        sql += " AND categoria = ?"; args.append(cat_alvo)

    with _conn() as c:
        rows = c.execute(sql + " ORDER BY preco_tabela", args).fetchall()

    # termo: casa cada palavra (sem acento) no nome; se não veio categoria explícita,
    # também tenta interpretar o termo como categoria.
    if termo:
        if not cat_alvo:
            cat_do_termo = next((v for k, v in _CATEGORIAS.items() if k in _norm(termo)), None)
            if cat_do_termo:
                rows = [r for r in rows if r["categoria"] == cat_do_termo]
        palavras = [p for p in _norm(termo).split() if p not in _CATEGORIAS]
        for p in palavras:
            rows = [r for r in rows if p in _norm(f"{r['name']} {r['specs'] or ''}")]

    if not rows:
        return ("Não encontrei nenhum instrumento com esses critérios. "
                "Talvez ajustando a faixa de preço ou a categoria.")

    cabecalho = f"{len(rows)} instrumento(s) encontrado(s):" if len(rows) <= 20 else \
        f"{len(rows)} instrumentos — mostrando os 20 mais baratos:"
    return cabecalho + "\n" + "\n".join(f"- {_linha_produto(r)}" for r in rows[:20])


@tool
def detalhe_produto(nome_ou_id: str) -> str:
    """Ficha completa de UM instrumento: preço de tabela, preço à vista no PIX, promoção
    ativa, especificações, disponibilidade e descrição.

    nome_ou_id: o nome (ou parte dele) ou o id numérico do produto. Se houver ambiguidade,
    a ferramenta devolve a lista de candidatos para você pedir mais detalhes ao cliente.
    """
    with _conn() as c:
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
    linhas.append(f"À vista no PIX: {_brl(r['preco_a_vista_pix'])}"
                  + ("" if r["promo_ativa_pct"] else "  (5% de desconto sobre a tabela)"))
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


def _identidade_confere(identificador: str, nome: str, email: str) -> bool:
    ident = _norm(identificador)
    if not ident:
        return False
    if ident == _norm(email):
        return True
    tokens = [t for t in ident.split() if len(t) > 1]
    nome_norm = _norm(nome)
    return bool(tokens) and all(t in nome_norm for t in tokens)


@tool
def status_pedido(order_id: int, identificador: str) -> str:
    """Consulta o andamento de um pedido. Exige verificação leve de identidade (LGPD): só
    retorna os dados se `identificador` bater com o nome OU o e-mail do cliente do pedido.

    order_id: número do pedido.
    identificador: nome completo (ou nome e sobrenome) ou e-mail do cliente, informado por ele.
    Se o cliente ainda não informou, PEÇA antes de chamar esta ferramenta.

    Retorna status, itens, valor, forma de pagamento, previsão de entrega, código de
    rastreio e há quantos dias o pedido foi feito (para aplicar prazos de troca/devolução).
    """
    with _conn() as c:
        o = c.execute("SELECT * FROM orders WHERE order_id = ?", [order_id]).fetchone()
        if not o:
            return f"Não encontrei nenhum pedido com o número {order_id}."
        cli = c.execute("SELECT * FROM customers WHERE customer_id = ?",
                        [o["customer_id"]]).fetchone()
        itens = c.execute("SELECT quantity, produto, preco_tabela FROM v_pedido_item "
                          "WHERE order_id = ?", [order_id]).fetchall()

    if not _identidade_confere(identificador, cli["name"] if cli else "", cli["email"] if cli else ""):
        return (f"Por segurança, não posso liberar os dados do pedido {order_id}: o nome/e-mail "
                "informado não confere com o cadastro. Pode confirmar o nome completo ou o "
                "e-mail usado na compra?")

    d = date.fromisoformat(o["order_date"])
    dias = (DATA_REFERENCE_DATE - d).days
    linhas = [
        f"Pedido {order_id} — {_STATUS_PEDIDO.get(o['status'], o['status'])}",
        f"Cliente: {cli['name']}",
        f"Data do pedido: {d.strftime('%d/%m/%Y')} (há {dias} dias; hoje = "
        f"{DATA_REFERENCE_DATE.strftime('%d/%m/%Y')})",
        "Itens: " + "; ".join(f"{it['quantity']}x {it['produto']}" for it in itens),
        f"Valor total: {_brl(o['total_brl'])}  ·  Pagamento: {_pagamento(o['payment_method'])}",
    ]
    if o["status"] == "cancelled":
        linhas.append(f"Motivo do cancelamento: {o['notes'] or 'não informado'}")
    if o["estimated_delivery"]:
        linhas.append(f"Previsão de entrega: {date.fromisoformat(o['estimated_delivery']).strftime('%d/%m/%Y')}")
    if o["tracking_code"]:
        linhas.append(f"Código de rastreio: {o['tracking_code']}")
    elif o["status"] in ("pending", "confirmed"):
        linhas.append("Ainda sem código de rastreio (só é gerado no despacho).")
    return "\n".join(linhas)


TOOLS = [buscar_produtos, detalhe_produto, status_pedido, consultar_politica]
