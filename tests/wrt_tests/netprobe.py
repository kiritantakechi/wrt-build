"""netprobe: the probes the tests run inside the sandbox's namespaces (r4s-ebpf-datapath D11).

``serve`` runs on the emulated internet and reports what it sees of a flow, on
port PORT of every address, IPv4 and IPv6:

- TCP: one JSON line with the peer's address and port and the connection's MSS
  (TCP_MAXSEG), then it closes; on HTTP_PORT the same as the body of an HTTP
  response, for clients that speak only HTTP (the router's uclient-fetch);
- UDP: a JSON datagram with the peer's address and port; a datagram ``big`` gets
  the same answer padded to BIG bytes, which the way back has to fragment;
- ESP (IP protocol 50, raw sockets, no xfrm): every packet is answered to its
  source with the same SPI and the next sequence number, the payload being
  the JSON of the source address.

UDP and ESP answer from the address they were sent to, as a reply must to get
back through a stateful NAT.

Every other command is a client and prints one JSON object: ``tcp``, ``udp`` and
``esp`` what the server saw; ``connect`` whether any TCP server accepted a
connection, refused it or never answered; ``listen`` the first datagram it
receives; ``send``
the port it sent one from; ``resolve`` the answers of a DNS server;
``solicit-prefix`` what a DHCPv6 server offers for prefix delegation;
``solicit-router`` that it asked the routers on a link for an advertisement, as a
host does when it attaches; ``inject`` the size of the Ethernet frame it put on
a segment, bypassing routing (a spoofed packet).
"""

import argparse
import asyncio
import contextlib
import ipaddress
import json
import os
import socket
import struct
import sys
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from collections.abc import Callable

PORT = 8007
HTTP_PORT = 80
BIG = 3000
TIMEOUT = 5.0
ESP_HEADER = struct.Struct("!II")
# Room for the packet information of a received datagram.
ANCILLARY = socket.CMSG_SPACE(64)
DNS_HEADER = struct.Struct("!HHHHHH")
DNS_TYPES = {"A": 1, "AAAA": 28}
DNS_POINTER = 0xC0
RESOLVE_ATTEMPTS = 3
RESOLVE_WAIT = 2.0
DHCP6_SERVERS = "ff02::1:2"
ROUTERS = "ff02::2"
ROUTER_SOLICITATION = 133
DHCP6_OPTION = struct.Struct("!HH")
# DHCPv6 message types and options (RFC 8415), as far as a Solicit needs them.
SOLICIT, ADVERTISE = 1, 2
CLIENT_ID, ORO, ELAPSED_TIME, DNS_SERVERS, IA_PD, IA_PREFIX = 1, 6, 8, 23, 25, 26

type Seen = dict[str, object]
# A command line argument: its name or flag, and the keywords of add_argument.
type Argument = tuple[str, dict[str, Any]]


def _family(host: str) -> socket.AddressFamily:
    v6 = isinstance(ipaddress.ip_address(host), ipaddress.IPv6Address)
    return socket.AF_INET6 if v6 else socket.AF_INET


def _decode(data: bytes | str) -> Seen:
    return cast("Seen", json.loads(data))


def _seen(address: str, port: int | None = None, **extra: int) -> bytes:
    fields = {"address": address} if port is None else {"address": address, "port": port}
    return json.dumps(fields | extra).encode()


def _esp_payload(sock: socket.socket, packet: bytes) -> bytes:
    """Strip the IPv4 header that raw IPv4 sockets, unlike IPv6 ones, deliver."""
    return packet[(packet[0] & 0x0F) * 4 :] if sock.family == socket.AF_INET else packet


def _peer(writer: asyncio.StreamWriter) -> bytes:
    host, port = writer.get_extra_info("peername")[:2]
    sock = cast("socket.socket", writer.get_extra_info("socket"))
    return _seen(host, port, mss=sock.getsockopt(socket.IPPROTO_TCP, socket.TCP_MAXSEG))


