# honk (honk-datapath design D1-D8): the eBPF transparent proxy, bound to the
# LAN side, built from source. Its eBPF object is built first, with the host
# rustc (build-std, admitted by RUSTC_BOOTSTRAP) and bpf-linker, which links the
# same LLVM; honk-core embeds it (patch 001) and doona, the web UI (D3).
# daeuniverse's feed has a honk package of its own; this one replaces it.

include $(TOPDIR)/rules.mk

PKG_NAME:=honk
# apk spells the beta prerelease with _beta; HONK_TAG is the upstream tag.
PKG_VERSION:=0.1.0_beta6
PKG_RELEASE:=1
HONK_TAG:=v0.1.0-beta.6

PKG_SOURCE:=$(PKG_NAME)-$(patsubst v%,%,$(HONK_TAG)).tar.gz
PKG_SOURCE_URL:=https://codeload.github.com/daeuniverse/honk/tar.gz/refs/tags/$(HONK_TAG)?
PKG_HASH:=cfddedeafa349d0bdfaebd792d6f15c9f31de46a051e5a0692749a74f69d8e6d
PKG_BUILD_DIR:=$(BUILD_DIR)/$(PKG_NAME)-$(patsubst v%,%,$(HONK_TAG))

PKG_LICENSE:=GPL-3.0-only
PKG_LICENSE_FILES:=LICENSE
PKG_MAINTAINER:=kiritantakechi <kiritantakechi@gmail.com>

PKG_BUILD_DEPENDS:=rust/host bpf-linker/host doona/host
PKG_BUILD_PARALLEL:=1

# The Clash API is left out (D8); jemalloc and REALITY (rprx) are honk's own
# defaults.
RUST_PKG_FEATURES:=ebpf,native-ui,jemalloc,rprx

include $(INCLUDE_DIR)/package.mk
include $(TOPDIR)/feeds/packages/lang/rust/rust-package.mk

define Package/honk
  SECTION:=net
  CATEGORY:=Network
  SUBMENU:=Web Servers/Proxies
  TITLE:=Transparent proxy in eBPF, bound to the LAN side
  URL:=https://github.com/daeuniverse/honk
  DEPENDS:=@(aarch64||x86_64) $(RUST_ARCH_DEPENDS) +libstdcpp \
    +kmod-veth +kmod-sched-core +kmod-sched-bpf \
    +kmod-nft-core +kmod-nft-queue +kmod-nfnetlink-queue +kmod-nf-conntrack \
    +@KERNEL_DEBUG_INFO_BTF +@KERNEL_CGROUP_BPF
endef

define Package/honk/description
  honk splits traffic by rules in the kernel with eBPF: direct traffic never
  leaves the kernel, proxied traffic goes to its nodes. wrt-build binds it to
  br-lan, podman0 and tailscale0 only, and never to a WAN interface. Its web
  UI, doona, is served by its native API once the configuration enables it.
endef

define Package/honk/conffiles
/etc/config/honk
/etc/honk/config.dae
endef

EBPF_OBJECT:=$(PKG_BUILD_DIR)/target-ebpf/bpfel-unknown-none/release/honk-ebpf

# The eBPF object, apart from the target build: none of rust-package.mk's
# variables (the target, RUSTFLAGS, the release profile) may reach it, or they
# would override crates/honk-ebpf's own (.cargo/config.toml, Cargo.toml). Its
# crate uses no unstable feature; RUSTC_BOOTSTRAP only admits build-std.
define Build/Compile/Ebpf
	cd $(PKG_BUILD_DIR)/crates/honk-ebpf && \
	env -u RUSTFLAGS -u CARGO_BUILD_TARGET -u CARGO_ENCODED_RUSTFLAGS \
		CARGO_HOME=$(CARGO_HOME) \
		CARGO_TARGET_DIR=$(PKG_BUILD_DIR)/target-ebpf \
		RUSTC_BOOTSTRAP=1 \
		cargo build -v --locked --release \
			-Zbuild-std=core --target bpfel-unknown-none
endef

# bindgen (boring-sys) reads the target's headers through the host libclang,
# with the include directories of the target's C++ compiler.
HONK_BINDGEN_ARGS:=--target=$(REAL_GNU_TARGET_NAME) --sysroot=$(TOOLCHAIN_DIR) \
	$(shell $(TARGET_CXX_NOCACHE) -E -x c++ -v /dev/null 2>&1 | \
		sed -n '/search starts here:/,/End of search list/{/^ /s/^ */-isystem /p}')

CARGO_PKG_VARS+= \
	TARGET_CXX=$(TARGET_CXX_NOCACHE) \
	BINDGEN_EXTRA_CLANG_ARGS="$(HONK_BINDGEN_ARGS)" \
	HONK_PREBUILT_EBPF_OBJECT=$(EBPF_OBJECT) \
	HONK_DOONA_DIR=$(STAGING_DIR_HOSTPKG)/share/doona/doona \
	GITHUB_REF=refs/tags/$(HONK_TAG)

define Build/Compile
	$(call Build/Compile/Ebpf)
	$(call Build/Compile/Cargo,crates/honk-core,--no-default-features)
endef

define Package/honk/install
	$(INSTALL_DIR) $(1)/usr/bin $(1)/etc/config $(1)/etc/honk $(1)/etc/init.d $(1)/etc/healthcheck.d
	$(INSTALL_BIN) $(PKG_INSTALL_DIR)/bin/honk-core $(1)/usr/bin/
	$(INSTALL_CONF) ./files/uci-config $(1)/etc/config/honk
	$(INSTALL_CONF) ./files/config.dae $(1)/etc/honk/config.dae
	$(INSTALL_BIN) ./files/init $(1)/etc/init.d/honk
	$(INSTALL_BIN) ./files/healthcheck $(1)/etc/healthcheck.d/50-honk
endef

$(eval $(call BuildPackage,honk))
