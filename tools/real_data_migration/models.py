from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass(frozen=True)
class Origin:
    file: str
    sheet: str
    row: int


@dataclass
class Issue:
    severity: str
    code: str
    message: str
    origin: Origin | None = None
    entity_ref: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if self.origin is None:
            d["origin"] = None
        return d


@dataclass
class Person:
    personnel_no: str
    first_name: str = ""
    last_name: str = ""
    national_id: str = ""
    employment_type: str = ""
    org_unit: str = ""
    location: str = ""
    position_no: str = ""
    position_title: str = ""
    origin: Origin | None = None


@dataclass
class Position:
    position_no: str
    title: str = ""
    org_unit: str = ""
    location: str = ""
    position_type: str = ""
    occupant_personnel_no: str = ""
    origin: Origin | None = None


@dataclass
class County:
    name: str
    code: str = ""
    origin: Origin | None = None


@dataclass
class Dataset:
    persons: list[Person] = field(default_factory=list)
    positions: list[Position] = field(default_factory=list)
    counties: list[County] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    source_rows: int = 0
    source_files: list[str] = field(default_factory=list)
    enrichment_rows: int = 0
    enrichment_applied: int = 0
    ignored_rows: int = 0
