# CI

工作流是 `.github/workflows/build.yml`，分成两个 job，每个都必须在 GitHub 托管 runner 的 6 小时上限内完成：

| job | 内容 | 缓存 |
|---|---|---|
| `host-toolchain` | fetch、patch，然后构建 tools 和交叉工具链 | 以 `scripts/toolchain-key.sh` 算出的键缓存 `staging_dir/{host,hostpkg,toolchain-*}` 和 `build_dir/host` |
| `firmware` | 恢复工具链，然后用 ci profile 构建（全部 kmod），产出未签名的产物和 `manifest.json` | `dl/` 和 ccache |

工具链的缓存键只由这些输入决定：runner 的架构、openwrt 的 `tools/` 和 `toolchain/` 两个目录的 tree SHA、packages feed 的 `lang/golang` 和 `lang/rust` 两个目录的 tree SHA、`config/toolchain.seed`、`flake.lock`。所以只改 packages 或 luci 的 SHA 时，工具链缓存仍然命中。

工作流里不引用任何 secret。

## 耗时记录

| 日期 | 环境 | 阶段 | 耗时 | 备注 |
|---|---|---|---|---|
| | | | | |

## 缓存用量

| 日期 | 工具链压缩包 | ccache | dl | 合计 |
|---|---|---|---|---|
| | | | | |
