from __future__ import annotations
import hashlib
from collections import defaultdict
from .models import Dataset, Issue, Origin
from .normalize import key


def _ref(kind: str, value: str) -> str:
    # Avoid placing direct personnel identifiers into routine logs/reports.
    digest = hashlib.sha256((kind + ":" + value).encode("utf-8")).hexdigest()[:12]
    return f"{kind}:{digest}"


def _is_named_position_type(value: str) -> bool:
    """Recognize approved named-position variants such as «بانام ایثار»."""
    compact = key(value).replace(" ", "")
    return compact.startswith("بانام")


def reconcile(
    ds: Dataset,
    expected_fixed: int | None = None,
    expected_named: int | None = None,
    expected_personnel: int | None = None,
) -> Dataset:
    people: dict[str, list] = defaultdict(list)
    national: dict[str, list] = defaultdict(list)
    positions: dict[str, list] = defaultdict(list)
    person_positions: dict[str, set[str]] = defaultdict(set)

    for p in ds.persons:
        if not p.personnel_no:
            ds.issues.append(Issue("error", "MISSING_PERSONNEL_NO", "Person row has no personnel number.", p.origin))
        else:
            people[p.personnel_no].append(p)
        if p.national_id:
            national[p.national_id].append(p)
        if p.personnel_no and p.position_no:
            person_positions[p.personnel_no].add(p.position_no)

    for value, rows in people.items():
        if len(rows) > 1:
            ds.issues.append(Issue("error", "DUPLICATE_PERSONNEL_NO", f"Personnel number appears {len(rows)} times.", rows[0].origin, _ref("person", value)))
    for value, rows in national.items():
        if len(rows) > 1:
            names = {key(f"{row.first_name} {row.last_name}") for row in rows}
            sources = {row.origin.file if row.origin else "" for row in rows}
            if len(names) == 1 and "" not in names and len(sources) > 1:
                ds.issues.append(Issue(
                    "warning", "CROSS_SOURCE_NATIONAL_ID",
                    "The same named person appears under different personnel numbers in separate employment sources; both employment records are preserved.",
                    rows[0].origin, _ref("national", value),
                ))
            else:
                ds.issues.append(Issue("error", "DUPLICATE_NATIONAL_ID", f"National ID appears {len(rows)} times.", rows[0].origin, _ref("national", value)))

    for pos in ds.positions:
        if not pos.position_no:
            ds.issues.append(Issue("error", "MISSING_POSITION_NO", "Position row has no position number.", pos.origin))
            continue
        positions[pos.position_no].append(pos)
        if pos.occupant_personnel_no:
            person_positions[pos.occupant_personnel_no].add(pos.position_no)
            if pos.occupant_personnel_no not in people:
                ds.issues.append(Issue("error", "ORPHAN_POSITION_OCCUPANT", "Position occupant is not present in imported personnel rows.", pos.origin, _ref("person", pos.occupant_personnel_no)))

    for value, rows in positions.items():
        if len(rows) > 1:
            ds.issues.append(Issue("error", "DUPLICATE_POSITION_NO", f"Position number appears {len(rows)} times.", rows[0].origin, _ref("position", value)))

    for person_no, pos_set in person_positions.items():
        if len(pos_set) > 1:
            origin: Origin | None = people.get(person_no, [None])[0].origin if people.get(person_no) else None
            ds.issues.append(Issue("warning", "PERSON_MULTIPLE_POSITIONS", f"Person resolves to {len(pos_set)} distinct positions; requires review.", origin, _ref("person", person_no)))

    if expected_fixed is not None or expected_named is not None:
        named = sum(1 for position in ds.positions if _is_named_position_type(position.position_type))
        fixed = len(ds.positions) - named
        if expected_fixed is not None and fixed != expected_fixed:
            ds.issues.append(Issue("error", "FIXED_POSITION_COUNT_MISMATCH", f"Fixed positions: imported={fixed}, expected={expected_fixed}."))
        if expected_named is not None and named != expected_named:
            ds.issues.append(Issue("error", "NAMED_POSITION_COUNT_MISMATCH", f"Named positions: imported={named}, expected={expected_named}."))
    if expected_personnel is not None and len(ds.persons) != expected_personnel:
        ds.issues.append(Issue(
            "error", "PERSONNEL_COUNT_MISMATCH",
            f"Personnel records: imported={len(ds.persons)}, expected={expected_personnel}.",
        ))
    return ds


def summary(ds: Dataset) -> dict:
    errors = sum(1 for i in ds.issues if i.severity == "error")
    warnings = sum(1 for i in ds.issues if i.severity == "warning")
    return {
        "source_files": len(ds.source_files),
        "source_rows": ds.source_rows,
        "persons": len(ds.persons),
        "positions": len(ds.positions),
        "counties": len(ds.counties),
        "enrichment_rows": ds.enrichment_rows,
        "enrichment_applied": ds.enrichment_applied,
        "ignored_rows": ds.ignored_rows,
        "errors": errors,
        "warnings": warnings,
        "eligible_for_staging": errors == 0,
    }
