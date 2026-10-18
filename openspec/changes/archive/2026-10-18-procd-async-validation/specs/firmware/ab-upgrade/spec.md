# Spec Delta

## ADDED Requirements

### Requirement: The system stays responsive while it checks an image
While the system validates an upgrade image, it SHALL go on feeding its watchdog and answering its other requests, however long the validation takes, and SHALL answer the validation request once the validation has ended.

#### Scenario: A validation slower than the watchdog
- **WHEN** validating an upgrade image takes longer than the watchdog's timeout
- **THEN** the router is not reset, the system answers other requests meanwhile, and the validation request is answered with its result once the validation ends
