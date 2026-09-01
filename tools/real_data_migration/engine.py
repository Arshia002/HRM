from __future__ import annotations
from collections import defaultdict
from pathlib import Path
import re
from .models import County, Dataset, Issue, Origin, Person, Position
from .normalize import digits, key, text
from .readers import ReaderError, read_records

SUPPORTED = {".csv", ".xlsx", ".xls"}


def _profile(filename: str) -> str:
    k = key(filename)
    if "پستبانام" in k:
        return "named_positions"
    if "شهرستان" in k:
        # The approved private workbook named "شهرستان" is not an independent
        # population source.  Its first sheet repeats the contractor workbook;
        # the compact sheet enriches 590 existing personnel with an organization
        # unit.  Treating it as people caused 590 false duplicate errors in a1.
        return "person_enrichment"
    if "رسمی" in k:
        return "persons"
    if any(token in k for token in ("شرکتی", "حجمی", "پیمانکاری")):
        return "persons"
    return "auto"


def _origin(path: Path, sheet: str, row: int) -> Origin:
    return Origin(path.name, sheet, row)


def _identifier(value: object) -> str:
    normalized = text(value)
    if re.fullmatch(r"[0-9\s./-]+", normalized):
        normalized = digits(normalized)
    return "" if normalized and set(normalized) == {"0"} else normalized


def _primary_person_records(records: list[tuple[str, int, dict[str, str]]]) -> list[tuple[str, int, dict[str, str]]]:
    """Choose the richest sheet when a workbook contains compact duplicates."""
    by_sheet: dict[str, list[tuple[str, int, dict[str, str]]]] = defaultdict(list)
    for record in records:
        by_sheet[record[0]].append(record)
    if len(by_sheet) <= 1:
        return records

    def score(item: tuple[str, list[tuple[str, int, dict[str, str]]]]) -> tuple[int, int, int]:
        _sheet, rows = item
        rich_fields = {
            "national_id", "employment_type", "org_unit", "location", "position_no", "position_title",
        }
        richness = sum(sum(bool(row.get(field)) for field in rich_fields) for _, _, row in rows)
        distinct_people = len({_identifier(row.get("personnel_no", "")) for _, _, row in rows})
        return richness, distinct_people, len(rows)

    return max(by_sheet.items(), key=score)[1]


def _enrichment_records(records: list[tuple[str, int, dict[str, str]]]) -> list[tuple[str, int, dict[str, str]]]:
    """Select the compact personnel/unit mapping, not the repeated full sheet."""
    by_sheet: dict[str, list[tuple[str, int, dict[str, str]]]] = defaultdict(list)
    for record in records:
        by_sheet[record[0]].append(record)
    candidates: list[tuple[tuple[int, int, int], list[tuple[str, int, dict[str, str]]]]] = []
    for rows in by_sheet.values():
        linked = [row for row in rows if _identifier(row[2].get("personnel_no", "")) and text(row[2].get("org_unit"))]
        if not linked:
            continue
        compact = sum(not row.get("national_id") and not row.get("employment_type") for _, _, row in linked)
        candidates.append(((compact, len(linked), -sum(len(row) for _, _, row in linked)), linked))
    return max(candidates, key=lambda item: item[0])[1] if candidates else []


def _normalize_position_type(value: object, *, named_profile: bool = False) -> str:
    normalized = text(value)
    if not normalized or normalized in {"0", "0.0"}:
        return "" if not named_profile else "invalid"
    return normalized


def load_directory(input_dir: Path) -> Dataset:
    ds = Dataset()
    enrichments: dict[str, tuple[str, Origin]] = {}
    if not input_dir.exists():
        ds.issues.append(Issue("error", "INPUT_DIR_MISSING", f"Input directory does not exist: {input_dir}"))
        return ds
    files = sorted(p for p in input_dir.iterdir() if p.is_file() and p.suffix.lower() in SUPPORTED)
    ds.source_files = [p.name for p in files]
    if not files:
        ds.issues.append(Issue("error", "NO_INPUT_FILES", "No .xls/.xlsx/.csv input files were found."))
        return ds

    for path in files:
        profile = _profile(path.name)
        try:
            all_records = list(read_records(path))
        except ReaderError as exc:
            ds.issues.append(Issue("error", "READER_ERROR", str(exc), Origin(path.name, "", 0)))
            continue
        if not all_records:
            ds.issues.append(Issue("warning", "NO_MAPPED_ROWS", "No recognizable tabular rows found.", Origin(path.name, "", 0)))
            continue
        ds.source_rows += len(all_records)
        if profile == "persons":
            records = _primary_person_records(all_records)
        elif profile == "person_enrichment":
            records = _enrichment_records(all_records)
        else:
            records = all_records

        if profile == "person_enrichment":
            for sheet, rownum, r in records:
                pno = _identifier(r.get("personnel_no", ""))
                unit = text(r.get("org_unit"))
                if pno and unit:
                    enrichments[pno] = (unit, _origin(path, sheet, rownum))
                    ds.enrichment_rows += 1
            continue

        for sheet, rownum, r in records:
            o = _origin(path, sheet, rownum)
            pno = _identifier(r.get("personnel_no", ""))
            posno = _identifier(r.get("position_no", ""))
            if profile == "persons":
                is_county, is_person, is_position = False, True, False
            elif profile == "named_positions":
                is_county, is_person, is_position = False, False, True
            else:
                is_county = bool(r.get("county_name") and not pno and not posno)
                is_person = bool(pno or r.get("first_name") or r.get("last_name"))
                is_position = bool(posno or r.get("position_title"))

            if is_county:
                name = text(r.get("county_name") or r.get("location"))
                if name:
                    ds.counties.append(County(name=name, code=text(r.get("county_code")), origin=o))
                continue

            if is_person:
                ds.persons.append(Person(
                    personnel_no=pno,
                    first_name=text(r.get("first_name")),
                    last_name=text(r.get("last_name")),
                    national_id=digits(r.get("national_id", "")),
                    employment_type=text(r.get("employment_type")),
                    org_unit=text(r.get("org_unit")),
                    location=text(r.get("location")),
                    position_no=posno,
                    position_title=text(r.get("position_title")),
                    origin=o,
                ))
            if is_position:
                position_type = _normalize_position_type(r.get("position_type"), named_profile=profile == "named_positions")
                if profile == "named_positions" and position_type == "invalid":
                    ds.ignored_rows += 1
                    ds.issues.append(Issue(
                        "warning",
                        "IGNORED_LEGACY_NAMED_POSITION",
                        "A legacy named-position row marked with type 0 was excluded from active import.",
                        o,
                    ))
                    continue
                ds.positions.append(Position(
                    position_no=posno,
                    title=text(r.get("position_title")),
                    org_unit=text(r.get("org_unit")),
                    location=text(r.get("location")),
                    position_type=position_type or ("بانام" if profile == "named_positions" else ""),
                    occupant_personnel_no=pno,
                    origin=o,
                ))
    people = {person.personnel_no: person for person in ds.persons if person.personnel_no}
    for personnel_no, (unit, origin) in enrichments.items():
        person = people.get(personnel_no)
        if person is None:
            ds.issues.append(Issue(
                "error", "ORPHAN_PERSON_ENRICHMENT",
                "An organization-unit enrichment row does not match imported personnel.",
                origin,
            ))
            continue
        person.org_unit = unit
        ds.enrichment_applied += 1
    return ds
