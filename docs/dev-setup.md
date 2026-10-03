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
export WRT_TESTDIR=/home/kiritan/wrt-test  # the emulator's and the tests' files, on the VM's own disk
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

The boards share one source tree and one toolchain, built without any board's CPU flags by `just toolchain-build`: the cross toolchain, and the Go and Rust host toolchains built on it (in `staging_dir/hostpkg`). `just build` brings the toolchain up to date first. A toolchain is built anew when it has no record of the flags it was built with, when the configuration's flags differ from the recorded ones, or when its C library or Rust's standard library is not the one its record names. Each board builds in directories of its own (`build_dir/target-*_<board>`, `staging_dir/target-*_<board>` and `bin/<board>`), so building one board leaves another's build as it was, and a board's build that compiles any part of the toolchain fails. The outputs go to `$WRT_WORKDIR/out/<board>/<profile>`, and `just test <board> <profile>` boots them in the emulator.

A build rebuilds only what changed. `just patch` moves the source tree to the patched commits in one checkout, so a file whose content stays the same keeps its modification time, and the build's stamps are named after the content of what they were built from and the target's compiler flags. A build with nothing changed therefore compiles nothing, and a change of `CONFIG_EXTRA_OPTIMIZATION` rebuilds every package with the new flags.

The compiler caches live beside the tree, in `$WRT_WORKDIR/compiler-cache`, one per language: `ccache/` for C and C++ (with `config/ccache.conf` linked in), `go-build/` for Go's build cache, and `sccache/` for Rust packages. The tree links them as `.ccache`, `tmp/go-build` and `.sccache`, so they outlive the tree, and every build reports what each of them served.

From a work directory of before build-acceleration, once:
- move `$WRT_WORKDIR/ccache` to `$WRT_WORKDIR/compiler-cache/ccache`, and the tree's `tmp/go-build` to `$WRT_WORKDIR/compiler-cache/go-build` (`just config` refuses a `tmp/go-build` directory);
- remove each board's own Rust, which its build's `PATH` would otherwise find first: run `staging_dir/target-*_<board>/host/lib/rustlib/uninstall.sh`, and delete `build_dir/target-*_<board>/host/rustc-*`.

Every build ends with a report of the stages that took the most time (`docs/ci.md`, Build time). Before build-acceleration, `just build r4s dev` with nothing changed took 28 minutes (2026-10-03, 23 of them in make): re-applying the patch series gave every patched file a new modification time, so the kernel was prepared (3:48) and compiled (9:47) again, and 16 packages with it, 58 stages in all.

A board's build directories take about 40 GB with the `dev` profile, 15 GB of which are the stages of Rust's host build; the sources, the toolchain and the compiler cache take about 20 GB more. The 112 GiB volume holds both boards once each built board's Rust stages are gone. They sit in `build_dir/target-*_<board>/host/rustc-*/build/<build triple>`, which nothing reads after the compiler is installed: `build/dist` and the `.built` stamp next to `build` keep later builds from compiling Rust again. When space runs short beyond that, delete a board's `build_dir/target-*_<board>` (the compiler cache keeps its next build short) or old emulator directories under `$WRT_TESTDIR/emu`.

Notes:

- Commands that need an FHS environment enter it themselves; you do not need to enter it manually. Build-related commands enter `wrt-build-fhs`; tests and `env-report` enter `wrt-test-fhs` (which contains all the tools of the build environment).
- Running these commands directly on macOS fails immediately with a hint and creates no directories.
- `just check` and `just fmt` run on any host; see `docs/conventions.md` for the rules.
- Keep the tests off the work volume: set `WRT_TESTDIR` to a directory on the VM's own disk (its default is `$WRT_WORKDIR`). The loop-mounted volume reaches its SSD through the host, and a flush there waits until the host has written everything it holds for the volume, a minute for a gigabyte. ext4 flushes with every journal commit, so a test's burst of writes stalls every writer on the volume for seconds, the emulator with its disks too, and the router then misses its network deadlines. The VM's own disk flushes the same gigabyte in half a second. `scripts/workdir-mount.sh` also has the loop device use direct I/O, so the VM does not cache the volume a second time, and small dirty-page limits in the VM (`vm.dirty_bytes` of 256 MB, `vm.dirty_background_bytes` of 64 MB, in `/etc/nixos/configuration.nix`) keep writes from piling up in it.
- Run one heavy job on the VM at a time: a build, or one board's tests.

Flakes cannot see new files that are not yet committed to the repository (by default they use only files tracked by git). Until you commit, use `nix develop path:.` instead of `nix develop`.

## 5. Serial console

Debugging the boot stage (U-Boot, A/B rollback) needs a 3.3V USB-TTL serial cable connected to the board's debug serial console, at 1500000 baud on both boards.
