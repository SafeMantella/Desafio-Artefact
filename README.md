# Empório da Música — Agente de Atendimento

Protótipo da **melodIA**, assistente virtual de atendimento ao cliente da **Empório da
Música**, loja (fictícia) de instrumentos musicais em Campo Grande/MS. Desafio técnico para
a vaga de AI Engineer na Artefact.

O agente assume a persona da loja, responde por mensagem de texto e sabe **quando consultar
dados** (catálogo, pedidos, promoções) e **quando consultar as políticas** (trocas, horários,
pagamento, frete, garantia). Perguntas fora do escopo da loja são recusadas educadamente.

---

## O que dá para perguntar

- *"Quais violões disponíveis até R$ 1000?"* → busca no catálogo, só o que está em estoque
- *"Quanto custa o Takamine GD20?"* → preço de tabela + preço à vista no PIX
- *"Qual o endereço e o horário da loja?"* → consulta o manual de políticas
- *"Me arrependi da compra do pedido 7, consigo devolver?"* → confirma a identidade, lê a
  política, percebe que o prazo de arrependimento conta do **recebimento** (dado que o sistema
  não tem) e pergunta ao cliente quando ele recebeu antes de responder
- *"Quais ukuleles até 500 reais?"* → a faixa vale sobre o preço **efetivo**: entra o que está a 439,20  com promoção, mesmo com tabela em R$ 549
- *"Vocês têm saxofone?"* → a loja trabalha com sopros, mas o catálogo está sem itens da categoria — e o agente diz isso, em vez de listar outra coisa
- *"Vocês vendem cordas de violão?"* → explica que a loja não trabalha com acessórios
- *"Me passa uma receita de bolo?"* → recusa educadamente e volta ao contexto da loja

Cinco conversas completas estão em [`examples/`](examples/), e a avaliação automática de 20
cenários (3 rodadas cada) em [`eval_report.md`](eval_report.md).

---

## Como rodar

### Pré-requisitos

