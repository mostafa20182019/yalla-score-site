#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The weekly head-to-head infographic (growth plan week 4, 2026-10-08).

«آخر N مواجهات» between the two clubs of a big match, as a 1080x1350
Facebook photo (4:5) in the site's blue: the two crests (user decision
2026-10-08 - crests on every card), the wins/draws tally, goals, the list of
meetings newest first, the last win of each side, and the data line.

Everything on it is a FACT from the 365scores head-to-head feed for that
match (dates, competitions, scores). Nothing is typed by hand: the derby
prototype in matches-guide/analysis-drafts/ carried notes (awarded games,
penalty shoot-outs) checked on Wikipedia; this one shows the official scores
only and says so in the footer.

    python h2h_card.py --match 4804684 --out /tmp/h2h.jpg
    python fb_post.py --h2h 4804684 [--dry]      # the post (fb_post.h2h_post)
    python fb_post.py --h2h auto                 # the biggest match of the next days, once a week
"""
import argparse
import datetime
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from PIL import Image, ImageDraw, ImageFilter          # noqa: E402

W, H = 1080, 1350
TOP, BOT = (16, 62, 108), (5, 20, 40)
WHITE, SOFT, DIM = (255, 255, 255), (205, 222, 238), (150, 172, 196)
GOLD = (246, 192, 60)
PANEL_FILL, PANEL_LINE = (255, 255, 255, 18), (255, 255, 255, 40)
CARD_FILL = (255, 255, 255, 22)
LINE = (70, 104, 140)
MAX_GAMES = 10
MIN_GAMES = 4          # fewer meetings on record = no card


# ---------------------------------------------------------------- data
def h2h_games(m):
    """[{date, comp, home, away, hg, ag}] newest first, played games only, up
    to MAX_GAMES, from 365scores' head-to-head for this match. [] offline."""
    import match_brief as MB
    gid = MB.resolve_s365_game(m)
    if not gid:
        return []
    try:
        j = MB._s365(f"games/h2h/?appTypeId=5&langId=27&gameId={gid}")
    except Exception:                                   # noqa: BLE001
        return []
    out = []
    for x in (j.get("game") or {}).get("h2hGames") or []:
        sc = x.get("scores") or []
        if len(sc) < 2 or sc[0] is None or sc[0] < 0 or sc[1] is None or sc[1] < 0:
            continue
        out.append({"date": (x.get("startTime") or "")[:10],
                    "comp": x.get("competitionDisplayName") or "",
                    "home": (x.get("homeCompetitor") or {}).get("name") or "",
                    "away": (x.get("awayCompetitor") or {}).get("name") or "",
                    "hg": int(sc[0]), "ag": int(sc[1])})
    out.sort(key=lambda g: g["date"], reverse=True)
    return out[:MAX_GAMES]


def tally(games, h, a):
    """wins per club, draws, goals per club, last win date per club."""
    from site_lib.names import ar_team
    w, gf, last = {h: 0, a: 0}, {h: 0, a: 0}, {h: None, a: None}
    draws = 0
    def side(name):
        n = ar_team(name)
        return h if n == h else (a if n == a else None)
    for g in games:                                   # newest first
        gh, ga = side(g["home"]), side(g["away"])
        if gh is None or ga is None:
            continue
        gf[gh] += g["hg"]; gf[ga] += g["ag"]
        if g["hg"] > g["ag"]:
            w[gh] += 1; last[gh] = last[gh] or g["date"]
        elif g["ag"] > g["hg"]:
            w[ga] += 1; last[ga] = last[ga] or g["date"]
        else:
            draws += 1
    return w, draws, gf, last


def ar_date(iso):
    from site_lib.arabic import _AR_MONTHS
    try:
        d = datetime.date.fromisoformat(iso[:10])
    except (TypeError, ValueError):
        return iso or ""
    return f"{d.day} {_AR_MONTHS[d.month]} {d.year}"


