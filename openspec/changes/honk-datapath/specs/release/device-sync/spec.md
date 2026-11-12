## MODIFIED Requirements

### Requirement: Sync through the proxy
The router SHALL run a sync container that downloads release artifacts to `/mnt/data/repo`. Its traffic passes through the container bridge and is routed by honk according to rules, so it does not depend on whether router-originated traffic can reach GitHub directly.

#### Scenario: Router cannot reach GitHub directly
- **WHEN** direct connections from the router to the Releases service are blocked and a sync is triggered
- **THEN** the sync still completes successfully
