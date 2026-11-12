# doona (honk-datapath design D3): honk's web UI, built from source and embedded
# into honk by its native-ui feature. It is built as doona's own release is:
# the dependencies its lockfile pins (integrity-checked by pnpm), both editions,
# then tools/package.sh, which adds each edition's licence notices. pnpm is the
# version doona's packageManager names, run by the Node of flake.nix. Both
# editions land in DOONA_DIR, as honk's ci/fetch-doona.sh lays them out.

include $(TOPDIR)/rules.mk

PKG_NAME:=doona
PKG_VERSION:=0.1.0-rc.6
PKG_RELEASE:=1

PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.gz
PKG_SOURCE_URL:=https://codeload.github.com/Zakkaus/doona/tar.gz/refs/tags/v$(PKG_VERSION)?
PKG_HASH:=d8b85ac93d692e507ce1174a8a1f23be3d2f7ff6a413ce43be061d9088d9b6f6

PKG_LICENSE:=GPL-3.0-only
PKG_LICENSE_FILES:=LICENSE
PKG_MAINTAINER:=kiritantakechi <kiritantakechi@gmail.com>

PKG_HOST_ONLY:=1

PNPM_VERSION:=11.15.1

include $(INCLUDE_DIR)/host-build.mk
include $(INCLUDE_DIR)/package.mk

define Download/pnpm
  FILE:=pnpm-$(PNPM_VERSION).tgz
  URL:=https://registry.npmjs.org/pnpm/-/
  HASH:=27460629b10111604e7f98882753b53398986820c20e0a065f3a4a5e9e7db71f
endef
$(eval $(call Download,pnpm))

define Package/doona
  SECTION:=net
  CATEGORY:=Network
  TITLE:=Web UI of honk, embedded into honk
  URL:=https://github.com/Zakkaus/doona
  BUILDONLY:=1
endef

define Package/doona/description
  doona is honk's web UI, served by honk's native API. The firmware embeds it
  into honk; this package builds it on the host.
endef

# honk's package sets HONK_DOONA_DIR to $(DOONA_DIR)/doona; honk takes the lite
# edition from its sibling, doona-lite.
DOONA_DIR:=$(STAGING_DIR_HOSTPKG)/share/doona
PNPM_DIR:=$(HOST_BUILD_DIR)/.pnpm
# pnpm's package store sits with the other downloads, so that a rebuild fetches
# nothing the lockfile already pinned; its cache and state stay in the build.
PNPM_ENV:= \
	PATH="$(PNPM_DIR)/bin:$(PATH)" \
	CI=true \
	npm_config_store_dir=$(DL_DIR)/pnpm-store \
	npm_config_cache=$(HOST_BUILD_DIR)/.pnpm-cache \
	npm_config_update_notifier=false \
	XDG_CACHE_HOME=$(HOST_BUILD_DIR)/.cache \
	XDG_DATA_HOME=$(HOST_BUILD_DIR)/.local/share \
	XDG_STATE_HOME=$(HOST_BUILD_DIR)/.local/state \
	SOURCE_DATE_EPOCH=$(SOURCE_DATE_EPOCH)

define Host/Prepare
	$(call Host/Prepare/Default)
	mkdir -p $(PNPM_DIR)/bin
	tar -xzf $(DL_DIR)/pnpm-$(PNPM_VERSION).tgz -C $(PNPM_DIR)
	printf '#!/bin/sh\nexec node %s "$$@"\n' $(PNPM_DIR)/package/bin/pnpm.mjs >$(PNPM_DIR)/bin/pnpm
	chmod 755 $(PNPM_DIR)/bin/pnpm
endef

define Host/Configure
endef

define Host/Compile
	cd $(HOST_BUILD_DIR) && $(PNPM_ENV) pnpm install --frozen-lockfile
	cd $(HOST_BUILD_DIR) && $(PNPM_ENV) pnpm build
	cd $(HOST_BUILD_DIR) && $(PNPM_ENV) pnpm -C apps/lite build
	rm -rf $(HOST_BUILD_DIR)/release
	cd $(HOST_BUILD_DIR) && $(PNPM_ENV) sh tools/package.sh
endef

# Each edition without its fonts, which honk does not embed (ci/fetch-doona.sh).
define Host/Install
	rm -rf $(DOONA_DIR)
	$(INSTALL_DIR) $(DOONA_DIR)/doona $(DOONA_DIR)/doona-lite
	tar -xzf $(HOST_BUILD_DIR)/release/doona-$(PKG_VERSION).tar.gz -C $(DOONA_DIR)/doona
	tar -xzf $(HOST_BUILD_DIR)/release/doona-lite-$(PKG_VERSION).tar.gz -C $(DOONA_DIR)/doona-lite
	rm -rf $(DOONA_DIR)/doona/fonts $(DOONA_DIR)/doona-lite/fonts
endef

define Host/Clean
	rm -rf $(DOONA_DIR)
	$(call Host/Clean/Default)
endef

$(eval $(call HostBuild))
$(eval $(call BuildPackage,doona))
