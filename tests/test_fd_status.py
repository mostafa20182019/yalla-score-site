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
print("ALL FD STATUS TESTS PASSED")
