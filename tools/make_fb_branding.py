#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Facebook / share images for the sticker logo (chosen 2026-11-07):

    "C:\Program Files\Python312\python.exe" tools/make_fb_branding.py --out DIR

  fb-cover.png    1640x924  flat site blue; logo-mix centred in the 1280x624
                            safe box (the band both the desktop and the phone
                            crop keep), 60% of its width; nothing else
  fb-profile.png  1080x1080 flat blue; the mark centred, 62% of the width -
                            Facebook crops a circle, the mark's square sits
                            inside it (474 px corner radius < 540)
  og-default.png  1200x630  flat blue; logo-mix centred, 55% wide
  icon-sample.png 512x512   the profile with 20% rounded corners (app-icon
                            preview); _icon-preview.png puts it next to a
                            64 px copy to judge legibility

Everything is drawn from tools/make_logo.py (same art, same rim), the blue
is style.css --green #1f94d3 (fb_cards.BLUE)."""
import argparse
import os
import sys

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tools"))
sys.stdout.reconfigure(encoding="utf-8")
from fb_cards import BLUE                                         # noqa: E402
import make_logo as L                                             # noqa: E402

SAFE = (180, 150, 1280, 624)       # the cover's safe box: x, y, w, h


def fit(im, w=None, h=None):
    """The sticker trimmed to its rim, scaled to width w (or height h)."""
    im = im.crop(im.getbbox())
    k = w / im.width if w else h / im.height
    return im.resize((max(1, round(im.width * k)), max(1, round(im.height * k))), Image.LANCZOS)


def centred(size, art, cx=None, cy=None):
    im = Image.new("RGBA", size, BLUE + (255,))
    cx = size[0] / 2 if cx is None else cx
    cy = size[1] / 2 if cy is None else cy
    im.alpha_composite(art, (int(cx - art.width / 2), int(cy - art.height / 2)))
    return im.convert("RGB")


def rounded(im, frac=0.2):
    """im with its corners cut round (radius = frac of the side), transparent."""
    m = Image.new("L", im.size, 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, im.width - 1, im.height - 1],
                                        radius=int(im.width * frac), fill=255)
    out = im.convert("RGBA")
    out.putalpha(m)
    return out


def main():
    ap = argparse.ArgumentParser(description="Facebook cover/profile + og image from the sticker logo")
    ap.add_argument("--out", required=True, help="output folder (outside the repo)")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    logo, mark = L.logo_mix(), L.mark()

    sx, sy, sw, sh = SAFE
    cover = centred((1640, 924), fit(logo, w=int(sw * 0.60)), sx + sw / 2, sy + sh / 2)
    L.save(cover, os.path.join(a.out, "fb-cover.png"))

    profile = centred((1080, 1080), fit(mark, w=int(1080 * 0.62)))
    L.save(profile, os.path.join(a.out, "fb-profile.png"))

    og = centred((1200, 630), fit(logo, w=int(1200 * 0.55)))
    L.save(og, os.path.join(a.out, "og-default.png"))

    icon = rounded(profile.resize((512, 512), Image.LANCZOS))
    L.save(icon, os.path.join(a.out, "icon-sample.png"))
    small = rounded(profile.resize((64, 64), Image.LANCZOS))
    sheet = Image.new("RGBA", (512 + 40 + 64 + 80, 512 + 80), (238, 242, 246, 255))   # style.css --bg
    sheet.alpha_composite(icon, (40, 40))
    sheet.alpha_composite(small, (512 + 80, 40))
    L.save(sheet.convert("RGB"), os.path.join(a.out, "_icon-preview.png"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
