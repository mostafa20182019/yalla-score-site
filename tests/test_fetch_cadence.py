r"""The lighter fetch (2026-09-13): standings + player charts only when a match
window is active or the last such fetch is an hour old.

    python tests/test_fetch_cadence.py     (from the repo root)
"""
import os, sys
from datetime import datetime, timedelta, timezone
sys.path.insert(0, os.getcwd())
import fetch_data as FD

CAIRO = FD.CAIRO
now = datetime(2026, 9, 13, 21, 0, tzinfo=CAIRO)          # 21:00 Cairo
now_utc = now.astimezone(timezone.utc)

live = [{"kickoff": "2026-09-13", "koff_time": "20:00", "status": "LIVE"}]
just_done = [{"kickoff": "2026-09-13", "koff_time": "18:00", "status": "FINISHED"}]     # 3 h ago: may have just ended
old_done = [{"kickoff": "2026-09-13", "koff_time": "14:00", "status": "FINISHED"}]      # 7 h ago: table long updated
upcoming = [{"kickoff": "2026-09-13", "koff_time": "22:00", "status": "UPCOMING"}]
postponed = [{"kickoff": "2026-09-13", "koff_time": "19:00", "status": "POSTPONED"}]

# 1) what counts as an active window
assert FD.match_window_active(live, now) is True
assert FD.match_window_active(just_done, now) is True
assert FD.match_window_active(old_done, now) is False
assert FD.match_window_active(upcoming, now) is False
assert FD.match_window_active(postponed, now) is False
assert FD.match_window_active([], now) is False
print("1 OK: live or finished within 4 h = active; upcoming / old / postponed / none = quiet")

# 2) the decision
fresh = {"slow_fetched_at": (now_utc - timedelta(minutes=20)).isoformat(timespec="seconds")}
stale = {"slow_fetched_at": (now_utc - timedelta(minutes=75)).isoformat(timespec="seconds")}
assert FD.slow_fetch_due(live, fresh, now_utc)[0] is True                  # active beats a fresh record
assert FD.slow_fetch_due(upcoming, fresh, now_utc)[0] is False             # quiet + fresh = skip
assert FD.slow_fetch_due(upcoming, stale, now_utc)[0] is True              # quiet + old = hourly fetch
assert FD.slow_fetch_due(upcoming, {}, now_utc)[0] is True                 # never fetched = fetch
assert FD.slow_fetch_due(upcoming, {"slow_fetched_at": "garbage"}, now_utc)[0] is True
assert FD.slow_fetch_due(None, fresh, now_utc)[0] is True                  # match list failed = know nothing = fetch
print("2 OK: active window, hourly, first run and a failed match list all fetch; quiet + fresh skips")

# 3) a naive (tz-less) timestamp in the record is read as UTC, not rejected
naive = {"slow_fetched_at": (now_utc - timedelta(minutes=10)).replace(tzinfo=None).isoformat(timespec="seconds")}
assert FD.slow_fetch_due(upcoming, naive, now_utc)[0] is False
print("3 OK: a naive timestamp is treated as UTC")
print("ALL FETCH CADENCE TESTS PASSED")
