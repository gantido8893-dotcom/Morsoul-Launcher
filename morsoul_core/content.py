"""Loads the static game files (JSON) that the rule checks need. Optional: without a content folder
the server skips the checks that need it (known IDs, unlock conditions) and keeps all others."""

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Content:
    cases: dict[str, dict] = field(default_factory=dict)
    clues: dict[str, dict] = field(default_factory=dict)
    tools: dict[str, dict] = field(default_factory=dict)
    sectors: dict[str, dict] = field(default_factory=dict)

    @property
    def loaded(self) -> bool:
        return bool(self.cases or self.clues or self.tools or self.sectors)

    @classmethod
    def empty(cls) -> "Content":
        return cls()

    @classmethod
    def load(cls, directory: Path | None) -> "Content":
        if directory is None or not Path(directory).is_dir():
            return cls.empty()
        d = Path(directory)

        def read(name: str, id_field: str) -> dict[str, dict]:
            p = d / name
            if not p.is_file():
                return {}
            records = json.loads(p.read_text(encoding="utf-8"))
            return {r[id_field]: r for r in records}

        return cls(
            cases=read("cases.json", "caseID"),
            clues=read("clues.json", "clueID"),
            tools=read("abilities.json", "toolID"),
            sectors=read("sectors.json", "sectorID"),
        )
