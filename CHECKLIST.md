# Checklist de implementação

Progresso por partes. Commit ao fim de cada parte, sem force-push.
Detalhe e justificativas: `CLAUDE.md` e (no fim) `README.md`.

---

## Parte 0 — Setup
- [x] `git init` + remote `origin` → SafeMantella/Desafio-Artefact (repo estava vazio)
- [x] memórias do projeto salvas
- [x] `.gitignore`
- [x] `requirements.txt`
- [x] `.env.example`
- [x] `config.py`
- [ ] venv + instalar dependências  *(passo do Pedro — ver README/Parte 7)*
- [x] `CLAUDE.md` + `CHECKLIST.md`
- [x] commit `setup inicial do projeto`

## Parte 1 — ETL / SQLite ✅
- [x] `build_db.py`: lê os 6 CSVs, normaliza tipos, cria tabelas + views (`v_produto`, `v_pedido_item`)
- [x] rodar → `emporio.db`; contagens conferidas (products=**65**, orders=**20**, customers=50)
- [x] `test_agent.py`: asserts de sanidade nas views (Takamine GD20, produto 96 sem estoque, promo do 127 sem PIX cumulativo)
- [x] commit `etl: csvs para sqlite com views`

## Parte 2 — Políticas ✅
- [x] `convert_policies.py` (pymupdf4llm) → `policies_raw.md`; `policies.md` = curado, 10 seções por `##`, divergências do PDF resolvidas
- [x] `tools.py::consultar_politica` — score por palavra-chave (word-boundary) + título, retorna 1-2 seções
- [x] asserts: arrependimento→4; horário→2; cordas→1; pagamento→3; rastreio→5; garantia→8; tópico desconhecido→ajuda
- [x] commit `tool de consulta a politicas` (+ `pymupdf4llm` no commit da Parte 3)

## Parte 3 — Tools de dados ✅
- [x] `buscar_produtos` (filtro SQL parametrizado + match de termo em nome/specs), `detalhe_produto` (com desambiguação), `status_pedido` (verificação leve de identidade: e-mail exato OU todos os tokens do nome)
- [x] `_brl()` formata moeda; `dias_desde_pedido` calculado contra `DATA_REFERENCE_DATE`
- [x] asserts: violões ≤ R$1000 disponíveis; GD20→R$2.199 + PIX; promo do 127; ambiguidade "Yamaha"; pedido 5 nome/e-mail certo vs errado; pedido inexistente
- [x] commit `tools de dados: produtos e pedidos`

## Parte 4 — Agente ✅ (código) · ⏳ smoke test ao vivo
- [x] `prompts.py`: persona (política 7.1) + escopo + guardrails preço/estoque/promoção + fluxo troca + LGPD + estilo WhatsApp + data de referência
- [x] `agent.py`: `ChatOpenAI(base_url=LM Studio)` + `create_react_agent` + `SqliteSaver(emporio.db)`; helper `responder()`; REPL em `python agent.py`
- [x] `test_agent.py::test_agente_compila` — grafo monta, 4 tools, checkpointer cria tabelas (sem LLM)
- [ ] **smoke test ao vivo** (Pedro: subir LM Studio) — ver Parte 4b
- [x] commit `agente react com langgraph + persona`

## Parte 4b — Smoke test ao vivo ✅
- [x] LM Studio: `qwen/qwen3.5-9b`, server no ar, `.env` com `MODEL=qwen/qwen3.5-9b`
- [x] 6 cenários testados — 6/6 OK após 2 ajustes:
  - `consultar_politica` agora devolve várias seções para perguntas de 2 assuntos (endereço + horário)
  - prompt: responder todos os pontos da pergunta; "previsão" ≠ "entregue"
- [x] latência observada: 10s–2min por turno (documentado no README)

## Parte 5 — Streamlit ✅ (código) · ⏳ validação ao vivo
- [x] `app.py`: `st.chat_input`, `thread_id` editável na sidebar, "Nova conversa", aviso se LM Studio offline, retomada de histórico via checkpointer (`get_state`)
- [x] boot headless OK (HTTP 200, sem tracebacks)
- [ ] validar multi-turno + persistência ao vivo (reabrir mesmo `thread_id`) — junto com a Parte 4b
- [x] commit `ui streamlit`

## Parte 6 — Exemplos de interação ✅
- [x] `run_examples.py`: 5 cenários, roda o agente de verdade, salva `examples/*.md` com as chamadas de ferramenta visíveis
- [x] transcripts gerados com `qwen/qwen3.5-9b` e revisados; o 04 (devolução) mostra o agente percebendo que o produto ainda não foi entregue → prazo de 7 dias nem começou
- [x] commit `exemplos de interacao`

