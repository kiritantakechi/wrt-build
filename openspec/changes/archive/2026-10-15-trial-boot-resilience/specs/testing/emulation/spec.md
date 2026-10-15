# Spec Delta

## MODIFIED Requirements

### Requirement: Fault injection
The emulator SHALL provide the following means of fault injection:
- forced power cut (terminate the VM immediately);
- a hardware watchdog device;
- keystrokes sent to the serial console during boot;
- restoring the disk to its initial state between tests.

The emulator SHALL log every action of its watchdog and every shutdown it is asked for, with the time, next to the console log and for the whole session, so that a reset the console does not explain is named there.

#### Scenario: Tests are isolated
- **WHEN** a test changes the configuration, and then the next test starts
- **THEN** the next test sees the disk in the image's initial state

#### Scenario: Forced power cut
- **WHEN** a test forces a power cut on the running system and then restarts the VM
- **THEN** the VM reboots from the same disk, and content already written to disk before the power cut is still there

#### Scenario: Watchdog reset logged
- **WHEN** userspace stops feeding the watchdog and the watchdog resets the machine
- **THEN** the emulator's log names the watchdog's action, while the console shows no shutdown
