# Module: scripts/verify_redisvl.py
# Derived from: 00_main_functionality.feature :: "Answer from memory when a similar question was seen before"
# Spec sources: milestone-1-scaffold-and-memory-schema.md (§6.12 verify_redisvl, FR-M1-17, §14 verification duty)
# Executable binding: tests/bdd/test_bdd_scripts_tooling.py
Feature: The redisvl verification script confirms the vector-memory APIs the store relies on (scripts/verify_redisvl.py)
  Answering "from the stored memory chunks" depends on three redisvl signatures: the
  KNN VectorQuery object, the float32 array_to_buffer packer, and per-key TTL on the
  index loader. This throwaway script probes each one in the installed redisvl and
  reports what is present, never crashing, so a signature drift is caught before the
  memory path is built on it.

  # covers: scripts.verify_redisvl.check
  Scenario: A capability that reports present is confirmed and logged as OK
    Given a capability probe that reports the feature is present
    When the verifier checks that probe
    Then the check returns a truthy result
    And an OK line naming the probe is printed

  # covers: scripts.verify_redisvl.check
  Scenario: A probe that raises is caught and reported as absent rather than crashing
    Given a capability probe that raises an exception
    When the verifier checks that probe
    Then the check returns a falsy result without propagating the error
    And an errored line naming the probe is printed

  # covers: scripts.verify_redisvl.has_load_ttl
  # source: milestone-1-scaffold-and-memory-schema.md :: "verification confirms the signatures used later"
  Scenario: The per-key TTL keyword on the index loader is detected in the installed redisvl
    When the loader TTL capability is probed
    Then the probe confirms the ttl keyword is accepted

  # covers: scripts.verify_redisvl.has_array_to_buffer
  Scenario: The float32 vector-packing helper is importable from the installed redisvl
    When the array-to-buffer capability is probed
    Then the probe confirms the helper is importable

  # covers: scripts.verify_redisvl.has_vector_query
  Scenario: The KNN VectorQuery object is importable from the installed redisvl
    When the vector-query capability is probed
    Then the probe confirms the query object is importable

  # covers: scripts.verify_redisvl.main
  # source: milestone-1-scaffold-and-memory-schema.md :: "verification confirms the signatures used later"
  Scenario: The verification report names the redisvl version and every probed signature
    When the redisvl verification report is produced
    Then the report states the installed redisvl version
    And the report lists the load-ttl, array-to-buffer and VectorQuery probes
