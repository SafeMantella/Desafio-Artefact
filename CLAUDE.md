# CLAUDE.md — Agente de Atendimento "Empório da Música"

> Contexto para retomar este projeto numa conversa nova. Escrito para o Pedro (e para o
> Claude) reencontrarem o trabalho meses depois sem re-descobrir tudo.

## 1. O que é

Desafio técnico para vaga de **AI Engineer na Artefact**. Protótipo em Python de um **agente
de atendimento** (mensagens de texto) para a loja fictícia **Empório da Música**
(instrumentos musicais, Campo Grande/MS).

O agente precisa: assumir a **persona** da loja; responder com base no contexto; saber
**quando consultar dados** (CSVs: produtos, pedidos, clientes, promoções) e **quando
consultar políticas** (PDF: trocas, horários, pagamento, frete, garantia); e **lidar com
perguntas fora do escopo** da loja.

- Enunciado do desafio: `desafio_tecnico_ai_eng_artefact.pdf` — **local, fora do repo**
  (no `.gitignore`: é material da Artefact, não nosso para republicar)
- Manual de políticas da loja: `data/políticas_da_loja.pdf`
- Repo: https://github.com/SafeMantella/Desafio-Artefact
- Plano detalhado (fora do repo): `~/.claude/plans/esse-espa-o-de-trabalho-whimsical-scroll.md`

Entregáveis: repo público + `README.md` (setup + justificativas + limitações + uso de IA) +
3-5 conversas de exemplo em `examples/` (≥1 não trivial).

## 2. Decisões técnicas (fechadas com o Pedro) — o "porquê" completo vai no README

| # | Decisão | Escolha | Porquê (resumo) |
|---|---------|---------|-----------------|
| 1 | Abordagem do agente | ReAct com **LangChain + LangGraph** (`langgraph.prebuilt.create_react_agent`) | Loop de raciocínio/tool pronto; LangChain é padrão de mercado. Fallback text-ReAct se o tool calling do modelo local for fraco. |
| 2 | Políticas (PDF) | `pymupdf4llm` converte o PDF → `policies_raw.md`; curadoria leve → `policies.md`; tool `consultar_politica(topico)` retorna seção por palavra-chave | Doc tem ~4k tokens / 10 seções. RAG com vector DB é over-engineering nessa escala. |
| 3 | Dados (CSVs) | ETL → **SQLite** (`emporio.db`) + views; SQL **parametrizado** nas tools (LLM não escreve SQL) | Mostra modelagem; joins/agregações limpos; sem risco de query gerada errada. |
| 4 | Conceito de "hoje" | Config `DATA_REFERENCE_DATE` (default `2026-03-25`) | Dataset é snapshot; pedidos vão até 2026-03-22. Sem isso, toda política de prazo dá "vencido". **Parte 10:** §4.1 conta do *recebimento*, não da compra — a tool declara que não tem essa data e o agente pergunta ao cliente. |
| 5 | Histórico de conversa | Checkpointer **`SqliteSaver`** do LangGraph, por `thread_id` + poda com `trim_messages` no `pre_model_hook` | Persiste entre execuções, reaproveita o SQLite. Persistir tudo ≠ reenviar tudo: `MAX_HISTORY_TOKENS` (8000) evita estourar a janela do modelo local em conversa longa. |
| 6 | Identificação do cliente | `status_pedido`: número do pedido + **e-mail exato** (normalizado). Nome não serve. `_identidade_confere` em `tools.py`; `test_identidade_nao_burlavel` varre os 20 pedidos | LGPD sem auth. v1 (substring) e v2 (agregação) eram burláveis 100%/70%; v3 (nome + 2 partes) resistia a spray mas deixava 3 pares colidirem. v4 troca a heurística inteira por uma comparação de string: apaga o resíduo e não tem como regredir. Trade-off: menos amigável, é o que e-commerce real pede. |
| 7 | Interface | **Streamlit** | Chat web pra demo; `thread_id` em `st.session_state`. |
| 9 | Identificação do cliente | `identificar_cliente(email)` na saudação — **convite, não exigência**. 3 estados: novo / cadastrado sem compra (32 de 50) / com pedidos | §7.2 manda cumprimentar pelo nome "se disponível". Exigir e-mail para responder horário coleta PII sem finalidade (§9). Cidade alimenta o frete; pedido em trânsito vira oferta de rastreio. Identificar ≠ autenticar: conteúdo de pedido só pelo `status_pedido`. |
| 8 | Modelo / provedor | **LM Studio** local; código agnóstico (base_url + nome via `.env`) | Sem custo, offline, PII não sai da máquina. `temperature=0` (Parte 10) para o eval medir o modelo, não o sampler. Números da última rodada: `eval_report.md`. |

**Defaults assumidos** (documentados no README):
- Idioma: **PT-BR apenas**.
- Persona: nome **melodIA** (decisão do Pedro; trocadilho melodia+IA). Informal e acolhedora
  ("amigo que entende de música"), cumprimenta pelo nome se conhecido, evita robotização,
  bordão "Sua música começa aqui." com parcimônia. Regras derivam da seção 7 do manual.
