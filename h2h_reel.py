#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Elgoon - the HEAD-TO-HEAD reel, rewritten (user 2026-11-20: «ريل المواجهات
ممكن نعيد كتابته»).

The first version was built on a reel API that no longer exists and on the
feed's own game list; it had not run since 2026-11-01. This one stands on
what the site uses today:

  * the pairs and their meetings are site_lib/h2h.py's - the same rows the
    /h2h/<slug> page shows (the saved history + our own finished matches,
    a result awarded by decision counted but not its goals);
  * the frames are moment_reel / day_reel's (the brand background, the small
    head logo, rows that fade in), inside the Reels safe band;
  * 14.5 s: the two clubs, the count of the meetings we hold, the last five
    game by game, the outro (user rule: every reel is 15 s or less).

NEVER an all-time record: the reel says «آخر N مواجهة» - what is saved, no
more (h2h page rule).

    python h2h_reel.py --pair al-ahly-pyramids --out h2h.mp4 --sheet h2h.png
    python h2h_reel.py --auto --publish     # a pair that meets TODAY (the morning run)

--auto posts one reel on the day two sides of a pair meet (store kind reel /
h2h:<slug>:<date>), nothing on any other day.
"""
import argparse
import datetime
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
from PIL import Image, ImageDraw                     # noqa: E402

import day_reel as DR                                # noqa: E402
import fb_cards as C                                 # noqa: E402
import fb_reel as R                                  # noqa: E402
import moment_reel as M                              # noqa: E402
import store                                         # noqa: E402
from site_lib import h2h as H                        # noqa: E402

W, H_, FPS = M.W, M.H, M.FPS
INTRO, TALLY, GAMES, OUTRO = 2.5, 3.5, 5.5, 3.0      # 14.5 s
LAST_N = 5
MIN_MEETINGS = 4
INK = DR.INK


def load_pool():
    """{match_id: row} - every match we hold, finished or to come."""
    import results_archive as RA
    from site_lib.config import load
    pool = {}
    rows = list(load("matches.json") or []) + RA.season_rows(RA.load())
    for f in load("fixtures.json") or []:
        for r in f.get("rounds") or []:
            rows += r.get("matches") or []
    for m in rows:
        if m.get("match_id") and str(m["match_id"]) not in pool:
            pool[str(m["match_id"])] = dict(m, status=(m.get("status") or "FINISHED"))
    return pool


def badge_of(team, pool):
    from site_lib.names import ar_team
    for m in pool.values():
        for side in ("home", "away"):
            if ar_team(m.get(side) or "") == team and m.get(f"{side}_badge"):
                return m[f"{side}_badge"]
    return None


def context(pair, pool, today=None):
    """Everything the reel says, or None when fewer than MIN_MEETINGS
    meetings are on record."""
    history = H.load_history(pair)
    notes = H.notes_for(pair, history)
    games = H.meetings(pair, history, pool)
    if len(games) < MIN_MEETINGS:
        return None
    t = H.tally(games, pair, notes)
    a, b = pair["a"], pair["b"]
    today = today or datetime.date.today().isoformat()
    nxt = H.next_meeting(pair, pool, today)
    return {"pair": pair, "a": a, "b": b, "n": len(games), "wins": t["wins"], "draws": t["draws"], "goals": t["goals"],
            "games": games[:LAST_N], "notes": notes, "next": nxt,
            "badges": {a: badge_of(a, pool), b: badge_of(b, pool)}}


def _meetings(n):
    return "مواجهتين" if n == 2 else f"{n} مواجهات" if n <= 10 else f"{n} مواجهة"


def build(ctx):
    """The scenes as (draw(t) -> frame, seconds, push_in)."""
    bg = R.background()
    mctx = M.context({"home": {"name": ""}, "away": {"name": ""}})
    a, b = ctx["a"], ctx["b"]
    title = f"{a} × {b}"

    def head(im, sub):
        R.logo_at(im, W / 2, DR.HEAD_LOGO_Y, DR.HEAD_LOGO_H)
        C.draw_center(ImageDraw.Draw(im), W / 2, DR.TITLE_Y, C.ar(sub), C.fit(ImageDraw.Draw(im), C.ar(sub), "ExtraBold", 44, W - 160, 28), C.WHITE)

    def crests(lay, cy, size, names=True):
        d = ImageDraw.Draw(lay)
        for team, x in ((a, W * 0.76), (b, W * 0.24)):
            R.crest_at(lay, ctx["badges"].get(team), team, size, x, cy)
            if names:
                nm = C.ar(team)
                d.text((x, cy + size * 0.5 + 60), nm, font=C.fit(d, nm, "ExtraBold", 58, W * 0.4, 30), fill=C.WHITE, anchor="mm")

    def intro(t):
        im = bg.copy()
        head(im, "المواجهات المباشرة")
        e = 1.0          # whole on the first frame (designer review 2026-11-20)
        if e > 0:
            lay = M.layer()
            crests(lay, 760, 250)
            mk = DR.mark(120)
            if mk is not None:
                lay.paste(mk, (int(W / 2 - 60), 700), mk)
            M.put(im, lay, e, dy=M.SLIDE * (1 - e))
        M.lines_block(im, t, [f"آخر {_meetings(ctx['n'])} بينهما"], (1180,), weight="ExtraBold", size=56, t0=-1.0)
        return im

    def tally(t):
        im = bg.copy()
        head(im, f"{title} · آخر {_meetings(ctx['n'])}")
        e = M.ease(t, 0.1, M.FADE + 0.1)
        if e > 0:
            lay = M.layer()
            d = ImageDraw.Draw(lay)
            crests(lay, 560, 150, names=False)
            cols = ((W * 0.76, ctx["wins"][a], f"فوز {a}"), (W * 0.5, ctx["draws"], "تعادل"), (W * 0.24, ctx["wins"][b], f"فوز {b}"))
            for x, n, lbl in cols:
                d.rounded_rectangle((x - 130, 720, x + 130, 1080), 36, fill=(255, 255, 255, 34))
                d.text((x, 860), str(n), font=C.font("ExtraBold", 200), fill=C.WHITE, anchor="mm")
                s = C.ar(lbl)
                d.text((x, 1020), s, font=C.fit(d, s, "ExtraBold", 36, 236, 20), fill=(255, 255, 255, 225), anchor="mm")
            g = C.ar(f"الأهداف: {a} {ctx['goals'][a]} · {b} {ctx['goals'][b]}")
            d.text((W / 2, 1190), g, font=C.fit(d, g, "ExtraBold", 48, W - 160, 28), fill=C.WHITE, anchor="mm")
            M.put(im, lay, e, dy=M.SLIDE * (1 - e))
        return im

    rows = ctx["games"]
    h, ys = DR.row_geometry(len(rows))

    def game_row(im, t, g, cy, t0):
        e = M.ease(t, t0, M.FADE + 0.1)
        if e <= 0:
            return
        lay = M.layer()
        d = ImageDraw.Draw(lay)
        d.rounded_rectangle((50, cy - h / 2 + 6, W - 50, cy + h / 2 - 6), int(h * 0.2), fill=(255, 255, 255, 26))
        cs = int(min(104, h * 0.62))
        for team, x, anchor, edge in ((g["home"], DR.HOME_X, "rm", DR.HOME_X - cs / 2 - 16),
                                      (g["away"], DR.AWAY_X, "lm", DR.AWAY_X + cs / 2 + 16)):
            R.crest_at(lay, ctx["badges"].get(team), team, cs, x, cy)
            nm = C.ar(team)
            d.text((edge, cy), nm, font=C.fit(d, nm, "ExtraBold", int(min(42, h * 0.3)), abs(edge - W / 2) - DR.NAME_GAP, 22),
                   fill=C.WHITE, anchor=anchor)
        sy = cy - h * 0.09
        f = C.font("ExtraBold", int(min(84, h * 0.5)))
        d.text((W / 2 + DR.SCORE_DX, sy), str(g["hg"]), font=f, fill=C.WHITE, anchor="mm")       # HOME goals on the right
        d.text((W / 2 - DR.SCORE_DX, sy), str(g["ag"]), font=f, fill=C.WHITE, anchor="mm")
        d.text((W / 2, sy), "-", font=C.font("ExtraBold", int(min(60, h * 0.36))), fill=M.GOLD, anchor="mm")
        note = (ctx["notes"].get(g["date"]) or {}).get("note")
        lb = C.ar(" · ".join(x for x in (H.ar_month_year(g["date"]), g.get("comp") or "", note) if x))
        d.text((W / 2, cy + h * 0.31), lb, font=C.fit(d, lb, "Bold", int(max(26, min(30, h * 0.17))), W - 2 * 190, 18),
               fill=(255, 255, 255, 215), anchor="mm")
        M.put(im, lay, e, dy=M.SLIDE * (1 - e))

    def games(t):
        im = bg.copy()
        head(im, f"آخر {_meetings(len(rows))} · الأحدث أولًا")
        for i, g in enumerate(rows):
            game_row(im, t, g, ys[i], 0.1 + i * 0.18)
        return im

    def outro(t):
        return M.scene({"kind": "cta", "secs": OUTRO, "lines": ["تابع صفحة الجون", "أرقام المواجهات قبل كل قمة"]}, t, mctx)

    return [(intro, INTRO, True), (tally, TALLY, True), (games, GAMES, True), (outro, OUTRO, False)]


def caption(ctx):
    a, b = ctx["a"], ctx["b"]
    lines = [f"⚔️ {a} × {b}: آخر {_meetings(ctx['n'])} بينهما", "",
             f"{a} فاز {ctx['wins'][a]} · تعادل {ctx['draws']} · {b} فاز {ctx['wins'][b]}",
             f"الأهداف: {a} {ctx['goals'][a]} · {b} {ctx['goals'][b]}"]
    nx = ctx.get("next")
    if nx and nx.get("kickoff"):
        when = H.ar_date(nx["kickoff"]) + (f" الساعة {nx['koff_time']} بتوقيت القاهرة" if nx.get("koff_time") else "")
        lines += ["", f"المواجهة القادمة: {when}."]
    lines += ["", "بتشجع مين؟ اكتب اسم فريقك في الكومنتات 👇",
              "", f"كل المواجهات مباراة بمباراة: https://elgoon.com/h2h/{ctx['pair']['slug']}",
              f"#الجون #{a.replace(' ', '_')} #{b.replace(' ', '_')}"]
    return "\n".join(lines) + "\n"


def meeting_today(pool, today):
    """[(pair, match)] for the pairs whose two sides meet today."""
    out = []
    for p in H.PAIRS:
        nx = H.next_meeting(p, pool, today)
        if nx and str(nx.get("kickoff") or "")[:10] == today and (nx.get("status") or "").upper() == "UPCOMING":
            out.append((p, nx))
    return out


def render(ctx, out, sheet=None):
    scenes = build(ctx)
    secs = sum(s[1] for s in scenes)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    ok = M.encode({"id": f"h2h-{ctx['pair']['slug']}"}, None, out, secs, frame_iter=DR.frames(scenes))
    if sheet:
        M.contact_sheet([draw(dur - 0.05) for draw, dur, _ in scenes], sheet, cols=len(scenes))
    return ok, secs


def publish(path, ctx, date):
    token = os.environ.get("FB_PAGE_TOKEN", "").strip()
    if not token:
        print("FB_PAGE_TOKEN not set: rendered, not published")
        return 0
    ref = f"h2h:{ctx['pair']['slug']}:{date}"
    if not store.claim(R.KIND, ref, title=f"h2h reel {ctx['pair']['slug']} {date}"):
        print(f"h2h reel {ref}: already published or held by another run")
        return 0
    try:
        vid = R.post_reel(token, path, caption(ctx))
        store.record_post(R.KIND, ref, vid, title=f"h2h reel {ctx['pair']['slug']} {date}")
        print(f"h2h reel {ref}: published as {vid}")
        return 0
    except Exception as e:                                   # noqa: BLE001
        store.release(R.KIND, ref)
        print(f"h2h reel {ref} FAILED: {e}")
        return 1


def main():
    from zoneinfo import ZoneInfo
    ap = argparse.ArgumentParser()
    ap.add_argument("--pair", help="a pair's slug (site_lib/h2h.PAIRS)")
    ap.add_argument("--auto", action="store_true", help="the pair that meets today, if any")
    ap.add_argument("--out")
    ap.add_argument("--sheet")
    ap.add_argument("--publish", action="store_true")
    args = ap.parse_args()
    today = datetime.datetime.now(ZoneInfo("Africa/Cairo")).date().isoformat()
    pool = load_pool()
    if args.auto:
        todo = meeting_today(pool, today)
        if not todo:
            print(f"h2h reel {today}: no pair meets today"); return 0
        pair = todo[0][0]
    else:
        pair = next((p for p in H.PAIRS if p["slug"] == args.pair), None)
        if not pair:
            print("no such pair - see site_lib/h2h.PAIRS"); return 1
    if args.publish:
        rec = store.get_post(R.KIND, f"h2h:{pair['slug']}:{today}")
        if rec and rec.get("post_id"):
            print(f"h2h reel {pair['slug']} {today}: already posted ({rec['post_id']})"); return 0
    ctx = context(pair, pool, today)
    if not ctx:
        print(f"h2h reel {pair['slug']}: fewer than {MIN_MEETINGS} meetings on record - no reel"); return 0
    out = args.out or os.path.join(HERE, "media", "reels", f"h2h-{pair['slug']}-{today}.mp4")
    ok, secs = render(ctx, out, args.sheet)
    print(f"{out}: {secs:.1f}s, {'UPLOADABLE' if ok else 'NOT uploadable'}")
    print(caption(ctx))
    if args.publish:
        if not ok:
            print("not publishing a file ffmpeg did not write"); return 1
        return publish(out, ctx, today)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
