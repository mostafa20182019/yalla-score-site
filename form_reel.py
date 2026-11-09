#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A club's FORM as a vertical reel (the day_reel.py pattern, 2026-11-09):
the same rows as form_card.py, landing one by one, the next fixture last.

    intro 2.5 s   the club's crest in its ring, «آخر 8 مباريات», the tally
    rows  ~6 s    the results newest first, each sliding in 0.4 s after the
                  one above - the mark disc, the opponent's crest and name,
                  the score (club goals RIGHT of the dash), the competition
    next  3.5 s   «المباراة القادمة»: both crests, the names, day + Cairo time
    outro 2.5 s   the wordmark + «تابع الجون» + elgoon.com

Encoded by moment_reel.encode with the page's music loop; the frames stay
inside the Reels safe band (fb_reel.SAFE_BOTTOM) and clear of the button
column on the right. Published through the store under kind "reel" /
ref form:<slug>:<match_id> - one reel per fixture - and ONLY behind the same
FB_REELS switch as every other reel (fb_reel.enabled()).

    python form_reel.py --club barcelona --out r.mp4 --sheet r.png      # local preview
    python fb_post.py --events                                           # the nightly run posts the card, then this
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from PIL import Image, ImageDraw     # noqa: E402

import fb_cards as C                 # noqa: E402
import fb_reel as R                  # noqa: E402
import form_card as FCard            # noqa: E402
import moment_reel as M              # noqa: E402
import store                         # noqa: E402

W, H, FPS = M.W, M.H, M.FPS
INTRO, NEXT, OUTRO = 2.5, 3.5, 2.5
ROW_STAGGER, ROWS_HOLD = 0.4, 2.4    # rows land one by one, then hold
ROW_TOP = 560                        # the first row's centre, under the title
MARK_X = W * 0.87                    # the mark disc: its right edge stays left of the Reels button column (x > 0.91 W)
PILL_X = W * 0.36


def rows_secs(n):
    return round(0.3 + n * ROW_STAGGER + ROWS_HOLD, 1)


