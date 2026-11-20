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
      and '[_n] if when in title else [f"{when} · {_n}"]' in _src,
      "an older day says its date once: in the title, not again beside it or under it")

# designer review 2026-11-19 (second list): the opening shot is the night's
# result, one row carries the logo's board, the head logo is small.
def _m(i, h, a, hs, as_, comp="Premier League"):
    return {"match_id": i, "home": h, "away": a, "home_score": hs, "away_score": as_, "competition": comp,
            "home_badge": None, "away_badge": None}


_night = [_m(1, "Everton FC", "Fulham FC", 5, 0), _m(2, "Liverpool FC", "Brentford FC", 1, 0),
          _m(3, "Arsenal FC", "Chelsea FC", 1, 1)]
check(D.hero_of(_night)["match_id"] == 3, "the night's result: two curated sides beat one, and beat a 5-0 between others")
check(D.hero_of(_night[:2])["match_id"] == 2, "...one curated side beats the widest margin")
check(D.hero_of([_m(1, "Everton FC", "Fulham FC", 5, 0), _m(2, "Fulham FC", "Brentford FC", 1, 0)])["match_id"] == 1
      and D.hero_of([]) is None, "...with no curated side: the widest margin; no results, no hero")
_q = "Africa Cup of Nations Qualification"
check(D.hero_of([_m(1, "توجو", "الجزائر", 0, 3, _q), _m(2, "مالاوي", "مصر", 0, 0, _q)])["match_id"] == 2,
      "...Egypt's match before another Arab nation's, whatever the score")
check(D.BAND_TOP < 420 and D.HEAD_LOGO_Y - D.HEAD_LOGO_H / 2 >= 195 and D.ROW_MAX_H >= 180,
      "the small head logo starts at the top safe line and the rows get the room")
_h6, _ = D.row_geometry(6)
_long = [_m(i, "Wolverhampton Wanderers FC", "Chelsea FC", 1, 0) for i in range(2)]
check(22 <= D.shot_name_size(_long, _h6) <= D.shot_name_size(_night, _h6) <= 42,
      "one name size for a whole shot: the longest name sets it")
check("hero=m is hero" in _src and "mark(h * 0.3) if hero" in _src and "max(26," in _src,
      "the hero row carries the board instead of the dash; the league label is never under 26 px")
cap = D.caption(ms[:3], "2026-11-08", now)
check(cap.count("8 - 1") == 3 and "https://elgoon.com/" + chr(10) in cap and "elgoon.com/matches" not in cap and "#الجون" in cap, "caption: every result, the link, the tag")

# ---------------------------------------------------------------- the MORNING reel (2026-11-20)
def _f(i, h, a, t, comp="Premier League"):
    return {"match_id": i, "home": h, "away": a, "home_score": None, "away_score": None, "status": "UPCOMING",
            "koff_time": t, "kickoff": "2026-11-22", "competition": comp, "home_badge": None, "away_badge": None}


_day = [_f(1, "Everton FC", "Fulham FC", "14:00"), _f(2, "Brentford FC", "Burnley FC", "16:00"),
        _f(3, "Liverpool FC", "Manchester United FC", "18:30"), _f(4, "Leeds United FC", "Sunderland AFC", "20:00")]
_now2 = datetime.datetime(2026, 11, 22, 9, 1, tzinfo=ZoneInfo("Africa/Cairo"))
check(D.today_label("2026-11-22", _now2) == "مباريات اليوم" and D.today_label("2026-11-23", _now2) == "مباريات الغد"
      and D.today_label("2026-11-25", _now2).startswith("مباريات الأربعاء"), "the morning reel: «مباريات اليوم» from the Cairo clock")
_sc = D.build(_day, "2026-11-22", _now2, fixtures=True)
check(len(_sc) == 3 and abs(sum(s[1] for s in _sc) - (D.INTRO + D.PAGE + D.OUTRO)) < 1e-9 and sum(s[1] for s in _sc) <= 15,
      "four fixtures: the day's match, one shot, the outro - inside 15 s")
_fr = [draw(dur - 0.05) for draw, dur, _ in _sc]
check(all(f.size == (R.W, R.H) for f in _fr), "every frame of the morning reel is 1080x1920")
_twelve = [_f(i, f"Team {i} FC", f"Side {i} FC", f"{10 + i}:00") for i in range(12)]
check(len(D.build(_twelve, "2026-11-22", _now2, fixtures=True)) == 4, "twelve fixtures: two shots of six")
check(D.under_line(dict(_day[2], channel="beIN Sports 1"), True).endswith("· beIN Sports 1")
      and "·" not in D.under_line(dict(_day[2], competition="No Such League"), True)
      and "beIN" not in D.under_line(dict(_day[2], channel="beIN Sports 1"), False),
      "the channel stands beside the league under a kick-off - only a channel we hold, never under a result")
check(D.team_name({"home": "الأهلي", "competition": "Saudi Pro League"}, "home") == "الأهلي السعودي"
      and D.team_name({"home": "الأهلي", "competition": "Egyptian Premier League"}, "home") == "الأهلي",
      "the Saudi «الأهلي» is written «الأهلي السعودي» on a reel; the bare name is the Egyptian club")
import fb_post as _P        # noqa: E402
_pool = [dict(_f(i, f"Team {i} FC", f"Side {i} FC", f"{10 + i % 9}:00"), kickoff="2026-11-22") for i in range(9)]
_orig = _P.todaycard_matches
_P.todaycard_matches = lambda matches, date, limit=None: sorted(matches[:limit or 9], key=lambda m: m["koff_time"])
try:
    check(len(D.today_matches(_pool, "2026-11-22")) == 6 and len(D.today_matches(_pool[:4], "2026-11-22")) == 4
          and len(D.today_matches(_pool + _pool[:3], "2026-11-22")) == 12,
          "nine fixtures show their six most important (full shots only), four show four, twelve show twelve")
finally:
    _P.todaycard_matches = _orig
_wf = open(".github/workflows/fb-post.yml", encoding="utf-8").read()
check("python day_reel.py --today --publish" in _wf and _wf.index("--daycard today") < _wf.index("day_reel.py --today --publish"),
      "the morning run posts the card, then the reel")
check('f"today:{date}"' in _src or "today:{date}" in open("day_reel.py", encoding="utf-8").read(),
      "the morning reel has its own store key (today:<date>): once a day, apart from the night's")

print("ALL OK" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
