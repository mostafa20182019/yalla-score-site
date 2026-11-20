# -*- coding: utf-8 -*-
r"""The club form / streak posts' rules of 2026-11-20 (story_events.STREAK_STEPS).

    python tests/test_form_rules.py      (from the repo root)

Two questions were open since the form card was built (2026-11-09) and kept
FB_FORM off: what when two curated clubs meet, and when a run is posted
again. The answers: one card a match, none for a head-to-head pair, a run at
5 then only at 8 and 10; the card alone (no reel), two a day at most.
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())

import fb_post as P            # noqa: E402
import story_events as SE      # noqa: E402

fails = 0


def ck(msg, cond, extra=""):
    global fails
    print(("  ok   " if cond else "  FAIL ") + msg + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails += 1


def rows(marks):
    """Form rows from a string of W/D/L, oldest first."""
    out = []
    for i, mk in enumerate(marks):
        gf, ga = {"W": (1, 0), "D": (0, 0), "L": (0, 1)}[mk]
        out.append({"mark": mk, "gf": gf, "ga": ga, "match_id": i, "opponent": "X", "date": "2026-10-01",
                    "comp_label": "", "competition": "", "club_badge": None})
    return out


print("1. a run is posted when it reaches 5, 8 or 10 - not at every match after the fifth")
got = {n: SE.streak_milestone(rows("L" + "W" * n)) for n in range(3, 12)}
ck("wins: 5, 8 and 10 only", {n for n, v in got.items() if v} == {5, 8, 10}
   and all(v == ("wins", n) for n, v in got.items() if v), str(got))
got = {n: SE.streak_milestone(rows("W" + "D" * n)) for n in range(3, 12)}
ck("without a win: 5, 8 and 10 only", {n for n, v in got.items() if v} == {5, 8, 10}, str(got))
ck("the first defeat after five wins or more is still posted, once",
   SE.streak_milestone(rows("D" + "W" * 6 + "L")) == ("first-loss", 6)
   and SE.streak_milestone(rows("D" + "W" * 6 + "LL")) is None
   and SE.streak_milestone(rows("D" + "W" * 4 + "L")) is None)


def ev(slug, mid, home, away, run):
    return {"kind": SE.KIND_FORM, "ref": f"form:{slug}:{mid}", "run": ["W", run],
            "next": {"match_id": mid, "home": home, "away": away}}


print("2. one form card a match")
a, b = ev("arsenal", 1, "أرسنال", "تشيلسي", 2), ev("chelsea", 1, "أرسنال", "تشيلسي", 4)
c = ev("liverpool", 2, "ليفربول", "برينتفورد", 1)
from site_lib import h2h as H      # noqa: E402
if not H.pair_of_match("أرسنال", "تشيلسي"):
    ck("two curated clubs in one match: the side on the longer run, whatever the order",
       [e["ref"] for e in SE.one_per_match([a, b, c])] == ["form:chelsea:1", "form:liverpool:2"]
       and [e["ref"] for e in SE.one_per_match([b, a, c])] == ["form:chelsea:1", "form:liverpool:2"])
    a2 = ev("arsenal", 1, "أرسنال", "تشيلسي", 4)
    ck("the same run: the first in the clubs' own order",
       [e["ref"] for e in SE.one_per_match([a2, b])] == ["form:arsenal:1"])
p = H.PAIRS[0]
pa, pb = (p.get("a") or p.get("home") or ""), (p.get("b") or p.get("away") or "")
names = [v for v in p.values() if isinstance(v, str)]
derby = next(((x, y) for x in names for y in names if x != y and H.pair_of_match(x, y)), None)
ck("a pair with a head-to-head page is found by its two names", derby is not None, str(p))
if derby:
    d1, d2 = ev("x", 9, derby[0], derby[1], 6), ev("y", 9, derby[0], derby[1], 3)
    ck("... and gets NO form card: the head-to-head reel owns that morning",
       SE.one_per_match([d1, d2, c]) == [c])

print("3. the card alone, two a day")
ck("no form reel after the card, and two form cards a Cairo day at most",
   P.FORM_REEL is False and P.FORM_DAILY_MAX == 2)
src = open("fb_post.py", encoding="utf-8").read()
ck("events_post counts both form kinds against the day's limit before claiming",
   "for k in FORM_KINDS) >= FORM_DAILY_MAX" in src
   and src.index("FORM_KINDS) >= FORM_DAILY_MAX") < src.index("if not store.claim(kind, ref, title=title):"))
ck("FB_FORM is still its own switch", 'os.environ.get("FB_FORM"' in src)

print("\nALL OK" if not fails else f"\n{fails} FAILED")
sys.exit(1 if fails else 0)
