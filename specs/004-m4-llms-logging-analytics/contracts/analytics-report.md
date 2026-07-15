# Contract: Analytics report (`analytics/report.py`, `memagent analytics`) — FR-016…019

**Consumers**: the operator (CLI), M6's CI report step, DuckDB users via the README note.

## aggregate(records: Iterable[dict]) -> dict

Pure; returns exactly the data-model §4 shape. Rules:

- `hit_rate` per research D10: hits ÷ (`memory_hit` + `memory_miss_web_search` +
  `degraded_web` where `degradation == "snippets_only"`); `0.0` on empty denominator.
- `top_topics`: top 10 `(topic, count)` from `analytics.topic` of classified records.
- `avg_latency_ms_by_route`: mean of `latency_ms.total` per route; records without a
  `total` are excluded from that route's mean.
- `errors`: count of records with non-empty `errors`; `unclassified`: count with
  `analytics` null/absent; `recent`: last 10 as `{ts, route, similarity_top, topic, query}`
  (topic `None` when unclassified).
- Tolerates blank lines (skipped by the reader) and missing optional keys.

## render_report(agg, console) -> None

- One rich section per aggregate area — the ten sections of FR-016 (headline stats may
  share a summary table; all ten data points MUST be visibly rendered).
- EVERY user-derived string — `query`, `topic`, source `title`/`url`, `language` — wrapped
  in `rich.markup.escape()` at cell-build time (FR-018).

## CLI command (`memagent analytics [--json]` — replaces the M1 stub in `cli.py`)

1. Read `Settings().turn_log_path`; stream line-by-line; `json.loads` per non-blank line.
2. Missing file → print friendly guidance ("no turns logged yet — run `memagent ask` …
   or see `logs/turns.sample.jsonl`") and exit 0 (FR-019 edge; not an error).
3. `--json`: `print(json.dumps(aggregate(records)))` to stdout, return BEFORE any rich
   Console output (FR-017 accept: stdout parses as JSON; contains `total_turns`,
   `hit_rate`; no table borders).
4. Default: `render_report(aggregate(records), Console())`.
5. Command does NOT require `OPENAI_API_KEY` or Redis (pure file read) — no key guard.

## Shipped artifacts

- `logs/turns.sample.jsonl` per data-model §5 coverage matrix (10 records; all 5 routes;
  ≥1 `analytics: null`; ≥1 non-empty `errors`; ≥1 non-`en`; ≥1 markup-bearing query).
- README gains verbatim:

  ```
  The turn log is directly DuckDB-queryable:
    duckdb -c "SELECT route, count(*) FROM read_json_auto('logs/turns.jsonl') GROUP BY route"
  ```

- `.gitignore` note: `logs/turns.jsonl` (live) stays untracked; `logs/turns.sample.jsonl`
  is tracked — verify the existing ignore rules allow exactly that split.

## Acceptance mapping

| FR | Check |
|---|---|
| FR-016 | unit: known 4-record set → total 4, hit_rate 2/3; null-analytics + errors counting |
| FR-017 | CliRunner: `--json` stdout is valid JSON, no `─` border chars |
| FR-018 | unit/CliRunner: `[red]boom[/red]` query renders literally (escape applied) |
| FR-019 | sample file coverage grep loop (quickstart); missing-file run prints guidance, exit 0, no traceback |
