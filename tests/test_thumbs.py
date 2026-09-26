r"""Card thumbnails (2026-09-22): cards render 640px copies, heroes keep 1600.

    python tests/test_thumbs.py   (from the repo root)

Lighthouse measured ~3 MB of the 3.9 MB home page as full-size photos inside
card slots. shrink_media.py now writes media/thumbs/<same name> at 640px and
every CARD render site maps through build_site.thumb_url; the article hero,
og:image and the RSS keep the original. Home page: 3,945 KiB -> 654 KiB.
"""
import io
import os
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())

fails = []


def ck(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  [{extra}]" if extra else ""))
    if not cond:
        fails.append(name)


import shrink_media as SM                                # noqa: E402
import build_site as B                                   # noqa: E402
from PIL import Image                                    # noqa: E402

# ---- the generator ---------------------------------------------------------
tmp = tempfile.mkdtemp(prefix="th-")
src = os.path.join(tmp, "big.jpg")
Image.new("RGB", (1600, 900), (30, 90, 160)).save(src, "JPEG")
_thumbs = SM.THUMBS
SM.THUMBS = os.path.join(tmp, "thumbs")
try:
    n1 = SM.thumb(src)
    with Image.open(os.path.join(SM.THUMBS, "big.jpg")) as im:
        w, fmt = im.width, im.format
    ck("1 a 1600px photo gets a 640px thumb, same name, same format",
       n1 > 0 and w == SM.THUMB_W and fmt == "JPEG", f"{w}px {fmt}")
    ck("2 idempotent: the second call writes nothing", SM.thumb(src) == 0)
    small = os.path.join(tmp, "small.jpg")
    Image.new("RGB", (400, 300)).save(small, "JPEG")
    SM.thumb(small)
    with Image.open(os.path.join(SM.THUMBS, "small.jpg")) as im:
        ck("3 a photo narrower than 640 is copied, never upscaled", im.width == 400)
finally:
    SM.THUMBS = _thumbs

# ---- the URL mapping -------------------------------------------------------
have = sorted(os.listdir(os.path.join("media", "thumbs")))
name = have[0] if have else None
ck("4 the repo actually holds thumbs", bool(name), str(len(have)))
ck("5 /media/<x> maps to /media/thumbs/<x> when the thumb exists",
   B.thumb_url(f"/media/{name}") == f"/media/thumbs/{name}")
ck("6 an absolute URL keeps its SITE_BASE",
   B.thumb_url(f"{B.SITE_BASE}/media/{name}") == f"{B.SITE_BASE}/media/thumbs/{name}")
ck("7 a photo with no thumb passes through (the new-image race)",
   B.thumb_url("/media/not-generated-yet.jpg") == "/media/not-generated-yet.jpg")
ck("8 external hotlinks pass through",
   B.thumb_url("https://cdn.example.com/x.jpg") == "https://cdn.example.com/x.jpg")
ck("9 the SVG placeholders pass through",
   B.thumb_url("/media/ph-pitch.svg") == "/media/ph-pitch.svg")
ck("10 an already-thumbed URL is not double-mapped",
   B.thumb_url(f"/media/thumbs/{name}") == f"/media/thumbs/{name}")

# ---- who uses it, and who must not ----------------------------------------
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_source import build_source  # noqa: E402  the whole build
bs = build_source()
ck("11 every card slot maps through thumb_url (6 sites + the home preload)",
   bs.count("thumb_url(") >= 7, str(bs.count("thumb_url(")))
ck("12 the article hero keeps the full-size file",
   'class="a-img" src="{esc(img)}"' in bs)
ck("13 og:image is never a thumb (head() receives the original)",
   'image=(feat and feat.get("image_url")) or None' in bs)
ck("14 the build ships media/thumbs into dist", 'os.path.join(DIST, "media", "thumbs")' in bs)

# ---- the pipeline order ----------------------------------------------------
wf = io.open(".github/workflows/publish.yml", encoding="utf-8").read()
ck("15 shrink_media (which writes the thumbs) runs BEFORE the build",
   0 < wf.find("shrink_media.py") < wf.find("python build_site.py"))

# ---- one rendered card -----------------------------------------------------
html = B.fmb_block({"title": "t", "image_url": f"/media/{name}",
                    "article_id": "1", "pub_date": "2026-09-22"},
                   [], "قائمة", "/news.html")
ck("16 a rendered featured card points at the thumb", f"/media/thumbs/{name}" in html)

print()
print(f"{len(fails)} FAILED: {', '.join(fails)}" if fails else "ALL THUMBS TESTS PASSED")
sys.exit(1 if fails else 0)
