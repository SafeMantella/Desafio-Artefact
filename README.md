# Empório da Música — Agente de Atendimento

Protótipo da **melodIA**, assistente virtual de atendimento ao cliente da **Empório da
Música**, loja (fictícia) de instrumentos musicais em Campo Grande/MS. Desafio técnico para
a vaga de AI Engineer na Artefact.

O agente assume a persona da loja, responde por mensagem de texto e sabe **quando consultar
dados** (catálogo, pedidos, promoções) e **quando consultar as políticas** (trocas, horários,
pagamento, frete, garantia). Perguntas fora do escopo da loja são recusadas com cordialidade.

---

## O que dá para perguntar

- *"Quais violões disponíveis até R$ 1000?"* → busca no catálogo, só o que está em estoque
- *"Quanto custa o Takamine GD20?"* → preço de tabela + preço à vista no PIX
- *"Qual o endereço e o horário da loja?"* → consulta o manual de políticas
- *"Me arrependi da compra do pedido 8, consigo devolver?"* → confirma a identidade, olha há
  quantos dias foi a compra e aplica a política de arrependimento (7 dias)
- *"Vocês vendem cordas de violão?"* → explica que a loja não trabalha com acessórios
- *"Me passa uma receita de bolo?"* → recusa educadamente e volta ao contexto da loja

Três a cinco conversas completas estão em [`examples/`](examples/).

---

## Como rodar

### Pré-requisitos

