#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The SCORERS RACE as a vertical reel (2026-11-10, picked by the user from
the new reel ideas): a league's top five scorers as horizontal bars that
grow from the right (RTL) together with a counter, then hold.

    intro 2 s   the wordmark, «سباق الهدافين», the league, «بعد الجولة» + N
    race  9 s   five rows: rank, the player's photo in a disc (his club's
                crest when the feed only has its default silhouette), the
                name, the club's crest + name, the bar and the counter at its
                tip. The leader's bar gold, the others white. Equal goals =
                equal rank and equal length; when a tie at the cut-off has
                more players than rows left, the whole group becomes ONE row
                («لاعبون متساوون» + their small discs) - nobody is picked.
    outro 3 s   the wordmark + elgoon.com (moment_reel's cta scene)

data/scorers.json (results[0].items[] -> competition, scorers[]) for the
players, data/standings.json for the round (the table_reel rule: the most
matches any club has played). Same canvas, safe band, music and encoder as
table_reel / day_reel / moment_reel. 14 s - under the 15 s rule.

    python scorers_reel.py --comp "Premier League" --out s.mp4 --sheet s.png --caption s.txt
    python scorers_reel.py --comp "Primera Division" --png frames/       # stills, no ffmpeg
    python scorers_reel.py --auto [--dry]     # nightly: the leagues whose round just ended
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from PIL import Image, ImageDraw     # noqa: E402

import day_reel as D                 # noqa: E402
import fb_cards as C                 # noqa: E402
import fb_reel as R                  # noqa: E402
import moment_reel as M              # noqa: E402

W, H, FPS = M.W, M.H, M.FPS
ROWS = 5
INTRO, RACE, OUTRO = 2.0, 9.0, 3.0
GROW_T0, GROW = 0.9, 4.6             # the bars grow 0.9 s .. 5.5 s, then hold 3.5 s
ROW_TOP, ROW_H, ROW_HALF = 590, 186, 80     # centres 590..1334; last row ends 1414 (1435 after the push-in) < SAFE_BOTTOM
PANEL_R = 978                        # row panels stop left of the Reels button column (0.91 W = 983)
X_RANK, X_DISC, DISC = 925, 828, 124
X_R = 742                            # right edge of the name / club line / bar start
BAR_MAX = 552                        # the leader's bar: 742 -> 190, its number at 174 and leftwards
BAR_H = 34
SMALL = 52                           # the faces inside a tied group's row
GROUP_FACES = 8
WHITE_BAR = (255, 255, 255)
TRACK = (255, 255, 255, 34)

_ATH = re.compile(r"/v(\d+)/Athletes/(\d+)")


# ---------------------------------------------------------------- data
def scorers_for(comp, path=None):
    d = json.load(open(path or os.path.join(HERE, "data", "scorers.json"), encoding="utf-8"))
    for block in d.get("results") or []:
        for it in block.get("items") or []:
            if it.get("competition") == comp and it.get("scorers"):
                return [clean(s) for s in it["scorers"]]
    raise SystemExit(f"no scorers for {comp!r} in scorers.json")


def clean(s):
    """The feed's names carry stray spaces («كيليان مبابي ») - strip them."""
    out = dict(s)
    out["name"] = " ".join((s.get("name") or "").split())
    out["team"] = " ".join((s.get("team") or "").split())
    out["goals"] = int(s.get("goals") or 0)
    out["played"] = int(s.get("played") or 0)
    return out


def round_for(comp, path=None):
    """The round from the table (the most matches any club has played)."""
    import table_reel as T
    try:
        table = T.table_for(comp, path)
    except SystemExit:
        return None
    n = max(int(r.get("played") or 0) for r in table)
    return n or None


def ranked(scorers):
    """Competition ranking: equal goals share a rank (1, 2, 3, 3, 5)."""
    out = []
    for s in scorers:
        r = dict(s)
        r["rank"] = 1 + sum(1 for o in scorers if o["goals"] > s["goals"])
        out.append(r)
    return sorted(out, key=lambda r: r["rank"])


def rows_for(scorers, n=ROWS):
    """At most n rows. A tie group that fits is shown player by player; one
    that does not becomes a single group row, so no order is invented.
    `more` marks a group that reaches the end of the feed's list (there may
    be more players on the same goals than the feed returns)."""
    rs = ranked(scorers)
    groups = []
    for r in rs:
        if groups and groups[-1][0]["goals"] == r["goals"]:
            groups[-1].append(r)
        else:
            groups.append([r])
    rows, used = [], 0
    for g in groups:
        left = n - used
        if left <= 0:
            break
        if len(g) <= left:
            rows += [dict(r, group=None) for r in g]
            used += len(g)
        else:
            rows.append({"rank": g[0]["rank"], "goals": g[0]["goals"], "group": g,
                         "more": rs.index(g[-1]) == len(rs) - 1})
            break
    return rows


def athlete(photo):
    m = _ATH.search(photo or "")
    return (int(m.group(2)), int(m.group(1))) if m else (None, None)


def shots_for(scorers, size=DISC):
    """{athlete id: RGBA photo disc} for the players 365scores has a REAL
    photo of - lineup_card.headshots drops the default silhouette (fetched
    under athlete 0 and compared byte for byte); those players get their
    club's crest instead."""
    import lineup_card as L
    players = []
    for s in scorers:
        aid, v = athlete(s.get("photo"))
        if aid:
            players.append({"athlete": aid, "img_v": v})
    try:
        return L.headshots(players, size)
    except Exception:                                   # noqa: BLE001
        return {}


_disc = {}


def disc(s, shots, size):
    """The player's photo disc, or (no real photo) a white disc with his
    club's crest - never the silhouette. Returns (RGBA, 'photo'|'crest')."""
    aid, _ = athlete(s.get("photo"))
    key = (aid, s.get("crest"), size)
    if key in _disc:
        return _disc[key]
    if aid in shots:
        im = shots[aid]
        if im.width != size:
            im = im.resize((size, size), Image.LANCZOS)
        out = (im, "photo")
    else:
        im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        ImageDraw.Draw(im).ellipse((0, 0, size - 1, size - 1), fill=C.WHITE)
        inner = int(size * 0.68)
        url = s.get("crest")
        cr = C.crest_image(R.big_badge(url), inner) or C.crest_image(url, inner)
        cr = R.fill_box(cr, inner) if cr else C.crest_placeholder(s.get("team"), inner)
        im.paste(cr, ((size - inner) // 2, (size - inner) // 2), cr)
        out = (im, "crest")
    _disc[key] = out
    return out


# ---------------------------------------------------------------- the race
def progress(t):
    """0..1 of the leader's goals at race time t (smooth start and finish)."""
    return M.ease(t, GROW_T0, GROW)


def value_at(goals, maxg, t):
    """Every bar grows at the same goals-per-second; a bar stops at its own
    total, so the leader finishes last and equal totals stay equal."""
    return min(float(goals), maxg * progress(t))


def bar_px(goals, maxg, t=None):
    v = goals if t is None else value_at(goals, maxg, t)
    return BAR_MAX * v / maxg if maxg else 0


def finish_t(goals, maxg):
    """When a bar reaches its total (bisection on the smooth progress)."""
    lo, hi = GROW_T0, GROW_T0 + GROW
    want = goals / maxg if maxg else 1
    for _ in range(30):
        mid = (lo + hi) / 2
        if progress(mid) < want:
            lo = mid
        else:
            hi = mid
    return hi


def ring_disc(lay, im, cx, cy, ring):
    d = ImageDraw.Draw(lay)
    r = im.width / 2 + 5
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=ring)
    lay.paste(im, (int(cx - im.width / 2), int(cy - im.height / 2)), im)


def num_at_tip(d, tip, cy, n, scale, fill):
    f = C.font("ExtraBold", int(62 * scale))
    s = str(n)
    bx = d.textbbox((0, 0), s, font=f)
    d.text((tip - 16 - bx[2], cy - (bx[1] + bx[3]) / 2), s, font=f, fill=fill)


def row(im, t, r, cy, t0, maxg, shots):
    e = M.ease(t, t0, M.FADE)
    if e <= 0:
        return
    lead = r["rank"] == 1
    col = M.GOLD if lead else WHITE_BAR
    lay = M.layer()
    d = ImageDraw.Draw(lay)
    d.rounded_rectangle((60, cy - ROW_HALF, PANEL_R, cy + ROW_HALF), 30, fill=(255, 255, 255, 22))
    C.draw_center(d, X_RANK, cy - 34, str(r["rank"]), C.font("ExtraBold", 50), M.GOLD if lead else C.WHITE)
    by = cy + 44                                        # the bar's centre line
    if r["group"] is None:
        im_d, _ = disc(r, shots, DISC)
        ring_disc(lay, im_d, X_DISC, cy, M.GOLD if lead else C.WHITE)
        nm = C.ar(r["name"])
        f = C.fit(d, nm, "ExtraBold", 42, X_R - 120, 26)
        d.text((X_R - C.text_w(d, nm, f), cy - 78), nm, font=f, fill=C.WHITE)
        # the club: its crest right, its name left of it, small
        R.crest_at(lay, r.get("crest"), r["team"], 40, X_R - 20, cy - 4)
        tm = C.ar(r["team"])
        ft = C.fit(d, tm, "Bold", 30, X_R - 50 - 140, 20)
        d.text((X_R - 50 - C.text_w(d, tm, ft), cy - 24), tm, font=ft, fill=M.SOFT)
    else:
        # a tie at the cut-off: «=» in the disc slot, the players' faces on the
        # name line (right to left, the feed's order), the label in the club slot
        d.ellipse((X_DISC - DISC / 2 - 5, cy - DISC / 2 - 5, X_DISC + DISC / 2 + 5, cy + DISC / 2 + 5), fill=C.WHITE)
        C.draw_center(d, X_DISC, cy - 58, "=", C.font("ExtraBold", 96), C.BLUE)
        x = X_R - SMALL / 2
        for s in r["group"][:GROUP_FACES]:
            im_s, _ = disc(s, shots, SMALL)
            ring_disc(lay, im_s, x, cy - 50, C.WHITE)
            x -= SMALL + 4
        if r["more"] or len(r["group"]) > GROUP_FACES:
            C.draw_center(d, x + SMALL / 2 - 8, cy - 78, "+", C.font("ExtraBold", 40), C.WHITE)
        lb = C.ar("لاعبون متساوون")
        fl = C.font("Bold", 30)
        d.text((X_R - C.text_w(d, lb, fl), cy - 24), lb, font=fl, fill=M.SOFT)
    # the track, the bar, the counter at its tip
    d.rounded_rectangle((X_R - BAR_MAX, by - BAR_H / 2, X_R, by + BAR_H / 2), BAR_H // 2, fill=TRACK)
    ln = bar_px(r["goals"], maxg, t)
    if ln > 1:
        d.rounded_rectangle((X_R - max(ln, BAR_H), by - BAR_H / 2, X_R, by + BAR_H / 2), BAR_H // 2, fill=col)
    v = value_at(r["goals"], maxg, t)
    tf = finish_t(r["goals"], maxg)
    scale = 1.0
    if t >= tf:
        scale = 1 + 0.22 * (1 - M.ease(t, tf, 0.28))   # a small pop when the bar lands
    num_at_tip(d, X_R - max(ln, BAR_H), by - 4, int(v + 1e-6), scale, col)
    M.put(im, lay, e, dx=M.SLIDE * (1 - e))             # slides in from the left, the bars' direction


def pair_line(lay, cy, text, num, weight, size, fill):
    """Arabic words and a number in their OWN slots (the number on the
    left, where an RTL sentence ends) - no digits through the bidi pass."""
    d = ImageDraw.Draw(lay)
    s = C.ar(text)
    f = C.font(weight, size)
    tw, nw, gap = C.text_w(d, s, f), C.text_w(d, str(num), f), size * 0.35
    x0 = W / 2 - (tw + gap + nw) / 2
    d.text((x0 + nw + gap, cy), s, font=f, fill=fill)
    d.text((x0, cy), str(num), font=f, fill=fill)


def build(scorers, comp, label, rnd=None, shots=None):
    bg = R.background()
    ctx = M.context({"home": {"name": ""}, "away": {"name": ""}})
    rows = rows_for(scorers)
    maxg = max(r["goals"] for r in rows) if rows else 1
    shots = shots if shots is not None else shots_for(
        [s for r in rows for s in (r["group"] or [r])])

    def intro(t):
        im = bg.copy()
        M.header(im)
        M.big_at(im, t, "سباق الهدافين", 600, 150)
        M.lines_block(im, t, [label], (880,), weight="ExtraBold", size=64, t0=0.35)
        if rnd:
            e = M.ease(t, 0.35 + M.STAGGER, M.FADE)
            if e > 0:
                lay = M.layer()
                pair_line(lay, 975, "بعد الجولة", rnd, "Bold", 52, M.SOFT)
                M.put(im, lay, e, dy=M.SLIDE * (1 - e))
        return im

    def race(t):
        im = bg.copy()
        M.header(im)
        d = ImageDraw.Draw(im)
        C.draw_center(d, W / 2, 425, C.ar(f"هدافو {label}"), C.font("ExtraBold", 44), C.WHITE)
        for i, r in enumerate(rows):
            row(im, t, r, ROW_TOP + i * ROW_H, 0.1 + i * 0.12, maxg, shots)
        return im

    def outro(t):
        sc = {"kind": "cta", "secs": OUTRO, "lines": ["ترتيب الهدافين كامل", "لحظة بلحظة على الجون"]}
        return M.scene(sc, t, ctx)

    return [(intro, INTRO, True), (race, RACE, True), (outro, OUTRO, False)]


# ---------------------------------------------------------------- caption
def goals_word(n):
    if n == 1:
        return "هدف واحد"
    if n == 2:
        return "هدفين"
    return f"{n} أهداف" if 3 <= n <= 10 else f"{n} هدفًا"


def caption(scorers, comp, label, rnd=None):
    from site_lib.competitions import COMP_SLUG
    rs = ranked(scorers)
    top = [r for r in rs if r["rank"] == 1]
    g = top[0]["goals"]
    if len(top) == 1:
        hook = f"⚽ {top[0]['name']} يتصدر هدافي {label} برصيد {goals_word(g)}"
    else:
        hook = f"⚽ {' و'.join(r['name'] for r in top)} يتقاسمون صدارة هدافي {label} برصيد {goals_word(g)}"
    lines = [hook + (f" بعد الجولة {rnd}" if rnd else ""), ""]
    for r in [r for r in rs if r["rank"] <= 3]:
        lines.append(f"{r['rank']}. {r['name']} ({r['team']}) - {goals_word(r['goals'])}")
    lines += ["", "مين هيكسب لقب الهداف في الآخر؟ قولنا في الكومنتات 👇", ""]
    slug = COMP_SLUG.get(comp)
    lines.append(f"ترتيب الهدافين كامل: https://elgoon.com/scorers/{slug}.html" if slug else "https://elgoon.com")
    tag = label.replace(" ", "_")
    lines.append(f"#الجون #هدافي_{tag} #{tag} #سباق_الهدافين")
    return "\n".join(lines) + "\n"



# ---------------------------------------------------------------- automation
# User, 2026-11-10: «أتمتها» - the race goes out on its own after every round
# of these three leagues. fb-post.yml runs `--auto` in the nightly daycard job
# (after the results card and the day reel), the same night the round's last
# match is in the data, or the next night for a late kick-off.
AUTO_COMPS = ("Premier League", "Egyptian Premier League", "Primera Division")
DONE = {"FINISHED", "AWARDED"}
SKIPPED = {"POSTPONED", "CANCELLED", "CANCELED", "SUSPENDED", "ABANDONED"}
FRESH_H = 144                # a round older than this is not news any more; 6 days because
                             # three leagues ending one weekend go out one a night and a
                             # late kick-off waits for the next night's run (the first
                             # run, 11-12, had La Liga R12 owed at 122 h). The next round
                             # starting retires a round anyway (round_done).
MAX_PER_RUN = 1              # three leagues ending one weekend = three nights, not one burst
# Reels the user uploaded BY HAND, so the automation must not post them again.
# The store only knows what this script posted; add a round's ref here when he
# posts one himself. 2026-11-11: the 11-10 renders of these two («انا نزلتهم
# الانجليزي والاسباني فمتنزلش انت المرة دي»).
HAND_POSTED = {
    "scorers:Premier League:2026-27:R10",
    "scorers:Primera Division:2026-27:R12",
}


def _kickoff(m):
    import datetime
    try:
        return datetime.datetime.fromisoformat(
            f"{m['kickoff']}T{m.get('koff_time') or '00:00'}:00").replace(tzinfo=C.CAIRO)
    except Exception:                                        # noqa: BLE001
        return None


def season_matches(comp, now, matches=None):
    """This season's matches of `comp`, archive + current, one per match_id."""
    import build_site as b
    import story_events as SE
    if matches is None:
        matches = b.load("matches_archive.json") + b.load("matches.json")
    season = SE.season_of(now.date().isoformat())
    seen, out = set(), []
    for m in matches:
        mid = str(m.get("match_id") or "")
        if not mid or mid in seen or m.get("competition") != comp:
            continue
        seen.add(mid)
        if isinstance(m.get("round"), int) and SE.season_of(m.get("kickoff")) == season:
            out.append(m)
    return out


def round_done(ms, now, need=None):
    """(round, last kick-off) when the LATEST round with a finished match is
    complete - every match finished or postponed - and ended inside FRESH_H;
    else None. Only the latest round counts: a postponed match from an old
    round, played weeks later, must not bring that round back. `need` = the
    matches a full round has (clubs // 2): the feed lists a round's fixtures
    only as they are scheduled, so six finished matches of an eleven-match
    round are not a finished round."""
    fin = [m for m in ms if (m.get("status") or "") in DONE]
    if not fin:
        return None
    rnd = max(m["round"] for m in fin)
    this = [m for m in ms if m["round"] == rnd]
    if need and len(this) < need:
        return None
    if any((m.get("status") or "") not in DONE | SKIPPED for m in this):
        return None
    kos = [k for k in (_kickoff(m) for m in this if (m.get("status") or "") in DONE) if k]
    if not kos:
        return None
    last = max(kos)
    if last > now or (now - last).total_seconds() > FRESH_H * 3600:
        return None
    return rnd, last


def round_size(comp, path=None):
    """Matches in a full round: half the clubs in the table (None = unknown)."""
    import table_reel as T
    try:
        return len(T.table_for(comp, path)) // 2 or None
    except SystemExit:
        return None


def ref_for(comp, now, rnd):
    import story_events as SE
    return f"scorers:{comp}:{SE.season_of(now.date().isoformat())}:R{rnd}"


def due(now=None, matches=None, posted=None):
    """[(comp, round, ref)] whose reel is owed, oldest round first.
    `posted(ref)` -> True when the store already has that reel."""
    import datetime
    now = now or datetime.datetime.now(C.CAIRO)
    out = []
    for comp in AUTO_COMPS:
        rd = round_done(season_matches(comp, now, matches), now, round_size(comp))
        if not rd:
            continue
        rnd, last = rd
        tab = round_for(comp)
        if tab and tab < rnd:
            print(f"scorers reel {comp} R{rnd}: the table still says R{tab} - the data lags, next night")
            continue
        ref = ref_for(comp, now, rnd)
        if posted and posted(ref):
            continue
        out.append((last, comp, rnd, ref))
    return [(c, r, ref) for _, c, r, ref in sorted(out)]


def _posted(ref):
    if ref in HAND_POSTED:
        return True
    import store
    rec = store.get_post(R.KIND, ref)
    return bool(rec and rec.get("post_id"))


def auto(dry=False, out_dir=None):
    """Claim-then-post, kind 'reel' / 'scorers:<comp>:<season>:R<n>' - one
    reel per league per round, ever. Never raises; a social error must not
    fail the nightly job."""
    import store
    from site_lib.names import comp_label
    try:
        todo = due(posted=_posted)
    except Exception as e:                                   # noqa: BLE001
        print(f"scorers reel: the store cannot be read ({str(e)[:120]}) - next night")
        return 0
    if not todo:
        print("scorers reel: no round finished since the last one")
        return 0
    token = os.environ.get("FB_PAGE_TOKEN", "").strip()
    out_dir = out_dir or os.path.join(HERE, "media", "reels")
    os.makedirs(out_dir, exist_ok=True)
    for comp, rnd, ref in todo[:MAX_PER_RUN]:
        label = comp_label(comp)
        try:
            scorers = scorers_for(comp)
        except SystemExit:
            scorers = []
        if not scorers:
            print(f"scorers reel {comp} R{rnd}: no scorers in the data")
            continue
        cap = caption(scorers, comp, label, rnd)
        if dry or not token:
            print(f"scorers reel {comp} R{rnd}: would be posted ({'dry run' if dry else 'FB_PAGE_TOKEN not set'})")
            print(cap)
            continue
        if not store.claim(R.KIND, ref, title=f"scorers {label} R{rnd}"):
            print(f"scorers reel {comp} R{rnd}: already published or held by another run")
            continue
        path = os.path.join(out_dir, f"scorers-{re.sub(r'[^a-z0-9]+', '-', comp.lower())}-R{rnd}.mp4")
        try:
            scenes = build(scorers, comp, label, rnd)
            secs = sum(x[1] for x in scenes)
            if not M.encode({"id": ref}, None, path, secs, frame_iter=D.frames(scenes)):
                store.release(R.KIND, ref)
                print(f"scorers reel {comp} R{rnd}: no usable encoder, next night")
                continue
            vid = R.post_reel(token, path, cap)
            store.record_post(R.KIND, ref, vid, title=f"scorers {label} R{rnd}")
            print(f"scorers reel {comp} R{rnd}: published as {vid}")
        except Exception as e:                               # noqa: BLE001
            store.release(R.KIND, ref)
            print(f"scorers reel {comp} R{rnd} FAILED: {e}")
    if len(todo) > MAX_PER_RUN:
        print(f"scorers reel: {len(todo) - MAX_PER_RUN} more league(s) owed - one a night")
    return 0


# ---------------------------------------------------------------- main
def main():
    from site_lib.names import comp_label
    ap = argparse.ArgumentParser()
    ap.add_argument("--comp", default="Premier League", help="the competition name in scorers.json")
    ap.add_argument("--out", help="the MP4")
    ap.add_argument("--sheet", help="also write a contact sheet PNG")
    ap.add_argument("--caption", help="write the post text here (default <out>-caption.txt)")
    ap.add_argument("--png", help="write stills (intro, race mid/end, outro) into this folder, no MP4")
    ap.add_argument("--auto", action="store_true", help="post the reel of every league whose round just ended (fb-post.yml, nightly)")
    ap.add_argument("--dry", action="store_true", help="with --auto: say what would be posted")
    args = ap.parse_args()
    if args.auto:
        return auto(dry=args.dry)
    scorers = scorers_for(args.comp)
    label = comp_label(args.comp)
    rnd = round_for(args.comp)
    scenes = build(scorers, args.comp, label, rnd)
    secs = sum(s[1] for s in scenes)
    intro, race, outro = (s[0] for s in scenes)
    stills = [("1-intro", intro(INTRO - 0.05)), ("2-race-mid", race(GROW_T0 + GROW * 0.45)),
              ("3-race-end", race(RACE - 0.05)), ("4-outro", outro(OUTRO - 0.05))]
    cap = caption(scorers, args.comp, label, rnd)
    if args.png:
        os.makedirs(args.png, exist_ok=True)
        for name, im in stills:
            im.save(os.path.join(args.png, f"{name}.png"))
        print(f"{len(stills)} stills -> {args.png}")
        print(cap)
        return 0
    if not args.out:
        ap.error("--out or --png")
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    ok = M.encode({"id": f"scorers-{args.comp}"}, None, args.out, secs, frame_iter=D.frames(scenes))
    if args.sheet:
        M.contact_sheet([im for _, im in stills], args.sheet, cols=len(stills))
    with open(args.caption or os.path.splitext(args.out)[0] + "-caption.txt", "w", encoding="utf-8") as fh:
        fh.write(cap)
    print(f"{args.out}: {secs:.1f}s, {'UPLOADABLE' if ok else 'NOT uploadable'}")
    print(cap)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
