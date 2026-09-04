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


# palavra-chave (normalizada, sem acento) -> números das seções
#
# É uma LISTA e não uma seção só porque há palavra que pertence a duas de verdade:
# "chegou quebrado" é §5.2 (avaria de transporte — recusar o recebimento, tem seguro) OU
# §4.2 (defeito de fabricação — troca em 30 dias), e só o cliente sabe qual. Devolver as
# duas seções deixa o agente PERGUNTAR qual é o caso em vez de chutar um procedimento.
_KEYWORDS: dict[str, list[str]] = {}
for _sec, _palavras in {
    "1": ["sobre a loja", "sobre a empresa", "empresa", "cnpj", "razao social", "endereco",
          "onde fica", "onde e", "localizacao", "local", "catalogo", "missao",
          "acessorio", "acessorios", "corda", "cordas", "palheta", "palhetas", "cabo", "cabos",
          "case", "cases", "pedal", "pedais", "amplificador", "amplificadores", "caixa de som",
          "vende", "vendem", "trabalha com", "tem a venda"],
    "2": ["horario", "hora", "que horas", "abre", "abrem", "fecha", "fecham", "funcionamento",
          "aberto", "domingo", "sabado", "feriado", "expediente", "atendimento presencial",
          "fora do expediente"],
    "3": ["pagamento", "forma de pagamento", "pagar", "pix", "cartao", "credito", "debito",
          "boleto", "parcelamento", "parcela", "parcelar", "juros", "a vista", "sem juros",
          "combinar", "duas formas", "bandeiras", "compensacao"],
    "4": ["troca", "trocar", "devolucao", "devolver", "devolvo", "arrependimento", "arrependi",
          "reembolso", "reembolsar", "estorno", "defeito", "veio com defeito", "venda final",
          "nao elegivel", "prazo de troca", "7 dias", "30 dias", "preferencia", "tamanho",
          "troca de cor", "outra cor", "setup", "regulagem", "boquilha", "boquilhas", "higiene",
          # ambíguas: podem ser defeito de fábrica (§4.2) ou avaria de transporte (§5.2).
          # Estão nas DUAS listas de propósito — ver o comentário do _KEYWORDS.
          "quebrado", "quebrada", "quebrou", "danificado", "danificada", "chegou quebrado",
          "veio quebrado", "chegou quebrada", "trincado", "trincada"],
    "5": ["frete", "entrega", "entregar", "envio", "enviar", "correios", "sedex", "pac",
          "jadlog", "rastreamento", "rastreio", "rastrear", "codigo de rastreamento", "motoboy",
          "prazo de entrega", "quando chega", "cep", "frete gratis", "regiao metropolitana",
          "outras cidades",
          # §5.2 (seguro/avaria) e §5.3 (despacho) — sem estas o cliente que teve problema
          # no transporte caía no fallback "não identifiquei o tópico", ou pior, na §4.
          "avaria", "avariado", "avariada", "amassado", "amassada", "caixa amassada",
          "extravio", "extraviado", "sumiu", "nao chegou", "seguro", "despacho", "despachado",
          "grande porte", "cotacao", "transportadora",
          "quebrado", "quebrada", "quebrou", "danificado", "danificada", "chegou quebrado",
          "veio quebrado", "chegou quebrada", "trincado", "trincada"],
    "6": ["promocao", "promocoes", "promo", "desconto", "black friday", "aniversario da loja",
          "volta as aulas", "queima de estoque", "semana do musico", "cupom", "oferta",
          "liquidacao", "rain check", "cumulativo", "cumulativa", "cumulatividade",
          "reserva de preco"],
    "7": ["whatsapp", "atendimento", "contato", "falar com atendente", "telefone", "numero da loja",
          "reclamacao", "reclamar", "fora de estoque", "descontinuado", "sac", "ouvidoria",
          "falar com humano", "3321-4500", "3341-4444"],
    "8": ["garantia", "defeito de fabricacao", "90 dias", "fabricante", "cobertura",
          "o que cobre", "nao cobre", "assistencia", "desgaste", "trastes", "feltros",
          "garantia legal", "garantia do fabricante", "certificado de garantia",
          "assistencia tecnica", "dano estetico"],
    "9": ["lgpd", "privacidade", "protecao de dados", "dados pessoais", "excluir meus dados",
          "exclusao de dados", "meus dados", "lei geral de protecao de dados", "13.709",
          "excluir dados", "exclusao", "compartilhamento", "marketing", "consentimento"],
    "10": ["disposicoes finais", "gerencia", "atualizacao do manual", "documento interno",
           "casos omissos", "duvidas sobre politica"],
}.items():
    for _p in _palavras:
        _KEYWORDS.setdefault(_norm(_p), []).append(_sec)

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
    for palavra, secs in _KEYWORDS.items():
        if re.search(rf"\b{re.escape(palavra)}\b", q):  # palavra inteira, não "vende" em "vendedor"
            for sec in secs:  # uma palavra pode pontuar duas seções (ex.: "quebrado")
                pontos[sec] = pontos.get(sec, 0) + len(palavra)  # match específico pesa mais
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


