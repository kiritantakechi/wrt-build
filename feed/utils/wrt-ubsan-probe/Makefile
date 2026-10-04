# wrt-ubsan-probe (toolchain-o3 D5): undefined behavior on purpose, which only
# config/ubsan.seed selects. Never in a dev, ci or release image
# (scripts/image-audit.sh refuses it).

include $(TOPDIR)/rules.mk

PKG_NAME:=wrt-ubsan-probe
PKG_VERSION:=1
PKG_RELEASE:=1

PKG_MAINTAINER:=kiritantakechi <kiritantakechi@gmail.com>
PKG_LICENSE:=GPL-2.0-only

include $(INCLUDE_DIR)/package.mk

define Package/wrt-ubsan-probe
  SECTION:=utils
  CATEGORY:=Utilities
  TITLE:=Signed overflow on purpose, for the ubsan profile's system tests
endef

define Package/wrt-ubsan-probe/description
  Overflows a signed integer on purpose. In the ubsan profile, where UBSan in
  trap mode instruments every target package, the overflow kills it with
  SIGTRAP: the profile's system test runs it and expects the harness to report
  the trap, which proves the instrumentation, its trap mode and the detection
  together. It also turns on, from early boot, the kernel's report of the
  processes that unhandled signals kill (debug.exception-trace), which the
  harness reads the traps from.
endef

define Build/Compile
	$(TARGET_CC) $(TARGET_CPPFLAGS) $(TARGET_CFLAGS) $(TARGET_LDFLAGS) \
		-o $(PKG_BUILD_DIR)/wrt-ubsan-probe $(PKG_BUILD_DIR)/wrt-ubsan-probe.c
endef

define Package/wrt-ubsan-probe/install
	$(INSTALL_DIR) $(1)/usr/bin $(1)/etc/sysctl.d
	$(INSTALL_BIN) $(PKG_BUILD_DIR)/wrt-ubsan-probe $(1)/usr/bin/
	$(INSTALL_DATA) ./files/exception-trace.conf $(1)/etc/sysctl.d/10-exception-trace.conf
endef

$(eval $(call BuildPackage,wrt-ubsan-probe))
