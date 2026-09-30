"""The supported boards (board-model D1): one description per board under ``boards/``.

A description declares every fact that differs between boards: the OpenWrt
device and board name, the SoC and its loader, the CPU tuning, the U-Boot
variant, the boot disk, the ports with their roles and drivers, and how the
emulator stands in for the board. The board's id is the file's name.

``Board`` is their schema, strict about unknown fields and types. ``board-check``
(``just check boards``) checks every description with it.
"""

import argparse
import sys
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

REPO_DIR = Path(__file__).resolve().parents[2]
BOARDS_DIR = REPO_DIR / "boards"


class _Facts(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class Loader(_Facts):
    """The signature of the SoC's loader, at its offset in the loader (sector 64 on)."""

    signature: Annotated[str, Field(min_length=4, max_length=4)]
    offset: Annotated[int, Field(ge=0)]


class Soc(_Facts):
    """The SoC: its device-tree compatible and the loader its boot ROM runs."""

    compatible: str
    loader: Loader


class UBoot(_Facts):
    """The board's U-Boot: its uboot-rockchip variant, and where its environment is built."""

    variant: str
    env_dir: str


class Port(_Facts):
    """A network port: its Linux device and its role."""

    device: Annotated[str, Field(pattern=r"^eth[0-9]+$")]
    role: Literal["wan", "lan"]


class Drivers(_Facts):
    """The kernel drivers of the board's ports, by the bus they register on."""

    platform: tuple[str, ...]
    pci: tuple[str, ...]


class Emulator(_Facts):
    """How the emulator stands in for the board: CPU model, cores and memory."""

    cpu: str
    cores: Annotated[int, Field(gt=0)]
    memory: Annotated[str, Field(pattern=r"^[0-9]+[MG]$")]


class Description(_Facts):
    """A board description, as its file holds it."""

    model: str
    device: str
    board_name: str
    soc: Soc
    cpu: str
    uboot: UBoot
    boot_disk: Literal["sd", "emmc"]
    ports: tuple[Port, ...]
    drivers: Drivers
    dt_enabled: tuple[str, ...]
    emulator: Emulator

    @model_validator(mode="after")
    def _port_roles(self) -> Self:
        roles = [port.role for port in self.ports]
        if roles.count("wan") != 1 or "lan" not in roles:
            msg = "the ports are one wan port and at least one lan port"
            raise ValueError(msg)
        if len({port.device for port in self.ports}) != len(self.ports):
            msg = "every port has a device of its own"
            raise ValueError(msg)
        return self


class Board(Description):
    """A supported board: its description and its id, the description file's name."""

    id: str

    @property
    def wan(self) -> Port:
        """The WAN port."""
        (wan,) = (port for port in self.ports if port.role == "wan")
        return wan

    @property
    def lan(self) -> tuple[Port, ...]:
        """The LAN ports, in the board's order."""
        return tuple(port for port in self.ports if port.role == "lan")


def load(board: str, directory: Path = BOARDS_DIR) -> Board:
    """Return the description of ``board`` (its id)."""
    path = directory / f"{board}.json"
    if not path.is_file():
        known = ", ".join(sorted(p.stem for p in directory.glob("*.json")))
        msg = f"no board {board!r} (boards: {known})"
        raise LookupError(msg)
    description = Description.model_validate_json(path.read_text())
    return Board.model_validate({"id": board, **dict(description)})


def load_all(directory: Path = BOARDS_DIR) -> tuple[Board, ...]:
    """Return every board's description, by id."""
    return tuple(load(path.stem, directory) for path in sorted(directory.glob("*.json")))


def _errors(path: Path, error: ValidationError) -> list[str]:
    return [
        f"{path.name}: {'.'.join(map(str, detail['loc'])) or '(description)'}: {detail['msg']}"
        for detail in error.errors()
    ]


def main(argv: list[str] | None = None) -> int:
    """Check every board description; print each problem with its board and field."""
    parser = argparse.ArgumentParser(prog="board-check", description=__doc__.splitlines()[0])
    parser.add_argument("--boards", type=Path, default=BOARDS_DIR, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    problems: list[str] = []
    paths = sorted(args.boards.glob("*.json"))
    if not paths:
        problems.append(f"{args.boards}: no board descriptions")
    for path in paths:
        try:
            load(path.stem, args.boards)
        except ValidationError as error:
            problems += _errors(path, error)
    for problem in problems:
        print(f"error: {problem}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
