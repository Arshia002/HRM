#!/usr/bin/env python3
"""Rebuild HRM application icons from the bundled official company logo source."""
from pathlib import Path

from PIL import Image


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    assets = root / "assets"
    source = assets / "company-logo-source.png"
    if not source.is_file():
        raise SystemExit(f"Missing official company logo source: {source}")
    image = Image.open(source).convert("RGBA")
    canvas = Image.new("RGBA", (256, 256), (255, 255, 255, 0))
    scaled = image.resize((220, 220), Image.Resampling.NEAREST)
    canvas.alpha_composite(scaled, ((256 - 220) // 2, (256 - 220) // 2))
    canvas.save(assets / "HRM.png")
    canvas.save(
        assets / "HRM.ico",
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print(f"HRM branding rebuilt from {source.name}")


if __name__ == "__main__":
    main()
