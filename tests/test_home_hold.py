# -*- coding: utf-8 -*-
"""An analysis of a match not yet played stays at the top of the home
analyses block until the match is over (user, 2026-10-09)."""
import sys, os, datetime
from zoneinfo import ZoneInfo
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from site_lib.articles import held_analyses
from site_lib.cards import home_insights

fails = 0
def ck(name, cond, extra=""):
    global fails
    print(f"  {'ok  ' if cond else 'FAIL'} {name}" + (f"  [{extra}]" if extra and not cond else ""))
    fails += 0 if cond else 1

CAIRO = ZoneInfo("Africa/Cairo")
now = datetime.datetime(2026, 10, 9, 12, 0, tzinfo=CAIRO)
A = lambda i, kind, mid=None: {"article_id": str(i), "kind": kind, "match_id": mid, "title": f"t{i}", "pub_ts": "x"}
arts = [A(700, "preview", 1), A(699, "preview", 2), A(697, "analysis", 560598), A(687, "analysis", 4804684),
        A(650, "analysis", 111), A(640, "analysis", 222), A(600, None)]
matches = [{"match_id": 560598, "kickoff": "2026-10-11", "koff_time": "18:30", "status": "UPCOMING"},
           {"match_id": 4804684, "kickoff": "2026-10-11", "koff_time": "20:00", "status": "UPCOMING"},
           {"match_id": 111, "kickoff": "2026-10-09", "koff_time": "08:00", "status": "UPCOMING"},   # 4h ago: over
           {"match_id": 222, "kickoff": "2026-10-08", "koff_time": "20:00", "status": "FINISHED"}]
held = held_analyses(arts, matches, now=now)
ck("1 analyses of unplayed matches are held, in kick-off order", held == ["697", "687"], str(held))
ck("2 a match 4h past kick-off or FINISHED is not held", "650" not in held and "640" not in held)
lead, more = home_insights(arts, False, held=held)
ck("3 the held analysis leads the block and the other follows", lead["article_id"] == "697" and more[0]["article_id"] == "687", str([lead["article_id"]] + [a["article_id"] for a in more]))
ck("4 newer previews come after the held ones", [a["article_id"] for a in more][1:3] == ["700", "699"])
lead2, more2 = home_insights(arts, False, held=[])
ck("5 nothing held: newest analytical piece leads, as before", lead2["article_id"] == "700")
lead3, _ = home_insights(arts, True, held=held)
ck("6 HOME_PIN still wins the lead when it is on", lead3["article_id"] == "700")
ck("7 the match ended -> released", held_analyses(arts, matches, now=now + datetime.timedelta(days=3)) == [])
# a match that fell out of the day window (a degraded fetch) is still found in the season fixtures
fixtures = [{"competition": "Premier League", "rounds": [{"round": 6, "matches": [
    {"match_id": 560598, "kickoff": "2026-10-11", "koff_time": "18:30", "status": "UPCOMING"}]}]}]
ck("8 a match missing from matches.json is held from fixtures.json",
   held_analyses(arts, [matches[1]], now=now, fixtures=fixtures) == ["697", "687"],
   str(held_analyses(arts, [matches[1]], now=now, fixtures=fixtures)))
print("\nALL HOME HOLD TESTS PASSED" if not fails else f"\n{fails} FAILED")
sys.exit(1 if fails else 0)
