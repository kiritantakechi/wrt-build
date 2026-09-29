include $(TOPDIR)/rules.mk

PKG_NAME:=wrt-containers
PKG_VERSION:=1
PKG_RELEASE:=1

PKG_MAINTAINER:=kiritantakechi <kiritantakechi@gmail.com>
PKG_LICENSE:=GPL-2.0-only

include $(INCLUDE_DIR)/package.mk

define Package/wrt-containers
  SECTION:=utils
  CATEGORY:=Utilities
  TITLE:=Pods declared on the data disk, started once it is mounted
  DEPENDS:=+podman +wrt-data
  PKGARCH:=all
endef

define Package/wrt-containers/description
  The app containers of r4s-services: Kubernetes Pod declarations in
  /mnt/data/containers/pods, played by podman when the data disk is mounted
  and played again only when a declaration changes. netavark installs no
  firewall rules; fw4 and einat handle the container network.
endef

define Package/wrt-containers/conffiles
/etc/containers/containers.conf.d/50-wrt.conf
endef

define Build/Compile
endef

define Package/wrt-containers/install
	$(CP) ./files/* $(1)/
endef

$(eval $(call BuildPackage,wrt-containers))
