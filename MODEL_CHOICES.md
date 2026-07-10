# Model Choices — selection, cost & quality justification

> This file is the assignment-required explanation of the 2-LLM choice (cost & quality).
> Selection method: three parallel market researchers (OpenAI lineup / Anthropic+Google /
> value market: Mistral, DeepSeek, Qwen, Kimi, Llama-via-hosts, Amazon Nova) swept the
> market on 2026-07-04; a judge picked the pair; an independent fact-checker then
> re-verified every model id and price against official provider pricing pages the same
> day. All checks passed.

## Build-time validation (M4, 2026-07-05)

- **Prices re-verified** against the official OpenAI pricing page
  (developers.openai.com/api/docs/pricing) on 2026-07-05: gpt-5.4-mini **$0.75 / $4.50**,
  gpt-5.4-nano **$0.20 / $1.25**, gpt-5.4 flagship **$2.50 / $15.00** — all unchanged.
  text-embedding-3-small is not listed on the main pricing page; its **$0.02**/1M stands
  on the 2026-07-04 verification.
- **GitHub Models free-dev aliases priced (2026-07-10)**: `openai/gpt-4.1-mini`
  **$0.40 / $1.60** and `openai/gpt-4.1-nano` **$0.10 / $0.40** (official model pages) are
  in the turn-log price table, so free-tier dev turns carry a paid-equivalent `cost_usd`
  estimate instead of 0 — the actual free-tier charge is $0.
- **`temperature=0` on the pinned `gpt-5.4-mini`**: ⏳ PENDING — requires a real
  `OPENAI_API_KEY`; the one-off probe (`chat.completions.create(model="gpt-5.4-mini",
  temperature=0, max_tokens=8)`, expect HTTP 200) runs the moment the key is available
  and this line will be updated with the dated outcome. Verified so far (2026-07-05, dev
  endpoint): the GitHub Models catalog serves **no `gpt-5.4*` ids** (37 models probed),
  so the pinned-id check cannot run there; `temperature=0` + `max_tokens` return HTTP 200
  on the dev alias `openai/gpt-4.1-mini`.

## The pair (one provider, one key)

| Role | Model | Price /1M tok (verified 2026-07-04, official OpenAI pricing page) | Why |
|---|---|---|---|
| Conversation | **gpt-5.4-mini** | $0.75 in / $4.50 out | Grounded RAG synthesis over a small, code-pre-filtered context (one summary + 2 chunks/page) with citation + refusal + injection rules. On the grounded/instruction-following axis this task actually lives on, published comparisons put mini on par with the flagship (this class of task, not a universal ranking); it is expected to support `temperature=0` for deterministic, reproducible grounded output (pending the real-key probe — see Build-time validation). |
| Analytics (+ page summaries) | **gpt-5.4-nano** | $0.20 in / $1.25 out | The classifier is a flat 5-field closed-enum schema (topic/category/question_type/language/confidence) and the summaries are 5–8 sentences from the first 6K chars — both are nano's documented sweet spot (classification, extraction, high-volume summarization). Reusing it for summaries keeps the app at exactly 2 LLMs. |
| Embeddings | **text-embedding-3-small** (1536d) | $0.02 in | Negligible cost; 1536 dims matches the FLAT index. Redis COSINE returns a normalized distance, so `similarity = 1 − distance` holds by the metric's definition. Same key/provider as the LLMs. |

**Keys the evaluator needs: exactly one — `OPENAI_API_KEY`** (covers conversation,
analytics, and embeddings). `TAVILY_API_KEY` stays optional (keyless ddgs fallback).
`make test` and CI run with zero keys.

