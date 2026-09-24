r"""The per-kind caps and the report window (2026-09-13).

    python tests/test_match_pick.py        (from the repo root)

Why this test exists: previews and reports shared ONE daily cap of 4 while the
writer ran one article per slot, four slots a day - so a day full of previews
spent the reports' budget. Of the 16 curated matches of 2026-09-08..13, 16 got
a preview and 8 got a report. The caps are separate now, and --pick --kind lets
the final-whistle dispatch ask for a report specifically.
"""
import datetime, os, sys
sys.path.insert(0, os.getcwd())
import match_brief as MB

CAIRO = MB.CAIRO
# NOW is frozen because the candidate WINDOWS are relative to it. The daily
# caps are not: has_room() asks the real Cairo clock what "today" is, so the
# article fixtures must carry the real date or the test starts failing at
# midnight (it did, the morning after it was written).
NOW = datetime.datetime(2026, 9, 13, 20, 0, tzinfo=CAIRO)
TODAY = MB._now().date().isoformat()
YESTERDAY = (MB._now().date() - datetime.timedelta(days=1)).isoformat()


def match(mid, home, away, status, kickoff, koff, comp="Premier League", hs=None, as_=None):
    return {"match_id": mid, "home": home, "away": away, "status": status,
            "kickoff": kickoff, "koff_time": koff, "competition": comp,
            "home_score": hs, "away_score": as_}


def art(kind, mid, date=TODAY):
    return {"article_id": mid, "kind": kind, "match_id": mid, "pub_date": date, "title": "t"}


# An ended match needs goals or lineups in our data before it can be reported.
# goal_events entries are keyed by the ARABIC club names (365scores spellings,
# what AR_TEAM maps the football-data names to) plus the date.
GOALS = [
    {"home": "أرسنال", "away": "تشيلسي", "date": "2026-09-13",
     "goals": [{"side": "h", "player": "x", "minute": "10"}]},
    {"home": "ليفربول", "away": "فولهام", "date": "2026-09-12",
     "goals": [{"side": "h", "player": "y", "minute": "20"}]},
]

BASE = {
    "matches": [
        # ended 3 h ago (kick-off 17:00, the pick subtracts 1.75 h for the whistle)
        match("1", "Arsenal FC", "Chelsea FC", "FINISHED", "2026-09-13", "17:00", hs=1, as_=0),
        # ended YESTERDAY evening - dead under the old 14.5 h window, alive under 30 h
        match("2", "Liverpool FC", "Fulham FC", "FINISHED", "2026-09-12", "21:00", hs=2, as_=1),
        # kicks off tomorrow
        match("3", "Manchester City FC", "Everton FC", "UPCOMING", "2026-09-14", "18:00"),
        match("4", "Real Madrid", "Getafe CF", "UPCOMING", "2026-09-14", "21:00",
              comp="Primera Division"),
        # not a curated club: never a candidate
        match("5", "Everton FC", "Brentford FC", "FINISHED", "2026-09-13", "17:00", hs=0, as_=0),
    ],
    "fixtures": [], "standings": [], "scorers": [], "assists": [],
    "goal_events": GOALS, "details": [], "articles": [],
}


def data(articles=()):
    d = dict(BASE)
    d["articles"] = list(articles)
    return d


def kinds(d, now=NOW):
    return [(c["kind"], c["match_id"]) for c in MB.candidates(d, now)]


# 1) the window: a match that ended last night is still reportable
ks = kinds(data())
assert ("report", "1") in ks, ks
assert ("report", "2") in ks, "a match that ended ~21 h ago must still be reportable"
assert ("report", "5") not in ks, "a non-curated match is never a candidate"
assert MB.REPORT_MAX_H >= 24, MB.REPORT_MAX_H
print("1 OK: the report window covers last night's late game, curated clubs only")

# 2) reports come before previews, and the freshest report first
assert ks[0] == ("report", "1"), ks
ordered = [k for k, _ in ks]
assert ordered == ["report"] * ordered.count("report") + ["preview"] * ordered.count("preview"), ks
assert ks[1] == ("report", "2"), ks          # then the older one
print("2 OK: reports before previews, freshest first")

# 3) four previews today do NOT block a report (the bug this fixes)
full_previews = [art("preview", str(100 + i)) for i in range(MB.PREVIEW_DAILY_CAP)]
d = data(full_previews)
assert MB.has_room(d["articles"], "report") is True
assert MB.has_room(d["articles"], "preview") is False
sys.argv = ["match_brief.py"]
picked = next((c for c in MB.candidates(d, NOW) if MB.has_room(d["articles"], c["kind"])), None)
assert picked and picked["kind"] == "report" and picked["match_id"] == "1", picked
print("3 OK: a day full of previews still lets a report through")

# 4) and the other way round: four reports today do not block a preview
full_reports = [art("report", str(200 + i)) for i in range(MB.REPORT_DAILY_CAP)]
d = data(full_reports)
assert MB.has_room(d["articles"], "report") is False
picked = next((c for c in MB.candidates(d, NOW) if MB.has_room(d["articles"], c["kind"])), None)
assert picked and picked["kind"] == "preview", picked
print("4 OK: the report cap is a report cap - previews keep their own budget")

# 5) yesterday's articles do not count against today
d = data([art("report", str(300 + i), YESTERDAY) for i in range(6)])
assert MB.today_count(d["articles"], "report") == 0
assert MB.has_room(d["articles"], "report") is True
print("5 OK: the cap is per Cairo day")

# 6) dedup is still per (match, kind): a preview never blocks its own report
d = data([art("preview", "1")])
assert ("report", "1") in kinds(d), "the preview of match 1 must not block its report"
d = data([art("report", "1")])
assert ("report", "1") not in kinds(d), "a written report must not be written twice"
print("6 OK: dedup stays per match AND kind")

print("ALL MATCH PICK TESTS PASSED")
