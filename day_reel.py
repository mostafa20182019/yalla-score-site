#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The day's RESULTS as a vertical reel (user, 2026-11-09: «اعمل برضه ريل
بنتائج مباريات امس ونزله», then «Yes, automate it»).

The same matches as the nightly results card (fb_post.daycard_matches: the
nine leagues' finished matches, curated clubs first, at most nine), drawn on
the reel canvas (fb_reel background + wordmark, the Reels safe band) and
encoded by moment_reel.encode with the page's music loop:

    intro 2.5 s  «نتائج أمس» + the day + «9 مباريات من الدوريات الكبرى»
    shots        SIX results a shot (user, 2026-11-19: «النتائج ممكن اكتر
                 من لقطة بس اللقطة الواحدة فيها ست مباريات» - it was three a
                 shot): one shot of 7 s, or two of 4.5 s when the night has
                 twelve - home crest/name on the RIGHT and its goals right of
                 the dash (the RTL rule), the league under the score
    outro 3 s    the wordmark + «كل النتائج والجداول» + elgoon.com

Posted by fb-post.yml right after the results card (daycard=results), with
the store claim kind "reel" / "day:<date>" - one reel per day, ever.

    python day_reel.py --date 2026-11-08 --out r.mp4 --sheet r.png   # local preview
    python day_reel.py --publish                                     # the nightly run
"""
import argparse
import datetime
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")

from PIL import Image, ImageDraw     # noqa: E402

import fb_cards as C                 # noqa: E402
import fb_reel as R                  # noqa: E402
import moment_reel as M              # noqa: E402
import store                         # noqa: E402

W, H, FPS = M.W, M.H, M.FPS
# SIX results a shot (user 2026-11-19), and only FULL shots after the first:
# a night of 6-11 results shows its first six, a night of twelve or more two
# shots of six; fewer than six = the one short shot the day has. Two shots at
# most: 2.5 + 2 x 4.5 + 3 = 14.5 s (user rule 2026-11-10: every reel is 15 s
# or less). The caption still lists every result the caller passed.
PER_SHOT = 6
MAX_SHOTS = 2
MAX_MATCHES = PER_SHOT * MAX_SHOTS   # what main() asks fb_post.daycard_matches for
INTRO, OUTRO = 2.5, 3.0
PAGE, PAGE_TWO = 7.0, 4.5            # one shot alone / each of two
BAND_TOP, BAND_BOTTOM = 480, R.SAFE_BOTTOM - 10   # under the page title, inside the Reels safe band
ROW_MAX_H = 170
HOME_X, AWAY_X = W - 150, 150        # the crests: clear of the Reels like/comment column on the right
SCORE_DX = 52                        # each side's goals, this far from the dash
NAME_GAP = 100                       # the names stop this far from the centre


def row_geometry(n):
    """(row height, [row centres]) for n rows: they fill the band, a short
    list sits in its middle with rows no taller than ROW_MAX_H."""
    n = max(1, n)
    h = min(ROW_MAX_H, (BAND_BOTTOM - BAND_TOP) / n)
    top = BAND_TOP + ((BAND_BOTTOM - BAND_TOP) - n * h) / 2
    return h, [top + h * (i + 0.5) for i in range(n)]


def shots(ms):
    """The results split into shots of PER_SHOT - full ones only past the first."""
    ms = list(ms)
    n = max(1, min(MAX_SHOTS, len(ms) // PER_SHOT))
    return [ms[i * PER_SHOT:(i + 1) * PER_SHOT] for i in range(n)]


def rel_label(date, now=None):
    """«أمس» / «اليوم» from the Cairo clock; any other day by name."""
    from zoneinfo import ZoneInfo
    today = (now or datetime.datetime.now(ZoneInfo("Africa/Cairo"))).date()
    delta = (datetime.date.fromisoformat(date) - today).days
    return {0: "نتائج اليوم", -1: "نتائج أمس"}.get(delta) or f"نتائج {day_name(date)}"


def day_name(date):
    from site_lib.arabic import _AR_DAYS, _AR_MONTHS
    dd = datetime.date.fromisoformat(date)
    return f"{_AR_DAYS[dd.weekday()]} {dd.day} {_AR_MONTHS[dd.month]}"


def row(im, t, m, cy, t0, h):
    """One result on ONE line, h tall: fades and slides in at t0."""
    from site_lib.names import ar_team, comp_label
    e = M.ease(t, t0, M.FADE + 0.1)
    if e <= 0:
        return
    lay = M.layer()
    d = ImageDraw.Draw(lay)
    d.rounded_rectangle((50, cy - h / 2 + 6, W - 50, cy + h / 2 - 6), int(h * 0.2), fill=(255, 255, 255, 26))
    cs = int(min(104, h * 0.62))                       # the crest
    for side, x, anchor, edge in (("home", HOME_X, "rm", HOME_X - cs / 2 - 16),
                                  ("away", AWAY_X, "lm", AWAY_X + cs / 2 + 16)):
        R.crest_at(lay, m.get(f"{side}_badge"), ar_team(m[side]), cs, x, cy)
        nm = C.ar(ar_team(m[side]))
        room = abs(edge - W / 2) - NAME_GAP
        d.text((edge, cy), nm, font=C.fit(d, nm, "ExtraBold", int(min(42, h * 0.3)), room, 22),
               fill=C.WHITE, anchor=anchor)
    sy = cy - h * 0.09
    f = C.font("ExtraBold", int(min(84, h * 0.5)))
    d.text((W / 2 + SCORE_DX, sy), str(m["home_score"]), font=f, fill=C.WHITE, anchor="mm")   # HOME goals on the right
    d.text((W / 2 - SCORE_DX, sy), str(m["away_score"]), font=f, fill=C.WHITE, anchor="mm")
    d.text((W / 2, sy), "-", font=C.font("ExtraBold", int(min(60, h * 0.36))), fill=M.GOLD, anchor="mm")
    lb = C.ar(comp_label(m["competition"]))
    d.text((W / 2, cy + h * 0.31), lb, font=C.fit(d, lb, "Bold", int(max(18, min(26, h * 0.17))), 2 * NAME_GAP + 60, 14),
           fill=M.GOLD, anchor="mm")
    M.put(im, lay, e, dy=M.SLIDE * (1 - e))


def build(ms, date, now=None):
    """The scenes as (draw(t) -> frame, seconds, push_in) - push_in False for
    the outro, which moment_reel.scene already pushes in."""
    pages = shots(ms)
    ms = [m for p in pages for m in p]
    bg = R.background()
    ctx = M.context({"home": {"name": ""}, "away": {"name": ""}})
    title, when = rel_label(date, now), day_name(date)

    def intro(t):
        im = bg.copy()
        M.header(im)
        M.big_at(im, t, title, 600, 170)
        # «من الدوريات الكبرى» only when it is true: a break night's results
        # come from the qualifiers and the cups (2026-11-19)
        from site_lib.competitions import LEAGUE_BAR
        _big = all(m.get("competition") in LEAGUE_BAR for m in ms)
        M.lines_block(im, t, [when, f"{len(ms)} مباريات من الدوريات الكبرى" if _big else f"أبرز {len(ms)} نتائج"], (900, 990),
                      weight="ExtraBold", size=56, t0=0.45)
        return im

    def page(rows):
        def draw(t):
            im = bg.copy()
            M.header(im)
            C.draw_center(ImageDraw.Draw(im), W / 2, 425, C.ar(f"{title} · {when}"),
                          C.font("ExtraBold", 40), C.WHITE)
            h, ys = row_geometry(len(rows))
            for i, m in enumerate(rows):
                row(im, t, m, ys[i], 0.1 + i * 0.15, h)
            return im
        return draw

    def outro(t):
        sc = {"kind": "cta", "secs": OUTRO, "lines": ["كل النتائج والجداول", "لحظة بلحظة على الجون"]}
        return M.scene(sc, t, ctx)

    secs = PAGE if len(pages) == 1 else PAGE_TWO
    return [(intro, INTRO, True)] + [(page(p), secs, True) for p in pages] + [(outro, OUTRO, False)]


def push_in(im, t, dur):
    z = 1 + M.PUSH_IN * min(1.0, t / dur)
    cw, ch = W / z, H / z
    return im.crop((int((W - cw) / 2), int((H - ch) / 2),
                    int((W + cw) / 2), int((H + ch) / 2))).resize((W, H), Image.BILINEAR)


def frames(scenes):
    for draw, dur, push in scenes:
        for i in range(int(round(dur * FPS))):
            t = i / FPS
            im = draw(t)
            yield push_in(im, t, dur) if push else im


def caption(ms, date, now=None):
    from site_lib.names import ar_team
    lines = [f"⚽ {rel_label(date, now)} ({day_name(date)})", ""]
    for m in ms:
        lines.append(f"{ar_team(m['home'])} {m['home_score']} - {m['away_score']} {ar_team(m['away'])}")
    lines += ["", "أنهي نتيجة فاجئتك؟ قولنا في الكومنتات 👇", "",
              "كل النتائج والمواعيد: https://elgoon.com/", "#الجون #نتائج_المباريات"]
    return "\n".join(lines) + "\n"


def publish(path, ms, date):
    """Claim-then-post, kind 'reel' / 'day:<date>': one results reel a day."""
    token = os.environ.get("FB_PAGE_TOKEN", "").strip()
    if not token:
        print("FB_PAGE_TOKEN not set: rendered, not published")
        return 0
    ref = f"day:{date}"
    if not store.claim(R.KIND, ref, title=f"results reel {date}"):
        print(f"day reel {date}: already published or held by another run")
        return 0
    try:
        vid = R.post_reel(token, path, caption(ms, date))
        store.record_post(R.KIND, ref, vid, title=f"results reel {date}")
        print(f"day reel {date}: published as {vid} ({len(ms)} matches)")
        return 0
    except Exception as e:                                   # noqa: BLE001
        store.release(R.KIND, ref)
        print(f"day reel {date} FAILED: {e}")
        return 1


def main():
    import fb_post as P
    import match_brief as MB
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="YYYY-MM-DD (default: the date the nightly card posts)")
    ap.add_argument("--out", help="the MP4 (default media/reels/day-<date>.mp4)")
    ap.add_argument("--sheet", help="also write a contact sheet PNG (one frame per scene)")
    ap.add_argument("--publish", action="store_true", help="upload to the page (needs FB_PAGE_TOKEN)")
    args = ap.parse_args()
    date = args.date or P.daycard_date()
    if args.publish:
        rec = store.get_post(R.KIND, f"day:{date}")
        if rec and rec.get("post_id"):
            print(f"day reel {date}: already posted ({rec['post_id']})")
            return 0
    ms = P.daycard_matches(MB.load_all()["matches"], date, limit=MAX_MATCHES)
    if len(ms) < P.DAYCARD_MIN:
        print(f"day reel {date}: only {len(ms)} finished match(es) - no reel")
        return 0
    scenes = build(ms, date)
    secs = sum(s[1] for s in scenes)
    out = args.out or os.path.join(HERE, "media", "reels", f"day-{date}.mp4")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    ok = M.encode({"id": f"day-{date}"}, None, out, secs, frame_iter=frames(scenes))
    if args.sheet:
        M.contact_sheet([draw(dur - 0.05) for draw, dur, _ in scenes], args.sheet, cols=len(scenes))
    print(f"{out}: {secs:.1f}s, {'UPLOADABLE' if ok else 'NOT uploadable'}")
    print(caption(ms, date))
    if args.publish:
        if not ok:
            print("not publishing a file ffmpeg did not write")
            return 1
        return publish(out, ms, date)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
