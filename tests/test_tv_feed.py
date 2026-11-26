# -*- coding: utf-8 -*-
"""The channel of a coming match by its number (tv_feed.py, 2026-11-26), the
players on a scoring run (site_lib/prefacts.player_runs) and the push before
a followed club's match (push_team.prematch).

    python tests/test_tv_feed.py
"""
import datetime
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import tv_feed as TV                       # noqa: E402
from site_lib import prefacts as PF        # noqa: E402

fails = []


def ck(name, ok):
    print(("OK   " if ok else "FAIL ") + name)
    if not ok:
        fails.append(name)


# ---- 1. the names as the site writes them
ck("1 the feed's three spellings of beIN are one",
   [TV.clean(x) for x in ("beIN SPORTS HD 1", "Bein Sports HD2", "beIN Sports 5 HD", "beIN Sports")]
   == ["beIN Sports 1", "beIN Sports 2", "beIN Sports 5", "beIN Sports"])
ck("2 any other name is kept as the feed wrote it", TV.clean(" ثمانية  1 ") == "ثمانية 1"
   and TV.clean("الرياضية المغربية (3)") == "الرياضية المغربية (3)")
ck("3 the field: the feed's order, no name twice, three at most",
   TV.channel_text(["beIN SPORTS HD 1", "beIN Sports 1 HD", "ثمانية 1"]) == "beIN Sports 1، ثمانية 1"
   and TV.channel_text([]) == "" and TV.channel_text(list("abcde")).count("،") == 2)

# ---- 2. what is asked, and when again
NOW = datetime.datetime(2026, 11, 26, 12, 0)
MS = [{"match_id": 1, "competition": "Saudi Pro League", "kickoff": "2026-11-27", "koff_time": "19:00", "status": "UPCOMING"},
      {"match_id": 2, "competition": "Saudi Pro League", "kickoff": "2026-12-10", "status": "UPCOMING"},
      {"match_id": 3, "competition": "Saudi Pro League", "kickoff": "2026-11-26", "status": "FINISHED"},
      {"match_id": 4, "competition": "Saudi Pro League", "kickoff": "2026-11-26", "status": "UPCOMING", "channel": None}]
ck("4 asked: a coming match of the next days, soonest first", [m["match_id"] for m in TV.wanted(MS, {}, NOW)] == [4, 1])
ck("5 an answer of this morning is kept, one of yesterday is asked again",
   [m["match_id"] for m in TV.wanted(MS, {"1": {"fetched": "2026-11-26T08:00:00"}, "4": {"fetched": "2026-11-25T08:00:00"}}, NOW)] == [4])


def fake(path):
    assert "userCountryId=131" in path and "gameId=" in path, path
    return {"game": {"tvNetworks": [{"name": "ثمانية 1"}, {"name": "تطبيق ثمانية"}] if "gameId=1&" in path else []}}


held, changed = TV.run(MS, {"99": {"fetched": "2026-10-01T00:00:00", "kickoff": "2026-10-01", "names": ["x"]}}, NOW, fake,
                       log=lambda *_: None)
ck("6 a run records every answer - an empty one too, so it is not asked every half hour - and drops old entries",
   changed and held["1"]["names"] == ["ثمانية 1", "تطبيق ثمانية"] and held["4"]["names"] == [] and "99" not in held)


def boom(path):
    raise OSError("offline")


h2, c2 = TV.run(MS, {}, NOW, boom, log=lambda *_: None)
ck("7 an unreachable feed records nothing and raises nothing", h2 == {} and c2 is False)
items = [dict(m) for m in MS] + [{"match_id": 5, "channel": "أون سبورت 1"}]
held["5"] = {"names": ["beIN Sports 9"]}
n = TV.apply(items, held)
ck("8 the channel is written where the feed named one - never over a value already there, never an empty one",
   n == 1 and items[0]["channel"] == "ثمانية 1، تطبيق ثمانية" and items[3].get("channel") is None
   and items[4]["channel"] == "أون سبورت 1")
import data_store as DS                    # noqa: E402
yml = open(os.path.join(ROOT, ".github", "workflows", "publish.yml"), encoding="utf-8").read()
ck("9 the store carries the file, and the publish run fills the channels after the fetch and before the save",
   "tv_feed.json" in DS.STORE_FILES and yml.index("python fetch_data.py") < yml.index("python tv_feed.py") < yml.index("python data_store.py push"))

# ---- 3. the players on a scoring run


def fm(h, a, hs, as_, day, goals, mid):
    return {"match_id": mid, "competition": "Premier League", "home": h, "away": a, "home_score": hs, "away_score": as_,
            "kickoff": day, "status": "FINISHED", "goals": goals}


