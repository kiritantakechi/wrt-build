# 上游贡献

向任何不属于本人的仓库提交 PR、issue 或推送，都必须先得到明确同意。这里的补丁只在本地准备好，是否提交、什么时候提交由维护者决定。

| # | 仓库 | 补丁 | 状态 | 链接 |
|---|---|---|---|---|
| 1 | openwrt/openwrt | `docs/upstream/0001-build-make-the-EROFS-compression-selectable.patch` | 已准备，尚未提交（等待确认） | — |
| 2 | openwrt/openwrt | `docs/upstream/0002-config-kernel-add-F2FS-compression-options.patch` | 已准备，尚未提交（等待确认） | — |

## 1. EROFS 压缩算法

问题：`include/image.mk:110` 判断的是 `CONFIG_EROFS_FS_ZIP_LZMA`，但这个符号不存在，Kconfig 里的选项名是 `KERNEL_EROFS_FS_ZIP_LZMA`。所以 LZMA 分支永远不会被执行，所有 EROFS 镜像实际都用 lz4hc 压缩。

为什么不能只改名：`KERNEL_EROFS_FS_ZIP_LZMA` 没有提示项，并且在开启 EROFS 时默认为 y。只改名的话，所有 EROFS 构建都会**静默改用 LZMA**，本项目的镜像也会跟着变，而我们选定的是 lz4hc。

补丁的做法：新增一个 `compression` 选择项，默认 lz4hc，与当前实际行为一致；选 LZMA 时同时选中内核的 LZMA 支持。`image.mk` 改为按这个选择项判断。

## 2. F2FS 压缩的内核选项

问题：fstools 支持用 `fstools_overlay_compression_type=` 把 overlay 格式化成带压缩的 f2fs，但 `config/Config-kernel.in` 里没有对应的 `KERNEL_F2FS_*` 选项，构建配置选不出来。

补丁的做法：新增 `KERNEL_F2FS_FS_COMPRESSION` 以及它下面的每一个算法选项（LZO、LZO-RLE、LZ4、LZ4HC、ZSTD）。内核把这些选项都默认为 y，有任何一个没有取值，构建就会停下，所以每个都要有对应的 `KERNEL_*`。

本项目的用法：不依赖这个补丁，而是用上游原生的内核配置叠加文件（`config/kernel.config` → `env/kernel-config`）提供同样的选项。补丁被上游接受之后，可以改回用 seed 里的 `CONFIG_KERNEL_F2FS_*`。
