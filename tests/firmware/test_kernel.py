"""firmware/kernel: version, BTF, BPF and cgroup v2, built-in filesystems, BBRv3, vermagic."""

import re
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from wrt_tests import spec

if TYPE_CHECKING:
    from wrt_tests.router import Router

CAPABILITY = "firmware/kernel"
PATCHES = Path(__file__).resolve().parents[2] / "patches" / "openwrt"
BBR3_ONLY_SYMBOLS = ("bbr_skb_marked_lost", "bbr_tso_segs")
KERNEL_PATCH_DIR = re.compile(r"^target/linux/[^/]+/(patches|hack|pending|backport)-[0-9.]+/")
BBR3_PATCH = re.compile(r"^target/linux/generic/hack-[0-9.]+/960-bbr3-")
BPF_OBJECT = "/tmp/wrt_pass.o"  # noqa: S108 (a path on the router)
# The smallest tcx program: it hands every packet on (TCX_NEXT). libbpf derives the
# program and attach type from the section name.
TCX_SOURCE = """\
__attribute__((section("tcx/ingress"), used)) int wrt_pass(void *ctx) { return -1; }
char LICENSE[] __attribute__((section("license"), used)) = "GPL";
"""
VIRTIO_NICS = ("eth0 (WAN)", "eth1 (LAN)")
SD_CARD = "/dev/mmcblk0"
# The drivers of the R4S ports register at boot, even where their devices are absent.
PORT_DRIVERS = (
    "/sys/bus/platform/drivers/rk_gmac-dwmac",  # the GMAC: WAN, eth0
    "/sys/bus/pci/drivers/r8169",  # the RTL8111 on PCIe: LAN, eth1
)


@spec(CAPABILITY, "Kernel version follows upstream", "Check running kernel")
def test_running_kernel_is_the_packaged_one(router: Router) -> None:
    packaged = re.search(
        r"^kernel-(\d+\.\d+\.\d+)~", router.run("apk list -I kernel"), re.MULTILINE
    )
    assert packaged is not None
    assert router.run("uname -r") == packaged.group(1)


@spec(CAPABILITY, "Provide BTF", "Check BTF")
def test_btf_for_kernel_and_modules(router: Router) -> None:
    assert int(router.run("wc -c < /sys/kernel/btf/vmlinux")) > 0
    modules = router.run("cut -d' ' -f1 /proc/modules").split()
    assert modules
    missing = router.run(
        f"for m in {' '.join(modules)}; do [ -s /sys/kernel/btf/$m ] || echo $m; done"
    )
    assert missing == ""


@spec(CAPABILITY, "BPF and cgroup v2", "Check cgroup mounts")
def test_cgroup2_only(router: Router) -> None:
    mounts = [line.split() for line in router.run("cat /proc/mounts").splitlines()]
    assert ["/sys/fs/cgroup", "cgroup2"] in [fields[1:3] for fields in mounts]
    assert [fields for fields in mounts if fields[2] == "cgroup"] == []


@spec(CAPABILITY, "BPF and cgroup v2", "Load a tcx program")
def test_tcx_program_attaches(router: Router, tmp_path: Path) -> None:
    program = tmp_path / "wrt_pass.o"
    subprocess.run(
        ["clang", "--target=bpf", "-O2", "-g", "-c", "-x", "c", "-", "-o", str(program)],
        input=TCX_SOURCE,
        text=True,
        check=True,
    )
    router.put(program, BPF_OBJECT)
    router.run("mountpoint -q /sys/fs/bpf || mount -t bpf bpf /sys/fs/bpf")
    router.run(f"bpftool prog load {BPF_OBJECT} /sys/fs/bpf/wrt_pass")
    try:
        router.run("bpftool net attach tcx_ingress pinned /sys/fs/bpf/wrt_pass dev br-lan")
        listing = router.run("bpftool net show dev br-lan")
        assert re.search(r"tcx/ingress\s+wrt_pass\b", listing), listing
    finally:
        router.returncode("bpftool net detach tcx_ingress dev br-lan")
        router.run("rm -f /sys/fs/bpf/wrt_pass")


