# -*- coding: utf-8 -*-
r"""«ساعة الأهداف» (goal_clock.py, designer review 2026-11-19).

    python tests/test_goal_clock.py      (from the repo root)

A finished match's goals on a 90-minute dial. What it guards: a minute lands
where the dial says (kick-off at the top, half-time at the bottom), the card
is drawn only from a goal list that adds up to the score, an own goal says
so, and nothing posts the card yet - it is a generator the user looks at
first.
"""
import io
import os
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())

import goal_clock as G                                  # noqa: E402
from site_lib.matchdata import match_details_index     # noqa: E402

fails = 0


def ck(msg, cond, extra=""):
    global fails
    print(("  ok   " if cond else "  FAIL ") + msg + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails += 1


ck("1 the dial: 0' at the top, 45' at the bottom, 90' back at the top; added time stands at its minute",
   G.angle_of(0) == 0 and G.angle_of(45) == 180 and G.angle_of(90) == 360 and G.angle_of(45, 3) == 180
   and G.angle_of(22) < G.angle_of(23) and G.angle_of(105) == 60)
x0, y0 = G.polar(100, 0)
x1, y1 = G.polar(100, 90)
x2, y2 = G.polar(100, 180)
ck("2 clockwise from the top: 0 deg above the centre, 90 to the right, 180 below",
   abs(x0 - G.CX) < 1e-6 and y0 < G.CY and x1 > G.CX and abs(y1 - G.CY) < 1e-6 and y2 > G.CY)
ck("3 a minute is digits (and added time); a word is not a minute",
   G.minute_of("45+2") == (45, 2) and G.minute_of("63'") == (63, 0) and G.minute_of("استراحة") is None and G.minute_of("") is None)

M = {"match_id": 1, "home": "أ", "away": "ب", "home_score": 2, "away_score": 1, "status": "FINISHED",
     "kickoff": "2026-11-01", "competition": "Egyptian Premier League", "home_badge": None, "away_badge": None}


def idx(goals):
    return match_details_index([{"match_id": 1, "home": "أ", "away": "ب", "date": "2026-11-01", "goals": goals,
                                 "cards": [], "subs": [],
                                 "lineups": {"h": {"xi": [{"name": "أ1"}, {"name": "أ2"}]}, "a": {"xi": [{"name": "ب1"}]}}}])


GOALS = [{"side": "a", "player": "ب1", "minute": "70", "tag": ""},
         {"side": "h", "player": "أ1", "minute": "12", "tag": ""},
         {"side": "h", "player": "ب1", "minute": "45+2", "tag": ""}]        # ب1 in his own net
g = G.goals_of(M, idx(GOALS))
ck("4 the goals in match order, each on its side, with its minute", g and [(x["side"], x["minute"]) for x in g] ==
   [("h", "12"), ("h", "45+2"), ("a", "70")], str(g))
ck("5 a goal by a name from the OTHER side's line-up is an own goal", g and [x["own"] for x in g] == [False, True, False])
ck("6 a goal list that does not add up to the score: no card", G.goals_of(M, idx(GOALS[:2])) is None)
ck("7 not finished, no details, a minute that is not one: no card",
   G.goals_of(dict(M, status="LIVE"), idx(GOALS)) is None and G.goals_of(M, match_details_index([])) is None
   and G.goals_of(M, idx(GOALS[:2] + [{"side": "h", "player": "أ2", "minute": "استراحة", "tag": ""}])) is None)

out = os.path.join(tempfile.mkdtemp(), "clock.jpg")
im = G.render(M, g, out)
ck("8 the card: 1080x1350, the same size as every card of the family", im.size == (1080, 1350) and os.path.getsize(out) > 20000)
px = im.convert("RGB").getpixel((60, 67))
ck("9 the red tag of the logo's red in the corner", px[0] > 190 and px[1] < 80 and px[2] < 120, str(px))
hx, hy = G.polar(G.R_HOME, G.angle_of(12))
p = im.convert("RGB").getpixel((int(hx), int(hy) - G.MARK_R + 2))
ck("10 the 12' goal stands on the outer ring at its angle (the marker's red rim is there)", p[0] > 170 and p[1] < 110, str(p))
many = [{"side": "h", "minute": str(60 + i), "base": 60 + i, "add": 0, "player": f"لاعب {i}", "own": False} for i in range(8)]
ck("11 eight goals of one side in eight minutes still draw (markers step inward, the list says how many more)",
   G.render(dict(M, home_score=8, away_score=0), many).size == (1080, 1350))

src = io.open("fb_post.py", encoding="utf-8").read() + io.open(".github/workflows/fb-post.yml", encoding="utf-8").read()
ck("12 a generator only: nothing posts it until the user has seen the look", "goal_clock" not in src)

print("ALL OK" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
