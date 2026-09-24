# -*- coding: utf-8 -*-
"""Score-verification guards (no network): fetch_data.reconcile_with_live and
fb_cards.score_verified. Reproduces the Betis 1-1 (FD) vs 1-0 (365scores) case."""
import sys, os, json, importlib.util, time, datetime
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ---- fetch_data.reconcile_with_live ---------------------------------------
spec = importlib.util.spec_from_file_location("fetch_data", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fetch_data.py"))
fd = importlib.util.module_from_spec(spec); spec.loader.exec_module(fd)
now = datetime.datetime.now(fd.CAIRO)
kod = now - datetime.timedelta(hours=2)            # date AND time of the kick-off (midnight-safe)
ko = kod.strftime("%H:%M")
today = kod.strftime("%Y-%m-%d")
LIVE = {"games": [
    {"h": "ريال بيتيس", "a": "ريال مدريد", "hs": 1, "as": 0, "live": False, "c": 11},
    {"h": "إبسويتش تاون", "a": "ليفربول", "hs": 0, "as": 2, "live": False, "c": 7},
    {"h": "سيلتا فيجو", "a": "ريال سوسيداد", "hs": 1, "as": 1, "live": True, "c": 11},   # reversed vs FD
]}
fd.http_get = lambda url, headers=None, timeout=40, retries=2: json.dumps(LIVE)
rows = [
    {"match_id": 1, "home": "Real Betis Balompié", "away": "Real Madrid CF", "kickoff": today, "koff_time": ko, "status": "FINISHED", "home_score": 1, "away_score": 1},
    {"match_id": 2, "home": "Ipswich Town FC", "away": "Liverpool FC", "kickoff": today, "koff_time": ko, "status": "FINISHED", "home_score": 0, "away_score": 2},
    {"match_id": 3, "home": "Real Sociedad de Fútbol", "away": "RC Celta de Vigo", "kickoff": today, "koff_time": ko, "status": "FINISHED", "home_score": 0, "away_score": 0},
    {"match_id": 4, "home": "Aston Villa FC", "away": "Arsenal FC", "kickoff": "2026-08-31", "koff_time": "22:00", "status": "FINISHED", "home_score": 0, "away_score": 1},
    {"match_id": 5, "home": "الأهلي", "away": "سموحة", "kickoff": today, "koff_time": ko, "status": "FINISHED", "home_score": 1, "away_score": 0},
]
dbg = {}
n = fd.reconcile_with_live(rows, dbg)
assert n == 2, (n, dbg)
assert (rows[0]["home_score"], rows[0]["away_score"], rows[0]["status"]) == (1, 0, "FINISHED")   # Betis corrected 1-1 -> 1-0
assert (rows[1]["home_score"], rows[1]["away_score"]) == (0, 2)                                    # unchanged, agrees
assert (rows[2]["home_score"], rows[2]["away_score"], rows[2]["status"]) == (1, 1, "LIVE")        # reversed pair, still live
assert rows[3]["home_score"] == 0 and rows[3]["status"] == "FINISHED"                              # old row untouched
assert rows[4]["home_score"] == 1                                                                  # 365 row untouched
print("reconcile OK:", dbg["reconcile"])
# live.json down -> nothing changes, no crash
fd.http_get = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down"))
rows2 = [dict(rows[0], home_score=1, away_score=1)]
assert fd.reconcile_with_live(rows2, dbg) == 0 and rows2[0]["home_score"] == 1 and "FAIL" in dbg["reconcile"]
print("reconcile OK: live.json outage leaves data untouched")

# ---- fb_cards.score_verified ----------------------------------------------
# the stability timer moved into store.py (fb_seen); drive it on a throwaway
# sqlite file so this suite keeps testing the real behaviour
import tempfile
for _k in ("CF_API_TOKEN", "CF_ACCOUNT_ID", "CF_D1_ID"):
    os.environ.pop(_k, None)
os.environ["D1_SQLITE"] = os.path.join(tempfile.mkdtemp(), "state.sqlite")
import store
import fb_cards as fc
assert store.backend() == "sqlite", store.backend()
store.init_schema()
live = {(fc.b._gnorm(g["h"]), fc.b._gnorm(g["a"])): g for g in LIVE["games"]}
betis = {"match_id": 564667, "home": "Real Betis Balompié", "away": "Real Madrid CF", "home_score": 1, "away_score": 1}
ok, why = fc.score_verified(betis, live); assert not ok and "mismatch" in why, why
betis_fixed = dict(betis, away_score=0)
ok, why = fc.score_verified(betis_fixed, live); assert ok and "365scores" in why, why
celta = {"match_id": 9, "home": "RC Celta de Vigo", "away": "Real Sociedad de Fútbol", "home_score": 1, "away_score": 1}
ok, why = fc.score_verified(celta, live); assert not ok and "still live" in why, why
# pair not in live.json -> stability rule
t0 = 1_000_000
unk = {"match_id": 77, "home": "Everton FC", "away": "Manchester United FC", "home_score": 0, "away_score": 3}
ok, why = fc.score_verified(unk, live, now=t0); assert not ok and "first seen" in why, why
ok, why = fc.score_verified(unk, live, now=t0 + 10 * 60); assert not ok and "stable for 10" in why, why
ok, why = fc.score_verified(dict(unk, away_score=2), live, now=t0 + 20 * 60); assert not ok and "first seen" in why   # score changed -> clock restarts
ok, why = fc.score_verified(dict(unk, away_score=2), live, now=t0 + 20 * 60 + fc.STABLE_MIN * 60 + 1); assert ok, why
print("score_verified OK: mismatch deferred, confirmed posts, live deferred, unknown pair needs a stable score")
print("ALL SCORE VERIFY TESTS PASSED")
