# Conversas de exemplo

Geradas rodando o agente de verdade (LM Studio no ar):

```bash
python run_examples.py
```

Cada arquivo é uma conversa numa thread nova. As linhas `🔧` mostram quando o agente
consultou dados ou políticas.

Para a cobertura sistemática (20 cenários × 3 rodadas, com taxa de acerto e latência), ver
[`../eval_report.md`](../eval_report.md).

| Arquivo | Cenário |
|---|---|
| `01_catalogo_violoes.md` | Busca no catálogo com filtro de preço + pergunta sobre promoção |
| `02_preco_produto.md` | Preço de um produto específico + preço no PIX |
| `03_info_loja.md` | Endereço, horário e parcelamento (políticas) |
| `04_devolucao_pedido.md` | **Não trivial:** pedido de devolução — o agente confere a identidade, lê a política, percebe que o prazo de arrependimento conta do **recebimento** (data que o sistema não tem), pergunta ao cliente e só então decide |
| `05_fora_de_escopo.md` | Acessório (cordas) + pergunta totalmente fora do escopo (receita) |
