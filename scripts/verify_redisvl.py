"""M1 verification duty (PLAN section 14): confirm the redisvl signatures M2 relies on.

Prints which of the later-needed APIs are present in the installed redisvl:
  - SearchIndex.load(..., ttl=...)          (per-key TTL at store time)
  - redisvl.redis.utils.array_to_buffer     (float32 byte-packing for vectors)
  - redisvl.query.VectorQuery               (KNN query object)

If load(ttl=) is absent, the documented fallback is an explicit EXPIRE pipeline:
store the keys, then EXPIRE each key with settings.memory_ttl_seconds.
"""

import importlib
import inspect

import redisvl


def check(label: str, fn) -> bool:
    try:
        ok = bool(fn())
    except Exception as exc:  # noqa: BLE001 - a verification script reports, never crashes
        print(f"  [??] {label}: check errored: {exc.__class__.__name__}: {exc}")
        return False
    print(f"  [{'OK' if ok else 'NO'}] {label}")
    return ok


def has_load_ttl() -> bool:
    from redisvl.index import SearchIndex

    return "ttl" in inspect.signature(SearchIndex.load).parameters


def has_array_to_buffer() -> bool:
    for mod in ("redisvl.redis.utils", "redisvl.utils.utils", "redisvl.utils"):
        try:
            m = importlib.import_module(mod)
        except ImportError:
            continue
        if hasattr(m, "array_to_buffer"):
            print(f"       (found in {mod})")
            return True
    return False


def has_vector_query() -> bool:
    from redisvl.query import VectorQuery  # noqa: F401

    return True


def main() -> None:
    print(f"redisvl version: {redisvl.__version__}")
    ttl_ok = check("SearchIndex.load(..., ttl=...)", has_load_ttl)
    check("array_to_buffer", has_array_to_buffer)
    check("query.VectorQuery", has_vector_query)
    if not ttl_ok:
        print(
            "  -> FALLBACK REQUIRED (documented): store keys, then pipeline EXPIRE per key\n"
            "     with settings.memory_ttl_seconds (see PLAN section 10.1 / M2 store.py)."
        )


if __name__ == "__main__":
    main()
