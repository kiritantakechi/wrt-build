# Local development environment

Builds run only on Linux: BTF needs pahole, and mold does not support macOS hosts. Locally, builds run in an OrbStack NixOS virtual machine, with the build directory on an external SSD. CI uses the same `flake.nix`, so host tool versions are identical in both places.

## 1. Virtual machine

You need an OrbStack NixOS virtual machine named `nixos` (currently NixOS 25.11, arm64):

```sh
orb create nixos nixos      # skip if it already exists
```

The macOS `/Users` and `/Volumes` directories appear in the VM at the same paths, and external drives are at `/mnt/mac/Volumes/<name>`. So this repository has the same path in the VM as on macOS.

Flakes are not enabled in the VM by default. You can enable them temporarily by setting an environment variable before each command:

```sh
export NIX_CONFIG="experimental-features = nix-command flakes"
```

You can also put `experimental-features = nix-command flakes` in `~/.config/nix/nix.conf` inside the VM, so you do not have to set it every time.

## 2. Build directory (an ext4 image file on the external SSD)

An OpenWrt build produces a large number of small files and requires a case-sensitive file system. So the build directory does not live directly on a macOS volume; instead, an ext4 image file sits on the external SSD and is loop-mounted inside the VM:

- all small-file reads and writes land on native Linux ext4;
- virtiofs only carries large block reads and writes of the image file;
- the macOS system disk is not used.

One-time setup:

```sh
# on macOS: stop Spotlight from indexing the volume, then allocate the image.
# HFS+ has no sparse files, so mkfile writes all 112 GiB (takes a while).
touch /Volumes/SSD/.metadata_never_index
mkfile -n 112g /Volumes/SSD/wrt-work.ext4

# in the VM (creates the filesystem once, owned by kiritan, then mounts it):
orb -m nixos -u root /Users/kiritan/Projects/wrt-build/scripts/workdir-mount.sh --format --owner kiritan
```

After each VM restart, mount it again (the script can be run repeatedly and never reformats):

```sh
orb -m nixos -u root /Users/kiritan/Projects/wrt-build/scripts/workdir-mount.sh
```

By default, the image file is `/mnt/mac/Volumes/SSD/wrt-work.ext4` and the mount point is `/mnt/wrt`. Its owner is set once, when the filesystem is created, and kept in it: as root, the VM sees the Mac's files as root's own, so the owner has to be named then.

Notes:

- Do not unplug the SSD or let the Mac sleep while it is mounted, or the ext4 file system may be corrupted.
- Before unplugging the drive, run `orb -m nixos -u root /Users/kiritan/Projects/wrt-build/scripts/workdir-unmount.sh` in the VM.
- The current SSD's measured sequential write speed is about 75 MB/s (2026-09-28, `dd` writing 2 GiB with `fdatasync`). This is the upper bound on local build I/O; the timings of the first full build are recorded in `docs/ci.md`.

## 3. PPP for the test sandbox

The emulated ISP runs pppd inside the test sandbox, which needs the `ppp_generic` and `ppp_async` modules and a `/dev/ppp` open to regular users; the WireGuard peer needs the `wireguard` module. After each VM restart, run (the OrbStack NixOS VM has no `modprobe` on its path, so kmod comes from nixpkgs):

```sh
orb -m nixos -u root sh -c 'NIX_CONFIG="experimental-features = nix-command flakes" nix shell nixpkgs#kmod -c /Users/kiritan/Projects/wrt-build/scripts/sandbox-prepare.sh'
```

`just env-report` fails with this hint when PPP is not ready. CI runs the same script from `runner-prepare.sh`.

## 4. Build

Every build is for one board, named by its description under `boards/`: `r4s` (NanoPi R4S) or `r6s` (NanoPi R6S). In the VM, run:

```sh
cd /Users/kiritan/Projects/wrt-build
export NIX_CONFIG="experimental-features = nix-command flakes"
export WRT_WORKDIR=/mnt/wrt
nix develop -c just build r4s dev  # check the board, fetch, patch, toolchain, config, build
```

Each step can also be run on its own:

```sh
just boards                  # the supported boards: ["r4s","r6s"]
just fetch
just patch
just toolchain-build dev     # the cross toolchain every board shares
just config r6s dev
just env-report
```

The boards share one source tree and one cross toolchain, built without any board's CPU flags. `just build` brings the toolchain up to date first; a toolchain without the record of the flags it was built with, such as one from before the board model, is built anew. Each board builds in directories of its own (`build_dir/target-*_<board>`, `staging_dir/target-*_<board>` and `bin/<board>`), so building one board leaves another's build as it was. Those directories also hold the host builds that packages bring, Rust's compiler among them, so each board's first build takes much longer than its later ones. The outputs go to `$WRT_WORKDIR/out/<board>/<profile>`, and `just test <board> <profile>` boots them in the emulator.

A board's build directories take about 40 GB with the `dev` profile, 15 GB of which are the stages of Rust's host build; the sources, the toolchain and the compiler cache take about 20 GB more. The 112 GiB volume holds both boards once each built board's Rust stages are gone. They sit in `build_dir/target-*_<board>/host/rustc-*/build/<build triple>`, which nothing reads after the compiler is installed: `build/dist` and the `.built` stamp next to `build` keep later builds from compiling Rust again. When space runs short beyond that, delete a board's `build_dir/target-*_<board>` (the compiler cache keeps its next build short) or old emulator directories under `$WRT_WORKDIR/emu`.

Notes:

- Commands that need an FHS environment enter it themselves; you do not need to enter it manually. Build-related commands enter `wrt-build-fhs`; tests and `env-report` enter `wrt-test-fhs` (which contains all the tools of the build environment).
- Running these commands directly on macOS fails immediately with a hint and creates no directories.
- `just check` and `just fmt` run on any host; see `docs/conventions.md` for the rules.
- Run one heavy job on the VM at a time: a build, or one board's tests. The emulator's disks live on the loop-mounted volume, which reaches the disk through the host. When a few gigabytes of writes pile up, the volume stalls every writer for seconds while it catches up, the emulator with them, and the router then misses its network deadlines. A smaller dirty-page limit in the VM (`vm.dirty_bytes`, `vm.dirty_background_bytes`) makes these stalls shorter.

Flakes cannot see new files that are not yet committed to the repository (by default they use only files tracked by git). Until you commit, use `nix develop path:.` instead of `nix develop`.

## 5. Serial console

Debugging the boot stage (U-Boot, A/B rollback) needs a 3.3V USB-TTL serial cable connected to the board's debug serial console, at 1500000 baud on both boards.