async def _tcp(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    del reader
    writer.write(_peer(writer) + b"\n")
    await writer.drain()
    writer.close()
    await writer.wait_closed()


async def _http(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    while (await reader.readline()).strip():  # the request line and headers
        pass
    body = _peer(writer)
    head = (
        f"HTTP/1.0 200 OK\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\n\r\n"
    )
    writer.write(head.encode() + body)
    await writer.drain()
    writer.close()
    await writer.wait_closed()


def _local(ancillary: list[tuple[int, int, bytes]]) -> str:
    """Return the address a datagram was sent to, from its packet information."""
    for level, kind, data in ancillary:
        if (level, kind) == (socket.IPPROTO_IP, socket.IP_PKTINFO):
            return socket.inet_ntop(socket.AF_INET, data[8:12])  # ipi_addr, the destination
        if (level, kind) == (socket.IPPROTO_IPV6, socket.IPV6_PKTINFO):
            return socket.inet_ntop(socket.AF_INET6, data[:16])
    msg = "a datagram without packet information"
    raise ValueError(msg)


def _from(family: socket.AddressFamily, local: str) -> list[tuple[int, int, bytes]]:
    """Return the packet information that makes a reply leave from ``local``."""
    if family == socket.AF_INET:
        info = struct.pack("=i4s4s", 0, socket.inet_aton(local), bytes(4))
        return [(socket.IPPROTO_IP, socket.IP_PKTINFO, info)]
    info = socket.inet_pton(socket.AF_INET6, local) + struct.pack("=i", 0)
    return [(socket.IPPROTO_IPV6, socket.IPV6_PKTINFO, info)]


def _answering(family: socket.AddressFamily, kind: socket.SocketKind, port: int) -> socket.socket:
    """Return a socket that learns where each datagram was sent, to answer from there.

    A host with several addresses would otherwise answer from its first one, and
    a stateful firewall on the way back rightly takes that for another flow.
    """
    raw = kind == socket.SOCK_RAW
    sock = socket.socket(family, kind, socket.IPPROTO_ESP if raw else 0)
    if family == socket.AF_INET:
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_PKTINFO, 1)
    else:
        sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_RECVPKTINFO, 1)
        if not raw:  # one socket per family, as start_server does
            sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
    if not raw:
        sock.bind(("", port))
    sock.setblocking(False)  # noqa: FBT003
    return sock


def _udp_reply(sock: socket.socket) -> None:
    data, ancillary, _, peer = sock.recvmsg(65535, ANCILLARY)
    answer = _seen(peer[0], peer[1])
    if data.strip() == b"big":
        answer = answer.ljust(BIG)
    sock.sendmsg([answer], _from(sock.family, _local(ancillary)), 0, peer)


def _esp_reply(sock: socket.socket) -> None:
    packet, ancillary, _, peer = sock.recvmsg(65535, ANCILLARY)
    packet = _esp_payload(sock, packet)
    if len(packet) >= ESP_HEADER.size:
        spi, sequence = ESP_HEADER.unpack_from(packet)
        reply = ESP_HEADER.pack(spi, sequence + 1) + _seen(peer[0])
        sock.sendmsg([reply], _from(sock.family, _local(ancillary)), 0, peer)


async def serve(port: int) -> None:
    """Answer TCP, UDP and ESP on every address until cancelled."""
    loop = asyncio.get_running_loop()
    hosts = ["0.0.0.0", "::"]  # noqa: S104
    servers = [
        await asyncio.start_server(_tcp, host=hosts, port=port),
        await asyncio.start_server(_http, host=hosts, port=HTTP_PORT),
    ]
    for family in (socket.AF_INET, socket.AF_INET6):
        udp = _answering(family, socket.SOCK_DGRAM, port)
        loop.add_reader(udp, _udp_reply, udp)
        esp = _answering(family, socket.SOCK_RAW, 0)
        loop.add_reader(esp, _esp_reply, esp)
    await asyncio.gather(*(server.serve_forever() for server in servers))


