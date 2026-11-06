# -*- coding: utf-8 -*-
r"""The free-photo finder (2026-11-06) — the offline parts.

    python tests/test_find_photo.py      (from the repo root)

The licence gate is the whole point: CC BY / CC BY-SA / CC0 / public domain
pass, anything NC or ND or unlabelled is refused, Openverse's short codes
and Commons' long names both read correctly. The merge keeps the widest
first and drops duplicates by URL. No network.
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())

import find_photo as F                                  # noqa: E402

fails = 0


def check(cond, msg):
    global fails
    print(("  ok   " if cond else "  FAIL ") + msg)
    if not cond:
        fails += 1


for s in ("CC BY 4.0", "CC BY-SA 3.0", "CC0", "Public domain", "CC BY 2.0", "CC BY-SA 4.0",
          "CC BY-SA 2.0", "cc by", "CC BY-SA", "CC0 1.0", "CC PDM 1.0"):
    check(F.licence_ok(s), f"accepts {s!r}")
for s in ("CC BY-NC 4.0", "CC BY-NC-SA 2.0", "CC BY-ND 4.0", "CC BY-NC-ND 3.0", "", None,
          "Copyrighted", "Fair use", "All rights reserved", "GFDL"):
    check(not F.licence_ok(s), f"refuses {s!r}")

# the merge: a monkeypatched find() with canned sources
F.commons_search = lambda q, n: ["File:A.jpg", "File:B.jpg"]
F.commons_imageinfo = lambda titles: [
    {"source": "commons", "title": "File:A.jpg", "url": "u/a", "thumb": "u/a", "page": "p/a",
     "width": 900, "height": 600, "licence": "CC BY 4.0", "author": "x", "date": "", "description": ""},
    {"source": "commons", "title": "File:B.jpg", "url": "u/b", "thumb": "u/b", "page": "p/b",
     "width": 3000, "height": 2000, "licence": "CC BY-NC 4.0", "author": "x", "date": "", "description": ""},
]
F.openverse = lambda q, n: [
    {"source": "openverse/flickr", "title": "c", "url": "u/c", "thumb": "u/c", "page": "p/c",
     "width": 2400, "height": 1600, "licence": "CC BY 2.0", "author": "y", "date": "", "description": ""},
    {"source": "openverse/wikimedia", "title": "A again", "url": "U/A", "thumb": "u/a", "page": "p/a",
     "width": 900, "height": 600, "licence": "CC BY 4.0", "author": "x", "date": "", "description": ""},
]
cands, sub = F.find("q", None, 1200, 10)
check([c["url"] for c in cands] == ["u/c", "u/a"], f"NC dropped, duplicate dropped, widest first: {[c['url'] for c in cands]}")
check(cands[0]["wide"] and not cands[1]["wide"], "the width flag follows --min-width")

print("\nALL OK" if not fails else f"\n{fails} FAILED")
sys.exit(1 if fails else 0)
