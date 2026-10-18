"""Text as outlines for the profile SVGs.

GitHub shows README images as <img>, which cannot load web fonts, so every
string is drawn from glyph outlines stored in glyphs.json (Tektur and
Instrument Sans, both OFL). Each glyph is defined once and placed with <use>.
"""
import json
from pathlib import Path
from xml.sax.saxutils import escape

_FONTS = json.loads((Path(__file__).with_name("glyphs.json")).read_text(encoding="utf-8"))


class Type:
    """Collects the glyphs a drawing uses; defs() emits them once."""

    def __init__(self):
        self._used = {}

    def width(self, text, face, size):
        font = _FONTS[face]
        return sum(font["glyphs"].get(ch, font["glyphs"]["?"])[0] for ch in text) * size / font["upm"]

    def text(self, text, x, y, face, size, fill, anchor="start", extra=""):
        """One line of text with its baseline at y. Returns SVG markup."""
        font = _FONTS[face]
        scale = size / font["upm"]
        if anchor != "start":
            w = self.width(text, face, size)
            x -= w if anchor == "end" else w / 2
        uses, cursor = [], 0
        for ch in text:
            advance, _ = font["glyphs"].get(ch, font["glyphs"]["?"])
            if ch != " ":
                gid = self._id(face, ch)
                uses.append(f'<use href="#{gid}" x="{cursor}"/>')
            cursor += advance
        label = f' aria-label="{escape(text)}"' if text.strip() else ""
        return (f'<g fill="{fill}"{label}{extra} transform="translate({x:.1f} {y:.1f}) scale({scale:.5f} {-scale:.5f})">'
                f'{"".join(uses)}</g>')

    def _id(self, face, ch):
        gid = f"{face[0]}{'m' if face.endswith('medium') else ''}{ord(ch)}"
        self._used[gid] = (face, ch)
        return gid

    def defs(self):
        return "".join(f'<path id="{gid}" d="{_FONTS[face]["glyphs"][ch][1]}"/>'
                       for gid, (face, ch) in sorted(self._used.items()))
