#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Elgoon — the article HERO (2026-11-06): a licensed photo composed into a
designed image — the person cut out of his snapshot and set on his club's
colours, the way Sky Sports / Goal build theirs.

    python hero_card.py --photo team-photos/liverpool/salah-wc.jpg --club "ليفربول" --out media/hero-salah-renewal.jpg
    python hero_card.py --photo <file|url> --club "مصر" --kicker "منتخب مصر" --out media/hero-egypt-squad.jpg
    python hero_card.py --photo ... --club ... --out ... --no-cutout      # the pillarbox fallback on purpose

Why (user, 2026-11-06: «الصور اللي بتنزل مع الأخبار مش بتكون حلوة لأن أنا
متقيد بنقطة الحقوق»): the licence rules stay exactly as they are — one CC /
public-domain photo of the NAMED person, credited — but the raw snapshot is
what looks amateur: a messy background, flat light, a random frame. The
sites whose images look designed never publish the raw photo; they compose
it. So: cut the subject out (rembg, open source, runs locally and on the
runner), set him on a gradient of his club's colours with a soft glow, a
faint crest watermark and the brand mark. Same licence, same credit (plus
«تركيب: الجون»), a different-looking site.

Output: 1600x900 JPEG (Google Discover wants >= 1200 px wide; 16:9 crops
cleanly to og 1.91:1). The subject's head sits in the band the article page
shows (`.a-img` object-position 50% 18%, max-height 400): rows ~10-56 %.

Fallbacks, in order: no rembg / model missing / mask too thin -> the photo
pillarboxed over a blurred, club-tinted copy of itself (the method the
article prompt already used by hand). Never a bare upscale, never a crop
through the head.
"""
import argparse
import io
import json
import os
import sys
import urllib.request

from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")

import fb_cards as C                    # noqa: E402  fonts, Arabic shaping, crests
import matchup_card as MC               # noqa: E402  the clubs' kit colours

W, H = 1600, 900
SUBJECT_X = 0.56                        # a touch right of centre: Arabic pages start on the right
SUBJECT_H = 0.93                        # the cutout's height as a share of the canvas
MAX_UPSCALE = 1.7                       # a head-and-shoulders snapshot may grow this much, no more
MIN_MASK_SHARE = 0.10                   # a mask covering less of its box is not a person
EXTRA_KITS = {                          # clubs/teams the matchup table does not carry
    "مصر": ("solid", [(192, 12, 36)], ("solid", [(255, 255, 255)])),
    "منتخب مصر": ("solid", [(192, 12, 36)], ("solid", [(255, 255, 255)])),
}
BRAND = (31, 148, 211)


# ---------------------------------------------------------------- colours
def _lum(c):
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


def _mul(c, k):
    return tuple(max(0, min(255, int(v * k))) for v in c)


def club_colours(name, competition=None):
    """(base, accent) for a club name as the site writes it. The base is the
    kit's strong colour (never white); the accent is the other one."""
    kit = MC.KITS_BY_COMP.get((competition, name)) or MC.KITS.get(name) or EXTRA_KITS.get(name)
    if not kit:
        return BRAND, (255, 255, 255)
    pattern, cols, alt = kit[0], list(kit[1]), kit[2]
    accent = kit[3] if len(kit) > 3 else None
    strong = [c for c in cols if _lum(c) < 200]
    if strong:
        base = max(strong, key=lambda c: (max(c) - min(c), -_lum(c)))   # the most saturated
        others = [c for c in cols if c != base] or [(255, 255, 255)]
        return base, (accent or others[0])
    # an all-white shirt (Real Madrid, Lyon...): the alternate kit or the trim
    for c in (alt[1] if alt else []) + ([accent] if accent else []):
        if c and _lum(c) < 200:
            return c, (accent if accent and accent != c else (255, 255, 255))
    return (29, 29, 27), (accent or (212, 175, 55))


