# The release signing tools (r4s-release-pipeline D2), built here from the
# first-party sources the pinned OpenWrt tree uses, never taken from a build job,
# whose host tools come from code that may be compromised: apk-tools 3 signs and
# verifies package indexes; usign, ucert and fwtool sign and verify firmware.
# `sign-tools --version` lists the four; `sign-tools <command>` runs a command
# (scripts/release-sign.sh) with them, and the few utilities it needs, on PATH.
{ pkgs }:
let
  inherit (pkgs) lib stdenv;

  openwrtProject =
    name: rev: hash:
    pkgs.fetchgit {
      url = "https://git.openwrt.org/project/${name}.git";
      inherit rev hash;
    };

  # The revisions of package/system/{usign,ucert,fwtool,apk} in the OpenWrt tree.
  usign = stdenv.mkDerivation {
    pname = "usign";
    version = "2025-10-03";
    src =
      openwrtProject "usign" "c4c72b1b07945ee192361dc751291a7c98d6adcd"
        "sha256-MXvv1vFwGyRZ+gxNVyUvW+gsinaCPiZSqOukCKxyV4A=";
    nativeBuildInputs = [
      pkgs.cmake
      pkgs.pkg-config
    ];
    buildInputs = [ pkgs.libubox ];
    cmakeFlags = [ "-DUSE_LIBUBOX=ON" ];
  };

  ucert = stdenv.mkDerivation {
    pname = "ucert";
    version = "2025-10-03";
    src =
      openwrtProject "ucert" "57270b247c91f003db6e3ba1a71d6d1fa5710fef"
        "sha256-94BibQXyYxO0MDldZFLLzY4w1leentrLVgOdoVpVk00=";
    nativeBuildInputs = [
      pkgs.cmake
      pkgs.pkg-config
    ];
    buildInputs = [
      pkgs.libubox
      pkgs.json_c
    ];
    cmakeFlags = [ "-DUCERT_FULL=1" ];
    # ucert runs usign for every signature, from where OpenWrt installs it.
    postPatch = ''
      substituteInPlace usign-exec.c --replace-fail '"/usr/bin/usign"' '"${usign}/bin/usign"'
    '';
  };

  fwtool = stdenv.mkDerivation {
    pname = "fwtool";
    version = "2025-10-03";
    src =
      openwrtProject "fwtool" "04cd252e4e9394ffacd51f56f1f124abc534f715"
        "sha256-pKMOpgeVDqJY0sMmcMzeG4zgV0JZkm3A5PYUXRY0cX4=";
    nativeBuildInputs = [ pkgs.cmake ];
  };

  apk = stdenv.mkDerivation {
    pname = "apk-tools";
    version = "3.0.5";
    src = pkgs.fetchgit {
      url = "https://gitlab.alpinelinux.org/alpine/apk-tools.git";
      rev = "b5a31c0d865342ad80be10d68f1bb3d3ad9b0866";
      hash = "sha256-iuJFgsn4yfQYqichMVhnOHFYj+5xPZYnXaCW0ZkKbRU=";
    };
    nativeBuildInputs = [
      pkgs.meson
      pkgs.ninja
      pkgs.pkg-config
    ];
    buildInputs = [
      pkgs.openssl
      pkgs.zlib
    ];
    # As OpenWrt's host build (package/system/apk), without the built-in help.
    mesonFlags = [
      "-Dcrypto_backend=openssl"
      "-Durl_backend=wget"
      "-Dzstd=disabled"
      "-Dhelp=disabled"
      "-Ddocs=disabled"
      "-Dlua=disabled"
      "-Dpython=disabled"
      "-Dtests=disabled"
    ];
  };

  tools = [
    apk
    usign
    ucert
    fwtool
  ];

  sign-tools = pkgs.writeShellApplication {
    name = "sign-tools";
    runtimeInputs = tools ++ [
      pkgs.coreutils
      pkgs.findutils
      pkgs.gnused
      pkgs.jq
      # release-keys.sh makes the apk key with it
      pkgs.openssl
    ];
    text = ''
      if [ "''${1:-}" = --version ]; then
        ${lib.concatMapStrings (tool: ''
          echo "${tool.pname} ${tool.version}"
        '') tools}
        exit 0
      fi
      exec "$@"
    '';
  };
in
pkgs.symlinkJoin {
  name = "sign-tools";
  paths = [ sign-tools ] ++ tools;
  meta.mainProgram = "sign-tools";
}
