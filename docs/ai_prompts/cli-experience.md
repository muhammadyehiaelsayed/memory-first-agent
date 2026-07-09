# CLI chat experience — live narration, commands, stop affordances (appended 2026-07-09)

A post-delivery UX pass on the `chat` REPL, on the `cli-ux-enhance` branch. Tooling:
Claude Code (Fable 5), a design-exploration workflow, then an adversarial review workflow.

## 1. Instruction (user-issued, verbatim)

1. "use workflows to enahnce the cli expaiance i would like to know what the agent do
   while working in which node he it now what discistion he took in frendly way not too
   much deatils and i want the best explaiciance and best font and i want alwasy to let
   user know if he want to stop how he can do it and it there other ation he can do he
   should know how to do it"

## 2. Approach

A design workflow generated three divergent chat-UX proposals (minimal / guided /
transparent-trace) each with an ASCII mockup, then a judge synthesized one implementable
spec honoring the locked contracts (pipe-clean stdout FR-M4-21, byte-identical banners,
the `_advance_status` test substrings). Net design: a single self-overwriting status line
(no scrolling trace — that was cut as "too much detail"), a rounded welcome/`/help` panel,
a small command set, and traceback-free Ctrl-C — all chrome on stderr, TTY-gated.

## 3. What changed (all in `src/memagent/cli.py`)

Two new pure, testable helpers:
- `status_label(node, update, merged) -> (label, colour) | None` — maps a just-finished
  node + the decision it took to a friendly emoji label and colour (green hit / yellow
  web / red blocked / cyan working), or None at the terminal nodes. Keeps the three
  test-locked substrings ("Found in memory (sim …)", "searching the web", "Reading N
  pages") verbatim inside the friendly text. `_advance_status` is now a thin renderer over it.
- `chat_help_text() -> str` — the greeting + command list + stop hint, shared
  byte-identically by the welcome panel and `/help`.

In-place `_chat` / `chat` changes (covered by existing scenarios):
- Welcome panel (rounded, cyan) shown at start and on `/help`; commands `/help` (or
  `help`/`?`), `/clear` (forget this chat; long-term Redis memory kept), `exit`/`quit`.
- The `you>` prompt now writes to stderr and input is read on a DAEMON thread via a small
  `read_line()` closure — fixing two real bugs: `input(prompt)` leaked the prompt to stdout
  (broke the pipe-clean contract), and a non-daemon reader parked on a blocked read would
  hang process exit.
- Ctrl-C is traceback-free. A real SIGINT under `asyncio.Runner` arrives as
  `asyncio.CancelledError` at the awaiting frame (NOT `KeyboardInterrupt`), so both are
  caught and `asyncio.current_task().uncancel()` balances the Runner's cancel: mid-answer →
  the turn is discarded ("⏹ Stopped — ask me something else"), the session stays alive;
  idle prompt → clean leave. `exit`/`quit`/Ctrl-D print "👋 bye" (stderr). An outer guard in
  `chat()` exits 130 cleanly if a rapid double Ctrl-C escapes to the run boundary.

## 4. Adversarial pre-push review + fix

A 3-lens review + skeptics confirmed ONE real medium bug: the original Ctrl-C handlers
caught `KeyboardInterrupt`, but under `asyncio.Runner` (Python 3.12) a real SIGINT is
delivered as `asyncio.CancelledError` at the await — so the handlers were dead code and
Ctrl-C killed the whole REPL. Reproduced on the exact interpreter, then fixed by catching
`(KeyboardInterrupt, asyncio.CancelledError)` + `uncancel()`, and moving input onto a daemon
reader so leaving never hangs on a parked read. A guard BDD scenario now proves a mid-answer
`CancelledError` discards only that turn and the chat keeps going.

## 5. Verified

- 3 new BDD scenarios (`status_label`, `chat_help_text`, and the cancel-keeps-going guard)
  with `# covers:` declarations; traceability gate passes at 150 functions / 230 scenarios.
- Mutation-verified: a wrong label colour, a broken locked substring, a terminal node
  returning a label instead of None, and a dropped command token each turn a test red.
- Live under a real PTY: the welcome panel, `/help` panel, the `you>` prompt, the live
  `🧠 Checking memory…` spinner, the clean one-line failure apology (the turn hit today's
  free-tier embedding rate cap — proving the no-traceback failure UX), and `👋 bye` on exit
  all rendered correctly. The happy-path narration was rendered from the real `status_label`
  outputs (backend was rate-limited at capture time); the single-Ctrl-C cancel-and-continue
  and the no-exit-hang were reproduced directly on Python 3.12.
- `make test`: 400 keyless green; `make lint` clean.

## 6. Docs updated

README (chat usage paragraph + counts), `docs/BDD.md` (counts, cli row, matrix rows),
`AI_USAGE.md` (this record's index entry).
