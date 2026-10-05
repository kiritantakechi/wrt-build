# Spec Delta

## MODIFIED Requirements

### Requirement: Common script skeleton
Every shell script SHALL be organized in the same order:
1. a one-line description of what the script does, plus its usage;
2. enable strict mode;
3. load the library modules it uses, by name;
4. argument parsing;
5. guards (host, build directory, build environment);
6. main logic.

#### Scenario: New script added
- **WHEN** a new script is added
- **THEN** its opening structure matches the existing scripts, and the check reports any missing part

## ADDED Requirements

### Requirement: Scripts load what they call
The shell scripts' shared functions SHALL be grouped by domain into library modules. A script SHALL load, by name, every module whose functions it calls, and a module SHALL load the modules it depends on itself. Shared functions SHALL receive the build tree they work on as an argument rather than through a global variable.

#### Scenario: Script calls a function it does not load
- **WHEN** a script calls a library function that none of the modules it loads, directly or through their own dependencies, provides
- **THEN** `just check` fails and names the script and the function

### Requirement: Layered test harness
The test harness's modules SHALL form four layers, from the bottom up: the repository and the build's outputs as data, the sandbox network, the emulated device, and the services on it. A module SHALL import only from its own layer and the layers below it, type-only imports included.

#### Scenario: Harness module imports from a higher layer
- **WHEN** a module of the harness imports from a layer above its own
- **THEN** `just check` fails and names the module and the import

### Requirement: No dead code in the host-side code
Every function of the shell library SHALL be called by a script, another library module or a test, and every module of the test harness SHALL be imported by the harness or a test. Code that a change replaces SHALL be removed by that change, without an alias for its old name.

#### Scenario: Library function that nothing calls
- **WHEN** a library module defines a function that no script, other module or test calls
- **THEN** `just check` fails and names the module and the function

#### Scenario: Harness module that nothing imports
- **WHEN** a module of the test harness is imported neither by the harness nor by a test, nor named as an entry point
- **THEN** `just check` fails and names the module
