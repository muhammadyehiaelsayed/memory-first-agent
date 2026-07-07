# Module: src/memagent/llm/clients.py
# Derived from: 00_main_functionality.feature :: "Answer from memory when a similar question was seen before"
# Spec sources: milestone-4-llms-logging-analytics.md
# Executable binding: tests/bdd/test_bdd_llm_clients.py
Feature: LLM transport and token accounting (src/memagent/llm/clients.py)
  The root "answer from memory" turn depends on two things this module owns:
  the embedder that turns the question into the query vector fed to the
  memory-first search, and the conversation LLM that writes the grounded
  answer while reporting per-turn token usage. This module finalises those
  AsyncOpenAI wrappers — one shared transport, retries disabled (tenacity is
  the single owner), and exactly one network seam per surface — so the answer
  the user reads is backed by faithful text and honest token accounting.

  # source: milestone-4-llms-logging-analytics.md :: complete() returns text plus usage
  # covers: memagent.llm.clients.OpenAIChatLLM.complete, memagent.llm.clients.OpenAIChatLLM._call
  Scenario: A completed answer carries the model text and token accounting
    Given a conversation chat client backed by a stubbed OpenAI SDK
    And the SDK returns the reply "hello world" using 11 prompt and 7 completion tokens
    When the agent asks the client to complete a system-and-user exchange
    Then the completion text is "hello world"
    And the reported usage maps prompt tokens to input and completion tokens to output for model "gpt-x"

  # source: milestone-4-llms-logging-analytics.md :: parse() returns a schema instance and usage
  # covers: memagent.llm.clients.OpenAIChatLLM.parse, memagent.llm.clients.OpenAIChatLLM._parse_call
  Scenario: A structured classification is returned together with its token usage
    Given an analytics chat client backed by a stubbed OpenAI SDK
    And the SDK returns a parsed QueryClassification object using 5 prompt and 2 completion tokens
    When the agent asks the client to parse a query into the QueryClassification schema
    Then the first result is the parsed QueryClassification instance
    And the second result reports usage keyed by input_tokens, output_tokens and model

  # covers: memagent.llm.clients.OpenAIChatLLM._usage
  Scenario: Token accounting falls back to zero when the SDK omits usage
    Given a conversation chat client whose stubbed SDK response has no usage block
    When the client completes an exchange
    Then the reported usage is zero input and zero output tokens for the configured model "gpt-z"

  # covers: memagent.llm.clients.OpenAIChatLLM.__init__
  Scenario: Constructing a chat client pins its model, token cap and temperature
    Given the pinned conversation configuration model "gpt-5.4-mini", max_tokens 2048, temperature 0
    When a chat client is constructed without a retry policy
    Then the client exposes exactly those pinned settings
    And its complete and parse network seams remain the plain unwrapped methods

  # covers: memagent.llm.clients.OpenAIEmbedder.embed, memagent.llm.clients.OpenAIEmbedder._embed_call
  Scenario: Embedding vectors are returned in the SDK's index order
    Given an embedder backed by a stubbed OpenAI SDK
    And the SDK returns two embeddings out of index order
    When the agent embeds a batch of texts
    Then the vectors come back ordered by their original index

  # covers: memagent.llm.clients.OpenAIEmbedder.__init__
  Scenario: A retry policy wraps the embedder's single network seam
    Given an embedder constructed with the production llm retry policy and zero-wait settings
    And its stubbed SDK raises a retryable timeout once before succeeding
    When the agent embeds a text
    Then the embedding call is retried and ultimately returns the vector
    And the embedder records the configured model and dimension

  # source: milestone-4-llms-logging-analytics.md :: conversation client carries the pinned params
  # covers: memagent.llm.clients.build_openai_clients
  Scenario: Building the client trio shares one transport with retries disabled
    Given default settings carrying an OpenAI API key
    When the three OpenAI clients are built
    Then the conversation client uses model "gpt-5.4-mini", max_tokens 2048 and temperature 0
    And the analytics client uses model "gpt-5.4-nano" and max_tokens 256
    And all three clients share one AsyncOpenAI transport with max_retries 0 and timeout 45.0

  # source: milestone-4-llms-logging-analytics.md :: base URL routing and key fail-fast
  # covers: memagent.llm.clients.build_openai_clients
  Scenario Outline: The shared transport honours the base URL and fails fast without a key
    Given an OpenAI API key "<key>" and base URL "<base>"
    When the OpenAI clients are built
    Then the outcome is "<outcome>"

    Examples:
      | key     | base                               | outcome             |
      | sk-live |                                    | openai default host |
      | ghp_pat | https://models.github.ai/inference | github models host  |
      |         |                                    | readable systemexit |
