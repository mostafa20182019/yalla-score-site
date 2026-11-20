#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Elgoon - «ساعة أهداف الشهر»: every goal a club scored and conceded in one
month on ONE 90-minute dial (designer review 2026-11-19, the weekly/monthly
version of goal_clock.py; user 2026-11-20: «اعمل 11»).

The outer ring is what the club SCORED (its crest at each minute), the inner
ring what it CONCEDED (a white ring at each minute). Under the dial, the six
quarter-hours with both counts. It answers «متى يسجل الأهلي أهدافه؟» with a
picture.

COMPUTED from the goal minutes of the club's own matches, and only when the
month is whole in our data: every finished match of the club that month has
a goal list that adds up to its score - one match missing and the card is
not drawn (a month of «most goals after the 75th minute» built on four
matches of five would be wrong).

    python club_clock.py al-ahly 2026-10 --out clock.jpg

story_social.club_month() makes it a post: one club a day in the first days
of a month, for the month before.
"""
import argparse
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
from PIL import Image, ImageDraw                       # noqa: E402

import goal_clock as GC                                # noqa: E402
import social_card as SC                               # noqa: E402

W, H = GC.W, GC.H
CX, CY = W // 2, 640
R_OUT, R_FOR, R_AGAINST, R_HUB = 290, 246, 160, 70
DOT_FOR, DOT_AGAINST = 21, 13
MIN_MATCHES, MIN_GOALS = 3, 4
BANDS = ((1, 15), (16, 30), (31, 45), (46, 60), (61, 75), (76, 90))


def band_of(base):
    for i, (lo, hi) in enumerate(BANDS):
        if lo <= base <= hi:
            return i
    return len(BANDS) - 1 if base > 90 else 0


def month_info(slug, ym, pool, md_idx):
    """{club, slug, month, matches, goals_for [(base, add)], goals_against,
    bands_for [6], bands_against [6], crest} for the club's month `ym`
    (YYYY-MM), or None: no such club, fewer than MIN_MATCHES matches, fewer
    than MIN_GOALS goals, or a match of the month without a full goal list."""
    from site_lib.clubs import TEAM_PAGES
    from site_lib.names import _team_match
    tp = next((t for t in TEAM_PAGES if t["slug"] == slug), None)
    if not tp:
        return None
    ms = [m for m in pool.values() if str(m.get("kickoff") or "")[:7] == ym and _team_match(tp, m)
          and (m.get("status") or "").upper() == "FINISHED" and m.get("home_score") is not None]
    if len(ms) < MIN_MATCHES:
        return None
    gf, ga, crest = [], [], None
    for m in ms:
        total = int(m["home_score"]) + int(m["away_score"])
        goals = GC.goals_of(m, md_idx) if total else []
        if goals is None:
            return None                    # the month is not whole: no card
        mine = "h" if _team_match(tp, {"home": m.get("home"), "away": "", "competition": m.get("competition")}) else "a"
        crest = crest or m.get("home_badge" if mine == "h" else "away_badge")
        for g in goals:
            (gf if g["side"] == mine else ga).append((g["base"], g["add"]))
    if len(gf) + len(ga) < MIN_GOALS:
        return None
    bf, ba = [0] * len(BANDS), [0] * len(BANDS)
    for b, _ in gf:
        bf[band_of(b)] += 1
    for b, _ in ga:
        ba[band_of(b)] += 1
    return {"club": tp["name"], "slug": slug, "month": ym, "matches": len(ms), "crest": crest,
            "goals_for": sorted(gf), "goals_against": sorted(ga), "bands_for": bf, "bands_against": ba}


def month_ar(ym):
    from site_lib.arabic import _AR_MONTHS
    y, m = ym.split("-")
    return f"{_AR_MONTHS[int(m)]} {y}"


def _matches(n):
    return "مباراتين" if n == 2 else f"{n} مباريات" if n <= 10 else f"{n} مباراة"


def polar(r, deg):
    a = math.radians(deg - 90)
    return CX + r * math.cos(a), CY + r * math.sin(a)


def _place(points, r0, size):
    """[(x, y)] for the marks of one ring: a mark that would sit on another
    steps inward."""
    out, placed = [], []
    for base, add in points:
        deg = GC.angle_of(base, add)
        r = r0
        while any(abs(r - pr) < 2 * size - 6 and abs((deg - pd + 180) % 360 - 180) * r * math.pi / 180 < 2 * size - 4
                  for pr, pd in placed) and r > R_HUB + size:
            r -= 2 * size - 4
        placed.append((r, deg))
        out.append(polar(r, deg))
    return out


def render(info, out=None):
    c = SC._Canvas("ساعة الأهداف")
    d, img, FC = c.d, c.img, c.FC
    club = info["club"]
    nf, na = len(info["goals_for"]), len(info["goals_against"])
    # the header: the club, the month, the two totals
    c.crest(W - 40 - 56, 196, 56, club, info.get("crest"))
    ttl = f"{club} في {month_ar(info['month'])}"
    c.right(W - 40 - 112 - 20, 150, ttl, c.fit(ttl, "ExtraBold", 60, W - 80 - 132 - 20, 30))
    sub = f"سجل {nf} واستقبل {na} في {_matches(info['matches'])}"
    c.right(W - 40 - 112 - 20, 232, sub, c.fit(sub, "Bold", 34, W - 80 - 132 - 20, 22), SC.SOFT)

    # the dial
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    o = ImageDraw.Draw(ov)
    o.ellipse([CX - R_OUT, CY - R_OUT, CX + R_OUT, CY + R_OUT], fill=(255, 255, 255, 20), outline=(255, 255, 255, 150), width=4)
    for r, al in ((R_FOR, 70), ((R_FOR + R_AGAINST) // 2, 34), (R_AGAINST, 70), (R_HUB + 22, 34)):
        o.ellipse([CX - r, CY - r, CX + r, CY + r], outline=(255, 255, 255, al), width=2)
    for q in range(6):
        x0, y0 = polar(R_HUB + 6, q * 60)
        x1, y1 = polar(R_OUT, q * 60)
        o.line([(x0, y0), (x1, y1)], fill=(255, 255, 255, 120 if q in (0, 3) else 46), width=3 if q in (0, 3) else 2)
    img.paste(ov, (0, 0), ov)
    fl = FC.font("ExtraBold", 28)
    for q, lbl in ((1, "15"), (2, "30"), (3, "45"), (4, "60"), (5, "75"), (0, "90")):
        x, y = polar(R_OUT + 34, q * 60)
        c.mid(x, y, lbl, fl, SC.SOFT)
    mk = GC.DC._mark(2 * R_HUB)
    if mk is not None:
        img.paste(mk, (CX - R_HUB, CY - R_HUB), mk)
    for x, y in _place(info["goals_against"], R_AGAINST, DOT_AGAINST):
        d.ellipse([x - DOT_AGAINST, y - DOT_AGAINST, x + DOT_AGAINST, y + DOT_AGAINST], outline=SC.WHITE, width=5)
    for x, y in _place(info["goals_for"], R_FOR, DOT_FOR):
        d.ellipse([x - DOT_FOR - 3, y - DOT_FOR - 3, x + DOT_FOR + 3, y + DOT_FOR + 3], fill=SC.RED)
        c.crest(int(x), int(y), DOT_FOR, club, info.get("crest"))
    key = "الدائرة الخارجية: أهدافه · الداخلية: الأهداف في مرماه"
    c.centre(CX, CY + R_OUT + 58, key, c.fit(key, "Bold", 26, W - 120, 16), SC.DIM)

    # the six quarter-hours, RIGHT to LEFT as the match is read
    y0, cw = CY + R_OUT + 112, (W - 80) // 7
    fb, fn = FC.font("Bold", 24), FC.font("ExtraBold", 40)
    c.right(W - 40, y0 + 52, "سجل", fb, SC.WHITE)
    c.right(W - 40, y0 + 112, "استقبل", fb, SC.SOFT)
    top_f = max(info["bands_for"])
    for i, (lo, hi) in enumerate(BANDS):
        x = W - 40 - cw * (i + 1) - cw // 2
        c.mid(x, y0 + 12, f"{lo}-{hi}", fb, SC.DIM)
        best = info["bands_for"][i] == top_f and top_f and info["bands_for"].count(top_f) == 1
        if best:
            c.rrect([x - cw // 2 + 8, y0 + 34, x + cw // 2 - 8, y0 + 92], 14, SC.RED + (255,))
        c.mid(x, y0 + 62, str(info["bands_for"][i]), fn, SC.WHITE)
        c.mid(x, y0 + 122, str(info["bands_against"][i]), fn, SC.SOFT)
    c.foot("دورة كاملة = 90 دقيقة · البداية من أعلى")
    if out:
        img.save(out, quality=90, optimize=True)
    return img


def render_bytes(info):
    import io
    buf = io.BytesIO()
    render(info).save(buf, "JPEG", quality=90, optimize=True)
    return buf.getvalue()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("club", help="a club page's slug")
    ap.add_argument("month", help="YYYY-MM")
    ap.add_argument("--out", default="club-clock.jpg")
    args = ap.parse_args()
    pool, md_idx = GC.load_pool()
    info = month_info(args.club, args.month, pool, md_idx)
    if not info:
        print("no card: no such club, too few matches or goals that month, or a match without its full goal list")
        return 1
    render(info, args.out)
    print(f"wrote {args.out}: {info['club']} {args.month}, {info['matches']} matches, "
          f"{len(info['goals_for'])} for / {len(info['goals_against'])} against")
    return 0


if __name__ == "__main__":
    sys.exit(main())
