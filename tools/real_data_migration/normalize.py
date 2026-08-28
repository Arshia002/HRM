from __future__ import annotations
import re
import unicodedata

_PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_ARABIC_TO_PERSIAN = str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک", "ة": "ه", "ۀ": "ه"})
_ZERO_WIDTH = re.compile(r"[\u200b\u200c\u200d\ufeff]")
_SPACE = re.compile(r"\s+")


def text(value: object) -> str:
    if value is None:
        return ""
    s = unicodedata.normalize("NFKC", str(value))
    s = s.translate(_PERSIAN_DIGITS).translate(_ARABIC_TO_PERSIAN)
    s = _ZERO_WIDTH.sub(" ", s)
    s = _SPACE.sub(" ", s).strip()
    if s.endswith(".0") and s[:-2].isdigit():
        s = s[:-2]
    return s


def key(value: object) -> str:
    s = text(value).lower()
    return re.sub(r"[^0-9a-zآ-ی]+", "", s)


def digits(value: object) -> str:
    return re.sub(r"\D+", "", text(value))
