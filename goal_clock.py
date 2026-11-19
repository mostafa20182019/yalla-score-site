#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Elgoon - «ساعة الأهداف»: a finished match's goals on a 90-minute dial
(designer review 2026-11-19).

The logo is a target board with an arrow in it. This card IS that board: one
turn of the dial is the 90 minutes (kick-off at the top, half-time at the
bottom, clockwise), and every goal is the scoring club's crest standing at
its minute - the home side on the outer ring, the away side on the inner
one. Under the dial, the scorers by minute. A card no results page draws,
made of data we already hold (the goal minutes of the match's details).

The designer's first idea was a shot map on a drawn goal; the feed carries
no shot coordinates, so this is the version the data can back.

COMPUTED, never guessed: the card is drawn only when the match is FINISHED
and its goal list adds up to the score. A goal by a name from the OTHER
side's line-up is an own goal and says so.

    python goal_clock.py 4885547 --out clock.jpg        # a match id we hold
    python goal_clock.py --last al-ahly --out clock.jpg  # a club's latest match with a goal

A generator only (2026-11-19): nothing posts it yet - the user sees the look
first, then it gets a post kind and its own switch.
"""
import argparse
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
from PIL import Image, ImageDraw, ImageFilter          # noqa: E402

import day_card as DC                                  # noqa: E402

W, H = DC.W, DC.H
WHITE, SOFT, DIM, RED = DC.WHITE, DC.SOFT, DC.DIM, DC.RED
CX, CY = W // 2, 652
R_OUT, R_HOME, R_AWAY, R_HUB = 300, 252, 164, 78
MARK_R = 30
LIST_MAX = 5


def minute_of(mn):
    """'45+2' -> (45, 2), '63' -> (63, 0), anything else -> None."""
    try:
        base, _, add = str(mn or "").strip().replace("'", "").partition("+")
        return int(base), int(add or 0)
    except ValueError:
        return None


def angle_of(base, add=0):
    """Degrees clockwise from the top for a minute: 0' at the top, 45' at the
    bottom, 90' back at the top. Added time is the minute it was added to
    (a 90+4 goal stands at 90); extra time keeps turning past the top."""
    m = min(max(int(base), 0), 120)
    return m / 90.0 * 360.0 if m <= 90 else (m - 90) / 90.0 * 360.0


def polar(r, deg):
    a = math.radians(deg - 90)
    return CX + r * math.cos(a), CY + r * math.sin(a)


def goals_of(m, md_idx):
    """[{side 'h'|'a', minute text, base, add, player, own}] in match order,
    or None when the match is not finished or its goal list does not add up
    to the score."""
    from site_lib.matchdata import _played_names, _side_of, match_details_for
    if (m.get("status") or "FINISHED").upper() != "FINISHED" or m.get("home_score") is None:
        return None
    got = match_details_for(md_idx, dict(m, status="FINISHED"))
    if not got:
        return None
    e, flipped = got
    raw = e.get("goals") or []
    if len(raw) != int(m["home_score"]) + int(m["away_score"]):
        return None
    sd = _side_of(flipped)
    on = {k: {x.strip() for x in _played_names(e, flipped, k)} for k in ("h", "a")}
    out = []
    for g in raw:
        mn = minute_of(g.get("minute"))
        side = sd(g.get("side"))
        if mn is None or side not in ("h", "a"):
            return None
        who = (g.get("player") or "").strip()
        out.append({"side": side, "minute": str(g.get("minute")).strip(), "base": mn[0], "add": mn[1], "player": who,
                    "own": bool(who) and who not in on[side] and who in on["a" if side == "h" else "h"]})
    out.sort(key=lambda g: (g["base"], g["add"]))
    return out


def render(m, goals, out=None):
    """The card. m = a match row (home, away, scores, badges, competition,
    kickoff); goals = goals_of(). Returns the PIL image."""
    import fb_cards as FC
    import matchup_card as MC
    from site_lib.names import ar_team, comp_label
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / (H - 1)
        d.line([(0, y), (W, y)], fill=tuple(round(p + (q - p) * t) for p, q in zip(DC.TOP, DC.BOT)))
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse([CX - 420, CY - 380, CX + 420, CY + 380], fill=(31, 148, 211, 70))
    img.paste(glow.filter(ImageFilter.GaussianBlur(120)), (0, 0), glow.filter(ImageFilter.GaussianBlur(120)))

    def text_c(cx, y, s, f, fill=WHITE):
        s = FC.ar(s); d.text((cx - d.textlength(s, font=f) / 2, y), s, font=f, fill=fill)
    def text_r(xr, y, s, f, fill=WHITE):
        s = FC.ar(s); d.text((xr - d.textlength(s, font=f), y), s, font=f, fill=fill)
    def text_l(xl, y, s, f, fill=WHITE):
        d.text((xl, y), FC.ar(s), font=f, fill=fill)
    def fit(s, weight, size, max_w, min_size=18):
        f = FC.font(weight, size)
        while d.textlength(FC.ar(s), font=f) > max_w and size > min_size:
            size -= 2; f = FC.font(weight, size)
        return f
    def overlay(fn):
        ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        fn(ImageDraw.Draw(ov))
        img.paste(ov, (0, 0), ov)
    def crest(cx, cy, r, name, url, ring=None):
        im = None
        try:
            im = FC.crest_image(url, int(2 * r * 0.78)) if url else None
        except Exception:                               # noqa: BLE001
            im = None
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=WHITE, outline=ring, width=4 if ring else 0)
        if im is not None:
            img.paste(im, (int(cx - im.width / 2), int(cy - im.height / 2)), im)
        else:
            f = FC.font("ExtraBold", int(r * 0.9))
            s = FC.ar((name or "?").strip()[:1])
            d.text((cx - d.textlength(s, font=f) / 2, cy - r * 0.6), s, font=f, fill=(16, 62, 108))

    h, a = ar_team(m.get("home")), ar_team(m.get("away"))
    hs, as_ = int(m["home_score"]), int(m["away_score"])
    # ---- the header: the brand, the red tag, the result
    FC.wordmark_at(img, W - 40, 66, 64, anchor="rm")
    ftag = FC.font("ExtraBold", 30)
    tw = d.textlength(FC.ar("ساعة الأهداف"), font=ftag)
    overlay(lambda o: o.rounded_rectangle([40, 40, 40 + tw + 44, 94], 27, fill=RED + (255,)))
    text_l(62, 47, "ساعة الأهداف", ftag)
    yr = 190
    crest(W - 40 - 56, yr, 56, h, m.get("home_badge"))
    crest(40 + 56, yr, 56, a, m.get("away_badge"))
    fs = FC.font("ExtraBold", 92)
    sc = f"{as_} - {hs}"                       # HOME is on the right, so its goals are the right-hand number
    bx = d.textbbox((0, 0), sc, font=fs)
    d.text((CX - (bx[0] + bx[2]) / 2, yr - (bx[1] + bx[3]) / 2), sc, font=fs, fill=WHITE)
    side_w = CX - 120 - (40 + 112 + 16)
    fh, fa = fit(h, "ExtraBold", 40, side_w), fit(a, "ExtraBold", 40, side_w)
    text_r(W - 40 - 112 - 16, yr - fh.size * 0.62, h, fh)
    text_l(40 + 112 + 16, yr - fa.size * 0.62, a, fa)
    sub = comp_label(m.get("competition")) + (" · " + MC.when_ar(str(m.get("kickoff"))[:10], None) if m.get("kickoff") else "")
    text_c(CX, 262, sub, fit(sub, "Bold", 28, W - 120, 18), SOFT)

    # ---- the dial: a target board whose one turn is the 90 minutes
    def board(o):
        o.ellipse([CX - R_OUT, CY - R_OUT, CX + R_OUT, CY + R_OUT], fill=(255, 255, 255, 20), outline=(255, 255, 255, 150), width=4)
        for r, al in ((R_HOME, 70), ((R_HOME + R_AWAY) // 2, 34), (R_AWAY, 70), (R_HUB + 24, 34)):
            o.ellipse([CX - r, CY - r, CX + r, CY + r], outline=(255, 255, 255, al), width=2)
        for q in range(6):                      # a spoke every quarter-hour
            x0, y0 = polar(R_HUB + 6, q * 60)
            x1, y1 = polar(R_OUT, q * 60)
            o.line([(x0, y0), (x1, y1)], fill=(255, 255, 255, 120 if q in (0, 3) else 46), width=3 if q in (0, 3) else 2)
    overlay(board)
    fl = FC.font("ExtraBold", 28)
    for q, lbl in ((1, "15"), (2, "30"), (3, "45"), (4, "60"), (5, "75"), (0, "90")):
        x, y = polar(R_OUT + 34, q * 60)
        bx = d.textbbox((0, 0), lbl, font=fl)
        d.text((x - (bx[0] + bx[2]) / 2, y - (bx[1] + bx[3]) / 2), lbl, font=fl, fill=SOFT)
    mk = DC._mark(2 * R_HUB)
    if mk is not None:
        img.paste(mk, (CX - R_HUB, CY - R_HUB), mk)
    # every goal at its minute: the scoring club's crest, the minute beside it
    placed = []
    fm = FC.font("ExtraBold", 24)
    for g in goals:
        r = R_HOME if g["side"] == "h" else R_AWAY
        deg = angle_of(g["base"], g["add"])
        # two goals of one side a few minutes apart would sit on each other
        while any(s == g["side"] and abs(r - pr) < 2 * MARK_R - 8 and abs((deg - pd + 180) % 360 - 180) * r * math.pi / 180 < 2 * MARK_R - 4
                  for s, pr, pd in placed):
            r -= 2 * MARK_R - 6
        placed.append((g["side"], r, deg))
        x, y = polar(r, deg)
        nm, url = (h, m.get("home_badge")) if g["side"] == "h" else (a, m.get("away_badge"))
        crest(int(x), int(y), MARK_R, nm, url, ring=RED)
    text_c(CX, CY + R_OUT + 62, f"الدائرة الخارجية: {h} · الداخلية: {a}",
           fit(f"الدائرة الخارجية: {h} · الداخلية: {a}", "Bold", 26, W - 120, 16), DIM)

    # ---- the scorers by minute, the home side on the right
    y0 = CY + R_OUT + 112
    fn_ = FC.font("ExtraBold", 30)
    for side, right in (("h", True), ("a", False)):
        mine = [g for g in goals if g["side"] == side]
        shown = mine[:LIST_MAX] if len(mine) <= LIST_MAX else mine[:LIST_MAX - 1]
        for i, g in enumerate(shown):
            who = (g["player"] or "هدف") + (" (عكسي)" if g["own"] else "")
            y = y0 + i * 44
            mt = g["minute"] + "'"
            mw = d.textlength(mt, font=fm)
            f = fit(who, "ExtraBold", fn_.size, CX - 60 - 40 - mw - 16, 18)
            if right:
                d.text((W - 40 - mw, y + 4), mt, font=fm, fill=DC.GOLD)
                text_r(W - 40 - mw - 14, y, who, f)
            else:
                d.text((40, y + 4), mt, font=fm, fill=DC.GOLD)
                text_l(40 + mw + 14, y, who, f)
        if len(mine) > len(shown):
            more = f"و{len(mine) - len(shown)} أهداف أخرى"
            (text_r if right else text_l)(W - 40 if right else 40, y0 + len(shown) * 44, more, FC.font("Bold", 24), DIM)
    text_l(40, H - 46, "elgoon.com", FC.font("Bold", 24), SOFT)
    text_r(W - 40, H - 44, "دورة كاملة = 90 دقيقة · البداية من أعلى", FC.font("Regular", 22), DIM)
    if out:
        img.save(out, quality=90, optimize=True)
    return img


def load_pool():
    """(matches by id, details index): everything finished we hold."""
    import results_archive as RA
    from site_lib.config import load
    from site_lib.matchdata import match_details_index, merge_details
    pool = {}
    for m in (load("matches.json") or []) + RA.season_rows(RA.load()) + (load("matches_archive.json") or []):
        if m.get("match_id") and str(m["match_id"]) not in pool and m.get("home_score") is not None:
            pool[str(m["match_id"])] = dict(m, status=(m.get("status") or "FINISHED"))
    return pool, match_details_index(merge_details(load("match_details.json"), load("details_archive.json")))


def last_for(slug, pool, md_idx):
    """The club's latest finished match that has a goal and a full goal list."""
    from site_lib.clubs import TEAM_PAGES
    from site_lib.names import _team_match
    tp = next((t for t in TEAM_PAGES if t["slug"] == slug), None)
    if not tp:
        return None
    rows = sorted((m for m in pool.values() if _team_match(tp, m) and (m.get("status") or "").upper() == "FINISHED"),
                  key=lambda m: (str(m.get("kickoff") or ""), m.get("koff_time") or ""), reverse=True)
    for m in rows:
        if goals_of(m, md_idx):
            return m
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("match_id", nargs="?")
    ap.add_argument("--last", metavar="CLUB_SLUG")
    ap.add_argument("--out", default="goal-clock.jpg")
    args = ap.parse_args()
    pool, md_idx = load_pool()
    m = last_for(args.last, pool, md_idx) if args.last else pool.get(str(args.match_id))
    if not m:
        print("no such finished match on record"); return 1
    goals = goals_of(m, md_idx)
    if not goals:
        print("no card: the match has no goals, or its goal list does not add up to the score"); return 1
    render(m, goals, args.out)
    print(f"wrote {args.out}: {m.get('home')} {m.get('home_score')}-{m.get('away_score')} {m.get('away')}, {len(goals)} goals")
    return 0


if __name__ == "__main__":
    sys.exit(main())
