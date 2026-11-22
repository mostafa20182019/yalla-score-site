# -*- coding: utf-8 -*-
r"""The match-day poster and the title-race reel (2026-11-20).

    python tests/test_poster_race.py      (from the repo root)

The poster's rule is colour: each half is filled ONLY from its own club's
kit, and two close colours are never left side by side. The reel's rule is
numbers: points only, and no chart unless our count of every drawn club's
matches and points equals the table's own.
"""
import datetime
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())

import match_poster as MP          # noqa: E402
import matchup_card as MC          # noqa: E402
import race_reel as RR             # noqa: E402

fails = 0


def ck(msg, cond, extra=""):
    global fails
    print(("  ok   " if cond else "  FAIL ") + msg + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails += 1


print("1. the poster's colours")
for h, a in (("الأهلي", "بيراميدز"), ("الأهلي", "الزمالك"), ("ليفربول", "مانشستر يونايتد"), ("ريال مدريد", "برشلونة"),
             ("الأهلي", "ليفربول"), ("الزمالك", "ريال مدريد")):
    hf, af = MP.fills(h, a)
    ho, ao = MP.own_colours(MC.kit_for(h)), MP.own_colours(MC.kit_for(a))
    ck(f"{h} × {a}: each half is one of its OWN club's colours (or the neutral slate)",
       (hf in ho or hf == MP.NEUTRAL_FILL) and (af in ao or af == MP.NEUTRAL_FILL), f"{hf} {af}")
hf, af = MP.fills("الأهلي", "ليفربول")
ck("two reds are never left side by side when the away side has another colour of its own",
   MP._dist(hf, af) >= 110, f"{hf} {af}")
hf, af = MP.fills("نادي غير معروف", "نادٍ آخر")
ck("a club with no colours on record gets the neutral slate - never an invented colour",
   hf == MP.NEUTRAL_FILL or hf in MP.own_colours(MC.NEUTRAL))
ck("a white club takes a colour of its own that is not light (white text on white is not a poster)",
   not MP._light(MP.fills("ريال مدريد", "الأهلي")[0]) or MP.fills("ريال مدريد", "الأهلي")[0] == MP.NEUTRAL_FILL)

FEED = {"home": ("#FFFF00", "#CAC9CE"), "away": ("#282E60", "#0A0A0A")}
hf, af = MP.fills("نادي غير معروف", "نادٍ آخر", None, FEED)
ck("a club our table lacks takes its REAL colours from the feed (user, 2026-11-22), not the grey slate",
   hf == (255, 255, 0) and af == (40, 46, 96), f"{hf} {af}")
ck("our KITS table still wins over the feed for a club it has",
   MP.fills("الأهلي", "نادٍ آخر", None, FEED)[0] == MP.fills("الأهلي", "نادٍ آخر")[0])
src = open("match_poster.py", encoding="utf-8").read()
ck("the run (main) fetches the feed colours and hands them to render and publish",
   "FC._feed_colors(m)" in src and "render(m, args.out, feed)" in src and "publish(m, date, feed)" in src
   and "render(m, feed=feed)" in src)
_ys = MP.render({"match_id": 7, "home": "نادي غير معروف", "away": "نادٍ آخر", "competition": "X",
                 "kickoff": "2026-11-23", "koff_time": "15:00"}, feed=FEED)
from io import BytesIO                                  # noqa: E402
from PIL import Image                                   # noqa: E402
_im = Image.open(BytesIO(_ys)).convert("RGB")
_dark = sum(1 for x in range(MP.W // 2 + 60, MP.W - 60, 3) for y in range(780, 880, 3)
            if sum(_im.getpixel((x, y))) < 200)
ck("a name on a yellow half is written dark (white on yellow does not read)", _dark > 60, str(_dark))

print("2. which match, and the text")
M = lambda i, h, a, comp, st="UPCOMING", t="20:00": {"match_id": i, "home": h, "away": a, "competition": comp,   # noqa: E731
                                                     "kickoff": "2026-11-23", "koff_time": t, "status": st}
ms = [M(1, "سموحة", "زد", "Egyptian Premier League"), M(2, "الأهلي", "بيراميدز", "Egyptian Premier League"),
      M(3, "الزمالك", "المصري", "Egyptian Premier League", st="FINISHED")]
ck("the day's match of ours still to be played; a match of nobody we follow gives no poster",
   (MP.pick(ms, "2026-11-23") or {}).get("match_id") == 2 and MP.pick(ms[:1], "2026-11-23") is None
   and MP.pick(ms, "2026-11-24") is None)
cap = MP.caption(ms[1])
ck("the caption: the two names, the league, the day, the kick-off in Cairo time, the match page",
   cap.startswith("🔥 الأهلي × بيراميدز") and "الدوري المصري" in cap and "20:00 بتوقيت القاهرة" in cap
   and "https://elgoon.com/m/2" in cap, cap)
ck("no betting word in it", not any(w in cap for w in ("توقع", "راهن", "اربح")))
ck("the Saudi «الأهلي» is written «الأهلي السعودي»",
   "الأهلي السعودي" in MP.caption(M(9, "الأهلي", "النصر", "Saudi Pro League")))
img = MP.render(ms[1])
ck("it renders a 1080x1350 JPEG", img[:2] == b"\xff\xd8" and len(img) > 20000)
os.environ.pop("FB_POSTER", None)
ck("behind its own switch: off unless FB_POSTER is on", MP.armed() is False)

print("3. the race: points only, and only when our counts are the table's")


def g(i, day, h, a, hs, as_):
    return {"match_id": i, "competition": "L", "kickoff": f"2026-09-{day:02d}", "home": h, "away": a,
            "home_score": hs, "away_score": as_, "status": "FINISHED"}


pool, n = [], 0
for rnd in range(1, 7):                       # six rounds: A beats B, C draws D
    n += 1; pool.append(g(n, rnd, "A", "B", 1, 0))
    n += 1; pool.append(g(n, rnd, "C", "D", 1, 1))
table = [{"pos": 1, "team": "A", "played": 6, "pts": 18}, {"pos": 2, "team": "C", "played": 6, "pts": 6},
         {"pos": 3, "team": "D", "played": 6, "pts": 6}, {"pos": 4, "team": "B", "played": 6, "pts": 0}]
today = datetime.date(2026, 11, 20)
rows = RR.series("L", pool, table, 4, today)
ck("each side's points after its own 1st, 2nd, ... match",
   rows and rows[0]["points"] == [3, 6, 9, 12, 15, 18] and rows[1]["points"] == [1, 2, 3, 4, 5, 6]
   and rows[3]["points"] == [0] * 6, str(rows and [r["points"] for r in rows]))
bad = [dict(r) for r in table]
bad[0]["pts"] = 17
ck("a table that says other points than our matches give -> no chart",
   RR.series("L", pool, bad, 4, today) is None)
ck("a match of ours the table has not counted -> no chart",
   RR.series("L", pool + [g(99, 7, "A", "D", 2, 0)], table, 4, today) is None)
ck("too few matches is not a race yet", RR.series("L", pool[:6], [dict(r, played=3, pts=p) for r, p in zip(table, (9, 3, 3, 0))], 4, today) is None)
ck("last season's matches of the same league are not counted",
   RR.series("L", pool + [dict(g(500, 1, "A", "B", 5, 0), kickoff="2026-03-01")], table, 4, today) is not None)
sc = RR.build("L", rows, 6)
secs = sum(s[1] for s in sc)
ck(f"the reel is {secs:.1f} s (15 s or less)", secs <= 15 and sc[-1][2] is False)
f0, f1 = sc[0][0](0.0), sc[0][0](RR.PAGE - 0.05)
box = (60, RR.LEG_TOP, 1020, RR.LEG_TOP + 250)
ck("the first frame is whole: the clubs and their points stand at 0 s as at the end",
   f0.size == (RR.W, RR.H) and list(f0.crop(box).convert("RGB").getdata()) == list(f1.crop(box).convert("RGB").getdata()))
cap = RR.caption("Egyptian Premier League", [dict(r, team=t) for r, t in zip(rows, ("بيراميدز", "الأهلي", "الزمالك", "سموحة"))], 6)
ck("the caption gives each club's points and matches, a question, the table's page - no «توقع»",
   "بيراميدز: 18 نقطة من 6 مباريات" in cap and "elgoon.com/standings/egypt" in cap and "توقع" not in cap, cap)
os.environ.pop("FB_RACE", None)
ck("behind its own switch, once every three rounds", RR.armed() is False and RR.RACE_EVERY == 3)

print("4. the workflow")
wf = open(os.path.join(".github", "workflows", "fb-post.yml"), encoding="utf-8").read()
ck("both variables reach the job, and neither script can fail it",
   "FB_POSTER: ${{ vars.FB_POSTER }}" in wf and "FB_RACE: ${{ vars.FB_RACE }}" in wf
   and "python match_poster.py --auto --publish | tee -a /tmp/fb.txt || true" in wf
   and "python reel_slots.py --run | tee -a /tmp/fb.txt || true" in wf)      # the race rides the slots since the same day

print("\nALL OK" if not fails else f"\n{fails} FAILED")
sys.exit(1 if fails else 0)
