{
  description = "wrt-build: reproducible OpenWrt build environment for NanoPi R4S";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-25.11";

  outputs =
    { self, nixpkgs }:
    let
      linuxSystems = [
        "x86_64-linux"
        "aarch64-linux"
      ];
      darwinSystems = [
        "aarch64-darwin"
        "x86_64-darwin"
      ];
      forSystems = systems: f: nixpkgs.lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});

      # Host LLVM used for BPF objects (CONFIG_BPF_TOOLCHAIN_HOST). Unwrapped clang:
      # the Nix cc-wrapper would inject hardening flags that are invalid for -target bpf.
      llvmFor = pkgs: pkgs.llvmPackages_21;

      # Tools needed outside the FHS environment (orchestration and lint), on every host.
      orchestrationTools =
        pkgs: with pkgs; [
          just
          git
          jq
          shellcheck
        ];

      # Everything OpenWrt's include/prereq-build.mk checks for, plus what U-Boot,
      # the kernel (BTF via the in-tree pahole) and the BPF host toolchain need.
      fhsFor =
        pkgs:
        let
          llvm = llvmFor pkgs;
        in
        pkgs.buildFHSEnv {
          name = "wrt-fhs";
          targetPkgs =
            p: with p; [
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
            ];
          profile = ''
            # OpenWrt host tools do not build cleanly with the Nix hardening flags.
            export NIX_HARDENING_ENABLE=
            export WRT_FHS=1
          '';
          runScript = "bash";
        };
    in
    {
      packages = forSystems linuxSystems (pkgs: rec {
        wrt-fhs = fhsFor pkgs;
        default = wrt-fhs;
      });

      devShells =
        forSystems linuxSystems (pkgs: {
          default = pkgs.mkShellNoCC {
            packages = orchestrationTools pkgs ++ [ (fhsFor pkgs) ];
          };
        })
        // forSystems darwinSystems (pkgs: {
          # macOS can run lint and orchestration, never the build itself.
          default = pkgs.mkShellNoCC { packages = orchestrationTools pkgs; };
        });

      formatter = forSystems (linuxSystems ++ darwinSystems) (pkgs: pkgs.nixfmt-rfc-style);
    };
}
