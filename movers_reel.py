#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Elgoon - «الصاعد والهابط»: the table's movers after a league round, as a
REEL (social review 2026-11-19; user 2026-11-20: «اعمل 9»).

The static table is on every page; who CLIMBED and who DROPPED is the news,
and it touches the mid-table clubs nobody covers. The reel is drawn from
story_social.round_movers()'s event - nothing is computed here:

  * the place AFTER the round is the official table's;
  * the place BEFORE is rebuilt by taking the round's points off that table,
    and a side level on points with another before the round is left out
    (its place then was the league's tie-breakers', not ours);
  * only when the table we hold is this round's table.

12.5 s: the league and the round, the movers (two climbs, two drops at
most), the outro (user rule: every reel is 15 s or less).

    python movers_reel.py --date 2026-11-09 --out movers.mp4 --sheet movers.png
    python movers_reel.py --auto            # the nightly run: post what is owed

--auto posts ONE league a night (the biggest move first), each round once
(store kind reel / movers:<competition>:R<n>:<season>).
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

W, H, FPS = M.W, M.H, M.FPS
INTRO, PAGE, OUTRO = 2.5, 7.0, 3.0                   # 12.5 s
UP, DOWN = (22, 163, 74), (225, 29, 72)              # a climb is green, a drop is the logo's red
CHIP_X0, CHIP_X1 = 70, 290                           # the move's chip, on the left of the row
ROW_MAX_H = 250
CREST_X = W - 150                                    # clear of the Reels button column


def events_for(day, data=None):
    """The movers events of the round that ended the day before `day`."""
    import story_events as SE
    import story_social as SS
    d = data or SE.load_data()
    return SS.round_movers(d.get("matches"), d.get("fixtures"), d.get("standings"), day)


def _places(n):
    n = abs(int(n))
    return "مركز" if n == 1 else "مركزين" if n == 2 else f"{n} مراكز" if n <= 10 else f"{n} مركزًا"


def build(ev):
    """The scenes as (draw(t) -> frame, seconds, push_in)."""
    from site_lib.names import comp_label
    bg = R.background()
    mctx = M.context({"home": {"name": ""}, "away": {"name": ""}})
    label = comp_label(ev["competition"])
    moves = ev["moves"]

    def head(im, sub):
        R.logo_at(im, W / 2, DR.HEAD_LOGO_Y, DR.HEAD_LOGO_H)
        d = ImageDraw.Draw(im)
        C.draw_center(d, W / 2, DR.TITLE_Y, C.ar(sub), C.fit(d, C.ar(sub), "ExtraBold", 44, W - 160, 28), C.WHITE)

    def intro(t):
        im = bg.copy()
        M.header(im)
        M.big_at(im, t, "حركة الجدول", 600, 150)
        M.lines_block(im, t, [label, f"بعد الجولة {ev['round']}"], (880, 975), weight="ExtraBold", size=60, t0=0.35)
        return im

    # at most four rows: they may stand taller than a results row
    n = max(1, len(moves))
    h = min(ROW_MAX_H, (DR.BAND_BOTTOM - DR.BAND_TOP) / n)
    top = DR.BAND_TOP + ((DR.BAND_BOTTOM - DR.BAND_TOP) - n * h) / 2
    ys = [top + h * (i + 0.5) for i in range(n)]

    def row(im, t, mv, cy, t0):
        e = M.ease(t, t0, M.FADE + 0.1)
        if e <= 0:
            return
        up = mv["after"] < mv["before"]
        col = UP if up else DOWN
        lay = M.layer()
        d = ImageDraw.Draw(lay)
        d.rounded_rectangle((50, cy - h / 2 + 6, W - 50, cy + h / 2 - 6), int(h * 0.2), fill=(255, 255, 255, 26))
        cs = int(min(110, h * 0.64))
        R.crest_at(lay, mv.get("crest"), mv["team"], cs, CREST_X, cy)
        edge = CREST_X - cs / 2 - 18
        nm = C.ar(mv["team"])
        d.text((edge, cy - h * 0.13), nm, font=C.fit(d, nm, "ExtraBold", int(min(50, h * 0.3)), edge - CHIP_X1 - 24, 24),
               fill=C.WHITE, anchor="rm")
        sub = C.ar(f"من المركز {mv['before']} إلى {mv['after']}")
        d.text((edge, cy + h * 0.2), sub, font=C.fit(d, sub, "Bold", int(max(28, min(34, h * 0.19))), edge - CHIP_X1 - 24, 20),
               fill=(255, 255, 255, 220), anchor="rm")
        # the chip: a triangle that points the way, and how many places
        ch = min(104, h * 0.6)
        d.rounded_rectangle((CHIP_X0, cy - ch / 2, CHIP_X1, cy + ch / 2), int(ch * 0.32), fill=col + (255,))
        tx, tw = CHIP_X1 - 62, 22
        tri = ([(tx, cy - tw), (tx - tw, cy + tw * 0.75), (tx + tw, cy + tw * 0.75)] if up
               else [(tx, cy + tw), (tx - tw, cy - tw * 0.75), (tx + tw, cy - tw * 0.75)])
        d.polygon(tri, fill=C.WHITE)
        d.text((CHIP_X0 + 70, cy), str(abs(mv["before"] - mv["after"])), font=C.font("ExtraBold", int(ch * 0.62)),
               fill=C.WHITE, anchor="mm")
        M.put(im, lay, e, dy=M.SLIDE * (1 - e))

    def page(t):
        # THE CLUBS ARE ON THE FIRST FRAME (designer review 2026-11-20: the
        # reel opened on the wordmark, then a title, and the first club came
        # after a second or more). No title shot: the first row stands whole
        # at 0 s and the others follow it.
        im = bg.copy()
        head(im, f"حركة الجدول · {label} · الجولة {ev['round']}")
        for i, mv in enumerate(moves):
            row(im, t, mv, ys[i], -1.0 if i == 0 else 0.35 + i * 0.3)
        return im

    def outro(t):
        return M.scene({"kind": "cta", "secs": OUTRO, "lines": ["تابع صفحة الجون", "حركة الجدول بعد كل جولة"]}, t, mctx)

    return [(page, INTRO + PAGE, True), (outro, OUTRO, False)]


