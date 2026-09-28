"""Unit tests of wrt_tests.bpf: the hand-written eBPF object is well-formed ELF."""

import struct

from wrt_tests.bpf import EM_BPF, PASS_PROGRAM, PROGRAM_SECTION, tcx_object

EHDR = struct.Struct("<16sHHIQQQIHHHHHH")
SHDR = struct.Struct("<IIQQQQIIQQ")
SYM = struct.Struct("<IBBHQQ")


def _sections(image: bytes) -> dict[str, tuple[int, bytes, int, int]]:
    """Map section names to (type, data, link, info)."""
    fields = EHDR.unpack_from(image)
    shoff, shnum, shstrndx = fields[6], fields[12], fields[13]
    headers = [SHDR.unpack_from(image, shoff + index * SHDR.size) for index in range(shnum)]
    names = headers[shstrndx]
    names_data = image[names[4] : names[4] + names[5]]
    sections: dict[str, tuple[int, bytes, int, int]] = {}
    for name, kind, _, _, offset, size, link, info, _, _ in headers[1:]:
        label = names_data[name : names_data.index(b"\0", name)].decode()
        sections[label] = (int(kind), image[offset : offset + size], int(link), int(info))
    return sections


def test_header_is_a_bpf_relocatable_object() -> None:
    ident, kind, machine, *_ = EHDR.unpack_from(tcx_object())
    assert ident[:7] == b"\x7fELF\x02\x01\x01"
    assert (kind, machine) == (1, EM_BPF)


def test_program_license_and_symbol() -> None:
    sections = _sections(tcx_object("probe"))
    assert sections[PROGRAM_SECTION][1] == PASS_PROGRAM
    assert sections["license"][1] == b"GPL\0"
    _, symtab, link, info = sections[".symtab"]
    assert (link, info) == (4, 1)
    name, st_info, _, shndx, value, size = SYM.unpack_from(symtab, SYM.size)
    strtab = sections[".strtab"][1]
    assert strtab[name : strtab.index(b"\0", name)] == b"probe"
    assert (st_info, shndx, value, size) == (0x12, 1, 0, len(PASS_PROGRAM))
