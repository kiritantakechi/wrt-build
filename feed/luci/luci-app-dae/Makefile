# SPDX-License-Identifier: Apache-2.0
#
# Copyright (C) 2024 ImmortalWrt.org
#
# luci-app-dae from ImmortalWrt's luci (applications/luci-app-dae at adc898b):
# settings, the text editor of /etc/dae/config.dae (saved, then hot-reloaded)
# and the log. wrt-build ships no geo data packages, and adds the CPU pinning
# switch of its init script.

include $(TOPDIR)/rules.mk

PKG_LICENSE:=Apache-2.0
PKG_MAINTAINER:=kiritantakechi <kiritantakechi@gmail.com>

LUCI_TITLE:=LuCI app for dae
LUCI_DEPENDS:=+dae

include $(TOPDIR)/feeds/luci/luci.mk

# call BuildPackage - OpenWrt buildroot signature
