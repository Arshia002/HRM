from __future__ import annotations
from .normalize import key

ALIASES = {
    "personnel_no": ["شماره پرسنلی", "شمارهپرسنلی", "کد پرسنلی", "کدپرسنلی", "پرسنلی"],
    "first_name": ["نام", "نام کوچک", "نامکوچک"],
    "last_name": ["نام خانوادگی", "نامخانوادگی", "فامیلی"],
    "national_id": ["کد ملی", "کدملی", "شماره ملی", "شمارهملی"],
    "employment_type": [
        "نوع استخدام", "نوعاستخدام", "عنوان نوع استخدام", "عنواننوعاستخدام",
        "وضعیت استخدام", "وضعیتاستخدام", "نوع قرارداد", "نوعقرارداد", "نحوه همکاری", "نحوههمکاری",
    ],
    "org_unit": [
        "واحد", "واحد سازمانی", "واحدسازمانی", "نام واحد سازمانی", "نامواحدسازمانی",
        "محل سازمانی", "محلسازمانی",
    ],
    "location": [
        "محل خدمت", "محلخدمت", "نام محل خدمت", "ناممحلخدمت",
        "محل خدمت واقعی", "محلخدمتواقعی", "شهرستان", "محل",
    ],
    "position_no": [
        "شماره پست سازمانی", "شمارهپستسازمانی", "کد پست سازمانی", "کدپستسازمانی",
        "شماره پست توانیر", "شمارهپستتوانیر", "شماره پست", "شمارهپست", "کد پست", "کدپست",
    ],
    "position_title": [
        "عنوان پست", "عنوانپست", "عنوان پست سازمانی", "عنوانپستسازمانی",
        "پست سازمانی", "پستسازمانی", "عنوان شغل", "عنوانشغل", "سمت",
    ],
    "position_type": ["نوع پست", "نوعپست", "وضعیت پست", "وضعیتپست"],
    "county_name": ["نام شهرستان", "نامشهرستان", "شهرستان"],
    "county_code": ["کد شهرستان", "کدشهرستان", "کد"],
}

_ALIAS_TO_FIELD = {}
for field, aliases in ALIASES.items():
    for alias in aliases:
        _ALIAS_TO_FIELD[key(alias)] = field


def canonical_header(value: object) -> str | None:
    return _ALIAS_TO_FIELD.get(key(value))


def map_headers(row: list[object]) -> dict[int, str]:
    result: dict[int, str] = {}
    seen: set[str] = set()
    for i, value in enumerate(row):
        field = canonical_header(value)
        if field and field not in seen:
            result[i] = field
            seen.add(field)
    return result


def header_score(row: list[object]) -> int:
    return len(set(map_headers(row).values()))