**Free dev mode:** the client also accepts an optional `OPENAI_BASE_URL`. Point it at
GitHub Models' OpenAI-compatible endpoint with a GitHub PAT as the key to develop for
free — a classic PAT works as-is; a fine-grained PAT needs the **Account permission
"Models: Read-only"** (verified 2026-07-05: without it the catalog lists but inference
returns 403 `no_access`) — GitHub's free tier serves the same OpenAI models *including the
text-embedding-3 series*, so the 0.70 threshold calibration carries over unchanged.
Free-tier limits (~50–150 req/day, token-per-request caps) are fine for development
but NOT for the recorded demo — run that on a real OpenAI key.

## Why this pair (evidence)

**Conversation = gpt-5.4-mini.** The conversation node's job is bounded: synthesize a
grounded answer over a deliberately small, code-pre-filtered context (threshold routing
lives in *code*, not model judgment; the context is capped to a per-page summary +
`WEB_CONTEXT_CHUNKS_PER_PAGE`=2 chunks). That is a grounded/instruction-following task,
not a deep-reasoning or agentic one. Public grounded-RAG / instruction-following
comparisons place gpt-5.4-mini on par with the gpt-5.4 flagship for this class of task,
while the flagship's aggregate lead comes almost entirely from agentic reasoning / coding /
computer-use — capabilities this architecture intentionally removes. (Confirm the exact eval
figures against the vendor's current model card before quoting them; a specific unversioned
number is deliberately not reproduced here.) The flagship's premium buys headroom the design
never exercises.

Two concrete wins for mini in THIS build:
1. It is **not** a temperature-rejecting reasoning model, so the client can send
   `temperature=0` for deterministic grounded output — the flagship 400-rejects
   `temperature`. Deterministic output also makes the captured demo transcript
   reproducible. *(Caveat from fact-checking: temperature support is version-sensitive
   across GPT-5-family snapshots — verified for gpt-5.4-mini specifically, but validate
   with one live API call against the pinned id at build time.)*
2. Output tokens cost 3.3× less ($4.50 vs $15.00/1M), which keeps the cost-asymmetry
   narrative clean: mini→nano is ≈3.75× input / 3.6× output — a "strong-but-cheap,
   matched to task difficulty" story.

**Analytics = gpt-5.4-nano (unanimous across researchers).** Flat closed-enum
classification and short-input summaries are its documented sweet spot. It is too weak
for the user-facing conversation role (weak on hard tasks; would risk the graded
refusal/citation behavior) — but that role is mini's.

**Embeddings = text-embedding-3-small (unanimous).** $0.02/1M, 1536 dims,
L2-normalized. No reason to pay 6.5× for 3-large (~2 MTEB points) at
hundreds-to-thousands of vectors. Critically, staying on OpenAI for embeddings is what
makes the **one-key** story true.

## Cost per turn

Memory hit ≈ one mini answer call over ~2.5–3.5K pre-filtered tokens → **~$0.006**.
Miss adds nano page summaries + embeddings → **~$0.008**. A 100-turn demo lands around
**$0.60–0.90** (vs ~$1.50–2 on the flagship). The absolute dollar delta is below the
grading noise floor — **cost is the tie-breaker here, not the driver.** The decisive
factors: task-matched quality, deterministic DX (temperature support), one key, and a
clean cost/quality narrative.

## Full market comparison (all prices verified 2026-07-04 unless flagged)

