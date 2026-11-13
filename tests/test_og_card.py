# -*- coding: utf-8 -*-
r"""Link-preview images drawn at build time (og_card.py, 2026-11-13).

    python tests/test_og_card.py     (from the repo root)

The head-to-head pages and the league hubs shared the site banner as their
og:image. They now get a 1200x630 card of their own numbers, drawn into
dist/og/ during the build. What must stay true: the size, equal values share
a rank, a failure never breaks a build, and head() knows the size of an image
that exists only in dist/.
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


import og_card as OG                                       # noqa: E402
from PIL import Image                                      # noqa: E402

ck("1 equal values share a rank", OG.shared_ranks([10, 9, 9, 9, 8]) == [1, 2, 2, 2, 5]
   and OG.shared_ranks([2, 2, 2, 2, 1]) == [1, 1, 1, 1, 5] and OG.shared_ranks([]) == [])

tmp = tempfile.mkdtemp()
p = OG.h2h("طرابزون سبور", "فنربخشة", 15, "فبراير 2020", 6, 1, 8, None, None,
           os.path.join(tmp, "og", "h2h", "x.jpg"))
ck("2 the head-to-head image is written, 1200x630, with no crest at hand",
   bool(p) and Image.open(p).size == (1200, 630))
p2 = OG.league("الدوري التركي", "الهدافون",
               [(1, None, "جيفت أوربان", 10), (2, None, "محمد صلاح", 9)], "هدف", "2026-2027",
               "تحديث 13 نوفمبر 2026", os.path.join(tmp, "og", "scorers", "x.jpg"), head="الترتيب · اللاعب")
ck("3 the league image is written, 1200x630", bool(p2) and Image.open(p2).size == (1200, 630))
ck("4 a league with no rows draws nothing",
   OG.league("x", "جدول الترتيب", [], "نقطة", "2026", "", os.path.join(tmp, "none.jpg")) is None
   and not os.path.exists(os.path.join(tmp, "none.jpg")))
ck("5 a failure returns None instead of raising (the page keeps the banner)",
   OG.h2h("a", "b", 1, "x", 0, 0, 0, None, None, os.path.join(tmp, "bad\0name.jpg")) is None)
ck("6 a preview under 300 KB", os.path.getsize(p) < 300_000 and os.path.getsize(p2) < 300_000)

import site_lib.shell as SH                                # noqa: E402

SH.DIST = tmp
SH._OG_DIMS.clear()
ck("7 head() reads the size of an image that lives only in dist/",
   SH._og_dims(SH.SITE_BASE + "/og/h2h/x.jpg") == (1200, 630))

src = io.open("site_pages/leagues.py", encoding="utf-8").read()
ck("8 a zeroed or last-season table gets no image (five clubs on 0 points are not a ranking)",
   'if not st.get("zeroed") and not st.get("past"):' in src)
ck("9 the scorers image ranks with shared_ranks", "og_card.shared_ranks(" in src)
hsrc = io.open("site_pages/h2h.py", encoding="utf-8").read()
ck("10 the head-to-head page passes its own tally to the image", "og_card.h2h(a, b, n," in hsrc)
ck("11 nothing is drawn into git: the images go to dist/og",
   'os.path.join(DIST, "og"' in src and 'os.path.join(DIST, "og"' in hsrc)

print()
if fails:
    print(f"{len(fails)} FAILED: " + "; ".join(fails))
    sys.exit(1)
print("all good")
