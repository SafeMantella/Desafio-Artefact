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

## Parte 2 — Políticas
- [ ] `policies.md`: PDF convertido, seccionado por `##`, inconsistências anotadas
- [ ] `tools.py::consultar_politica` + mapa tópico→seção
- [ ] asserts: "troca"→seção 4; "horário"→seção 2; "cordas"→seção 1 (escopo)
- [ ] commit `tool de consulta a politicas`

## Parte 3 — Tools de dados
- [ ] `buscar_produtos`, `detalhe_produto`, `status_pedido` (verificação leve de identidade)
- [ ] asserts: violões ≤ R$1000 disponíveis; "Takamine GD20"→R$2199; pedido 5 e-mail certo vs errado; produto 96 indisponível
- [ ] commit `tools de dados: produtos e pedidos`

## Parte 4 — Agente
- [ ] `prompts.py`: persona + regras (escopo, guardrails preço/estoque, promoções, LGPD, quando usar cada tool, resposta curta estilo WhatsApp)
- [ ] `agent.py`: `ChatOpenAI(base_url=...)` + `create_react_agent(model, tools, checkpointer, prompt)` + `SqliteSaver`
- [ ] smoke test com LM Studio ligado: 4 cenários do PDF + fora de escopo + acessório
- [ ] commit `agente react com langgraph + persona`

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
