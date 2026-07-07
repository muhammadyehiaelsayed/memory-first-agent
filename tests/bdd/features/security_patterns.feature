# Module: src/memagent/security/patterns.py
# Derived from: 00_main_functionality.feature :: "Block malicious input at the guard before any model call"
# Spec sources: milestone-5-security-reliability.md
# Executable binding: tests/bdd/test_bdd_security.py
Feature: Severity folding and pattern compilation (src/memagent/security/patterns.py)
  The pattern registry feeds both the L1 screen and the L3 sanitizer. max_severity
  folds two severities by an explicit rank (HIGH > MEDIUM > None) rather than by the
  string values, so any HIGH match dominates regardless of registry order and the
  block decision behind the root "blocked" route is order-independent. _c compiles
  every registry regex case-insensitively.

  # source: milestone-5-security-reliability.md :: max_severity ranks by explicit order (spec note §6.3)
  # covers: memagent.security.patterns.max_severity
  Scenario: Severity folding ranks HIGH above MEDIUM above nothing
    Then folding HIGH with MEDIUM yields HIGH
    And folding MEDIUM with HIGH still yields HIGH
    And folding nothing with MEDIUM yields MEDIUM
    And folding nothing with nothing yields nothing

  # covers: memagent.security.patterns._c
  Scenario: The registry compiler produces case-insensitive matchers
    When I compile the pattern "ignore"
    Then it is a compiled regular expression
    And it matches "IGNORE" regardless of letter case
