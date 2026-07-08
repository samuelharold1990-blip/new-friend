#!/usr/bin/env python3
"""Regenerate the placeholder photo pack (SVGs) and PWA icons (PNGs).

The placeholders make the app work out of the box; users replace them by
dropping real images into photos/<mood>/. Pure stdlib — no Pillow.

Usage: python scripts/gen_placeholders.py
"""
from __future__ import annotations

import struct
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PHOTOS = ROOT / "photos"
ICONS = ROOT / "companion" / "static" / "icons"

# mood -> (label, gradient top, gradient bottom, icon svg fragment)
MOODS = {
    "morning": ("morning", "#ffd89b", "#f8926f",
                '<circle cx="384" cy="500" r="120" fill="#fff" opacity="0.9"/>'
                '<g stroke="#fff" stroke-width="14" stroke-linecap="round" opacity="0.9">'
                '<line x1="384" y1="310" x2="384" y2="250"/><line x1="384" y1="690" x2="384" y2="750"/>'
                '<line x1="194" y1="500" x2="134" y2="500"/><line x1="574" y1="500" x2="634" y2="500"/>'
                '<line x1="250" y1="366" x2="207" y2="323"/><line x1="518" y1="634" x2="561" y2="677"/>'
                '<line x1="250" y1="634" x2="207" y2="677"/><line x1="518" y1="366" x2="561" y2="323"/></g>'),
    "coffee": ("coffee", "#c79081", "#dfa579",
               '<rect x="274" y="420" width="200" height="230" rx="30" fill="none" stroke="#fff" stroke-width="14"/>'
               '<path d="M474 460 h40 a50 50 0 0 1 0 100 h-40" fill="none" stroke="#fff" stroke-width="14"/>'
               '<path d="M320 380 q 15 -40 0 -70 M 374 380 q 15 -40 0 -70 M 428 380 q 15 -40 0 -70"'
               ' fill="none" stroke="#fff" stroke-width="12" stroke-linecap="round" opacity="0.85"/>'),
    "gym": ("gym", "#5ee7df", "#4a90b8",
            '<g fill="#fff" opacity="0.9"><rect x="180" y="470" width="60" height="120" rx="14"/>'
            '<rect x="528" y="470" width="60" height="120" rx="14"/>'
            '<rect x="130" y="495" width="40" height="70" rx="12"/>'
            '<rect x="598" y="495" width="40" height="70" rx="12"/>'
            '<rect x="240" y="515" width="288" height="30" rx="15"/></g>'),
    "outdoors": ("outdoors", "#96e6a1", "#4a9d6e",
                 '<g fill="none" stroke="#fff" stroke-width="14" stroke-linecap="round" opacity="0.9">'
                 '<path d="M170 640 L 320 420 L 420 560 L 500 460 L 610 640 Z"/>'
                 '<circle cx="540" cy="360" r="52"/></g>'),
    "selfie_generic": ("selfie", "#e8b3d8", "#b06ab3",
                       '<g fill="none" stroke="#fff" stroke-width="14" opacity="0.9">'
                       '<rect x="264" y="360" width="240" height="340" rx="36"/>'
                       '<circle cx="384" cy="480" r="56"/>'
                       '<path d="M310 660 q 74 -60 148 0" stroke-linecap="round"/></g>'),
    "evening": ("evening", "#4b6cb7", "#26264e",
                '<path d="M 440 340 a 130 130 0 1 0 60 240 a 150 150 0 0 1 -60 -240 Z" fill="#fff" opacity="0.9"/>'
                '<g fill="#fff" opacity="0.8"><circle cx="290" cy="380" r="8"/><circle cx="330" cy="560" r="6"/>'
                '<circle cx="250" cy="480" r="5"/></g>'),
    "cozy": ("cozy", "#f6d365", "#c98850",
             '<g fill="none" stroke="#fff" stroke-width="14" stroke-linecap="round" opacity="0.9">'
             '<path d="M 384 660 C 250 560 210 460 270 400 C 320 355 384 390 384 440 '
             'C 384 390 448 355 498 400 C 558 460 518 560 384 660 Z"/></g>'),
    "dressed_up": ("dressed up", "#a18cd1", "#753a88",
                   '<g fill="none" stroke="#fff" stroke-width="13" opacity="0.9" stroke-linejoin="round">'
                   '<path d="M 384 330 l 26 52 58 8 -42 41 10 58 -52 -27 -52 27 10 -58 -42 -41 58 -8 Z"/>'
                   '<path d="M 330 560 q 54 40 108 0 l 30 120 q -84 40 -168 0 Z"/></g>'),
}

