#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The site's share images, drawn from the tiger (rebrand 2026-11-04):

    "C:\\Program Files\\Python312\\python.exe" tools/make_og_banner.py

Writes assets-src/og-banner.png (1200x630: every page's default og:image,
served from /assets/og-banner.png) and assets-src/fb-cover-1640x624.png (the
Facebook page cover - the user uploads it himself). The old files showed the
retired ball and «يلا سكور» / yallascore.site; this one shows the tiger head,
«الجون», the tagline and elgoon.com, in the site's blues (style.css --blue
#1f94d3 on the dark navy the cards use). Fonts and the Arabic shaper are
fb_cards' - one engine on every platform (see fb_cards.font)."""
import os
import sys

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
from fb_cards import ar, font                                   # noqa: E402

SRC = os.path.join(HERE, "assets-src")
TIGER = os.path.join(SRC, "tiger-head-512.png")
NAVY = (12, 42, 70)
NAVY_2 = (16, 58, 94)
BLUE = (31, 148, 211)
WHITE = (255, 255, 255)
SOFT = (200, 224, 240)
TAGLINE = "نتائج مباشرة · أخبار الكورة · ترتيب الدوريات"


def _bg(w, h):
    """Navy with a faint pitch: the centre circle and the halfway line."""
    im = Image.new("RGB", (w, h), NAVY)
    d = ImageDraw.Draw(im)
    for y in range(h):                              # a soft vertical gradient
        t = y / h
        d.line([(0, y), (w, y)], fill=tuple(int(NAVY[i] + (NAVY_2[i] - NAVY[i]) * t) for i in range(3)))
    line = (30, 78, 118)
    cx, r = int(w * 0.5), int(h * 0.42)
    d.ellipse([cx - r, h // 2 - r, cx + r, h // 2 + r], outline=line, width=3)
    d.line([(cx, 0), (cx, h)], fill=line, width=3)
    d.rectangle([0, h - 10, w, h], fill=BLUE)      # the brand strip at the foot
    return im


def _tiger(size):
    t = Image.open(TIGER).convert("RGBA")
    return t.resize((size, size), Image.LANCZOS)


def _pill(d, cx, cy, text, f, pad_x=36, pad_y=14):
    """White pill with the domain in blue, centred on (cx, cy)."""
    tw = d.textlength(text, font=f)
    th = f.size
    x0, y0 = cx - tw / 2 - pad_x, cy - th / 2 - pad_y
    x1, y1 = cx + tw / 2 + pad_x, cy + th / 2 + pad_y
    d.rounded_rectangle([x0, y0, x1, y1], radius=(y1 - y0) / 2, fill=WHITE)
    d.text((cx, cy), text, font=f, fill=BLUE, anchor="mm")


def banner(w, h, out, tiger_px, name_px, tag_px, dom_px):
    im = _bg(w, h)
    # the tiger on the left third (it faces LEFT on the site - keep it so)
    t = _tiger(tiger_px)
    tx, ty = int(w * 0.07), (h - tiger_px) // 2 - 10
    im.alpha_composite(t.convert("RGBA"), (tx, ty)) if im.mode == "RGBA" else im.paste(t, (tx, ty), t)
    d = ImageDraw.Draw(im)
    # the words on the right two thirds, right-aligned (Arabic)
    rx = int(w * 0.93)
    d.text((rx, int(h * 0.36)), ar("الجون"), font=font("ExtraBold", name_px), fill=WHITE, anchor="rm")
    d.text((rx, int(h * 0.56)), ar(TAGLINE), font=font("Bold", tag_px), fill=SOFT, anchor="rm")
    _pill(d, rx - 150, int(h * 0.76), "elgoon.com", font("Bold", dom_px))
    im.save(out, "PNG", optimize=True)
    print(f"{os.path.relpath(out, HERE)}: {w}x{h}, {os.path.getsize(out) // 1024} KB")


if __name__ == "__main__":
    banner(1200, 630, os.path.join(SRC, "og-banner.png"), tiger_px=400, name_px=150, tag_px=40, dom_px=38)
    banner(1640, 624, os.path.join(SRC, "fb-cover-1640x624.png"), tiger_px=420, name_px=160, tag_px=42, dom_px=40)
