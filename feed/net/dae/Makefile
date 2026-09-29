# dae (r4s-ebpf-datapath design D5): ImmortalWrt's net/dae, upgraded to 2.1.1 and
# with wrt-build's init script, which binds only the LAN side. dae opens no AF_XDP
# sockets, so ImmortalWrt's kmod-xdp-sockets-diag (and the kernel's XDP sockets
# it needs) is left out; its sockmap needs no stream parser either, as it
# attaches its sk_skb program as a stream verdict.

include $(TOPDIR)/rules.mk

PKG_NAME:=dae
PKG_VERSION:=2.1.1
PKG_RELEASE:=1

PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).zip
PKG_SOURCE_URL:=https://github.com/daeuniverse/dae/releases/download/v$(PKG_VERSION)/dae-full-src.zip?
PKG_HASH:=880d56d2f4b80c009c29693a5ec1d6a44b4958aeba6323af879787934ee0e855

PKG_LICENSE:=AGPL-3.0-only
PKG_LICENSE_FILES:=LICENSE
PKG_MAINTAINER:=kiritantakechi <kiritantakechi@gmail.com>

PKG_BUILD_DEPENDS:=golang/host bpf-headers
PKG_BUILD_PARALLEL:=1
PKG_BUILD_FLAGS:=no-mips16

GO_PKG:=github.com/daeuniverse/dae
GO_PKG_EXCLUDES:=control/kern/tests
GO_PKG_LDFLAGS_X:= \
	$(GO_PKG)/cmd.Version=$(PKG_VERSION) \
	$(GO_PKG)/common/consts.MaxMatchSetLen_=1024
GO_PKG_TAGS:=trace

include $(INCLUDE_DIR)/package.mk
include $(INCLUDE_DIR)/bpf.mk
include $(TOPDIR)/feeds/packages/lang/golang/golang-package.mk

UNZIP_CMD:=unzip -q -d $(PKG_BUILD_DIR) $(DL_DIR)/$(PKG_SOURCE)

define Package/dae
  SECTION:=net
  CATEGORY:=Network
  SUBMENU:=Web Servers/Proxies
  TITLE:=Transparent proxy in eBPF, bound to the LAN side
  URL:=https://github.com/daeuniverse/dae
  DEPENDS:=$(GO_ARCH_DEPENDS) $(BPF_DEPENDS) \
    +ca-bundle +kmod-sched-core +kmod-sched-bpf +kmod-veth
endef

define Package/dae/description
  dae splits traffic by rules in the kernel with eBPF: direct traffic never
  leaves the kernel, proxied traffic goes to its nodes. wrt-build binds it to
  br-lan, podman0 and tailscale0 only, and never to a WAN interface.
endef

define Package/dae/conffiles
/etc/config/dae
/etc/dae/config.dae
endef

DAE_CFLAGS:= \
	-O2 -Wall -Werror \
	-DMAX_MATCH_SET_LEN=1024 \
	-I$(BPF_HEADERS_DIR)/tools/lib \
	-I$(BPF_HEADERS_DIR)/arch/$(BPF_KARCH)/include/asm/mach-generic

# go generate compiles the BPF objects with the host clang (BPF_TOOLCHAIN_HOST),
# little-endian only, as every target of this build is.
define Build/Compile
	( \
		export \
		$(GO_GENERAL_BUILD_CONFIG_VARS) \
		$(GO_PKG_BUILD_CONFIG_VARS) \
		$(GO_PKG_BUILD_VARS) \
		BPF_CLANG="$(CLANG)" \
		BPF_STRIP_FLAG="-strip=$(LLVM_STRIP)" \
		BPF_CFLAGS="$(DAE_CFLAGS)" \
		BPF_TARGET="bpfel" \
		BPF_TRACE_TARGET="$(GO_ARCH)" ; \
		go generate $(PKG_BUILD_DIR)/control/control.go ; \
		go generate $(PKG_BUILD_DIR)/trace/trace.go ; \
		$(call GoPackage/Build/Compile) ; \
	)
endef

define Package/dae/install
	$(call GoPackage/Package/Install/Bin,$(1))
	$(INSTALL_DIR) $(1)/etc/config $(1)/etc/dae $(1)/etc/init.d $(1)/etc/hotplug.d/net $(1)/etc/healthcheck.d
	$(INSTALL_CONF) ./files/uci-config $(1)/etc/config/dae
	$(INSTALL_CONF) ./files/config.dae $(1)/etc/dae/config.dae
	$(INSTALL_BIN) ./files/init $(1)/etc/init.d/dae
	$(INSTALL_DATA) ./files/hotplug.sh $(1)/etc/hotplug.d/net/50-dae
	$(INSTALL_BIN) ./files/healthcheck $(1)/etc/healthcheck.d/50-dae
endef

$(eval $(call GoBinPackage,dae))
$(eval $(call BuildPackage,dae))