SVG_TEMPLATE = """<svg xmlns="http://www.w3.org/2000/svg" width="768" height="1024" viewBox="0 0 768 1024">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="0.4" y2="1">
      <stop offset="0" stop-color="{top}"/>
      <stop offset="1" stop-color="{bottom}"/>
    </linearGradient>
  </defs>
  <rect width="768" height="1024" fill="url(#bg)"/>
  <circle cx="{bx}" cy="200" r="170" fill="#ffffff" opacity="0.07"/>
  <circle cx="{bx2}" cy="840" r="220" fill="#ffffff" opacity="0.06"/>
  {icon}
  <text x="384" y="880" text-anchor="middle" font-family="-apple-system, Segoe UI, sans-serif"
        font-size="40" font-weight="600" fill="#ffffff" opacity="0.95">{label}</text>
  <text x="384" y="930" text-anchor="middle" font-family="-apple-system, Segoe UI, sans-serif"
        font-size="22" fill="#ffffff" opacity="0.7">placeholder — add photos to photos/{mood}/</text>
</svg>
"""


def write_svgs() -> None:
    for mood, (label, top, bottom, icon) in MOODS.items():
        d = PHOTOS / mood
        d.mkdir(parents=True, exist_ok=True)
        for i, (bx, bx2) in enumerate([(600, 180), (170, 590)], start=1):
            svg = SVG_TEMPLATE.format(top=top, bottom=bottom, icon=icon, label=label,
                                      mood=mood, bx=bx, bx2=bx2)
            (d / f"placeholder-{i}.svg").write_text(svg)
    print(f"wrote {len(MOODS) * 2} placeholder SVGs under {PHOTOS}")


# ---- minimal PNG writer (RGBA, no dependencies) ----

def png_bytes(width: int, height: int, pixel_fn) -> bytes:
    raw = bytearray()
    for y in range(height):
        raw.append(0)  # filter: none
        for x in range(width):
            raw.extend(pixel_fn(x, y))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data)))

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b""))


def icon_pixel_fn(size: int):
    """Purple-pink gradient with a white chat-bubble heart."""
    def lerp(a, b, t):
        return int(a + (b - a) * t)

    top, bottom = (176, 95, 214), (238, 93, 143)

    def inside_heart(px, py):
        # map to heart coordinates: x in [-1.4, 1.4], y in [-1.4, 1.4] (y up)
        x = (px / size - 0.5) * 2.9
        y = (0.52 - py / size) * 2.9
        return (x * x + y * y - 1) ** 3 - x * x * y * y * y <= 0

    def fn(px, py):
        if inside_heart(px, py):
            return (255, 255, 255, 255)
        t = py / size
        return (lerp(top[0], bottom[0], t), lerp(top[1], bottom[1], t),
                lerp(top[2], bottom[2], t), 255)
    return fn


def write_icons() -> None:
    ICONS.mkdir(parents=True, exist_ok=True)
    for size in (192, 512):
        (ICONS / f"icon-{size}.png").write_bytes(png_bytes(size, size, icon_pixel_fn(size)))
    print(f"wrote icons under {ICONS}")


if __name__ == "__main__":
    write_svgs()
    write_icons()
