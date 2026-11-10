# -*- coding: utf-8 -*-
r"""The SCORERS RACE reel (scorers_reel.py, 2026-11-10).

    python tests/test_scorers_reel.py      (from the repo root)

Guards: the reel stays under the 15 s rule, every frame is 1080x1920 and
nothing is drawn under the Reels safe band or in the button column on the
right (also after the push-in), equal goals give the same rank and the same
bar, a tie at the cut-off becomes ONE group row instead of an invented order,
the feed's stray spaces are stripped, the default silhouette falls back to
the club's crest, and the caption names the leader. No network, no ffmpeg.
"""
import io
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())

from PIL import Image, ImageChops            # noqa: E402

import day_reel as D                         # noqa: E402
import fb_cards as C                         # noqa: E402
import fb_reel as R                          # noqa: E402
import lineup_card as L                      # noqa: E402
import scorers_reel as S                     # noqa: E402

fails = 0


def check(cond, msg):
    global fails
    print(("  ok   " if cond else "  FAIL ") + msg)
    if not cond:
        fails += 1


C.crest_image = lambda url, size: None       # no network: crests draw as the lettered placeholder

PHOTO = "https://imagecache.365scores.com/image/upload/f_png,w_64,h_64,c_limit,q_auto:eco,dpr_2,d_Athletes:default.png/v9/Athletes/{}"


def sc(name, team, goals, aid):
    return {"name": name, "team": team, "crest": None, "photo": PHOTO.format(aid), "goals": goals, "played": 0, "value": goals}


# the feed's spaces
check(S.clean({"name": "كيليان مبابي ", "team": " ريال  مدريد", "goals": "13"})["name"] == "كيليان مبابي", "name stripped")
check(S.clean({"name": "x", "team": " ريال  مدريد", "goals": "13"})["team"] == "ريال مدريد", "club name spaces collapsed")
check(S.athlete(PHOTO.format(39820)) == (39820, 9), "athlete id + version read from the photo URL")

# ranks and ties
clean5 = [sc("أ", "ن", g, i + 1) for i, g in enumerate((15, 13, 10, 9, 8, 7))]
rows = S.rows_for(clean5)
check([r["rank"] for r in rows] == [1, 2, 3, 4, 5] and all(r["group"] is None for r in rows), "no tie: five single rows")
pl = [sc("أ", "ن", g, i + 1) for i, g in enumerate((9, 7, 6, 6, 5, 5, 5, 5, 5, 4))]
rows = S.rows_for(pl)
check([r["rank"] for r in rows] == [1, 2, 3, 3, 5], f"equal goals share a rank ({[r['rank'] for r in rows]})")
check(S.bar_px(rows[2]["goals"], 9) == S.bar_px(rows[3]["goals"], 9), "equal goals -> equal bar length")
check(all(S.value_at(6, 9, t) == S.value_at(6, 9, t) for t in (1.0, 2.0, 4.0)), "equal goals -> equal counter at any time")
check(rows[4]["group"] is not None and len(rows[4]["group"]) == 5 and not rows[4]["more"],
      "five tied at the cut-off with one row left -> one group row, nobody picked")
eg = [sc("أ", "ن", g, i + 1) for i, g in enumerate((8, 4, 4, 4, 3, 3, 3, 3, 3, 3))]
rows = S.rows_for(eg)
check(len(rows) == 5 and rows[4]["group"] and rows[4]["more"], "a group that reaches the end of the feed is marked 'more'")
fit = [sc("أ", "ن", g, i + 1) for i, g in enumerate((9, 8, 7, 6, 6, 4))]
rows = S.rows_for(fit)
check(len(rows) == 5 and all(r["group"] is None for r in rows), "a tie that fits stays player by player")
check(S.value_at(9, 9, S.GROW_T0 + S.GROW + 0.01) == 9 and S.value_at(4, 9, 0) == 0, "bars grow 0 -> total")
check(S.finish_t(4, 9) < S.finish_t(9, 9), "the leader finishes last")

# default silhouette -> the club's crest
DEFAULT = b"default-silhouette"
buf = io.BytesIO()
Image.new("RGB", (240, 240), (200, 30, 30)).save(buf, "PNG")
REAL = buf.getvalue()
L._HS.clear()
L.fetch_bytes = lambda url, timeout=10: DEFAULT if "/Athletes/0" in url or "/Athletes/2" in url else REAL
shots = S.shots_for([sc("أ", "ن", 9, 1), sc("ب", "ن", 7, 2)])
check(1 in shots and 2 not in shots, "the default silhouette is dropped")
S._disc.clear()
check(S.disc(sc("أ", "ن", 9, 1), shots, 124)[1] == "photo", "a real photo stays the photo")
check(S.disc(sc("ب", "ن", 7, 2), shots, 124)[1] == "crest", "no real photo -> the club's crest")

# the reel: duration, size, safe band
scenes = S.build(pl, "Premier League", "الدوري الإنجليزي", 10, shots={})
secs = sum(s[1] for s in scenes)
check(secs <= 15, f"{secs:.1f} s <= 15")
check(len(scenes) == 3, "intro + race + outro")
bg = R.background()
for k, (draw, dur, push) in enumerate(scenes):
    for t in (dur * 0.4, dur - 0.05):
        im = draw(t)
        check(im.size == (R.W, R.H), f"scene {k} frame 1080x1920")
        # the outro (moment_reel's cta scene) zooms itself: its reference is the zoomed canvas
        pairs = (((im, bg, "raw"), (D.push_in(im, t, dur), D.push_in(bg, t, dur), "pushed")) if push
                 else ((im, D.push_in(bg, t, dur), "self-zoomed"),))
        for fr, ref, tag in pairs:
            below = ImageChops.difference(fr.crop((0, R.SAFE_BOTTOM, R.W, R.H)), ref.crop((0, R.SAFE_BOTTOM, R.W, R.H))).getbbox()
            check(below is None, f"scene {k} t={t:.1f} {tag}: nothing under the safe band ({below})")
        if k == 1:
            col = ImageChops.difference(im.crop((int(R.W * 0.91), 0, R.W, R.H)), bg.crop((int(R.W * 0.91), 0, R.W, R.H))).getbbox()
            check(col is None, f"race t={t:.1f}: the button column on the right stays clear ({col})")
check(S.ROW_TOP + (S.ROWS - 1) * S.ROW_H + S.ROW_HALF < R.SAFE_BOTTOM, "last row ends above the safe band")

# the caption
cap = S.caption(pl, "Premier League", "الدوري الإنجليزي", 10)
first = cap.splitlines()[0]
check("يتصدر" in first and "9 أهداف" in first and "بعد الجولة 10" in first, "caption hook: the leader and his goals")
check("https://elgoon.com" in cap and "#الجون" in cap and "4. " not in cap, "caption: link, #الجون, ranks 1-3 only")
check(S.goals_word(15) == "15 هدفًا" and S.goals_word(2) == "هدفين", "Arabic count agreement")
print("ALL OK" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
