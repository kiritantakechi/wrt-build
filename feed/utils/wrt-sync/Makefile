include $(TOPDIR)/rules.mk

PKG_NAME:=wrt-sync
PKG_VERSION:=1
PKG_RELEASE:=1

PKG_MAINTAINER:=kiritantakechi <kiritantakechi@gmail.com>
PKG_LICENSE:=GPL-2.0-only

include $(INCLUDE_DIR)/package.mk

define Package/wrt-sync
  SECTION:=utils
  CATEGORY:=Utilities
  TITLE:=Local repository of releases, and upgrades from it
  DEPENDS:=+wrt-data +podman +usign +ucert +uclient-fetch +jsonfilter +ucode
  PKGARCH:=all
endef

define Package/wrt-sync/description
  The device side of r4s-release-pipeline (D4): wrt-sync fetches the newest
  release through a container on podman's network, so dae routes it like the
  LAN's traffic, into /mnt/data/repo, and activates it only once its signed
  manifest, its files and its package indexes verify. apk installs from that
  repository; wrt-update upgrades to its image.
endef

define Package/wrt-sync/conffiles
/etc/config/wrt-sync
endef

define Build/Compile
endef

define Package/wrt-sync/install
	$(CP) ./files/. $(1)/
endef

$(eval $(call BuildPackage,wrt-sync))
