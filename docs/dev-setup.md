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

# in the VM (creates the filesystem once, then mounts it):
orb -m nixos -u root /Users/kiritan/Projects/wrt-build/scripts/workdir-mount.sh --format
```

After each VM restart, mount it again (the script can be run repeatedly and never reformats):

```sh
orb -m nixos -u root /Users/kiritan/Projects/wrt-build/scripts/workdir-mount.sh
```

By default, the image file is `/mnt/mac/Volumes/SSD/wrt-work.ext4`, the mount point is `/mnt/wrt`, and the mount point is owned by user `kiritan`.

Notes:

- Do not unplug the SSD or let the Mac sleep while it is mounted, or the ext4 file system may be corrupted.
- Before unplugging the drive, run `orb -m nixos -u root /Users/kiritan/Projects/wrt-build/scripts/workdir-unmount.sh` in the VM.
- The current SSD's measured sequential write speed is about 75 MB/s (2026-09-28, `dd` writing 2 GiB with `fdatasync`). This is the upper bound on local build I/O; the timings of the first full build are recorded in `docs/ci.md`.

## 3. Build

In the VM, run:

```sh
cd /Users/kiritan/Projects/wrt-build
export NIX_CONFIG="experimental-features = nix-command flakes"
export WRT_WORKDIR=/mnt/wrt
nix develop -c just build dev      # fetch + patch + config + build, local profile
```

Each step can also be run on its own:

```sh
just fetch
just patch
just config dev
just env-report
```

Notes:

- Commands that need an FHS environment enter it themselves; you do not need to enter it manually. Build-related commands enter `wrt-build-fhs`; tests and `env-report` enter `wrt-test-fhs` (which contains all the tools of the build environment).
- Running these commands directly on macOS fails immediately with a hint and creates no directories.
- `just check` and `just fmt` run on any host; see `docs/conventions.md` for the rules.

Flakes cannot see new files that are not yet committed to the repository (by default they use only files tracked by git). Until you commit, use `nix develop path:.` instead of `nix develop`.

## 4. Serial console

Debugging the boot stage (U-Boot, A/B rollback) needs a 3.3V USB-TTL serial cable connected to the R4S debug serial console, at 1500000 baud.
