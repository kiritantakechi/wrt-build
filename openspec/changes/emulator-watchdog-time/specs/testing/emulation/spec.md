# Spec Delta

## ADDED Requirements

### Requirement: Only the guest trips the watchdog
The emulated watchdog SHALL reset the machine only when the guest stops feeding it. The emulator SHALL run the board's cores so that load on the host, which a device never has, cannot keep the guest from running for the watchdog's timeout, also on a host with fewer cores than the board.

#### Scenario: Busy guest on fewer host cores
- **WHEN** the emulator has fewer host cores than the board has cores, and the guest is kept busy for longer than the watchdog's timeout
- **THEN** the emulator logs no watchdog action, and the guest runs on without a reboot
