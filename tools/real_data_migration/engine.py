from __future__ import annotations
from pathlib import Path
from .models import County, Dataset, Issue, Origin, Person, Position
from .normalize import digits, key, text
from .readers import ReaderError, read_records

SUPPORTED = {".csv", ".xlsx", ".xls"}


def _profile(filename: str) -> str:
    k = key(filename)
    if "پستبانام" in k or "پستبانام" in k:
        return "named_positions"
    if "شهرستان" in k:
        return "counties"
    if "رسمی" in k:
        return "persons"
    if any(token in k for token in ("شرکتی", "حجمی", "پیمانکاری")):
        return "persons"
    return "auto"


def _origin(path: Path, sheet: str, row: int) -> Origin:
    return Origin(path.name, sheet, row)


def load_directory(input_dir: Path) -> Dataset:
    ds = Dataset()
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
            records = list(read_records(path))
        except ReaderError as exc:
            ds.issues.append(Issue("error", "READER_ERROR", str(exc), Origin(path.name, "", 0)))
            continue
        if not records:
            ds.issues.append(Issue("warning", "NO_MAPPED_ROWS", "No recognizable tabular rows found.", Origin(path.name, "", 0)))
            continue
        for sheet, rownum, r in records:
            ds.source_rows += 1
            o = _origin(path, sheet, rownum)
            pno = digits(r.get("personnel_no", "")) or text(r.get("personnel_no", ""))
            posno = digits(r.get("position_no", "")) or text(r.get("position_no", ""))
            if profile == "counties":
                is_county, is_person, is_position = True, False, False
            elif profile == "persons":
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
                ds.positions.append(Position(
                    position_no=posno,
                    title=text(r.get("position_title")),
                    org_unit=text(r.get("org_unit")),
                    location=text(r.get("location")),
                    position_type=text(r.get("position_type")) or ("بانام" if profile == "named_positions" else ""),
                    occupant_personnel_no=pno,
                    origin=o,
                ))
    return ds