# §5.2: "instrumentos de grande porte (baterias acústicas, pianos digitais, contrabaixos)
# podem exigir frete especial com cotação individual". Casa pelo NOME do produto e não pela
# categoria, de propósito: a categoria "Baixos" só tem baixo ELÉTRICO (porte de guitarra) e
# "Teclados e Pianos" só tem sintetizador — marcar as duas como grande porte seria mandar o
# cliente pedir cotação à toa. Hoje casam os 3 kits de bateria acústica; os outros termos
# ficam prontos para quando o catálogo tiver o item.
_GRANDE_PORTE = ("bateria acustica", "piano digital", "contrabaixo acustico")


def _e_grande_porte(nome: str) -> bool:
    return any(t in _norm(nome) for t in _GRANDE_PORTE)


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
    if _e_grande_porte(r["name"]):
        partes.append("GRANDE PORTE: fora de Campo Grande o frete pode exigir cotação "
                      "individual (política 5.2)")
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
    if _e_grande_porte(r["name"]):
        linhas.append(
            "Frete: instrumento de GRANDE PORTE. Em Campo Grande e região vale a regra normal; "
            "para outras cidades pode exigir frete especial com cotação individual (política "
            "5.2). Avise o cliente antes que ele pergunte e ofereça o contato da equipe.")
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
_PRAZO_CG = "1 a 3 dias úteis"                                # §5.1
# §5.1 diz "grátis ACIMA de R$ 500,00" e "ABAIXO de R$ 500,00, taxa fixa" — os R$ 500,00
# exatos ficam de fora das duas frases. Adotado `>` (500,00 redondo paga frete), que é a
# leitura literal de "acima de". Suposição registrada no README e no topo do policies.md.
_COMBINACAO_ACIMA_DE = 2000.0                                 # §3.1: PIX + cartão na mesma compra


def _frete_e_total(subtotal: float) -> tuple[float, float]:
    """(frete, total) para a região metropolitana, a partir do SUBTOTAL que o cliente paga.

    A §5.1 fala em "pedidos acima de R$ 500,00" sem dizer se é antes ou depois dos descontos.
    Adotado DEPOIS: é o subtotal que o cliente efetivamente paga, como faz e-commerce real.
    A consequência prática está no `simular_pagamento`: um item de R$ 520 passa do limite no
    cartão, mas no PIX cai para R$ 494 e volta a pagar frete — e aí o cartão sai mais barato.
    """
    gratis_acima, taxa = _FRETE_CG
    frete = 0.0 if subtotal > gratis_acima else taxa
    return frete, subtotal + frete


def _max_parcelas(valor: float) -> tuple[int, float]:
    """(nº máximo de parcelas, valor da parcela), respeitando o mínimo de cada faixa."""
    minimo = lambda n: next((m for ate, m in _FAIXAS_PARCELAMENTO if n <= ate), None)
    for n in range(_FAIXAS_PARCELAMENTO[-1][0], 1, -1):
        if valor / n >= minimo(n):
            return n, valor / n
    return 1, valor


