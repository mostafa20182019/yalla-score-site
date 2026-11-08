# -*- coding: utf-8 -*-
"""news_image.py - the article image, style C (user choice 2026-11-08).

    python tests/test_news_image.py        (from the repo root)

Pins what the design promises: our navy panel and blue edge, the photo
framed so the head is never sliced, a blurred pillarbox stripped (and a
blurred BACKGROUND left alone), no club crest or kit colour anywhere in the
code, and a long label that shrinks instead of overflowing. Synthetic photos
- no network, no model. One real-photo face check runs only where rembg is
installed (the article runners), because without the person finder the
plain face cascade can pick a face in the crowd.
"""
import io
import os
import random
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())
from PIL import Image, ImageFilter  # noqa: E402

import news_image as N  # noqa: E402

fails = []


def ok(n, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + n + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails.append(n)


def noise(w, h, seed=1):
    rnd = random.Random(seed)
    small = Image.new("RGB", (w // 4, h // 4))
    small.putdata([(rnd.randrange(256), rnd.randrange(256), rnd.randrange(256)) for _ in range((w // 4) * (h // 4))])
    return small.resize((w, h), Image.NEAREST)


src = io.open("news_image.py", encoding="utf-8").read()

# 1 the house style is C, and it is the default
ok("1 style C is the default of build() and of the command line",
   'def build(photo_src, out, kicker="", style="c"' in src and 'ap.add_argument("--style", default="c"' in src)

# 2 a portrait photo with a red "hair" band at the very top and the face just under it
photo = noise(600, 1200)
for y in range(0, 40):
    for x in range(0, 600):
        photo.putpixel((x, y), (230, 20, 20))
TMP = os.environ.get("TEMP") or os.environ.get("RUNNER_TEMP") or "/tmp"
tmp = os.path.join(TMP, "news_image_test.jpg")
p = os.path.join(TMP, "news_image_src.png")
photo.save(p)
im, face = N.build(p, tmp, "الأهلي", "c", "0.5,0.08")
ok("2 the image is 1600x900 RGB", im.size == (1600, 900) and im.mode == "RGB", im.size)
px = im.getpixel((100, 800))
ok("3 the left panel is our navy", max(px) < 70 and px[2] >= px[0], px)
edge = im.getpixel((600, 450))
ok("4 the slanted edge is the site blue", abs(edge[0] - 31) < 40 and abs(edge[1] - 148) < 40 and abs(edge[2] - 211) < 40, edge)
top = im.getpixel((1100, 4))
ok("5 the head is never sliced: the hair band at the photo's top edge is still in the image", top[0] > 150 and top[1] < 90, top)

# 6 a centred pillarbox is stripped; a one-sided blurred background is not
sharp = noise(400, 762, seed=2)
bg = sharp.resize((1600, 762)).filter(ImageFilter.GaussianBlur(28))
padded = bg.copy()
padded.paste(sharp, (600, 0))
w = N.unpad(padded).width
ok("6a a centred pillarbox (400 px photo on blurred bands) is stripped", 360 <= w <= 420, w)
bokeh = noise(1600, 900, seed=3)
bokeh.paste(bokeh.crop((0, 0, 500, 900)).filter(ImageFilter.GaussianBlur(25)), (0, 0))
ok("6b a photo with one blurred side (bokeh) is left whole", N.unpad(bokeh).width == 1600, N.unpad(bokeh).width)

# 7 no club marks in the design
ok("7 no club crest, kit colour or cutout in the code",
   "assets-src/crests" not in src and "kit_for" not in src and "import matchup_card" not in src
   and "only_mask=True" in src and "remove(small, only_mask=True" in src)

# 8 a long label shrinks to fit the panel
im2, _ = N.build(p, tmp, "باريس سان جيرمان وأولمبيك مارسيليا", "c", "0.5,0.2")
ok("8 a long label renders without overflowing the panel (no exception, size kept)", im2.size == (1600, 900))

# 8b the mood grade (2026-11-08: «لو الخبر حزين تخلى الصورة حزينة ولو الخبر حلو تخلى الصورة مفرحة»)
from PIL import ImageStat  # noqa: E402
col = noise(900, 900, seed=5)
p2 = os.path.join(TMP, "news_image_mood.png")
col.save(p2)
sat = {}
for mood in ("happy", "neutral", "sad"):
    im_m, _ = N.build(p2, None, "الأهلي", "c", "0.5,0.3", mood)
    region = im_m.crop((900, 100, 1500, 800)).convert("HSV")
    sat[mood] = ImageStat.Stat(region).mean[1]
    if mood == "sad":
        sad_edge = im_m.getpixel((600, 450))
ok("8b the mood grades the photo: happy more colourful than neutral, sad far less",
   sat["happy"] > sat["neutral"] + 3 and sat["sad"] < sat["neutral"] * 0.6, {k: round(v) for k, v in sat.items()})
ok("8c a sad image trades the bright blue edge for a muted steel one", abs(sad_edge[2] - 146) < 30 and sad_edge[2] - sad_edge[0] < 60, sad_edge)
ok("8d the mood is a command-line choice: happy / neutral / sad", '"--mood"' in src and set(N.MOODS) == {"happy", "neutral", "sad"})
ok("8e the grade never touches the person: no cutout, no face or shirt edit in grade()",
   "def grade(" in src and "remove(" not in src[src.index("def grade("):src.index("def style_c(")])
try:
    os.remove(p2)
except Exception:
    pass

# 9 the real-photo face check, only where the person finder exists
try:
    import rembg  # noqa: F401
    has_rembg = True
except Exception:
    has_rembg = False
if has_rembg and os.path.exists("media/dembele-france-2026.jpg"):
    f = N.find_face(N.unpad(N.load_photo("media/dembele-france-2026.jpg")))
    ok("9 Dembélé's face is found on his head, not in the crowd beside it", f is not None and 600 < f[0] < 820 and f[1] < 320, f)
else:
    print("  skip 9 (rembg not installed here - the article runners have it)")

for f_ in (tmp, p):
    try:
        os.remove(f_)
    except Exception:
        pass
print(f"\n{len(fails)} FAILED: {fails}" if fails else "\nALL NEWS IMAGE TESTS PASSED")
sys.exit(1 if fails else 0)
