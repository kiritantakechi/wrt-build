# 本机开发环境

构建只能在 Linux 上进行：BTF 需要 pahole，mold 也不支持 macOS 宿主机。本机的做法是在 OrbStack 的 NixOS 虚拟机里构建，构建目录放在外接 SSD 上。CI 使用同一份 `flake.nix`，所以两边的宿主机工具版本完全一致。

## 1. 虚拟机

需要一台 OrbStack 的 NixOS 虚拟机，名字叫 `nixos`（当前是 NixOS 25.11，arm64）：

```sh
orb create nixos nixos      # skip if it already exists
```

macOS 的 `/Users` 和 `/Volumes` 在虚拟机里会以同样的路径出现，其中外接盘在 `/mnt/mac/Volumes/<name>`。所以本仓库在虚拟机里的路径和 macOS 上一样。

虚拟机默认没有打开 flakes。可以在每条命令前加一个环境变量来临时打开：

```sh
export NIX_CONFIG="experimental-features = nix-command flakes"
```

也可以把 `experimental-features = nix-command flakes` 写进虚拟机里的 `~/.config/nix/nix.conf`，这样就不用每次都加了。

## 2. 构建目录（外接 SSD 上的 ext4 镜像文件）

OpenWrt 的构建会产生大量小文件，而且要求文件系统区分大小写。所以构建目录不直接放在 macOS 卷上，而是在外接 SSD 上放一个 ext4 镜像文件，在虚拟机里 loop 挂载使用：

- 小文件的读写都落在 Linux 原生的 ext4 上；
- virtiofs 只承担镜像文件的大块读写；
- macOS 的系统盘不会被占用。

一次性准备工作：

```sh
# on macOS: stop Spotlight from indexing the volume, then allocate the image.
# HFS+ has no sparse files, so mkfile writes all 112 GiB (takes a while).
touch /Volumes/SSD/.metadata_never_index
mkfile -n 112g /Volumes/SSD/wrt-work.ext4

# in the VM (creates the filesystem once, then mounts it):
orb -m nixos -u root /Users/kiritan/Projects/wrt-build/scripts/workdir-mount.sh --format
```

以后每次虚拟机重启后，重新挂载一次即可（这个脚本可以重复执行，不会重复格式化）：

```sh
orb -m nixos -u root /Users/kiritan/Projects/wrt-build/scripts/workdir-mount.sh
```

默认情况下，镜像文件是 `/mnt/mac/Volumes/SSD/wrt-work.ext4`，挂载点是 `/mnt/wrt`，挂载点归属用户 `kiritan`。

注意事项：

- 挂载期间不要拔掉 SSD，也不要让 Mac 进入睡眠，否则 ext4 可能损坏。
- 拔盘之前先在虚拟机里执行 `orb -m nixos -u root /Users/kiritan/Projects/wrt-build/scripts/workdir-unmount.sh`。
- 当前这块 SSD 的实测顺序写入约 75 MB/s（2026-09-28，`dd` 写 2 GiB 并 `fdatasync`）。它是本机构建 I/O 的上限；首次完整构建的耗时记录在 `docs/ci.md`。

## 3. 构建

在虚拟机里执行：

```sh
cd /Users/kiritan/Projects/wrt-build
export NIX_CONFIG="experimental-features = nix-command flakes"
export WRT_WORKDIR=/mnt/wrt
nix develop -c just build dev      # fetch + patch + config + build, local profile
```

每一步也可以单独执行：

```sh
just fetch
just patch
just config dev
just env-report
```

说明：

- 需要 FHS 环境的命令会自己进入对应的环境，不需要手动进入：构建相关的命令进入 `wrt-build-fhs`，测试和 `env-report` 进入 `wrt-test-fhs`（它包含构建环境的全部工具）。
- 在 macOS 上直接运行这些命令会立刻失败并给出提示，也不会创建任何目录。
- `just check` 和 `just fmt` 在任何宿主机上都可以运行，规则见 `docs/conventions.md`。

仓库里还没有提交的新文件，flakes 是看不到的（它默认只使用已被 git 跟踪的文件）。在提交之前，要用 `nix develop path:.` 代替 `nix develop`。

## 4. 串口

调试引导阶段（U-Boot、A/B 回滚）需要一根 3.3V 的 USB-TTL 串口线，接到 R4S 的调试串口上，波特率 1500000。
