# -*- coding: utf-8 -*-
r"""The league TABLE reel (table_reel.py, 2026-11-09).

    python tests/test_table_reel.py      (from the repo root)

Guards: the zones (top four blue, bottom three red in La Liga), one page per
five clubs between intro and outro, every frame 1080x1920, the last row inside
the Reels safe band, and a caption with the top five. Frames only, no ffmpeg.
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())

import fb_reel as R         # noqa: E402
import table_reel as T      # noqa: E402

fails = 0


def check(cond, msg):
    global fails
    print(("  ok   " if cond else "  FAIL ") + msg)
    if not cond:
        fails += 1


comp = "Primera Division"
check(T.zone(4, 20, comp) == T.UCL and T.zone(5, 20, comp) is None, "La Liga: 4th blue, 5th plain")
check(T.zone(18, 20, comp) == T.DROP and T.zone(17, 20, comp) is None, "La Liga: 18th red, 17th plain")
table = [{"pos": i + 1, "team": "FC Barcelona", "crest": None, "played": 12, "pts": 40 - i} for i in range(20)]
scenes = T.build(table, comp, "الدوري الإسباني")
check(len(scenes) == 2 + 2, f"20 clubs -> intro + the top ten on 2 pages + outro ({len(scenes)})")
check(sum(s[1] for s in scenes) <= 15, "15 s or less (user rule 2026-11-10)")
for draw, dur, _ in scenes:
    check(draw(dur - 0.05).size == (R.W, R.H), "frame 1080x1920")
bottom = T.ROW_TOP + (T.PER_PAGE - 1) * T.ROW_H + T.ROW_HALF
check(bottom < R.SAFE_BOTTOM, f"last row ends at {bottom} < {R.SAFE_BOTTOM}")
cap = T.caption(table, "الدوري الإسباني", comp)
check("بعد الجولة 12" in cap and "1. " in cap and "5. " in cap and "6. " not in cap, "caption: round + top five only")
print("ALL OK" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
