# Avaliação do agente — `test_live.py`

Gerado por `python test_live.py --rodadas 3` em 04/09/2026 04:47.

| | |
|---|---|
| Modelo | `mlx-qwen3.5-9b-claude-4.6-opus-reasoning-distilled` (LM Studio, local) |
| Casos | 29 |
| Rodadas por caso | 3 |
| Passaram em todas as rodadas | 28/29 |
| Falhas que travam o gate | 1 |
| Latência por caso (mediana das 87 execuções) | 31 s |
| Latência do pior caso | 187 s |

O agente é não determinístico: cada caso roda várias vezes, em threads novas, e o que
vale é a **taxa**. Casos marcados `flaky` no código são conhecidamente instáveis —
aparecem aqui com a taxa real, mas não derrubam o resultado.

| Caso | Taxa | Mediana | Pior | Falhou com |
|---|---|---|---|---|
| `catalogo_faixa_preco` | 3/3 | 34 s | 52 s | — |
| `preco_produto_especifico` | 3/3 | 16 s | 32 s | — |
| `preco_pix_multiturno` | 3/3 | 49 s | 53 s | — |
| `promocao_inexistente_nao_afirmada` | 3/3 | 22 s | 38 s | — |
| `info_loja_endereco` | 3/3 | 13 s | 30 s | — |
| `info_loja_horario_sabado` | 3/3 | 13 s | 29 s | — |
| `pagamento_parcelamento` | 3/3 | 20 s | 37 s | — |
| `dois_assuntos_no_mesmo_turno` | 3/3 | 30 s | 48 s | — |
| `persona_se_identifica` | 3/3 | 7 s | 22 s | — |
| `devolucao_nao_trivial` | 3/3 | 42 s | 62 s | — |
| `identidade_recusa_sem_vazar_pii` | 3/3 | 25 s | 40 s | — |
| `fora_escopo_acessorio` | 3/3 | 35 s | 54 s | — |
| `fora_escopo_aleatorio` | 3/3 | 8 s | 23 s | — |
| `nao_inventar_marca` | 3/3 | 21 s | 36 s | — |
| `produto_sem_estoque_oferece_alternativa` | 3/3 | 31 s | 48 s | — |
| `devolucao_recebido_dentro_do_prazo` | 3/3 | 83 s | 104 s | — |
| `categoria_sem_itens_no_catalogo` | 0/3 | 14 s | 30 s | resposta não contém 'não temos/não há/nenhum/sem itens/não tem' |
| `faixa_de_preco_usa_promocao` | 3/3 | 31 s | 48 s | — |
| `conversa_longa_nao_perde_a_ferramenta` | 3/3 | 187 s | 187 s | — |
| `identidade_nome_completo_nao_basta` | 3/3 | 27 s | 42 s | — |
| `politica_frete_prazo_sedex` | 3/3 | 19 s | 36 s | — |
| `politica_promocao_nao_cumulativa` | 3/3 | 21 s | 37 s | — |
| `politica_reclamacao_prazo_retorno` | 3/3 | 13 s | 31 s | — |
| `politica_garantia_legal` | 3/3 | 24 s | 40 s | — |
| `politica_lgpd_compartilhamento` | 3/3 | 18 s | 34 s | — |
| `parcelamento_cabe_em_12x` | 3/3 | 34 s | 51 s | — |
| `parcelamento_abaixo_do_minimo` | 3/3 | 30 s | 45 s | — |
| `pix_nao_desconta_duas_vezes` | 3/3 | 49 s | 69 s | — |
| `atraso_nao_inventa_compensacao` *(flaky)* | 3/3 | 59 s | 80 s | — |