- **Python 3.11+**
- **[LM Studio](https://lmstudio.ai/)** com um modelo que suporte *tool use* / function calling.
  Desenvolvido e testado com **Qwen3.5-9B** (`qwen/qwen3.5-9b`); a família Qwen2.5-Instruct
  (7B+) e Llama-3.1-8B-Instruct também funcionam. Modelos maiores respondem melhor em
  português e chamam as ferramentas de forma mais confiável.
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
python test_agent.py              # 6 checks, sem depender do LLM
```

Cobrem a lógica não-trivial: views do ETL (preço promocional, PIX não-cumulativo,
disponibilidade), roteamento do `consultar_politica`, as três tools de dados (incluindo a
verificação de identidade) e a montagem do grafo do agente.

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
de política devolve a(s) seção(ões) relevante(s) do manual em markdown.

### As 4 ferramentas

| Ferramenta | Quando o agente usa | Retorno |
|---|---|---|
| `buscar_produtos(termo, categoria, preco_min, preco_max, apenas_disponiveis)` | catálogo, opções por tipo/preço, disponibilidade | lista com preço de tabela, preço promocional e preço no PIX |
| `detalhe_produto(nome_ou_id)` | preço/specs/promoção de **um** instrumento | ficha completa; desambigua se o nome casar vários |
| `status_pedido(order_id, identificador)` | andamento de um pedido | status, itens, valor, previsão, rastreio, dias desde a compra — **só após conferir identidade** |
| `consultar_politica(topico)` | horário, endereço, pagamento, troca/devolução, frete, garantia, LGPD, escopo | seção(ões) do `policies.md` |

---

## Decisões técnicas e justificativas

> As decisões abaixo eram livres. O critério foi: **a solução mais simples que resolve bem o
> problema deste dataset** (65 produtos, 20 pedidos, um manual de 8 páginas), deixando o caminho
> de evolução explícito.
>
> **O loop:** toda tecnologia ou biblioteca que entra no código entra aqui com a motivação.
> Quando uma decisão muda — inclusive por causa de um teste real (ver histórico de commits) —
> esta seção muda junto. A tabela é o índice; as subseções detalham as escolhas de arquitetura.

| Tecnologia | Papel no projeto | Motivação (detalhe) |
|---|---|---|
| **Python 3.11+** | linguagem | única exigência obrigatória do desafio |
| **LangGraph** — `create_react_agent`, `SqliteSaver` | laço do agente ReAct + persistência do histórico | laço de raciocínio, *binding* de ferramentas e checkpoint prontos e testados (§1, §7) |
| **LangChain** — `langchain-core`, `langchain-openai` | decorator `@tool`, tipos de mensagem, `ChatOpenAI` | `ChatOpenAI` é o adaptador de modelo que o `create_react_agent` espera; com `base_url` aponta direto pro LM Studio (§1) |
| **LM Studio** | serve o modelo local via API compatível com OpenAI | custo zero, offline, e a PII do cliente não sai da máquina — LGPD (§2) |
| **Qwen3.5-9B** (trocável) | o modelo de linguagem | melhor *tool calling* da faixa aberta pequena + PT-BR aceitável (§2) |
| **SQLite** (`sqlite3`, stdlib) | catálogo/pedidos consultáveis + histórico de conversa | modelagem explícita em *views*, *joins* limpos, um arquivo só, zero dependência (§4, §7) |
| **pandas** | ETL dos CSVs (`read_csv` → `to_sql`) | 2 linhas por CSV e inferência de tipo nas colunas mistas int/decimal; usado só no `build_db.py` (§4) |
| **pymupdf4llm** (+ `pymupdf`) | PDF de políticas → markdown | conversão reproduzível e versionada; usado só no `convert_policies.py`, em *build-time* (§3) |
| **Streamlit** | interface de chat | chat web em poucas linhas; `thread_id` editável para demonstrar a persistência (§8) |
| **python-dotenv** | configuração via `.env` | tira `MODEL` / `base_url` / data de referência do código e do git — estilo 12-factor (§10) |
| **`assert` + `__main__`** | testes (`test_agent.py`) | 6 checks sem framework, rodam em qualquer lugar, zero dependência de teste (§11) |

O metapacote `langchain` está em `requirements.txt` como guarda-chuva de versões; o código
importa os componentes (`langchain-core`, `langchain-openai`) e `langgraph` diretamente.

### 1. Abordagem do agente — ReAct com LangChain + LangGraph

`create_react_agent` (de `langgraph.prebuilt`): um laço em que o modelo alterna entre
raciocinar e chamar ferramentas até ter a resposta. O modelo fala com o LM Studio via
`ChatOpenAI(base_url=...)` — o LM Studio expõe a mesma API da OpenAI, então esse adaptador
do `langchain-openai` conecta sem código de cola. As ferramentas são funções Python
decoradas com `@tool` (`langchain-core`).

- **Por que não RAG puro:** os dados mais consultados (preço, estoque, status de pedido) são
  estruturados e mudam — pedem *function calling* sobre um banco, não recuperação de texto.
- **Por que não um agente de SQL:** deixar um modelo local de 9B escrever SQL é frágil e
  arriscado. Ferramentas com SQL fixo e parametrizado dão o mesmo poder com muito menos risco.
- **Por que não uma única função "responder":** a força do exercício é justamente o agente
  *decidir* entre dados e políticas — isso é natural no ReAct com ferramentas bem descritas.
- **Por que o `create_react_agent` pronto e não montar o grafo à mão:** o laço ReAct, o
  *binding* de ferramentas e o checkpointer de histórico já vêm prontos e testados no
  LangGraph; reimplementar isso não agregaria nada aqui.

### 2. Modelo e provedor — LM Studio (modelo local)

- **Custo zero e offline.** Nenhuma chave de API, nenhuma cota.
- **Privacidade.** O manual da loja cita a LGPD e o atendimento lida com nome, e-mail e pedidos
  de clientes. Rodar o modelo localmente evita mandar esses dados para uma API de terceiros —
  um argumento real de conformidade, não só de custo.
- **Trade-off assumido:** *tool calling* de modelos abertos pequenos é menos confiável que o de
  modelos frontier. Mitigações: só 4 ferramentas, descrições ricas, `temperature=0.3`, e um
  system prompt curto e imperativo. O código é agnóstico ao modelo (`base_url` + `MODEL` no
  `.env`), então trocar por uma API é mudar duas variáveis.
- **Recomendação:** Qwen3.5-9B (`qwen/qwen3.5-9b`) — foi o modelo do *smoke test* (6/6
  cenários). A família Qwen2.5-Instruct 7B+ é uma alternativa mais leve. Modelos frontier via
  API resolveriam a latência e a confiabilidade do *tool calling*, ao custo de mandar PII pra
  fora.

### 3. Políticas — conversão com `pymupdf4llm` + ferramenta de seção (sem embeddings)

`convert_policies.py` usa `pymupdf4llm` para transformar o PDF em `policies_raw.md`
(reproduzível, versionado). Esse resultado passa por uma curadoria leve → `policies.md`
(headings sem `**bold**`, rodapés de página removidos, tabelas normalizadas). A tool
`consultar_politica` pontua as 10 seções por palavra-chave e título e devolve a(s) mais
relevante(s).

- **Por que não RAG com vector store:** o manual tem ~4 mil tokens e 10 seções bem
  delimitadas. Chunking + embeddings + FAISS/Chroma seria mais infraestrutura, mais latência e
  mais um ponto de falha para resolver um problema que uma tabela de palavras-chave resolve de
  forma **determinística** e explicável. RAG semântico só se justificaria com uma quantidade massiva de
  documentos.
- **Por que não jogar o manual inteiro no system prompt:** gastaria ~4k tokens de contexto em
  todo turno (a janela de um modelo local é menor) e misturaria política irrelevante no
  raciocínio.
- **Duas divergências no PDF original** foram resolvidas e anotadas no cabeçalho de
  `policies.md`: o WhatsApp aparece como `(67) 3341-4444` (seção 1.2) e `(67) 3321-4500`
  (seção 7) — adotado o do quadro "Dados da Empresa"; e o e-mail aparece com e sem acento —
  adotado `contato@emporiodamusica.com.br`.

### 4. Tratamento dos dados — ETL para SQLite com views

`build_db.py` carrega os 6 CSVs em `emporio.db` com tipos normalizados e cria duas views que
concentram a regra de negócio:

- **`v_produto`**: junta a categoria, agrega a **maior promoção ativa** por produto
  (`promotions.csv` tem produtos com várias linhas; política 6.2: promoções não são
  cumulativas), e calcula:
  - `preco_promocional` (quando há promo ativa);
  - `preco_a_vista_pix` — 5% sobre a tabela, **mas** sem incidir sobre preço já promocional
    (política 6.2);
  - `disponivel` = `status = 'active'` **e** `stock_quantity > 0` (há produtos `active` com
    estoque 0).
- **`v_pedido_item`**: itens do pedido com nome e preço do produto.

Quirks tratados: preços em `int` e `decimal` na mesma coluna; `status` de produto
(`active` / `discontinued` / `coming_soon`); campos de pedido (`tracking_code`,
`estimated_delivery`) só preenchidos para pedidos enviados; strings vazias → `NULL`. Nomes de
produto claramente sintéticos e às vezes inconsistentes com a descrição (ex.: "Music Man Bass
1X" com descrição de "Fender Jazz Bass") — a decisão foi **confiar nos campos estruturados**
(nome, preço, categoria, estoque, status) e tratar a descrição como texto livre.

**Por que pandas no ETL:** `pd.read_csv(...).to_sql(...)` resolve o carregamento em duas
linhas por arquivo e já infere os tipos das colunas com int e decimal misturados. É a única
dependência que o `build_db.py` usa; `csv` da stdlib + `INSERT` na mão seria mais código
para o mesmo resultado.

**Por que SQLite e não manter os DataFrames na memória:** o SQLite deixa a modelagem
explícita (tabelas + views documentam as regras de negócio), dá joins e agregações limpos, e
é o mesmo arquivo que o checkpointer de conversa usa. O LLM nunca gera SQL — as tools usam
consultas fixas com parâmetros.

### 5. Conceito de "hoje" — `DATA_REFERENCE_DATE` configurável

Todos os 20 pedidos do dataset são de outubro/2025 a março/2026. Contra a data real, **todo
pedido estaria fora de qualquer prazo** (7 dias de arrependimento, 30 de defeito), e a demo
sugerida no enunciado ("me arrependi, posso devolver?") nunca teria um caso positivo.

O dataset é um *snapshot*, então o agente ancora o "hoje" numa data de referência configurável
(padrão `2026-03-25`, logo após o último pedido). A tool `status_pedido` devolve
`dias_desde_pedido` já calculado — o agente compara com o prazo que vem do **texto da
política**, sem regra de prazo hard-coded.

### 6. Verificação de identidade — consciente de LGPD

Um pedido expõe PII (nome, e-mail, itens, previsão de entrega). `status_pedido` (função
`_identidade_confere` em `tools.py`) só libera os dados se o `identificador` for o
**e-mail exato** ou trouxer o **primeiro nome do cliente + ao menos duas partes distintas
do nome cadastrado**, com match de **palavra inteira** e **sem nenhuma palavra que não seja
do nome**. Rejeita: um nome só ("Ana"), um sobrenome só ("Santos"), pedaço de palavra
("ana" ⊂ "Mariana"), nome repetido ("Ana Ana"), e "spray" de nomes comuns.

Esta é a segunda versão. A primeira (match de substring, um token) e uma correção intermediária
(≥2 tokens, mas ignorando palavras inválidas e sem deduplicar) eram burláveis: `order_id`
sequencial + só saber o primeiro nome = 100% de acesso, ou uma string única de nomes comuns =
70% às cegas. As duas falhas viraram teste (`test_identidade_nao_burlavel`: 50 clientes ×
ataques de repetição/spray/sobrenome + casos legítimos). Ainda **não** é autenticação de
verdade — produção pediria login, código por e-mail/WhatsApp e rate limit no `order_id` (nas
limitações).

### 7. Histórico de conversa — checkpointer SQLite do LangGraph

`SqliteSaver` sobre o mesmo `emporio.db`, indexado por `thread_id`. A conversa sobrevive ao
fechar o app: reabrir com o mesmo `thread_id` (campo na barra lateral do Streamlit) retoma o
contexto. Custo de implementação: ~5 linhas.

### 8. Interface — Streamlit

Chat web pronto em poucas linhas, bom para a demonstração e para gerar os exemplos. O
`thread_id` fica editável na barra lateral para mostrar a persistência. Há também um REPL
(`python agent.py`) para teste rápido no terminal.

### 9. Persona e prompt — "melodIA"

O nome do assistente é **melodIA** (trocadilho *melodia* + *IA*). Nenhum material do desafio
dá um nome; a escolha foi minha, e ela combina com a identidade musical da loja e com o tom
informal que o manual pede — um nome com o qual o cliente conversa, não um rótulo genérico.
Fora isso, a persona vem da **seção 7 do manual**: tom acolhedor ("um amigo que entende de
música"), respostas curtas estilo WhatsApp, cumprimenta pelo nome quando disponível.

O system prompt (`prompts.py`) também carrega os **guardrails**: nunca informar
preço/estoque/prazo sem ferramenta (seção 7.1 — "informações precisas"), sempre mostrar preço
original + % + final nas promoções, oferecer alternativas para itens sem estoque, apresentar
listas item a item, não corrigir dados que o cliente informa, não inventar marcas, e recusar
assuntos fora do escopo (com exemplo concreto de recusa para ancorar um modelo pequeno).

**Grounding de política (mitigado, não eliminado):** o prompt manda o agente afirmar *apenas*
o que aparece no texto que `consultar_politica` retornou, e dizer "vou confirmar com a equipe"
quando a política não cobre a pergunta. Surgiu de uma falha real — o modelo tinha inventado
"compensação por atraso na entrega", que não existe no manual. A regra **reduz** a frequência
mas **não a zera**: para a mesma pergunta-isca, rodadas diferentes deram ora uma resposta
100% ancorada na §5, ora um resíduo ("não temos reembolso por atraso" + um prazo inventado).
Guardrail de prompt sobre modelo local (`temperature=0.3`) é probabilístico. Fechar de vez
exigiria um check pós-resposta determinístico ou o eval automatizado — ambos listados em
"Com mais tempo".

Várias dessas regras foram acrescentadas **depois de observar falhas em conversas reais** —
ver os commits `fix: ...` e `prompt: ...`.

### 10. Configuração — `.env` via `python-dotenv`

`config.py` lê um `.env` (não versionado) com `OPENAI_BASE_URL`, `MODEL`,
`DATA_REFERENCE_DATE`. Mantém a configuração fora do código e do git, e torna o projeto
agnóstico ao modelo/endpoint — trocar o LM Studio por uma API é mudar duas linhas do `.env`,
sem tocar em código.

### 11. Testes — `assert` + `__main__`, sem framework

`test_agent.py` são 6 funções com `assert`, rodadas por um `main()` próprio. Cobrem a lógica
não-trivial (views do ETL, roteamento de política, verificação de identidade, montagem do
grafo) sem chamar o LLM. Para 6 checks, pytest seria uma dependência a mais sem ganho;
`python test_agent.py` roda em qualquer lugar.

---

## Limitações conhecidas

- **Confiabilidade do *tool calling* depende do modelo local.** Um modelo fraco pode responder
  preço/estoque sem chamar a ferramenta, ou vazar uma resposta fora de escopo. Com Qwen3.5-9B o
  comportamento no smoke test foi bom (6/6 cenários), mas não é garantido a 100%.
- **Latência.** Localmente, cada turno leva de ~10 s a ~2 min, dependendo do modelo, do
  hardware e de quantas ferramentas o agente encadeia num turno. Aceitável para demonstração,
  não para produção — uma API resolveria.
- **Sem guard determinístico de escopo.** A recusa de assuntos fora da loja é só via prompt.
- **Verificação de identidade não é autenticação.** Exige nome+sobrenome ou e-mail exato
  (ver decisão 6), mas não há login, código de confirmação nem rate limit — e `order_id` é
  sequencial. Suficiente para protótipo, não para produção.
- **Busca de produto é lexical** (casa palavras no nome e nas specs). "Violão para iniciante"
  não vira uma busca semântica.
- **`consultar_politica` é por palavra-chave.** Uma pergunta com vocabulário muito distante das
  palavras mapeadas pode não casar a seção certa.
- **Frete e parcelamento não são calculados** — o agente informa as regras da política, não
  simula valores para um CEP ou uma compra específica.
- **Dados sintéticos com ruído** (nomes x descrições inconsistentes) limitam o que a descrição
  pode ser usada para responder.

## Com mais tempo

- **Camada de avaliação** (casos fixos rodados contra o LLM: pergunta → ferramenta esperada →
  substring esperada/proibida) medindo escolha de ferramenta, guardrails e aplicação de
  política. É o que fecharia o resíduo do grounding de forma repetível.
- **Guard de saída** determinístico para grounding de política: se a resposta final citar um
  prazo/regra que não aparece literalmente no texto que a tool retornou naquele turno,
  descartar e regenerar.
- **Guard de entrada** determinístico para assuntos fora de escopo e para *prompt injection*.
- **RAG semântico** no lugar da tabela de palavras-chave, se o corpo de políticas crescer.
- **Autenticação real** para consulta de pedido (código por e-mail/WhatsApp).
- **Busca semântica** de produtos (embeddings das descrições) para perguntas por "vibe".
- **Streaming** da resposta token a token na UI.
- **Fallback text-ReAct** automático quando o *tool calling* nativo do modelo falha.

---

## Uso de assistentes de código

Todo o projeto foi construído em par com o **Claude Code** (modelo Claude Sonnet), no seguinte
fluxo:

1. **Leitura e entrevista (plan mode).** O Claude leu o enunciado, o manual de políticas e os 6
   CSVs, mapeou os *quirks* dos dados, e então me entrevistou — **uma decisão de cada vez** —
   sobre as escolhas técnicas (abordagem do agente, acesso às políticas, camada de dados, data
   de referência, histórico, identificação, interface, modelo). Para cada uma ele apresentou
   opções com trade-offs e uma recomendação; **as decisões foram minhas**.
2. **O loop decisão → README.** Cada decisão fechada foi registrada na seção "Decisões
   técnicas" com a motivação, antes de virar código. Ajustes feitos depois (ex.: regras de
   prompt após ver falhas em conversas reais, ou o nome "melodIA") entram pelo mesmo loop: muda
   a decisão, muda a seção.
3. **Plano e execução por partes.** As decisões viraram um plano e um `CHECKLIST.md` em 8
   partes. Cada parte: implementar → escrever o teste (`test_agent.py`, `assert` puro) → rodar →
   **um commit por parte** (histórico incremental, sem *force-push*, como o enunciado pede).
4. **Documentação viva.** `CLAUDE.md` (visão geral + decisões + armadilhas dos dados) e
   `CHECKLIST.md` foram mantidos atualizados ao longo do caminho.

O que **eu** decidi e revisei: a stack inteira (LangChain/LangGraph, LM Studio, `pymupdf4llm`,
SQLite, Streamlit), todas as decisões técnicas, o nome do assistente, o recorte de cada parte
e a redação final. O que o **Claude** fez: análise dos dados, primeira implementação de cada
módulo, os testes, os rascunhos de documentação, e o *smoke test* que revelou os ajustes de
prompt.

---

## Estrutura do repositório

```
config.py            paths, modelo, base_url, DATA_REFERENCE_DATE (lê .env)
build_db.py          ETL: data/*.csv → emporio.db (tabelas + views)
convert_policies.py  PDF de políticas → policies_raw.md (pymupdf4llm)
policies_raw.md      saída bruta da conversão (reproduzível)
policies.md          versão curada, usada pela tool consultar_politica
tools.py             as 4 ferramentas (SQL parametrizado; política por palavra-chave)
prompts.py           system prompt — persona + regras
agent.py             create_react_agent + checkpointer SQLite; REPL em __main__
app.py               interface Streamlit
test_agent.py        6 checks assert-based (não usam o LLM)
CLAUDE.md            visão geral para retomar o projeto depois
CHECKLIST.md         progresso por partes
data/                dados fornecidos (não alterados)
examples/            3-5 conversas de exemplo
```
