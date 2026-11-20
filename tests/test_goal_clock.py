# -*- coding: utf-8 -*-
r"""«ساعة الأهداف» (goal_clock.py, designer review 2026-11-19).

    python tests/test_goal_clock.py      (from the repo root)

A finished match's goals on a 90-minute dial. What it guards: a minute lands
where the dial says (kick-off at the top, half-time at the bottom), the card
is drawn only from a goal list that adds up to the score, an own goal says
so, and the nightly post picks ONE match, with the night's results.
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

# ---------------------------------------------------------------- the nightly post (2026-11-20: «جميلة اعملها»)
import datetime                    # noqa: E402
import story_events as SE          # noqa: E402
import story_social as SS          # noqa: E402

DAY = "2026-11-08"


def fin(i, h, a, hs, as_, comp="Premier League"):
    return {"match_id": i, "home": h, "away": a, "home_score": hs, "away_score": as_, "status": "FINISHED",
            "kickoff": DAY, "koff_time": "18:00", "competition": comp, "home_badge": None, "away_badge": None}


def det(i, h, a, goals):
    return {"match_id": i, "home": SE.ar_team(h), "away": SE.ar_team(a), "date": DAY, "cards": [], "subs": [], "lineups": {},
            "goals": [{"side": s_, "player": f"لاعب {n}", "minute": str(mn), "tag": ""} for n, (s_, mn) in enumerate(goals)]}


MS = [fin(1, "Everton FC", "Fulham FC", 4, 2), fin(2, "Liverpool FC", "Brentford FC", 2, 1),
      fin(3, "Arsenal FC", "Chelsea FC", 1, 0), fin(4, "Team X", "Team Y", 5, 4, comp="Some Small League")]
DT = [det(1, "Everton FC", "Fulham FC", [("h", 5), ("a", 20), ("h", 30), ("h", 50), ("a", 70), ("h", 88)]),
      det(2, "Liverpool FC", "Brentford FC", [("h", 12), ("a", 40), ("h", 77)]),
      det(3, "Arsenal FC", "Chelsea FC", [("h", 60)]),
      det(4, "Team X", "Team Y", [("h", i * 9 + 1) for i in range(5)] + [("a", i * 9 + 5) for i in range(4)])]
D8 = datetime.date(2026, 11, 8)
ev = SS.goal_clock_night(MS, [], DT, D8)
ck("12 the night's dial: ONE match - one of ours with three goals or more (Liverpool 2-1), not the bigger score of others",
   len(ev) == 1 and ev[0]["ref"] == DAY and ev[0]["match"]["match_id"] == 2 and len(ev[0]["goals"]) == 3, str([e["title"] for e in ev]))
t = ev[0]["text"] if ev else ""
ck("13 the caption: the result, then every goal with its minute and its side, the match page, #الجون last",
   "ساعة الأهداف" in t and t.count("الدقيقة ") == 3 and "الدقيقة 12:" in t and "/m/2" in t and t.splitlines()[-1].startswith("#الجون"), t)
ev2 = SS.goal_clock_night([MS[0], MS[2], MS[3]], [], DT, D8)
ck("14 none of ours with three goals: the fullest dial of the leagues we show (6 goals) - never a league nobody follows (9 goals)",
   len(ev2) == 1 and ev2[0]["match"]["match_id"] == 1)
ck("15 a night without a three-goal match, a match whose goals do not add up, no details: no post",
   SS.goal_clock_night([MS[2]], [], DT, D8) == [] and SS.goal_clock_night([MS[1]], [], [det(2, "Liverpool FC", "Brentford FC", [("h", 12)])], D8) == []
   and SS.goal_clock_night(MS, [], [], D8) == [])
from zoneinfo import ZoneInfo      # noqa: E402
at = lambda d, h: datetime.datetime(2026, 11, d, h, 5, tzinfo=ZoneInfo("Africa/Cairo"))      # noqa: E731
ck("16 the clock: with the night's results (from 23:00 Cairo, still that night until 03:00)",
   SS.goal_clock_night(MS, [], DT, at(8, 21)) == [] and len(SS.goal_clock_night(MS, [], DT, at(8, 23))) == 1
   and (SS.goal_clock_night(MS, [], DT, at(9, 1)) or [{}])[0].get("ref") == DAY and SS.goal_clock_night(MS, [], DT, at(9, 10)) == [])
import fb_post as fp               # noqa: E402
src = io.open("fb_post.py", encoding="utf-8").read()
ck("17 registered once, posted as the CARD with the caption, the text alone when the card fails - and not behind FB_SOCIAL (he asked for it)",
   [k for k, _ in SE.DETECTORS].count(SS.KIND_CLOCK) == 1 and SS.KIND_CLOCK not in fp.SOCIAL_KINDS
   and 'GClock.render(ev["match"], ev["goals"])' in src)
im2 = G.render(ev[0]["match"], ev[0]["goals"])
ck("18 the event alone draws the card (what the nightly run does)", im2.size == (1080, 1350))

print("ALL OK" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
