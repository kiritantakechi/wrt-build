## MODIFIED Requirements

### Requirement: Weekly automated PR
The bot SHALL check the main branches of the repositories in `upstream.lock` (openwrt, packages, luci, and daeuniverse's OpenWrt feed) once a week. When there are updates, it SHALL open a PR that updates `upstream.lock`, with the old and new SHAs and a summary of the upstream commits in the PR description. When none of the repositories has updates, it MUST NOT open a PR. It SHALL start the bump branch's check and build before it opens the PR, so that a PR that cannot be opened leaves them running and fails the bot's run naming why. A bump run again on a day whose branch exists MUST NOT change the branch, and SHALL open the PR that branch still lacks.

#### Scenario: Upstream has updates
- **WHEN** the weekly check runs and upstream has new commits
- **THEN** a PR that updates `upstream.lock` appears, with the old and new SHAs and a summary of the upstream commits in its description

#### Scenario: Upstream has no updates
- **WHEN** the weekly check runs but none of the repositories has new commits
- **THEN** no PR is opened

#### Scenario: The PR cannot be opened
- **WHEN** the bot pushes a bump branch but may not open PRs
- **THEN** the branch's check and build run, and the bot's run fails, saying that it may not open the PR

#### Scenario: Bump run again
- **WHEN** the bot runs again on a day whose bump branch exists, with commits on it the bot did not make
- **THEN** the branch keeps its commits, and the bot opens its PR if it has none