# ---------------------------------------------------------------- drawing
def render(m, games, out, when=""):
    """Write the card for match `m` (matches.json shape) and its h2h games."""
    import fb_cards as FC
    import matchup_card as MC
    from site_lib.names import ar_team, comp_label
    h, a = ar_team(m.get("home")), ar_team(m.get("away"))
    w, draws, gf, last = tally(games, h, a)
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / (H - 1)
        d.line([(0, y), (W, y)], fill=tuple(round(p + (q - p) * t) for p, q in zip(TOP, BOT)))
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse([W // 2 - 420, 120, W // 2 + 420, 760], fill=(31, 148, 211, 70))
    glow = glow.filter(ImageFilter.GaussianBlur(120))
    img.paste(glow, (0, 0), glow)

    def text_c(cx, y, s, f, fill=WHITE):
        s = FC.ar(s); d.text((cx - d.textlength(s, font=f) / 2, y), s, font=f, fill=fill)
    def text_r(xr, y, s, f, fill=WHITE):
        s = FC.ar(s); d.text((xr - d.textlength(s, font=f), y), s, font=f, fill=fill)
    def text_l(xl, y, s, f, fill=WHITE):
        d.text((xl, y), FC.ar(s), font=f, fill=fill)
    def rrect(box, r, fill, outline=None, width=2):
        ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(ov).rounded_rectangle(box, r, fill=fill, outline=outline, width=width)
        img.paste(ov, (0, 0), ov)

    def badge(cx, cy, r, name, url, kit):
        sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(sh).ellipse([cx - r + 4, cy - r + 10, cx + r + 4, cy + r + 10], fill=(0, 0, 0, 110))
        sh = sh.filter(ImageFilter.GaussianBlur(10))
        img.paste(sh, (0, 0), sh)
        im = None
        try:
            im = FC.crest_image(url, int(2 * r * 0.72)) if url else None
        except Exception:                               # noqa: BLE001
            im = None
        if im is not None:
            d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=WHITE)
            img.paste(im, (cx - im.width // 2, cy - im.height // 2), im)
        else:                                           # the coloured disc, like the matchup card
            face = Image.new("RGB", (2 * r, 2 * r), kit[1][0])
            fd = ImageDraw.Draw(face)
            if kit[0] == "bands":
                for y0 in (int(r * 0.62), int(r * 0.98)):
                    fd.rectangle([0, y0, 2 * r, y0 + int(r * 0.22)], fill=kit[1][1])
            elif kit[0] == "halves":
                fd.rectangle([r, 0, 2 * r, 2 * r], fill=kit[1][1])
            msk = Image.new("L", (2 * r, 2 * r), 0)
            ImageDraw.Draw(msk).ellipse([0, 0, 2 * r - 1, 2 * r - 1], fill=255)
            img.paste(face, (cx - r, cy - r), msk)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=WHITE, width=6)

    # brand + title
    icon = Image.open(os.path.join(HERE, "assets-src", "app-icon-1024.png")).convert("RGB")
    ball = icon.crop((218, 105, 806, 693)).resize((52, 52), Image.LANCZOS)
    bm = Image.new("L", (52, 52), 0)
    ImageDraw.Draw(bm).ellipse([0, 0, 51, 51], fill=255)
    img.paste(ball, (W - 52 - 40, 36), bm)
    text_r(W - 40 - 52 - 12, 40, "يلا سكور", FC.font("ExtraBold", 34))
    sub = " · ".join(x for x in (comp_label(m.get("competition")), when) if x)
    if sub:
        text_l(40, 46, sub, FC.font("Bold", 26), SOFT)
    n = len(games)
    text_c(W // 2, 92, f"آخر {n} مواجهات" if n != 2 else "آخر مواجهتين", FC.font("ExtraBold", 80))
    text_c(W // 2, 196, f"بين {h} و{a}", FC.font("Bold", 42), GOLD)

    # the two sides + the record
    rrect([40, 272, W - 40, 600], 28, PANEL_FILL, PANEL_LINE)
    HX, AX, CY, R = 880, 200, 372, 66                  # home on the RIGHT (RTL)
    hk, ak = MC.kits(h, a, m.get("competition"))
    badge(HX, CY, R, h, m.get("home_badge"), hk)
    badge(AX, CY, R, a, m.get("away_badge"), ak)
    fn = FC.font("ExtraBold", 42)
    for cx, name in ((HX, h), (AX, a)):
        f = fn
        while d.textlength(FC.ar(name), font=f) > 300 and f.size > 24:
            f = FC.font("ExtraBold", f.size - 4)
        text_c(cx, CY + R + 8, name, f)
    for cx, k, label, col in ((690, w[h], f"فوز {h}", GOLD), (540, draws, "تعادل", WHITE), (390, w[a], f"فوز {a}", GOLD)):
        f = FC.font("ExtraBold", 96)
        s = str(k)
        d.text((cx - d.textlength(s, font=f) / 2, 286), s, font=f, fill=col)
        fl = FC.font("Bold", 28)
        while d.textlength(FC.ar(label), font=fl) > 140 and fl.size > 18:
            fl = FC.font("Bold", fl.size - 2)
        text_c(cx, 398, label, fl, SOFT)
    d.line([(465, 306), (465, 436)], fill=LINE, width=2)
    d.line([(615, 306), (615, 436)], fill=LINE, width=2)

    def goals_pair(cx, scored, conceded):
        for dx, k, label in ((+78, scored, "سجّل"), (-78, conceded, "استقبل")):
            x = cx + dx
            rrect([x - 68, 506, x + 68, 584], 16, (0, 0, 0, 70))
            f = FC.font("ExtraBold", 44)
            s = str(k)
            d.text((x - d.textlength(s, font=f) / 2, 508), s, font=f, fill=WHITE)
            text_c(x, 554, label, FC.font("Bold", 22), SOFT)
    goals_pair(HX - 30, gf[h], gf[a])
    goals_pair(AX + 30, gf[a], gf[h])
    text_c(W // 2, 470, "الأهداف", FC.font("Bold", 30), WHITE)
    text_c(W // 2, 510, f"في {n} مباريات" if n > 2 else "في المباراتين", FC.font("Regular", 24), DIM)
    text_c(W // 2, 540, "بالنتائج الرسمية", FC.font("Regular", 24), DIM)

    # the meetings: 2 columns x 5, newest at the top right
    CW, CH, GAP = 486, 112, 10
    COLS = (W - 40 - CW, 40)
    fnm, fs, fc = FC.font("ExtraBold", 32), FC.font("ExtraBold", 34), FC.font("Bold", 21)
    for i, g in enumerate(games[:MAX_GAMES]):
        x0 = COLS[i // 5]
        y0 = 618 + (i % 5) * (CH + GAP)
        rrect([x0, y0, x0 + CW, y0 + CH], 18, CARD_FILL, None, 1)
        nb = 34
        d.ellipse([x0 + CW - nb - 12, y0 + 12, x0 + CW - 12, y0 + 12 + nb], fill=GOLD)
        s = str(i + 1)
        f = FC.font("ExtraBold", 22)
        d.text((x0 + CW - 12 - nb / 2 - d.textlength(s, font=f) / 2, y0 + 15), s, font=f, fill=(20, 30, 50))
        head = f"{g['comp']} · {ar_date(g['date'])}"
        fh = fc
        while d.textlength(FC.ar(head), font=fh) > CW - nb - 40 and fh.size > 14:
            fh = FC.font("Bold", fh.size - 1)
        text_r(x0 + CW - nb - 22, y0 + 14, head, fh, DIM)
        gh, ga = ar_team(g["home"]), ar_team(g["away"])
        hw, aw = g["hg"] > g["ag"], g["ag"] > g["hg"]
        mid = x0 + CW / 2 - 16
        fh2 = fnm
        while max(d.textlength(FC.ar(gh), font=fh2), d.textlength(FC.ar(ga), font=fh2)) > 150 and fh2.size > 20:
            fh2 = FC.font("ExtraBold", fh2.size - 2)
        text_l(mid + 66, y0 + 46, gh, fh2, WHITE if hw else SOFT)     # home RIGHT of the score
        text_r(mid - 66, y0 + 46, ga, fh2, WHITE if aw else SOFT)     # away LEFT of it
        sc = f"{g['ag']} - {g['hg']}"                                 # drawn LTR: away left, home right
        rrect([mid - 56, y0 + 46, mid + 56, y0 + 88], 12, (0, 0, 0, 90))
        d.text((mid - d.textlength(sc, font=fs) / 2, y0 + 46), sc, font=fs, fill=WHITE)

    # the last win of each side + footer
    fy = 618 + 5 * (CH + GAP) + 4
    rrect([40, fy, W - 40, fy + 60], 18, (246, 192, 60, 26), (246, 192, 60, 120), 2)
    parts = []
    for name in (h, a):
        parts.append(f"آخر فوز لـ{name}: {ar_date(last[name])}" if last[name] else f"{name} بلا فوز في هذه المواجهات")
    fact = " · ".join(parts)
    ff = FC.font("Bold", 30)
    while d.textlength(FC.ar(fact), font=ff) > W - 120 and ff.size > 18:
        ff = FC.font("Bold", ff.size - 2)
    text_c(W // 2, fy + 10 + (30 - ff.size) // 2, fact, ff, WHITE)
    text_l(40, H - 46, "yallascore.site", FC.font("Bold", 24), SOFT)
    text_r(W - 40, H - 44, "البيانات: 365Scores · النتائج الرسمية", FC.font("Regular", 22), DIM)
    img.save(out, quality=90, optimize=True) if out.lower().endswith((".jpg", ".jpeg")) else img.save(out)
    return {"n": n, "wins": w, "draws": draws, "goals": gf, "last": last}


def for_match(m, out):
    """Fetch + render. None when the record is too short to be worth a card."""
    import matchup_card as MC
    games = h2h_games(m)
    if len(games) < MIN_GAMES:
        return None
    return render(m, games, out, when=MC.when_ar(m.get("kickoff"), m.get("koff_time")))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--match", required=True)
    ap.add_argument("--out", default=os.path.join(HERE, "data", "briefs", "h2h.jpg"))
    args = ap.parse_args()
    import match_brief as MB
    d = MB.load_all()
    m = next((x for x in d["matches"] if str(x.get("match_id")) == str(args.match)), None)
    if not m:
        sys.exit(f"match {args.match} is not in matches.json")
    r = for_match(m, args.out)
    print(args.out if r else "too few meetings on record", r)
