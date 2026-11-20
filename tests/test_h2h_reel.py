# -*- coding: utf-8 -*-
r"""The head-to-head reel, rewritten (h2h_reel.py, 2026-11-20).

    python tests/test_h2h_reel.py      (from the repo root)

Frames only, no ffmpeg. What it guards: the reel is built from the SAME rows
the /h2h page shows, it is 15 s or less, every frame is 1080x1920, the
caption says «آخر N» and never an all-time record, and --auto posts only on
the day a pair meets.
"""
import io
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())

import fb_reel as R            # noqa: E402
import h2h_reel as HR          # noqa: E402
from site_lib import h2h as H  # noqa: E402

fails = 0


def ck(msg, cond, extra=""):
    global fails
    print(("  ok   " if cond else "  FAIL ") + msg + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails += 1


pair = next(p for p in H.PAIRS if p["slug"] == "al-ahly-zamalek")
ctx = HR.context(pair, {}, "2026-11-20")
ck("1 the first pair has enough saved meetings for a reel", ctx is not None and ctx["n"] >= HR.MIN_MEETINGS)
if ctx:
    games = H.meetings(pair, H.load_history(pair), {})
    t = H.tally(games, pair, H.notes_for(pair, H.load_history(pair)))
    ck("2 the numbers are the /h2h page's own: the same meetings, the same tally",
       ctx["n"] == len(games) and ctx["wins"] == t["wins"] and ctx["draws"] == t["draws"] and ctx["goals"] == t["goals"]
       and sum(ctx["wins"].values()) + ctx["draws"] == ctx["n"])
    ck("3 the last five, newest first", len(ctx["games"]) == min(HR.LAST_N, ctx["n"])
       and [g["date"] for g in ctx["games"]] == sorted((g["date"] for g in ctx["games"]), reverse=True))
    scenes = HR.build(ctx)
    secs = sum(s[1] for s in scenes)
    ck("4 four scenes, 15 s or less (user rule)", len(scenes) == 4 and secs <= 15, str(secs))
    frames = [draw(dur - 0.05) for draw, dur, _ in scenes]
    ck("5 every frame is 1080x1920", all(f.size == (R.W, R.H) for f in frames))
    cap = HR.caption(ctx)
    ck("6 the caption: «آخر N», the tally, the pair's page, #الجون - and never an all-time claim",
       f"آخر {HR._meetings(ctx['n'])}" in cap and f"https://elgoon.com/h2h/{pair['slug']}" in cap and "#الجون" in cap
       and "تاريخ المواجهات" not in cap and "عبر التاريخ" not in cap, cap)
    ck("7 no prediction wording (predictions are switched off)", "التوقع" not in cap and "توقع" not in cap)

few = {"slug": "x-y", "a": "فريق لا وجود له", "b": "فريق آخر لا وجود له"}
ck("8 fewer than four meetings on record: no reel", HR.context(few, {}, "2026-11-20") is None)

up = {"1": {"match_id": 1, "home": pair["a"], "away": pair["b"], "kickoff": "2026-11-20", "koff_time": "20:00", "status": "UPCOMING"},
      "2": {"match_id": 2, "home": "طرابزون سبور", "away": "فنربخشة", "kickoff": "2026-11-25", "status": "UPCOMING"}}
ck("9 --auto: the pair that meets TODAY, no other day and no other pair",
   [p["slug"] for p, _ in HR.meeting_today(up, "2026-11-20")] == [pair["slug"]] and HR.meeting_today(up, "2026-11-21") == []
   and HR.meeting_today({}, "2026-11-20") == [])
src = io.open("h2h_reel.py", encoding="utf-8").read()
wf = io.open(".github/workflows/fb-post.yml", encoding="utf-8").read()
ck("10 on the current reel code (moment_reel / day_reel), posted once per pair and day, from the morning run",
   "R.FPS" not in src and "R.lerp" not in src and 'f"h2h:{ctx[\'pair\'][\'slug\']}:{date}"' in src
   and "python h2h_reel.py --auto --publish" in wf)

print("ALL OK" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