@tool
def simular_pagamento(preco_de_tabela: float, ja_esta_em_promocao: bool = False,
                      entrega_em_campo_grande: bool = False, valor_no_pix: float = 0) -> str:
    """Calcula as formas de pagamento para um valor: preço à vista no PIX, em quantas vezes
    dá para parcelar e quanto fica cada parcela. Opcionalmente, o frete metropolitano.

    Use SEMPRE que a pergunta envolver CONTA sobre um valor concreto: "dá pra parcelar em
    12x?", "quanto fica a parcela?", "quanto sai no PIX?", "pago frete nessa compra?".
    NUNCA faça essa conta de cabeça.
    Para as regras gerais de pagamento, sem um valor na mesa, use consultar_politica.

    preco_de_tabela: o valor a pagar, ANTES de qualquer desconto de pagamento. Pode ser o
        preço de tabela de um produto, a soma de vários, ou simplesmente o valor que o
        cliente informou ("uma compra de R$ 549") — nesse caso use o número que ele deu,
        sem precisar saber qual é o produto.
        NUNCA passe o valor "à vista no PIX" que outra ferramenta já devolveu: é ESTA que
        aplica o desconto do PIX, e passar o preço já descontado desconta duas vezes.
        Se o produto tem promoção ativa, passe o preço PROMOCIONAL e marque
        `ja_esta_em_promocao=True`.
    ja_esta_em_promocao: True quando o valor acima já é um preço promocional. O desconto do
        PIX não incide sobre preço promocional (política 6.2), e a ferramenta respeita isso.
    entrega_em_campo_grande: True só se o cliente disse que é em Campo Grande ou região
        metropolitana. Se ele não disse, deixe False e pergunte a cidade.
    valor_no_pix: só para COMBINAR formas de pagamento, o que a política permite acima de
        R$ 2.000,00. Preencha com quanto o cliente quer pagar no PIX; o resto vai no
        cartão e a ferramenta calcula as duas partes. Deixe 0 se ele não pediu combinação.
    """
    log.debug("simular_pagamento(preco=%s, promo=%s, cg=%s)",
              preco_de_tabela, ja_esta_em_promocao, entrega_em_campo_grande)
    if not preco_de_tabela or preco_de_tabela <= 0:
        return "Preciso do valor da compra para calcular. Confirme o produto com o cliente."

    # §3.1: combinar formas só é permitido acima de R$ 2.000,00
    if valor_no_pix and valor_no_pix > 0:
        if preco_de_tabela <= _COMBINACAO_ACIMA_DE:
            return (f"Combinar formas de pagamento só é permitido em compras acima de "
                    f"{_brl(_COMBINACAO_ACIMA_DE)}, e esta é de {_brl(preco_de_tabela)}. "
                    "Explique isso ao cliente e ofereça uma forma só.")
        if valor_no_pix >= preco_de_tabela:
            return ("O valor no PIX tem que ser MENOR que o total — senão não é combinação, "
                    "é pagamento à vista no PIX. Confirme com o cliente quanto ele quer "
                    "colocar em cada forma.")
        desconto = 0.0 if ja_esta_em_promocao else round(valor_no_pix * _PIX_DESCONTO, 2)
        no_cartao = round(preco_de_tabela - valor_no_pix, 2)
        n_c, parc_c = _max_parcelas(no_cartao)
        linhas = [
            f"Combinação de formas para {_brl(preco_de_tabela)} (permitida acima de "
            f"{_brl(_COMBINACAO_ACIMA_DE)}):",
            f"- No PIX: {_brl(valor_no_pix)}" + (
                f" com {int(_PIX_DESCONTO * 100)}% de desconto -> paga {_brl(valor_no_pix - desconto)}"
                if desconto else " (sem os 5%: o preço já é promocional, política 6.2)"),
            f"- No cartão: {_brl(no_cartao)}" + (
                f" em até {n_c}x sem juros de {_brl(parc_c)}" if n_c > 1
                else " — só à vista, nesse valor a parcela ficaria abaixo do mínimo"),
            f"- TOTAL a pagar: {_brl(preco_de_tabela - desconto)}"
            + (f" (economia de {_brl(desconto)} na parte do PIX)" if desconto else ""),
        ]
        return "\n".join(linhas)

    n, parcela = _max_parcelas(preco_de_tabela)
    pct = int(_PIX_DESCONTO * 100)
    linhas = [f"Simulação para {_brl(preco_de_tabela)}:"]
    if ja_esta_em_promocao:
        linhas.append(f"- À vista no PIX: {_brl(preco_de_tabela)} — o mesmo valor. Os {pct}% do "
                      "PIX NÃO incidem sobre preço promocional (política 6.2); o desconto da "
                      "promoção já está aplicado aqui.")
    else:
        linhas.append(f"- À vista no PIX: {_brl(preco_de_tabela * (1 - _PIX_DESCONTO))} "
                      f"({pct}% de desconto sobre a tabela).")
    if n == 1:
        linhas.append("- Cartão de crédito: só à vista. Nesse valor, mesmo em 2x a parcela "
                      "ficaria abaixo do mínimo permitido pela política.")
    else:
        linhas.append(f"- Cartão de crédito: até {n}x sem juros, de {_brl(parcela)} cada. "
                      f"Acima de {n}x a parcela cairia abaixo do mínimo da faixa.")

    if preco_de_tabela > _COMBINACAO_ACIMA_DE:
        linhas.append(f"- Acima de {_brl(_COMBINACAO_ACIMA_DE)} dá para COMBINAR formas "
                      "(ex.: parte no PIX, parte no cartão). Ofereça ao cliente; se ele "
                      "quiser, pergunte quanto vai no PIX e chame esta ferramenta de novo "
                      "com valor_no_pix preenchido.")

    gratis_acima, _ = _FRETE_CG
    if entrega_em_campo_grande:
        # O limite de frete grátis vale sobre o subtotal PAGO (ver _frete_e_total). Como o
        # PIX derruba o subtotal em 5%, uma compra perto de R$ 500 pode ter frete diferente
        # em cada forma de pagamento — quando isso acontece, as duas contas saem.
        no_pix = (preco_de_tabela if ja_esta_em_promocao
                  else round(preco_de_tabela * (1 - _PIX_DESCONTO), 2))
        f_pix, t_pix = _frete_e_total(no_pix)
        f_car, t_car = _frete_e_total(preco_de_tabela)
        rotulo = lambda f: "grátis" if not f else _brl(f)
        if f_pix == f_car:
            linhas.append(f"- Frete em Campo Grande e região: {rotulo(f_car)}"
                          + (f" (o limite é subtotal acima de {_brl(gratis_acima)})"
                             if not f_car else
                             f" — seria grátis com subtotal acima de {_brl(gratis_acima)}"))
        else:
            barato = "no PIX" if t_pix < t_car else "no cartão"
            linhas.append(
                f"- Frete em Campo Grande e região: DEPENDE da forma de pagamento. O limite "
                f"de {_brl(gratis_acima)} vale sobre o subtotal PAGO, já com desconto. "
                f"No PIX: {_brl(no_pix)} + frete {rotulo(f_pix)} = {_brl(t_pix)}. "
                f"No cartão: {_brl(preco_de_tabela)} + frete {rotulo(f_car)} = {_brl(t_car)}. "
                f"Apresente as DUAS ao cliente: aqui sai mais barato {barato}.")
        linhas.append(f"- Prazo em Campo Grande e região: {_PRAZO_CG}, por motoboy próprio — "
                      "o cliente é contactado por telefone antes da entrega.")
    else:
        linhas.append(
            "- Frete: para fora de Campo Grande NÃO tenho como calcular nesta ferramenta — "
            "depende do CEP, do peso e das dimensões. Chame a ferramenta calcular_frete informando "
            "o CEP do cliente. Se for instrumento de grande porte, passe o WhatsApp e e-mail da loja.")
    return "\n".join(linhas)


