include $(TOPDIR)/rules.mk

PKG_NAME:=wrt-metrics
PKG_VERSION:=1
PKG_RELEASE:=1

PKG_MAINTAINER:=kiritantakechi <kiritantakechi@gmail.com>
PKG_LICENSE:=GPL-2.0-only

include $(INCLUDE_DIR)/package.mk

define Package/wrt-metrics
  SECTION:=utils
  CATEGORY:=Utilities
  TITLE:=hwmon and filesystem collectors for the ucode node exporter
  DEPENDS:=+prometheus-node-exporter-ucode +rpcd-mod-ucode
  PKGARCH:=all
endef

define Package/wrt-metrics/description
  The two collectors r4s-services monitors with that the ucode node exporter
  lacks: hwmon (temperatures) and filesystem (size and use of each mount),
  under node_exporter's metric names. The exporter runs in a jail of its own
  mounts, so an rpcd plugin reports the host's filesystems over ubus.
endef

define Build/Compile
endef

define Package/wrt-metrics/install
	$(INSTALL_DIR) $(1)/usr/share/ucode/node-exporter/lib $(1)/usr/share/rpcd/ucode
	$(INSTALL_DATA) ./files/*.uc $(1)/usr/share/ucode/node-exporter/lib/
	$(INSTALL_DATA) ./files/rpcd/wrt-metrics $(1)/usr/share/rpcd/ucode/
endef

define Package/wrt-metrics/postinst
#!/bin/sh
[ -n "$${IPKG_INSTROOT}" ] || /etc/init.d/rpcd reload
endef

$(eval $(call BuildPackage,wrt-metrics))
