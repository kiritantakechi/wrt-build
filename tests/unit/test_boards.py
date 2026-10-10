"""Unit tests of wrt_tests.boards: the board descriptions and their schema."""

import json
import shutil
from typing import TYPE_CHECKING, Any

import pytest

from wrt_tests.boards import BOARDS_DIR, Description, load, load_all
from wrt_tests.data import DataError, read_json

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


def test_the_supported_boards_load() -> None:
    boards = {board.id: board for board in load_all()}
    assert set(boards) == {"r4s", "r6s"}
    assert boards["r4s"].wan.device == "eth0"
    assert [port.device for port in boards["r4s"].lan] == ["eth1"]
    assert boards["r6s"].wan.device == "eth1"
    assert [port.device for port in boards["r6s"].lan] == ["eth0", "eth2"]


def test_the_device_follows_the_board_name() -> None:
    # wrt-sync finds its board's release assets by the device its board name gives.
    for board in load_all():
        assert board.device == board.board_name.replace(",", "_"), board.id


def test_an_unknown_board_names_the_known_ones() -> None:
    with pytest.raises(LookupError, match=r"no board 'r9s' \(boards: r4s, r6s\)"):
        load("r9s")


def _no_cpu(description: dict[str, Any]) -> None:
    del description["cpu"]


def _cores_in_words(description: dict[str, Any]) -> None:
    description["soc"]["cores"][0] = "little"


def _an_id(description: dict[str, Any]) -> None:
    description["id"] = "r6s"


def _two_wan_ports(description: dict[str, Any]) -> None:
    description["ports"][0]["role"] = "wan"


@pytest.mark.parametrize(
    ("breakage", "field"),
    [
        (_no_cpu, "cpu"),
        (_cores_in_words, "soc.cores.0"),
        (_an_id, "id"),
        (_two_wan_ports, "(document)"),
    ],
    ids=["missing field", "wrong type", "id in the file", "two WAN ports"],
)
def test_a_broken_description_is_refused(
    tmp_path: Path, breakage: Callable[[dict[str, Any]], None], field: str
) -> None:
    boards = tmp_path / "boards"
    shutil.copytree(BOARDS_DIR, boards)
    description = read_json(boards / "r6s.json", Description).model_dump(mode="json")
    breakage(description)
    (boards / "r6s.json").write_text(json.dumps(description), encoding="utf-8")
    with pytest.raises(DataError) as refused:
        load("r6s", boards)
    located = {problem.split(": ")[1] for problem in refused.value.problems}
    assert field in located
