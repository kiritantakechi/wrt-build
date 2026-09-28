"""A minimal eBPF object file, written without a compiler.

The kernel spec asks for a tcx program to be attached on the router. Compiling one
needs a clang with the BPF backend, which Apple's clang lacks, and device tests may
run from macOS. The program is two instructions, so the ELF relocatable object that
libbpf (bpftool) loads is written here directly: a ``tcx/ingress`` section with
the code (libbpf derives the program and attach type from that name), a
``license`` section, and a symbol table naming the program.
"""

import struct

EM_BPF = 247
ET_REL = 1
SHT_PROGBITS, SHT_SYMTAB, SHT_STRTAB = 1, 2, 3
SHF_WRITE, SHF_ALLOC, SHF_EXECINSTR = 1, 2, 4
STB_GLOBAL, STT_FUNC = 1, 2

_EHDR = struct.Struct("<16sHHIQQQIHHHHHH")
_SHDR = struct.Struct("<IIQQQQIIQQ")
_SYM = struct.Struct("<IBBHQQ")
_INSN = struct.Struct("<BBhi")

# r0 = -1 (TCX_NEXT: let the next program or the stack have the packet); exit
PASS_PROGRAM = _INSN.pack(0xB7, 0, 0, -1) + _INSN.pack(0x95, 0, 0, 0)


def _strtab(*names: str) -> tuple[bytes, dict[str, int]]:
    table = b"\0"
    offsets: dict[str, int] = {}
    for name in names:
        offsets[name] = len(table)
        table += name.encode() + b"\0"
    return table, offsets


def _align(offset: int, alignment: int) -> int:
    return -(-offset // alignment) * alignment


PROGRAM_SECTION = "tcx/ingress"


def tcx_object(program: str = "wrt_pass", code: bytes = PASS_PROGRAM) -> bytes:
    """Return an ELF object with one ``SEC("tcx/ingress")`` program named ``program``."""
    section_names = (PROGRAM_SECTION, "license", ".symtab", ".strtab", ".shstrtab")
    shstrtab, name_of = _strtab(*section_names)
    strtab, symbol_of = _strtab(program)
    symtab = _SYM.pack(0, 0, 0, 0, 0, 0) + _SYM.pack(
        symbol_of[program], STB_GLOBAL << 4 | STT_FUNC, 0, 1, 0, len(code)
    )
    # (name, type, flags, data, alignment, link, info, entry size); index = position + 1
    sections = (
        (PROGRAM_SECTION, SHT_PROGBITS, SHF_ALLOC | SHF_EXECINSTR, code, 8, 0, 0, 0),
        ("license", SHT_PROGBITS, SHF_ALLOC | SHF_WRITE, b"GPL\0", 1, 0, 0, 0),
        (".symtab", SHT_SYMTAB, 0, symtab, 8, 4, 1, _SYM.size),
        (".strtab", SHT_STRTAB, 0, strtab, 1, 0, 0, 0),
        (".shstrtab", SHT_STRTAB, 0, shstrtab, 1, 0, 0, 0),
    )

    body = bytearray()
    headers = [_SHDR.pack(0, 0, 0, 0, 0, 0, 0, 0, 0, 0)]
    for name, kind, flags, data, alignment, link, info, entsize in sections:
        offset = _align(_EHDR.size + len(body), alignment)
        body += bytes(offset - _EHDR.size - len(body)) + data
        headers.append(
            _SHDR.pack(
                name_of[name], kind, flags, 0, offset, len(data), link, info, alignment, entsize
            )
        )
    section_offset = _align(_EHDR.size + len(body), 8)
    body += bytes(section_offset - _EHDR.size - len(body))

    ident = b"\x7fELF" + bytes([2, 1, 1]) + bytes(9)  # 64-bit, little-endian, version 1
    header = _EHDR.pack(
        ident,
        ET_REL,
        EM_BPF,
        1,  # e_version
        0,  # e_entry
        0,  # e_phoff: no program headers
        section_offset,
        0,  # e_flags
        _EHDR.size,
        0,  # e_phentsize
        0,  # e_phnum
        _SHDR.size,
        len(headers),
        section_names.index(".shstrtab") + 1,
    )
    return header + bytes(body) + b"".join(headers)
