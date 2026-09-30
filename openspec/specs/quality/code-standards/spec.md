# quality/code-standards Specification

## Purpose
Define uniform, enforced standards for all code in the repository: consistent formatting, passing static checks, a common script structure, and symmetric naming, checked by one command and enforced in CI.

## Requirements

### Requirement: Uniform formatting
Code in the repository SHALL use fixed formatters and be committed in formatted form:
- shell scripts use shfmt (POSIX dialect);
- Nix uses nixfmt;
- Python uses ruff format;
- all text files follow `.editorconfig`.

Any difference from the formatter output MUST fail the check.

#### Scenario: Unformatted code committed
- **WHEN** the indentation of a shell script differs from shfmt's output
- **THEN** the format check fails and shows the diff that needs to be applied

### Requirement: All static checks pass
Code in the repository SHALL pass all of the following static checks:
- shellcheck (including the optional checks enabled in the repository configuration);
- ruff check (all rules enabled, excluding only a few documented ones);
- ty;
- actionlint;
- forbidden-pattern checks.

#### Scenario: New static check warning
- **WHEN** a script gains a new shellcheck warning
- **THEN** the check fails and names the file, line number, and rule code

### Requirement: Common script skeleton
Every shell script SHALL be organized in the same order:
1. a one-line description of what the script does, plus its usage;
2. enable strict mode;
3. source the common function library;
4. argument parsing;
5. guards (host, build directory, build environment);
6. main logic.

#### Scenario: New script added
- **WHEN** a new script is added
- **THEN** its opening structure matches the existing scripts, and the check reports any missing part

### Requirement: Symmetric naming
- Operations that have an inverse SHALL come in pairs with symmetric names, for example mount/unmount, pack/unpack, up/down.
- just recipe names SHALL match the corresponding script names.
- Scripts that act on a specific object SHALL be named "object-verb"; pipeline stage scripts are named with a single verb.
- Environment variables SHALL all use the `WRT_` prefix.

#### Scenario: Unpaired operation
- **WHEN** the repository has a command that mounts the build directory
- **THEN** a matching unmount command also exists, and the two are named symmetrically

### Requirement: One command to check and format
`just check` SHALL run all formatters and static checks in check-only mode, without modifying anything; `just fmt` SHALL format all files. Both SHALL run on macOS and Linux. CI SHALL run `just check` on every push and fail if it does not pass.

#### Scenario: Format then check
- **WHEN** `just fmt` runs first, then `just check`
- **THEN** all format-related checks in `just check` pass