def g(side, player):
    return {"side": side, "player": player, "minute": "10", "tag": ""}


SEASON = [fm("A", "x1", 0, 1, "2026-08-01", [g("a", "خصم")], 1),
          fm("A", "x2", 2, 0, "2026-08-08", [g("h", "هداف"), g("h", "زميل")], 2),
          fm("x3", "A", 1, 2, "2026-08-15", [g("h", "خصم"), g("a", "هداف"), g("a", "هداف")], 3),
          fm("A", "x4", 1, 1, "2026-08-22", [g("h", "هداف"), g("a", "خصم")], 4)]
runs, played = PF.player_runs("A", SEASON)
ck("10 he scored in each of the side's last three; the opponent's scorer is not the side's", runs == [(3, "هداف")] and played == 4)
ck("11 the sentence names the side, the count and the competition",
   PF.player_facts("A", "أ", SEASON, "الدوري الإنجليزي") == [(9, "سجل هداف في آخر 3 مباريات " + PF._lam("أ") + " في الدوري الإنجليزي.")])
HOLE = SEASON[:2] + [dict(SEASON[2], goals=[g("a", "هداف")])] + SEASON[3:]
ck("12 a match with a goal we cannot name stops the count there - no guess", PF.player_runs("A", HOLE)[0] == [])
NOGOALS = SEASON[:3] + [dict(SEASON[3], goals=None, match_id=44)]
ck("13 a match with no scorers on record gives no run", PF.player_runs("A", NOGOALS)[0] == [])
PF.GOALS.clear(); PF.GOALS["44"] = SEASON[3]["goals"]
ck("14 the archive's scorers stand in for a row that carries none", PF.player_runs("A", NOGOALS)[0] == [(3, "هداف")])
PF.GOALS.clear()
ALL = [fm("B", f"y{i}", 1, 0, f"2026-08-{i + 1:02d}", [g("h", "قناص")], 10 + i) for i in range(4)]
ck("15 every match of the season = «في كل مباريات ... هذا الموسم»",
   PF.player_facts("B", "ب", ALL, "الدوري")[0][1] == "سجل قناص في كل مباريات ب (4) في الدوري هذا الموسم.")

# ---- 4. the push before a followed club's match
import push_team as PT                     # noqa: E402
import story_events as SE                  # noqa: E402
from zoneinfo import ZoneInfo              # noqa: E402

CAIRO = ZoneInfo("Africa/Cairo")
TP = [{"slug": "al-ahly", "name": "الأهلي", "league": "Egyptian Premier League", "tokens": ["الأهلي"]}]
real = PT.TEAM_PAGES[0]
M = {"match_id": 777, "competition": real["league"], "home": real["name"], "away": "خصم", "kickoff": "2026-11-28",
     "koff_time": "20:00", "status": "UPCOMING"}


def at(hh, mm):
    return datetime.datetime(2026, 11, 28, hh, mm, tzinfo=CAIRO)


def due(now, **kw):
    return [(tp["slug"], m["match_id"]) for tp, m in PT.prematch_due([dict(M, **kw)], now, [real])]


ck("16 due between 150 and 30 minutes before kick-off, not earlier, not later",
   due(at(18, 0)) == [(real["slug"], 777)] and due(at(19, 20)) == [(real["slug"], 777)]
   and due(at(17, 0)) == [] and due(at(19, 45)) == [] and due(at(20, 30)) == [])
ck("17 a postponed match, or one with no kick-off time, is never due",
   due(at(18, 0), status="POSTPONED") == [] and due(at(18, 0), koff_time=None) == [])
p, title = PT.prematch_payload(M, "لم يخسر الفريق في آخر 6 مباريات له في الدوري المصري.")
j = json.loads(p)
ck("18 the notification: the two names and the hour, the fact under them, the match page",
   title == j["title"] == f"⏰ {SE._side_names(M)[0]} × خصم الساعة 20:00"
   and j["body"] == "لم يخسر الفريق في آخر 6 مباريات له في الدوري المصري." and j["url"].endswith("/m/777"))
ck("19 with no fact the second line is the competition", SE.comp_label(M["competition"]) in json.loads(PT.prematch_payload(M, "")[0])["body"])
src = open(os.path.join(ROOT, "push_team.py"), encoding="utf-8").read()
ck("20 once a match per club through the store, and one notification for a reader who follows both sides",
   'deliver(f"pre:{m[\'match_id\']}"' in src and "seen_by_match.setdefault" in src and "python push_team.py --prematch || true" in yml)

print()
if fails:
    print(f"{len(fails)} FAILED: " + "; ".join(fails))
    sys.exit(1)
print("ALL OK")
