# -*- coding: utf-8 -*-
r"""The free-footage finder (2026-11-09) — offline parts.

    python tests/test_find_video.py      (from the repo root)

The rating is the point: a club's own CC BY video is «rights-holder» (legal,
blocked by Rights Manager), «all goals» compilations are «broadcast?», a
supporter's {{own}} clip is «own», Universal Newsreels are «archive-pd»; the
licence gate refuses NC/ND; the merge puts own/archive first. No network.
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())

import find_video as V                                  # noqa: E402

fails = 0


def check(cond, msg):
    global fails
    print(("  ok   " if cond else "  FAIL ") + msg)
    if not cond:
        fails += 1


for s in ("CC BY 4.0", "CC BY-SA 2.0", "CC0", "Public domain", "CC BY 3.0"):
    check(V.licence_ok(s), f"accepts {s!r}")
for s in ("CC BY-NC 4.0", "CC BY-ND 4.0", "CC BY-NC-SA 3.0", "", None, "Copyrighted"):
    check(not V.licence_ok(s), f"refuses {s!r}")

check(V.rate("Train like a Real Madrid goalkeeper", "Real Madrid", "{{From YouTube|1=x}}", "")[0] == "rights-holder",
      "a club's own YouTube video is rights-holder")
check(V.rate("All 48 goals of Cristiano Ronaldo", "Someone", "{{From YouTube|1=x}}", "")[0] == "broadcast?",
      "«all goals» is a broadcast compilation")
check(V.rate("Chelsea win the Champions League", "Elizabeth Mavor", "{{From YouTube|1=x}}",
             "Just a few videos I filmed at the final")[0] == "fan-import", "a fan's YouTube import is fan-import")
check(V.rate("Kylian Mbappe at the Bernabéu", "SdHb", "{{own}}", "")[0] == "own", "{{own}} is own")
check(V.rate("Chelsea fans chanting", "cfcunofficial", "[https://www.flickr.com/photos/x Flickr]", "")[0] == "own",
      "a Flickr photographer's clip is own")
check(V.rate("1958-02-10 Britain Mourns", "Universal Studios", "https://archive.org/details/x", "")[0] == "archive-pd",
      "a Universal newsreel is archive-pd")
check(V.rate("Japanese players celebrating", "Mehdi Mortazavian", "[https://www.mehrnews.com/news/1 Mehr]", "", reviewed=True)[0] == "own",
      "a news agency's reviewed footage is own")
check(V.rate("Japanese players celebrating", "Mehdi Mortazavian", "[https://www.mehrnews.com/news/1 Mehr]", "", reviewed=False)[0] == "fan-import",
      "the same source unreviewed stays fan-import")

# merge order and dedup
V.commons = lambda q, n: [
    {"url": "u/a", "licence_ok": True, "kind": "fan-import", "width": 1920, "title": "a"},
    {"url": "u/b", "licence_ok": True, "kind": "own", "width": 1280, "title": "b"},
    {"url": "u/c", "licence_ok": False, "kind": "own", "width": 4000, "title": "c"},
    {"url": "u/a", "licence_ok": True, "kind": "fan-import", "width": 1920, "title": "a again"},
]
V.archive = lambda q, n: [{"url": "u/d", "licence_ok": True, "kind": "archive-pd", "width": None, "title": "d"}]
hits = V.find(["q"], 5)
check([h["url"] for h in hits] == ["u/b", "u/d", "u/a"], f"own, then archive, then imports; NC and duplicates dropped: {[h['url'] for h in hits]}")

print("\nALL OK" if not fails else f"\n{fails} FAILED")
sys.exit(1 if fails else 0)