# ---------------------------------------------------------------- canvas
def background(base, accent):
    """A diagonal gradient from the club colour to its deep shade, a light
    sweep in the accent, a radial glow where the subject will stand."""
    dark = _mul(base, 0.42)
    im = Image.new("RGB", (W, H), dark)
    top = Image.new("RGB", (W, H), base)
    g = Image.linear_gradient("L").resize((W, H)).rotate(25, expand=False, resample=Image.BILINEAR)
    im = Image.composite(top, im, g)
    # the light sweep (accent at low opacity, from the top-left)
    sweep = Image.new("L", (W, H), 0)
    ImageDraw.Draw(sweep).polygon([(0, 0), (int(W * 0.55), 0), (int(W * 0.2), H), (0, H)], fill=70)
    im = Image.composite(Image.new("RGB", (W, H), accent), im, sweep.filter(ImageFilter.GaussianBlur(120)))
    # the glow behind the subject
    glow = Image.new("L", (W, H), 0)
    cx = int(W * SUBJECT_X)
    ImageDraw.Draw(glow).ellipse((cx - 520, int(H * 0.08), cx + 520, int(H * 1.25)), fill=95)
    im = Image.composite(Image.new("RGB", (W, H), _mul(accent, 1.0)), im, glow.filter(ImageFilter.GaussianBlur(170)))
    return im


def watermark_crest(im, url, name, base):
    """A big faint crest on the left, half off the canvas — the broadcast
    graphics habit. Skipped when the cache has no crest to rasterise."""
    if not url:
        return
    import fb_reel as R                                      # noqa: PLC0415  big_badge, fill_box
    size = 820
    cr = C.crest_image(R.big_badge(url), size) or C.crest_image(url, size)
    if not cr:
        return
    cr = R.fill_box(cr, size).copy()                         # the feed's 68px badge, scaled to the box
    cr.putalpha(cr.getchannel("A").point(lambda v: v * 13 // 100))
    im.paste(cr, (-160, H - size + 60), cr)


def brand(im):
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, W, 6), fill=(255, 255, 255))
    C.draw_center(d, W - 110, 28, C.ar("الجون"), C.font("ExtraBold", 40), (255, 255, 255))


def kicker(im, text, accent):
    """A short Arabic line bottom-right (the club, the competition) — never
    the headline; the page carries that."""
    if not text:
        return
    d = ImageDraw.Draw(im)
    s = C.ar(text)
    f = C.fit(d, s, "ExtraBold", 54, W * 0.42, 30)
    tw = C.text_w(d, s, f)
    x1, y1 = W - 70, H - 70
    pad = 26
    d.rounded_rectangle((x1 - tw - 2 * pad, y1 - 78, x1, y1), 18, fill=(0, 0, 0))
    d.text((x1 - pad - tw, y1 - 66), s, font=f, fill=(255, 255, 255))
    d.rectangle((x1 - tw - 2 * pad, y1 - 78, x1 - tw - 2 * pad + 10, y1), fill=accent)


# ---------------------------------------------------------------- the subject
def load_photo(src):
    if src.startswith("http://") or src.startswith("https://"):
        req = urllib.request.Request(src, headers={"User-Agent": "elgoon-hero/1.0"})
        data = urllib.request.urlopen(req, timeout=60).read()
        return Image.open(io.BytesIO(data)).convert("RGB")
    return Image.open(src).convert("RGB")


def cutout(photo):
    """The subject on transparency, or None when rembg (or its model) is not
    there or the mask is too thin to be a person."""
    try:
        from rembg import remove, new_session               # noqa: PLC0415
        session = new_session("u2net_human_seg")
    except Exception as e:                                   # noqa: BLE001
        print(f"  no cutout: {str(e)[:90]}")
        return None
    rgba = remove(photo.convert("RGBA"), session=session, post_process_mask=True)
    a = rgba.getchannel("A")
    bb = a.getbbox()
    if not bb:
        return None
    hist = a.crop(bb).histogram()
    share = sum(hist[129:]) / float((bb[2] - bb[0]) * (bb[3] - bb[1]))
    if share < MIN_MASK_SHARE:
        print(f"  mask too thin ({share:.0%}), falling back")
        return None
    return rgba.crop(bb)


