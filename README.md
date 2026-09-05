# Empório da Música: Customer Service Agent

Prototype of **melodIA**, virtual customer service assistant for **Empório da Música**, a (fictional) musical instruments store in Campo Grande/MS, Brazil. Technical challenge for the AI Engineer position at Artefact.

The agent adopts the store's persona, responds via text message, and knows **when to query data** (catalog, orders, promotions) and **when to check store policies** (exchanges, hours, payment methods, shipping, warranty). Out-of-scope questions are politely declined.

> ### ⏱️ For the agent, today is **2026-03-25**
>
> The provided dataset is a *snapshot*: the 20 orders span from Oct/2025 to **2026-03-22**. Against the real-world clock, every order would be past every deadline (7-day remorse return window, 30-day defect exchange, 90-day warranty), and the prompt's reference query, *"I regret my purchase, can I return it?"*, would never yield a positive case. That is why the agent's "today" is an anchored reference date set right after the last order, rather than `date.today()`.
>
> This applies to everything you see here: the conversations in [`examples/`](examples/), the test cases in [`eval_report.md`](eval_report.md), and the test suite. It can be changed in a single environment variable (`DATA_REFERENCE_DATE` in `.env`) without touching code. **The complete rationale is in [Decision 5](#5-concept-of-today-configurable-data_reference_date).**

---

## What You Can Ask

- *"Which acoustic guitars are available under R$ 1,000?"* → searches the catalog, only in-stock items
- *"How much is the Takamine GD20?"* → list price + upfront PIX cash price
- *"What is the store's address and opening hours?"* → consults the policy manual
- *"I regret purchasing order 7, can I return it?"* → verifies customer identity, reads the policy, recognizes that the remorse return window starts upon **receipt/delivery** (data not present in the system), and asks the customer when they received the item before answering
- *"Which ukuleles under 500 reais?"* → the price range applies to the **effective** price: includes items at R$ 439.20 with active promotions, even with a list price of R$ 549.00
- *"Do you have solid spruce top guitars?"* or *"61-key keyboard"* → searches by **specification**, not by model name: built for musicians who know their specs
- *"Do you sell saxophones?"* → the store carries woodwinds/brass, but the category currently has no catalog items, and the agent states this directly instead of recommending unrelated gear
- *"Do you sell guitar strings?"* → explains that the store does not carry accessories
- *"Can you give me a cake recipe?"* → politely declines and steers back to the store context
- *"Do you have the Shelby SN-7C guitar?"* → discontinued item; the agent transparently explains that it is discontinued and suggests equivalent available alternatives (§7.3)
- *"I had a custom setup done on my guitar, can I exchange it?"* → declines the exchange because custom-setup or customized instruments are non-eligible items (§4.4)
- *"I want to pay R$ 500 via PIX and the remaining R$ 1,500 on card"* → declines the split because combining payment methods is only permitted for purchases over R$ 2,000 (§3.1)
- *"I live in Campo Grande and my purchase was exactly R$ 500, is shipping free?"* → informs that a flat shipping fee of R$ 35.00 applies, since free shipping requires strictly *above* R$ 500 (§5.1)

Five complete conversations are in [`examples/`](examples/), and an end-to-end evaluation covering 44 scenarios is in [`test_live.py`](test_live.py), with pass rate and latency per case reported in [`eval_report.md`](eval_report.md).

---

## How to Run

### Prerequisites

- **Python 3.11+**
- **[LM Studio](https://lmstudio.ai/)** with a model that meets three requirements: tool use / function calling support, decent Brazilian Portuguese, and a context window of **40k tokens or more** (up from an earlier 16k recommendation — the system prompt alone is ~3.5k tokens plus ~1.5-2k for the 7 tool schemas, a fixed ~5.5k cost per turn before any conversation history or tool output, on top of the `MAX_HISTORY_TOKENS=32000` default). The project does not depend on any specific model: `.env` allows swapping the model and endpoint without touching code, and was exercised across multiple model sizes throughout development. The model used for versioned evaluation is listed in the header of [`eval_report.md`](eval_report.md), which `test_live.py` automatically generates. Larger models handle tool calling more reliably and write better Portuguese at the expense of latency (see Decision 2). In LM Studio: max GPU offload recommended.

### Steps

```bash
# 1. Environment
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2. Local database from CSVs
python build_db.py                 # generates emporio.db

# 3. Configuration
cp .env.example .env               # adjust MODEL to the exact ID loaded in LM Studio
                                   # DATA_REFERENCE_DATE=2026-03-25 is pre-set:
                                   # this is the agent's "today" (see callout above)

# 4. LM Studio: load model and click "Start Server" (port 1234).
#    Recommended loading: max GPU offload + maximum context size

# 5. Run the interface
streamlit run app.py               # Chat UI  (http://localhost:8501)
# or in the terminal:
python agent.py                    # simple REPL
```

Environment variables (`.env`):

| Variable | Default | Description |
|---|---|---|
| `OPENAI_BASE_URL` | `http://localhost:1234/v1` | LM Studio endpoint (OpenAI-compatible API) |
| `OPENAI_API_KEY` | `lm-studio` | any non-empty string; LM Studio ignores it |
| `MODEL` | *(set yours)* | exact model ID loaded in LM Studio, as shown in the Developer tab |
| `DATA_REFERENCE_DATE` | `2026-03-25` | **agent's "today".** The dataset is a snapshot; without this, all orders expire; see [Decision 5](#5-concept-of-today-configurable-data_reference_date) |

### Testing

```bash
python test_agent.py             # 13 deterministic checks, no LLM (seconds)
python test_live.py              # 44 cases × 3 rounds against LM Studio (hours)
python test_live.py --rodadas 1  # 1 round only, for fast iteration
python test_live.py identidade   # only test cases matching "identidade"
```

- Both test suites use `DATA_REFERENCE_DATE=2026-03-25`: deadline assertions ("79 days ago", "7 days") only make sense relative to this anchor. `test_agent.py` validates this up front and fails with an explanatory message rather than throwing an ambiguous config error.
- **`test_agent.py`** covers non-trivial logic without invoking the model: ETL views (promotional pricing, non-cumulative PIX, availability, currency normalization, brand corrections), keyword routing across the 10 sections of `consultar_politica`, zero-loss curation of `policies.md`, data tools (incl. identity verification across the 20 orders), installment plan arithmetic, conversation history trimming, and graph compilation.
- **`test_live.py`** is the end-to-end agent evaluation: each scenario declares customer messages, expected tool call(s), and what the final answer must/must not contain (exact price, no fabricated promotions, no PII leaked on failed identity checks, no made-up policies, persona consistency, out-of-scope refusals, etc.). Because the agent is non-deterministic, **each test case runs 3 times** and is evaluated by pass rate (3/3, 2/3...); passing once does not differentiate skill from luck. Cases with known variance are flagged `flaky=True`: reported with real pass rates without failing the suite. Every run writes [`eval_report.md`](eval_report.md) with pass rate and latency per case.

---

## Architecture

```
       Streamlit (app.py)  ──or──  REPL (agent.py)
                     │
                     ▼
         ReAct Agent  (LangChain + LangGraph, create_react_agent)
           • system prompt = persona + guardrails  (prompts.py)
           • history persisted by thread_id (SqliteSaver → emporio.db)
                     │
         ┌────────────┴───────────────┐
         ▼                            ▼
    7 tools (tools.py)                    LM Studio (local model)
    ├─ buscar_produtos      ┐
    ├─ detalhe_produto      ├─→  emporio.db  (SQLite; views v_produto, v_pedido_item)
    ├─ status_pedido        │        ▲   build_db.py: 6 CSVs → SQLite
    ├─ identificar_cliente  │        │
    ├─ simular_pagamento    ┘        │
    ├─ calcular_frete       ──→ Zip code / dimensions (local calculation, standalone)
    └─ consultar_politica   ──→ policies.md   (convert_policies.py: PDF → policies_raw.md)
```

The model receives the 7 tools and decides on each turn whether to reply directly or invoke a tool. Data tools execute **parameterized SQL** (the LLM never writes raw SQL). The policy tool returns the relevant markdown sections from the store manual.

### Tools

| Tool | When the agent uses it | Return value |
|---|---|---|
| `buscar_produtos(termo, categoria, preco_min, preco_max, apenas_disponiveis)` | catalog lookups, filtering by category/price, stock status, **spec-based search** (`termo` matches instrument name AND specs: "tampo spruce", "61 teclas", "7 cordas") | list containing list price, promo price, and upfront PIX price. The price filter checks the **effective price** (promo price when active) |
| `detalhe_produto(nome_ou_id)` | price/specs/promo for **a single** instrument | complete product datasheet; disambiguates if name matches multiple items |
| `status_pedido(order_id, identificador)` | order progress & tracking | status, items, total amount, delivery estimate, tracking code, days **since purchase** (and a disclaimer that receipt date is not recorded), provided **only after identity verification** |
| `consultar_politica(topico)` | store hours, address, payment, returns/exchanges, shipping, warranty, LGPD, scope | relevant section(s) from `policies.md` |
| `identificar_cliente(email)` | recognize returning customers upon greeting (optional) | first name, city, order history presence; **does not** leak private order data |
| `simular_pagamento(preco_de_tabela, ja_esta_em_promocao, entrega_em_campo_grande, valor_no_pix)` | **arithmetic** over an amount: installment limits, monthly fee, PIX price, local shipping fee, split PIX + card over R$ 2,000 | structured simulation with tiers and PIX discount |
| `calcular_frete(cep, produto_ou_categoria, peso_kg, ...)` | national shipping calculation outside Campo Grande via postal code, weight, and dimensions (Policy 5.2) | quotes across 3 carriers (PAC, SEDEX, Jadlog) with deadlines, tracking, and insurance. Directs large items (acoustic drums, digital pianos, upright basses) to WhatsApp/email for manual quote |

A search takes **one single call**: `buscar_produtos` returns the full list (up to 20 items) in one roundtrip (20 results do not mean 20 tool calls). `detalhe_produto` operates on one instrument at a time because its purpose is disambiguating a specific name.

---

## Technical Decisions and Rationale

> The decisions below were flexible. The guiding criterion was: **the simplest solution that cleanly solves the problem for this dataset** (65 products, 20 orders, an 8-page policy manual), while keeping the upgrade path explicit.

| Technology | Role in Project | Motivation (detail) |
|---|---|---|
| **Python 3.11+** | Programming language | Only mandatory requirement of the technical challenge |
| **LangGraph** (`create_react_agent`, `SqliteSaver`) | ReAct agent loop + conversation checkpointing | Reasoning loop, tool binding, and battle-tested checkpoints (§1, §7) |
| **LangChain** (`langchain-core`, `langchain-openai`) | `@tool` decorator, message schemas, `ChatOpenAI` | `ChatOpenAI` is the model adapter expected by `create_react_agent`; with `base_url` it points straight to LM Studio (§1) |
| **LM Studio** | Serves local model via OpenAI-compatible API | Zero cost, 100% offline, customer PII never leaves the local machine, ensuring LGPD compliance (§2) |
| **Open Local Model** (any model supporting tool use; configured via `.env`) | Language model | Codebase is agnostic: `base_url` + `MODEL` configured in `.env`; differences between models impact tool calling accuracy and latency, not code (§2) |
| **SQLite** (`sqlite3`, stdlib) | Queryable catalog/orders + conversation checkpoints | Explicit modeling via views, clean joins, single file, zero dependencies (§4, §7) |
| **pandas** | CSV ETL (`read_csv` → `to_sql`) | 2 lines per CSV and automatic type inference on mixed int/decimal columns; only used in `build_db.py` (§4) |
| **pymupdf4llm** (+ `pymupdf`) | Policy PDF → Markdown | Reproducible, versioned conversion; only used in `convert_policies.py` at build time (§3) |
| **Streamlit** | Chat user interface | Interactive web chat in minimal code; editable `thread_id` to demonstrate persistence (§8) |
| **python-dotenv** | Environment configuration via `.env` | Keeps `MODEL`, `base_url`, and reference date out of code and git, following 12-factor style (§10) |
| **`assert` + `__main__`** | Test suite (`test_agent.py` without LLM, `test_live.py` against LM Studio) | Framework-free, zero test dependencies, runs everywhere (§11) |

<details id="1-agent-approach-react-with-langchain--langgraph">
<summary><b>1. Agent Approach: ReAct with LangChain + LangGraph</b></summary>

`create_react_agent` (from `langgraph.prebuilt`): an execution loop where the model alternates between reasoning and invoking tools until reaching a final answer. The model communicates with LM Studio via `ChatOpenAI(base_url=...)`. Tools are standard Python functions decorated with `@tool` (`langchain-core`).

- **Why not pure RAG:** Core query targets (pricing, inventory, order status) are structured and dynamic, requiring function calling against a database rather than unstructured text retrieval.
- **Why not a Text-to-SQL agent:** Letting a local model generate raw SQL is fragile and risky. Fixed, parameterized tools provide the exact same capabilities with significantly less vulnerability.
- **Why not a single "answer" function:** The strength of this challenge lies in having the agent *decide* between structured data and policy text, a pattern natively handled by ReAct with rich tool descriptions.
- **Why use prebuilt `create_react_agent` instead of assembling the graph manually:** The ReAct loop, tool binding, and conversation checkpointer come pre-tested in LangGraph.

</details>

<details id="2-model-and-provider-lm-studio-local-model">
<summary><b>2. Model and Provider: LM Studio (Local Model)</b></summary>

- **Zero cost and offline:** No API keys, no quotas, no billing.
- **Data privacy:** The store policy manual explicitly references Brazil's LGPD privacy law. Customer support processes names, emails, and order history. Running the model locally prevents leaking sensitive customer PII to third-party APIs. A genuine compliance argument, not merely a cost consideration.
- **Known trade-off:** Tool calling in small open models is less reliable than in frontier models. Mitigations: only 7 tools, detailed docstrings, `temperature=0`, and a compact system prompt. The codebase is model-agnostic (`base_url` + `MODEL` in `.env`), so switching to a cloud API only requires changing two environment variables.
- **Model selection:** The primary axis is tool-calling reliability vs. inference latency. Smaller models respond in seconds but make occasional tool errors. These edge cases observed in real testing were codified into explicit prompt rules. Larger models make fewer tool errors at the expense of latency. [`eval_report.md`](eval_report.md) records which model produced each benchmark result, with pass rate and latency per case, enabling comparisons grounded in data rather than impression. Frontier models via API would solve latency and reliability simultaneously, at the cost of transmitting PII externally.
- **The operational tension:** The core business problem stated in the challenge is *inquiry volume*: "the team is overwhelmed by repetitive questions". The numbers are measured, not guessed ([`eval_report.md`](eval_report.md), 87 runs): **median of 32s per case**, peaking at 177s in the worst-case scenario (`conversa_longa_nao_perde_a_ferramenta`, seven turns with tool calls in almost all). These apply to the model evaluated in that report; switching models shifts both numbers, which is why the versioned report records the exact model used. Without streaming or queues, this **demonstrates** the agent's logic, but does not address volume on a single local GPU: an agent waiting half a minute per response is not alleviating support bottlenecks. This prototype optimizes for cost, privacy, and offline reproducibility; a production deployment addressing real volume would use a batched serving layer (or API), streaming responses, and an asynchronous queue. The agent here is the component validated first; the serving layer is the next step, not an afterthought.

</details>

<details id="3-store-policies-conversion-via-pymupdf4llm--section-retrieval-tool-without-embeddings">
<summary><b>3. Store Policies: Conversion via <code>pymupdf4llm</code> + Section Retrieval Tool (Without Embeddings)</b></summary>

`convert_policies.py` uses `pymupdf4llm` to extract the policy PDF into `policies_raw.md` (reproducible, versioned). This output underwent light curation into `policies.md` (cleaned headings without `**bold**`, removed running headers/footers, normalized tables). The tool `consultar_politica` scores the 10 sections using keywords and titles, returning the most relevant segments.

- **Why not RAG with a vector store:** The manual has ~4,000 tokens across 10 well-defined sections. A vector database would introduce extra infrastructure, latency, and failure points to solve a problem that a keyword table resolves **deterministically** and explainably. Semantic vector search is only justified over massive document volumes.
- **Why not inject the entire manual into the system prompt:** It would consume ~4k context tokens on every turn (the context window of a local model is smaller, and on a frontier model it is 4k tokens wasted per turn), besides polluting reasoning with irrelevant rules.

#### Maintainability Criteria: Division of Responsibilities
To balance latency, mathematical precision, and operational maintainability:
1. **In System Prompt (Section 1):** Only permanent corporate registry data and identity (Corporate Name, CNPJ, founded in 2008, mission, and strict catalog boundary excluding accessories). Answers corporate inquiries without tool calling overhead.
2. **Via Policy Tool (`consultar_politica`, Section 2 onwards):** Descriptive and dynamic operating rules (business hours, weekend/holiday hours, seasonal extensions such as Black Friday/Christmas, return/exchange terms, shipping terms, warranty terms). Textual updates are made directly in `policies.md` without touching agent code. For returns/exchanges (Section 4), the agent cross-references policy guidelines with `status_pedido` data (distinguishing receipt date vs. purchase date and barring ineligible items such as mouthpieces, custom setups, and final sale items).
3. **Via Deterministic Arithmetic Tool (`simular_pagamento`, Sections 3 & 5.1):** Exact mathematical computations (5% PIX discount, installment brackets up to 3x/50, 4-6x/80, 7-12x/100, and split payment threshold over R$ 2,000). Eliminates LLM math hallucinations; automated tests in `test_simular_pagamento` ensure in-code constants strictly match the manual's wording.
4. **Promotion Governance (Section 6):** Three-layer integrity: the database (`v_produto`) applies only the highest active discount without stacking the 5% PIX discount (§6.2); `consultar_politica` details seasonal campaigns and forbids rain checks (price holds on out-of-stock gear); and the prompt strictly prohibits the agent from calling the permanent PIX discount a "promotion" or inventing coupon codes.
5. **Customer Support Channels (Section 7):** The store maintains two active WhatsApp lines: (67) 3341-4444 (also serving as the landline) and (67) 3321-4500 (remote support). For complaints (§7.3), the prompt enforces empathetic listening with a management SLA of up to 24 business hours; for discontinued products, it instructs transparent communication and equivalent available recommendations.
6. **Statutory vs. Manufacturer Warranty (Section 8):** Clear distinction of terms: in-store defect exchanges are valid for up to 30 days from purchase (§4.2); thereafter, the 90-day statutory warranty from receipt applies (§8.1), followed by manufacturer coverage (6 months to 2 years, §8.2). Exclusions such as natural wear (frets, strings, felt pads, reeds) and cosmetic damage are dynamically backed by policy text.
7. **Data Privacy & Protection (Section 9):** LGPD compliance (Brazilian General Data Protection Law, Law No. 13,709/2018) in infrastructure and behavior: local model (LM Studio) without external data transmission; order data protected by strict email verification; and `consultar_politica` covering data deletion rights and processing purposes.
8. **Final Provisions and Omitted Cases (Section 10):** Guardrail against rule hallucinations: if a customer query is not explicitly covered in the manual, the agent is prohibited from inventing plausible compromises (fines, compensations, custom deadlines) and instructed to honestly state that it will check with management.

</details>

<details id="4-data-processing-etl-to-sqlite-with-views">
<summary><b>4. Data Processing: ETL to SQLite with Views</b></summary>

`build_db.py` ingests the 6 CSV files into `emporio.db` with normalized data types and creates two views encapsulating core business rules:

- **`v_produto`**: joins category details, computes the **highest active promotion** per product (`promotions.csv` has multi-row entries per product; Policy 6.2 states promotions do not stack), and calculates:
  - `preco_promocional` (when an active promo exists);
  - `preco_a_vista_pix`: 5% off list price, **except** when a promotional price is already active (Policy 6.2);
  - `disponivel` = `status = 'active'` AND `stock_quantity > 0`.
- **`v_pedido_item`**: order line items mapped to product names and prices.

**Why pandas in the ETL:** `pd.read_csv(...).to_sql(...)` handles ingestion in two lines per file and infers types across mixed int/decimal columns (`products.price_brl` contains 53 integers and 12 decimals; `orders.total_brl` similarly). Normalization to 2 decimal places is an **explicit** transformation step in `build_db.py`, because silent inference is fine until the day it breaks. This is the only dependency used by `build_db.py`; stdlib `csv` + manual `INSERT` would be more code for the exact same result.

#### Data Traps

The synthetic dataset contains subtle edge cases that do not trigger database errors, but cause silent incorrect responses if handled naively:

| Data Trap | Where it appears | Handling in Code |
|---|---|---|
| Out-of-order records | `products.csv`: IDs 81-130, then 145, then 131-144 | Always sort by price / `product_id`, never trust file line order |
| `status = 'active'` ≠ in stock | Product 96 (Giannini GF-3D) has status `active` with stock 0 | `disponivel = active AND stock > 0` → 61 of 65 available. This trap originally made the agent claim an out-of-stock item "does not exist in the catalog" |
| Duplicate promotions | `promotions.csv` has 25 rows, only 4 active, with repeated product IDs | The view aggregates `MAX(discount_percent)` among active records (§6.2: non-cumulative) |
| Missing actual delivery date | `orders.csv` records expected delivery, not actual receipt | `status_pedido` declares this constraint, prompting the agent to ask the customer (see Decision 5) |
| Missing unit price on order items | `order_items.csv` only records quantity | `status_pedido` reports total order amount and flags discrepancies against list price sums |
| Name vs. description brand mismatch | 6 products (detailed below) | Corrected in ETL at build time |

#### Declared Brand Correction

10 products (IDs 135-144) feature template names (e.g., `Music Man Bass 1X Electric Bass`, `Bateria Acústica Yamaha Kit 1 Studio`, `Teclado Sintetizador Korg Synth 1 Pro`), and in **6** of them, the description text references a **different** brand than the title. This is not a typo: the generator generated titles and descriptions in separate unlinked passes.

| Product ID | Title Brand | Description Referenced |
|---|---|---|
| 135 | Music Man | Fender Jazz Bass |
| 137 | Yamaha | Ibanez |
| 139 | Yamaha | Pearl Export |
| 140 | Pearl | Tama |
| 142 | Korg | Roland |
| 144 | Roland | Yamaha |

Leaving this as-is causes the agent to read descriptions and pitch a brand the store does not sell under that SKU. Therefore, `build_db.py` **fixes description brands during ETL**, via a strict rule (explicit brand list + whole-word matching), backed by an `assert` that exactly 6 rows are modified, ensuring the build fails if upstream data changes rather than silently altering the catalog.

Two boundaries are intentionally maintained: **raw files in `data/` are never touched** (corrections live strictly in the ETL DataFrame pipeline), and only the **brand token** is replaced; foreign model designations ("Jazz Bass", "Export") remain, as rewriting them would invent ungrounded data.

**Why SQLite over in-memory DataFrames:** SQLite makes domain modeling explicit (tables + views document business logic), offers clean joins and aggregations, and shares the same database file used for conversation persistence. The LLM never generates SQL; tools run fixed queries with bound parameters.

</details>

<details id="5-concept-of-today-configurable-data_reference_date">
<summary><b>5. Concept of "Today": Configurable <code>DATA_REFERENCE_DATE</code></b></summary>

All 20 orders in the dataset date from October 2025 to March 2026. Against the real-world calendar, **every order would be past all policy deadlines** (7 days remorse, 30 days defect), rendering the benchmark query ("I regret my purchase, can I return it?") permanently negative.

Because the dataset is a frozen snapshot, the agent anchors "today" to a configurable reference date (default `2026-03-25`, immediately following the latest order). The tool `status_pedido` returns precalculated day deltas, allowing the agent to compare against the deadlines defined in **store policy text** without hardcoded dates.

**Which clock to use (refined after re-reading policy):** The reference date solves one part of the problem. The second part is *from when* each deadline is calculated. Policy §4.1 specifies 7 calendar days **from product receipt**; §4.2 specifies 30 days **from purchase**. The database only records purchase dates: order data contains estimated delivery, but **no actual delivery date**. Evaluating the 7-day remorse window against purchase date mismeasures the policy rule.

Now, `status_pedido` clearly labels the counter as "N days **since purchase**" and explicitly informs the agent that receipt date is unrecorded; the prompt instructs the agent to check the baseline date and **ask the customer when they received the product**. Positive side effect: on `2026-03-25`, no order was purchased within the last 7 days; asking for the receipt date makes positive return scenarios possible (captured in test case `devolucao_recebido_dentro_do_prazo`).

**Why not `date.today()` as default:** Falling back to the system clock when the environment variable is missing would silently turn every return inquiry into "past deadline" on any machine where `.env` was omitted. A fixed default fails predictably; a dynamic clock fails invisibly.

</details>

<details id="6-identity-verification-lgpd--privacy-conscious">
<summary><b>6. Identity Verification: LGPD / Privacy Conscious</b></summary>

Customer orders expose PII (name, email, items, purchase price, delivery estimate, tracking code). `status_pedido` only releases data upon validating **order number + exact registered email** (`_identidade_confere` in `tools.py`, normalizing case and accents). Names are not accepted, not even the customer's full legal name.

**Evolution of the check:** The initial version checked name substrings (100% bypassable blindly); the second split name tokens (~70% bypassable). The third required first name + two distinct tokens with whole-word matching, which resisted common name spraying but still allowed collisions across 3 customer pairs where one name was a subset of another. Switching to exact email matching eliminated all heuristics: verification became a clean string comparison with zero regression surface.

**The deliberate trade-off:** More secure, slightly more demanding. Customers providing only their name are declined and asked for their registered purchase email, following standard e-commerce practice. `test_identidade_nao_burlavel` iterates across all 20 orders: valid email unlocks, name alone is rejected, and an email with a single modified character is blocked.

</details>

<details id="7-conversation-history-langgraph-sqlite-checkpointer--context-trimming">
<summary><b>7. Conversation History: LangGraph SQLite Checkpointer & Context Trimming</b></summary>

`SqliteSaver` operates over the same `emporio.db`, indexed by `thread_id`. Conversations survive application restarts: reopening with the same `thread_id` (editable in Streamlit sidebar) restores the entire session.

**History trimming (`agent._podar`).** Persisting all history and *resending* all history are distinct concerns. Without trimming, `create_react_agent` resends the full conversation transcript on every turn; since `consultar_politica` can return up to 3 sections (~1,200 tokens), 10-15 turns will exceed local model context windows, quietly degrading answers before crashing. A `pre_model_hook` leveraging `trim_messages` (`langchain-core`) caps the payload sent to the LLM to the latest `MAX_HISTORY_TOKENS` (default 32,000, configurable in `.env`). The persisted SQLite history remains intact.

The critical requirement for trimming is `start_on="human"`: slicing mid-turn across a tool call would leave an orphaned `ToolMessage` missing its preceding `AIMessage(tool_calls=...)`, causing the OpenAI API to reject the request. `test_poda_historico` generates 240 synthetic messages, validating both token trimming and zero orphaned tool messages. Test scenario `conversa_longa_nao_perde_a_ferramenta` verifies this end-to-end, and [`validacao_conversa_longa.md`](validacao_conversa_longa.md) documents validation against the live model: 42 conversation turns before trimming triggered, plus deep truncation tests (22 of 36 messages pruned) with zero API rejections and accurate tool execution.

**When trimming begins depends on model verbosity.** In a 28-turn validation via Streamlit with a verbose model, history expanded at ~340 tokens per turn: reaching 5,100 tokens at turn 15 and 9,600 tokens at turn 28 across 94 messages with 14 tool invocations. Under that pace, an 8,000 ceiling begins trimming around turn 23. Testing `_podar` against live transcripts with tighter ceilings (4,000 and 1,000) reduced message counts from 71 to 35 and 11 messages respectively, strictly under the ceiling and **without orphaned tool messages**. Lesson learned: turn capacity is a property of the model's verbosity, making configurable ceilings and orphan validation essential.

</details>

<details id="8-user-interface-streamlit">
<summary><b>8. User Interface: Streamlit</b></summary>

A functional web chat built in minimal code, suitable for demonstrations and recording test dialogues. The `thread_id` can be adjusted in the sidebar to prove session persistence. A terminal REPL (`python agent.py`) is also included for fast command-line testing.

</details>

<details id="9-persona-and-prompt-melodia">
<summary><b>9. Persona and Prompt: "melodIA"</b></summary>

The assistant persona is named **melodIA** (*melodia* [melody] + *IA* [AI]). Friendly and welcoming, designed to make shoppers comfortable.

The system prompt (`prompts.py`) enforces strict **guardrails**: never guess price/stock/deadlines without tool confirmation (Policy 7.1, "accurate information"), always present original price + discount % + final price on promotions, suggest alternatives for out-of-stock items, present lists item-by-item, never correct details provided by customers, never invent uncataloged brands, and refuse off-topic inquiries (backed by concrete refusal few-shots to guide smaller models).

**Policy grounding (mitigated, not fully eliminated):** The prompt instructs the agent to assert *only* what appears in text returned by `consultar_politica`, and state "I will check with the team" whenever policy text does not cover the question. This addressed an observed failure where a model hallucinated "late delivery compensation" absent from the manual.

Policy rule principle: Lives strictly in policy text, never hardcoded in code or prompts.

</details>

<details id="10-configuration-env-via-python-dotenv">
<summary><b>10. Configuration: <code>.env</code> via <code>python-dotenv</code></b></summary>

`config.py` loads environment variables: `OPENAI_BASE_URL`, `MODEL`, `DATA_REFERENCE_DATE`. Keeps configuration out of git repositories and decoupled from code, maintaining full model and provider agnosticism.

</details>

<details id="11-testing-assert--__main__-zero-framework-overhead">
<summary><b>11. Testing: <code>assert</code> + <code>__main__</code>, Zero Framework Overhead</b></summary>

Two test tiers, both relying on native `assert` and standard `main()` blocks without pytest:

- **`test_agent.py`** (13 test functions, no LLM): deterministic logic covering ETL views and brand corrections, keyword routing for the 10 policy sections (including Section 4.4 exceptions like mouthpieces and custom setups), data tools, national shipping calculator (`calcular_frete`), identity validation across all 20 orders, installment arithmetic in `simular_pagamento` (including constant validation against manual text), and context window trimming. Includes `test_policies_sem_perda`, verifying that policy curation only changed formatting: every number, value, and email address from `policies_raw.md` is preserved. Runs in seconds on any environment.
- **`test_live.py`** (44 test cases × k rounds against LM Studio): end-to-end evaluation where each scenario asserts customer dialogue turns, expected tool invocations, and mandatory/forbidden response substrings. Covers discontinued vs. out-of-stock items (§7.3), customized items ineligible for return (§4.4), refusal of split payments under R$ 2,000 (§3.1), Campo Grande free shipping threshold at exactly R$ 500 (§5.1), resistance to prompt injections demanding full customer email dumps, and the 90-day statutory warranty (§8.1) calculated from receipt rather than purchase. Generates [`eval_report.md`](eval_report.md) with pass rates and latencies (median and worst-case) per scenario.

</details>

<details id="12-customer-identification-invitation-not-a-gate">
<summary><b>12. Customer Identification: Invitation, Not a Gate</b></summary>

The store policy manual (§7.2) describes standard support protocol beginning with *"greet the customer by name, **if available**"*. `identificar_cliente(email)` fulfills this: returning first name, city, and purchase history existence.

- **Why invite rather than mandate:** The alternative would gate the conversation until an email is provided. That would force PII collection just to answer *"what time do you open?"*, violating LGPD purpose limitation (§9) and losing shoppers who only wanted a price check. The agent invites the email upon greeting and continues seamlessly if none is provided; eval case `identificacao_nao_bloqueia_atendimento` explicitly forbids tool calling on simple hours inquiries.
- **Three user states, not two:** "New customer vs. returning customer" misses dataset realities: out of 50 customers, **32 have registered accounts with zero purchases**. They represent the largest cohort and deserve distinct handling: greeting them by name without fabricating non-existent purchase histories.
- **Enabled integrations:** City data feeds shipping calculations (24 of 50 customers reside in Campo Grande where shipping is immediately computable), and in-transit orders prompt proactive delivery tracking offers.
- **Clear security boundary:** Identification is not authentication. The tool may reference the *order ID* of an in-transit order, but reveals **no order contents**: items, totals, and tracking codes remain exclusive to `status_pedido`, which requires order ID + matching email.

</details>

<details id="13-installment-and-shipping-the-only-policy-rules-implemented-in-code">
<summary><b>13. Installment and Shipping: The Only Policy Rules Implemented in Code</b></summary>

`simular_pagamento` computes installment capacity, per-installment values, PIX cash pricing, and local metropolitan shipping. This departs from project conventions (policy rules belong in text, not code) for a deliberate reason: **it is arithmetic, and arithmetic is where local LLMs hallucinate**. "R$ 549 in 12x" produces installments of R$ 45.75 (below the R$ 100 tier floor), yet the agent previously agreed when calculating mentally from §3.1 text. The true maximum is 6x of R$ 91.50.

To prevent this departure from becoming technical debt, it is guarded by two constraints:
1. All figures reside in a **single configuration table** at the top of the module with manual paragraph annotations (`_PIX_DESCONTO`, `_FAIXAS_PARCELAMENTO`, `_FRETE_CG`). `_FAIXAS_PARCELAMENTO` implements **§3.1** (specific rule), rather than the summary table in §3 (which states a flat "minimum installment of R$ 100.00"). The two only align between 7x and 12x; this divergence is documented in the header of `policies.md`.
2. `test_simular_pagamento` asserts **every constant against the text of `policies.md`**. If the manual changes without code updates, the test suite fails immediately naming the conflicting constant.

The four rules of §3.1 are implemented in code, including split payments: for purchases above R$ 2,000.00, the simulation supports paying partly via PIX and partly via credit card, calculating both legs: the 5% discount applies **only** to the PIX portion, and installment calculations are reapplied to the card balance.

Shipping is handled at two levels with dedicated tools:
- **Campo Grande Metropolitan Area (§5.1):** calculated within `simular_pagamento` (free above R$ 500, flat fee of R$ 35 otherwise), delivered via internal courier in 1-3 business days.
- **Other Cities / National Shipping (§5.2):** calculated via dedicated tool `calcular_frete(cep, produto_ou_categoria, ...)`. Because the product catalog (`products.csv`) lacks physical dimensions and weights, the system uses **standardized parcel categories** (aligned with musical instrument e-commerce benchmarks):
  * **Acoustic Guitar:** 105 × 45 × 15 cm | 3.5 kg (volumetric: 11.8 kg)
  * **Electric Guitar:** 105 × 40 × 12 cm | 4.5 kg (volumetric: 8.4 kg)
  * **Keyboard / Synthesizer:** 105 × 40 × 15 cm | 6.0 kg (volumetric: 10.5 kg)
  * **Ukulele:** 60 × 25 × 12 cm | 1.0 kg (volumetric: 3.0 kg)
  * **Wind / Brass Instruments:** 60 × 25 × 18 cm | 2.5 kg (volumetric: 4.5 kg)
  * **Orchestral Strings:** 80 × 30 × 15 cm | 2.5 kg (volumetric: 6.0 kg)
  * **General Standard:** 90 × 35 × 15 cm | 3.0 kg (volumetric: 7.9 kg)

  Volumetric weight follows the postal formula `(L × W × H) / 6000`, billing whichever is greater between dead weight and dimensional weight. The tool automatically resolves catalog categories when customers provide only model names (e.g. "Yamaha C40"), applies regional distance multipliers from MS origin (Southeast 1.15, South 1.20, Northeast 1.40, North 1.60, Midwest 1.00), and outputs 3 shipping quotes: PAC (5-12 days), SEDEX (2-5 days), and Jadlog (3-8 days), all including declared insurance. For oversized gear (acoustic drum kits, digital pianos, upright basses), automatic calculation is blocked, directing customers to human support via WhatsApp/email.

Policy §5.1 leaves two edge cases open, both documented as assumptions in `policies.md` and enforced in `test_simular_pagamento`:
- **Exactly R$ 500.00 pays shipping.** The text states "free *above* R$ 500.00" and "*below* R$ 500.00, flat fee". The exact figure is resolved via strict literal reading of "above" (`>`).
- **Free shipping applies to PAID subtotal, after discounts**, not the list price. In a R$ 520 purchase, credit card qualifies for free shipping (total R$ 520.00), but a 5% PIX discount reduces the subtotal to R$ 494.00, reintroducing the R$ 35 fee (total R$ 529.00), meaning **card is cheaper than PIX**. When payment methods fall on opposite sides of the threshold, `simular_pagamento` returns both comparisons; the prompt instructs presenting both options rather than choosing for the customer.

The final provision of §5.2 (oversized instruments may require custom freight quotes) is surfaced via the catalog: `buscar_produtos` **and** `detalhe_produto` flag oversized items and advise the customer upfront. Flagging is based on **product title**, not category: the "Basses" category only contains electric basses (guitar-sized) and "Keyboards" only contains synths. Currently, this matches the 3 acoustic drum sets; digital pianos and upright basses are prepped for future catalog additions.

---

</details>

---

## Known Limitations

- **Tool calling reliability depends on local model capacity.** Weaker models may answer price/inventory without calling tools or fail to refuse out-of-scope queries.
- **Single concurrent user by design.** The prototype runs locally: `@st.cache_resource` instantiates **one** agent per process, the checkpointer opens **one** SQLite connection (`check_same_thread=False`), and LM Studio processes requests sequentially. Multi-user concurrency would require a dedicated serving backend, connection pools, and authenticated sessions.
- **Unbounded history growth without TTL.** `SqliteSaver` captures full state on every step: after comprehensive testing, `emporio.db` reached 95 MB and 1,905 checkpoints for 65 products and 20 orders. In production, this requires expiration policies or a separate store.
- **Inference latency vs. inquiry volume.** Median latency of 32s per case, up to 177s worst-case, across 87 non-streamed test runs ([`eval_report.md`](eval_report.md)). Smaller models respond in seconds but compromise tool accuracy.
- **Agent has no clock awareness.** Context injects the reference *date*, never the *time*. Policy §7.1 requests stating reopening hours when contacted after hours: the agent can state operating hours (§2), but does not know if the store is currently open.
- **Complaints are not stored.** Policy §7.3 specifies "listen with empathy, register, and forward to management". The agent listens and forwards, but persists nothing: database access is read-only and no ticketing table exists. The 24-business-hour SLA is communicated accurately.
- **No tool to prepare or submit return orders.** While the agent verifies remorse eligibility and policies, there is currently no write tool (`preparar_devolucao`) to register or initiate returns in the system. The agent must guide customers to support channels rather than promising direct system execution.
- **No deterministic scope guardrail.** Out-of-scope refusal relies entirely on prompt instructions.
- **Identity verification is not full authentication.** Enforces exact registered email matching, but lacks login tokens, OTP verification, and rate limiting. Adequate for a prototype, not production.
- **Product search is lexical** (logical AND keyword matching across title and specs). While `tools._SPECS_PT` maps Portuguese terms to English JSON keys (`tampo`→`top`, `teclas`→`keys`), catalog values mix languages ("Mogno" on Kala, "Mahogany" on Gibson). Semantic vector search would be required to unify multilingual values and match broad queries like "beginner guitar".
- **Policy retrieval is keyword-based.** Queries with phrasing distant from indexed keywords may miss target sections. When vocabulary is inherently ambiguous ("arrived damaged"), the tool returns both §5.2 (transit damage) and §4.2 (manufacturing defect), and the prompt instructs the agent to ask clarifying questions.
- **Category-estimated shipping dimensions and weights.** Because `products.csv` lacks packaging dimensions, parcel profiles are estimated by category (see §13). Opening damage claims is outside the prototype's scope.
- **Missing unit prices on order items.** `order_items.csv` only records quantities. Two orders feature sales discounts not reflected in list price sums (Order 3: R$ 3,450 vs. R$ 3,498; Order 20: R$ 1,400 vs. R$ 1,488). `status_pedido` flags discrepancies without guessing individual item discounts.
- **Remaining synthetic dataset noise.** Brand contradictions between title and description are fixed in ETL (see §4), but minor quirks remain: Product 142 description mentions "88 keys" while `specs` states `keys: 61`, and 10 products retain template names (`Bass 1X`, `Kit 1 Studio`). The project rule is to trust **structured fields** (`name`, `price_brl`, `category_id`, `stock_quantity`, `status`) and treat `description` as unstructured text rather than ground truth.

---

## Future Improvements

- **LLM-as-a-judge** for qualitative dimensions that regex/substring matching cannot capture (tone, completeness, cordiality).
- **Automated CI evaluation** using a lightweight served model instead of local LM Studio dependency.
- **Deterministic output guard** for policy grounding: discard and regenerate responses containing terms or deadlines absent from the tool output.
- **Deterministic input guard** for prompt injections and out-of-scope topics.
- **Semantic RAG** for policies if document volume expands.
- **Real user authentication** for order lookups (SMS/Email/WhatsApp OTP).
- **Semantic product search** (catalog embeddings) to support natural language queries.
- **Token streaming** in the UI.
- **Tool for preparing return requests (`preparar_devolucao`)** to formalize return flows in backend.
- **Automatic text-ReAct fallback** when native tool calling fails.

---

## Use of AI Coding Assistants

The entire project was built pair-programming with **Claude Code** (Claude Sonnet for construction and Claude Opus for technical review and corrective refactoring), following this workflow:

1. **Analysis and interview (plan mode):** Claude reviewed the requirements, policy manual, and 6 CSVs, mapped dataset traps, and interviewed me, **one decision at a time**, regarding technical architecture (agent pattern, policy access, data layer, reference date, history persistence, identification, interface, model selection). Options, trade-offs, and recommendations were presented; **all final decisions were mine**.
2. **Decision-to-README loop:** Each concluded decision was documented in the "Technical Decisions" section with rationale before writing code. Subsequent refinements (e.g. prompt adjustments from live runs or the "melodIA" name) followed the same documentation-first loop.
3. **Phased execution plan:** Decisions were translated into an 8-phase `CHECKLIST.md`. Each phase followed: implement → write tests (`test_agent.py`, pure `assert`) → execute tests → **one commit per phase** (clean incremental git history, without force-pushing).
4. **Living documentation:** `CLAUDE.md` (project overview + decisions + data traps) and `CHECKLIST.md` were continuously maintained.

What **I** decided and reviewed: the entire technology stack (LangChain/LangGraph, LM Studio, `pymupdf4llm`, SQLite, Streamlit), all architectural decisions, assistant persona and naming, scope boundaries, and final text. What **Claude** executed: data profiling, initial module scaffolding, test implementations, documentation drafts, and smoke testing that highlighted prompt edge cases.