def row_h(n):
    """Row pitch: 100 px, or less so the last row's bottom stays inside the
    safe band (ten rows: 91)."""
    return min(100, (R.SAFE_BOTTOM - 60 - ROW_TOP) // max(1, n - 1)) if n > 1 else 100


def row(im, t, r, cy, t0, rh):
    """One result: fades and slides in at t0."""
    e = M.ease(t, t0, M.FADE + 0.1)
    if e <= 0:
        return
    lay = M.layer()
    d = ImageDraw.Draw(lay)
    half = rh // 2 - 5
    d.rounded_rectangle((60, cy - half, W - 60, cy + half), 26, fill=(255, 255, 255, 26))
    mr = 26 if rh >= 90 else 22
    FCard.draw_mark(lay, MARK_X, cy, mr, r["mark"])
    cr = 64 if rh >= 90 else 54
    cx = MARK_X - mr - 24 - cr / 2
    d.ellipse([cx - cr / 2, cy - cr / 2, cx + cr / 2, cy + cr / 2], fill=C.WHITE)
    R.crest_at(lay, r.get("opponent_badge"), r["opponent"], int(cr * 0.78), cx, cy)
    name_r = cx - cr / 2 - 16
    pill_w = 150
    px0, px1 = PILL_X - pill_w / 2, PILL_X + pill_w / 2
    nm = C.ar(r["opponent"])
    f = C.fit(d, nm, "ExtraBold", 40 if rh >= 90 else 34, name_r - px1 - 20, 22)
    d.text((name_r - C.text_w(d, nm, f), cy - f.size * 0.62), nm, font=f, fill=C.WHITE)
    d.rounded_rectangle((px0, cy - 28, px1, cy + 28), 14, fill=(255, 255, 255, 235))
    sc = f"{r['ga']} - {r['gf']}"                          # the club's goals RIGHT of the dash
    fs = C.font("ExtraBold", 40 if rh >= 90 else 34)
    bx = d.textbbox((0, 0), sc, font=fs)
    d.text(((px0 + px1) / 2 - (bx[0] + bx[2]) / 2, cy - (bx[1] + bx[3]) / 2), sc, font=fs, fill=FCard.TOP)
    comp = C.ar(r["comp_label"])
    fc = C.fit(d, comp, "Bold", 24, px0 - 90, 16)
    d.text((px0 - 14 - C.text_w(d, comp, fc), cy - fc.size * 0.62), comp, font=fc, fill=M.SOFT)
    M.put(im, lay, e, dy=M.SLIDE * (1 - e))


def build(ev):
    """The scenes as (draw(t) -> frame, seconds, push_in)."""
    from site_lib.names import ar_team
    import story_events as SE
    bg = R.background()
    club, rec, nxt = ev["club"], ev["record"], ev.get("next")
    rows = list(reversed(ev["rows"]))
    colour = FCard.club_colour(club["name"])
    ctx = M.context({"home": {"name": ""}, "away": {"name": ""}})
    n = rec["p"]
    title = f"آخر {n} مباريات" if 3 <= n <= 10 else f"آخر {n} مباراة"
    tally = f"فوز {rec['w']} · تعادل {rec['d']} · خسارة {rec['l']}"

    def club_crest(im, t, cy, size, t0=0.0):
        e = M.ease(t, t0, 0.45)
        if e <= 0:
            return
        lay = M.layer()
        d = ImageDraw.Draw(lay)
        d.ellipse([W / 2 - size / 2 - 10, cy - size / 2 - 10, W / 2 + size / 2 + 10, cy + size / 2 + 10], fill=colour)
        d.ellipse([W / 2 - size / 2, cy - size / 2, W / 2 + size / 2, cy + size / 2], fill=C.WHITE)
        R.crest_at(lay, club.get("badge"), club["name"], int(size * 0.78), W / 2, cy)
        M.put(im, lay, e, dy=M.SLIDE * (1 - e))

    def intro(t):
        im = bg.copy()
        M.header(im)
        club_crest(im, t, 680, 360)
        M.lines_block(im, t, [club["name"], title, tally], (930, 1030, 1120),
                      weight="ExtraBold", size=72, t0=0.35)
        return im

    rh = row_h(len(rows))

    def results(t):
        im = bg.copy()
        M.header(im)
        C.draw_center(ImageDraw.Draw(im), W / 2, 440, C.ar(f"{club['name']} · {title}"),
                      C.font("ExtraBold", 44), C.WHITE)
        for i, r in enumerate(rows):
            row(im, t, r, ROW_TOP + i * rh, 0.3 + i * ROW_STAGGER, rh)
        return im

    def fixture(t):
        im = bg.copy()
        M.header(im)
        M.lines_block(im, t, ["المباراة القادمة"], (480,), weight="ExtraBold", size=60, fill=M.GOLD, t0=0.05)
        if nxt:
            h, a = ar_team(nxt["home"]), ar_team(nxt["away"])
            for name, url, x, t0 in ((h, nxt.get("home_badge"), W * 0.72, 0.3), (a, nxt.get("away_badge"), W * 0.28, 0.5)):
                e = M.ease(t, t0, 0.45)
                if e > 0:
                    lay = M.layer()
                    d = ImageDraw.Draw(lay)
                    d.ellipse([x - 150, 760 - 150, x + 150, 760 + 150], fill=C.WHITE)
                    R.crest_at(lay, url, name, 230, x, 760)
                    nm = C.ar(name)
                    C.draw_center(d, x, 950, nm, C.fit(d, nm, "ExtraBold", 50, W * 0.40, 26), C.WHITE)
                    M.put(im, lay, e, dy=M.SLIDE * (1 - e))
            kk = SE._kick_dt(nxt)
            when = SE.ar_date(nxt.get("kickoff"), weekday=True, year=False)
            lines = [when + (f" · {kk:%H:%M} بتوقيت القاهرة" if nxt.get("koff_time") and kk else ""),
                     SE.comp_label(nxt.get("competition"))]
            M.lines_block(im, t, lines, (1110, 1200), size=46, fill=M.SOFT, t0=0.8)
        return im

    def outro(t):
        sc = {"kind": "cta", "secs": OUTRO, "lines": ["كل النتائج والجداول", "تابع الجون"]}
        return M.scene(sc, t, ctx)

    scenes = [(intro, INTRO, True), (results, rows_secs(len(rows)), True)]
    if nxt:
        scenes.append((fixture, NEXT, True))
    scenes.append((outro, OUTRO, False))
    return scenes


def frames(scenes):
    import day_reel as D
    for draw, dur, push in scenes:
        for i in range(int(round(dur * FPS))):
            t = i / FPS
            im = draw(t)
            yield D.push_in(im, t, dur) if push else im


def caption(ev):
    return ev["text"] + "\n"


def reel_path(ev):
    return os.path.join(HERE, "media", "reels", f"{ev['ref'].replace(':', '-')}.mp4")


def render(ev, out=None, sheet=None):
    """Encode the reel; (path, uploadable, seconds)."""
    scenes = build(ev)
    secs = sum(s[1] for s in scenes)
    out = out or reel_path(ev)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    ok = M.encode({"id": ev["ref"]}, None, out, secs, frame_iter=frames(scenes))
    if sheet:
        M.contact_sheet([draw(dur - 0.05) for draw, dur, _ in scenes], sheet, cols=len(scenes))
    return out, ok, secs


def publish(ev, token=None, out=None):
    """Claim-then-post under kind 'reel' / the event's ref. Silent (0) when
    FB_REELS is off, the token is absent or the reel is already on record;
    never raises - a reel must not fail the events run."""
    token = token if token is not None else os.environ.get("FB_PAGE_TOKEN", "").strip()
    if not R.enabled():
        print(f"form reel {ev['ref']}: FB_REELS is off - not rendered"); return 0
    if not token:
        print(f"form reel {ev['ref']}: FB_PAGE_TOKEN not set - not rendered"); return 0
    rec = store.get_post(R.KIND, ev["ref"])
    if rec and rec.get("post_id"):
        print(f"form reel {ev['ref']}: already published ({rec['post_id']})"); return 0
    if not store.claim(R.KIND, ev["ref"], title=ev.get("title")):
        print(f"form reel {ev['ref']}: held by another run"); return 0
    try:
        path, ok, secs = render(ev, out)
        if not ok:
            raise RuntimeError("ffmpeg did not write the file")
        vid = R.post_reel(token, path, caption(ev))
        store.record_post(R.KIND, ev["ref"], vid, title=ev.get("title"))
        print(f"form reel {ev['ref']}: published as {vid} ({secs:.1f} s)")
        return 0
    except Exception as e:                                   # noqa: BLE001
        store.release(R.KIND, ev["ref"])
        print(f"form reel {ev['ref']} FAILED: {e}")
        return 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--club", required=True, help="a curated club's slug")
    ap.add_argument("--out", help="the MP4 (default media/reels/form-<slug>-<match>.mp4)")
    ap.add_argument("--sheet", help="also write a contact sheet PNG (one frame per scene)")
    ap.add_argument("--n", type=int)
    ap.add_argument("--publish", action="store_true", help="upload to the page (FB_REELS=1 + FB_PAGE_TOKEN)")
    args = ap.parse_args()
    ev = FCard.sample_event(args.club, n=args.n)
    if not ev:
        print(f"{args.club}: no fixture in the next 30 days or too few results"); return 1
    if args.publish:
        return publish(ev, out=args.out)
    out, ok, secs = render(ev, args.out, args.sheet)
    print(f"{out}: {secs:.1f}s, {'UPLOADABLE' if ok else 'NOT uploadable'}")
    print(caption(ev))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
