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

- Enunciado do desafio: `desafio_tecnico_ai_eng_artefact.pdf`
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
| 4 | Conceito de "hoje" | Config `DATA_REFERENCE_DATE` (default `2026-03-25`) | Dataset é snapshot; pedidos vão até 2026-03-22. Sem isso, toda política de prazo dá "vencido". |
| 5 | Histórico de conversa | Checkpointer **`SqliteSaver`** do LangGraph, por `thread_id` | Persiste entre execuções, reaproveita o SQLite. Cliente volta e o agente lembra. |
| 6 | Identificação do cliente | `status_pedido`: e-mail exato OU (primeiro nome + ≥2 partes distintas do nome, match de palavra inteira, sem palavra fora do nome). `_identidade_confere` em `tools.py`; `test_identidade_nao_burlavel` | LGPD sem auth. v1 (substring) e v2 (agregação) eram burláveis 100%/70% às cegas — v3 fecha isso. Resíduo conhecido: 3 pares de clientes com nome-subconjunto colidem (não é ataque cego); documentado no README §6. |
| 7 | Interface | **Streamlit** | Chat web pra demo; `thread_id` em `st.session_state`. |
| 8 | Modelo / provedor | **LM Studio** local; código agnóstico (base_url + nome via `.env`), default `qwen/qwen3.5-9b` | Sem custo, offline, PII não sai da máquina. `test_live.py` 13/13 com qwen3.5-9b. |

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
tools.py           as 4 tools LangChain (buscar_produtos, detalhe_produto,
                   status_pedido, consultar_politica)                        [Partes 2-3]
prompts.py         system prompt / persona / regras                         [Parte 4]
agent.py           monta o ReAct agent + checkpointer                       [Parte 4]
app.py             Streamlit                                                [Parte 5]
test_agent.py      7 checks assert-based, sem LLM (views, política, tools, identidade)  [ao longo]
test_live.py       13 casos ponta a ponta contra o LM Studio (avaliação do agente)     [Parte 9]
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

**Completo + rodada de correções pós-análise do @ANALISTA.** Ver `CHECKLIST.md` (Parte 9).
Partes 0-8: ETL, políticas, 4 tools, agente (melodIA), Streamlit, 5 exemplos, README, clone
limpo. `test_agent.py`: 7/7. `test_live.py`: 16/16 (última execução). Correções: #4 identidade
(v3 + resíduo documentado), #1 grounding (mitigado), #3/#5 (README), #2 (eval harness),
#2b eval endurecido (16 casos, oráculo de PII derivado, whitelist no lugar de blacklist) —
que achou e fechou o bug do `buscar_produtos` ("existe sem estoque" virava "não existe").

Pendências opcionais (Pedro): validar o Streamlit ao vivo num clone limpo; decidir se mantém
o PDF do enunciado no repo.

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
- `políticas_da_loja.pdf`: **duas versões do WhatsApp** — (67) 3341-4444 (pág. 2, seção 1.2)
  e (67) 3321-4500 (pág. 6, seção 7). E-mail aparece com e sem acento. → `policies.md` usa
  os dados da seção 1.2 como canônicos e anota a divergência.
- Categorias 6, 7, 8 (sopro, cordas orquestrais) existem em `categories.csv` mas **não têm
  produtos**.

## 7. Convenções

- Tudo em **PT-BR** (código, mensagens, docs).
- SQL **sempre parametrizado**, nunca gerado pelo LLM.
- Regras de política vivem no **texto** (`policies.md`), não hard-coded (exceção: cálculos
  auxiliares como `dias_desde_pedido`, que a tool entrega pronto pro agente comparar).
- Trabalhar **por partes** (CHECKLIST), 1 commit por parte, sem force-push.
- **O loop:** decisão técnica = opções + recomendação + Pedro escolhe + registrada na seção
  "Decisões técnicas" do README com a motivação. Toda tecnologia/lib usada no código tem
  entrada lá. Mudou a decisão (ex.: ajuste pós-teste real) → muda a seção.
