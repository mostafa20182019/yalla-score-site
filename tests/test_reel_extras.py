# -*- coding: utf-8 -*-
r"""Four additions of 2026-11-20 (user: «اعمل 9 و 10 و 11 و 13»).

    python tests/test_reel_extras.py      (from the repo root)

  9   movers_reel.py   «الصاعد والهابط» as a reel, from story_social's event
  10  round_brief.py   the Iraqi league's «الجولة بالأرقام» every two rounds
  11  club_clock.py    a club's month on one goal dial + its post kind
  13  scorers_reel.py  the assist makers' race on even rounds

Frames only, no ffmpeg.
"""
import datetime
import io
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())

import fb_reel as R                # noqa: E402
import story_events as SE          # noqa: E402
import story_social as SS          # noqa: E402

fails = 0


def ck(msg, cond, extra=""):
    global fails
    print(("  ok   " if cond else "  FAIL ") + msg + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails += 1


# ---------------------------------------------------------------- 13: scorers / assists by turn
import scorers_reel as S           # noqa: E402

race = [{"name": f"لاعب {i}", "team": "فريق", "goals": g} for i, g in enumerate((5, 4, 4, 3, 3, 2))]
ck("1 an odd round is the scorers', an even round the assist makers'", S.what_for(11, race) == "goals" and S.what_for(10, race) == "assists")
flat = [{"name": f"لاعب {i}", "team": "فريق", "goals": 3} for i in range(6)]
ck("2 a chart that is no race keeps the scorers: six level at the top, too few names, a leader on one",
   S.what_for(10, flat) == "goals" and S.what_for(10, race[:2]) == "goals"
   and S.what_for(10, [dict(r, goals=1) for r in race]) == "goals" and S.what_for(None, race) == "goals")
cap_g, cap_a = S.caption(race, "Premier League", "الدوري الإنجليزي", 10), S.caption(race, "Premier League", "الدوري الإنجليزي", 10, "assists")
ck("3 the two captions: goals in one, «تمريرات حاسمة» in the other, each with its own question and tag",
   "5 أهداف" in cap_g and "هدافي" in cap_g and "5 تمريرات حاسمة" in cap_a and "صنّاع أهداف الدوري الإنجليزي" in cap_a
   and "تمريرات" not in cap_g and "#صناع_الأهداف" in cap_a and "#سباق_الهدافين" in cap_g)
ck("4 number agreement for the assists", S.assists_word(1) == "تمريرة حاسمة واحدة" and S.assists_word(2) == "تمريرتين حاسمتين"
   and S.assists_word(11) == "11 تمريرة حاسمة")
sc = S.build(race, "Premier League", "الدوري الإنجليزي", 10, shots={}, what="assists")
ck("5 the assists reel is the same three scenes, 15 s or less, 1080x1920",
   len(sc) == 3 and sum(x[1] for x in sc) <= 15 and all(draw(dur - 0.05).size == (R.W, R.H) for draw, dur, _ in sc))
src = io.open("scorers_reel.py", encoding="utf-8").read()
ck("6 one reel a round either way: the store key does not carry the kind", 'f"scorers:{comp}:' in src and "what_for(rnd, asst)" in src)

# ---------------------------------------------------------------- 9: the movers reel
import movers_reel as MV           # noqa: E402

PLG = "Premier League"


def res(i, h, a, hs, as_, kick):
    return {"match_id": i, "home": h, "away": a, "home_score": hs, "away_score": as_, "status": "FINISHED",
            "kickoff": kick, "koff_time": "18:00", "competition": PLG}


JT = [{"pos": i + 1, "team": t, "pts": p, "played": 10, "crest": None} for i, (t, p) in enumerate(
    (("Everton FC", 16), ("Arsenal FC", 15), ("Chelsea FC", 14), ("Liverpool FC", 12), ("Fulham FC", 9),
     ("Brentford FC", 7), ("Leeds United FC", 6), ("Burnley FC", 5)))]
JR = [res(1, "Burnley FC", "Arsenal FC", 1, 0, "2026-11-07"), res(2, "Brentford FC", "Liverpool FC", 1, 0, "2026-11-08"),
      res(3, "Everton FC", "Leeds United FC", 3, 0, "2026-11-08"), res(4, "Fulham FC", "Chelsea FC", 2, 0, "2026-11-07")]
data = {"matches": [], "fixtures": [{"competition": PLG, "rounds": [{"round": 10, "matches": JR}]}],
        "standings": [{"competition": PLG, "table": JT}]}
evs = MV.events_for(datetime.date(2026, 11, 9), data)
ck("7 the reel is drawn from story_social's event: the same moves, each with the table's crest slot",
   len(evs) == 1 and evs[0]["moves"] and all({"team", "before", "after", "crest"} <= set(m) for m in evs[0]["moves"]))
ev = evs[0]
scenes = MV.build(ev)
# two scenes since 2026-11-20: the title-only opening left, the clubs are on frame 0
ck("8 two scenes (rows, outro), 12.5 s, every frame 1080x1920", len(scenes) == 2 and abs(sum(s[1] for s in scenes) - 12.5) < 1e-9
   and all(draw(dur - 0.05).size == (R.W, R.H) for draw, dur, _ in scenes))
cap = MV.caption(ev)
ck("9 the caption is the event's own lines, one question, the table's link, #الجون",
   all(ln in cap for ln in ev["lines"]) and "standings/england" in cap and cap.count("؟") == 1 and "#الجون" in cap)
lag = dict(data, standings=[{"competition": PLG, "table": [dict(r, played=9) for r in JT]}])
ck("10 a table that does not hold the round yet (it lags the results): no event, so no reel", MV.events_for(datetime.date(2026, 11, 9), lag) == [])
ck("11 the movers are a reel now, not a text post: the kind is in no post list",
   SS.KIND_MOVERS not in SS.SOCIAL_KINDS and SS.KIND_MOVERS not in [k for k, _ in SE.DETECTORS])
wf = io.open(".github/workflows/fb-post.yml", encoding="utf-8").read()
ck("12 the nightly run posts it after the scorers reel and can never fail the job",
   "python movers_reel.py --auto | tee -a /tmp/fb.txt || true" in wf and wf.index("scorers_reel.py --auto") < wf.index("movers_reel.py --auto"))

# ---------------------------------------------------------------- 11: a club's month on the dial
import club_clock as CC            # noqa: E402
from site_lib.matchdata import match_details_index     # noqa: E402

EPL = "Egyptian Premier League"


def m(i, h, a, hs, as_, day):
    return {"match_id": i, "home": h, "away": a, "home_score": hs, "away_score": as_, "status": "FINISHED",
            "kickoff": f"2026-10-{day:02d}", "competition": EPL, "home_badge": None, "away_badge": None}


def dt(i, h, a, day, goals):
    return {"match_id": i, "home": h, "away": a, "date": f"2026-10-{day:02d}", "cards": [], "subs": [], "lineups": {},
            "goals": [{"side": s_, "player": "لاعب", "minute": str(mn), "tag": ""} for s_, mn in goals]}


MS = [m(1, "الأهلي", "سموحة", 2, 0, 3), m(2, "المصري", "الأهلي", 1, 1, 10), m(3, "الأهلي", "الجونة", 3, 1, 20),
      m(4, "الأهلي", "إنبي", 0, 0, 27)]
DT = [dt(1, "الأهلي", "سموحة", 3, [("h", 12), ("h", 80)]), dt(2, "المصري", "الأهلي", 10, [("h", 30), ("a", 88)]),
      dt(3, "الأهلي", "الجونة", 20, [("h", 5), ("a", 44), ("h", 77), ("h", "90+2")])]
pool = {str(x["match_id"]): x for x in MS}
info = CC.month_info("al-ahly", "2026-10", pool, match_details_index(DT))
ck("13 the month: every goal for and against, from the club's side whoever is at home",
   info and info["matches"] == 4 and len(info["goals_for"]) == 6 and len(info["goals_against"]) == 2, str(info))
ck("14 the quarter-hours add up to the goals; added time counts with the last quarter-hour",
   info and sum(info["bands_for"]) == 6 and sum(info["bands_against"]) == 2 and info["bands_for"] == [2, 0, 0, 0, 0, 4])
ck("15 a match of the month without its full goal list: NO card (a goalless draw needs none)",
   CC.month_info("al-ahly", "2026-10", pool, match_details_index(DT[:2])) is None)
ck("16 too few matches, too few goals, no such club: no card",
   CC.month_info("al-ahly", "2026-09", pool, match_details_index(DT)) is None
   and CC.month_info("no-such-club", "2026-10", pool, match_details_index(DT)) is None)
im = CC.render(info)
ck("17 the card: 1080x1350, the family's red tag", im.size == (1080, 1350) and im.convert("RGB").getpixel((60, 67))[0] > 190)
ev = SS.club_month(MS, [], DT, datetime.date(2026, 11, 1))
ck("18 the post: day 1 of the month is the first club's, for the month before, with its best quarter-hour",
   len(ev) == 1 and ev[0]["ref"] == "al-ahly:2026-10" and "سجل 6 واستقبل 2 في 4 مباريات" in ev[0]["text"]
   and "من الدقيقة 76 إلى 90 (4 أهداف)" in ev[0]["text"], ev[0]["text"] if ev else "")
ck("19 another club's day, a day past the list, no details: nothing",
   SS.club_month(MS, [], DT, datetime.date(2026, 11, 2)) == [] and SS.club_month(MS, [], DT, datetime.date(2026, 11, 9)) == []
   and SS.club_month(MS, [], [], datetime.date(2026, 11, 1)) == [])
fb = io.open("fb_post.py", encoding="utf-8").read()
ck("20 registered once, posted as the card with the caption, not behind FB_SOCIAL",
   [k for k, _ in SE.DETECTORS].count(SS.KIND_MONTH) == 1 and SS.KIND_MONTH not in SS.SOCIAL_KINDS
   and 'CClock.render_bytes(ev["info"])' in fb)

# ---------------------------------------------------------------- 10: the Iraqi league every two rounds
import round_brief as RB           # noqa: E402

ck("21 the Iraqi league is in the round pick, last; only its even rounds are offered",
   RB.LEAGUES[-1] == "Iraq Stars League" and RB.on_schedule("Iraq Stars League", 14) and not RB.on_schedule("Iraq Stars League", 13)
   and RB.on_schedule("Egyptian Premier League", 13) and RB.on_schedule("Iraq Stars League", None))
ck("22 the other leagues keep their order: Egyptian, Turkish, then the rest", RB.LEAGUES[:2] == ["Egyptian Premier League", "Turkish Super Lig"]
   and len(RB.LEAGUES) == len(set(RB.LEAGUES)) == 9)

print("ALL OK" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
