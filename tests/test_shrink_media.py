r"""The media library stays web-sized (2026-09-20).

    python tests/test_shrink_media.py     (from the repo root)

media/ had reached 75 MB: 240 photos averaging 323 KB, 96 over 300 KB and three
over a megabyte — the largest a 4544x2452, 3.2 MB hero. The article pipeline
downloads from Wikimedia at full size, so this is not a one-off clean-up; the
shrinker runs in publish.yml before every build.

The tests are mostly about what the shrinker must NOT do, because each of those
mistakes is expensive: a renamed file breaks an article's image_url, its CC
credit line and the Facebook posts that scraped it; an upscale or a pointless
re-encode loses quality for nothing.
"""
import glob, io, os, sys, tempfile, shutil
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())
from PIL import Image
import shrink_media as SM

fails = []
def ck(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  [{extra}]" if extra else ""))
    if not cond:
        fails.append(name)

tmp = tempfile.mkdtemp()
def make(name, w, h, quality=95, colour=(200, 30, 30)):
    """A photo-like image: noise, so JPEG cannot cheat it down to nothing."""
    import random
    im = Image.new("RGB", (w, h), colour)
    px = im.load()
    random.seed(1)
    for y in range(0, h, 2):
        for x in range(0, w, 2):
            px[x, y] = (random.randrange(256), random.randrange(256), random.randrange(256))
    p = os.path.join(tmp, name)
    im.save(p, "JPEG", quality=quality)
    return p

# ------------------------------------------------------------- the library
fs = sorted(glob.glob("media/*.jpg"))
sizes = [os.path.getsize(f) / 1024 for f in fs]
widths = [Image.open(f).size[0] for f in fs]
ck("1 no photo is wider than the widest slot the site renders",
   max(widths) <= SM.MAX_W, f"max {max(widths)}px")
ck("2 no photo is over a megabyte any more",
   max(sizes) < 1024, f"largest {max(sizes):.0f} KB")
ck("3 the library is web-sized", sum(sizes) / 1024 < 60,
   f"{sum(sizes) / 1024:.1f} MB, avg {sum(sizes) / len(sizes):.0f} KB")

# --------------------------------------------------------- what it must not do
big = make("wide.jpg", 3000, 1500)
before = os.path.getsize(big)
b, a = SM.shrink(big)
ck("4 an oversized photo is resized and re-encoded", a < b and Image.open(big).size[0] == SM.MAX_W,
   f"{b // 1024} → {a // 1024} KB, now {Image.open(big).size[0]}px")
ck("5 the filename is untouched (image_url, CC credit and FB previews depend on it)",
   os.path.exists(big) and os.path.basename(big) == "wide.jpg")
b2, a2 = SM.shrink(big)
ck("6 running it again does nothing (idempotent - it runs on every publish)", a2 == b2)

small = make("small.jpg", 800, 600, quality=70)
sb = os.path.getsize(small)
b3, a3 = SM.shrink(small)
ck("7 a small photo is never upscaled and never touched",
   a3 == b3 == sb and Image.open(small).size == (800, 600))

# a big-but-already-efficient file must not be re-encoded for a crumb
eff = make("efficient.jpg", 1500, 900, quality=40)
be, ae = SM.shrink(eff)
ck("8 a re-encode that would not really shrink it is skipped",
   ae == be or (be - ae) / be >= SM.MIN_GAIN, f"{be // 1024} → {ae // 1024} KB")

# orientation: a photo the camera marked as rotated must come out upright
rot = Image.new("RGB", (2000, 1000), (10, 120, 10))
p = os.path.join(tmp, "rot.jpg")
exif = Image.Exif()
exif[274] = 6                      # orientation: rotate 90
rot.save(p, "JPEG", quality=95, exif=exif)
SM.shrink(p)
w, h = Image.open(p).size
ck("9 EXIF rotation is applied, not dropped and left sideways", h > w, f"{w}x{h}")

# ---------------------------------------------------------------- the wiring
wf = open(".github/workflows/publish.yml", encoding="utf-8").read()
ck("10 it runs before the build on every publish",
   "Shrink new photos" in wf and wf.index("Shrink new photos") < wf.index("Build the static site"))
ck("11 a failure never takes the publish down",
   "Shrink new photos" in wf and "continue-on-error: true" in
   wf[wf.index("Shrink new photos"):wf.index("Shrink new photos") + 200])
ck("12 the smaller bytes are committed back, or every run would redo the work",
   "':!data/predictions.json' media/" in wf)

shutil.rmtree(tmp, ignore_errors=True)
print()
print(f"{len(fails)} FAILED: {', '.join(fails)}" if fails else "ALL MEDIA-SIZE TESTS PASSED")
sys.exit(1 if fails else 0)