def place_subject(im, cut):
    """Scale the cutout to SUBJECT_H of the canvas (bounded by MAX_UPSCALE so a
    small snapshot does not turn to mush), anchor it to the bottom edge a bit
    right of centre, with a soft shadow."""
    k = min(H * SUBJECT_H / cut.height, MAX_UPSCALE)
    k = min(k, W * 0.62 / cut.width)
    cw, ch = max(1, int(cut.width * k)), max(1, int(cut.height * k))
    cut = cut.resize((cw, ch), Image.LANCZOS)
    x = int(W * SUBJECT_X - cw / 2)
    y = H - ch                                      # feet / torso bleed off the bottom
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sh = Image.new("RGBA", cut.size, (0, 0, 0, 0))
    sh.putalpha(cut.getchannel("A").point(lambda v: v * 55 // 100))
    shadow.paste(sh, (x + 18, y + 26), sh)
    shadow = shadow.filter(ImageFilter.GaussianBlur(22))
    im.paste(shadow, (0, 0), shadow)
    im.paste(cut, (x, y), cut)
    return (x, y, x + cw, y + ch)


def pillarbox(im, photo, base):
    """The fallback: the photo whole, centred, over a blurred and club-tinted
    enlargement of itself — nothing cropped, nothing upscaled hard."""
    big = photo.copy()
    k = max(W / big.width, H / big.height)
    big = big.resize((int(big.width * k) + 1, int(big.height * k) + 1), Image.BILINEAR)
    big = big.crop(((big.width - W) // 2, (big.height - H) // 2, (big.width - W) // 2 + W, (big.height - H) // 2 + H))
    big = big.filter(ImageFilter.GaussianBlur(28))
    big = Image.blend(big, Image.new("RGB", (W, H), _mul(base, 0.5)), 0.55)
    im.paste(big, (0, 0))
    k = min((H - 60) / photo.height, (W * 0.78) / photo.width, 1.8)
    ph = photo.resize((max(1, int(photo.width * k)), max(1, int(photo.height * k))), Image.LANCZOS)
    x, y = (W - ph.width) // 2, (H - ph.height) // 2
    frame = Image.new("RGB", (ph.width + 12, ph.height + 12), (255, 255, 255))
    im.paste(frame, (x - 6, y - 6))
    im.paste(ph, (x, y))
    return (x, y, x + ph.width, y + ph.height)


# ---------------------------------------------------------------- build
def build(photo_src, club, out, kicker_text=None, competition=None, crest_url=None,
          use_cutout=True, crest_name=None):
    photo = load_photo(photo_src)
    base, accent = club_colours(club, competition)
    im = background(base, accent)
    watermark_crest(im, crest_url, crest_name or club, base)
    cut = cutout(photo) if use_cutout else None
    mode = "cutout" if cut is not None else "pillarbox"
    box = place_subject(im, cut) if cut is not None else pillarbox(im, photo, base)
    brand(im)
    kicker(im, kicker_text, accent)
    os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
    im.save(out, "JPEG", quality=88, optimize=True, progressive=True)
    return {"out": out, "mode": mode, "size": [W, H], "subject_box": list(box),
            "colours": {"base": base, "accent": accent}, "bytes": os.path.getsize(out)}


def crest_for(club):
    """The club's badge URL from the site's data, when the feed has one."""
    try:
        import build_site as b                               # noqa: PLC0415
        for m in b.load("matches.json") + b.load("fixtures.json"):
            for side in ("home", "away"):
                if b.ar_team(m.get(side)) == club and m.get(f"{side}_badge"):
                    return m[f"{side}_badge"]
    except Exception:                                        # noqa: BLE001
        pass
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--photo", required=True, help="local file or http(s) URL of the LICENSED photo")
    ap.add_argument("--club", required=True, help="the club / team name as the site writes it (colours)")
    ap.add_argument("--out", required=True, help="media/hero-<short-ascii>.jpg")
    ap.add_argument("--kicker", help="short Arabic line bottom-right (club, competition)")
    ap.add_argument("--competition", help="to pick the Saudi Al-Ahli's green over Egypt's red")
    ap.add_argument("--crest", help="badge URL (default: looked up in our data)")
    ap.add_argument("--no-cutout", action="store_true", help="skip rembg, use the pillarbox")
    args = ap.parse_args()
    r = build(args.photo, args.club, args.out, args.kicker, args.competition,
              args.crest or crest_for(args.club), not args.no_cutout)
    print(json.dumps(r, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
