# upstream.lock

`upstream.lock` pins the three upstream repositories the build uses. Each line is one repository, with four whitespace-separated columns:

```
<name> <git-url> <commit-sha> <commit-epoch>
```

| Field | Meaning |
|---|---|
| `name` | `openwrt` is the main source tree; the others are feeds, and the name is both `feeds/<name>` and `patches/<name>/` |
| `git-url` | Where the source is fetched from (GitHub mirror) |
| `commit-sha` | The full 40-character commit SHA; the build checks out only this commit |
| `commit-epoch` | The commit time of this commit (Unix seconds); the value on the `openwrt` line is the build's `SOURCE_DATE_EPOCH` |

## How each part uses this file

- **`just fetch`**:
  - runs `git fetch --depth 1 origin <sha>` for each repository, then checks out that commit;
  - writes every line of the generated `feeds.conf` in the form `src-git <name> <url>^<sha>`, plus one `src-link wrtbuild` line for the project's own feed;
  - writes the openwrt `commit-epoch` to `version.date` in the source tree, which `scripts/get_source_date_epoch.sh` reads first.
- **`just patch`**:
  - first resets every repository to its commit in the lock;
  - then runs `git am` on `patches/<name>/*.patch` in file-name order, with a fixed committer identity and date.
  - As a result, the same lock and patches yield the same source tree SHA, no matter when or on which machine they are applied.

Why feeds are not fetched by `scripts/feeds update`: if a feed directory already exists and the config says `^sha`, upstream `scripts/feeds update` skips it without updating anything. So when a SHA in the lock changes, the local feed would not follow. That is why `fetch` checks out each feed itself and afterwards only runs `feeds update -i` to rebuild the index.

## Updating

`upstream.lock` itself is the record of what is pinned. It changes through the weekly bump (`.github/workflows/bump.yml`, `scripts/upstream-bump.sh`): every Monday the heads of the three default branches are compared with the lock, and when any moved, a pull request from `bump/<date>` updates the SHA and commit time of each and lists the commits in between. It merges once its candidate has passed the upgrade drill (docs/release-flow.md). To bump by hand, run the same script and build before committing:

```sh
just upstream-bump /tmp/pull-request.md
```
