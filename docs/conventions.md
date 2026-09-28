# 代码规范

所有规则都由 `just check` 强制执行，CI 里的 `check` 工作流也跑同一条命令，不过就失败。`just fmt` 负责格式化，它和 `just check` 里的格式检查一一对应。两条命令在 macOS 和 Linux 上都能运行，所需工具由 `nix develop .#quality` 提供；在 NixOS 上，它们会自动进入 `wrt-test-fhs` 运行，因为 uv 安装的 Python 工具是通用 Linux 二进制。

## 规则与检查

下表“检查名”一列就是 `scripts/check.sh` 输出的名字，两边一一对应。

| 规则 | 检查名 | 格式化 |
|---|---|---|
| shell 脚本格式：POSIX 方言、tab 缩进、case 分支缩进（`.editorconfig`） | `shfmt` | `shfmt -w` |
| shell 脚本静态检查：`shell=sh`，除 `require-double-brackets` 外的全部可选检查（`.shellcheckrc`） | `shellcheck` | — |
| Nix 格式 | `nixfmt` | `nixfmt` |
| GitHub Actions 工作流，包括其中 `run:` 块的 shellcheck | `actionlint` | — |
| 全部文本：UTF-8、LF、文件末尾换行、没有行尾空格、缩进风格（`.editorconfig`） | `editorconfig-checker` | — |
| 历史和待提交文件里都不能有密钥 | `gitleaks` | — |
| 构建步骤不能执行或应用下载来的内容，不能用 `sed -i` 就地修改上游文件 | `forbidden-patterns` | — |
| 脚本骨架，以及脚本和 just 命令按名字一一对应 | `skeleton` | — |
| Python 格式（`tests/`） | `ruff-format` | `ruff format` |
| Python 静态检查：`select = ["ALL"]`，排除项写在 `tests/ruff.toml` 里并注明原因 | `ruff-check` | — |
| Python 类型检查：全部规则按 error 处理（`tests/ty.toml`） | `ty` | — |
| 规格与用例的对应结构：标记指向存在的场景、一个场景只有一个用例、目录规则（设计 D13） | `spec-coverage` | — |

不受这些规则约束的文件：`patches/` 和 `docs/upstream/`（保持上游补丁的原样），`.claude/`（工具生成），以及锁文件。OpenWrt 包的 `Makefile` 按上游惯例混用 tab 和两个空格，所以不检查缩进风格。

## 脚本骨架

`scripts/` 下的每个脚本都按这个顺序组织：

```sh
#!/bin/sh
# <name>: <one-line purpose>.
# Usage: scripts/<name>.sh [args]
# (optional further comment lines)
set -eu
# shellcheck source=scripts/lib.sh
. "$(dirname -- "$0")/lib.sh"

<argument parsing>
require_linux; require_workdir; ensure_fhs build "$@"   # only the guards it needs
<main>
```

- `<name>` 与文件名一致；第二行以句号结尾。
- 脚本必须可执行。`lib.sh` 是被引用的库，不可执行，开头两行是 `# lib: ...` 和 `# Usage: ...`。
- 命令替换的返回值不能被吞掉（shellcheck 的 `check-extra-masked-returns`）：先赋值给变量，再使用。
- POSIX sh 没有局部变量。函数内部用到的变量名不要和调用者冲突；需要隔离时放进子 shell。

## 命名

- **流水线阶段**用单独的动词：`fetch`、`patch`、`config`、`build`、`test`、`check`、`fmt`。
- **针对具体对象的操作**用“对象-动词”：`env-report`、`image-audit`、`runner-prepare`、`toolchain-key`、`toolchain-build`、`toolchain-pack`、`toolchain-unpack`、`workdir-mount`、`workdir-unmount`。
- **成对的操作**名字对称：`mount`/`unmount`、`pack`/`unpack`、`check`/`fmt`。
- **每个脚本都有同名的 just 命令**，反过来每个 just 命令（`default` 除外）都有同名脚本，由 `skeleton` 检查。just 命令按 `build`、`image`、`test`、`quality`、`ci`、`workdir` 分组。
- **环境变量**统一用 `WRT_` 前缀。
