# -*- coding: utf-8 -*-
r"""«سباق القمة» - the title race as lines: each of the top clubs' POINTS,
match by match, growing together (a reel, 13 s).

    python race_reel.py --comp "Egyptian Premier League" --out race.mp4 --sheet race.png
    python race_reel.py --auto            # nightly: a league whose round ended (FB_RACE=on)

WHY (designer review 2026-11-20; user: «اعمل 18»): every reel on the page is
a list of rows. Here the motion itself is the story - who pulled away and
when - and it is drawn from nothing but our own finished results.

WHAT IS DRAWN, and why it cannot be wrong:
  * POINTS, never positions: a position needs tie-breakers we do not hold; a
    side's points after its k-th match is three for a win and one for a draw.
  * the x axis is each side's OWN matches (1st, 2nd, ...), not rounds: a
    postponed match moves no line to the wrong place.
  * only when our count of every drawn club's matches and points EQUALS the
    table's own «لعب» and «نقاط» - otherwise there is no reel (series() -> None).
The clubs are the table's top RACE_N. Each line is the club's own colour
(match_poster.own_colours) on a white under-stroke, its crest riding the end.

The first frame is whole (the designer's rule of the same day): the heading,
the four clubs with their points as the table has them, and the axes; the
lines then grow. 10 s + the 3 s closing shot = 13 s (the 15 s rule).

Behind its own switch, FB_RACE, and at most once every RACE_EVERY rounds of a
league: a new kind, read before it is live.
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
PAGE, OUTRO = 10.0, 3.0                              # 13 s
RACE_N = 4                                           # the table's top clubs drawn
RACE_MIN_GAMES = 5                                   # fewer matches than this is not a race yet
RACE_EVERY = 3                                       # a league gets the reel once every N rounds
GROW_FROM, GROW_FOR = 0.6, 7.2                       # when the lines start and how long they take
# the chart's box, inside the Reels safe band and clear of the button column
X0, X1 = 150, W - 170
Y0, Y1 = 760, DR.BAND_BOTTOM - 40
LEG_TOP, LEG_H = 380, 84                             # the four clubs with their points, over the chart


def season_start(today=None):
    d = today or datetime.date.today()
    return f"{d.year if d.month >= 7 else d.year - 1}-07-01"


def series(comp, pool, table, n=RACE_N, today=None):
    """[{team, crest, points: [after match 1, 2, ...], pts}] for the table's
    top n clubs, or None when a count of ours disagrees with the table's."""
    from site_lib.tables import team_key, team_results
    start = season_start(today)
    games = [m for m in pool or [] if m.get("competition") == comp and str(m.get("kickoff") or "") >= start]
    res = team_results(games)
    out = []
    for r in (table or [])[:n]:
        mine = res.get(team_key(r.get("team"))) or []
        pts, acc = [], 0
        for _, x in mine:
            acc += 3 if x == "w" else 1 if x == "d" else 0
            pts.append(acc)
        if len(mine) != int(r.get("played") or 0) or acc != int(r.get("pts") or 0):
            return None                  # we do not hold what the table holds: no chart
        if len(pts) < RACE_MIN_GAMES:
            return None
        out.append({"team": r.get("team"), "crest": r.get("crest"), "points": pts, "pts": acc,
                    "pos": r.get("pos")})
    return out if len(out) >= 3 else None


def line_colour(team, comp=None):
    """The club's own colour for its line (our KITS table / the neutral grey)."""
    import match_poster as MP
    import matchup_card as MC
    from site_lib.names import ar_team
    cols = MP.own_colours(MC.kit_for(ar_team(team), comp))
    return next((c for c in cols if 120 < sum(c) < 700), cols[0])


