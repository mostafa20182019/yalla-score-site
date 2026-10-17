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


def _big_crest(url, size):
    """The crest at `size` px for the bare image. The site's badge URLs ask
    365scores for 68 px (136 at dpr 2) - fine beside a score, a smudge in a
    344 px ring - so the bare image asks the same host for 400 px; football-
    data crests are 200 px PNGs and may be scaled up to `size` (at most 1.3x,
    the LANCZOS limit before edges soften). None when nothing can be read."""
    import build_site as b
    from PIL import Image as _I
    if not url:
        return None
    hi = url.replace("w_68,h_68", "w_400,h_400").replace("dpr_2", "dpr_1") if "w_68,h_68" in url else url
    for u in (hi, url):
        b.local_crest(u)
        path = os.path.join(b.CRESTS_CACHE, b._crest_name(u))
        if not os.path.exists(path) or path.lower().endswith(".svg"):
            continue
        try:
            im = _I.open(path).convert("RGBA")
        except Exception:                               # noqa: BLE001
            continue
        k = min(size / max(im.width, im.height), 1.3)       # fit the ring; upscale at most 1.3x
        im = im.resize((max(1, round(im.width * k)), max(1, round(im.height * k))), _I.LANCZOS)
        return im
    return None


def _lum(c):
    return (0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]) / 255


