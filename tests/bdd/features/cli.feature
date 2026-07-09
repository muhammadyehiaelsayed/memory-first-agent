# Module: src/memagent/cli.py
# Derived from: 00_main_functionality.feature :: "Answer from memory when a similar question was seen before"
# Spec sources: milestone-4-llms-logging-analytics.md, milestone-6-e2e-evals-delivery.md
# Executable binding: tests/bdd/test_bdd_cli.py
Feature: Command-line interface (src/memagent/cli.py)
  The Typer CLI is the user-facing surface for the memory-first agent. `ask` and
  `chat` run a turn and present the route the deterministic router chose: the
  memory-hit banner with cited sources on "memory_hit", a miss or offline banner
  on a web fallback, a blocked banner when the guard fires, and a plain apology
  (exit 1) on a failed turn. `analytics` reports the per-turn JSONL log and
  `wipe-memory` recreates the Redis index. stdout stays pipe-clean; operational
  and error text goes to stderr.

  # covers: memagent.cli._hit_banner
  Scenario: The memory-hit banner shows the similarity to two decimals
    Given a memory hit whose top similarity is 0.9
    When the hit banner is formatted
    Then the banner reads "[MEMORY HIT sim=0.90]"

  # covers: memagent.cli._print_sources
  Scenario: Cited sources print one per line, and an empty list prints nothing
    Given a single web source titled "Redis docs" at "https://redis.io/x"
    When the sources are printed
    Then stdout contains "(web) Redis docs <https://redis.io/x>"
    And printing an empty list of sources writes nothing to stdout

  # covers: memagent.cli._emit
  Scenario: Emitting to a non-terminal stdout stays byte-identical plain text
    Given a colored banner to emit to a non-terminal stdout
    When the line is emitted
    Then stdout is exactly the banner text with no color codes

  # covers: memagent.cli._advance_status
  Scenario: The live status names the step that runs next as each node finishes
    Given a recording status line
    When memory search finishes as a hit with similarity 0.83
    Then the status label mentions "Found in memory (sim 0.83)"
    When memory search finishes as a miss
    Then the status label mentions "searching the web"
    When the web search returns 3 results
    Then the status label mentions "Reading 3 pages"

  # covers: memagent.cli.status_label
  Scenario: status_label narrates each decision, colours it, and keeps the locked step names
    Given a turn state at the default threshold
    When status_label is asked about a memory hit with similarity 0.83
    Then it returns a green label containing "Found in memory (sim 0.83)"
    When status_label is asked about a memory miss
    Then it returns a yellow label containing "searching the web"
    When status_label is asked about a web search with 3 results
    Then it returns a cyan label containing "Reading 3 pages"
    When status_label is asked about a terminal answer node
    Then it returns nothing to narrate

  # covers: memagent.cli.chat_help_text
  Scenario: The chat help lists every command and both ways to stop
    When the chat help text is built
    Then it names every command and both ways to stop

  # covers: memagent.cli._stream_turn
  Scenario: Streaming a turn returns the merged state, the memory-search update, and the block flag
    Given a stubbed streaming agent and a fresh turn state
    When the turn is streamed to completion
    Then the merged state resolves route "memory_hit" with the memory answer
    And the memory-search update is returned and the turn is not blocked

  # covers: memagent.cli._exit_redis_down
  Scenario: A Redis outage is reported to stderr and exits non-zero
    Given a Redis connection failure
    When the CLI reports the Redis outage
    Then a CLI exit is raised with code 1
    And stderr contains "cannot reach Redis"
    And stderr contains "make redis-up"

  # covers: memagent.cli._wipe
  Scenario: Wiping memory drops and recreates the vector index
    Given the Redis client and index helpers are stubbed
    When the wipe coroutine runs
    Then the vector index is recreated and the client is closed
    And stdout contains "Wiped and recreated index 'web_memory'."

  # covers: memagent.cli.wipe_memory
  Scenario: wipe-memory reports a friendly error when Redis is unreachable
    Given wiping the index fails with a Redis connection error
    When the "wipe-memory" command is invoked
    Then the command exits with a non-zero status
    And stderr contains "cannot reach Redis"

  # covers: memagent.cli._ask
  Scenario: A single question is answered through the agent facade
    Given the agent answers any question with a memory-hit turn result
    When the ask coroutine runs for a question
    Then the coroutine returns the agent's turn result with route "memory_hit"

  # covers: memagent.cli.ask
  Scenario: ask refuses to run without an OpenAI key
    Given no OpenAI API key is configured
    When the user asks a question with the "ask" command
    Then the command exits with a non-zero status
    And stderr contains "OPENAI_API_KEY is not set"

  # covers: memagent.cli.ask
  Scenario: ask presents the memory-hit banner and cited sources
    Given the turn resolves as "memory_hit"
    When the user asks a question with the "ask" command
    Then the command exits successfully
    And stdout contains "[MEMORY HIT sim=0.90]"
    And stdout contains "(memory) Doc <https://redis.io/x>"

  # covers: memagent.cli.ask
  Scenario: ask shows the miss banner when it falls back to the web
    Given the turn resolves as "memory_miss_web_search"
    When the user asks a question with the "ask" command
    Then the command exits successfully
    And stdout contains "[MEMORY MISS → searching the web]"
    And stdout contains "(web) WebDoc <https://ex.com/a>"

  # covers: memagent.cli.ask
  Scenario: ask shows the offline banner when Redis is down mid-turn
    Given the turn resolves as "degraded_web"
    When the user asks a question with the "ask" command
    Then the command exits successfully
    And stdout contains "[MEMORY OFFLINE → searching the web (not cached)]"

  # covers: memagent.cli.ask
  Scenario: ask prints the blocked banner and no sources for a guarded turn
    Given the turn resolves as "blocked"
    When the user asks a question with the "ask" command
    Then the command exits successfully
    And stdout contains "[BLOCKED by input guard]"
    And stdout does not contain "should-not-print"

  # covers: memagent.cli.ask
  Scenario: ask reports a failed turn as a bare apology with a non-zero exit
    Given the turn resolves as "failed"
    When the user asks a question with the "ask" command
    Then the command exits with a non-zero status
    And stdout contains "Sorry, I ran into a problem answering."
    And stdout does not contain "MEMORY"

  # covers: memagent.cli.ask
  Scenario: ask surfaces a Redis outage as a friendly error and non-zero exit
    Given answering the question fails because Redis is unreachable
    When the user asks a question with the "ask" command
    Then the command exits with a non-zero status
    And stderr contains "cannot reach Redis"

  # covers: memagent.cli.chat
  Scenario: chat refuses to start without an OpenAI key
    Given no OpenAI API key is configured
    When the "chat" command is invoked
    Then the command exits with a non-zero status
    And stderr contains "OPENAI_API_KEY is not set"

  # covers: memagent.cli.chat
  Scenario: chat starts the interactive REPL when a key is configured
    Given an OpenAI API key is configured and the REPL loop is stubbed
    When the "chat" command is invoked
    Then the command exits successfully
    And the REPL loop was started

  # source: milestone-4-llms-logging-analytics.md :: the hit/miss banner honours the inclusive 0.70 boundary
  # covers: memagent.cli._chat
  Scenario: The chat REPL prints the hit banner, the answer, and its sources
    Given a stubbed agent whose turn streams a memory hit with similarity 0.95
    And the user types one question and then "exit"
    When the chat REPL runs
    Then stdout contains "[MEMORY HIT sim=0.95]"
    And stdout contains "Cached answer about redis."
    And stdout contains "(memory) Redis Docs <https://redis.io/x>"

  # covers: memagent.cli._chat
  Scenario: A failed turn shows one clean error, never a hit banner then an apology
    Given a stubbed agent whose turn hits memory but then fails to answer
    And the user types one question and then "exit"
    When the chat REPL runs
    Then stdout contains "a required step failed"
    And stdout does not contain "MEMORY HIT"

  # covers: memagent.cli._chat
  Scenario: A cancelled turn (Ctrl-C) is discarded and the chat keeps going
    Given a stubbed agent whose first turn is cancelled mid-answer and whose next turn answers
    And the user types one question, then another, then "exit"
    When the chat REPL runs
    Then stdout contains "Answer after the cancelled one."
    And stdout does not contain "Traceback"

  # source: milestone-3-langgraph-guardrails.md :: an L1-blocked payload never enters replayed chat history
  # covers: memagent.cli._chat
  Scenario: A blocked chat turn is refused and never re-enters replayed history
    Given a stubbed agent that blocks the first question and answers the next
    And the user types a blocked question, then a normal question, then exits
    When the chat REPL runs
    Then stdout contains "[BLOCKED by input guard]"
    And the blocked question does not appear in the next turn's replayed history

  # source: milestone-4-llms-logging-analytics.md :: --json prints aggregates to stdout only
  # covers: memagent.cli.analytics
  Scenario: analytics --json prints the aggregate object as JSON to stdout
    Given a turn log with one memory-hit turn and one web-miss turn
    When the "analytics --json" command is invoked
    Then the command exits successfully
    And stdout is a JSON object whose total_turns is 2 and hit_rate is 0.5

  # covers: memagent.cli.analytics
  Scenario: analytics renders the report tables over the turn log
    Given a turn log with one memory-hit turn and one web-miss turn
    When the "analytics" command is invoked
    Then the command exits successfully
    And stdout contains "Turn log summary"

  # source: milestone-4-llms-logging-analytics.md :: a missing turn log prints a friendly message
  # covers: memagent.cli.analytics
  Scenario: analytics prints friendly guidance when no turn log exists
    Given no turn log file exists yet
    When the "analytics" command is invoked
    Then the command exits successfully
    And stderr contains "no turns logged yet"
