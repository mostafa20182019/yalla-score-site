# -*- coding: utf-8 -*-
r"""The CLIP reel (clip_reel.py, 2026-11-09): free-licensed footage retold.

    python tests/test_clip_reel.py      (from the repo root)

What it guards, with no network and no ffmpeg: every script in clips/
passes validate() (a Commons source and a CC licence per clip, in < out,
no clip over 15 s, the whole reel 28-40 s, a six-word headline), the
on-frame credit names CC BY and the caption carries the Arabic credit and
#الجون, the panel's crop window never includes the uploader's top-left
watermark, a composed frame is 1080x1920 with nothing below the Reels safe
band, and the score strip keeps the home side on the RIGHT.
"""
import glob
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())

from PIL import Image, ImageDraw                        # noqa: E402
import clip_reel as K                                   # noqa: E402
import fb_cards as C                                    # noqa: E402

fails = 0


def check(cond, msg):
    global fails
    print(("  ok   " if cond else "  FAIL ") + msg)
    if not cond:
        fails += 1


WATERMARK = (0, 0, 260, 190)        # Mehr News' logo box in the 1920x1080 source

scripts = sorted(glob.glob(os.path.join("clips", "*.json")))
check(scripts, "at least one script in clips/")
for path in scripts:
    s = json.load(open(path, encoding="utf-8"))
    try:
        total = K.validate(s)
        check(K.MIN_SECS <= total <= K.MAX_SECS, f"{path}: {total:.1f} s")
    except AssertionError as e:
        check(False, f"{path}: {e}")
        continue
    check(s["id"] == os.path.splitext(os.path.basename(path))[0], f"{path}: id matches the file name")
    cap = K.caption(s)
    check("#الجون" in cap and "CC BY" in cap and "https://elgoon.com" in cap,
          f"{path}: caption carries #الجون, the licence and the site")
    check("يلا سكور" not in json.dumps(s, ensure_ascii=False), f"{path}: the old name appears nowhere")
    ctx = K.context(s)
    for i, clip in enumerate(s["clips"], 1):
        x, y, w, h = K.crop_box(clip)
        check(x >= WATERMARK[2] or y >= WATERMARK[3], f"{path} clip {i}: crop window clear of the watermark corner")
        check(x + w <= 1920 and y + h <= 1080, f"{path} clip {i}: crop window inside the source frame")
        im = K.overlay_frame(clip, ctx)
        check(im.size == (K.W, K.H), f"{path} clip {i}: frame is {K.W}x{K.H}")
        band = im.crop((0, K.BOTTOM + 8, K.W, K.H)).convert("L")
        lo, hi = band.getextrema()
        check(hi - lo < 90, f"{path} clip {i}: nothing below the safe band (contrast {hi - lo})")
        top = im.crop((0, 12, K.W, K.TOP - 4)).convert("L")   # below the canvas' 8 px white stripe
        lo, hi = top.getextrema()
        check(hi - lo < 90, f"{path} clip {i}: nothing above the safe band (contrast {hi - lo})")
        # the credit is on every clip frame: the credit row is not flat canvas
        row = im.crop((0, K.CREDIT_Y, K.W, K.CREDIT_Y + 28)).convert("L")
        check(row.getextrema()[1] - row.getextrema()[0] > 40, f"{path} clip {i}: credit drawn on the frame")
    out = K.outro_image(s, ctx)
    check(out.size == (K.W, K.H), f"{path}: outro frame is {K.W}x{K.H}")
    band = out.crop((0, K.BOTTOM + 8, K.W, K.H)).convert("L")
    lo, hi = band.getextrema()
    check(hi - lo < 90, f"{path}: outro keeps the safe band (contrast {hi - lo})")

# the score strip: home digits on the RIGHT of the dash (fb_cards rule 4)
ctx = {"home": {"name": "ألمانيا", "flag": "de"}, "away": {"name": "اليابان", "flag": "jp"}}
lay = Image.new("RGBA", (K.W, K.H), (0, 0, 0, 0))
K.score_strip(ImageDraw.Draw(lay), lay, ctx, 7, 0)
g = lay.convert("RGB").convert("L")


def dark(box):
    return sum(1 for v in g.crop(box).getdata() if v < 80)


cy = K.STRIP_Y + K.STRIP_H // 2
right = dark((K.W // 2 - 10, K.STRIP_Y, K.W // 2 + 120, K.STRIP_Y + K.STRIP_H))
left = dark((K.W // 2 - 120, K.STRIP_Y, K.W // 2 - 10, K.STRIP_Y + K.STRIP_H))
check(right > 0 and left > 0, "score strip draws both digits")
check(right != left, "home and away digits are different glyphs («7» right, «0» left)")
check(K.flag("de") is not None and K.flag("jp") is not None and K.flag("xx") is None,
      "flags: known codes draw, unknown falls back to the crest")

print("\nALL OK" if not fails else f"\n{fails} FAILED")
sys.exit(1 if fails else 0)
