"""log_turn node — NO-OP STUB in M2. Replaced by M4's real TurnLogger/JSONL node."""


def make_log_turn(resources):  # noqa: ARG001 — uniform node factory signature
    async def log_turn(state: dict) -> dict:  # noqa: ARG001
        return {}

    return log_turn