- **Python 3.11+**
- **[LM Studio](https://lmstudio.ai/)** com um modelo que suporte *tool use* / function calling.
  A avaliação versionada em [`eval_report.md`](eval_report.md) é com **Qwen3.8-27B**
  (`qwen/qwen3.8-27b`): 20/20 casos em 3 rodadas cada. O projeto foi construído com
  **Qwen3.5-9B** (`qwen/qwen3.5-9b`), que também roda — mais rápido e menos confiável no
  *tool calling*; a família Qwen2.5-Instruct (7B+) e Llama-3.1-8B-Instruct servem como
  alternativas mais leves. Modelos maiores respondem melhor em português e chamam as
  ferramentas de forma mais confiável, ao custo de latência (ver decisão 2).
  Sugestões no LM Studio: contexto de 16k+ e GPU offload no máximo.

### Passos

```bash
# 1. Ambiente
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2. Banco local a partir dos CSVs
python build_db.py                 # gera emporio.db

# 3. Configuração
cp .env.example .env               # ajuste MODEL para o id exato carregado no LM Studio

# 4. LM Studio: carregue o modelo e clique em "Start Server" (porta 1234).
#    Sugestão de carregamento: GPU offload no máximo + contexto máximo

# 5. Rode a interface
streamlit run app.py               # UI de chat  (http://localhost:8501)
# ou, no terminal:
python agent.py                    # REPL simples
```

Variáveis de ambiente (`.env`):

| Variável | Padrão | Descrição |
|---|---|---|
| `OPENAI_BASE_URL` | `http://localhost:1234/v1` | endpoint do LM Studio (API compatível com OpenAI) |
| `OPENAI_API_KEY` | `lm-studio` | qualquer valor não vazio; o LM Studio ignora |
| `MODEL` | `qwen/qwen3.5-9b` | id do modelo carregado no LM Studio |
| `DATA_REFERENCE_DATE` | `2026-03-25` | "hoje" do agente — ver decisão 4 abaixo |

### Testes

```bash
python test_agent.py             # 8 checks determinísticos, sem LLM — segundos
python test_live.py              # 20 casos × 3 rodadas contra o LM Studio — horas
python test_live.py --rodadas 1  # 1 rodada só, para iterar
python test_live.py identidade   # só os casos cujo nome contém "identidade"
```

- **`test_agent.py`** cobre a lógica não-trivial sem chamar o modelo: views do ETL (preço
  promocional, PIX não-cumulativo, disponibilidade), roteamento do `consultar_politica`, as
  três tools de dados (incl. os ataques à verificação de identidade), a poda de histórico e a
  montagem do grafo.
- **`test_live.py`** é a avaliação do agente: cada caso declara as mensagens do cliente, a(s)
  ferramenta(s) que deviam ser chamadas e o que a resposta final deve / não deve conter (preço
  certo, sem promoção inventada, sem PII vazada em recusa de identidade, sem política
  inventada, persona, recusa de fora-de-escopo, etc.). Como o agente é não determinístico,
  **cada caso roda 3 vezes** e o que vale é a taxa (3/3, 2/3…) — passar uma vez não distingue
  acerto de sorte. Casos com oscilação conhecida são marcados `flaky=True`: entram no relatório
  com a taxa real, mas não derrubam o resultado. Cada execução escreve
  [`eval_report.md`](eval_report.md) com taxa e latência por caso.

---

## Arquitetura

```
       Streamlit (app.py)  ──ou──  REPL (agent.py)
                     │
                     ▼
        Agente ReAct  (LangChain + LangGraph, create_react_agent)
          • system prompt = persona + regras  (prompts.py)
          • histórico persistido por thread_id (SqliteSaver → emporio.db)
                     │
        ┌────────────┴───────────────┐
        ▼                            ▼
   4 tools (tools.py)          LM Studio (modelo local)
   ├─ buscar_produtos ────────┐
   ├─ detalhe_produto ────────┤──→  emporio.db  (SQLite; views v_produto, v_pedido_item)
   ├─ status_pedido ──────────┘         ▲
   └─ consultar_politica ───────→ policies.md   │  build_db.py: 6 CSVs → SQLite
                                               │  convert_policies.py: PDF → policies_raw.md
```

O modelo recebe as quatro ferramentas e decide, a cada turno, se responde direto ou se chama
uma delas. As tools de dados executam **SQL parametrizado** (o LLM nunca escreve SQL). A tool
de política devolve as seções relevantes do manual em markdown.

### As 4 ferramentas (tools)

| Ferramenta | Quando o agente usa | Retorno |
|---|---|---|
| `buscar_produtos(termo, categoria, preco_min, preco_max, apenas_disponiveis)` | catálogo, opções por tipo/preço, disponibilidade | lista com preço de tabela, preço promocional e preço no PIX. A faixa de preço filtra o **preço efetivo** (o promocional quando há promoção) |
| `detalhe_produto(nome_ou_id)` | preço/specs/promoção de **um** instrumento | ficha completa; desambigua se o nome casar vários |
| `status_pedido(order_id, identificador)` | andamento de um pedido | status, itens, valor, previsão, rastreio, dias **desde a compra** (e o aviso de que não há data de recebimento) — **só após conferir identidade** |
| `consultar_politica(topico)` | horário, endereço, pagamento, troca/devolução, frete, garantia, LGPD, escopo | seção(ões) do `policies.md` |

---

## Decisões técnicas e justificativas

> As decisões abaixo eram livres. O critério foi: **a solução mais simples que resolve bem o problema deste dataset** (65 produtos, 20 pedidos, um manual de 8 páginas), deixando o caminho de evolução explícito.

| Tecnologia | Papel no projeto | Motivação (detalhe) |
|---|---|---|
| **Python 3.11+** | linguagem | única exigência obrigatória do desafio |
| **LangGraph** — `create_react_agent`, `SqliteSaver` | laço do agente ReAct + persistência do histórico | laço de raciocínio, *binding* de ferramentas e checkpoint prontos e testados (§1, §7) |
| **LangChain** — `langchain-core`, `langchain-openai` | decorator `@tool`, tipos de mensagem, `ChatOpenAI` | `ChatOpenAI` é o adaptador de modelo que o `create_react_agent` espera; com `base_url` aponta direto pro LM Studio (§1) |
| **LM Studio** | serve o modelo local via API compatível com OpenAI | custo zero, offline, e a PII do cliente não sai da máquina — LGPD (§2) |
| **Qwen3.8-27B** (trocável; 3.5-9B como alternativa leve) | o modelo de linguagem | melhor *tool calling* da faixa aberta local + PT-BR bom; o `.env` troca o modelo sem tocar em código (§2) |
| **SQLite** (`sqlite3`, stdlib) | catálogo/pedidos consultáveis + histórico de conversa | modelagem explícita em *views*, *joins* limpos, um arquivo só, zero dependência (§4, §7) |
| **pandas** | ETL dos CSVs (`read_csv` → `to_sql`) | 2 linhas por CSV e inferência de tipo nas colunas mistas int/decimal; usado só no `build_db.py` (§4) |
| **pymupdf4llm** (+ `pymupdf`) | PDF de políticas → markdown | conversão reproduzível e versionada; usado só no `convert_policies.py`, em *build-time* (§3) |
| **Streamlit** | interface de chat | chat web em poucas linhas; `thread_id` editável para demonstrar a persistência (§8) |
| **python-dotenv** | configuração via `.env` | tira `MODEL` / `base_url` / data de referência do código e do git — estilo 12-factor (§10) |
| **`assert` + `__main__`** | testes (`test_agent.py` sem LLM, `test_live.py` contra o LM Studio) | sem framework, zero dependência de teste, rodam em qualquer lugar (§11) |

### 1. Abordagem do agente — ReAct com LangChain + LangGraph

`create_react_agent` (de `langgraph.prebuilt`): um loop em que o modelo alterna entre
raciocinar e chamar ferramentas até ter a resposta. O modelo fala com o LM Studio via
`ChatOpenAI(base_url=...)`. As ferramentas são funções Python decoradas com `@tool` (`langchain-core`).

- **Por que não RAG puro:** os dados mais consultados (preço, estoque, status de pedido) são
  estruturados e mudam — pedem *function calling* sobre um banco, não recuperação de texto.
- **Por que não um agente de SQL:** deixar um modelo local escrever SQL é frágil e
  arriscado. Ferramentas com SQL fixo e parametrizado dão o mesmo poder com muito menos risco.
- **Por que não uma única função "responder":** a força do exercício é justamente o agente
  *decidir* entre dados e políticas — isso é natural no ReAct com ferramentas bem descritas.
- **Por que o `create_react_agent` pronto e não montar o grafo à mão:** o laço ReAct, o
  *binding* de ferramentas e o checkpointer de histórico já vêm prontos e testados no LangGraph,

### 2. Modelo e provedor — LM Studio (modelo local)

- **Custo zero e offline.** Nenhuma chave de API, nenhuma cota.
- **Privacidade.** O manual da loja cita a LGPD e o atendimento lida com nome, e-mail e pedidos de clientes. Rodar o modelo localmente evita mandar esses dados para uma API de terceiros. Um argumento real de conformidade, não só de custo.
- **Trade-off assumido:** *tool calling* de modelos abertos pequenos é menos confiável que o de modelos frontier. Mitigações: só 4 ferramentas, descrições ricas, `temperature=0`, e um system prompt curto. O código é agnóstico ao modelo (`base_url` + `MODEL` no `.env`), então trocar por uma API é mudar duas variáveis.
- **Recomendação:** Qwen3.8-27B (`qwen/qwen3.8-27b`) — é o modelo do relatório versionado: **20/20 casos, 3 rodadas cada** ([`eval_report.md`](eval_report.md)). O Qwen3.5-9B, com que o projeto foi construído, é a alternativa leve: bem mais rápido, e foi com ele que apareceram os erros de *tool calling* que viraram regra de prompt. Modelos frontier via API resolveriam latência e confiabilidade de uma vez, ao custo de mandar PII para fora.
- **A tensão que esta escolha assume:** o problema de negócio do enunciado é *volume* — "a equipe está sobrecarregada com perguntas recorrentes". Os números são medidos, não estimados ([`eval_report.md`](eval_report.md), 60 execuções): **mediana de 56 s por caso**, e 415 s no pior (uma conversa de 7 turnos). Sem *streaming* nem fila, isso **demonstra** que a lógica do agente funciona, mas não ataca o volume: um atendente esperando um minuto por resposta não está menos sobrecarregado. Este protótipo otimiza para custo, privacidade e reprodutibilidade offline; um deployment real contra o volume seria outra decisão — modelo servido com *batching* (ou API), resposta em *streaming*, e uma fila de atendimento. O agente aqui é a peça que se prova primeiro; a camada de serving é o passo seguinte, não um detalhe.

### 3. Políticas — conversão com `pymupdf4llm` + ferramenta de seção (sem embeddings)

`convert_policies.py` usa `pymupdf4llm` para transformar o PDF de políticas em `policies_raw.md`
(reproduzível, versionado). Esse resultado passa por uma curadoria leve → `policies.md`
(headings sem `**bold**`, rodapés de página removidos, tabelas normalizadas). A tool
`consultar_politica` pontua as 10 seções por palavra-chave e título e devolve as mais
relevantes.

- **Por que não RAG com vector store:** o manual tem ~4 mil tokens e 10 seções bem delimitadas. Seria mais infraestrutura, mais latência e mais um ponto de falha para resolver um problema que uma tabela de palavras-chave resolve de forma **determinística** e explicável. RAG semântico só se justificaria com uma quantidade massiva de documentos.
- **Por que não jogar o manual inteiro no system prompt:** gastaria ~4k tokens de contexto em todo turno (a janela de um modelo local é menor, e em modelo frontier são 4k tokens gastos garantidos), além de misturar política irrelevante no raciocínio.

### 4. Tratamento dos dados — ETL para SQLite com views

`build_db.py` carrega os 6 CSVs em `emporio.db` com tipos normalizados e cria duas views queconcentram a regra de negócio:

- **`v_produto`**: junta a categoria, agrega a **maior promoção ativa** por produto(`promotions.csv` tem produtos com várias linhas; política 6.2: promoções não são cumulativas), e calcula:
  - `preco_promocional` (quando há promo ativa);
  - `preco_a_vista_pix` — 5% sobre a tabela, **mas** sem incidir sobre preço já promocional (política 6.2);
  - `disponivel` = `status = 'active'` e `stock_quantity > 0`.
- **`v_pedido_item`**: itens do pedido com nome e preço do produto.

**Por que pandas no ETL:** `pd.read_csv(...).to_sql(...)` resolve o carregamento em duas linhas por arquivo e já infere os tipos das colunas com int e decimal misturados. É a única dependência que o `build_db.py` usa; `csv` da stdlib + `INSERT` na mão seria mais código para o mesmo resultado.

**Por que SQLite e não manter os DataFrames na memória:** o SQLite deixa a modelagem explícita (tabelas + views documentam as regras de negócio), dá joins e agregações limpos, e é o mesmo arquivo que o checkpointer de conversa usa. O LLM nunca gera SQL — as tools usam consultas fixas com parâmetros.

### 5. Conceito de "hoje" — `DATA_REFERENCE_DATE` configurável

Todos os 20 pedidos do dataset são de outubro/2025 a março/2026. Contra a data real, **todo pedido estaria fora de qualquer prazo** (7 dias de arrependimento, 30 de defeito), e a demo sugerida no enunciado ("me arrependi, posso devolver?") nunca teria um caso positivo.

O dataset é um *snapshot*, então o agente ancora o "hoje" numa data de referência configurável
(padrão `2026-03-25`, logo após o último pedido). A tool `status_pedido` devolve os dias já
calculados — o agente compara com o prazo que vem do **texto da política**, sem regra de prazo
hard-coded.

**Qual relógio (corrigido depois de reler a política):** a data de referência resolve metade do
problema. A outra metade é *de quando* cada prazo conta. O manual §4.1 dá 7 dias corridos
**após o recebimento** do produto; §4.2 dá 30 dias **após a compra**. A tool só sabe a data da
compra — o dataset tem previsão de entrega, mas **nenhuma data de entrega efetiva**. Comparar
os 7 dias com o relógio da compra é medir a coisa errada, e era o que o prompt mandava fazer.

Agora `status_pedido` rotula o número como "há N dias **da compra**" e declara explicitamente
que o sistema não registra recebimento; o prompt manda o agente reparar de quando o prazo conta
e **perguntar ao cliente quando ele recebeu** se for o caso. Efeito colateral bom: com
`2026-03-25` nenhum pedido está a menos de 7 dias da compra, então o cenário do enunciado ("me
arrependi, posso devolver?") só tinha resposta negativa. Perguntando a data de recebimento, o
caso positivo passa a existir — e virou caso de eval
(`devolucao_recebido_dentro_do_prazo`).

### 6. Verificação de identidade — consciente de LGPD

Um pedido expõe PII (nome, e-mail, itens, previsão de entrega). `status_pedido` (função
`_identidade_confere` em `tools.py`) só libera os dados se o `identificador` for o
**e-mail exato** ou trouxer o **primeiro nome do cliente + ao menos duas partes distintas
do nome cadastrado**, com match de **palavra inteira** e **sem nenhuma palavra que não seja
do nome**. Rejeita: um nome só ("Ana"), um sobrenome só ("Santos"), pedaço de palavra
("ana" ⊂ "Mariana"), nome repetido ("Ana Ana"), e "spray" de nomes comuns.

### 7. Histórico de conversa — checkpointer SQLite do LangGraph

`SqliteSaver` sobre o mesmo `emporio.db`, indexado por `thread_id`. A conversa sobrevive ao
fechar o app: reabrir com o mesmo `thread_id` (campo na barra lateral do Streamlit) retoma o
contexto.

**Poda do histórico (`agent._podar`).** Persistir tudo e *reenviar* tudo são coisas diferentes.
Sem poda, o `create_react_agent` manda a conversa inteira ao modelo a cada turno; como
`consultar_politica` pode devolver 3 seções (~1.200 tokens), 10-15 turnos estouram a janela de
um modelo local — em silêncio, degradando as respostas antes de falhar. Um `pre_model_hook`
com `trim_messages` (`langchain-core`) corta pelos últimos `MAX_HISTORY_TOKENS` (padrão 8.000,
configurável no `.env`) **só o que vai para o LLM**; o histórico salvo continua completo, então
o `thread_id` ainda retoma a conversa toda.

O detalhe que faz isso funcionar é `start_on="human"`: cortar no meio de uma sequência de
ferramenta deixaria uma `ToolMessage` sem a chamada que a originou, e a API rejeita o request.
`test_poda_historico` (sem LLM) monta 240 mensagens sintéticas e verifica as duas coisas — que
podou e que não sobrou `ToolMessage` órfã. O caso `conversa_longa_nao_perde_a_ferramenta`
cobre o mesmo ponta a ponta, e
[`validacao_conversa_longa.md`](validacao_conversa_longa.md) registra a validação contra o
modelo real: 42 turnos até o corte disparar, mais um anexo com corte profundo (22 de 36
mensagens descartadas) — em nenhum dos dois a API recusou o request, e o agente seguiu chamando
a ferramenta certa.

### 8. Interface — Streamlit

Chat web pronto em poucas linhas, bom para a demonstração e para gerar os exemplos. O
`thread_id` fica editável na barra lateral para mostrar a persistência. Há também um REPL
(`python agent.py`) para teste rápido no terminal.

### 9. Persona e prompt — "melodIA"

O nome do assistente é **melodIA** (trocadilho *melodia* + *IA*). Foco em persona acolhedora e amigável pra deixar comprador confortável.

O system prompt (`prompts.py`) também carrega os **guardrails**: nunca informar preço/estoque/prazo sem ferramenta (seção 7.1 — "informações precisas"), sempre mostrar preço original + % + final nas promoções, oferecer alternativas para itens sem estoque, apresentar listas item a item, não corrigir dados que o cliente informa, não inventar marcas, e recusar assuntos fora do escopo (com exemplo concreto de recusa para ancorar um modelo pequeno).

**Grounding de política (mitigado, não eliminado):** o prompt manda o agente afirmar *apenas* o que aparece no texto que `consultar_politica` retornou, e dizer "vou confirmar com a equipe" quando a política não cobre a pergunta. Surgiu de uma falha real — o modelo tinha inventado "compensação por atraso na entrega", que não existe no manual. Para a mesma pergunta-isca, rodadas diferentes deram ora uma resposta 100% ancorada na §5, ora um resíduo ("não temos reembolso por atraso" + um prazo inventado). Fechar de vez exigiria um check pós-resposta determinístico ou o eval automatizado — ambos listados em "Com mais tempo".

Regra de política: vive só no texto, não no código nem no prompt.

### 10. Configuração — `.env` via `python-dotenv`

`config.py` lê um `.env` com `OPENAI_BASE_URL`, `MODEL`, `DATA_REFERENCE_DATE`. Mantém a configuração fora do código e do git, e torna o projeto agnóstico ao modelo/endpoint.

### 11. Testes — `assert` + `__main__`, sem framework

Dois níveis, ambos com `assert` e um `main()` próprio, sem pytest:

- **`test_agent.py`** (8 funções, sem LLM): a lógica determinística — views do ETL, roteamento de política, as tools de dados, os ataques à verificação de identidade (repetição, spray, sobrenome, *bound* de colisão cruzada) e a poda de histórico. Rápido, roda em qualquer lugar.
- **`test_live.py`** (20 casos × k rodadas, contra o LM Studio): a avaliação ponta a ponta — cada caso declara os turnos do cliente, a(s) ferramenta(s) esperada(s) e o que a resposta deve / não deve conter. Lento e não 100% determinístico (é o preço de avaliar um modelo local), mas é o que trava regressão de comportamento quando o prompt muda.

Evals: Cada execução escreve **[`eval_report.md`](eval_report.md)** com a taxa e a latência (mediana e pior caso) de cada caso. O arquivo é versionado de propósito: quem for avaliar o projeto vê o número sem precisar instalar o LM Studio e baixar o modelo.

pytest aqui seria uma dependência a mais sem ganho nessa escala.

---

## Limitações conhecidas

- **Confiabilidade do *tool calling* depende do modelo local.** Um modelo fraco pode responder preço/estoque sem chamar a ferramenta, ou vazar uma resposta fora de escopo.
- **Latência vs. o problema de volume.** Mediana de 56 s por caso e 415 s no pior, medidos em 60 execuções com o 27B local, sem streaming. O 9B é bem mais rápido, com tool calling menos confiável.
- **Sem guard determinístico de escopo.** A recusa de assuntos fora da loja é só via prompt.
- **Verificação de identidade não é autenticação.** Exige nome+sobrenome ou e-mail exato (ver decisão 6), mas não há login, código de confirmação nem rate limit — e `order_id` é sequencial. Suficiente para protótipo, não para produção.
- **Busca de produto é lexical** (casa palavras no nome e nas specs). "Violão para iniciante" não vira uma busca semântica.
- **`consultar_politica` é por palavra-chave.** Uma pergunta com vocabulário muito distante das palavras mapeadas pode não casar a seção certa.
- **Frete e parcelamento não são calculados** — o agente informa as regras da política, não simula valores para um CEP ou uma compra específica.
- **Dados sintéticos com ruído** (nomes x descrições inconsistentes) limitam o que a descrição pode ser usada para responder.

## Com mais tempo

- **LLM-as-judge** para os julgamentos que `contém`/`não contém` não alcança (tom, completude,
  se a recusa soou cordial). Hoje o eval só checa substring e ferramenta chamada.
- **Rodar o eval em CI**, com um modelo servido pequeno em vez de depender do LM Studio local —
  hoje é um comando manual, e por isso o relatório é versionado.
- **Guard de saída** determinístico para grounding de política: se a resposta final citar um
  prazo/regra que não aparece literalmente no texto que a tool retornou naquele turno,
  descartar e regenerar. Fecharia o resíduo que `test_live.py` hoje só detecta.
- **Guard de entrada** determinístico para assuntos fora de escopo e para *prompt injection*.
- **RAG semântico** no lugar da tabela de palavras-chave, se o corpo de políticas crescer.
- **Autenticação real** para consulta de pedido (código por e-mail/WhatsApp).
- **Busca semântica** de produtos (embeddings das descrições) para perguntas por "vibe".
- **Streaming** da resposta token a token na UI.
- **Fallback text-ReAct** automático quando o *tool calling* nativo do modelo falha.

---

## Uso de assistentes de código

Todo o projeto foi construído em par com o **Claude Code** — Claude Sonnet na construção e Claude Opus na revisão técnica e na rodada de correções que ela gerou, no seguinte fluxo:

1. **Leitura e entrevista (plan mode).** O Claude leu o enunciado, o manual de políticas e os 6 CSVs, mapeou os *quirks* dos dados, e então me entrevistou — **uma decisão de cada vez** — sobre as escolhas técnicas (abordagem do agente, acesso às políticas, camada de dados, data de referência, histórico, identificação, interface, modelo). Para cada uma ele apresentou opções com trade-offs e uma recomendação; **as decisões foram minhas**.
2. **O loop decisão → README.** Cada decisão fechada foi registrada na seção "Decisões técnicas" com a motivação, antes de virar código. Ajustes feitos depois (ex.: regras de prompt após ver falhas em conversas reais, ou o nome "melodIA") entram pelo mesmo loop: muda a decisão, muda a seção.
3. **Plano e execução por partes.** As decisões viraram um plano e um `CHECKLIST.md` em 8 partes. Cada parte: implementar → escrever o teste (`test_agent.py`, `assert` puro) → rodar → **um commit por parte** (histórico incremental, sem *force-push*, como o enunciado pede).
4. **Documentação viva.** `CLAUDE.md` (visão geral + decisões + armadilhas dos dados) e `CHECKLIST.md` foram mantidos atualizados ao longo do caminho.

O que **eu** decidi e revisei: a stack inteira (LangChain/LangGraph, LM Studio, `pymupdf4llm`, SQLite, Streamlit), todas as decisões técnicas, o nome do assistente, o recorte de cada parte e a redação final. O que o **Claude** fez: análise dos dados, primeira implementação de cada módulo, os testes, os rascunhos de documentação, e o *smoke test* que revelou os ajustes de prompt.