@spec(CAPABILITY, "Root and overlay filesystems built in", "Boot without loading modules")
def test_filesystems_are_built_in(router: Router) -> None:
    filesystems = router.run("cat /proc/filesystems").split()
    modules = router.run("cut -d' ' -f1 /proc/modules").split()
    for filesystem in ("erofs", "f2fs"):
        assert filesystem in filesystems
        assert filesystem not in modules
    mounts = [line.split()[1:3] for line in router.run("cat /proc/mounts").splitlines()]
    assert ["/rom", "erofs"] in mounts
    assert ["/overlay", "f2fs"] in mounts


@spec(CAPABILITY, "Same kernel boots in the emulator", "Shipped kernel boots in the emulator")
def test_virt_devices(router: Router) -> None:
    assert "console=ttyAMA0" in router.run("cat /proc/cmdline").split()
    assert router.returncode("dmesg | grep -q 'printk: console \\[ttyAMA0\\] enabled'") == 0
    assert router.run("awk '$2 == \"/rom\" { print $1 }' /proc/mounts") in {
        "/dev/root",
        f"{SD_CARD}p2",
    }
    assert router.returncode(f"[ -b {SD_CARD}p2 ]") == 0
    assert router.run("ls /sys/bus/pci/drivers/sdhci-pci/ | grep -c '^0000:'") == "1"
    nics = router.run("ls /sys/bus/virtio/drivers/virtio_net/ | grep '^virtio'").split()
    assert len(nics) == len(VIRTIO_NICS)
    # OpenWrt builds without WATCHDOG_SYSFS; the driver announces itself instead.
    assert router.returncode("dmesg | grep -q 'i6300ESB timer .*initialized'") == 0
    assert router.returncode("[ -c /dev/watchdog0 ]") == 0


@spec(CAPABILITY, "Drivers for the R4S ports", "Port drivers registered")
def test_port_drivers_registered(router: Router) -> None:
    for driver in PORT_DRIVERS:
        assert router.returncode(f"[ -d {driver} ]") == 0, driver


@spec(CAPABILITY, "BBRv3 as default congestion control", "Check congestion control settings")
def test_bbr3_is_the_default(router: Router) -> None:
    assert router.run("sysctl -n net.ipv4.tcp_congestion_control") == "bbr"
    assert router.run("sysctl -n net.core.default_qdisc") == "fq"
    symbols = set(router.run("awk '{ print $3 }' /proc/kallsyms").split())
    assert set(BBR3_ONLY_SYMBOLS) <= symbols


@spec(CAPABILITY, "BBRv3 as default congestion control", "Router-originated connections use BBR")
def test_local_connection_uses_bbr(router: Router) -> None:
    # Hold a connection from the router to its own web server open, then look at it.
    info = router.run(
        "(sleep 5 | nc 127.0.0.1 80 >/dev/null) & sleep 2; ss -Htin state established 'dport = :80'"
    )
    assert re.search(r"\bbbr\b", info), info


@spec(CAPABILITY, "BBRv3 is the only kernel source change", "Audit kernel patches")
def test_only_bbr3_patches_the_kernel() -> None:
    changed = {
        line.split()[3].removeprefix("b/")
        for patch in PATCHES.glob("*.patch")
        for line in patch.read_text().splitlines()
        if line.startswith("diff --git ")
    }
    kernel = {path for path in changed if KERNEL_PATCH_DIR.match(path)}
    assert kernel
    assert {path for path in kernel if not BBR3_PATCH.match(path)} == set()


@spec(CAPABILITY, "Standard vermagic", "Install a kmod from the same build")
def test_kmod_of_the_same_build_loads(router: Router, repository: str) -> None:
    router.run(f"apk add --repository {repository}/targets/packages/packages.adb kmod-dummy")
    router.run("modprobe dummy")
    assert "dummy" in router.run("cut -d' ' -f1 /proc/modules").split()


@spec(CAPABILITY, "Standard vermagic", "Reject a kmod with a different kernel config")
def test_kmod_of_another_kernel_is_refused(router: Router) -> None:
    # A kmod depends on kernel=<version>~<vermagic>; a virtual package with the
    # running version but another vermagic has exactly the dependency of a kmod
    # from a build with a different kernel configuration.
    version = router.run("uname -r")
    dependency = f"kernel={version}~{'0' * 32}-r1"
    code = router.returncode(f"apk add --virtual kmod-wrt-vermagic-probe '{dependency}'")
    assert code != 0
    assert router.returncode("apk info -e kmod-wrt-vermagic-probe") != 0