def tcp(host: str, port: int) -> Seen:
    """Connect and return what the server saw."""
    with socket.create_connection((host, port), timeout=TIMEOUT) as sock:
        return _decode(sock.makefile().readline())


def connect(host: str, port: int) -> Seen:
    """Open a TCP connection to any server; return whether it was accepted."""
    try:
        with socket.create_connection((host, port), timeout=TIMEOUT):
            return {"connection": "accepted"}
    except ConnectionRefusedError:
        return {"connection": "refused"}
    except TimeoutError:
        return {"connection": "unanswered"}


def udp(host: str, port: int, *, source_port: int = 0, big: bool = False) -> Seen:
    """Send one datagram (from ``source_port``) and return what the server saw.

    ``size`` and ``from`` describe the answer: its length and its source.
    """
    with socket.socket(_family(host), socket.SOCK_DGRAM) as sock:
        sock.settimeout(TIMEOUT)
        sock.bind(("", source_port))
        sock.sendto(b"big" if big else b"whoami", (host, port))
        data, (source, *_) = sock.recvfrom(65535)
    return _decode(data) | {"size": len(data), "from": source}


def esp(host: str, spi: int) -> Seen:
    """Send one ESP packet with ``spi`` and return what the server saw."""
    with socket.socket(_family(host), socket.SOCK_RAW, socket.IPPROTO_ESP) as sock:
        sock.settimeout(TIMEOUT)
        sock.sendto(ESP_HEADER.pack(spi, 1) + b"whoami", (host, 0))
        while True:
            packet, (source, *_) = sock.recvfrom(65535)
            packet = _esp_payload(sock, packet)
            if source == host and ESP_HEADER.unpack_from(packet) == (spi, 2):
                return _decode(packet[ESP_HEADER.size :])


