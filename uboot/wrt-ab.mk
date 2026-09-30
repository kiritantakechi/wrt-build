# Build glue of the A/B U-Boot (r4s-ab-rollback design D3, board-model D3):
# uboot-rockchip builds the U-Boot of every board with it, uboot-wrt-qemu the
# emulator's. The tree links this directory in as env/uboot. uboot-rockchip
# includes it after its variants' definitions, which it extends.

WRT_AB_DIR := $(TOPDIR)/env/uboot

# The boards, each as <U-Boot variant>:<board id>:<environment directory in the
# U-Boot tree> (scripts/lib.sh writes them from boards/*.json).
include $(TOPDIR)/env/wrt-boards.mk

# The variables the stored environment may set (ENV_WRITEABLE_LIST). U-Boot takes
# this list only from its C configuration; u-boot.mk passes KBUILD_CFLAGS on.
WRT_AB_WRITEABLE := boot_slot:sw,bootcount:dw,upgrade_available:dw
WRT_AB_KBUILD_CFLAGS := -DCFG_ENV_FLAGS_LIST_STATIC='\"$(WRT_AB_WRITEABLE)\"'

# WrtAB/config <board>: the configuration fragments after the defconfig in
# UBOOT_CONFIG.
WrtAB/config = wrt-ab board-$(1)

# WrtAB/Build <board>,<environment directory in the U-Boot tree>: build the
# package's variant with the slot logic. Preparing it puts the fragments where
# U-Boot finds them, and writes the board constants followed by the shared
# logic as the variant's default environment, wrt.env (ENV_SOURCE_FILE).
define WrtAB/Build
PKG_FILE_DEPENDS += $(WRT_AB_DIR)/
KBUILD_CFLAGS += $(WRT_AB_KBUILD_CFLAGS)

define Build/Prepare
	$$(call Build/Prepare/Default)
	$$(INSTALL_DIR) $$(PKG_BUILD_DIR)/board/wrt
	$$(CP) $(WRT_AB_DIR)/wrt-ab.config $(WRT_AB_DIR)/board-$(1).config $$(PKG_BUILD_DIR)/board/wrt/
	cat $(WRT_AB_DIR)/board-$(1).env $(WRT_AB_DIR)/wrt-ab.env >$$(PKG_BUILD_DIR)/$(2)/wrt.env
endef
endef

define WrtAB/newline


endef

# A board's variant: its definition gains the fragments, on a line of their own
# after its last, and the package the slot logic.
WRT_AB_BOARD := $(subst :, ,$(filter $(BUILD_VARIANT):%,$(WRT_AB_BOARDS)))
ifneq ($(WRT_AB_BOARD),)
WRT_AB_CONFIG := $(call WrtAB/config,$(word 2,$(WRT_AB_BOARD)))
U-Boot/$(BUILD_VARIANT) += $(WrtAB/newline)UBOOT_CONFIG += $(WRT_AB_CONFIG)
$(eval $(call WrtAB/Build,$(word 2,$(WRT_AB_BOARD)),$(word 3,$(WRT_AB_BOARD))))
endif