def caption(ev):
    """The event's own text (the lines story_social wrote) with one question."""
    lines = list(ev["lines"]) + ["", "مين فاجئك في الجولة دي؟ قولنا في الكومنتات 👇", "",
                                 f"{ev['link_label']}: {ev['link']}",
                                 " ".join(["#الجون"] + list(ev.get("tags") or []))]
    return "\n".join(lines) + "\n"


def render(ev, out, sheet=None):
    scenes = build(ev)
    secs = sum(s[1] for s in scenes)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    ok = M.encode({"id": f"movers-{ev['ref']}"}, None, out, secs, frame_iter=DR.frames(scenes))
    if sheet:
        M.contact_sheet([draw(dur - 0.05) for draw, dur, _ in scenes], sheet, cols=len(scenes))
    return ok, secs


def _slug(ref):
    import re
    return re.sub(r"[^a-z0-9]+", "-", ref.lower()).strip("-")


REEL_MIN_MOVES = 4      # fewer clubs than this is a CARD: two rows on a quarter of the screen for 12.5 s
                        # was the thinnest reel on the page (designer review 2026-11-20)


def pending(day, data=None):
    """[(ref, event)] of the rounds that ended the day before `day` and have
    no post yet. Raises what the data or the store raises."""
    out = []
    for ev in events_for(day, data):
        ref = f"movers:{ev['ref']}"
        rec = store.get_post(R.KIND, ref)
        if not (rec and rec.get("post_id")):
            out.append((ref, ev))
    return out


def post_card(token, ev, cap):
    """The same moves as a still card (social_card.render_movers)."""
    import fb_post as P
    import social_card as SC
    return P.post_photo(token, SC.render_movers_bytes(ev), cap)


def auto(dry=False, today=None):
    """Claim-then-post, kind 'reel' / 'movers:<ref>': one league a night,
    each round once. Never raises: a social error must not fail the night."""
    from zoneinfo import ZoneInfo
    day = today or datetime.datetime.now(ZoneInfo("Africa/Cairo")).date()
    try:
        todo = pending(day)
    except Exception as e:                                   # noqa: BLE001
        print(f"movers reel: the data or the store cannot be read ({str(e)[:120]}) - next time"); return 0
    if not todo:
        print("movers reel: no round ended yesterday with a move of two places"); return 0
    ref, ev = todo[0]
    token = os.environ.get("FB_PAGE_TOKEN", "").strip()
    cap = caption(ev)
    if dry or not token:
        print(f"movers reel {ref}: would be posted ({'dry run' if dry else 'FB_PAGE_TOKEN not set'})")
        print(cap); return 0
    if not store.claim(R.KIND, ref, title=ev["title"][:80]):
        print(f"movers reel {ref}: already published or held by another run"); return 0
    if len(ev["moves"]) < REEL_MIN_MOVES:
        try:
            pid = post_card(token, ev, cap)
            store.record_post(R.KIND, ref, pid, title=ev["title"][:80])
            print(f"movers {ref}: {len(ev['moves'])} move(s) - published as a card, {pid}")
        except Exception as e:                               # noqa: BLE001
            store.release(R.KIND, ref)
            print(f"movers card {ref} FAILED: {e}")
        return 0
    path = os.path.join(HERE, "media", "reels", f"{_slug(ref)}.mp4")
    try:
        ok, _ = render(ev, path)
        if not ok:
            store.release(R.KIND, ref)
            print(f"movers reel {ref}: no usable encoder, next night"); return 0
        vid = R.post_reel(token, path, cap)
        store.record_post(R.KIND, ref, vid, title=ev["title"][:80])
        print(f"movers reel {ref}: published as {vid}")
    except Exception as e:                                   # noqa: BLE001
        store.release(R.KIND, ref)
        print(f"movers reel {ref} FAILED: {e}")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="YYYY-MM-DD: the day AFTER the round's last match (default: today, Cairo)")
    ap.add_argument("--out")
    ap.add_argument("--sheet")
    ap.add_argument("--auto", action="store_true")
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()
    day = datetime.date.fromisoformat(args.date) if args.date else None
    if args.auto:
        return auto(dry=args.dry, today=day)
    from zoneinfo import ZoneInfo
    evs = events_for(day or datetime.datetime.now(ZoneInfo("Africa/Cairo")).date())
    if not evs:
        print("no round ended the day before with a move of two places - no reel"); return 0
    ev = evs[0]
    out = args.out or os.path.join(HERE, "media", "reels", f"{_slug('movers:' + ev['ref'])}.mp4")
    ok, secs = render(ev, out, args.sheet)
    print(f"{out}: {secs:.1f}s, {'UPLOADABLE' if ok else 'NOT uploadable'}")
    print(caption(ev))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
