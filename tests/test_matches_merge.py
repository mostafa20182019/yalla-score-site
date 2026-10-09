r"""The day window (matches.json) keeps a league the feed dropped (2026-10-09),
the same rule as merge_fixture_rounds for the season.

    python tests/test_matches_merge.py     (from the repo root)
"""
import os, sys, datetime
sys.path.insert(0, os.getcwd())
sys.stdout.reconfigure(encoding="utf-8")
import fetch_data as FD

FDC = "https://crests.football-data.org/64.png"
S365 = "https://imagecache.365scores.com/x.png"

def row(mid, comp, kick, status="UPCOMING", badge=FDC, hs=None, aw=None):
    return {"match_id": mid, "competition": comp, "home": f"H{mid}", "away": f"A{mid}", "home_badge": badge,
            "away_badge": badge, "kickoff": kick, "koff_time": "20:00", "status": status,
            "home_score": hs, "away_score": aw, "round": 6, "channel": None}

cutoff, horizon = datetime.date(2026, 10, 4), datetime.date(2026, 10, 23)
prev = [row(1, "Premier League", "2026-10-10"), row(2, "Premier League", "2026-10-11"),
        row(3, "Premier League", "2026-09-20", "FINISHED", hs=1, aw=0),          # outside the window: not restored
        row(4, "UEFA Champions League", "2026-10-21"),
        row(9, "Egyptian Premier League", "2026-10-11", badge=S365)]              # never this feed's
# 1) the feed answered the PL with nothing and the UCL with nothing: both kept from the file
out, note = FD.merge_window_matches([row(7, "Primera Division", "2026-10-10")], prev, cutoff, horizon)
ids = sorted(m["match_id"] for m in out)
assert ids == [1, 2, 4, 7], ids
assert "Premier League: 0 fetched < 2 kept -> 2 merged" in note and "UEFA Champions League: 0 fetched < 1 kept" in note, note
assert "Egyptian" not in note
print("1 OK: a league the feed dropped keeps its window rows; the 365scores league and out-of-window rows are left alone")

# 2) a short answer: the fresh row overrides, the missing one is kept
out2, note2 = FD.merge_window_matches([row(2, "Premier League", "2026-10-11", "LIVE", hs=1, aw=0)], prev, cutoff, horizon)
pl = {m["match_id"]: m for m in out2 if m["competition"] == "Premier League"}
assert set(pl) == {1, 2} and pl[2]["status"] == "LIVE" and pl[1]["status"] == "UPCOMING", pl
print("2 OK: the fresh row wins, the missing one is kept")

# 3) a complete (or larger) answer never merges - the feed is the truth when it answers
full = [row(1, "Premier League", "2026-10-10", "FINISHED", hs=2, aw=2), row(2, "Premier League", "2026-10-11"),
        row(5, "Premier League", "2026-10-17"), row(4, "UEFA Champions League", "2026-10-21")]
out3, note3 = FD.merge_window_matches(full, prev, cutoff, horizon)
assert note3 is None and sorted(m["match_id"] for m in out3) == [1, 2, 4, 5], (note3, out3)
print("3 OK: a complete answer replaces the window outright")

# 4) no previous file -> untouched
out4, note4 = FD.merge_window_matches([row(7, "Primera Division", "2026-10-10")], [], cutoff, horizon)
assert note4 is None and len(out4) == 1
print("4 OK: nothing to merge with on the first run")

# 5) the merged rows come back sorted by kick-off
assert [m["match_id"] for m in out] == [1, 7, 2, 4] or [m["kickoff"] for m in out] == sorted(m["kickoff"] for m in out)
print("5 OK: sorted by kick-off")
print("ALL MATCHES-MERGE TESTS PASSED")
