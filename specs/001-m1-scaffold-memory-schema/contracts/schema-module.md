# Contract: `memagent.memory.schema` (M1 — real logic)

Consumers: `cli.py wipe-memory` (M1), `memory/store.py` + `resources.build_resources()` (M2).
Source: milestone file §4.2/§6.5; PLAN §4.2. Stability: **fixed in M1** — M2+ import, never
modify signatures.

```python
def build_schema(settings: Settings) -> IndexSchema
```
- Returns the redisvl `IndexSchema` for index `settings.memory_index_name` ("web_memory"):
  HASH storage, `prefix="chunk"` + `key_separator=":"` (Redis PREFIX `chunk:` — setting
  `prefix="chunk:"` would produce `chunk::<id>` keys and is a defect), the 11 fields of
  [data-model.md](../data-model.md) Entity 2, vector field FLAT/cosine/float32 with
  `dims = settings.embedding_dim`.
- Pure function; no I/O.

```python
def get_index(settings: Settings, client) -> AsyncSearchIndex
```
- Binds the schema to an async Redis client (`redis.asyncio`). No I/O at construction.

```python
async def ensure_index(index: AsyncSearchIndex) -> bool
```
- Creates the index iff missing (`create(overwrite=False)`); **never drops data**; returns
  True iff it created it. Safe to call at every startup.

```python
async def wipe_index(index: AsyncSearchIndex) -> None
```
- Drops the index AND its keys, then recreates it empty. Primary call:
  `create(overwrite=True, drop=True)` (redisvl 0.23.0). Documented fallback if FR-017
  verification shows drift: `await index.delete(drop=True)` then
  `await index.create(overwrite=False)`.
- Idempotent across repeated calls and when the index is absent (FR-019).

```python
def assert_index_dims(embedder_dim: int, settings: Settings) -> None
```
- Raises `ValueError` iff `embedder_dim != settings.embedding_dim`; the message MUST name
  both dims, `EMBEDDING_MODEL`/`EMBEDDING_DIM`, and `memagent wipe-memory` as the recovery.
- Defined in M1; **not called at M1 startup** (no embedder exists). M2 wires it into
  `build_resources()`.

## Error behavior (M1)

Redis unreachable during `wipe-memory` → the CLI exits non-zero with a one-line readable
error naming the redis URL (no stack-trace wall). The typed `MemoryUnavailableError` wrapper
is an M5 concern — do not add it here.

## Verification hooks

- `FT.INFO web_memory` (or RedisInsight) shows the index after `wipe-memory`; key prefix is
  `chunk:` with a single colon.
- `scripts/verify_redisvl.py` (FR-017) prints presence/absence of `load(..., ttl=)`,
  `array_to_buffer`, `VectorQuery` and the EXPIRE-pipeline fallback note if absent.