def listen(port: int, *, ipv6: bool = False, timeout: float = TIMEOUT * 6) -> Seen:
    """Wait for one datagram on ``port`` and return its source and payload."""
    with socket.socket(socket.AF_INET6 if ipv6 else socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        sock.bind(("", port))
        data, (host, source_port, *_) = sock.recvfrom(65535)
    return {"address": host, "port": source_port, "payload": data.decode()}


def send(host: str, port: int, payload: str, *, bind: str = "") -> Seen:
    """Send one datagram (from address ``bind``) and return the local port it left from."""
    with socket.socket(_family(host), socket.SOCK_DGRAM) as sock:
        sock.bind((bind, 0))
        sock.sendto(payload.encode(), (host, port))
        return {"port": sock.getsockname()[1]}


def _checksum(data: bytes) -> int:
    """Return the Internet checksum (RFC 1071) of ``data``."""
    padded = data + b"\0" * (len(data) % 2)
    total = int(sum(struct.unpack(f"!{len(padded) // 2}H", padded)))
    total = (total >> 16) + (total & 0xFFFF)
    return ~(total + (total >> 16)) & 0xFFFF


def inject(interface: str, mac: str, source: str, destination: str, port: int) -> Seen:
    """Put an IPv4/UDP frame for ``destination`` on ``interface``, addressed to ``mac``."""
    addresses = socket.inet_aton(source) + socket.inet_aton(destination)
    payload = b"spoofed"
    udp_header = struct.pack("!HHHH", 40000, port, 8 + len(payload), 0)
    pseudo = addresses + struct.pack("!BBH", 0, socket.IPPROTO_UDP, len(udp_header) + len(payload))
    udp_header = udp_header[:6] + struct.pack("!H", _checksum(pseudo + udp_header + payload))
    header = struct.pack("!BBHHHBBH", 0x45, 0, 20 + len(udp_header) + len(payload), 0, 0, 64, 17, 0)
    header = header[:10] + struct.pack("!H", _checksum(header + addresses)) + addresses
    with socket.socket(socket.AF_PACKET, socket.SOCK_RAW) as sock:
        sock.bind((interface, 0))
        frame = bytes.fromhex(mac.replace(":", "")) + sock.getsockname()[4] + b"\x08\x00"
        sent = sock.send(frame + header + udp_header + payload)
    return {"size": sent}


def _skip_name(message: bytes, offset: int) -> int:
    """Return the offset after a DNS name: labels up to an empty one, or a pointer."""
    length = message[offset]
    if length == 0:
        return offset + 1
    if length >= DNS_POINTER:
        return offset + 2
    return _skip_name(message, offset + 1 + length)


def _exchange(sock: socket.socket, query: bytes, address: tuple[str, int]) -> bytes:
    """Send ``query`` and return the answer, retrying the same query as a stub resolver does.

    dnsmasq, with strict-order, moves on to its next server only when a client
    asks again.
    """
    for _ in range(RESOLVE_ATTEMPTS - 1):
        sock.sendto(query, address)
        with contextlib.suppress(TimeoutError):
            return sock.recv(65535)
    sock.sendto(query, address)
    return sock.recv(65535)


def resolve(name: str, server: str, kind: str, *, port: int = 53) -> Seen:
    """Ask ``server`` for the ``kind`` records of ``name``; return the rcode and answers."""
    ident = os.getpid() & 0xFFFF
    question = b"".join(bytes([len(label)]) + label.encode() for label in name.split("."))
    query = DNS_HEADER.pack(ident, 0x0100, 1, 0, 0, 0) + question + b"\0"
    query += struct.pack("!HH", DNS_TYPES[kind], 1)
    with socket.socket(_family(server), socket.SOCK_DGRAM) as sock:
        sock.settimeout(RESOLVE_WAIT)
        message = _exchange(sock, query, (server, port))
    _, flags, questions, count, _, _ = DNS_HEADER.unpack_from(message)
    offset = DNS_HEADER.size
    for _ in range(questions):
        offset = _skip_name(message, offset) + 4
    answers = []
    for _ in range(count):
        offset = _skip_name(message, offset)
        kind_code, _, _, length = struct.unpack_from("!HHIH", message, offset)
        offset += 10
        if kind_code == DNS_TYPES[kind]:
            family = socket.AF_INET6 if kind == "AAAA" else socket.AF_INET
            answers.append(socket.inet_ntop(family, message[offset : offset + length]))
        offset += length
    return {"rcode": flags & 0x0F, "answers": answers}


def _dhcp6_options(data: bytes) -> dict[int, bytes]:
    options: dict[int, bytes] = {}
    offset = 0
    while offset + DHCP6_OPTION.size <= len(data):
        code, length = DHCP6_OPTION.unpack_from(data, offset)
        offset += DHCP6_OPTION.size
        options[code] = data[offset : offset + length]
        offset += length
    return options


def _dhcp6_option(code: int, data: bytes) -> bytes:
    return DHCP6_OPTION.pack(code, len(data)) + data


def solicit_prefix(interface: str) -> Seen:
    """Solicit a delegated prefix on ``interface``; return the first offer."""
    duid = struct.pack("!HH6s", 3, 1, bytes.fromhex("020000000001"))  # DUID-LL, made up
    message = bytes([SOLICIT]) + os.urandom(3)
    message += _dhcp6_option(CLIENT_ID, duid)
    message += _dhcp6_option(ELAPSED_TIME, b"\0\0")
    message += _dhcp6_option(IA_PD, struct.pack("!III", 1, 0, 0))
    message += _dhcp6_option(ORO, struct.pack("!H", DNS_SERVERS))
    with socket.socket(socket.AF_INET6, socket.SOCK_DGRAM) as sock:
        sock.settimeout(TIMEOUT * 2)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, interface.encode())
        sock.bind(("::", 546))
        sock.sendto(message, (DHCP6_SERVERS, 547, 0, socket.if_nametoindex(interface)))
        while (reply := sock.recv(65535))[:4] != bytes([ADVERTISE]) + message[1:4]:
            pass
    options = _dhcp6_options(reply[4:])
    prefix = _dhcp6_options(options[IA_PD][12:])[IA_PREFIX]
    servers = options.get(DNS_SERVERS, b"")
    return {
        "prefix": f"{ipaddress.IPv6Address(prefix[9:25])}/{prefix[8]}",
        "dns": [
            str(ipaddress.IPv6Address(servers[i : i + 16])) for i in range(0, len(servers), 16)
        ],
    }