## Parte 7 — README ✅ (rascunho) · ⏳ ajuste pós-smoke-test
- [x] como rodar (pré-req LM Studio + modelo, comandos, `.env`)
- [x] arquitetura + as 4 tools
- [x] justificativas das 9 decisões técnicas
- [x] limitações conhecidas + "com mais tempo"
- [x] uso de IA (Claude Code — workflow: entrevista pergunta a pergunta, execução por partes)
- [x] revisar após o smoke test (modelo real Qwen3.5-9B, nota de latência)
- [x] versões fixadas em `requirements.txt`
- [x] commit `readme completo`

## Parte 8 — Fechamento ✅
- [x] histórico: commits incrementais, sem force-push
- [x] persona: assistente batizado de **melodIA** (decisão do Pedro) — registrado no README §9
- [x] push; repo público confirmado
- [x] `git clone` limpo → venv → `build_db.py` → `test_agent.py` (partes offline)

## Parte 9 — Correções pós-análise (@ANALISTA)

- [x] **#4 segurança** (`98ff555` → revisão ANALISTA achou 2 bypasses → `d62afc5`):
  v3 do `_identidade_confere` — e-mail exato OU (primeiro nome + ≥2 partes distintas do nome,
  match de palavra inteira, sem palavra fora do nome). Fecha: sobrenome isolado, "Ana Ana"
  (repetição, era 100%), spray de nomes comuns (era 70% às cegas). `test_identidade_nao_burlavel`
  cobre os 3 ataques + casos legítimos. Varredura: 0/50 em cada ataque, 50/50 legítimo.
