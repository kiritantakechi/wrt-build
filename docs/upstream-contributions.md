# 上游贡献

向任何不属于本人的仓库提交 PR、issue 或推送，都必须先得到明确同意。这里的补丁只在本地准备好，是否提交、什么时候提交由维护者决定。

| # | 仓库 | 补丁 | 状态 | 链接 |
|---|---|---|---|---|
| 1 | openwrt/openwrt | `docs/upstream/0001-build-make-the-EROFS-compression-selectable.patch` | 已准备，尚未提交（等待确认） | — |
| 2 | openwrt/openwrt | `patches/openwrt/0001-config-kernel-add-F2FS-compression-options.patch` | 可以提交，尚未提交 | — |

## 1. EROFS 压缩算法

问题：`include/image.mk:110` 判断的是 `CONFIG_EROFS_FS_ZIP_LZMA`，但这个符号不存在，Kconfig 里的选项名是 `KERNEL_EROFS_FS_ZIP_LZMA`。所以 LZMA 分支永远不会被执行，所有 EROFS 镜像实际都用 lz4hc 压缩。

为什么不能只改名：`KERNEL_EROFS_FS_ZIP_LZMA` 没有提示项，并且在开启 EROFS 时默认为 y。只改名的话，所有 EROFS 构建都会**静默改用 LZMA**，本项目的镜像也会跟着变，而我们选定的是 lz4hc。

补丁的做法：新增一个 `compression` 选择项，默认 lz4hc，与当前实际行为一致；选 LZMA 时同时选中内核的 LZMA 支持。`image.mk` 改为按这个选择项判断。