# ponytail: nome distinto de `_GRANDE_PORTE` (linha ~221) de propósito — aquele é
# específico por design (baixo elétrico e sintetizador não contam); este é mais amplo
# porque calcular_frete recebe texto livre do cliente ("bateria", "contrabaixo") sem o
# contexto de nome de produto exato. Reusar o mesmo identificador causava shadowing: o
# Python resolve o global no momento da CHAMADA, então `_e_grande_porte()` (que só deveria
# ler a lista específica) acabava lendo esta lista ampla — "Yamaha Bass 3X" e "Korg Synth 1
# Pro" viravam "grande porte" incorretamente em calcular_frete.
#
# "bateria" sozinho é seguro: os 3 únicos produtos da categoria "Baterias e Percussão" são
# todos "Bateria Acústica ..." (conferido no catálogo). Já "baixo" e "piano" soltos NÃO
# entram — a categoria "Baixos" só tem baixo ELÉTRICO (porte de guitarra) e a categoria
# "Teclados e Pianos" só tem sintetizador; "piano" solto também casaria por substring com o
# nome da própria categoria ("Teclados e Pianos"), marcando sintetizador à toa.
# "contrabaixo" solto fica: em PT-BR é sempre o instrumento acústico grande (contrabaixo
# ≠ baixo elétrico), coerente com o exemplo do docstring da ferramenta.
_GRANDE_PORTE_FRETE = ("bateria acustica", "bateria", "piano digital", "contrabaixo")


