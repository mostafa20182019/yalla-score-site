#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A league TABLE as a vertical reel (user, 2026-11-09: «اعمل ريل بترتيب
الدورى الاسبانى هيكون فيه الفريق واللوجو بتاعه والنقاط»).

data/standings.json -> intro («ترتيب الدوري الإسباني» + after how many
rounds), one page per five clubs (position, crest, Arabic name, points; the
Champions League places marked blue, the relegation places red), outro.
Same canvas, wordmark, safe band, music and encoder as day_reel / moment_reel.

    python table_reel.py --comp "Primera Division" --out t.mp4 --sheet t.png
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")

import json                          # noqa: E402
from PIL import ImageDraw            # noqa: E402

import day_reel as D                 # noqa: E402
import fb_cards as C                 # noqa: E402
import fb_reel as R                  # noqa: E402
import moment_reel as M              # noqa: E402

W, H = M.W, M.H
PER_PAGE = 5
INTRO, PAGE, OUTRO = 2.5, 3.5, 3.0
# the top ten: 2.5 + 2 x 3.5 + 3 = 12.5 s (user rule 2026-11-10: every reel is 15 s or less); the full
# table is one tap away (the caption's link)
MAX_ROWS = 10
ROW_TOP, ROW_H, ROW_HALF = 560, 172, 74     # centres 560..1248, last row ends 1322 < safe band
X_POS, X_CREST, X_NAME_R, X_PTS = 930, 830, 755, 165
UCL = (31, 148, 211)                        # the Champions League places
DROP = (214, 48, 64)                        # relegation
ZONES = {"Primera Division": (4, 3), "Premier League": (4, 3), "Serie A": (4, 3),
         "Bundesliga": (4, 2), "Ligue 1": (3, 2)}


def table_for(comp, path=None):
    d = json.load(open(path or os.path.join(HERE, "data", "standings.json"), encoding="utf-8"))
    for block in d["results"]:
        for it in block.get("items") or []:
            if it.get("competition") == comp and it.get("table"):
                return it["table"]
    raise SystemExit(f"no table for {comp!r} in standings.json")


def zone(pos, n, comp):
    top, down = ZONES.get(comp, (0, 0))
    if pos <= top:
        return UCL
    if down and pos > n - down:
        return DROP
    return None


def row(im, t, r, cy, t0, n, comp):
    from site_lib.names import ar_team
    e = M.ease(t, t0, M.FADE)
    if e <= 0:
        return
    lay = M.layer()
    d = ImageDraw.Draw(lay)
    d.rounded_rectangle((60, cy - ROW_HALF, 990, cy + ROW_HALF), 28, fill=(255, 255, 255, 26))
    z = zone(r["pos"], n, comp)
    if z:
        d.rounded_rectangle((972, cy - ROW_HALF + 14, 990, cy + ROW_HALF - 14), 6, fill=z)
    fp = C.font("ExtraBold", 54)
    C.draw_center(d, X_POS, cy - 36, str(r["pos"]), fp, M.GOLD if r["pos"] == 1 else C.WHITE)
    R.crest_at(lay, r.get("crest"), ar_team(r["team"]), 100, X_CREST, cy)
    nm = C.ar(ar_team(r["team"]))
    f = C.fit(d, nm, "ExtraBold", 48, X_NAME_R - 310, 28)
    d.text((X_NAME_R - C.text_w(d, nm, f), cy - 32), nm, font=f, fill=C.WHITE)
    C.draw_center(d, X_PTS, cy - 58, str(r["pts"]), C.font("ExtraBold", 70), C.WHITE)
    C.draw_center(d, X_PTS, cy + 24, C.ar("نقطة"), C.font("Bold", 26), M.SOFT)
    M.put(im, lay, e, dy=M.SLIDE * (1 - e))