- [x] **#1 grounding** (`c7d8061`): prompt manda afirmar só o que `consultar_politica` retornou.
  ANALISTA reproduziu resposta limpa E resíduo pro mesmo input → é **mitigação probabilística,
  não fix determinístico**. README §9 diz "mitigado, não eliminado"; fechar de vez = guard de
  saída ou eval (#2). Não reabrir por prompt.
- [x] **#2 eval harness** (`1c2734c`): `test_live.py` — 13 casos ponta a ponta contra o LM
  Studio (ferramenta esperada + contém/não-contém na resposta). Cobre catálogo, preço, PIX
  multi-turno, promoção falsa, políticas, devolução não-trivial, recusa de identidade sem
  vazar PII, fora de escopo, não inventar marca, produto sem estoque. Última rodada: 13/13.
- [x] **#2b eval endurecido** (revisão do ANALISTA sobre o próprio `test_live.py`): 13 → 16
  casos. Oráculo de PII **derivado** do retorno da tool com a identidade correta (3 → 8 campos
  cobertos) + exigência de recusa explícita; `"a|b"` em `contem` = qualquer uma serve
  (whitelist onde blacklist de frase era furada: marca inventada, produto sem estoque);
  `tool_esperada` aceita lista. Casos novos: persona (`melodIA`), duas tools no mesmo turno,
  isca de atraso→reembolso (marcada `flaky=True`, não derruba o gate).
- [x] **bug achado pelo eval**: `buscar_produtos` com `apenas_disponiveis=True` devolvia
  "não encontrei nada" para produto que existe mas está sem estoque → agente dizia ao cliente
  "não está no catálogo" (falso). Agora refaz a busca sem o filtro e diferencia os dois casos.
  Assert em `test_agent.py`; o caso do eval foi de 1/3 para 3/3 rodadas.
- [x] **#3** (`e4b5593`): meio-termo de embeddings documentado na decisão 3 do README.
- [x] **#5** (`6cfc5f7`): tensão modelo-local × volume nomeada na decisão 2 do README.

## Parte 10 — Segunda rodada de análise (revisão do Opus)

Revisão técnica das decisões do projeto. Cinco correções principais + menores; o que já tinha
sido feito na Parte 9 foi verificado antes de mexer.

- [x] **conexão sqlite vazando** (`2a7c5a6`): `with _conn() as c` faz commit/rollback mas **não
  fecha** — cada chamada de tool vazava um handle num processo (Streamlit) que fica de pé por
  horas. Agora `contextlib.closing` nas 3 queries.
- [x] **`buscar_produtos`, 2 bugs** (`63b667a`):
  (a) categoria não mapeada era descartada **em silêncio** — `categoria="saxofone"` devolvia os
  20 instrumentos mais baratos (ukuleles). Categorias 6/7/8 entraram no vocabulário (o manual §1
  diz que a loja trabalha com sopros e cordas orquestrais, só não há produtos) e categoria
  desconhecida agora devolve a lista de categorias válidas;
  (b) `preco_min`/`preco_max` filtravam `preco_tabela` e ignoravam promoção — "ukulele até
  R$ 500" excluía o Ohana CK-20, que sai por R$ 439,20. Agora filtra e ordena por
  `COALESCE(preco_promocional, preco_tabela)`.
- [x] **relógio de arrependimento errado** (`d54567b`): `policies.md` §4.1 conta 7 dias **do
  recebimento**; §4.2 conta 30 **da compra**. A tool só dá dias da compra e o prompt mandava
  comparar os dois com ele. Agora a tool rotula "há N dias da compra" + declara que não há data
  de recebimento, e o prompt manda perguntar ao cliente quando o prazo contar dali. Saíram do
  prompt os prazos hard-coded e o horário de funcionamento (duplicavam `policies.md`, e o
  horário dava atalho para não chamar `consultar_politica`).
- [x] **histórico sem poda** (`5286302`): `create_react_agent` reenviava a conversa inteira a
  cada turno; com retorno de política (~1.200 tokens) 10-15 turnos estouram a janela local — e o
  eval não via, porque nenhum caso passava de 2 turnos. `pre_model_hook` + `trim_messages`
  (`MAX_HISTORY_TOKENS`, default 8000); `start_on="human"` evita `ToolMessage` órfã.
  `test_poda_historico` cobre sem LLM. Junto: `temperature` 0.3 → 0 e log (turno em INFO,
  ferramenta em DEBUG, sem PII).
- [x] **eval com n=1** (`73dee54`): rodava cada caso uma vez e reportava "16/16". Agora
  `--rodadas N` (default 3), gate por taxa, latência medida e `eval_report.md` versionado.
  16 → 20 casos: caso positivo de arrependimento (cliente informa quando recebeu), categoria sem
  itens, faixa de preço com promoção, conversa longa (poda ponta a ponta).
- [x] **enunciado fora do repo** (`2c92d7d`): `.gitignore` + `git rm --cached`. Fecha a pendência
  aberta na Parte 8.
- [x] **README + evidência** (`fef902e`): decisões 2, 5, 7, 9 e 11 atualizadas; latência deixa
  de ser chute (56 s de mediana, 415 s no pior, em 60 execuções); `eval_report.md` versionado
  (20/20 em 3 rodadas com `qwen/qwen3.8-27b`); `examples/` regerados com o prompt novo — o 04
  passou a ser o pedido 7 com "recebi ontem", que exercita o relógio de recebimento.

- [x] **validação da poda ao vivo**: `validacao_conversa_longa.md` — 42 turnos numa thread nova
  (o corte disparou no turno 39) + dois anexos: o fluxo de devolução fechado com a poda ativa e
  um corte profundo (22 de 36 mensagens, teto 2000 só naquele processo). Zero erro de API nos
  três. Fecha a pendência da Parte 8.

Achados que a validação levantou e que **não** foram mexidos (mudar o prompt invalidaria o
`eval_report.md`, que é de outra configuração): o bordão "Sua música começa aqui." sai em 42 de
42 respostas, contra a regra de parcimônia do prompt; e na fronteira do corte o agente pode ver
o próprio eco de um fato já podado ("Olá, Pedro!") sem a origem — uma vez respondeu com a recusa
de fora-de-escopo, outra percebeu sozinho. Decisão do Pedro se vira correção.

## Parte 11 — Revisão do README (`brainstorm.txt`)

13 pontos anotados pelo Pedro relendo o README; cada um investigado contra o código e o
dado real, veredito dele, implementação por fase com um commit por fase.

- [x] item 1 — cifrão escapado em `app.py`, `run_examples.py` e nos 5 `examples/*.md`
- [x] item 7 — dinheiro normalizado no ETL (`data/` intocado)
- [x] item 14 a/b — marca da descrição corrigida no ETL a cada build (6 produtos, com assert)
- [x] item 14 d — `status_pedido` avisa quando total ≠ soma dos itens
- [x] item 5 — `test_policies_sem_perda`: curadoria não perdeu número, valor nem e-mail
- [x] item 12a — roteamento das 10 seções de política travado por teste
- [x] item 9 — identidade só por pedido + e-mail exato (heurística de nome deletada)
- [x] item 13 — `simular_pagamento`, com as constantes conferidas contra `policies.md`
- [x] item 14 c — prompt oferece as specs depois de apresentar um instrumento
- [x] item 12b — eval de 20 → 28 casos (5 de política, 2 de parcelamento, 1 de identidade)
- [x] itens 2, 3, 6, 8, 11 — README: armadilhas dos dados, uma busca = uma chamada,
      conta de preço, por que não `date.today()`, limitação de hardware / usuário único
- [x] item 4 — decidido NÃO: `data/` são fixtures, sem elas o repo não é reproduzível
- [ ] **Pedro, com LM Studio:** `python run_examples.py` (o exemplo 04 ainda identifica por
      nome) e `python test_live.py` (relatório versionado ainda descreve 20 casos)