def solicit_router(interface: str) -> Seen:
    """Send a Router Solicitation on ``interface`` (RFC 4861), as a host does when attaching."""
    with socket.socket(socket.AF_INET6, socket.SOCK_RAW, socket.IPPROTO_ICMPV6) as sock:
        sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_MULTICAST_HOPS, 255)
        sock.sendto(
            bytes([ROUTER_SOLICITATION, 0, 0, 0, 0, 0, 0, 0]),
            (ROUTERS, 0, 0, socket.if_nametoindex(interface)),
        )
    return {"sent": ROUTERS}


def main() -> None:
    """Command line: ``serve``, or one client probe printing JSON."""
    parser = argparse.ArgumentParser(prog="netprobe", description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(required=True)

    def command(
        name: str, run: Callable[[argparse.Namespace], Seen | None], *arguments: Argument
    ) -> None:
        sub = commands.add_parser(name)
        for flag, options in arguments:
            sub.add_argument(flag, **options)
        sub.set_defaults(run=run)

    host: Argument = ("host", {})
    port: Argument = ("--port", {"type": int, "default": PORT})
    command("serve", lambda a: asyncio.run(serve(a.port)), port)
    command("tcp", lambda a: tcp(a.host, a.port), host, port)
    command(
        "connect",
        lambda a: connect(a.host, a.port),
        host,
        ("--port", {"type": int, "required": True}),
    )
    command(
        "udp",
        lambda a: udp(a.host, a.port, source_port=a.source_port, big=a.big),
        host,
        port,
        ("--source-port", {"type": int, "default": 0}),
        ("--big", {"action": "store_true"}),
    )
    command(
        "esp",
        lambda a: esp(a.host, a.spi),
        host,
        ("--spi", {"type": lambda value: int(value, 0), "default": 0x1000}),
    )
    command(
        "send",
        lambda a: send(a.host, a.port, a.payload, bind=a.bind),
        host,
        port,
        ("--payload", {"default": "hello"}),
        ("--bind", {"default": ""}),
    )
    command(
        "listen",
        lambda a: listen(a.port, ipv6=a.ipv6, timeout=a.timeout),
        ("--port", {"type": int, "required": True}),
        ("--ipv6", {"action": "store_true"}),
        ("--timeout", {"type": float, "default": TIMEOUT * 6}),
    )
    command(
        "resolve",
        lambda a: resolve(a.name, a.server, a.type, port=a.port),
        ("name", {}),
        ("--server", {"required": True}),
        ("--port", {"type": int, "default": 53}),
        ("--type", {"default": "A"}),
    )
    command("solicit-prefix", lambda a: solicit_prefix(a.interface), ("interface", {}))
    command("solicit-router", lambda a: solicit_router(a.interface), ("interface", {}))
    command(
        "inject",
        lambda a: inject(a.interface, a.mac, a.source, a.destination, a.port),
        ("interface", {}),
        ("--mac", {"required": True}),
        ("--source", {"required": True}),
        ("--destination", {"required": True}),
        ("--port", {"type": int, "required": True}),
    )
    args = parser.parse_args()
    if (result := args.run(args)) is not None:
        json.dump(result, sys.stdout)


if __name__ == "__main__":
    main()
