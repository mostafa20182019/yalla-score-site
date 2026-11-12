# -*- coding: utf-8 -*-
r"""The GROUP reel (group_reel.py, 2026-11-12: Egypt v Malawi, AFCON 2027
qualifiers).

    python tests/test_group_reel.py      (from the repo root)

Guards: the table is COMPUTED from the results (Egypt 4 / Angola 4 / Malawi 3
/ South Sudan 0 after two rounds), only matches finished before the kick-off
count, another group's teams stay out, a full tie keeps alphabetical order and
shares the position, the reel stays under the 15 s rule, every frame is
1080x1920 with nothing under the Reels safe band or in the button column, and
the home team is on the RIGHT in both legs. No network, no ffmpeg.
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())

from PIL import ImageChops                   # noqa: E402

import day_reel as D                         # noqa: E402
import fb_cards as C                         # noqa: E402
import fb_reel as R                          # noqa: E402
import group_reel as G                       # noqa: E402

fails = 0


def check(cond, msg):
    global fails
    print(("  ok   " if cond else "  FAIL ") + msg)
    if not cond:
        fails += 1


C.crest_image = lambda url, size: None       # no network: flags draw as the lettered placeholder
COMP = "Africa Cup of Nations Qualification"
BADGE = {"مصر": "b/5100", "مالاوي": "b/7051", "أنجولا": "b/5105", "جنوب السودان": "b/19417"}


def mk(mid, day, t, home, away, hs=None, as_=None, rnd=1, status="FINISHED", comp=COMP):
    return {"match_id": mid, "competition": comp, "home": home, "away": away,
            "home_badge": BADGE.get(home), "away_badge": BADGE.get(away),
            "kickoff": day, "koff_time": t, "status": status, "round": rnd,
            "home_score": hs, "away_score": as_}


MS = [mk(4847456, "2026-09-25", "19:00", "مالاوي", "جنوب السودان", 2, 1),
      mk(4716604, "2026-09-25", "21:00", "مصر", "أنجولا", 0, 0),
      mk(4847473, "2026-09-29", "18:00", "جنوب السودان", "مصر", 0, 5, 2),
      mk(4847488, "2026-10-06", "22:00", "أنجولا", "مالاوي", 3, 1, 2),
      mk(4716606, "2026-11-13", "21:00", "مصر", "مالاوي", rnd=3, status="UPCOMING"),
      mk(4883938, "2026-11-14", "18:00", "أنجولا", "جنوب السودان", rnd=3, status="UPCOMING"),
      mk(4716607, "2026-11-17", "15:00", "مالاوي", "مصر", rnd=4, status="UPCOMING"),
      # another group of the same competition, and Egypt in another competition
      mk(9001, "2026-09-25", "18:00", "المغرب", "تونس", 1, 0),
      mk(9002, "2026-10-10", "20:00", "مصر", "تونس", 2, 0, comp="Friendly")]

match = G.find(MS, 4716606)
tab = G.table(MS, match)
got = [(r["pos"], r["team"], r["played"], r["won"], r["drawn"], r["lost"], r["gf"], r["ga"], r["pts"]) for r in tab]
want = [(1, "مصر", 2, 1, 1, 0, 5, 0, 4), (2, "أنجولا", 2, 1, 1, 0, 3, 1, 4),
        (3, "مالاوي", 2, 1, 0, 1, 3, 4, 3), (4, "جنوب السودان", 2, 0, 0, 2, 1, 7, 0)]
check(got == want, f"the computed table is the group after two rounds ({got})")
check(G.rounds_played(tab) == 2 and G.rounds_words(2) == "بعد جولتين", "two rounds -> «بعد جولتين»")
check({r["team"] for r in tab} == set(BADGE), "the group = the four teams; Morocco/Tunisia and the friendly stay out")
check(all(r["badge"] == BADGE[r["team"]] for r in tab), "every flag comes from the matches' own *_badge")
check(G.hook_lines(tab, match) == ("مالاوي ورانا بنقطة…", "والليلة المواجهة"), f"hook {G.hook_lines(tab, match)}")

# a result after the kick-off does not count for this match's table
late = MS + [mk(9100, "2026-11-14", "18:00", "أنجولا", "جنوب السودان", 4, 0, 3)]
check([r["pts"] for r in G.table(late, match)] == [4, 4, 3, 0], "a match after the kick-off is not in the table")
# the return leg: R3 not played in this data -> still the table after two rounds
ret = G.find(MS, 4716607)
check([r["team"] for r in G.table(MS, ret)] == [r["team"] for r in tab], "the return leg reads the same group")
check(G.hook_lines(G.table(MS, ret), ret)[1] == "والنهارده المواجهة", "a 15:00 kick-off is «النهارده», not «الليلة»")

# a full tie (points, difference, scored) keeps alphabetical order and shares the position
tie = [mk(1, "2026-09-25", "18:00", "مصر", "أنجولا", 1, 1), mk(2, "2026-09-25", "18:00", "مالاوي", "جنوب السودان", 1, 1),
       mk(3, "2026-10-01", "18:00", "مصر", "مالاوي", rnd=2, status="UPCOMING")]
tt = G.table(tie, G.find(tie, 3))
check([r["pos"] for r in tt] == [1, 1, 1, 1] and [r["team"] for r in tt] == sorted(BADGE),
      f"all level -> one shared position, alphabetical ({[(r['pos'], r['team']) for r in tt]})")

check(G.ar_time("21:00") == ("9", "مساءً") and G.ar_time("15:00") == ("3", "عصرًا"), "Cairo clock words")
check(G.gd_text(5) == "+5" and G.gd_text(-6) == "-6" and G.gd_text(0) == "0", "goal difference signs")

# the caption
cap = G.caption(tab, match)
lines = cap.splitlines()
check(lines[0] == "مالاوي ورانا بنقطة واحدة… والليلة الحسم ⚽🇪🇬", f"caption hook: {lines[0]}")
check(lines[1] == "مصر × مالاوي — تصفيات أمم أفريقيا 2027، الساعة 9 مساءً", f"caption match line: {lines[1]}")
check("https://elgoon.com" in cap and lines[-1] == "#الجون #منتخب_مصر #مصر_مالاوي #تصفيات_أمم_أفريقيا", "caption link + tags")
check("مالاوي × مصر" in G.caption(G.table(MS, ret), ret), "the return leg's caption names Malawi first")

# home on the RIGHT, in both legs: record where each flag is drawn in the match scene
for m in (match, ret):
    calls = []
    real = R.crest_at
    R.crest_at = lambda im, url, name, size, cx, cy, alpha=255, _r=real: (calls.append((name, cx, size)), _r(im, url, name, size, cx, cy, alpha))
    try:
        G.build(G.table(MS, m), m)[2][0](G.MATCH - 0.05)
    finally:
        R.crest_at = real
    big = {n: x for n, x, s in calls if s >= 200}
    check(big.get(m["home"], 0) > big.get(m["away"], 10**6) and big[m["home"]] > R.W / 2,
          f"{m['home']} (home) right of {m['away']}: {big}")

# the reel: duration, size, safe band, button column
scenes = G.build(tab, match)
secs = sum(s[1] for s in scenes)
check(secs <= 15, f"{secs:.1f} s <= 15")
check(len(scenes) == 4, "hook + table + match + outro")
bg = R.background()
for k, (draw, dur, push) in enumerate(scenes):
    for t in (dur * 0.4, dur - 0.05):
        im = draw(t)
        check(im.size == (R.W, R.H), f"scene {k} frame 1080x1920")
        pairs = (((im, bg, "raw"), (D.push_in(im, t, dur), D.push_in(bg, t, dur), "pushed")) if push
                 else ((im, D.push_in(bg, t, dur), "self-zoomed"),))
        for fr, ref, tag in pairs:
            below = ImageChops.difference(fr.crop((0, R.SAFE_BOTTOM, R.W, R.H)), ref.crop((0, R.SAFE_BOTTOM, R.W, R.H))).getbbox()
            check(below is None, f"scene {k} t={t:.1f} {tag}: nothing under the safe band ({below})")
        if push:
            col = ImageChops.difference(im.crop((int(R.W * 0.91), 0, R.W, R.H)), bg.crop((int(R.W * 0.91), 0, R.W, R.H))).getbbox()
            check(col is None, f"scene {k} t={t:.1f}: the button column on the right stays clear ({col})")
check(G.ROW_YS[-1] + G.ROW_HALF + 34 + 50 < R.SAFE_BOTTOM, "the last row and the note end above the safe band")

print("ALL OK" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