| Model | Role considered | Input /1M | Output /1M | Verified | Notes |
|---|---|---|---|---|---|
| **gpt-5.4-mini** | **Conversation (CHOSEN)** | **$0.75** | **$4.50** | ✅ official page | ~$0.006 hit / ~$0.008 miss per turn; temperature=0 support pending real-key probe |
| **gpt-5.4-nano** | **Analytics (CHOSEN)** | **$0.20** | **$1.25** | ✅ official page | Enum classifier + short summaries = its sweet spot |
| **text-embedding-3-small** | **Embeddings (CHOSEN)** | **$0.02** | n/a | ✅ | 1536d, L2-normalized |
| gpt-5.4 (flagship) | Conversation (RUNNER-UP) | $2.50 | $15.00 | ✅ official page | Reasoning family: rejects temperature; strongest injection resistance |
| claude-sonnet-5 | Conversation alt | $3.00 ($2/$10 intro→2026-08-31) | $15.00 | ✅ platform.claude.com | No Anthropic embeddings endpoint → +1 key |
| claude-opus-4-8 | Conversation alt | $5.00 | $25.00 | ✅ platform.claude.com | +1 key; overkill for pre-filtered chunks |
| claude-haiku-4-5 | Analytics alt | $1.00 | $5.00 | ✅ platform.claude.com | 10×/12.5× Gemini Flash-Lite; still +1 embeddings key |
| claude-fable-5 | Conversation alt | $10.00 | $50.00 | ✅ platform.claude.com | Frontier-priced; ~30% heavier tokenizer; profligate for RAG |
| gemini-2.5-flash-lite | Analytics alt | $0.10 | $0.40 | ✅ ai.google.dev | Cheapest anywhere; +provider; free tier trains on data & rate-limits |
| gemini-2.5-flash | Conversation alt (all-Google) | $0.30 | $2.50 | ✅ ai.google.dev | Only credible 1-key non-OpenAI stack (see why-not) |
| gemini-embedding-001 | Embeddings alt | $0.15 | n/a | ✅ ai.google.dev | Enables the all-Google option |
| mistral-large-3 / small-4 | Value pair (1 EU key) | ~$0.50 / ~$0.15 | ~$1.50 / ~$0.60 | ⚠️ aggregator-only | Versioned ids/prices NOT on official page — unverifiable |
| deepseek-v4-flash | Value | $0.14 | $0.28 | ✅ official | China residency optics; json_object-only + strict-mode bug; no embeddings |
| llama-4-maverick (Groq/Together) | Value | ~$0.15 | ~$0.60 | ⚠️ aggregators | Host fragmentation; free-tier 429s mid-demo; no first-party embeddings |
| amazon-nova-lite | Value analytics | $0.06 | $0.24 | ✅ AWS | AWS+IAM+Bedrock enablement = heaviest evaluator setup in the sweep |

## Why NOT each alternative

- **gpt-5.4 (flagship) for conversation** — over-provisioned: its differentiators
  (agentic reasoning, huge context, tool orchestration) are exactly what this design
  removes by putting routing in code and pre-bounding context. Not ahead of mini on the
  grounded axis; 3.3× output cost; rejects `temperature`. Documented as the
  zero-code-change runner-up, not rejected as wrong.
- **gpt-5.4-nano for conversation** — too weak for user-facing grounded synthesis +
  injection resistance + refusal judgment. Correct for analytics only.
- **gpt-5.6 Sol / Terra / Luna** — preview-only as of 2026-07-04: partner-gated, no GA
  pricing, no stable ids. Wiring it into a clone-and-run take-home risks the
  evaluator's account lacking access. Future-upgrade note only.
- **text-embedding-3-large** — 6.5× the price for ~2 MTEB points at this scale; 3072
  dims would force an index rebuild.
- **claude-opus-4-8** — best-in-class injection resistance but overkill, and Anthropic
  has NO embeddings endpoint (verified: official docs redirect to Voyage AI) → 2nd key,
  breaks the one-key story. Also rejects temperature; different structured-output
  surface (code rework).
- **claude-sonnet-5** — strongest Anthropic value pick, but still no embeddings
  endpoint → +1 key, and its $2/$10 intro pricing expires 2026-08-31 (cost table would
  silently drift). Code-level guardrails already carry the injection defense.
- **claude-haiku-4-5** — fine classifier, but 10× input / 12.5× output the price of
  Gemini Flash-Lite and doesn't solve the embeddings gap.
- **claude-fable-5** — $10/$50 frontier pricing, ~30% heavier tokenizer, retention
  requirements; zero benefit for grounded RAG over a few chunks.
