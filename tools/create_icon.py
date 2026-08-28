#!/usr/bin/env python3
from pathlib import Path

from PIL import Image, ImageDraw


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    assets = root / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    size = 1024
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((48, 48, 976, 976), radius=210, fill="#17324d")
    draw.rounded_rectangle((82, 82, 942, 942), radius=180, outline="#26c6b5", width=24)
    nodes = [(270, 310), (512, 210), (754, 310), (350, 670), (674, 670)]
    for start, end in ((0, 1), (1, 2), (0, 3), (2, 4), (3, 4)):
        draw.line((nodes[start], nodes[end]), fill="#74e1d5", width=38)
    for x, y in nodes:
        draw.ellipse((x - 62, y - 62, x + 62, y + 62), fill="#f7fafc", outline="#26c6b5", width=20)
    bolt = [(520, 330), (410, 545), (505, 545), (455, 790), (660, 490), (550, 490)]
    draw.polygon(bolt, fill="#ffb020")
    image.save(assets / "HRM.png")
    image.save(assets / "HRM.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])


if __name__ == "__main__":
    main()
