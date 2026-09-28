# upstream.lock

`upstream.lock` 固定了构建所用的三个上游仓库。每行对应一个仓库，四列之间用空白分隔：

```
<name> <git-url> <commit-sha> <commit-epoch>
```

| 字段 | 含义 |
|---|---|
| `name` | `openwrt` 是主源码树，其余都是 feed：名字就是 `feeds/<name>`，也是 `patches/<name>/` |
| `git-url` | 获取源码的地址（GitHub 镜像） |
| `commit-sha` | 完整的 40 位提交 SHA，构建只会检出这个提交 |
| `commit-epoch` | 这个提交的提交时间（Unix 秒）；`openwrt` 这一行的值就是构建的 `SOURCE_DATE_EPOCH` |

## 各部分怎么使用这个文件

- **`just fetch`**：
  - 对每个仓库执行 `git fetch --depth 1 origin <sha>`，然后切到这个提交；
  - 生成的 `feeds.conf` 每行都写成 `src-git <name> <url>^<sha>` 这种形式，另外再加一行自有 feed 的 `src-link wrtbuild`；
  - 把 openwrt 的 `commit-epoch` 写进源码树里的 `version.date`，`scripts/get_source_date_epoch.sh` 会优先读取这个文件。
- **`just patch`**：
  - 先把所有仓库重置回 lock 里的提交；
  - 再按文件名顺序对 `patches/<name>/*.patch` 执行 `git am`，并固定提交者的身份和时间。
  - 因此同一份 lock 和补丁，不管什么时候、在哪台机器上应用，得到的源码树 SHA 都相同。

为什么 feed 不交给 `scripts/feeds update` 去获取：如果 feed 目录已经存在，并且配置里写的是 `^sha`，上游的 `scripts/feeds update` 会直接跳过，不做任何更新。这样一来，lock 里的 SHA 变了，本地的 feed 也不会跟着变。所以 `fetch` 自己检出每个 feed，之后只执行 `feeds update -i` 重建索引。

## 当前固定的版本

| 仓库 | SHA | 提交时间 |
|---|---|---|
| openwrt | `101929399c12644ac8c3fe9b11b83c93fe9ee755` | 2026-09-27 22:07:24 +0200 |
| packages | `a637759c3aae15f112bff2f3a845c74ee331b978` | 2026-09-27 22:10:12 +0200 |
| luci | `05dc750ddb5e5c4aacf4ae0635bbf8b14a494909` | 2026-09-27 16:42:14 UTC |

luci 取的是 openwrt 那个提交之前，luci master 上的最后一个提交。

## 更新

更新只通过每周的 bump PR 进行（见 `r4s-release-pipeline`）。不要手动改 SHA 却不跑完整构建。改动 SHA 时，`commit-epoch` 也要一起更新：

```sh
git -C <checkout> log -1 --format=%ct <sha>
```
