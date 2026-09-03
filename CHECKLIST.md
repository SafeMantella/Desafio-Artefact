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

## Parte 8 — Fechamento
- [ ] revisar histórico de commits
- [ ] batizar a persona? (decisão de 2 min do Pedro; default = "assistente virtual do Empório da Música")
- [ ] push; confirmar repo público
- [ ] `git clone` limpo + seguir o README do zero
