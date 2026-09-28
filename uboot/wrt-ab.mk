# Build glue of the A/B U-Boot (design D3), shared by uboot-rockchip for the R4S
# and uboot-wrt-qemu for the emulator. scripts/config.sh links this directory
# into the tree as env/uboot.

WRT_AB_DIR := $(TOPDIR)/env/uboot

# The variables the stored environment may set (ENV_WRITEABLE_LIST). U-Boot takes
# this list only from its C configuration; u-boot.mk passes KBUILD_CFLAGS on.
WRT_AB_WRITEABLE := boot_slot:sw,bootcount:dw,upgrade_available:dw
WRT_AB_KBUILD_CFLAGS := -DCFG_ENV_FLAGS_LIST_STATIC='\"$(WRT_AB_WRITEABLE)\"'

# WrtAB/config <board>: the configuration fragments after the board's defconfig
# in UBOOT_CONFIG.
WrtAB/config = wrt-ab board-$(1)

# Build/Prepare/WrtAB <board>,<board directory in the U-Boot tree>
# Puts the fragments where U-Boot finds them, and writes the board constants
# followed by the shared logic as the board's wrt.env (ENV_SOURCE_FILE).
define Build/Prepare/WrtAB
	$(INSTALL_DIR) $(PKG_BUILD_DIR)/board/wrt
	$(CP) $(WRT_AB_DIR)/wrt-ab.config $(WRT_AB_DIR)/board-$(1).config $(PKG_BUILD_DIR)/board/wrt/
	cat $(WRT_AB_DIR)/board-$(1).env $(WRT_AB_DIR)/wrt-ab.env >$(PKG_BUILD_DIR)/$(2)/wrt.env
endef
