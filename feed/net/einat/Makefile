# einat (r4s-ebpf-datapath design D6): endpoint-independent NAT44 in eBPF, with
# the Aya loader only, and the mark patch of design D2 (patches/).

include $(TOPDIR)/rules.mk

PKG_NAME:=einat
PKG_VERSION:=0.1.11
PKG_RELEASE:=1

PKG_SOURCE:=einat-ebpf-$(PKG_VERSION).tar.gz
PKG_SOURCE_URL:=https://codeload.github.com/EHfive/einat-ebpf/tar.gz/refs/tags/v$(PKG_VERSION)?
PKG_HASH:=24bfa2346bc7de38626d2873aae5cacd95ba686d2fff8e37adaaef52d7b69847
PKG_BUILD_DIR:=$(BUILD_DIR)/einat-ebpf-$(PKG_VERSION)

PKG_LICENSE:=GPL-2.0-or-later GPL-2.0-only
PKG_LICENSE_FILES:=LICENSE
PKG_MAINTAINER:=kiritantakechi <kiritantakechi@gmail.com>

# libbpf only for the BPF helper headers of the BPF object: the loader is Aya.
PKG_BUILD_DEPENDS:=rust/host libbpf bpf-headers
PKG_BUILD_PARALLEL:=1

RUST_PKG_FEATURES:=aya

include $(INCLUDE_DIR)/bpf.mk
include $(INCLUDE_DIR)/package.mk
include $(TOPDIR)/feeds/packages/lang/rust/rust-package.mk

# build.rs compiles the BPF object with the clang in PATH (the host one, from
# flake.nix) and strips it with llvm-strip.
TARGET_PATH_PKG:=$(LLVM_PATH):$(TARGET_PATH_PKG)
CARGO_PKG_VARS+= EINAT_BPF_CFLAGS="-I$(STAGING_DIR)/usr/include"

define Package/einat
  SECTION:=net
  CATEGORY:=Network
  SUBMENU:=Routing and Redirection
  TITLE:=Endpoint-independent NAT44 in eBPF (full cone)
  URL:=https://github.com/EHfive/einat-ebpf
  DEPENDS:=@(aarch64||x86_64) $(BPF_DEPENDS) +kmod-sched-core +kmod-sched-bpf \
    +@KERNEL_DEBUG_FS +@KERNEL_DEBUG_INFO_BTF
endef

define Package/einat/description
  einat translates IPv4 addresses on the tc hooks of the WAN interface with
  endpoint-independent mapping and filtering, and marks the inbound packets it
  translated back, so the firewall can accept exactly those.
endef

define Package/einat/conffiles
/etc/config/einat
endef

define Build/Compile
	$(call Build/Compile/Cargo,,--no-default-features)
endef

define Package/einat/install
	$(INSTALL_DIR) $(1)/usr/bin $(1)/etc/config $(1)/etc/init.d $(1)/etc/healthcheck.d
	$(INSTALL_BIN) $(PKG_INSTALL_DIR)/bin/einat $(1)/usr/bin/
	$(INSTALL_CONF) ./files/uci-config $(1)/etc/config/einat
	$(INSTALL_BIN) ./files/init $(1)/etc/init.d/einat
	$(INSTALL_BIN) ./files/healthcheck $(1)/etc/healthcheck.d/50-einat
endef

$(eval $(call BuildPackage,einat))
