# -*- coding: utf-8 -*-
r"""The day's RESULTS reel (day_reel.py, 2026-11-09).

    python tests/test_day_reel.py      (from the repo root)

What it guards: «أمس» / «اليوم» from the Cairo clock, SIX results a shot
(user 2026-11-19: «النتائج ممكن اكتر من لقطة بس اللقطة الواحدة فيها ست
مباريات») between the intro and the outro, every frame 1080x1920, the rows
inside the Reels safe band and clear of the right-hand button column, the
home goals drawn on the RIGHT of the dash, and a caption naming every
result. No ffmpeg needed: frames only.
"""
import datetime
import os
import sys
from zoneinfo import ZoneInfo

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())

import day_reel as D        # noqa: E402
import fb_reel as R         # noqa: E402

fails = 0


def check(cond, msg):
    global fails
    print(("  ok   " if cond else "  FAIL ") + msg)
    if not cond:
        fails += 1


now = datetime.datetime(2026, 11, 9, 0, 16, tzinfo=ZoneInfo("Africa/Cairo"))
check(D.rel_label("2026-11-08", now) == "نتائج أمس", "the night after: «نتائج أمس»")
check(D.rel_label("2026-11-09", now) == "نتائج اليوم", "same day: «نتائج اليوم»")
check(D.rel_label("2026-11-05", now).startswith("نتائج الخميس"), "older day: by name")


def match(i, hs, as_):
    return {"match_id": i, "home": "Liverpool FC", "away": "Chelsea FC", "home_score": hs, "away_score": as_,
            "competition": "Premier League", "home_badge": None, "away_badge": None}


ms = [match(i, 8, 1) for i in range(7)]   # 8 = lots of ink, 1 = little
scenes = D.build(ms, "2026-11-08", now)
check(len(scenes) == 3, f"7 matches -> intro + ONE shot of six + outro ({len(scenes)})")
for _n, _want in ((3, [3]), (6, [6]), (9, [6]), (11, [6]), (12, [6, 6]), (20, [6, 6])):
    _ms = [match(i, 2, 1) for i in range(_n)]
    _sc = D.build(_ms, "2026-11-08", now)
    _got = [len(p) for p in D.shots(_ms)]
    check(_got == _want and len(_sc) == 2 + len(_want) and sum(s[1] for s in _sc) <= 15,
          f"{_n} matches: shots of {_got} - six a shot, full shots only - {sum(s[1] for s in _sc):.1f} s")
_h6, _ys6 = D.row_geometry(D.PER_SHOT)
check(_ys6[0] - _h6 / 2 >= D.BAND_TOP - 1 and _ys6[-1] + _h6 / 2 <= R.SAFE_BOTTOM, "six rows fill the safe band, no more")
check(scenes[-1][2] is False, "the outro is not pushed in twice")
secs = sum(s[1] for s in scenes)
check(12 <= secs <= 15, f"length {secs:.1f} s (15 s or less, user rule 2026-11-10)")

_h7, _ys7 = D.row_geometry(6)
last_row_bottom = _ys7[-1] + _h7 / 2
check(last_row_bottom <= R.SAFE_BOTTOM, f"rows end at {last_row_bottom:.0f} <= safe band {R.SAFE_BOTTOM}")
check(D.HOME_X + 52 < R.W * 0.91, "home crest clear of the like/comment column")

for draw, dur, _ in scenes:
    im = draw(dur - 0.05)
    check(im.size == (R.W, R.H), f"frame {im.size}")

# home goals on the RIGHT: an 8-1 row has more ink right of centre in the score band
im = scenes[1][0](scenes[1][1] - 0.05).convert("L")
cy = int(_ys7[0])
def ink(x0, x1):
    return sum(1 for x in range(int(x0), int(x1), 2) for y in range(cy - 50, cy + 25, 2) if im.getpixel((x, y)) > 245)
right, left = ink(R.W / 2 + 20, R.W / 2 + 90), ink(R.W / 2 - 90, R.W / 2 - 20)
check(right > left, f"the «8» (home) is right of the dash, the «1» left (ink {right} vs {left})")

# designer review 2026-11-19: on a day that is neither today nor yesterday the
# title already carries the date - it must not be said a second time
_src = open("day_reel.py", encoding="utf-8").read()
check(D.rel_label("2026-11-05", now) == "نتائج " + D.day_name("2026-11-05")
      and 'title if when in title else f"{title} · {when}"' in _src
      and "[_n] if when in title else [when, _n]" in _src,
      "an older day says its date once: in the title, not again beside it or under it")
cap = D.caption(ms[:3], "2026-11-08", now)
check(cap.count("8 - 1") == 3 and "https://elgoon.com/" + chr(10) in cap and "elgoon.com/matches" not in cap and "#الجون" in cap, "caption: every result, the link, the tag")

print("ALL OK" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
