# Spec Delta

## ADDED Requirements

### Requirement: Waiting for a condition
The harness's polling helper SHALL call a probe until the probe answers with content, and return that answer. An empty answer SHALL count as no answer yet, whatever its type: `None`, `False`, zero, an empty string and an empty collection alike. When the time limit passes without an answer with content, the helper SHALL fail and name what it waited for.

#### Scenario: A probe answers empty first
- **WHEN** a probe answers with an empty string, then with an empty list, then with a value
- **THEN** the wait goes on through the empty answers, and returns the value

#### Scenario: No answer within the time limit
- **WHEN** a probe answers only with empty values until the time limit passes
- **THEN** the wait fails, and its error names what it waited for
