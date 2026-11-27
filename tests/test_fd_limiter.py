# -*- coding: utf-8 -*-
"""The football-data rate limiter (2026-11-27): wait only when the minute is
really full, and remember that a season has started.

    python tests/test_fd_limiter.py     (from the repo root)

The standings fetch used to wait 60 s before its first call and 7 s before
every other one, whatever had happened before: 146 s of a 366 s fetch.
"""
import io, os, sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())
import fetch_data as F

fails = 0
def ck(msg, cond, extra=""):
    global fails
    print(("  ok   " if cond else "  FAIL ") + msg + (f"  [{extra}]" if extra and not cond else ""))
    fails += not cond

slept = []
def run(times):
    """Ask the limiter at each of `times` (seconds); a wait moves the clock."""
    F._FD_CALLS[:] = []
    slept[:] = []
    shift = 0.0
    for t in times:
        w = F.fd_wait(now=t + shift, sleep=slept.append)
        shift += w
    return [round(x, 1) for x in slept if x > 0]

ck("1 nine calls a minute, one under the feed's ten", F.FD_PER_MIN == 9)
ck("2 nine calls in a row: no wait at all", run([0, 1, 2, 3, 4, 5, 6, 7, 8]) == [])
w = run([0, 1, 2, 3, 4, 5, 6, 7, 8, 9])
ck("3 the tenth waits until the first has left the minute - not a fixed 60 s", w == [51.5], str(w))
ck("4 calls a minute apart never wait (what the standings fetch meets after the 365scores leagues)",
   run([0, 5, 10, 15, 20, 25, 30, 35, 150, 151, 152, 153, 154, 155]) == [])
w = run(list(range(20)))
ck("5 twenty calls in a burst: never more than nine inside any minute",
   all(sum(1 for c in F._FD_CALLS if 0 <= x - c < 60) <= F.FD_PER_MIN for x in F._FD_CALLS) and len(w) >= 2, str(w))
src = io.open("fetch_data.py", encoding="utf-8").read()
ck("6 no fixed wait is left in the football-data path", "time.sleep(60)" not in src and "time.sleep(7)" not in src)
ck("7 every football-data request asks the limiter first",
   src.count("fd_wait()") >= 4 and src.index("fd_wait()\n            j = json.loads(http_get(url, hdr))".replace("\n", "\r\n" if "\r\n" in src else "\n")) > 0)
ck("8 the «has the season's main stage begun» answer is kept between runs and not asked twice",
   "_FD_STARTED.get(comp) == start[:10]" in src and "_FD_STARTED[comp] = start[:10]" in src
   and '_DBG["fd_main_stage_started"] = dict(_FD_STARTED)' in src and '_PREV_DBG.get("fd_main_stage_started")' in src)
ck("9 each phase of the fetch is timed into fetch_debug.json", '_DBG["timing"] = _TIMING' in src and src.count("_phase(") >= 9)
print("ALL OK" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
