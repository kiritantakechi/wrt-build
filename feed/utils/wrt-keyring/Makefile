include $(TOPDIR)/rules.mk

PKG_NAME:=wrt-keyring
PKG_VERSION:=1
PKG_RELEASE:=1

PKG_MAINTAINER:=kiritantakechi <kiritantakechi@gmail.com>
PKG_LICENSE:=GPL-2.0-only

include $(INCLUDE_DIR)/package.mk

define Package/wrt-keyring
  SECTION:=base
  CATEGORY:=Base system
  TITLE:=Release public keys of wrt-build
  PKGARCH:=all
endef

define Package/wrt-keyring/description
  The trust anchors of the release build (r4s-release-pipeline D1): the release
  keys' public halves, for apk (/etc/apk/keys) and for firmware signatures
  (/etc/opkg/keys, as usign and ucert read them). It replaces openwrt-keyring
  and holds more than one key of each during a key rotation.
endef

define Build/Compile
endef

# files/ mirrors the root filesystem; scripts/release-keys.sh adds the keys.
define Package/wrt-keyring/install
	$(INSTALL_DIR) $(1)/etc/apk/keys $(1)/etc/opkg/keys
	[ ! -d ./files ] || $(CP) ./files/. $(1)/
endef

$(eval $(call BuildPackage,wrt-keyring))
