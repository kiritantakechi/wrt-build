"""The data files' readers (module-boundaries D7): every problem names its file, entry and field."""

import json
from typing import TYPE_CHECKING, Annotated

import pytest
from pydantic import BaseModel, ConfigDict, Field

from wrt_tests.data import DataError, read_json, read_toml, write_json

if TYPE_CHECKING:
    from pathlib import Path


class _Part(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    name: Annotated[str, Field(min_length=1)]
    size: int


class _Assembly(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    name: str
    part: _Part


DISK = _Part(name="disk", size=8)
FAN = _Part(name="fan", size=1)
PART = DISK.model_dump()


def _json(tmp_path: Path, document: object) -> Path:
    path = tmp_path / "data.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _toml(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "data.toml"
    path.write_text(text, encoding="utf-8")
    return path


def _problems(error: pytest.ExceptionInfo[DataError]) -> tuple[str, ...]:
    return error.value.problems


def test_a_json_document_reads_as_its_model(tmp_path: Path) -> None:
    path = _json(tmp_path, {"name": "router", "part": PART})
    assert read_json(path, _Assembly) == _Assembly(name="router", part=DISK)


def test_a_json_list_reads_as_a_list_of_its_model(tmp_path: Path) -> None:
    path = _json(tmp_path, [PART, FAN.model_dump()])
    assert read_json(path, list[_Part]) == [DISK, FAN]


@pytest.mark.parametrize(
    ("document", "problem"),
    [
        ({"name": "router", "part": {**PART, "colour": "red"}}, "part.colour: Extra inputs"),
        ({"name": "router", "part": {**PART, "size": "8"}}, "part.size: Input should be"),
        ({"name": "router", "part": {"name": "disk"}}, "part.size: Field required"),
    ],
    ids=["unknown field", "wrong type", "missing field"],
)
def test_a_json_document_names_the_field(tmp_path: Path, document: object, problem: str) -> None:
    path = _json(tmp_path, document)
    with pytest.raises(DataError) as error:
        read_json(path, _Assembly)
    (found,) = _problems(error)
    assert found.startswith(f"{path}: {problem}")


@pytest.mark.parametrize(
    ("entry", "problem"),
    [
        ({**PART, "colour": "red"}, "[1]: colour: Extra inputs"),
        ({**PART, "size": "8"}, "[1]: size: Input should be"),
        ({"name": "disk"}, "[1]: size: Field required"),
    ],
    ids=["unknown field", "wrong type", "missing field"],
)
def test_a_json_list_names_the_entry_and_the_field(
    tmp_path: Path, entry: dict[str, object], problem: str
) -> None:
    path = _json(tmp_path, [PART, entry])
    with pytest.raises(DataError) as error:
        read_json(path, list[_Part])
    (found,) = _problems(error)
    assert found.startswith(f"{path}: {problem}")


def test_a_toml_table_reads_as_a_list_of_its_model(tmp_path: Path) -> None:
    path = _toml(
        tmp_path, '[[part]]\nname = "disk"\nsize = 8\n\n[[part]]\nname = "fan"\nsize = 1\n'
    )
    assert read_toml(path, "part", _Part) == [DISK, FAN]


def test_a_toml_file_without_the_table_has_no_entries(tmp_path: Path) -> None:
    assert read_toml(_toml(tmp_path, "# nothing reviewed yet\n"), "part", _Part) == []


@pytest.mark.parametrize(
    ("entry", "problem"),
    [
        ('name = "fan"\nsize = 1\ncolour = "red"\n', "part[1]: colour: Extra inputs"),
        ('name = "fan"\nsize = "1"\n', "part[1]: size: Input should be"),
        ('name = "fan"\n', "part[1]: size: Field required"),
    ],
    ids=["unknown field", "wrong type", "missing field"],
)
def test_a_toml_table_names_the_entry_and_the_field(
    tmp_path: Path, entry: str, problem: str
) -> None:
    path = _toml(tmp_path, f'[[part]]\nname = "disk"\nsize = 8\n\n[[part]]\n{entry}')
    with pytest.raises(DataError) as error:
        read_toml(path, "part", _Part)
    (found,) = _problems(error)
    assert found.startswith(f"{path}: {problem}")


def test_a_toml_file_with_another_table_names_it(tmp_path: Path) -> None:
    path = _toml(tmp_path, '[[part]]\nname = "disk"\nsize = 8\n\n[[parts]]\nname = "fan"\n')
    with pytest.raises(DataError) as error:
        read_toml(path, "part", _Part)
    assert _problems(error) == (f"{path}: parts: not an entry of [[part]]",)


def test_a_toml_table_that_is_not_an_array_names_it(tmp_path: Path) -> None:
    path = _toml(tmp_path, '[part]\nname = "disk"\nsize = 8\n')
    with pytest.raises(DataError) as error:
        read_toml(path, "part", _Part)
    assert _problems(error) == (f"{path}: part: not an array of tables ([[part]])",)


def test_a_written_document_reads_back(tmp_path: Path) -> None:
    path = tmp_path / "data.json"
    write_json(path, _Assembly(name="router", part=DISK))
    assert read_json(path, _Assembly) == _Assembly(name="router", part=DISK)


def test_a_written_document_is_a_file_of_its_own(tmp_path: Path) -> None:
    original = _json(tmp_path, PART)
    linked = tmp_path / "linked.json"
    linked.hardlink_to(original)
    write_json(linked, FAN)
    assert read_json(original, _Part) == DISK
    assert read_json(linked, _Part) == FAN