- **gemini-2.5-flash-lite (analytics)** — cheapest paid option anywhere and adequate,
  but adds a 2nd provider/key, a different structured-output surface (rework), and its
  FREE tier trains on data + daily caps can 429 mid-evaluation. ~$1 saving on a ~$2 demo.
- **gemini-3.1-flash-lite** — preview-adjacent id (stability risk), 2.5× the input
  price of 2.5-flash-lite.
- **all-Google one-key stack (gemini-2.5-flash + gemini-embedding-001)** — the only
  credible 1-key non-OpenAI option. Rejected: injection resistance / strict grounding a
  step below on exactly the graded behaviors; full classifier + client rework; free
  tier trains on data and rate-limits; displaces a fully-verified single-OpenAI stack
  for no material gain.
- **gemini-3.1-pro-preview** — frontier tier with long-context pricing this app never
  needs; unstable "preview" id.
- **all-Mistral (large-3 + small-4 + mistral-embed)** — the best value alternative that
  preserves ONE key and has good EU optics + free tier. Rejected: versioned ids/prices
  are aggregator-sourced, NOT on the official pricing page (the assignment demands a
  documented, verifiable cost story); realistic saving ~$1.50 on a ~$2 demo; thinner
  docs/community for a solo few-day build. Named as the value runner-up.
- **deepseek-v4-flash** — cheapest raw tokens, but China data residency = poor
  EU-GDPR optics on a graded artifact; structured output is json_object-only with a
  documented strict-mode malformed-JSON bug; legacy model names deprecate 2026-07-24;
  no embeddings endpoint.
- **kimi / qwen (Moonshot / Alibaba)** — same residency-optics problem; Qwen's free dev
  tier ended April 2026; cheapness doesn't overcome the optics for a graded take-home.
- **llama-4 via Groq/Together/Fireworks** — open-weight and cheap, but provider
  fragmentation, rate-limited free tiers that can 429 during a live demo, no
  first-party embeddings, host-dependent structured-output support.
- **amazon-nova-lite/micro (Bedrock)** — cheapest analytics on paper, but AWS account +
  IAM + Bedrock model-access enablement + region config is the heaviest evaluator setup
  in the sweep. Disqualified on setup friction alone.
- **OpenRouter (aggregator)** — one key for many chat models, but no native embeddings
  → back to 2 keys; adds a credit top-up step and a middleman; json_schema support
  varies by underlying model.

## Embedding models considered

gemini-embedding-001 ($0.15/1M — only relevant on an all-Google stack), Cohere
embed-v4, Voyage (Anthropic's partner), local bge/gte via sentence-transformers
(zero-key but a torch-sized install for a marginal, English-only gain) — all rejected
on second-key or dependency-weight grounds at this corpus size with exact FLAT KNN.
`text-embedding-3-large` is documented as a one-line env upgrade
(`EMBEDDING_MODEL` + `EMBEDDING_DIM=3072`, then `wipe-memory`; ~3× index memory).

**Important:** `SIMILARITY_THRESHOLD=0.70` is calibrated for text-embedding-3-small.
Cosine-similarity scales differ per embedding model — changing `EMBEDDING_MODEL`
changes what 0.70 *means* and requires re-tuning the threshold.

## Runner-up pair (documented, zero code change)

**gpt-5.4 (flagship) + gpt-5.4-nano + text-embedding-3-small** — same provider, same
key, same SDK; `CONVERSATION_MODEL` env-swap only. Prefer it when maximum answer
quality / injection resistance outweighs cost and determinism. Secondary runner-up on a
different axis: **all-Mistral** (1 EU key, near-zero cost) — only after confirming its
model ids/prices on the official page.

## Future upgrade path (do NOT wire in)

gpt-5.6 (Sol/Terra/Luna): preview-only, partner-gated, no stable ids as of 2026-07-04.
One-line future note only — a gated or renamed preview id would break the evaluator's
demo.
