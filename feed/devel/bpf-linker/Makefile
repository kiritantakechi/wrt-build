# bpf-linker (honk-datapath design D2): the linker of Rust's eBPF programs.
# rustc emits such a program as LLVM bitcode; bpf-linker links and optimizes
# it and generates the BPF object with LLVM, which must read rustc's bitcode.
# It therefore links the LLVM rustc links (packages 0012), statically, from
# RUST_LLVM_PREFIX: no second LLVM, and none of another version.

include $(TOPDIR)/rules.mk

PKG_NAME:=bpf-linker
PKG_VERSION:=0.11.0
PKG_RELEASE:=1

PKG_SOURCE:=$(PKG_NAME)-$(PKG_VERSION).tar.gz
PKG_SOURCE_URL:=https://codeload.github.com/aya-rs/bpf-linker/tar.gz/refs/tags/v$(PKG_VERSION)?
PKG_HASH:=e32948056bd2604cdcc7fb384155feaf52f05512e02f4e8a7368af48e22f30f2

PKG_LICENSE:=MIT Apache-2.0
PKG_LICENSE_FILES:=LICENSE-MIT LICENSE-APACHE
PKG_MAINTAINER:=kiritantakechi <kiritantakechi@gmail.com>

PKG_HOST_ONLY:=1
HOST_BUILD_DEPENDS:=rust/host

include $(INCLUDE_DIR)/host-build.mk
include $(INCLUDE_DIR)/package.mk
include $(TOPDIR)/feeds/packages/lang/rust/rust-host-build.mk

# LLVM 23, the one Rust 1.99 links. Linked statically, it brings zlib and zstd,
# taken from the host tools, and libstdc++, which bpf-linker finds through the
# host compiler's search directories.
RUST_HOST_FEATURES:=llvm-23,llvm-link-static
CARGO_HOST_VARS+= \
	LLVM_PREFIX=$(RUST_LLVM_PREFIX) \
	ZLIB_PATH=$(STAGING_DIR_HOST)/lib \
	LIBZSTD_PATH=$(STAGING_DIR_HOST)/lib

define Package/bpf-linker
  SECTION:=devel
  CATEGORY:=Development
  TITLE:=Linker of eBPF programs written in Rust
  URL:=https://github.com/aya-rs/bpf-linker
  BUILDONLY:=1
endef

define Package/bpf-linker/description
  bpf-linker links eBPF programs that rustc emitted as LLVM bitcode into
  BPF objects, with the LLVM that rustc itself links.
endef

$(eval $(call RustBinHostBuild))
$(eval $(call HostBuild))
$(eval $(call BuildPackage,bpf-linker))
