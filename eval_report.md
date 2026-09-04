# Avaliação do agente — `test_live.py`

Gerado por `python test_live.py --rodadas 3` em 04/09/2026 12:14.

| | |
|---|---|
| Modelo | `mlx-qwen3.5-9b-claude-4.6-opus-reasoning-distilled` (LM Studio, local) |
| Casos | 33 |
| Rodadas por caso | 3 |
| Passaram em todas as rodadas | 32/33 |
| Falhas que travam o gate | 1 |
| Latência por caso (mediana das 99 execuções) | 33 s |
| Latência do pior caso | 190 s |

O agente é não determinístico: cada caso roda várias vezes, em threads novas, e o que
vale é a **taxa**. Casos marcados `flaky` no código são conhecidamente instáveis —
aparecem aqui com a taxa real, mas não derrubam o resultado.

| Caso | Taxa | Mediana | Pior | Falhou com |
|---|---|---|---|---|
| `catalogo_faixa_preco` | 3/3 | 33 s | 54 s | — |
| `preco_produto_especifico` | 3/3 | 21 s | 40 s | — |
| `preco_pix_multiturno` | 3/3 | 55 s | 58 s | — |
| `promocao_inexistente_nao_afirmada` | 3/3 | 21 s | 40 s | — |
| `info_loja_endereco` | 3/3 | 15 s | 34 s | — |
| `info_loja_horario_sabado` | 3/3 | 17 s | 36 s | — |
| `pagamento_parcelamento` | 3/3 | 32 s | 51 s | — |
| `dois_assuntos_no_mesmo_turno` | 3/3 | 26 s | 47 s | — |
| `persona_se_identifica` | 3/3 | 9 s | 27 s | — |
| `devolucao_nao_trivial` | 3/3 | 46 s | 68 s | — |
| `identidade_recusa_sem_vazar_pii` | 3/3 | 27 s | 45 s | — |
| `fora_escopo_acessorio` | 3/3 | 16 s | 33 s | — |
| `fora_escopo_aleatorio` | 3/3 | 8 s | 25 s | — |
| `nao_inventar_marca` | 3/3 | 20 s | 38 s | — |
| `produto_sem_estoque_oferece_alternativa` | 3/3 | 37 s | 57 s | — |
| `devolucao_recebido_dentro_do_prazo` | 3/3 | 91 s | 91 s | — |
| `categoria_sem_itens_no_catalogo` | 3/3 | 22 s | 40 s | — |
| `faixa_de_preco_usa_promocao` | 3/3 | 43 s | 60 s | — |
| `conversa_longa_nao_perde_a_ferramenta` | 3/3 | 190 s | 190 s | — |
| `identidade_nome_completo_nao_basta` | 3/3 | 30 s | 50 s | — |
| `politica_frete_prazo_sedex` | 3/3 | 21 s | 43 s | — |
| `politica_promocao_nao_cumulativa` | 3/3 | 20 s | 40 s | — |
| `politica_reclamacao_prazo_retorno` | 3/3 | 16 s | 38 s | — |
| `politica_garantia_legal` | 3/3 | 35 s | 55 s | — |
| `politica_lgpd_compartilhamento` | 0/3 | 18 s | 37 s | resposta não contém 'não compartilha/não são compartilhados/não compartilhamos/não vendemos/nunca vendemos/nunca compartilha/jamais' |
| `parcelamento_cabe_em_12x` | 3/3 | 29 s | 50 s | — |
| `parcelamento_abaixo_do_minimo` | 3/3 | 35 s | 56 s | — |
| `pix_nao_desconta_duas_vezes` | 3/3 | 59 s | 83 s | — |
| `identificacao_nao_bloqueia_atendimento` | 3/3 | 19 s | 39 s | — |
| `identificacao_cliente_conhecido` | 3/3 | 19 s | 39 s | — |
| `identificacao_cadastrado_sem_compras` | 3/3 | 10 s | 30 s | — |
| `identificacao_cliente_novo_nao_cadastra` | 3/3 | 28 s | 48 s | — |
| `atraso_nao_inventa_compensacao` *(flaky)* | 3/3 | 71 s | 98 s | — |
