# -*- coding: utf-8 -*-
"""The night's cap on match reels (2026-11-27): four went out in 37 minutes
on 25 November. A match of ours always gets its reel and goes first; the
others only while fewer than NIGHT_CAP match reels are out in NIGHT_H hours.

    python tests/test_reel_night.py     (from the repo root)
"""
import os, sys, time
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())
import fb_reel as R
import store

fails = 0
def ck(msg, cond, extra=""):
    global fails
    print(("  ok   " if cond else "  FAIL ") + msg + (f"  [{extra}]" if extra and not cond else ""))
    fails += not cond

def m(i, h, a, comp):
    return ({"match_id": i, "home": h, "away": a, "competition": comp}, {})

ZAM = m(1, "الزمالك", "النادي الأفريقي", "CAF Champions League")
LIV = m(2, "Liverpool FC", "Everton FC", "Premier League")
RMA = m(3, "Real Madrid", "Getafe CF", "Primera Division")
SAU = m(4, "الأهلي", "النصر", "Saudi Pro League")
ids = lambda todo: [t[0]["match_id"] for t in todo]       # noqa: E731
ck("1 the numbers shipped: two in twelve hours", (R.NIGHT_CAP, R.NIGHT_H) == (2, 12))
ck("2 a match of ours is home; a curated European club and the Saudi «الأهلي» are not",
   R.is_home(ZAM[0]) and not R.is_home(LIV[0]) and not R.is_home(SAU[0]))
ck("3 with room, every match - ours first, whatever the order they came in", ids(R.due([LIV, RMA, ZAM], 0)) == [1, 2, 3])
ck("4 the cap reached: only the match of ours", ids(R.due([LIV, RMA, ZAM], 2)) == [1] and R.due([LIV, RMA], 2) == [])
ck("5 one more still fits under the cap", ids(R.due([LIV, RMA], 1)) == [2, 3])
ck("6 a store that cannot say: nothing capped goes out, ours still does", ids(R.due([LIV, ZAM], None)) == [1])
real = store.posted_since
try:
    now = time.time()
    store.posted_since = lambda kind, since: [{"ref_id": "4741995", "posted_at": now}, {"ref_id": "scorers:PL:12", "posted_at": now},
                                              {"ref_id": "file:x", "posted_at": now}, {"ref_id": "today:2026-11-27", "posted_at": now}]
    ck("7 only match reels count - not the slot reels, the morning reel or a file reel", R.night_count() == 1, str(R.night_count()))
    def boom(kind, since):
        raise RuntimeError("D1 down")
    store.posted_since = boom
    ck("8 an unreadable store is None, not zero", R.night_count() is None)
finally:
    store.posted_since = real
src = open("fb_reel.py", encoding="utf-8").read()
ck("9 the run and the workflow's question both ask it", src.count("night_count())") == 2)
print("ALL OK" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
