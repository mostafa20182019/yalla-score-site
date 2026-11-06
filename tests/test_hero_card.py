# -*- coding: utf-8 -*-
r"""The article hero composer (2026-11-06).

    python tests/test_hero_card.py      (from the repo root)

Offline: a synthetic "photo" (a figure on a plain background) goes through
both paths — the cutout when rembg and its model are present, the pillarbox
always — and the output must be 1600x900, >= 1200 px wide for Discover, with
the club's colour as the dominant background and the subject inside the band
the article page shows. Colour picking is checked for a red club, a white
club (Real Madrid must not get a white canvas) and an unknown name (brand).
"""
import os
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())

from PIL import Image, ImageDraw                        # noqa: E402
import hero_card as HC                                  # noqa: E402

fails = 0


def check(cond, msg):
    global fails
    print(("  ok   " if cond else "  FAIL ") + msg)
    if not cond:
        fails += 1


# colours
base, acc = HC.club_colours("الأهلي")
check(base == (192, 12, 36), f"Al Ahly base is its red {base}")
base, acc = HC.club_colours("ريال مدريد")
check(HC._lum(base) < 200, f"Real Madrid never gets a white canvas {base}")
base, acc = HC.club_colours("الزمالك")
check(base == (200, 16, 46), f"Zamalek (white/red bands) picks the red {base}")
base, acc = HC.club_colours("الأهلي", "Saudi Pro League")
check(base == (11, 138, 62), f"Saudi Al-Ahli is green by competition {base}")
base, acc = HC.club_colours("نادي غير معروف")
check(base == HC.BRAND, "an unknown club falls back to the brand blue")
base, acc = HC.club_colours("مصر")
check(base == (192, 12, 36), "the national team is red")

# a synthetic portrait: a dark figure on a flat light background
tmp = tempfile.mkdtemp(prefix="hero-")
src = os.path.join(tmp, "photo.jpg")
im = Image.new("RGB", (800, 1000), (235, 235, 230))
d = ImageDraw.Draw(im)
d.ellipse((300, 120, 500, 320), fill=(90, 60, 40))           # head
d.rectangle((250, 320, 550, 1000), fill=(180, 20, 30))        # shirt
im.save(src, quality=92)

out = os.path.join(tmp, "hero.jpg")
r = HC.build(src, "الأهلي", out, kicker_text="الأهلي", use_cutout=False)
check(r["mode"] == "pillarbox", "pillarbox on request")
h = Image.open(out)
check(h.size == (1600, 900), f"output is 1600x900 ({h.size})")
check(os.path.getsize(out) < 600_000, f"under 600 KB ({os.path.getsize(out) // 1024} KB)")
px = h.convert("RGB").getpixel((40, 450))
check(px[0] > px[1] + 40 and px[0] > px[2] + 40, f"the margin is the club's red {px}")
x0, y0, x1, y1 = r["subject_box"]
check(y0 <= 900 * 0.12, f"the subject starts inside the hero band (top {y0})")

r2 = HC.build(src, "الأهلي", os.path.join(tmp, "hero2.jpg"), use_cutout=True)
check(r2["mode"] in ("cutout", "pillarbox"), f"cutout path returns a mode ({r2['mode']})")
if r2["mode"] == "cutout":
    x0, y0, x1, y1 = r2["subject_box"]
    check(y1 == 900, "the cutout is anchored to the bottom edge")
    check(x0 > 0 and x1 < 1600, "the cutout stays inside the canvas")
    check(y0 < 900 * 0.3, f"the head sits in the band the page shows (top {y0})")
else:
    print("  (rembg or its model is absent here: cutout path not exercised)")

print("\nALL OK" if not fails else f"\n{fails} FAILED")
sys.exit(1 if fails else 0)