# Dimensões (C x L x A em cm) e pesos (kg) padronizados de embalagem por categoria (§5.2).
# Adotados para viabilizar cálculos determinísticos quando o produto não possui medidas no catálogo:
# chave: (comprimento_cm, largura_cm, altura_cm, peso_kg, rótulo)
DIMENSOES_PADRAO = {
    "violao": (105.0, 45.0, 15.0, 3.5, "Violão"),
    "guitarra": (105.0, 40.0, 12.0, 4.5, "Guitarra"),
    "teclado": (105.0, 40.0, 15.0, 6.0, "Teclado / Arranjador"),
    "ukulele": (60.0, 25.0, 12.0, 1.0, "Ukulele"),
    "sopro": (60.0, 25.0, 18.0, 2.5, "Instrumento de Sopro"),
    "cordas": (80.0, 30.0, 15.0, 2.5, "Cordas Orquestrais"),
    "padrao": (90.0, 35.0, 15.0, 3.0, "Instrumento (Padrão)"),
}


@tool
def calcular_frete(cep: str, produto_ou_categoria: str = "",
                   peso_kg: float = 0.0, comprimento_cm: float = 0.0,
                   largura_cm: float = 0.0, altura_cm: float = 0.0) -> str:
    """Calcula o valor do frete e prazos para entregas fora de Campo Grande com base no CEP,
    peso e dimensões do produto (política 5.2). Se peso ou dimensões não forem informados,
    adota o padrão de embalagem da categoria do instrumento.

    ATENÇÃO: Instrumentos de grande porte (baterias acústicas, pianos digitais, contrabaixos)
    exigem frete especial com cotação individual. A ferramenta detecta esses itens e orienta
    a passar WhatsApp e e-mail da loja para cotação com atendente humano.

    cep: CEP de destino informado pelo cliente (ex.: '01310-100' ou '01310100').
    produto_ou_categoria: nome do instrumento ou categoria (ex.: 'violão', 'Tagima T-635',
        'bateria acústica', 'contrabaixo', 'teclado').
    peso_kg: peso do produto em kg (se 0, usa o padrão da categoria).
    comprimento_cm: comprimento em cm (se 0, usa o padrão da categoria).
    largura_cm: largura em cm.
    altura_cm: altura em cm.
    """
    log.debug("calcular_frete(cep=%r, prod=%r, peso=%s)", cep, produto_ou_categoria, peso_kg)
    cep_digitos = re.sub(r"\D", "", cep or "")
    if len(cep_digitos) < 5:
        return "Preciso de um CEP válido com pelo menos 5 dígitos para calcular o frete."

    alvo = _norm(produto_ou_categoria)
    # Se o modelo foi informado mas não traz a categoria diretamente, busca no catálogo
    if alvo and not any(k in alvo for k in ("violao", "violoes", "guitarra", "ukulele", "teclado", "sopro", "flauta", "sax", "corda")):
        with closing(_conn()) as c:
            row = c.execute(
                "SELECT categoria FROM v_produto WHERE LOWER(name) LIKE ? OR LOWER(description) LIKE ? LIMIT 1",
                [f"%{alvo}%", f"%{alvo}%"]
            ).fetchone()
            if row and row["categoria"]:
                alvo = f"{alvo} {_norm(row['categoria'])}"

    # §5.2: Instrumentos de grande porte exigem cotação individual com atendente humano
    if any(p in alvo for p in _GRANDE_PORTE_FRETE) or peso_kg > 25 or max(comprimento_cm, largura_cm, altura_cm) > 150:
        return (
            "Instrumento de grande porte (baterias acústicas, pianos digitais, contrabaixos): "
            "exige frete especial com cotação individual e não pode ser calculado automaticamente.\n"
            "Oriente o cliente a falar diretamente com a equipe para cotação humana:\n"
            "- WhatsApp: (67) 3341-4444\n"
            "- E-mail: contato@emporiodamusica.com.br"
        )

    # Entregas na região metropolitana de Campo Grande (MS). Valores vêm de _FRETE_CG /
    # _PRAZO_CG (não literais): são as mesmas constantes que simular_pagamento usa e que
    # test_simular_pagamento confere contra o texto de policies.md — sem isso, esta string
    # divergiria em silêncio se o manual mudasse o valor do frete ou do prazo.
    if cep_digitos.startswith(("790", "7910", "7911", "7912", "7913", "7914", "7915")):
        gratis_acima, taxa = _FRETE_CG
        return (
            f"CEP {cep}: Destino na Região Metropolitana de Campo Grande (§5.1).\n"
            f"- Entrega por motoboy próprio em {_PRAZO_CG}.\n"
            f"- Taxa fixa de {_brl(taxa)} (grátis para compras acima de {_brl(gratis_acima)}).\n"
            "- O cliente será contactado por telefone antes da entrega."
        )

    # Resolução de dimensões e peso: usa dados informados ou aplica pacote padronizado por categoria
    tipo_pacote = "padrao"
    if "ukulele" in alvo:
        tipo_pacote = "ukulele"
    elif "violao" in alvo or "violoes" in alvo:
        tipo_pacote = "violao"
    elif "guitarra" in alvo:
        tipo_pacote = "guitarra"
    elif "teclado" in alvo:
        tipo_pacote = "teclado"
    elif any(s in alvo for s in ("sopro", "flauta", "sax", "clarinete", "trompete")):
        tipo_pacote = "sopro"
    elif any(s in alvo for s in ("corda", "violino", "viola", "violoncelo")):
        tipo_pacote = "cordas"

    def_c, def_l, def_a, def_peso, rotulo = DIMENSOES_PADRAO[tipo_pacote]
    c_cm = comprimento_cm if comprimento_cm > 0 else def_c
    l_cm = largura_cm if largura_cm > 0 else def_l
    a_cm = altura_cm if altura_cm > 0 else def_a
    peso = peso_kg if peso_kg > 0 else def_peso

    vol = (c_cm * l_cm * a_cm) / 6000.0
    peso_cobrado = max(peso, vol, 1.0)

    # Multiplicador de distância regional a partir de Campo Grande/MS (prefixo 7)
    regiao_prefixo = cep_digitos[0]
    mult = 1.0
    if regiao_prefixo in "0123":  # SP, RJ, ES, MG (Sudeste)
        mult = 1.15
    elif regiao_prefixo in "89":  # PR, SC, RS (Sul)
        mult = 1.20
    elif regiao_prefixo in "45":  # Nordeste
        mult = 1.40
    elif regiao_prefixo == "6":   # Norte
        mult = 1.60
    else:                         # Centro-Oeste / DF (7)
        mult = 1.0

    pac_valor = round((28.0 + peso_cobrado * 4.2) * mult, 2)
    sedex_valor = round((52.0 + peso_cobrado * 8.5) * mult, 2)
    jadlog_valor = round((35.0 + peso_cobrado * 5.5) * mult, 2)

    return (
        f"Cotação de frete para o CEP {cep} — Política 5.2:\n"
        f"- Pacote: {rotulo} ({c_cm:.0f}×{l_cm:.0f}×{a_cm:.0f} cm | peso real: {peso:.1f} kg | "
        f"peso cúbico: {vol:.1f} kg → cobrado: {peso_cobrado:.1f} kg)\n"
        f"- PAC (Correios): {_brl(pac_valor)} | Prazo estimado: 5 a 12 dias úteis | Rastreamento: Sim | Seguro: Incluído\n"
        f"- SEDEX (Correios): {_brl(sedex_valor)} | Prazo estimado: 2 a 5 dias úteis | Rastreamento: Sim | Seguro: Incluído\n"
        f"- Jadlog (.package): {_brl(jadlog_valor)} | Prazo estimado: 3 a 8 dias úteis | Rastreamento: Sim | Seguro: Incluído\n\n"
        "Nota: Todos os envios incluem seguro contra extravios e danos. "
        "Em caso de avaria no transporte, o cliente deve recusar o recebimento e contatar a loja imediatamente."
    )



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
            f"{_brl(soma_tabela)}, e o pedido foi fechado em {_brl(o['total_brl'])}. A "
            "diferença vem do que entrou no fechamento (desconto de pagamento, promoção da "
            "época, frete) e o sistema não guarda o preço unitário pago. Informe o VALOR "
            "TOTAL do pedido e não recalcule item a item.")
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


