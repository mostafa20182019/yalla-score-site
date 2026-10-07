r"""AI match pieces for the FEATURED clubs + «هل أصاب توقعنا؟» (2026-10-07).

    python tests/test_featured_pieces.py   (from the repo root)

User ask: «عايز تحليل عن مباريات الفرق المميزة وعن توقعنا». Previews/reports
now cover the hub's featured clubs (HUB_FOCUS) besides the 11 curated ones,
big games (both clubs featured) first; a report carries the frozen pre-match
prediction and the verdict, a miss as plainly as a hit. Pure: no network.
"""
import datetime
import io
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())
fails = []


def ck(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  [{extra}]" if extra else ""))
    if not cond:
        fails.append(name)


import article_put as AP                                   # noqa: E402
import match_brief as MB                                   # noqa: E402
import store                                               # noqa: E402

E, P = "Egyptian Premier League", "Premier League"
ck("both featured (Egypt)", MB.featured_sides({"competition": E, "home": "الزمالك", "away": "الأهلي"}) == 2)
ck("one featured (England, football-data names)",
   MB.featured_sides({"competition": P, "home": "Arsenal FC", "away": "Leeds United FC"}) == 1)
ck("none featured", MB.featured_sides({"competition": E, "home": "سموحة", "away": "غزل المحلة"}) == 0)
ck("a curated club outside HUB_FOCUS still counts (Trabzonspor is in both; Pyramids too)",
   MB.featured_sides({"competition": E, "home": "بيراميدز", "away": "سموحة"}) == 1)

now = datetime.datetime(2026, 10, 10, 9, 0, tzinfo=MB.CAIRO)
def up(mid, comp, h, a, t):
    return {"match_id": mid, "competition": comp, "home": h, "away": a, "status": "UPCOMING",
            "kickoff": "2026-10-10", "koff_time": t}
d = {"matches": [up(1, E, "سموحة", "غزل المحلة", "18:00"),          # nobody featured
                 up(2, P, "Arsenal FC", "Leeds United FC", "14:30"),  # one featured, soonest
                 up(3, P, "Liverpool FC", "Manchester City FC", "21:00")],  # big game
     "articles": [], "goal_events": [], "details": []}
cs = MB.candidates(d, now=now)
ck("a match without a featured club is not a candidate", 1 not in [int(c["match_id"]) for c in cs])
ck("the big game (both featured) goes first", [int(c["match_id"]) for c in cs] == [3, 2], [c["match_id"] for c in cs])
ck("daily caps are 6 previews and 6 reports", MB.PREVIEW_DAILY_CAP == 6 and MB.REPORT_DAILY_CAP == 6)

store.pred_all = lambda: {"9": {"ph": 0.62, "pd": 0.21, "pa": 0.17, "score": "2-0", "conf": "mid"}}
fin = {"match_id": 9, "competition": P, "home": "Liverpool FC", "away": "Manchester City FC",
       "home_score": 0, "away_score": 1}
pc = MB.prediction_check(fin)
ck("report: the frozen prediction, formatted like the page", (pc["home_win"], pc["draw"], pc["away_win"]) == ("62%", "21%", "17%"))
ck("report: a MISS is called a miss", pc["hit"] is False and pc["verdict_ar"] == "لم يُصب التوقع", pc["verdict_ar"])
ck("report: no logged prediction -> no section", MB.prediction_check(dict(fin, match_id=10)) is None)

body = "<p>" + "كلمة " * 320 + "</p>"
rec = {"title": "t", "summary": "s", "body": body, "author": "a", "pub_date": "2026-10-10", "match_id": 9, "kind": "report"}
bad, _ = AP.validate(rec)
ck("a report without --match-brief is refused", any("--match-brief" in x for x in bad), bad)
brief = {"kind": "report", "match": {"match_id": 9}, "prediction_check": pc}
bad2, _ = AP.validate(rec, brief=brief)
ck("a report quoting our prediction must carry the disclaimer", any("ليست نصيحة للمراهنة" in x for x in bad2), bad2)
ok, _ = AP.validate(dict(rec, body=body + "<p>رجّح النموذج بنسبة 62% … وليست نصيحة للمراهنة.</p>"), brief=brief)
ck("a report with the brief's own 62% and the disclaimer passes", ok == [], ok)

w = io.open("worker.js", encoding="utf-8").read()
t = io.open("wrangler.toml", encoding="utf-8").read()
ck("six match slots (10:00 and 15:00 added)", 'const MATCH_SLOTS = ["10:00", "13:00", "15:00", "17:00", "20:00", "23:30"];' in w)
ck("the match cron string is identical in wrangler.toml and worker.js",
   '"0 7,8,9,10,12,13,14,16,17 * * *"' in t and '"0 7,8,9,10,12,13,14,16,17 * * *"' in w)
ck("still five cron strings (the free-plan cap)", t.split("crons = [", 1)[1].split("]", 1)[0].count('"') == 10)

print(f"\n{len(fails)} failed" if fails else "\nall passed")
sys.exit(1 if fails else 0)
