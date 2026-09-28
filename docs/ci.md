# CI

两个工作流，都跑在 GitHub 托管的 ubuntu-24.04 runner 上（4 核 x86_64，单个 job 最长 6 小时）：

| 工作流 | job | 内容 | 缓存 |
|---|---|---|---|
| `check.yml` | `check` | `nix develop .#quality -c just check`，每次推送都跑，不做路径过滤 | — |
| `build.yml` | `host-toolchain` | fetch、patch，然后构建 tools 和交叉工具链 | 以 `scripts/toolchain-key.sh` 算出的键缓存 `staging_dir/{host,hostpkg,toolchain-*}` 和 `build_dir/host` |
| `build.yml` | `firmware` | 恢复工具链，然后用 ci profile 构建（全部 kmod），产出未签名的产物和 `manifest.json` | `dl/` 和 ccache |
| `build.yml` | `system-test` | 下载 firmware 的产物，`just test ci` 在模拟器里跑全部用例，再用 `spec-coverage` 核对覆盖；上传 JUnit 报告 | — |

`build.yml` 只在代码变化时运行（`openspec/`、`docs/` 和 Markdown 文件的改动不触发），而且同一分支上的新推送会取消还在运行的旧流水线。

工具链的缓存键只由这些输入决定：runner 的架构、openwrt 的 `tools/` 和 `toolchain/` 两个目录的 tree SHA、packages feed 的 `lang/golang` 和 `lang/rust` 两个目录的 tree SHA、`config/toolchain.seed`，以及构建环境的指纹 `WRT_BUILD_INPUTS`（构建包的 store 路径加上构建 profile，见 `flake.nix` 的 `buildInputsId`）。所以只改 packages 或 luci 的 SHA、或者往测试环境里加工具时，工具链缓存仍然命中。

工作流里不引用任何 secret。

## 耗时记录

| 日期 | run | 阶段 | 耗时 | 备注 |
|---|---|---|---|---|
| 2026-09-28 | 早期试跑 | tools（冷缓存） | 约 43 分钟 | |
| 2026-09-28 | 早期试跑 | 交叉工具链 GCC 15.3.0（冷缓存） | 约 35 分钟 | |
| 2026-09-28 | 36371318405 | host-toolchain job 合计 | 83 分钟 | 其中构建 tools 和工具链 79 分 49 秒，打包并保存缓存 6 秒 |
| 2026-09-28 | 36371318405 | firmware job 合计 | 103 分钟 | 其中构建 98 分 04 秒（ccache 为空、dl 缓存为空，全部 kmod） |

第一次冷缓存的完整流水线约 3 小时 6 分钟，两个构建 job 都远在 6 小时上限之内。

## 缓存用量

GitHub 仓库的缓存总额是 10 GB。

| 日期 | 工具链压缩包 | ccache | dl | Nix 安装器 | 合计 |
|---|---|---|---|---|---|
| 2026-09-28 | 776 MiB | 1243 MiB | 1456 MiB | 45 MiB | 3521 MiB |

每次运行都会新存一份 ccache（键带 run ID），旧的由 GitHub 按最近最少使用淘汰。按现在的用量，工具链留在缓存里即可，不需要改存为 Release 附件（design D11 的退路）。
