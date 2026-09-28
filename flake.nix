{
  description = "wrt-build: reproducible OpenWrt build environment for NanoPi R4S";

  inputs = {
    # Stable base for the build environment: the host tools behind the cached toolchain.
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-25.11";
    # Newest uv and emulator tools (qemu, dtc, u-boot-tools); never part of the build.
    nixpkgs-unstable.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
  };

  outputs =
    { nixpkgs, nixpkgs-unstable, ... }:
    let
      linuxSystems = [
        "x86_64-linux"
        "aarch64-linux"
      ];
      darwinSystems = [
        "aarch64-darwin"
        "x86_64-darwin"
      ];
      forSystems =
        systems: f:
        nixpkgs.lib.genAttrs systems (
          system: f nixpkgs.legacyPackages.${system} nixpkgs-unstable.legacyPackages.${system}
        );

      # Orchestration and code standards (just check / just fmt), on every host.
      qualityTools =
        pkgs: unstable: with pkgs; [
          just
          git
          jq
          shellcheck
          shfmt
          nixfmt
          actionlint
          editorconfig-checker
          gitleaks
          unstable.uv
        ];

      # Everything OpenWrt's include/prereq-build.mk checks for, plus what U-Boot,
      # the kernel (BTF via the in-tree pahole) and the BPF host toolchain need.
      buildPackages =
        pkgs:
        let
          # Host LLVM for BPF objects (CONFIG_BPF_TOOLCHAIN_HOST). Unwrapped clang:
          # the Nix cc-wrapper would inject hardening flags invalid for -target bpf.
          llvm = pkgs.llvmPackages_21;
          # Host packages built with LTO into static libraries (package/system/apk
          # uses meson -Db_lto=true) need an LTO-aware archiver. Distribution
          # binutils load GCC's LTO plugin automatically; the Nix binutils does
          # not, and the gcc wrapper does not ship gcc-ar/gcc-nm/gcc-ranlib, so
          # expose the unwrapped ones without shadowing the wrapped gcc.
          gccLtoTools =
            map (tool: pkgs.writeShellScriptBin "gcc-${tool}" ''exec ${pkgs.gcc.cc}/bin/gcc-${tool} "$@"'')
              [
                "ar"
                "nm"
                "ranlib"
              ];
        in
        with pkgs;
        [
          bash
          coreutils
          findutils
          diffutils
          gnugrep
          gnused
          gawk
          gnutar
          gnumake
          gnupatch
          util-linux
          which
          file
          time
          bc
          cpio
          rsync
          wget
          curl
          git
          unzip
          zip
          gzip
          bzip2
          xz
          zstd
          perl
          (python3.withPackages (ps: [
            ps.setuptools
            ps.pyelftools
          ]))
          gcc
          # The gcc wrapper finds libc headers through -isystem, but configure
          # scripts that search the filesystem (CMake find_path for iconv.h in
          # tools/cmake) need them in /usr/include.
          glibc.dev
          binutils
          pkg-config
          bison
          flex
          gettext
          swig
          quilt
          ncurses
          ncurses.dev
          zlib
          zlib.dev
          openssl
          openssl.dev
          just
          jq
          llvm.clang-unwrapped
          llvm.llvm
        ]
        ++ gccLtoTools;

      buildProfile = ''
        # OpenWrt host tools do not build cleanly with the Nix hardening flags.
        export NIX_HARDENING_ENABLE=
        # LTO-aware archiver for host builds (see gccLtoTools); target builds
        # set their own AR/NM/RANLIB from the cross toolchain.
        export AR=gcc-ar NM=gcc-nm RANLIB=gcc-ranlib
        # bubblewrap runs us in a user namespace where chown to an unmapped
        # uid fails with EINVAL. fakeroot tries the real chown first and only
        # ignores EPERM, so rootfs installation (apk under fakeroot) failed
        # with "failed to preserve owner". Make fakeroot skip the real chown.
        export FAKEROOTDONTTRYCHOWN=1
      '';

      # The emulator: QEMU for aarch64 guests only, without the display, audio and
      # storage backends the tests never use, and with the fixes in patches/qemu
      # (sdhci-pci lost its BAR on loadvm, which the tests do between every two).
      emulatorQemu =
        unstable:
        (unstable.qemu.override {
          minimal = true;
          enableTools = true;
          # option ROMs, which PCI devices such as virtio-net-pci load
          enableBlobs = true;
          hostCpuTargets = [ "aarch64-softmmu" ];
        }).overrideAttrs
          (old: {
            patches = (old.patches or [ ]) ++ nixpkgs.lib.filesystem.listFilesRecursive ./patches/qemu;
          });

      # System tests: emulator, image extraction, network sandbox peers, and the
      # shared libraries that uv-managed Python and manylinux wheels expect in an
      # FHS layout. Later changes append their peers (PPPoE server, registry, ...).
      testPackages =
        pkgs: unstable:
        [
          unstable.uv
          (emulatorQemu unstable)
          unstable.dtc
          unstable.ubootTools
        ]
        ++ (with pkgs; [
          stdenv.cc.cc.lib
          # boot partition reading (debugfs) and the network sandbox
          e2fsprogs
          iproute2
          iputils
          dnsmasq
          # LAN clients take their address over DHCP; only this applet of
          # busybox, which would otherwise shadow coreutils in the FHS.
          (writeShellScriptBin "udhcpc" ''exec ${busybox}/bin/busybox udhcpc "$@"'')
        ])
        ++ testSsh pkgs;

      # ssh and scp with a fixed configuration instead of the host's: the router's
      # host key changes with every fresh image, and inside the test sandbox the
      # host's configuration files may belong to an unmapped user, which OpenSSH
      # refuses to read.
      testSsh =
        pkgs:
        let
          config = pkgs.writeText "wrt-test-ssh-config" ''
            Host *
              StrictHostKeyChecking no
              UserKnownHostsFile /dev/null
              LogLevel ERROR
          '';
        in
        map (tool: pkgs.writeShellScriptBin tool ''exec ${pkgs.openssh}/bin/${tool} -F ${config} "$@"'') [
          "ssh"
          "scp"
        ];

      # Fingerprint of everything that shapes host-built tools and the cross
      # toolchain: the build package set and the build profile. The toolchain
      # cache key uses it, so editing test or quality tooling never invalidates
      # the cached toolchain.
      buildInputsId =
        pkgs:
        pkgs.writeText "wrt-build-inputs" (
          nixpkgs.lib.concatLines (map toString (buildPackages pkgs)) + buildProfile
        );

      fhsFor =
        pkgs:
        {
          name,
          kind,
          packages,
        }:
        pkgs.buildFHSEnv {
          inherit name;
          targetPkgs = _: packages;
          profile = buildProfile + ''
            export WRT_BUILD_INPUTS=${buildInputsId pkgs}
            export WRT_FHS=${kind}
          '';
          runScript = "bash";
        };

      # The test environment is a superset of the build environment, so scripts
      # that only need the build environment also run inside the test one.
      environmentsFor = pkgs: unstable: {
        wrt-build-fhs = fhsFor pkgs {
          name = "wrt-build-fhs";
          kind = "build";
          packages = buildPackages pkgs;
        };
        wrt-test-fhs = fhsFor pkgs {
          name = "wrt-test-fhs";
          kind = "test";
          packages = buildPackages pkgs ++ testPackages pkgs unstable;
        };
      };
    in
    {
      packages = forSystems linuxSystems (
        pkgs: unstable:
        environmentsFor pkgs unstable
        // {
          default = (environmentsFor pkgs unstable).wrt-build-fhs;
        }
      );

      # quality: code standards only (just check / just fmt), identical on every host.
      # build:    quality plus, on Linux, the build environment; CI's build jobs, which
      #           then never build the emulator.
      # default:  quality plus, on Linux, the build and test environments.
      devShells =
        forSystems linuxSystems (
          pkgs: unstable:
          let
            environments = environmentsFor pkgs unstable;
          in
          rec {
            quality = pkgs.mkShellNoCC { packages = qualityTools pkgs unstable; };
            build = pkgs.mkShellNoCC {
              inputsFrom = [ quality ];
              packages = [ environments.wrt-build-fhs ];
            };
            default = pkgs.mkShellNoCC {
              inputsFrom = [ quality ];
              packages = builtins.attrValues environments;
            };
          }
        )
        // forSystems darwinSystems (
          pkgs: unstable: rec {
            # macOS runs the code standards and orchestration, never a build or a test.
            quality = pkgs.mkShellNoCC { packages = qualityTools pkgs unstable; };
            default = quality;
          }
        );

      formatter = forSystems (linuxSystems ++ darwinSystems) (pkgs: _: pkgs.nixfmt);
    };
}
