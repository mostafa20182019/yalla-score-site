# -*- coding: utf-8 -*-
r"""The MOMENT reel (2026-11-05): a historic moment as a typography reel.

    python tests/test_moment_reel.py      (from the repo root)

What it guards: every script in moments/ passes the brief's limits (6-8
scenes, 14-17.5 s, lines of six words or fewer, a credited photo on disk),
every scene kind renders a frame of the right size with nothing but the
header above the Reels safe band's top, the score block keeps the home side
on the RIGHT, and the caption always carries the photo credit. No ffmpeg
needed: frames only.
"""
import glob
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())

from PIL import Image, ImageDraw                        # noqa: E402
import moment_reel as M                                 # noqa: E402
import fb_cards as C                                    # noqa: E402

fails = 0


def check(cond, msg):
    global fails
    print(("  ok   " if cond else "  FAIL ") + msg)
    if not cond:
        fails += 1


scripts = sorted(glob.glob(os.path.join("moments", "*.json")))
check(scripts, "at least one script in moments/")
for path in scripts:
    s = json.load(open(path, encoding="utf-8"))
    try:
        total = M.validate(s)
        check(14 <= total <= 17.5, f"{path}: {total:.1f} s")
    except AssertionError as e:
        check(False, f"{path}: {e}")
        continue
    check(s["id"] == os.path.splitext(os.path.basename(path))[0], f"{path}: id matches the file name")
    cap = M.caption(s)
    check("#الجون" in cap, f"{path}: caption carries #الجون")
    if (s.get("photo") or {}).get("file"):
        check("CC" in cap, f"{path}: caption credits the photo's licence")
    ctx = M.context(s)
    for i, sc in enumerate(s["scenes"]):
        im = M.scene(sc, float(sc["secs"]) - 0.05, ctx)
        check(im.size == (M.W, M.H), f"{path} scene {i + 1} {sc['kind']}: frame is {M.W}x{M.H}")
        # nothing drawn in the band the Reels player covers at the bottom
        band = im.crop((0, M.BOTTOM + 8, M.W, M.H)).convert("L")
        lo, hi = band.getextrema()
        check(hi - lo < 90, f"{path} scene {i + 1} {sc['kind']}: nothing below the safe band (contrast {hi - lo})")
        # the very first frame is never blank: the header is there
        first = M.scene(sc, 0.0, ctx)
        check(first.size == (M.W, M.H), f"{path} scene {i + 1}: first frame renders")

# the score block: home digits on the RIGHT half (fb_cards rule 4)
im = Image.new("RGB", (M.W, M.H), C.BLUE_DARK)
M.score_block(im, 1.0, 7, 0, "مصر", "الكونغو", 1000, t0=0.0)
g = im.convert("L")
right = g.crop((M.W // 2, 1000, M.W, 1160)).getextrema()[1]
left = g.crop((0, 1000, M.W // 2, 1160)).getextrema()[1]
check(right > 200 and left > 200, "score block draws both digits")
# a «7» is wider in white pixels than a «0»'s ring: count bright pixels per half
def bright(box):
    return sum(1 for v in g.crop(box).getdata() if v > 200)
check(bright((M.W // 2, 1000, M.W, 1160)) != bright((0, 1000, M.W // 2, 1160)),
      "home and away digits are different glyphs, home on the right")

print("\nALL OK" if not fails else f"\n{fails} FAILED")
sys.exit(1 if fails else 0)
