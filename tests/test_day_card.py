# -*- coding: utf-8 -*-
r"""The day card across competitions (day_card.py, designer review 2026-11-19).

    python tests/test_day_card.py      (from the repo root)

The nightly results card and the morning fixtures card were redrawn: one
header (a red tag, a two-word title, the date ONCE), the matches under their
competition's name, ONE match framed in the logo's red. What this guards is
the choice of that match (the card and the reel must frame the same one), the
grouping order, the fallback when the competitions are too many for the
card, and that a single competition's card keeps its old layout.
"""
import os
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())

import day_card as DC        # noqa: E402
import day_reel as DR        # noqa: E402

fails = 0


def ck(msg, cond, extra=""):
    global fails
    print(("  ok   " if cond else "  FAIL ") + msg + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails += 1


PL, LL, Q = "Premier League", "Primera Division", "Africa Cup of Nations Qualification"


def fx(i, h, a, comp=PL, t="18:00"):
    return {"match_id": i, "home": h, "away": a, "competition": comp, "status": "TIMED", "koff_time": t,
            "home_score": None, "away_score": None, "home_badge": None, "away_badge": None}


def res(i, h, a, hs, as_, comp=PL):
    return dict(fx(i, h, a, comp), status="FINISHED", home_score=hs, away_score=as_)


day = [fx(1, "FC Barcelona", "Villarreal CF", LL), fx(2, "Hull City AFC", "Brighton & Hove Albion FC"),
       fx(3, "Liverpool FC", "Manchester United FC"), fx(4, "Getafe CF", "Club Atlético de Madrid", LL)]
ck("1 the hero: a match between TWO curated sides beats an earlier match with one", DC.day_hero(day)["match_id"] == 3)
ck("2 ...one curated side is enough when no match has two", DC.day_hero([day[1], day[0], day[3]])["match_id"] == 1)
ck("3 fixtures with none of ours: no hero (nothing to rank them by)", DC.day_hero([day[1], day[3]]) is None)
r = [res(1, "Hull City AFC", "Brighton & Hove Albion FC", 4, 0), res(2, "Getafe CF", "Club Atlético de Madrid", 1, 2, LL)]
ck("4 results with none of ours: the widest margin", DC.day_hero(r)["match_id"] == 1)
q = [res(1, "توجو", "الجزائر", 0, 3, Q), res(2, "مالاوي", "مصر", 0, 0, Q), res(3, "إثيوبيا", "موزمبيق", 0, 1, Q)]
ck("5 a break night: Egypt first, then an Arab nation, before any margin",
   DC.day_hero(q)["match_id"] == 2 and DC.day_hero([q[2], q[0]])["match_id"] == 1)
ck("6 Egypt at any age is Egypt («مصر تحت 17»)",
   DC.day_hero([res(1, "توجو", "الجزائر", 0, 3, Q), res(2, "مصر تحت 17", "اليونان تحت 17", 1, 1, "FIFA U-17 World Cup")])["match_id"] == 2)
ck("7 the card and the reel frame the same match", DR.hero_of(q)["match_id"] == DC.day_hero(q)["match_id"]
   and DR.hero_of(r)["match_id"] == DC.day_hero(r)["match_id"])

g = DC.day_groups(day, DC.day_hero(day))
ck("8 groups: the hero's competition first and the hero first in it, the rest in the order they appear",
   [c for c, _ in g] == [PL, LL] and [m["match_id"] for m in g[0][1]] == [3, 2] and [m["match_id"] for m in g[1][1]] == [1, 4])
ck("9 no hero: the caller's order, untouched", [(c, [m["match_id"] for m in ms]) for c, ms in DC.day_groups(day)] == [(LL, [1, 4]), (PL, [2, 3])])

tmp = tempfile.mkdtemp()
from PIL import Image        # noqa: E402

out = os.path.join(tmp, "a.jpg")
info = DC.render(day, "2026-11-22", "all", out)
im = Image.open(out)
ck("10 the fixtures card: 1080x1350, grouped by competition, the hero named", im.size == (1080, 1350)
   and info["grouped"] and info["groups"] == 2 and info["hero"] == 3 and info["rows"] == 4, str(info))
px = im.convert("RGB").getpixel((60, 67))
ck("11 the red tag of the logo's red in the corner", px[0] > 190 and px[1] < 80 and px[2] < 120, str(px))
many = [res(i, f"Team {i} FC", f"Side {i} FC", i, 0, f"Competition {i}") for i in range(1, 10)]
info2 = DC.render(many, "2026-11-22", "all", os.path.join(tmp, "b.jpg"))
ck("12 nine matches from nine competitions: no group headers, every row still drawn",
   not info2["grouped"] and info2["rows"] == 9 and info2["hero"] == 9, str(info2))
info3 = DC.render(day, "2026-11-22", "all", os.path.join(tmp, "c.jpg"), theme="light")
ck("13 the light theme draws the same card on the reels' blue",
   info3 == info and Image.open(os.path.join(tmp, "c.jpg")).convert("RGB").getpixel((540, 20))[2] > 170)
src = open("day_card.py", encoding="utf-8").read()
ck("14 one competition's card keeps its own layout (the new branch is for comp == \"all\" only)",
   'if comp == "all" and not part:' in src)
ck("15 the channel under a kick-off comes from the verified table only (match_tv), never guessed",
   'm.get("channel") or match_tv(m)' in src)

print("ALL OK" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
