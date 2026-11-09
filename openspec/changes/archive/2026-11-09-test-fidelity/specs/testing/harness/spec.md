# Spec Delta

## MODIFIED Requirements

### Requirement: Failures name the router's state
A test failure that involves the router SHALL show what the harness can still see of the router and its networks. A wait for a reboot that does not come SHALL show the command that was to reboot the router, the command's output and the console since it ran. A failing test with the router online SHALL show the LAN clients' addresses and routes, the router's WAN state with its log, and the emulated ISP's sessions with its log. When the router does not answer, the report SHALL say so after a few seconds instead of waiting out a connection for each of its parts. Gathering this SHALL NOT change the test's outcome.

#### Scenario: A reboot that does not come
- **WHEN** a command detached on the router ends without rebooting it, and the harness waits for the reboot
- **THEN** the wait fails at its time limit, and the failure shows the command, its output and the console since it ran

#### Scenario: A failing test with the router online
- **WHEN** a test that uses the router online fails
- **THEN** its report has a section with the LAN clients' addresses and routes, the router's WAN state and log, and the ISP's sessions and log

#### Scenario: A failing test with the router unreachable
- **WHEN** a test that uses the router online fails while the router takes no new connection
- **THEN** its report says that the router did not answer, still shows the LAN clients' and the ISP's state, and is ready within 20 s

### Requirement: Fixtures by layer
Each layer of the test harness SHALL provide the fixtures of its own domain. The suite's root configuration SHALL compose the layers' fixtures and define none of its own. A fixture that only one suite of tests uses SHALL live in that suite's directory. A test that returns the router to its snapshot after it SHALL NOT run in a module whose fixtures keep the router, after that module's first test that uses them: such a test fails at its setup and says so, instead of taking their state from the module's later tests.

#### Scenario: Fixture defined in the root configuration
- **WHEN** the suite's root configuration defines a fixture
- **THEN** the harness's structure check fails and names the fixture

#### Scenario: A test that would reset a module's router
- **WHEN** a test that resets the router after it starts while a module's fixtures keep the router
- **THEN** the test fails at its setup, naming the module, before it changes anything

## ADDED Requirements

### Requirement: Commands on the router end with their time limit
A command the harness runs on the router SHALL fail when its time limit passes, as a timeout that names the command, and SHALL leave no process of its own running on the router after that. A login session on the router that does not end within its time limit SHALL be ended and fail likewise, showing what the session printed.

#### Scenario: A command that overruns its time limit
- **WHEN** a command on the router starts a process that holds a lock, and runs past its time limit
- **THEN** the command fails as a timeout that names it, and the lock is free again

#### Scenario: A login session that does not end
- **WHEN** a login session on the router runs past its time limit
- **THEN** it fails as a timeout, with what the session printed

### Requirement: What a test sets up, it takes down
A fixture or test that changes the emulated machine or the networks around it for itself SHALL undo the change when it ends, whether it passes or fails, and also when it fails while still setting the change up.

#### Scenario: A setup that fails halfway
- **WHEN** a fixture fails while it brings up the WireGuard peer's tunnel
- **THEN** the peer's network namespace holds no tunnel afterwards, and the next fixture can bring one up

#### Scenario: A test that fails while writes are slowed
- **WHEN** a test that slows down the boot disk's writes fails before it cuts the power
- **THEN** the boot disk's writes are no longer limited afterwards