def render(name, out, tagline="", colour=None, badge=None, bare=False):
    """Dark kit (most clubs): the colour as the canvas, white text.
    LIGHT kit (Zamalek, Real Madrid, Man City's sky blue): the colour stays
    the canvas - it IS the club's colour - and the text turns to the kit's
    second colour / alternate kit (Zamalek red, Real's navy, City's navy),
    so the image is still unmistakably that club and still readable."""
    FC = MC._fonts()
    kit = MC.kit_for(name)
    base = colour or kit[1][0]
    light = _lum(base) > 0.55
    if light:
        ink = kit[1][1] if len(kit[1]) > 1 else (kit[2][1][0] if len(kit) > 2 else (16, 34, 74))
        if _lum(ink) > 0.55:
            ink = (16, 34, 74)
        top, bot = _tint(base, 0.6), _shade(base, 0.90)
        text, soft, line = ink, _tint(ink, 0.25), ink
        stripe = (0, 0, 0, 10)
    else:
        top, bot = _tint(base, 0.08), _shade(base, 0.58)
        text, soft, line = WHITE, _tint(base, 0.82), WHITE
        stripe = (255, 255, 255, 10)
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / (H - 1)
        d.line([(0, y), (W, y)], fill=tuple(round(a + (b - a) * t) for a, b in zip(top, bot)))
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(ov)
    for i in range(0, W, 64):                          # faint stand stripes
        od.polygon([(i, H), (i + 24, H), (i + 24 + 160, 380), (i + 160, 380)], fill=stripe)
    # bare (user, 2026-10-16: «شيل اسم الفريق وأي كلام، خلي الشكل مع الشعار
    # فقط»): the crest alone, centred, no name, no tagline, no brand row
    cx, cy = W // 2, (H // 2 if bare else 300)
    ccy = H // 2 if bare else 262
    # bare crest is bigger (user, same day: «كبّر الشعار شوية»): ring 128 -> 172,
    # the halo rings grow with it. 172 keeps the ring inside the article
    # hero's ~425-row band (y 127-552) and the SAFE band (y 140-540).
    R = 172 if bare else 128
    r1, r2 = (300, 420) if bare else (230, 330)
    od.ellipse([cx - r1, cy - r1, cx + r1, cy + r1], outline=line + (70,), width=3)
    od.ellipse([cx - r2, cy - r2, cx + r2, cy + r2], outline=line + (30,), width=3)
    img.paste(ov, (0, 0), ov)
    drawn = False
    if bare:
        big = _big_crest(badge, int(2 * R * 0.80))
        if big is not None:
            from PIL import ImageFilter as _F
            sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            ImageDraw.Draw(sh).ellipse([cx - R + 6, ccy - R + 14, cx + R + 6, ccy + R + 14], fill=(0, 0, 0, 90))
            sh = sh.filter(_F.GaussianBlur(12))
            img.paste(sh, (0, 0), sh)
            d.ellipse([cx - R, ccy - R, cx + R, ccy + R], fill=WHITE)
            img.paste(big, (cx - big.width // 2, ccy - big.height // 2), big)
            drawn = True
    if not drawn and not MC._crest(img, d, cx, ccy, R, badge):
        MC._disc(img, d, cx, ccy, R, kit)
    if light:                                          # the white ring needs an edge on a light canvas
        d.ellipse([cx - R, ccy - R, cx + R, ccy + R], outline=_tint(ink, 0.6), width=4)
    if bare:
        img.save(out, quality=90, optimize=True)
        return out
    MC._text_c(d, FC, cx, 262 + 128 + 10, name, FC.font("ExtraBold", 84), text, max_w=900, size=84, weight="ExtraBold")
    if tagline:
        MC._text_c(d, FC, cx, 90, tagline, FC.font("Bold", 38), soft, max_w=800, size=38, weight="Bold")
    WHITE_, SOFT_ = text, soft                         # the brand row follows the ink
    x0, _, x1, _ = SAFE
    icon = Image.open(os.path.join(HERE, "assets-src", "app-icon-1024.png")).convert("RGB")
    bs = 52
    ball = icon.crop((218, 105, 806, 693)).resize((bs, bs), Image.LANCZOS)
    m = Image.new("L", (bs, bs), 0)
    ImageDraw.Draw(m).ellipse([0, 0, bs - 1, bs - 1], fill=255)
    img.paste(ball, (x1 - bs, 480), m)
    fb = FC.font("ExtraBold", 34)
    s = FC.ar("يلا سكور")
    d.text((x1 - bs - 12 - d.textlength(s, font=fb), 484), s, font=fb, fill=WHITE_)
    d.text((x0, 492), "yallascore.site", font=FC.font("Bold", 28), fill=SOFT_)
    img.save(out, quality=90, optimize=True)
    return out


def _star(d, cx, cy, r, fill):
    import math
    pts = []
    for i in range(10):
        a = -math.pi / 2 + i * math.pi / 5
        rr = r if i % 2 == 0 else r * 0.45
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    d.polygon(pts, fill=fill)


def render_bands(name, out, badge=None, colour=(200, 16, 46), stars=0, seed=7):
    """The kit-stripe identity image (user, 2026-10-17, from a Zamalek shirt
    photo: «زي كده بس من غير علامة نايك»): a white canvas, two bands in the
    club colour whose ends dissolve into a pixel grid, the crest in the
    middle with its stars above. No text, no brand - the crest-only rule."""
    import random
    rnd = random.Random(seed)
    img = Image.new("RGB", (W, H), (250, 250, 250))
    d = ImageDraw.Draw(img)
    # a faint vertical sheen so the white is not flat
    for y in range(H):
        t = abs(y - H / 2) / (H / 2)
        v = round(250 - 8 * t)
        d.line([(0, y), (W, y)], fill=(v, v, v))
    bands = [(246, 336), (376, 466)]                   # y0, y1 of each band (90 px, 40 px apart)
    solid = (520, W - 520)                             # solid between these x
    cell = 18
    for y0, y1 in bands:
        d.rectangle([solid[0], y0, solid[1], y1], fill=colour)
        # the dissolve: a pixel grid that thins away from the solid part, with
        # a few cells spilling above and below the band's edge (the shirt)
        for side in (-1, 1):
            for k in range(0, 360, cell):
                p = 1.0 - k / 360
                x = (solid[0] - k - cell) if side < 0 else (solid[1] + k)
                for yy in range(y0 - cell, y1 + cell, cell):
                    inside = y0 <= yy < y1
                    if rnd.random() < (p if inside else p * 0.25):
                        d.rectangle([x, yy, x + cell - 1, yy + cell - 1], fill=colour)
    # the crest, big, on the bands
    cx, cy = W // 2, 352
    big = _big_crest(badge, 330)
    if big is not None:
        # a white halo in the crest's own shape (its alpha, pasted around the
        # centre), so the bands stop at the crest the way a shirt's do
        halo = Image.new("RGBA", big.size, (255, 255, 255, 0))
        halo.paste((255, 255, 255, 255), (0, 0), big.split()[-1])
        for dx in range(-7, 8, 2):
            for dy in range(-7, 8, 2):
                img.paste(halo, (cx - big.width // 2 + dx, cy - big.height // 2 + dy), halo)
        img.paste(big, (cx - big.width // 2, cy - big.height // 2), big)
    else:
        d.ellipse([cx - 150, cy - 150, cx + 150, cy + 150], fill=WHITE, outline=colour, width=8)
    gold = (212, 175, 55)
    top = cy - (big.height // 2 if big is not None else 150) - 40
    for i in range(stars):
        _star(d, cx + (i - (stars - 1) / 2) * 42, top, 16, gold)
    img.save(out, quality=92, optimize=True)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--club", required=True, help="the club's name as the site writes it")
    ap.add_argument("--tagline", default="")
    ap.add_argument("--colour", help="hex, when the club has no kit in matchup_card (the NT)")
    ap.add_argument("--badge-as", help="look the crest up under this name (NT: مصر)")
    ap.add_argument("--bare", action="store_true", help="the crest only: no name, no tagline, no brand")
    ap.add_argument("--bands", action="store_true", help="the kit-stripe style: white canvas, two bands in the club colour, crest + stars")
    ap.add_argument("--stars", type=int, default=0, help="--bands: gold stars above the crest")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    from site_lib.clubs import TEAM_PAGES
    tp = next((t for t in TEAM_PAGES if t["name"] == a.club), None)
    comp = tp.get("league") if tp else None
    key = a.badge_as or a.club
    badge = MC.club_badge(key, comp) or MC.club_badge(key)
    colour = MC._rgb(a.colour) if a.colour else None
    if a.bands:
        kit = MC.KITS.get(a.club)
        band = colour or (kit[1][1] if kit and len(kit[1]) > 1 else (kit[1][0] if kit else (200, 16, 46)))
        print(render_bands(a.club, a.out, badge=badge, colour=band, stars=a.stars))
        return
    print(render(a.club, a.out, a.tagline, colour=colour, badge=badge, bare=a.bare))


if __name__ == "__main__":
    main()