# ---------------------------------------------------------------------------
# Identificação do cliente (opcional) — personaliza o atendimento, não autentica
# ---------------------------------------------------------------------------
# Fronteira de segurança, explícita: esta tool NÃO é um login. Ela só confirma que um
# e-mail pertence a alguém do cadastro e devolve o suficiente para cumprimentar pelo nome
# (§7.2: "cumprimentar pelo nome, se disponível"). Dado de pedido continua saindo apenas
# pelo status_pedido, que exige número do pedido + e-mail.
#
# Por que ela pode citar um pedido EM TRÂNSITO sem afrouxar nada: `order_id` é sequencial
# de 1 a 20 (limitação já documentada no README), então quem tem o e-mail já consegue
# enumerar os pedidos no status_pedido. O e-mail é, na prática, o fator único desde antes
# desta tool. Citar o pedido a caminho não amplia a exposição — só troca uma varredura
# silenciosa por um atendimento útil.


@tool
def identificar_cliente(email: str) -> str:
    """Verifica se um e-mail pertence a um cliente já cadastrado, para personalizar o
    atendimento. NÃO é autenticação e NÃO libera dados de pedido — para isso, status_pedido.

    Use quando o cliente oferecer o e-mail espontaneamente, ou logo depois de convidá-lo a
    se identificar na saudação. NUNCA exija o e-mail para responder preço, catálogo,
    horário, política ou qualquer coisa que não seja pessoal: a identificação é opcional.

    email: o e-mail que o cliente informou, exatamente como veio.

    Retorna o primeiro nome (para o cumprimento), a cidade (útil para o frete) e se há
    pedidos — ou a instrução de tratar como cliente novo.
    """
    log.debug("identificar_cliente(dominio=%r)", email.split("@")[-1] if "@" in email else "?")
    if "@" not in (email or ""):
        return ("Isso não parece um e-mail. Não insista: a identificação é opcional — "
                "siga o atendimento normalmente e só peça o e-mail se a conversa chegar "
                "em pedido ou histórico.")

    with closing(_conn()) as c:
        cli = c.execute("SELECT * FROM customers WHERE LOWER(TRIM(email)) = ?",
                        [_norm(email)]).fetchone()
        if not cli:
            return ("Não há cadastro com esse e-mail. Trate como CLIENTE NOVO: dê as boas-vindas, "
                    "pergunte como pode chamá-lo e siga o atendimento normalmente. Não afirme "
                    "que criou cadastro — este sistema não cadastra clientes.")
        pedidos = c.execute(
            "SELECT order_id, status, order_date FROM orders WHERE customer_id = ? "
            "ORDER BY order_date DESC", [cli["customer_id"]]).fetchall()

    primeiro = cli["name"].split()[0]
    linhas = [f"Cliente cadastrado: {cli['name']}. Chame-o de {primeiro} (só o primeiro nome).",
              f"Cidade: {cli['city']}."]
    if _norm(cli["city"]) == "campo grande":
        linhas.append("É Campo Grande: ao usar simular_pagamento, passe "
                      "entrega_em_campo_grande=True sem precisar perguntar a cidade.")
    else:
        linhas.append("Fora de Campo Grande: o frete não é calculável (depende de CEP, peso "
                      "e dimensões) — use as regras da política de frete.")

    if not pedidos:
        linhas.append("Ainda NÃO tem nenhum pedido. Cumprimente pelo nome e trate como quem "
                      "ainda vai fazer a primeira compra — não invente histórico de compras.")
    else:
        ultimo = pedidos[0]
        linhas.append(f"Tem {len(pedidos)} pedido(s); o mais recente é de "
                      f"{date.fromisoformat(ultimo['order_date']).strftime('%d/%m/%Y')}.")
        transito = [p for p in pedidos if p["status"] in ("shipped", "confirmed", "pending")]
        if transito:
            p0 = transito[0]
            linhas.append(f"O pedido {p0['order_id']} está '{_STATUS_PEDIDO.get(p0['status'], p0['status'])}' "
                          "— ofereça acompanhar. Para dar QUALQUER detalhe (itens, valor, "
                          "rastreio) chame status_pedido com o número e este mesmo e-mail.")
        else:
            linhas.append("Nenhum pedido em andamento. Se ele perguntar de um pedido antigo, "
                          "peça o número e use status_pedido.")
    return "\n".join(linhas)


TOOLS = [buscar_produtos, detalhe_produto, status_pedido, consultar_politica,
         simular_pagamento, identificar_cliente, calcular_frete]