def build(table, comp, label):
    bg = R.background()
    ctx = M.context({"home": {"name": ""}, "away": {"name": ""}})
    played = max(int(r.get("played") or 0) for r in table)
    title, sub = f"ترتيب {label}", f"بعد الجولة {played}"
    table = list(table)[:MAX_ROWS]
    n = len(table)

    def intro(t):
        im = bg.copy()
        M.header(im)
        M.big_at(im, t, "الترتيب", 600, 170)
        M.lines_block(im, t, [label, sub], (900, 990), weight="ExtraBold", size=58, t0=0.45)
        return im

    def page(rows, k, pages):
        def draw(t):
            im = bg.copy()
            M.header(im)
            d = ImageDraw.Draw(im)
            C.draw_center(d, W / 2, 425, C.ar(f"{title} · {sub}"), C.font("ExtraBold", 40), C.WHITE)
            for i, r in enumerate(rows):
                row(im, t, r, ROW_TOP + i * ROW_H, 0.1 + i * 0.18, n, comp)
            # the legend under the page that shows the zone
            leg = []
            if any(zone(r["pos"], n, comp) == UCL for r in rows):
                leg.append((UCL, "دوري أبطال أوروبا"))
            if any(zone(r["pos"], n, comp) == DROP for r in rows):
                leg.append((DROP, "الهبوط"))
            for col, txt in leg:
                y = ROW_TOP + len(rows) * ROW_H - ROW_H / 2 + 30
                s = C.ar(txt)
                f = C.font("Bold", 32)
                tw = C.text_w(d, s, f)
                d.rounded_rectangle((W / 2 + tw / 2 + 16, y + 8, W / 2 + tw / 2 + 44, y + 36), 6, fill=col)
                d.text((W / 2 - tw / 2, y), s, font=f, fill=C.WHITE)
            return im
        return draw

    def outro(t):
        sc = {"kind": "cta", "secs": OUTRO, "lines": ["الجدول كامل", "لحظة بلحظة على الجون"]}
        return M.scene(sc, t, ctx)

    pages = [table[i:i + PER_PAGE] for i in range(0, n, PER_PAGE)]
    return ([(intro, INTRO, True)] + [(page(p, k, len(pages)), PAGE, True) for k, p in enumerate(pages)]
            + [(outro, OUTRO, False)])


def caption(table, label, comp):
    from site_lib.names import ar_team
    from site_lib.competitions import COMP_SLUG
    played = max(int(r.get("played") or 0) for r in table)
    lines = [f"📊 ترتيب {label} بعد الجولة {played}", ""]
    for r in table[:5]:
        lines.append(f"{r['pos']}. {ar_team(r['team'])} - {r['pts']} نقطة")
    lines += ["...", "", "مين هياخد الدوري السنة دي؟ قولنا في الكومنتات 👇", ""]
    slug = COMP_SLUG.get(comp)
    lines.append(f"الجدول كامل: https://elgoon.com/standings/{slug}.html" if slug else "https://elgoon.com")
    lines.append("#الجون #ترتيب_الدوري")
    return "\n".join(lines) + "\n"


def main():
    from site_lib.names import comp_label
    ap = argparse.ArgumentParser()
    ap.add_argument("--comp", default="Primera Division")
    ap.add_argument("--out", required=True)
    ap.add_argument("--sheet")
    args = ap.parse_args()
    table = table_for(args.comp)
    label = comp_label(args.comp)
    scenes = build(table, args.comp, label)
    secs = sum(s[1] for s in scenes)
    ok = M.encode({"id": f"table-{args.comp}"}, None, args.out, secs, frame_iter=D.frames(scenes))
    if args.sheet:
        M.contact_sheet([draw(dur - 0.05) for draw, dur, _ in scenes], args.sheet, cols=len(scenes))
    cap = caption(table, label, args.comp)
    with open(os.path.splitext(args.out)[0] + "-caption.txt", "w", encoding="utf-8") as fh:
        fh.write(cap)
    print(f"{args.out}: {secs:.1f}s, {'UPLOADABLE' if ok else 'NOT uploadable'}")
    print(cap)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
