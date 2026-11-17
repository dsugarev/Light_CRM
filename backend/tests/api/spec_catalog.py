"""Parse the endpoint catalog in docs/05-api-specification.md.

Every table row of the form `| METHOD | `/path` | purpose | access | req |` is
an endpoint. Pipes escaped as `\\|` inside a cell are not column separators.
"""

import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path

SPEC_PATH = Path(__file__).resolve().parents[3] / "docs" / "05-api-specification.md"

_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
_UNESCAPED_PIPE = re.compile(r"(?<!\\)\|")


@dataclass(frozen=True, slots=True)
class CatalogEntry:
    method: str
    path: str
    access: str
    section: str

    @property
    def key(self) -> str:
        return f"{self.method} {self.path}"


@cache
def load_catalog() -> tuple[CatalogEntry, ...]:
    entries: list[CatalogEntry] = []
    section = ""
    for line in SPEC_PATH.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            section = line[3:].strip()
            continue
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in _UNESCAPED_PIPE.split(line)[1:-1]]
        if len(cells) < 4 or cells[0] not in _METHODS:
            continue
        entries.append(
            CatalogEntry(
                method=cells[0],
                path=cells[1].strip("`"),
                access=cells[3].replace("`", ""),
                section=section,
            )
        )
    return tuple(entries)
