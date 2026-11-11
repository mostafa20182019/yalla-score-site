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

# ---- automation (2026-11-10, «أتمتها»): one reel per league per finished round
import datetime                                          # noqa: E402
NOW = datetime.datetime(2026, 11, 10, 0, 16, tzinfo=C.CAIRO)


def mk(mid, rnd, status, day, t="18:00", comp="Premier League"):
    return {"match_id": 1000 + mid, "competition": comp, "round": rnd, "status": status,
            "kickoff": day, "koff_time": t}


done10 = [mk(i, 10, "FINISHED", "2026-11-08") for i in range(9)] + [mk(9, 10, "POSTPONED", "2026-11-09")]
check(S.round_done(done10, NOW) == (10, datetime.datetime(2026, 11, 8, 18, 0, tzinfo=C.CAIRO)),
      "a round with every match finished or postponed is done")
half = done10[:-1] + [mk(9, 10, "IN_PLAY", "2026-11-09")]
check(S.round_done(half, NOW) is None, "a match still playing: not done")
started = done10 + [mk(20, 11, "FINISHED", "2026-11-09")] + [mk(21 + i, 11, "UPCOMING", "2026-11-12") for i in range(9)]
check(S.round_done(started, NOW, 10) is None, "the next round has a finished match: R10 is old news, R11 not done")
partial = [mk(40 + i, 9, "FINISHED", "2026-11-08", comp="Egyptian Premier League") for i in range(6)]
check(S.round_done(partial, NOW, 10) is None, "six listed matches of a ten-match round are not a finished round")
check(S.round_done(partial, NOW) is not None, "(without the size the same six would pass - the guard is what stops it)")
late = done10 + [mk(30, 4, "FINISHED", "2026-11-09")]
check(S.round_done(late, NOW)[0] == 10, "a postponed R4 match played late does not bring R4 back")
stale = [mk(i, 8, "FINISHED", "2026-10-31") for i in range(10)]
check(S.round_done(stale, NOW) is None, "a round that ended 9 days ago is not news")
check(S.round_done([], NOW) is None, "no matches: nothing due")

matches = (done10 + [mk(100 + i, 12, "FINISHED", "2026-11-08", "22:00", "Primera Division") for i in range(10)]
           + [mk(200 + i, 8, "FINISHED", "2026-10-31", comp="Egyptian Premier League") for i in range(9)])
_rf, _rs = S.round_for, S.round_size
S.round_size = lambda comp, path=None: 10
S.round_for = lambda comp, path=None: {"Premier League": 10, "Primera Division": 12, "Egyptian Premier League": 8}[comp]
d = S.due(NOW, matches, posted=lambda ref: False)
check([(c, r) for c, r, _ in d] == [("Premier League", 10), ("Primera Division", 12)],
      f"due: the oldest round first, the stale Egyptian round out: {d}")
check(d[0][2] == "scorers:Premier League:2026-27:R10", f"the store ref names league, season and round: {d[0][2]}")
d2 = S.due(NOW, matches, posted=lambda ref: ref.endswith("Premier League:2026-27:R10"))
check([c for c, _, _ in d2] == ["Primera Division"], "an already posted reel is not owed again")
S.round_for = lambda comp, path=None: 11 if comp == "Primera Division" else 10
d3 = S.due(NOW, matches, posted=lambda ref: False)
check([c for c, _, _ in d3] == ["Premier League"], "the table behind the matches (scorers lag): wait a night")
S.round_for, S.round_size = _rf, _rs
check(S.round_size("Premier League") == 10, "a 20-club table means ten matches a round")
check(S.MAX_PER_RUN == 1, "one scorers reel a night")

print("ALL OK" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
