#!/usr/bin/env python3
"""Render the site's default social preview card (Open Graph / Twitter image).

The output is committed to ``static/images/og-default.png`` and referenced from
``themes/uber-style/layouts/partials/head.html`` as the ``og:image`` fallback for
every page that does not set its own ``image:`` in front matter.

Re-run this whenever the branding in ``themes/uber-style/assets/scss/_variables.scss``
changes so the card and the site keep telling the same story::

    python3 scripts/generate_og_image.py

Requires Pillow (``pip install Pillow``). Fonts are resolved from the macOS system
font directory with a portable fallback, so the script also runs on Linux CI.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# Open Graph's canonical size. Facebook, LinkedIn, Slack and X all crop from this.
WIDTH, HEIGHT = 1200, 630
# Drawn at 2x and downsampled: letterspaced small caps look ragged at 1x.
SCALE = 2

# Brand tokens, mirrored from themes/uber-style/assets/scss/_variables.scss.
BG = (10, 10, 12)
ACCENT = (0, 102, 204)
WHITE = (255, 255, 255)
MUTED = (150, 155, 165)

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = REPO_ROOT / "static" / "images" / "og-default.png"

FONT_CANDIDATES = {
    # (family file, face index) pairs, first hit wins.
    "bold": [
        ("/System/Library/Fonts/HelveticaNeue.ttc", 1),
        ("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 0),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 0),
    ],
    "medium": [
        ("/System/Library/Fonts/HelveticaNeue.ttc", 10),
        ("/System/Library/Fonts/Supplemental/Arial.ttf", 0),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 0),
    ],
    "regular": [
        ("/System/Library/Fonts/HelveticaNeue.ttc", 0),
        ("/System/Library/Fonts/Supplemental/Arial.ttf", 0),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 0),
    ],
}


def load_font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    for path, index in FONT_CANDIDATES[weight]:
        if os.path.exists(path):
            return ImageFont.truetype(path, size * SCALE, index=index)
    raise SystemExit(f"no usable font found for weight {weight!r}")


def draw_glow(img: Image.Image) -> None:
    """Accent wash bleeding in from the right, so the card is not a flat rectangle."""
    w, h = img.size
    glow = Image.new("RGB", (w, h), BG)
    pixels = glow.load()
    cx, cy = int(w * 0.86), int(h * 0.18)
    radius = h * 1.15
    for y in range(0, h, 2):
        for x in range(0, w, 2):
            d = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
            t = max(0.0, 1.0 - d / radius) ** 2.6
            px = tuple(int(BG[i] + (ACCENT[i] - BG[i]) * t * 0.55) for i in range(3))
            for dy in range(2):
                for dx in range(2):
                    if x + dx < w and y + dy < h:
                        pixels[x + dx, y + dy] = px
    img.paste(glow, (0, 0))


def draw_tracked(draw: ImageDraw.ImageDraw, xy, text: str, font, fill, tracking: int) -> None:
    """PIL has no letter-spacing, so step glyph by glyph."""
    x, y = xy
    for char in text:
        draw.text((x, y), char, font=font, fill=fill)
        x += draw.textlength(char, font=font) + tracking * SCALE


def wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    lines, current = [], ""
    for word in text.split():
        probe = f"{current} {word}".strip()
        if draw.textlength(probe, font=font) <= max_width or not current:
            current = probe
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def render(headline: str, accent_word: str, subtitle: str, footer: str, out: Path) -> None:
    img = Image.new("RGB", (WIDTH * SCALE, HEIGHT * SCALE), BG)
    draw_glow(img)
    draw = ImageDraw.Draw(img)

    margin = 88 * SCALE
    content_width = WIDTH * SCALE - margin * 2

    # Accent rule anchoring the eyebrow.
    draw.rectangle(
        [margin, 92 * SCALE, margin + 56 * SCALE, 96 * SCALE], fill=ACCENT
    )

    eyebrow_font = load_font("bold", 20)
    draw_tracked(
        draw, (margin, 124 * SCALE), "YENNJ12.JS.ORG", eyebrow_font, MUTED, tracking=4
    )

    headline_font = load_font("bold", 74)
    y = 186 * SCALE
    for line in wrap(draw, headline, headline_font, content_width):
        draw.text((margin, y), line, font=headline_font, fill=WHITE)
        y += 88 * SCALE
    draw.text((margin, y), accent_word, font=headline_font, fill=ACCENT)
    y += 116 * SCALE

    subtitle_font = load_font("regular", 30)
    for line in wrap(draw, subtitle, subtitle_font, content_width):
        draw.text((margin, y), line, font=subtitle_font, fill=MUTED)
        y += 44 * SCALE

    footer_font = load_font("medium", 22)
    draw.text(
        (margin, HEIGHT * SCALE - 92 * SCALE), footer, font=footer_font, fill=MUTED
    )

    out.parent.mkdir(parents=True, exist_ok=True)
    img.resize((WIDTH, HEIGHT), Image.LANCZOS).save(out, "PNG", optimize=True)
    print(f"wrote {out} ({out.stat().st_size // 1024} KB)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--headline", default="Engineering Excellence")
    parser.add_argument("--accent", default="Redefined")
    parser.add_argument(
        "--subtitle",
        default="Architecture deep dives, AI systems, and the engineering behind them.",
    )
    parser.add_argument(
        "--footer", default="Engineering  ·  AI & LLM  ·  Infrastructure  ·  Finance"
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    render(args.headline, args.accent, args.subtitle, args.footer, args.out)


if __name__ == "__main__":
    main()
