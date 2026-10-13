#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A club's IDENTITY image in its own colour (user pick «ب», 2026-10-13).

    python club_identity_card.py --club الأهلي --tagline "القلعة الحمراء · نادي القرن" --out team-photos/al-ahly/red-castle-card.jpg

The representative image for a club: its primary kit colour as the canvas
(a darker shade at the bottom), faint stand stripes, the crest inside the
white ring, the name, an optional tagline above - and the brand row inside
the same SAFE band as every card. The user chose this over a blue-canvas
variant for the Al Ahly image; the colour is the club's own, the layout is
the card's. Save it under team-photos/<slug>/ with credit
«الصورة: تصميم يلا سكور» and team_photos.py registers it.
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from PIL import Image, ImageDraw                       # noqa: E402
import matchup_card as MC                              # noqa: E402
from matchup_card import W, H, SAFE, WHITE, SOFT       # noqa: E402


def _shade(c, k):
    return tuple(max(0, round(v * k)) for v in c)


def _tint(c, k):
    return tuple(min(255, round(v + (255 - v) * k)) for v in c)


def render(name, out, tagline="", colour=None, badge=None):
    FC = MC._fonts()
    kit = MC.kit_for(name)
    base = colour or kit[1][0]
    if sum(base) > 600:                                # a white kit: use the accent/alternate
        alt = kit[2][1][0] if len(kit) > 2 else None
        base = alt if alt and sum(alt) <= 600 else (31, 148, 211)
    top, bot = _tint(base, 0.08), _shade(base, 0.58)
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / (H - 1)
        d.line([(0, y), (W, y)], fill=tuple(round(a + (b - a) * t) for a, b in zip(top, bot)))
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(ov)
    for i in range(0, W, 64):                          # faint stand stripes
        od.polygon([(i, H), (i + 24, H), (i + 24 + 160, 380), (i + 160, 380)], fill=(255, 255, 255, 10))
    cx, cy = W // 2, 300
    od.ellipse([cx - 230, cy - 230, cx + 230, cy + 230], outline=(255, 255, 255, 70), width=3)
    od.ellipse([cx - 330, cy - 330, cx + 330, cy + 330], outline=(255, 255, 255, 30), width=3)
    img.paste(ov, (0, 0), ov)
    if not MC._crest(img, d, cx, 262, 128, badge):
        MC._disc(img, d, cx, 262, 128, kit)
    MC._text_c(d, FC, cx, 262 + 128 + 10, name, FC.font("ExtraBold", 84), max_w=900, size=84, weight="ExtraBold")
    if tagline:
        MC._text_c(d, FC, cx, 90, tagline, FC.font("Bold", 38), _tint(base, 0.82), max_w=800, size=38, weight="Bold")
    x0, _, x1, _ = SAFE
    icon = Image.open(os.path.join(HERE, "assets-src", "app-icon-1024.png")).convert("RGB")
    bs = 52
    ball = icon.crop((218, 105, 806, 693)).resize((bs, bs), Image.LANCZOS)
    m = Image.new("L", (bs, bs), 0)
    ImageDraw.Draw(m).ellipse([0, 0, bs - 1, bs - 1], fill=255)
    img.paste(ball, (x1 - bs, 480), m)
    fb = FC.font("ExtraBold", 34)
    s = FC.ar("يلا سكور")
    d.text((x1 - bs - 12 - d.textlength(s, font=fb), 484), s, font=fb, fill=WHITE)
    d.text((x0, 492), "yallascore.site", font=FC.font("Bold", 28), fill=SOFT)
    img.save(out, quality=90, optimize=True)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--club", required=True, help="the club's name as the site writes it")
    ap.add_argument("--tagline", default="")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    from site_lib.clubs import TEAM_PAGES
    tp = next((t for t in TEAM_PAGES if t["name"] == a.club), None)
    comp = tp.get("league") if tp else None
    badge = MC.club_badge(a.club, comp) or MC.club_badge(a.club)
    print(render(a.club, a.out, a.tagline, badge=badge))


if __name__ == "__main__":
    main()