- Fora de escopo: acessórios (cordas, palhetas, cabos, cases, pedais, amplificadores) →
  redireciona educadamente; perguntas alheias → recusa cordial e volta pro contexto da loja.
- Guardrails: nunca inventar preço/estoque/prazo sem tool; promoção sempre com preço
  original + % + final; não confirmar disponibilidade sem checar `stock`.

## 3. Mapa do repo

```
config.py          paths, MODEL, OPENAI_BASE_URL, DATA_REFERENCE_DATE (lê .env)
build_db.py        ETL: os 6 CSVs de data/ → emporio.db (tabelas + views)   [Parte 1]
convert_policies.py  PDF de políticas → policies_raw.md (pymupdf4llm)         [Parte 2]
policies_raw.md    saída bruta da conversão (artefato reproduzível)          [Parte 2]
policies.md        policies_raw.md curado (headings limpos, divergências resolvidas) — usado pelo agente  [Parte 2]
tools.py           as 6 tools LangChain (buscar_produtos, detalhe_produto,
                   status_pedido, consultar_politica, simular_pagamento,
                   identificar_cliente)                              [Partes 2-3, 11]
prompts.py         system prompt / persona / regras                         [Parte 4]
agent.py           monta o ReAct agent + checkpointer                       [Parte 4]
app.py             Streamlit                                                [Parte 5]
test_agent.py      12 checks assert-based, sem LLM (views+ETL, política sem perda,
                   roteamento das 10 seções, tools, identidade, parcelamento/frete, poda)  [ao longo]
test_live.py       avaliação ponta a ponta contra o LM Studio, k rodadas por caso      [Parte 9-10]
eval_report.md     saída da última execução do eval (taxa + latência por caso)      [Parte 10]
examples/          3-5 conversas de exemplo                                 [Parte 6]
data/              dados fornecidos — NÃO alterar
```

## 4. Como rodar

1. LM Studio: carregar um modelo com suporte a tool use (ex.: Qwen2.5-7B-Instruct) e
   **Start Server** (porta 1234).
2. `python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`
3. `cp .env.example .env` (ajustar `MODEL` para o id exato carregado no LM Studio)
4. `python build_db.py` → gera `emporio.db`
5. `streamlit run app.py`

## 5. Estado atual

**Completo + três rodadas de correções pós-análise.** Ver `CHECKLIST.md` (Partes 9, 10 e 11).
Partes 0-8: ETL, políticas, tools, agente (melodIA), Streamlit, 5 exemplos, README, clone
limpo. Hoje: `test_agent.py` 11/11; `test_live.py` com 29 casos (relatório versionado ainda
é o da Parte 10, com 20 — regerar). Correções: #4 identidade
(v3 + resíduo documentado), #1 grounding (mitigado), #3/#5 (README), #2 (eval harness),
#2b eval endurecido (16 casos, oráculo de PII derivado, whitelist no lugar de blacklist) —
que achou e fechou o bug do `buscar_produtos` ("existe sem estoque" virava "não existe").

**Parte 10** (revisão do Opus sobre as decisões): conexão sqlite vazando (`closing`);
`buscar_produtos` descartava categoria desconhecida em silêncio e ignorava promoção na faixa de
preço; relógio de arrependimento contava da compra e não do recebimento; histórico sem poda
(`pre_model_hook` + `trim_messages`); eval rodava n=1 (agora `--rodadas`, default 3, com
`eval_report.md` versionado); enunciado saiu do versionamento.

**Parte 12** (auditoria da §5 — Política de Frete e Entregas): das 11 cláusulas da seção, 2
eram calculadas, 6 viviam só no texto e 3 tinham furo. Fechados os três:
1. **Avaria/extravio não roteava.** "chegou quebrado", "avaria", "amassada", "extravio",
   "sumiu" caíam no fallback do `consultar_politica` e o modelo reformulava para "defeito",
   respondendo com a §4 (troca em 30 dias) o que a §5.2 resolve de outro jeito (recusar o
   recebimento, acionar o seguro). `_KEYWORDS` passou a mapear palavra → **lista** de seções:
   "quebrado" pontua a 4 E a 5 (ambiguidade real — só o cliente sabe qual é), e o prompt
   manda perguntar em vez de escolher. "defeito de fabricação" continua fora da 5.
2. **Grande porte (§5.2) nunca disparava.** `buscar_produtos` e `detalhe_produto` marcam o
   item e mandam avisar antes que o cliente pergunte — os DOIS, porque o eval pegou o
   agente indo pela busca para dar o preço e nunca vendo o aviso que só estava na ficha.
   Match por NOME (`_e_grande_porte`), não por categoria: a categoria "Baixos" só tem baixo
   elétrico e "Teclados e Pianos" só tem sintetizador.
3. **Prazo da §5.1 não saía com o frete.** `simular_pagamento` agora devolve "1 a 3 dias
   úteis, motoboy próprio, contato por telefone" (`_PRAZO_CG`) junto da conta do frete.

