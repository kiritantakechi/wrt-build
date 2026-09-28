include $(TOPDIR)/rules.mk

PKG_NAME:=zsh-plugins
PKG_VERSION:=1
PKG_RELEASE:=1

AUTOSUGGESTIONS_VERSION:=0.7.1
SYNTAX_HIGHLIGHTING_VERSION:=0.8.0

PKG_SOURCE:=zsh-autosuggestions-$(AUTOSUGGESTIONS_VERSION).tar.gz
PKG_SOURCE_URL:=https://codeload.github.com/zsh-users/zsh-autosuggestions/tar.gz/v$(AUTOSUGGESTIONS_VERSION)?
PKG_HASH:=0df7affff21cd87ed298e6a3970ed08a1dd66a6efa676454ee5b091ad503badf

PKG_MAINTAINER:=kiritantakechi <kiritantakechi@gmail.com>
PKG_LICENSE:=MIT BSD-3-Clause

include $(INCLUDE_DIR)/package.mk

SYNTAX_HIGHLIGHTING_SOURCE:=zsh-syntax-highlighting-$(SYNTAX_HIGHLIGHTING_VERSION).tar.gz

define Download/syntax-highlighting
  FILE:=$(SYNTAX_HIGHLIGHTING_SOURCE)
  URL:=https://codeload.github.com/zsh-users/zsh-syntax-highlighting/tar.gz/$(SYNTAX_HIGHLIGHTING_VERSION)?
  HASH:=5981c19ebaab027e356fe1ee5284f7a021b89d4405cc53dc84b476c3aee9cc32
endef
$(eval $(call Download,syntax-highlighting))

define Package/zsh-plugins
  SECTION:=utils
  CATEGORY:=Utilities
  SUBMENU:=Shells
  TITLE:=zsh autosuggestions and syntax highlighting with a global zshrc
  DEPENDS:=+zsh
  PKGARCH:=all
endef

define Package/zsh-plugins/description
 zsh-autosuggestions $(AUTOSUGGESTIONS_VERSION) and zsh-syntax-highlighting
 $(SYNTAX_HIGHLIGHTING_VERSION), loaded from /etc/zsh/zshrc.
endef

define Build/Prepare
	mkdir -p $(PKG_BUILD_DIR)/autosuggestions $(PKG_BUILD_DIR)/syntax-highlighting
	$(TAR) -C $(PKG_BUILD_DIR)/autosuggestions --strip-components=1 -xzf $(DL_DIR)/$(PKG_SOURCE)
	$(TAR) -C $(PKG_BUILD_DIR)/syntax-highlighting --strip-components=1 -xzf $(DL_DIR)/$(SYNTAX_HIGHLIGHTING_SOURCE)
endef

define Build/Compile
endef

define Package/zsh-plugins/install
	$(INSTALL_DIR) $(1)/etc/zsh
	$(INSTALL_DATA) ./files/zshrc $(1)/etc/zsh/zshrc
	$(INSTALL_DIR) $(1)/usr/share/zsh/plugins/zsh-autosuggestions
	$(INSTALL_DATA) $(PKG_BUILD_DIR)/autosuggestions/zsh-autosuggestions.zsh \
		$(1)/usr/share/zsh/plugins/zsh-autosuggestions/
	$(INSTALL_DIR) $(1)/usr/share/zsh/plugins/zsh-syntax-highlighting
	$(CP) $(PKG_BUILD_DIR)/syntax-highlighting/zsh-syntax-highlighting.zsh \
		$(PKG_BUILD_DIR)/syntax-highlighting/highlighters \
		$(PKG_BUILD_DIR)/syntax-highlighting/.version \
		$(PKG_BUILD_DIR)/syntax-highlighting/.revision-hash \
		$(1)/usr/share/zsh/plugins/zsh-syntax-highlighting/
endef

$(eval $(call BuildPackage,zsh-plugins))
