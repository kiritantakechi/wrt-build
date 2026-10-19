# Spec Delta

## ADDED Requirements

### Requirement: Failures name the router's state
A test failure that involves the router SHALL show what the harness can still see of the router and its networks. A wait for a reboot that does not come SHALL show the command that was to reboot the router, the command's output and the console since it ran. A failing test with the router online SHALL show the LAN clients' addresses and routes, the router's WAN state with its log, and the emulated ISP's sessions with its log. Gathering this SHALL NOT change the test's outcome.

#### Scenario: A reboot that does not come
- **WHEN** a command detached on the router ends without rebooting it, and the harness waits for the reboot
- **THEN** the wait fails at its time limit, and the failure shows the command, its output and the console since it ran

#### Scenario: A failing test with the router online
- **WHEN** a test that uses the router online fails
- **THEN** its report has a section with the LAN clients' addresses and routes, the router's WAN state and log, and the ISP's sessions and log
