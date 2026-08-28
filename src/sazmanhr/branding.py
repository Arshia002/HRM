"""Branding and visual constants for the HRM native desktop shell."""
from __future__ import annotations

import sys
from pathlib import Path

APP_NAME = "HRM"
PRODUCT_TITLE = "سامانه مدیریت منابع انسانی"
COMPANY_NAME = "شرکت توزیع نیروی برق استان کرمانشاه"
PRODUCT_TAGLINE = "مدیریت یکپارچه منابع انسانی و ساختار سازمانی"

# Native palette reconstructed for the v4.9-inspired shell while preserving
# the proven desktop architecture.  Keep these values centralized so future
# visual refinements do not touch security/networking code.
NAVY_950 = "#102F4C"
NAVY_900 = "#153B5C"
NAVY_800 = "#1B496D"
TEAL_600 = "#0F8B8D"
TEAL_500 = "#17A2A4"
TEAL_100 = "#DDF4F3"
ORANGE_500 = "#F5A623"
SURFACE = "#FFFFFF"
SURFACE_MUTED = "#F5F8FC"
BORDER = "#DCE5EF"
TEXT = "#18324A"
TEXT_MUTED = "#6A7D8F"
SUCCESS = "#178A62"
DANGER = "#B42318"


def resource_path(relative: str) -> Path:
    """Resolve bundled resources both from source and PyInstaller one-file builds."""
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        return Path(frozen_root) / relative
    return Path(__file__).resolve().parents[2] / relative


def logo_path() -> Path:
    return resource_path("assets/HRM.png")
