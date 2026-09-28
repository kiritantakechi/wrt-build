# r4s-build-foundation 验证

## 自动化部分

foundation 的每个规格场景都对应一个测试用例，或者在 `tests/verified-elsewhere.toml` 里登记了由哪个构建或 CI job 验证。对照关系以工具的输出为准，这里不另外维护表格：

```sh
nix develop -c sh -c 'cd tests && uv run spec-coverage --change r4s-build-foundation'
```

在模拟器里对一次构建的出货镜像运行全部用例（本机虚拟机或 CI 的 `system-test` job）：

```sh
nix develop -c just test dev      # or: just test ci
```

报告写在 `tests/.reports/emulation.xml`。

## 真机部分

只有一条命令。先把镜像写入 microSD 卡（写之前务必确认设备名）：

```sh
gzip -dc openwrt-rockchip-armv8-friendlyarm_nanopi-r4s-erofs-sysupgrade.img.gz | sudo dd of=/dev/<sd> bs=4M conv=fsync
```

电脑接到 R4S 的 LAN 口（靠近 USB 口的那个），用 DHCP 取得地址，然后在 macOS 或虚拟机上运行：

```sh
just test-device 10.0.0.1
```

模拟器专属的用例（断电、故障安全按键、恢复出厂、升级这些会改动设备状态的操作）在真机上会显示为跳过，并写明原因。只有真机才能验证的场景是“刷写后启动”：从 SD 卡经 U-Boot 启动到用户态，并能在 LAN 上打开管理界面。

报告写在 `tests/.reports/device.xml`，结果存档到 `docs/validation/foundation-device.md`。