def build(comp, rows, round_no=None):
    """The scenes as (draw(t) -> frame, seconds, push_in)."""
    from site_lib.names import ar_team, comp_label
    bg = R.background()
    mctx = M.context({"home": {"name": ""}, "away": {"name": ""}})
    label = comp_label(comp)
    games = max(len(r["points"]) for r in rows)
    top = max(r["pts"] for r in rows)
    ymax = max(3, ((top + 2) // 3) * 3)
    cols = [line_colour(r["team"], comp) for r in rows]

    def px(i):                       # the i-th match (1-based, fractional while growing)
        return X0 + (X1 - X0) * (i - 1) / max(1, games - 1)

    def py(p):
        return Y1 - (Y1 - Y0) * p / ymax

    def at(r, i):
        """A side's points at fractional match index i (straight between two matches)."""
        pts = r["points"]
        i = max(1.0, min(float(len(pts)), i))
        lo = int(i)
        if lo >= len(pts):
            return float(pts[-1])
        return pts[lo - 1] + (pts[lo] - pts[lo - 1]) * (i - lo)

    def page(t):
        im = bg.copy()
        R.logo_at(im, W / 2, DR.HEAD_LOGO_Y, DR.HEAD_LOGO_H)
        d = ImageDraw.Draw(im)
        head = f"سباق القمة · {label}" + (f" · بعد الجولة {round_no}" if round_no else "")
        C.draw_center(d, W / 2, DR.TITLE_Y, C.ar(head), C.fit(d, C.ar(head), "ExtraBold", 46, W - 160, 28), C.WHITE)
        lay = M.layer()
        ld = ImageDraw.Draw(lay)
        # the four clubs and their points as the table has them: whole from 0 s
        cw = (W - 100) / len(rows)
        for k, r in enumerate(rows):
            cx = W - 50 - cw * (k + 0.5)                         # the leader on the right
            ld.rounded_rectangle((cx - cw / 2 + 8, LEG_TOP, cx + cw / 2 - 8, LEG_TOP + 250), 26, fill=(255, 255, 255, 30))
            ld.rounded_rectangle((cx - cw / 2 + 8, LEG_TOP, cx + cw / 2 - 8, LEG_TOP + 16), 8, fill=cols[k] + (255,),
                                 outline=(12, 30, 66, 255), width=3)
            R.crest_at(lay, r.get("crest"), ar_team(r["team"]), LEG_H, cx, LEG_TOP + 74)
            nm = C.ar(ar_team(r["team"]))
            ld.text((cx, LEG_TOP + 150), nm, font=C.fit(ld, nm, "ExtraBold", 34, cw - 30, 20), fill=C.WHITE, anchor="mm")
            pt = C.ar(f"{r['pts']} نقطة")
            ld.text((cx, LEG_TOP + 206), pt, font=C.font("Bold", 30), fill=(255, 255, 255, 230), anchor="mm")
        # the axes: a line every three points, the matches' numbers under
        for p in range(0, ymax + 1, 3 if ymax <= 30 else 6):
            y = py(p)
            ld.line([(X0, y), (X1, y)], fill=(255, 255, 255, 46), width=2)
            ld.text((X0 - 22, y), str(p), font=C.font("Bold", 28), fill=(255, 255, 255, 215), anchor="rm")
        step = 1 if games <= 12 else 2 if games <= 24 else 5
        for g in range(1, games + 1):
            if g == 1 or g == games or g % step == 0:
                ld.text((px(g), Y1 + 34), str(g), font=C.font("Bold", 26), fill=(255, 255, 255, 215), anchor="mm")
        cap = C.ar("النقاط بعد كل مباراة")
        ld.text((W / 2, Y1 + 84), cap, font=C.font("Bold", 30), fill=(255, 255, 255, 225), anchor="mm")
        im.alpha_composite(lay) if im.mode == "RGBA" else im.paste(lay, (0, 0), lay)
        # the lines, growing together
        e = M.ease(t, GROW_FROM, GROW_FOR)
        upto = 1 + (games - 1) * e
        lay2 = M.layer()
        d2 = ImageDraw.Draw(lay2)
        heads = []
        for k, r in enumerate(rows):
            end = min(upto, float(len(r["points"])))
            pts = [(px(1), py(at(r, 1)))]
            g = 2
            while g <= int(end):
                pts.append((px(g), py(r["points"][g - 1])))
                g += 1
            if end > int(end):
                pts.append((px(end), py(at(r, end))))
            if len(pts) > 1:
                # a DARK under-stroke: a light-blue club's line on a white one
                # read as a hollow white line on this background
                d2.line(pts, fill=(12, 30, 66, 255), width=18, joint="curve")
                d2.line(pts, fill=cols[k] + (255,), width=11, joint="curve")
            heads.append((pts[-1], r))
        # crests ride the ends; the leader is drawn last, on top
        for (x, y), r in reversed(heads):
            d2.ellipse((x - 40, y - 40, x + 40, y + 40), fill=(255, 255, 255, 255))
            R.crest_at(lay2, r.get("crest"), ar_team(r["team"]), 62, x, y)
        im.paste(lay2, (0, 0), lay2)
        return im

    def outro(t):
        return M.scene({"kind": "cta", "secs": OUTRO, "lines": ["تابع صفحة الجون", "سباق القمة بعد كل جولة"]}, t, mctx)

    return [(page, PAGE, True), (outro, OUTRO, False)]


def caption(comp, rows, round_no=None):
    from site_lib.competitions import COMP_SLUG
    from site_lib.names import ar_team, comp_label
    label = comp_label(comp)
    lines = [f"📈 سباق القمة في {label}" + (f" بعد الجولة {round_no}" if round_no else "") + ":", ""]
    for r in rows:
        n = len(r["points"])
        lines.append(f"{r['pos']}. {ar_team(r['team'])}: {r['pts']} نقطة من {n} " + ("مباريات" if 3 <= n <= 10 else "مباراة"))
    slug = COMP_SLUG.get(comp)
    lines += ["", "مين هيكسب السباق في رأيك؟ قولنا في الكومنتات 👇", "",
              "تابع الصفحة: النتائج كل ليلة والمباريات كل صباح.",
              f"الجدول كاملًا: https://elgoon.com/standings/{slug}" if slug else "الجدول كاملًا: https://elgoon.com/",
              f"#الجون #{label.replace(' ', '_')}"]
    return "\n".join(lines) + "\n"


def render(comp, rows, out, sheet=None, round_no=None):
    scenes = build(comp, rows, round_no)
    secs = sum(s[1] for s in scenes)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    ok = M.encode({"id": f"race-{comp}"}, None, out, secs, frame_iter=DR.frames(scenes))
    if sheet:
        M.contact_sheet([scenes[0][0](0.0), scenes[0][0](PAGE / 2), scenes[0][0](PAGE - 0.05)], sheet, cols=3)
    return ok, secs


def load(comp, today=None):
    """(rows or None) for one competition from the data files."""
    import story_events as SE
    d = SE.load_data()
    st = next((s for s in d.get("standings") or [] if s.get("competition") == comp), None)
    if not st or not st.get("table") or st.get("zeroed") or st.get("past"):
        return None
    pool = SE.results_pool(d.get("matches"), d.get("archive"))
    # the top four; the top three when the fourth's count is not the table's
    # (a match the table has not taken in yet) - never a club we cannot count
    return series(comp, pool, st["table"], RACE_N, today) or series(comp, pool, st["table"], 3, today)


def armed():
    return (os.environ.get("FB_RACE", "") or "").strip().lower() == "on"


def auto(dry=False, today=None):
    """One league whose round ended yesterday and whose round number is a
    multiple of RACE_EVERY; kind 'reel' / 'race:<competition>:R<n>'. Never
    raises: a social error must not fail the night."""
    import movers_reel as MV
    from zoneinfo import ZoneInfo
    day = today or datetime.datetime.now(ZoneInfo("Africa/Cairo")).date()
    try:
        import story_events as SE
        import story_social as SS
        d = SE.load_data()
        ended = SS.rounds_ended(d.get("matches"), d.get("fixtures"), day) if hasattr(SS, "rounds_ended") else \
            [(ev["competition"], ev["round"]) for ev in MV.events_for(day, d)]
    except Exception as e:                                   # noqa: BLE001
        print(f"race reel: the data cannot be read ({str(e)[:120]}) - next night"); return 0
    for comp, rnd in ended:
        try:
            if int(rnd) % RACE_EVERY:
                continue
        except (TypeError, ValueError):
            continue
        rows = load(comp, day)
        if not rows:
            print(f"race reel {comp} R{rnd}: our counts do not equal the table's - no reel"); continue
        ref = f"race:{comp}:R{rnd}"
        rec = store.get_post(R.KIND, ref)
        if rec and rec.get("post_id"):
            continue
        cap = caption(comp, rows, rnd)
        token = os.environ.get("FB_PAGE_TOKEN", "").strip()
        if dry or not token or not armed():
            why = "dry run" if dry else "FB_RACE is not on" if not armed() else "FB_PAGE_TOKEN not set"
            print(f"race reel {ref}: would be posted ({why})"); print(cap); return 0
        if not store.claim(R.KIND, ref, title=f"race {comp} R{rnd}"):
            return 0
        path = os.path.join(HERE, "media", "reels", f"{MV._slug(ref)}.mp4")
        try:
            ok, _ = render(comp, rows, path, round_no=rnd)
            if not ok:
                store.release(R.KIND, ref); print(f"race reel {ref}: no usable encoder, next night"); return 0
            vid = R.post_reel(token, path, cap)
            store.record_post(R.KIND, ref, vid, title=f"race {comp} R{rnd}")
            print(f"race reel {ref}: published as {vid}")
        except Exception as e:                               # noqa: BLE001
            store.release(R.KIND, ref)
            print(f"race reel {ref} FAILED: {e}")
        return 0
    print("race reel: no league reached a round to draw"); return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--comp", help="a competition as the data spells it, e.g. \"Egyptian Premier League\"")
    ap.add_argument("--round", type=int)
    ap.add_argument("--out")
    ap.add_argument("--sheet")
    ap.add_argument("--auto", action="store_true")
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()
    if args.auto:
        return auto(dry=args.dry)
    comp = args.comp or "Egyptian Premier League"
    rows = load(comp)
    if not rows:
        print(f"{comp}: our counts do not equal the table's, or too few matches - no reel"); return 0
    out = args.out or os.path.join(HERE, "media", "reels", "race-preview.mp4")
    ok, secs = render(comp, rows, out, args.sheet, args.round)
    print(f"{out}: {secs:.1f}s, {'UPLOADABLE' if ok else 'NOT uploadable'}")
    print(caption(comp, rows, args.round))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
