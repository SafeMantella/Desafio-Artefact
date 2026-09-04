# Empório da Música — Agente de Atendimento

Protótipo da **melodIA**, assistente virtual de atendimento ao cliente da **Empório da
Música**, loja (fictícia) de instrumentos musicais em Campo Grande/MS. Desafio técnico para
a vaga de AI Engineer na Artefact.

O agente assume a persona da loja, responde por mensagem de texto e sabe **quando consultar
dados** (catálogo, pedidos, promoções) e **quando consultar as políticas** (trocas, horários,
pagamento, frete, garantia). Perguntas fora do escopo da loja são recusadas educadamente.

> ### ⏱️ Para o agente, hoje é **25/03/2026**
>
> O dataset fornecido é um *snapshot*: os 20 pedidos vão de out/2025 a **22/03/2026**.
> Contra a data real do relógio, todo pedido estaria fora de todo prazo (7 dias de
> arrependimento, 30 de defeito, 90 de garantia) e a demo do enunciado — *"me arrependi,
> posso devolver?"* — nunca teria um caso positivo. Por isso o "hoje" do agente é uma data
> de referência ancorada logo após o último pedido, e não `date.today()`.
>
> Vale para tudo o que você vai ver aqui: as conversas de [`examples/`](examples/), os casos
> de [`eval_report.md`](eval_report.md) e os testes. Muda numa variável —
> `DATA_REFERENCE_DATE` no `.env` — sem tocar em código. **O porquê completo está na
> [decisão 5](#5-conceito-de-hoje--data_reference_date-configurável).**

---

## O que dá para perguntar

- *"Quais violões disponíveis até R$ 1000?"* → busca no catálogo, só o que está em estoque
- *"Quanto custa o Takamine GD20?"* → preço de tabela + preço à vista no PIX
- *"Qual o endereço e o horário da loja?"* → consulta o manual de políticas
- *"Me arrependi da compra do pedido 7, consigo devolver?"* → confirma a identidade, lê a
  política, percebe que o prazo de arrependimento conta do **recebimento** (dado que o sistema
  não tem) e pergunta ao cliente quando ele recebeu antes de responder
- *"Quais ukuleles até 500 reais?"* → a faixa vale sobre o preço **efetivo**: entra o que está a 439,20  com promoção, mesmo com tabela em R$ 549
- *"Tem violão de tampo sólido em spruce?"* ou *"teclado de 61 teclas"* → busca pela
  **especificação**, não pelo modelo — o caso do músico que já sabe o que quer
- *"Vocês têm saxofone?"* → a loja trabalha com sopros, mas o catálogo está sem itens da categoria — e o agente diz isso, em vez de listar outra coisa
- *"Vocês vendem cordas de violão?"* → explica que a loja não trabalha com acessórios
- *"Me passa uma receita de bolo?"* → recusa educadamente e volta ao contexto da loja

Cinco conversas completas estão em [`examples/`](examples/), e a avaliação automática de 29
cenários (3 rodadas cada) em [`eval_report.md`](eval_report.md).

---

## Como rodar

### Pré-requisitos

- **Python 3.11+**
- **[LM Studio](https://lmstudio.ai/)** com um modelo que atenda a três requisitos:
  suporte a *tool use* / function calling, português do Brasil decente e janela de
  contexto de 16k ou mais. O projeto não depende de nenhum modelo específico — o `.env`
  troca o modelo e o endpoint sem tocar em código, e foi exercitado com vários portes
  diferentes ao longo do desenvolvimento. Qual foi usado na avaliação versionada está no
  cabeçalho do [`eval_report.md`](eval_report.md), que o próprio `test_live.py` escreve.
  Modelos maiores acertam mais o *tool calling* e escrevem melhor em português, ao custo
  de latência (ver decisão 2). No LM Studio: GPU offload no máximo.

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
                                   # DATA_REFERENCE_DATE=2026-03-25 já vem preenchida:
                                   # é o "hoje" do agente (ver o quadro no topo)

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
| `MODEL` | *(defina o seu)* | id exato do modelo carregado no LM Studio, como aparece na aba Developer |
| `DATA_REFERENCE_DATE` | `2026-03-25` | **"hoje" do agente.** O dataset é um snapshot; sem isso todo pedido fica fora de prazo — ver [decisão 5](#5-conceito-de-hoje--data_reference_date-configurável) |

### Testes

```bash
python test_agent.py             # 11 checks determinísticos, sem LLM — segundos
python test_live.py              # 29 casos × 3 rodadas contra o LM Studio — horas
python test_live.py --rodadas 1  # 1 rodada só, para iterar
python test_live.py identidade   # só os casos cujo nome contém "identidade"
```

- Os dois usam `DATA_REFERENCE_DATE=2026-03-25`: asserts de prazo ("há 79 dias", "7 dias")
  só fazem sentido nessa âncora. `test_agent.py` checa isso logo no início e falha dizendo
  qual data ele esperava, em vez de acusar um erro que seria de configuração.
- **`test_agent.py`** cobre a lógica não-trivial sem chamar o modelo: views do ETL (preço
  promocional, PIX não-cumulativo, disponibilidade, normalização de dinheiro, correção de
  marca), roteamento das 10 seções de `consultar_politica`, a curadoria de `policies.md` sem
  perda, as tools de dados (incl. identidade contra os 20 pedidos), a aritmética de
  parcelamento, a poda de histórico e a montagem do grafo.
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

O modelo recebe as cinco ferramentas e decide, a cada turno, se responde direto ou se chama
uma delas. As tools de dados executam **SQL parametrizado** (o LLM nunca escreve SQL). A tool
de política devolve as seções relevantes do manual em markdown.

### As 5 ferramentas (tools)

| Ferramenta | Quando o agente usa | Retorno |
|---|---|---|
| `buscar_produtos(termo, categoria, preco_min, preco_max, apenas_disponiveis)` | catálogo, opções por tipo/preço, disponibilidade, **busca por especificação** (`termo` casa no nome E nas specs: "tampo spruce", "61 teclas", "7 cordas") | lista com preço de tabela, preço promocional e preço no PIX. A faixa de preço filtra o **preço efetivo** (o promocional quando há promoção) |
| `detalhe_produto(nome_ou_id)` | preço/specs/promoção de **um** instrumento | ficha completa; desambigua se o nome casar vários |
| `status_pedido(order_id, identificador)` | andamento de um pedido | status, itens, valor, previsão, rastreio, dias **desde a compra** (e o aviso de que não há data de recebimento) — **só após conferir identidade** |
| `consultar_politica(topico)` | horário, endereço, pagamento, troca/devolução, frete, garantia, LGPD, escopo | seção(ões) do `policies.md` |
| `simular_pagamento(valor, entrega_em_campo_grande)` | **conta** sobre um valor: quantas parcelas cabem, quanto fica cada uma, preço no PIX, frete metropolitano | simulação pronta; para fora de Campo Grande declara que o frete não é calculável e manda oferecer contato humano |

Uma busca é **uma** chamada: `buscar_produtos` devolve a lista inteira (até 20 itens) numa
só ida à ferramenta — 20 resultados não são 20 tool calls. `detalhe_produto` é que é de um
instrumento por chamada, porque o seu trabalho é desambiguar um nome.

---

## Decisões técnicas e justificativas

> As decisões abaixo eram livres. O critério foi: **a solução mais simples que resolve bem o problema deste dataset** (65 produtos, 20 pedidos, um manual de 8 páginas), deixando o caminho de evolução explícito.

| Tecnologia | Papel no projeto | Motivação (detalhe) |
|---|---|---|
| **Python 3.11+** | linguagem | única exigência obrigatória do desafio |
| **LangGraph** — `create_react_agent`, `SqliteSaver` | laço do agente ReAct + persistência do histórico | laço de raciocínio, *binding* de ferramentas e checkpoint prontos e testados (§1, §7) |
| **LangChain** — `langchain-core`, `langchain-openai` | decorator `@tool`, tipos de mensagem, `ChatOpenAI` | `ChatOpenAI` é o adaptador de modelo que o `create_react_agent` espera; com `base_url` aponta direto pro LM Studio (§1) |
| **LM Studio** | serve o modelo local via API compatível com OpenAI | custo zero, offline, e a PII do cliente não sai da máquina — LGPD (§2) |
| **Modelo local aberto** (qualquer um com *tool use*; trocável pelo `.env`) | o modelo de linguagem | o código é agnóstico — `base_url` + `MODEL` no `.env`; o que muda entre modelos é confiabilidade do *tool calling* e latência, não o código (§2) |
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
- **Trade-off assumido:** *tool calling* de modelos abertos pequenos é menos confiável que o de modelos frontier. Mitigações: só 5 ferramentas, descrições ricas, `temperature=0`, e um system prompt curto. O código é agnóstico ao modelo (`base_url` + `MODEL` no `.env`), então trocar por uma API é mudar duas variáveis.
- **Como escolher:** o eixo é confiabilidade de *tool calling* contra latência. Modelos menores respondem em segundos e erram mais a chamada de ferramenta — foram os erros deles, vistos em conversa real, que viraram regra explícita no prompt. Modelos maiores acertam mais e demoram proporcionalmente. O [`eval_report.md`](eval_report.md) registra qual modelo gerou aquele resultado, com taxa e latência por caso, para a comparação ser sobre número e não sobre impressão. Modelos frontier via API resolveriam latência e confiabilidade de uma vez, ao custo de mandar PII para fora.
- **A tensão que esta escolha assume:** o problema de negócio do enunciado é *volume* — "a equipe está sobrecarregada com perguntas recorrentes". Os números são medidos, não estimados ([`eval_report.md`](eval_report.md), 87 execuções): **mediana de 32 s por caso**, e 177 s no pior — `conversa_longa_nao_perde_a_ferramenta`, sete turnos com ferramenta em quase todos. Valem para o modelo daquele relatório; trocar de modelo move os dois números, e é por isso que o relatório versionado registra qual foi. Sem *streaming* nem fila, isso **demonstra** que a lógica do agente funciona, mas não ataca o volume: um atendente esperando meio minuto por resposta não está menos sobrecarregado. Este protótipo otimiza para custo, privacidade e reprodutibilidade offline; um deployment real contra o volume seria outra decisão — modelo servido com *batching* (ou API), resposta em *streaming*, e uma fila de atendimento. O agente aqui é a peça que se prova primeiro; a camada de serving é o passo seguinte, não um detalhe.

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

**Por que pandas no ETL:** `pd.read_csv(...).to_sql(...)` resolve o carregamento em duas linhas por arquivo e já infere os tipos das colunas com int e decimal misturados (`products.price_brl` tem 53 valores inteiros e 12 decimais; `orders.total_brl` idem). A normalização para 2 casas é um passo **explícito** do `build_db.py` — inferência silenciosa é ótima até o dia em que muda. É a única dependência que o `build_db.py` usa; `csv` da stdlib + `INSERT` na mão seria mais código para o mesmo resultado.

#### Armadilhas dos dados

O dataset é sintético e tem peculiaridades que não dão erro — dão resposta errada, se você
tratar o dado com ingenuidade. Cada uma virou código:

| Armadilha | Onde aparece | O que o código faz |
|---|---|---|
| Linhas fora de ordem | `products.csv`: ids 81–130, depois 145, depois 131–144 | ordenar por preço/`product_id`, nunca confiar na ordem do arquivo |
| `status = 'active'` ≠ disponível | produto 96 (Giannini GF-3D) é `active` com estoque 0 | `disponivel = active AND stock > 0` → 61 de 65. Foi essa armadilha que produziu o bug de o agente dizer "não está no catálogo" para item que existe sem estoque |
| Promoções duplicadas | `promotions.csv` tem 25 linhas, só 4 ativas, com produto repetido | a view agrega `MAX(discount_percent)` entre as ativas (§6.2: não são cumulativas) |
| Sem data de entrega efetiva | `orders.csv` tem previsão, não recebimento | `status_pedido` declara isso e o agente pergunta ao cliente (ver decisão 5) |
| Sem preço unitário no pedido | `order_items.csv` só tem quantidade | `status_pedido` informa o total do pedido e avisa quando ele diverge da soma a preço de tabela |
| Nome × descrição se contradizem | 6 produtos (ver abaixo) | corrigido no ETL a cada build |

#### Uma correção declarada no dado

10 produtos (ids 135–144) têm nome de template — `Music Man Bass 1X Electric Bass`,
`Bateria Acústica Yamaha Kit 1 Studio`, `Teclado Sintetizador Korg Synth 1 Pro` — e em **6**
deles a descrição cita uma marca **diferente** da do nome. Não é typo: o gerador montou nome
e descrição em passes independentes.

| Produto | Nome diz | Descrição dizia |
|---|---|---|
| 135 | Music Man | Fender Jazz Bass |
| 137 | Yamaha | Ibanez |
| 139 | Yamaha | Pearl Export |
| 140 | Pearl | Tama |
| 142 | Korg | Roland |
| 144 | Roland | Yamaha |

Deixar como estava significa o agente ler a descrição e oferecer ao cliente uma marca que a
loja não vende com aquele nome. Então `build_db.py` **corrige a marca da descrição a cada
build**, por regra (lista explícita de marcas + match de palavra inteira), com um `assert`
de que são exatamente 6 linhas — se o dado mudar, o build falha em vez de reescrever o
catálogo em silêncio.

Duas coisas ficam de fora, de propósito: **os arquivos em `data/` não são tocados** (a
correção vive no ETL, sobre o DataFrame), e só a **marca** é trocada — nome de modelo alheio
("Jazz Bass", "Export") permanece, porque reescrevê-lo seria inventar dado em vez de
resolver a contradição.

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

**Por que não `date.today()` como padrão:** cair no relógio real quando a variável não
existe transformaria, em silêncio, toda resposta de prazo em "fora do prazo" na máquina de
quem esqueceu o `.env`. Um default fixo erra de forma previsível; um default dinâmico erra
de forma que ninguém percebe.

### 6. Verificação de identidade — consciente de LGPD

Um pedido expõe PII (nome, e-mail, itens, valor, previsão de entrega, rastreio).
`status_pedido` só libera os dados com **número do pedido + e-mail exato** do cadastro
(`_identidade_confere` em `tools.py`, normalizando caixa e acento). Nome não serve, nem o
nome completo do próprio cliente.

**Como chegamos aqui.** A primeira versão aceitava nome por substring e era 100% burlável
às cegas; a segunda, por agregação de partes do nome, ~70%. A terceira exigia primeiro nome
+ duas partes distintas, com match de palavra inteira — resistia a spray de nomes comuns e a
"Ana Ana", mas ainda deixava colidir três pares de clientes cujo nome é subconjunto do
outro. Trocar por e-mail exato apagou a heurística inteira e o resíduo junto: a verificação
virou uma comparação de string, que não tem como regredir.

**O trade-off, assumido:** ficou mais seguro e menos amigável. O cliente que oferece o nome
completo é recusado e precisa confirmar o e-mail da compra — que é o que um e-commerce real
pede. `test_identidade_nao_burlavel` varre os 20 pedidos: e-mail certo abre, nome recusa,
e-mail com um caractere trocado recusa.

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

**Quando o corte começa depende do modelo.** Numa validação de 28 turnos pela interface do
Streamlit, com um modelo mais verboso, o histórico cresceu ~340 tokens por turno: 5.100 aos
15 turnos e 9.600 aos 28, em 94 mensagens com 14 chamadas de ferramenta. Nesse ritmo o padrão
de 8.000 só passa a cortar por volta do 23º turno — contra os 42 da validação acima. Rodando
`_podar` sobre esse histórico real com tetos menores (4.000 e 1.000), ele corta de 71 para 35
e para 11 mensagens, sempre dentro do teto e **sempre sem `ToolMessage` órfã**. A conclusão
prática: o número de turnos que cabe não é uma propriedade do agente, é do modelo — por isso
o teto é configurável e a verificação de órfã é o que realmente trava o bug.

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

- **`test_agent.py`** (11 funções, sem LLM): a lógica determinística — views do ETL e a correção de marca, roteamento das 10 seções de política, as tools de dados, a verificação de identidade contra os 20 pedidos, a aritmética de `simular_pagamento` (e a conferência das constantes contra o manual) e a poda de histórico. Inclui `test_policies_sem_perda`, que garante que a curadoria de `policies.md` mexeu em forma e não em conteúdo: todo número, valor e e-mail do `policies_raw.md` sobrevive no curado. Rápido, roda em qualquer lugar.
- **`test_live.py`** (29 casos × k rodadas, contra o LM Studio): a avaliação ponta a ponta — cada caso declara os turnos do cliente, a(s) ferramenta(s) esperada(s) e o que a resposta deve / não deve conter. Lento e não 100% determinístico (é o preço de avaliar um modelo local), mas é o que trava regressão de comportamento quando o prompt muda.

Evals: Cada execução escreve **[`eval_report.md`](eval_report.md)** com a taxa e a latência (mediana e pior caso) de cada caso. O arquivo é versionado de propósito: quem for avaliar o projeto vê o número sem precisar instalar o LM Studio e baixar o modelo.

pytest aqui seria uma dependência a mais sem ganho nessa escala.

### 12. Parcelamento e frete — a única regra de política que virou código

`simular_pagamento` calcula quantas parcelas cabem num valor, quanto fica cada uma, o preço
no PIX e o frete metropolitano. Isso contraria a convenção do projeto (regra de política
vive no texto, não no código) e a exceção é deliberada: **é aritmética, e aritmética é onde
o modelo local alucina**. "R$ 549 em 12x" dá parcela de R$ 45,75 — abaixo do mínimo de
R$ 100 da faixa — e o agente respondia "pode sim" quando tinha que fazer a conta de cabeça
a partir do texto da §3.1. O teto real ali é 6x de R$ 91,50.

Para a exceção não virar dívida escondida, ela vem com um guard-rail:

1. Todos os números ficam numa **tabela única** no topo do módulo, com o parágrafo do manual
   anotado ao lado (`_PIX_DESCONTO`, `_FAIXAS_PARCELAMENTO`, `_FRETE_CG`).
2. `test_simular_pagamento` confere **cada constante contra o texto de `policies.md`**. Se o
   manual mudar e o código não, o teste quebra dizendo qual constante divergiu. É o que
   torna a duplicação sustentável em vez de invisível.

O frete entra só na metade calculável (região metropolitana: grátis acima de R$ 500, senão
R$ 35). Para outras cidades depende de CEP, peso e dimensões: a ferramenta **declara que não
calcula**, manda informar as modalidades da §5.2 e oferecer o contato da equipe para
cotação. Uma tool que só reimprimisse a §5 seria uma segunda porta para a mesma fonte —
`consultar_politica` já faz isso.

---

## Limitações conhecidas

- **Confiabilidade do *tool calling* depende do modelo local.** Um modelo fraco pode responder preço/estoque sem chamar a ferramenta, ou vazar uma resposta fora de escopo.
- **Um usuário por vez, por construção.** O protótipo roda o modelo na máquina de quem o
  demonstra, e a arquitetura assume isso: `@st.cache_resource` dá **uma** instância do agente
  por processo, o checkpointer abre **uma** conexão SQLite (`check_same_thread=False`) e o
  LM Studio atende um request por vez. Duas pessoas simultâneas disputam os três. O
  isolamento existente é por `thread_id`, não por sessão nem por usuário — não há noção de
  quem está falando. Dois processos escrevendo a mesma `thread_id` ao mesmo tempo intercalam
  turnos no histórico (visto na validação, mandando mensagem pela UI enquanto um script
  escrevia na mesma thread): não corrompe o checkpoint, mas a conversa sai fora de ordem. Multiusuário de verdade pede modelo servido à parte, pool de conexões
  e sessão autenticada; nada disso é difícil, mas nenhum deles cabia no hardware desta demo.
- **O histórico cresce sem TTL.** O `SqliteSaver` grava o estado inteiro a cada passo do
  grafo: depois das conversas de teste, o `emporio.db` estava com 95 MB e 1.905 checkpoints
  para 65 produtos e 20 pedidos. Num protótipo local é irrelevante; num deploy pediria
  expiração ou um store separado do catálogo.
- **Latência vs. o problema de volume.** Mediana de 32 s por caso e 177 s no pior, medidos em 87 execuções, sem *streaming* ([`eval_report.md`](eval_report.md)). Varia muito com o porte do modelo: os menores respondem em segundos e erram mais o *tool calling*.
- **Sem guard determinístico de escopo.** A recusa de assuntos fora da loja é só via prompt.
- **Verificação de identidade não é autenticação.** Exige o e-mail exato do cadastro (ver decisão 6), mas não há login, código de confirmação nem rate limit — e `order_id` é sequencial. Suficiente para protótipo, não para produção.
- **Busca de produto é lexical** (casa palavras no nome e nas specs, todas em E lógico).
  Dá para pesquisar por especificação — `tools._SPECS_PT` traduz o substantivo em PT-BR
  para a chave inglesa do JSON (`tampo`→`top`, `teclas`→`keys`), e número solto casa por
  palavra inteira para "7 cordas" não trazer o Yamaha C70. O teto é o dado: os VALORES
  misturam idioma no mesmo campo ("Mogno" no Kala, "Mahogany" na Gibson), então `mogno`
  não acha a Gibson. Cobrir isso pede busca semântica, não mais entradas na tabela.
  "Violão para iniciante" também não funciona: está só em `description`, que fica fora do
  match de propósito (ver o ruído nome × descrição abaixo).
- **`consultar_politica` é por palavra-chave.** Uma pergunta com vocabulário muito distante das palavras mapeadas pode não casar a seção certa.
- **Frete e parcelamento não são calculados** — o agente informa as regras da política, não simula valores para um CEP ou uma compra específica.
- **Preço por item de pedido não existe no dado.** `order_items.csv` só tem quantidade. O
  que a loja cobrou está apenas no total do pedido, e em 2 dos 20 pedidos ele não bate com a
  soma a preço de tabela (pedido 3: R$ 3.450 contra R$ 3.498; pedido 20: R$ 1.400 contra
  R$ 1.488) — houve desconto na venda que o dataset não registra. `status_pedido` avisa e o
  agente não recalcula item a item.
- **Ruído que sobrou no dataset sintético.** A contradição de marca entre nome e descrição é
  corrigida no ETL (ver §4), mas duas outras ficam: a descrição do produto 142 fala em
  "88 teclas" enquanto `specs` diz `keys: 61`, e 10 produtos continuam com nome de template
  (`Bass 1X`, `Kit 1 Studio`). Corrigi-las seria escolher arbitrariamente qual das duas
  colunas é a verdade. A regra do projeto é confiar nos campos **estruturados** (`name`,
  `price_brl`, `category_id`, `stock_quantity`, `status`) e tratar `description` como texto
  livre — nunca como fonte de fato.

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

1. **Leitura e entrevista (plan mode).** O Claude leu o enunciado, o manual de políticas e os 6 CSVs, mapeou as armadilhas dos dados, e então me entrevistou — **uma decisão de cada vez** — sobre as escolhas técnicas (abordagem do agente, acesso às políticas, camada de dados, data de referência, histórico, identificação, interface, modelo). Para cada uma ele apresentou opções com trade-offs e uma recomendação; **as decisões foram minhas**.
2. **O loop decisão → README.** Cada decisão fechada foi registrada na seção "Decisões técnicas" com a motivação, antes de virar código. Ajustes feitos depois (ex.: regras de prompt após ver falhas em conversas reais, ou o nome "melodIA") entram pelo mesmo loop: muda a decisão, muda a seção.
3. **Plano e execução por partes.** As decisões viraram um plano e um `CHECKLIST.md` em 8 partes. Cada parte: implementar → escrever o teste (`test_agent.py`, `assert` puro) → rodar → **um commit por parte** (histórico incremental, sem *force-push*, como o enunciado pede).
4. **Documentação viva.** `CLAUDE.md` (visão geral + decisões + armadilhas dos dados) e `CHECKLIST.md` foram mantidos atualizados ao longo do caminho.

O que **eu** decidi e revisei: a stack inteira (LangChain/LangGraph, LM Studio, `pymupdf4llm`, SQLite, Streamlit), todas as decisões técnicas, o nome do assistente, o recorte de cada parte e a redação final. O que o **Claude** fez: análise dos dados, primeira implementação de cada módulo, os testes, os rascunhos de documentação, e o *smoke test* que revelou os ajustes de prompt.
