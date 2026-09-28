# The emulator's U-Boot (r4s-ab-rollback design D3): qemu_arm64 built from the
# same U-Boot as the R4S's, with the same A/B slot logic. A test artifact: it
# installs nothing, scripts/build.sh takes it from the image staging directory.

include $(TOPDIR)/rules.mk

# Version and hash come from uboot-rockchip, so the two builds cannot drift apart.
UBOOT_ROCKCHIP := $(TOPDIR)/package/boot/uboot-rockchip/Makefile
PKG_VERSION := $(shell sed -n 's/^PKG_VERSION:=//p' $(UBOOT_ROCKCHIP))
PKG_HASH := $(shell sed -n 's/^PKG_HASH:=//p' $(UBOOT_ROCKCHIP))
PKG_RELEASE:=1

PKG_MAINTAINER:=kiritantakechi <kiritantakechi@gmail.com>

UBOOT_USE_INTREE_DTC:=1

include $(INCLUDE_DIR)/u-boot.mk
include $(INCLUDE_DIR)/package.mk
include $(TOPDIR)/env/uboot/wrt-ab.mk

define U-Boot/Default
  BUILD_TARGET:=rockchip
  BUILD_SUBTARGET:=armv8
  UENV:=default
endef

define U-Boot/wrt-qemu
  NAME:=the emulated R4S (QEMU virt)
  UBOOT_CONFIG:=qemu_arm64 $(call WrtAB/config,qemu)
endef

UBOOT_TARGETS := wrt-qemu

# As uboot-rockchip builds its host tools.
UBOOT_CUSTOMIZE_CONFIG := \
	--disable TOOLS_MKEFICAPSULE \
	--set-str MKIMAGE_DTC_PATH $(PKG_BUILD_DIR)/scripts/dtc/dtc

PKG_FILE_DEPENDS += $(WRT_AB_DIR)/
KBUILD_CFLAGS += $(WRT_AB_KBUILD_CFLAGS)

define Build/Prepare
	$(call Build/Prepare/Default)
	$(call Build/Prepare/WrtAB,qemu,board/emulation/qemu-arm)
endef

define Build/InstallDev
	$(INSTALL_DIR) $(STAGING_DIR_IMAGE)
	$(CP) $(PKG_BUILD_DIR)/u-boot.bin $(STAGING_DIR_IMAGE)/wrt-qemu-u-boot.bin
endef

define Package/u-boot/install/default
endef

$(eval $(call BuildPackage/U-Boot))
