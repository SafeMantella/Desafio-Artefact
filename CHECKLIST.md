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

## Parte 4b — Smoke test ao vivo
- [ ] LM Studio: carregar modelo com tool use (ex.: Qwen2.5-7B-Instruct), Start Server, ajustar `MODEL` no `.env`
- [ ] `python agent.py` e testar: "violões até R$1000?" · "quanto custa o Takamine GD20?" · "endereço/horário?" · "me arrependi do pedido 8" (→ identificação → política) · "vendem cordas?" · "capital da França?"
- [ ] afinar prompt/tools conforme o comportamento do modelo

## Parte 5 — Streamlit
- [ ] `app.py`: chat, `thread_id` em `session_state`, botão "nova conversa", aviso se LM Studio offline
- [ ] validar multi-turno + persistência (fechar/reabrir mesmo `thread_id`)
- [ ] commit `ui streamlit`

## Parte 6 — Exemplos de interação
- [ ] 3-5 conversas em `examples/*.md`: catálogo c/ filtro de preço · preço pontual · info da loja · **devolução aplicando política + dados do pedido (não trivial)** · fora de escopo/acessório
- [ ] commit `exemplos de interacao`

## Parte 7 — README
- [ ] como rodar (pré-req LM Studio + modelo, comandos)
- [ ] justificativas de todas as decisões técnicas
- [ ] limitações conhecidas + "com mais tempo"
- [ ] uso de IA (Claude Code — workflow)
- [ ] `pip freeze` → pinar versões em `requirements.txt`
- [ ] commit `readme completo`

## Parte 8 — Fechamento
- [ ] revisar histórico de commits
- [ ] batizar a persona? (decisão de 2 min do Pedro; default = "assistente virtual do Empório da Música")
- [ ] push; confirmar repo público
- [ ] `git clone` limpo + seguir o README do zero
