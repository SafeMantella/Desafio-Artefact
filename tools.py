"""Tools do agente. SQL sempre parametrizado; regras de política vêm do texto de policies.md.

- consultar_politica(topico)                      -> seção(ões) do manual de políticas
- buscar_produtos(...)                            -> catálogo (Parte 3)
- detalhe_produto(nome_ou_id)                     -> ficha de um produto (Parte 3)
- status_pedido(order_id, identificador)          -> pedido, com verificação leve (Parte 3)
"""
import re
import sqlite3
import unicodedata

from langchain_core.tools import tool

from config import DB_PATH, POLICIES_PATH


def _norm(s: str) -> str:
    """minúsculas, sem acento — para casar texto de forma robusta."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower().strip()


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
        m = re.match(r"^##\s+(\d+)\.\s", linha)
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
