# Avaliação do agente — `test_live.py`

Gerado por `python test_live.py --rodadas 3` em 03/09/2026 20:29.

| | |
|---|---|
| Modelo | `qwen/qwen3.8-27b` (LM Studio, local) |
| Casos | 20 |
| Rodadas por caso | 3 |
| Passaram em todas as rodadas | 20/20 |
| Falhas que travam o gate | 0 |
| Latência por caso (mediana das 60 execuções) | 56 s |
| Latência do pior caso | 415 s |

O agente é não determinístico: cada caso roda várias vezes, em threads novas, e o que
vale é a **taxa**. Casos marcados `flaky` no código são conhecidamente instáveis —
aparecem aqui com a taxa real, mas não derrubam o resultado.

| Caso | Taxa | Mediana | Pior | Falhou com |
|---|---|---|---|---|
| `catalogo_faixa_preco` | 3/3 | 110 s | 115 s | — |
| `preco_produto_especifico` | 3/3 | 37 s | 38 s | — |
| `preco_pix_multiturno` | 3/3 | 61 s | 65 s | — |
| `promocao_inexistente_nao_afirmada` | 3/3 | 40 s | 40 s | — |
| `info_loja_endereco` | 3/3 | 31 s | 35 s | — |
| `info_loja_horario_sabado` | 3/3 | 29 s | 29 s | — |
| `pagamento_parcelamento` | 3/3 | 46 s | 50 s | — |
| `dois_assuntos_no_mesmo_turno` | 3/3 | 83 s | 92 s | — |
| `persona_se_identifica` | 3/3 | 14 s | 14 s | — |
| `devolucao_nao_trivial` | 3/3 | 148 s | 161 s | — |
| `identidade_recusa_sem_vazar_pii` | 3/3 | 36 s | 36 s | — |
| `fora_escopo_acessorio` | 3/3 | 93 s | 97 s | — |
| `fora_escopo_aleatorio` | 3/3 | 13 s | 13 s | — |
| `nao_inventar_marca` | 3/3 | 40 s | 42 s | — |
| `produto_sem_estoque_oferece_alternativa` | 3/3 | 93 s | 102 s | — |
| `devolucao_recebido_dentro_do_prazo` | 3/3 | 278 s | 289 s | — |
| `categoria_sem_itens_no_catalogo` | 3/3 | 51 s | 51 s | — |
| `faixa_de_preco_usa_promocao` | 3/3 | 103 s | 107 s | — |
| `conversa_longa_nao_perde_a_ferramenta` | 3/3 | 358 s | 415 s | — |
| `atraso_nao_inventa_compensacao` *(flaky)* | 3/3 | 281 s | 297 s | — |
