include $(TOPDIR)/rules.mk

PKG_NAME:=wrt-ab
PKG_VERSION:=1
PKG_RELEASE:=1

PKG_MAINTAINER:=kiritantakechi <kiritantakechi@gmail.com>
PKG_LICENSE:=GPL-2.0-only

include $(INCLUDE_DIR)/package.mk

define Package/wrt-ab
  SECTION:=utils
  CATEGORY:=Utilities
  TITLE:=A/B slots: upgrade, health check, slot switch
  DEPENDS:=@TARGET_rockchip +uboot-envtools +jsonfilter
  PKGARCH:=all
endef

define Package/wrt-ab/description
  The Linux side of the A/B slots (r4s-ab-rollback): sysupgrade writes only the
  inactive slot and makes it the trial slot, wrt-healthcheck confirms a trial
  slot or reboots it so that U-Boot can roll back, and wrt-slot shows the state
  or switches slots by hand.
endef

define Package/wrt-ab/conffiles
/etc/config/wrt-ab
endef

define Build/Compile
endef

define Package/wrt-ab/install
	$(CP) ./files/* $(1)/
	$(INSTALL_DIR) $(1)/etc/healthcheck.d
endef

$(eval $(call BuildPackage,wrt-ab))
