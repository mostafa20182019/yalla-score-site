r"""A degraded football-data answer must not shrink a season (2026-09-13).

    python tests/test_fixtures_merge.py     (from the repo root)
"""
import os, sys
sys.path.insert(0, os.getcwd())
sys.stdout.reconfigure(encoding="utf-8")
import fetch_data as FD


def row(mid, home, away, kick, status, rd, hs=None, aw=None):
    return {"match_id": mid, "home": home, "away": away, "kickoff": kick, "koff_time": "20:00",
            "status": status, "home_score": hs, "away_score": aw, "round": rd}


prev = [
    {"competition": "Primera Division", "current": 4, "src": "fd", "rounds": [
        {"round": r, "matches": [row(100 + r, f"H{r}", f"A{r}", f"2026-09-{r:02d}", "UPCOMING", r)]}
        for r in range(1, 39)]},
    {"competition": "Serie A", "current": 3, "rounds": [                      # written before the src mark existed
        {"round": r, "matches": [row(300 + r, f"S{r}", f"T{r}", f"2026-09-{r:02d}", "UPCOMING", r)]}
        for r in range(1, 39)]},
    {"competition": "Egyptian Premier League", "current": 3, "rounds": [      # a 365scores league, never this feed's
        {"round": 3, "matches": [row(9, "Ahly", "Zamalek", "2026-09-10", "FINISHED", 3, 1, 0)]}]},
]

# 1) degraded fetch: only rounds 4 and 5 came back -> the previous rounds are kept, fresh rows win
by = {"Primera Division": {4: [row(104, "H4", "A4", "2026-09-04", "FINISHED", 4, 2, 0)],
                           5: [row(105, "H5", "A5", "2026-09-05", "LIVE", 5, 1, 0)]},
      "Serie A": {4: [row(304, "S4", "T4", "2026-09-04", "FINISHED", 4, 0, 0)]}}
out, note = FD.merge_fixture_rounds(by, prev)
pd_ = out["Primera Division"]
assert sorted(pd_) == list(range(1, 39)), sorted(pd_)
assert pd_[4][0]["status"] == "FINISHED" and pd_[4][0]["home_score"] == 2, pd_[4]      # fresh row overrides
assert pd_[5][0]["status"] == "LIVE" and pd_[1][0]["status"] == "UPCOMING", (pd_[5], pd_[1])
assert sum(len(v) for v in pd_.values()) == 38
assert sorted(out["Serie A"]) == list(range(1, 39))                                  # unmarked but fetched -> merged too
assert "Egyptian Premier League" not in out, out.keys()                              # never pulled into the FD merge
assert note and "Primera Division: 2 fetched < 38 kept" in note and "Serie A" in note, note
print("1 OK: a league that came back short keeps its season; the fresh rows override the old ones")

# 2) a complete fetch never merges: the feed is the truth when it answers (even if an id changed)
full = {"Primera Division": {r: [row(200 + r, f"X{r}", f"Y{r}", f"2026-09-{r:02d}", "UPCOMING", r)] for r in range(1, 39)}}
out2, note2 = FD.merge_fixture_rounds(full, prev)
assert out2["Primera Division"][1][0]["match_id"] == 201 and note2 is None, note2
print("2 OK: a complete answer replaces the file outright")

# 3) nothing to merge with (first run, broken file) -> untouched
out3, note3 = FD.merge_fixture_rounds({"Primera Division": {4: []}}, [])
assert out3 == {"Primera Division": {4: []}} and note3 is None
print("3 OK: no previous file, no merge")

# 4) a league the feed dropped entirely AND that was never marked is left alone (transition case)
out4, note4 = FD.merge_fixture_rounds({"Primera Division": {4: [row(104, "H4", "A4", "2026-09-04", "FINISHED", 4, 2, 0)]}},
                                      [prev[1]])
assert "Serie A" not in out4 and note4 is None
print("4 OK: an unmarked league absent from the fetch is not resurrected")

# 5) a league marked src fd that vanished from the fetch IS restored from the file
out5, note5 = FD.merge_fixture_rounds({}, [prev[0]])
assert sorted(out5["Primera Division"]) == list(range(1, 39)) and "0 fetched" in note5, note5
print("5 OK: a marked league that vanished comes back from the file")
print("ALL FIXTURES MERGE TESTS PASSED")
