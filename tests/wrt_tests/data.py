"""The one way to read a data file: through its schema (module-boundaries D7).

``read_json`` reads a JSON document and ``read_toml`` the entries of a TOML
file's array of tables, each as the schema it is given: pydantic models strict
about unknown fields and types. Both raise ``DataError``, which names the file,
the entry (its index) and the field of every problem.
"""

import tomllib
from typing import TYPE_CHECKING, get_origin

from pydantic import BaseModel, TypeAdapter, ValidationError

if TYPE_CHECKING:
    from pathlib import Path

type Location = tuple[int | str, ...]


class DataError(ValueError):
    """A data file that does not match its schema: one line per problem."""

    def __init__(self, problems: list[str]) -> None:
        """Hold ``problems``, each naming its file, entry and field."""
        super().__init__("\n".join(problems))
        self.problems = tuple(problems)


def _where(location: Location, entries: str | None) -> str:
    """Name where a problem lies: its field, after its entry in a file of entries.

    ``entries`` names the entries of such a file by their index, as ``"[{}]"``
    or ``"warning[{}]"`` do; it is None for a file that is one document.
    """
    if entries is None or not location:
        return ".".join(map(str, location)) or "(document)"
    entry, *field = location
    return f"{entries.format(entry)}: {'.'.join(map(str, field)) or '(entry)'}"


def _problems(
    path: Path, error: ValidationError, entries: str | None, at: Location = ()
) -> list[str]:
    """Render ``error``'s problems, each at its location after ``at``."""
    return [
        f"{path}: {_where((*at, *detail['loc']), entries)}: {detail['msg']}"
        for detail in error.errors()
    ]


def read_json[T](path: Path, schema: type[T]) -> T:
    """Return the JSON document of ``path`` as ``schema``: a model, or a list of one."""
    entries = "[{}]" if get_origin(schema) is list else None
    try:
        return TypeAdapter(schema).validate_json(path.read_bytes())
    except ValidationError as error:
        raise DataError(_problems(path, error, entries)) from None


def write_json(path: Path, record: BaseModel) -> None:
    """Write ``record`` to ``path`` as a JSON document, as ``read_json`` reads it back.

    The document replaces ``path`` whole, as a file of its own: a file linked to
    the one it replaces keeps what that one held.
    """
    staged = path.with_name(f".{path.name}.new")
    staged.write_text(record.model_dump_json(indent=2, exclude_none=True) + "\n", encoding="utf-8")
    staged.replace(path)


def read_toml[M: BaseModel](path: Path, table: str, model: type[M]) -> list[M]:
    """Return the entries of ``path``'s array of tables ``table`` as ``model``.

    The file holds that array alone; a file without it has no entries.
    """
    try:
        document = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        raise DataError([f"{path}: {error}"]) from None
    if others := sorted(set(document) - {table}):
        raise DataError([f"{path}: {key}: not an entry of [[{table}]]" for key in others])
    entries = document.get(table, [])
    if not isinstance(entries, list):
        raise DataError([f"{path}: {table}: not an array of tables ([[{table}]])"])
    read: list[M] = []
    problems: list[str] = []
    for index, entry in enumerate(entries):
        try:
            read.append(model.model_validate(entry))
        except ValidationError as error:
            problems += _problems(path, error, f"{table}[{{}}]", (index,))
    if problems:
        raise DataError(problems)
    return read
