# Quickstart: Validating Milestone 4

**Prerequisites**: repo at `~/Desktop/epam/memory-first-agent`, `uv sync` done,
`make redis-up` running, `.env` with the classic GitHub PAT (dev) — plus, for step 6 only,
a real OpenAI platform key. Contracts referenced from `contracts/`; record/aggregate
shapes from `data-model.md`.

## 1. Zero-key gates (Constitution P-VIII)

```bash
cd ~/Desktop/epam/memory-first-agent
uv run ruff check . && uv run ruff format --check .
make test        # 36 prior tests + test_classifier_parsing.py + test_turnlog.py, all green, no keys
```

## 2. Turn log over live turns (US1)

```bash
rm -f logs/turns.jsonl
uv run memagent ask "How does Redis 8 vector search work?"
uv run memagent ask "How does Redis 8 vector search work?"
python3 -c "
import json
lines = [json.loads(l) for l in open('logs/turns.jsonl') if l.strip()]
assert len(lines) == 2, lines
routes = [l['route'] for l in lines]
assert routes[0] == 'memory_miss_web_search' and routes[1] == 'memory_hit', routes
r = lines[0]
for k in ('turn_id','ts','session_id','query','query_sha256','route','degradation',
          'similarity_top','similarity_threshold','web','sources','latency_ms','tokens',
          'guardrail','errors','analytics'):
    assert k in r, k
assert len(r['query_sha256']) == 16
assert r['web'] and r['web']['provider'] in ('tavily','ddgs')
assert lines[1]['web'] is None
assert 'total' in r['latency_ms'] and 'classify' in r['latency_ms']
assert 'answer_llm' in r['tokens'] and 'analytics_llm' in r['tokens']
print('turn log OK:', routes)
"
```

Expected: `turn log OK: ['memory_miss_web_search', 'memory_hit']` (run from a wiped or
warm memory accordingly; the two-line count is the invariant).

## 3. Analytics report + sample (US2)

```bash
uv run memagent analytics                     # ten sections over live turns.jsonl
uv run memagent analytics --json | python3 -c "import json,sys; a=json.load(sys.stdin); print('json OK', a['total_turns'], a['hit_rate'])"
# sample coverage (FR-019):
for r in memory_hit memory_miss_web_search degraded_web blocked failed; do
  grep -q "\"route\": \"$r\"" logs/turns.sample.jsonl || echo "MISSING $r"; done
grep -q '"analytics": null' logs/turns.sample.jsonl || echo "MISSING null analytics"
grep -q "read_json_auto('logs/turns.jsonl')" README.md || echo "MISSING DuckDB note"
# missing-file friendliness:
TURN_LOG_PATH=logs/nope.jsonl uv run memagent analytics    # friendly guidance, exit 0
```

## 4. REPL banners + history (US4)

```bash
uv run memagent chat
# > ask a novel question         → [MEMORY MISS → searching the web], answer, sources
# > ask the identical question   → [MEMORY HIT sim=0.7x–1.00], no web log lines on stderr
# > exit
```

Answer must appear BEFORE the `log_turn`/classify stderr lines of that turn (watch order).
Calibration note (M2/M3 measured): pick a topic known to re-hit — the Redis question above
re-asks at ~0.74.

## 5. stdout pipe-clean (FR-021)

```bash
uv run memagent ask "What is trafilatura?" > /tmp/out.txt 2>/tmp/err.txt
grep -cE "turn_id=" /tmp/out.txt   # 0 (no log lines on stdout)
grep -cE "turn_id=" /tmp/err.txt   # ≥1 (operational lines carry turn_id)
```

## 6. FR-007 live probe (real key, one-off — Clarify Option B)

```bash
OPENAI_API_KEY=sk-…real… OPENAI_BASE_URL= uv run python -c "…probe from contracts/llm-clients.md…"
```

Expected: a short reply (HTTP 200) — proves `temperature=0` AND `max_tokens` on
`gpt-5.4-mini`. Record the outcome + date in `MODEL_CHOICES.md` and
`docs/ai_prompts/milestone-4.md`. Rejection contingencies in the contract.

## 7. Fail-fast + docs

```bash
OPENAI_API_KEY= uv run memagent ask "x"     # one readable line, exit 1, no traceback
grep -c '\$0.75' MODEL_CHOICES.md            # ≥1 (price table ported + re-verified)
```

## 8. Demoable outcome (PLAN §13, M4 row)

All four subcommands do real work in one session: `wipe-memory` → `ask` ×2 → `chat`
(one turn) → `analytics` shows a real hit-rate and topic table over those turns.
