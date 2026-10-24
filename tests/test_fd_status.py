# -*- coding: utf-8 -*-
"""fetch_data._fix_status / _norm_status unit test (no network)."""
import os
import sys, importlib.util
sys.stdout.reconfigure(encoding="utf-8")
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
spec = importlib.util.spec_from_file_location("fetch_data", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fetch_data.py"))
fd = importlib.util.module_from_spec(spec); spec.loader.exec_module(fd)

CAIRO = ZoneInfo("Africa/Cairo")
now = datetime(2026, 9, 4, 20, 12, tzinfo=CAIRO)
def row(status, hs=None, aws=None): return {"status": status, "home_score": hs, "away_score": aws}
def fix(status, hours_ago, hs=None, aws=None):
    return fd._fix_status(row(status, hs, aws), now - timedelta(hours=hours_ago), now)["status"]

# the 2026-09-04 bug: Aug-31 Villa 0-1 Arsenal came through non-FINISHED with a score
assert fix("UPCOMING", 4 * 24 + 22, 0, 1) == "FINISHED"
assert fix("LIVE", 4 * 24, 4, 3) == "FINISHED"                 # Chelsea 4-3 Brighton labelled LIVE
# the 2026-08-16 lag case still works: kicked off 30 min ago, scheduled, score flowing
assert fix("UPCOMING", 0.5, 1, 0) == "LIVE"
# genuinely live game keeps LIVE
assert fix("LIVE", 1.2, 0, 0) == "LIVE"
# LIVE but no score and >3h old -> never fake a live game
assert fix("LIVE", 5, None, None) == "UPCOMING"
# future fixture untouched
assert fix("UPCOMING", -30, None, None) == "UPCOMING"
# 2h50 in: still inside the window
assert fix("UPCOMING", 2.9, 2, 2) == "LIVE"
# finished stays finished regardless
assert fix("FINISHED", 0.1, 1, 0) == "FINISHED"
assert fix("POSTPONED", 48, None, None) == "POSTPONED"
# status map
assert fd._norm_status("AWARDED") == "FINISHED"
assert fd._norm_status("POSTPONED") == "POSTPONED" and fd._norm_status("CANCELLED") == "POSTPONED"
assert fd._norm_status("TIMED") == "UPCOMING" and fd._norm_status("PAUSED") == "LIVE"

# ---- reconcile_with_live (2026-10-24): football-data served Aston Villa x
# Man City as TIMED (no score) eight hours after kick-off; 365scores had it
# over at 2-1. An UPCOMING row past its kick-off with a live pair takes the
# pair's score and status, exactly as a LIVE/FINISHED row does.
import json as _json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # reconcile imports build_site
_real_get = fd.http_get
fd.http_get = lambda url, *a, **k: _json.dumps({"games": [
    {"h": "أستون فيلا", "a": "مانشستر سيتي", "hs": 2, "as": 1, "live": False},
    {"h": "تشيلسي", "a": "توتنهام هوتسبر", "hs": 1, "as": 0, "live": True},
]})
_now = datetime.now(CAIRO)
def _ko(hours_ago):
    t = _now - timedelta(hours=hours_ago)
    return t.strftime("%Y-%m-%d"), t.strftime("%H:%M")
_rows = [
    dict(zip(("kickoff", "koff_time"), _ko(8)), status="UPCOMING", home="Aston Villa FC", away="Manchester City FC", home_score=None, away_score=None),
    dict(zip(("kickoff", "koff_time"), _ko(1)), status="UPCOMING", home="Chelsea FC", away="Tottenham Hotspur FC", home_score=None, away_score=None),
    dict(zip(("kickoff", "koff_time"), _ko(-3)), status="UPCOMING", home="Arsenal FC", away="Everton FC", home_score=None, away_score=None),
]
_dbg = {}
_n = fd.reconcile_with_live(_rows, _dbg)
assert "FAIL" not in (_dbg.get("reconcile") or ""), _dbg
assert _rows[0]["status"] == "FINISHED" and (_rows[0]["home_score"], _rows[0]["away_score"]) == (2, 1), _rows[0]
assert _rows[1]["status"] == "LIVE" and (_rows[1]["home_score"], _rows[1]["away_score"]) == (1, 0), _rows[1]
assert _rows[2]["status"] == "UPCOMING" and _rows[2]["home_score"] is None, _rows[2]   # not kicked off: untouched
assert _n == 2, _dbg
fd.http_get = _real_get
print("ALL FD STATUS TESTS PASSED (incl. reconcile of a stale UPCOMING row)")
