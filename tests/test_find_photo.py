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

# --club (2026-11-08: the player in the STORY'S club's shirt first)
al = F.club_aliases("Paris Saint-Germain")
check("psg" in al and "saint" not in al and "paris" not in al,
      f"PSG words: psg/germain, never «saint» (Saint-Lô) or «paris» (Paris FC): {sorted(al)}")
check({"münchen", "bayern"} <= F.club_aliases("FC Bayern Munich"), "Bayern is also found as München")
check(F.club_aliases("Manchester City") == {"manchester city"}, "Manchester City is matched as the whole name, never «city» alone")
check("spurs" in F.club_aliases("Tottenham Hotspur"), "Tottenham is also found as Spurs")
F.club_files = lambda player, club, n: (["File:K1.jpg"], ["Category:Harry Kane with FC Bayern Munich"])
F.year_files = lambda player, since, n: (["File:K2.jpg", "File:K3.jpg"], ["Category:Harry Kane in 2025"])
F.commons_search = lambda q, n: ["File:K4.jpg"]
F.commons_imageinfo = lambda titles: [
    {"source": "commons", "title": "File:K4.jpg", "url": "u/k4", "thumb": "", "width": 5000, "licence": "CC BY 4.0", "description": "England v Panama"},
    {"source": "commons", "title": "File:K2.jpg", "url": "u/k2", "thumb": "", "width": 2000, "licence": "CC BY-SA 4.0",
     "description": "Testspiel", "categories": ["FC Red Bull Salzburg vs FC Bayern München 2025"]},
    {"source": "commons", "title": "File:K1.jpg", "url": "u/k1", "thumb": "", "width": 1300, "licence": "CC BY-SA 4.0", "description": ""},
    {"source": "commons", "title": "File:K3.jpg", "url": "u/k3", "thumb": "", "width": 3000, "licence": "CC BY-SA 4.0", "description": "Salzburg stadium"},
]
F.openverse = lambda q, n: []
cands, sub = F.find("Harry Kane", None, 1200, 10, club="FC Bayern Munich")
check([c["url"] for c in cands][:2] == ["u/k2", "u/k1"] and all(c["club"] for c in cands[:2]) and not cands[2]["club"],
      f"club photos first (by category name or «with <club>» filing), the rest after: {[(c['url'], c['club']) for c in cands]}")

print("\nALL OK" if not fails else f"\n{fails} FAILED")
sys.exit(1 if fails else 0)