Mais as duas suposições que a §5.1 deixa em aberto, agora documentadas e travadas em teste:
R$ 500,00 exatos **pagam** frete ("acima de" é estrito), e o limite vale sobre o **subtotal
pago** (decisão do Pedro), não sobre o preço de tabela. Consequência que a ferramenta agora
diz em voz alta: numa compra de R$ 520 o cartão ganha frete grátis (total R$ 520,00) e o PIX
cai para R$ 494,00 e paga os R$ 35 (total R$ 529,00) — **o cartão sai mais barato que o
PIX**. Quando as formas caem em lados diferentes do limite, saem as duas contas.

**Parte 11** (revisão do README pelo Pedro, `brainstorm.txt` — arquivo local, fora do repo):
cifrão escapado nos renderizadores; dinheiro normalizado no ETL; ruído nome×descrição
corrigido no ETL a cada build (6 produtos, `data/` intocado); aviso de divergência
total×soma no `status_pedido`; identidade só por e-mail; tool `simular_pagamento` com as
constantes conferidas contra `policies.md`; busca por especificação (`_SPECS_PT`); eval de
20 → 29 casos; testes 8 → 11.

Tudo rodado: `test_agent.py` 11/11, `test_live.py` 29/29 em 3 rodadas, `examples/` e
`eval_report.md` regerados, e o Streamlit validado ao vivo em 28 turnos — o que fecha a
pendência da Parte 10 e achou o balão vazio no chat (`AIMessage` com `content='\n\n'`).

## 6. Armadilhas dos dados (descobertas na exploração)

- `products.csv`: 65 produtos, IDs 81–145 **sem buracos**, mas as **linhas do CSV estão fora
  de ordem** (81–130, depois 145, depois 131–144) — ordenar por `product_id` sempre.
  `price_brl` mistura int e decimal. `status` ∈ {active (62), discontinued (113, 136),
  coming_soon (130)}. Alguns `active` têm `stock_quantity = 0` (ex.: produto 96) →
  "disponível" = `active` **E** `stock > 0` (61 disponíveis, 4 com promoção ativa).
- `products.csv`: **nomes sintéticos inconsistentes com a descrição** (ex.: "Music Man Bass
  1X Electric Bass" com descrição de "Fender Jazz Bass"; teclados idem). → confiar nos
  campos estruturados (name, price, category, stock, status); tratar `description` como
  texto livre.
- `specs` é JSON embutido no CSV e o **schema varia por categoria** (violão: top/back_sides;
  guitarra: body/neck; bateria: shells/pieces).
- `promotions.csv`: `is_active = 1` só em 4 linhas (produtos 90, 94, 121, 127). Vários
  produtos têm **múltiplas linhas** de promoção → agregar (maior `discount_percent` entre as
  ativas).
- `orders.csv`: 20 pedidos (IDs 1–20). `tracking_code` / `estimated_delivery` só existem
  para status `delivered`/`shipped`. `notes` só para `cancelled`. **Não há data de entrega
  efetiva.** Todos os pedidos são de out/2025 a mar/2026 → ver `DATA_REFERENCE_DATE` (decisão #4).
- `products.csv`: 10 produtos (135–144) têm **nome de template** (`Bass 1X`, `Kit 1 Studio`,
  `Synth 1 Pro`) e em 6 deles a descrição cita **outra marca**. O `build_db.py` corrige a
  marca a cada build (assert de exatamente 6). Sobra a divergência descrição×specs do 142
  ("88 teclas" com `keys: 61`) — documentada, não corrigida.
- `order_items.csv`: **sem preço unitário**. Em 2 dos 20 pedidos (3 e 20) o total não bate
  com a soma a preço de tabela — desconto na venda que o dataset não registra.
- `políticas_da_loja.pdf`: **duas versões do WhatsApp** — (67) 3341-4444 (pág. 2, seção 1.2)
  e (67) 3321-4500 (pág. 6, seção 7). E-mail aparece com e sem acento. → `policies.md` usa
  os dados da seção 1.2 como canônicos e anota a divergência.
- Categorias 6, 7, 8 (sopro, cordas orquestrais) existem em `categories.csv` mas **não têm
  produtos**.

## 7. Convenções

- Tudo em **PT-BR** (código, mensagens, docs).
- SQL **sempre parametrizado**, nunca gerado pelo LLM. O banco é **só leitura**.
- **Nunca** coletar dado de pagamento (cartão, chave PIX, CPF).
- Regras de política vivem no **texto** (`policies.md`), não hard-coded (exceção: cálculos
  auxiliares como `dias_desde_pedido`, que a tool entrega pronto pro agente comparar).
- Trabalhar **por partes** (CHECKLIST), 1 commit por parte, sem force-push.
- **O loop:** decisão técnica = opções + recomendação + Pedro escolhe + registrada na seção
  "Decisões técnicas" do README com a motivação. Toda tecnologia/lib usada no código tem
  entrada lá. Mudou a decisão (ex.: ajuste pós-teste real) → muda a seção.
