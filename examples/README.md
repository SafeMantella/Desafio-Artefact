# Conversas de exemplo

Geradas rodando o agente de verdade (LM Studio no ar):

```bash
python run_examples.py
```

Cada arquivo é uma conversa numa thread nova. As linhas `🔧` mostram quando o agente
consultou dados ou políticas.

| Arquivo | Cenário |
|---|---|
| `01_catalogo_violoes.md` | Busca no catálogo com filtro de preço + pergunta sobre promoção |
| `02_preco_produto.md` | Preço de um produto específico + preço no PIX |
| `03_info_loja.md` | Endereço, horário e parcelamento (políticas) |
| `04_devolucao_pedido.md` | **Não trivial:** pedido de devolução — o agente confere a identidade, olha há quantos dias foi a compra e aplica a política de arrependimento |
| `05_fora_de_escopo.md` | Acessório (cordas) + pergunta totalmente fora do escopo (receita) |
