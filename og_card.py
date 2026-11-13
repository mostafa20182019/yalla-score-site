#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Link-preview images (og:image, 1200x630) for pages that had none of their
own and shared the site banner: the head-to-head pages and the league hubs.

Designed by the graphic-designer review of 2026-11-13 (samples approved by
the user the same day: «الشكل عاجبني»): the matchup card's canvas - our blue
top to bottom, white ring crests, the «الجون» wordmark right and elgoon.com
left on the bottom row. No red but the wordmark's own dart board, so nothing
reads as a club colour. Everything sits inside x 60..1140, so a 16:9 crop
(Google Discover) loses nothing.

Drawn at BUILD time into dist/og/ (never into git) from the same numbers the
page shows:

    h2h(a, b, n, since, wins_a, draws, wins_b, crest_a, crest_b, out)
    league(label, kind, rows, unit, season, stamp, out, head="المركز · الفريق")

Shaping, fonts, the wordmark and the crest cache are fb_cards' own (one
engine on Windows and on the Linux runner). A failure returns None and the
page keeps the banner - a preview image never breaks a build.

    python og_card.py            # two samples into data/briefs/ (needs local data)
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from PIL import Image, ImageDraw, ImageFilter          # noqa: E402

W, H = 1200, 630
TOP, BOT = (31, 148, 211), (12, 66, 104)          # matchup_card.TOP / BOT
WHITE, SOFT = (255, 255, 255), (220, 236, 248)
INK = (12, 66, 104)
X0, X1 = 60, 1140                                 # the 16:9-safe band
PANEL, PANEL_LINE = (8, 44, 74, 150), (255, 255, 255, 46)


def _fc():
    import fb_cards as FC
    return FC


def _canvas(pitch=True):
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / (H - 1)
        d.line([(0, y), (W, y)], fill=tuple(round(a + (b - a) * t) for a, b in zip(TOP, BOT)))
    if pitch:
        ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        od = ImageDraw.Draw(ov)
        od.line([(W // 2, 0), (W // 2, H)], fill=(255, 255, 255, 30), width=3)
        od.ellipse([W // 2 - 215, H // 2 - 215, W // 2 + 215, H // 2 + 215],
                   outline=(255, 255, 255, 30), width=3)
        img.paste(ov, (0, 0), ov)
    return img, ImageDraw.Draw(img)


def _rrect(img, box, r, fill, outline=None, width=2):
    ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(ov).rounded_rectangle(box, r, fill=fill, outline=outline, width=width)
    img.paste(ov, (0, 0), ov)


def _fit(FC, d, s, weight, size, max_w, min_size=22):
    f = FC.font(weight, size)
    while d.textlength(FC.ar(s), font=f) > max_w and size > min_size:
        size -= 2
        f = FC.font(weight, size)
    return f


def _text_c(FC, d, cx, y, s, f, fill=WHITE):
    t = FC.ar(s)
    d.text((cx - d.textlength(t, font=f) / 2, y), t, font=f, fill=fill)


def _text_r(FC, d, xr, y, s, f, fill=WHITE):
    t = FC.ar(s)
    d.text((xr - d.textlength(t, font=f), y), t, font=f, fill=fill)


def _ring(img, d, cx, cy, r, im):
    sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).ellipse([cx - r + 4, cy - r + 10, cx + r + 4, cy + r + 10], fill=(0, 0, 0, 90))
    sh = sh.filter(ImageFilter.GaussianBlur(10))
    img.paste(sh, (0, 0), sh)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=WHITE)
    if im is not None:
        img.paste(im, (cx - im.width // 2, cy - im.height // 2), im)


def _brand_row(FC, img, d):
    FC.wordmark_at(img, X1, H - 50, 64, anchor="rm")
    d.text((X0, H - 68), "elgoon.com", font=FC.font("Bold", 28), fill=SOFT)


def _save(img, out):
    os.makedirs(os.path.dirname(out), exist_ok=True)
    img.save(out, quality=88, optimize=True, progressive=True)
    return out


def shared_ranks(values):
    """1, 2, 2, 2, 5 for 10, 9, 9, 9, 8: equal values share a rank, so the
    image never orders players the numbers do not order."""
    out = []
    for i, v in enumerate(values):
        out.append(out[-1] if i and v == values[i - 1] else i + 1)
    return out


def _games_ar(n):
    """«15 مباراة» / «6 مباريات» - the count as the page words it."""
    return f"{n} مباريات" if 3 <= n <= 10 else f"{n} مباراة"


def h2h(a, b, n, since, wins_a, draws, wins_b, crest_a, crest_b, out):
    """The head-to-head page's image: both crests, the title, the tally.
    Club A on the RIGHT (the page's order). No goals on it: awarded results
    and shoot-outs make a goals line need a footnote the image has no room for."""
    try:
        FC = _fc()
        img, d = _canvas()
        title = f"مواجهات {a} و{b}"
        _text_c(FC, d, W // 2, 44, title, _fit(FC, d, title, "ExtraBold", 68, 1000))
        _text_c(FC, d, W // 2, 132, f"آخر {_games_ar(n)} في كل البطولات · منذ {since}",
                FC.font("Bold", 30), SOFT)
        cy, r = 318, 92
        for cx, club, url in ((1010, a, crest_a), (190, b, crest_b)):
            _ring(img, d, cx, cy, r, FC.crest_image(url, 128) if url else None)
            _text_c(FC, d, cx, cy + r + 14, club, _fit(FC, d, club, "ExtraBold", 46, 250))
        _rrect(img, [330, 214, 870, 438], 28, PANEL, PANEL_LINE)
        d = ImageDraw.Draw(img)
        fnum = FC.font("ExtraBold", 120)
        for cx, k, label in ((780, wins_a, f"فوز {a}"), (600, draws, "تعادل"), (420, wins_b, f"فوز {b}")):
            s = str(k)
            d.text((cx - d.textlength(s, font=fnum) / 2, 226), s, font=fnum, fill=WHITE)
            # a long name («فوز طرابزون سبور») shrinks to stay inside its third
            _text_c(FC, d, cx, 372, label, _fit(FC, d, label, "Bold", 30, 156, 14), SOFT)
        d.line([(510, 250), (510, 402)], fill=(255, 255, 255, 70), width=2)
        d.line([(690, 250), (690, 402)], fill=(255, 255, 255, 70), width=2)
        _brand_row(FC, img, d)
        return _save(img, out)
    except Exception as ex:                                 # noqa: BLE001
        print(f"  ! og image {os.path.basename(out)} not drawn: {ex}")
        return None


def league(label, kind, rows, unit, season, stamp, out, head="المركز · الفريق"):
    """A league hub's image. kind = the page («جدول الترتيب» / «الهدافون»);
    rows = the first lines of the list that page leads with:
    [(position, crest url, name, value)], at most five."""
    try:
        FC = _fc()
        rows = list(rows)[:5]
        if not rows:
            return None
        img, d = _canvas(pitch=False)
        rx, dy = X1, 34
        pf = FC.font("Bold", 30)
        pw = d.textlength(FC.ar(kind), font=pf) + 48
        _rrect(img, [rx - pw, 118 + dy, rx, 174 + dy], 28, (255, 255, 255, 255))
        d = ImageDraw.Draw(img)
        _text_r(FC, d, rx - 24, 126 + dy, kind, pf, INK)
        _text_r(FC, d, rx, 200 + dy, label, _fit(FC, d, label, "ExtraBold", 92, 470, 40))
        # the season in TWO runs: python-bidi turns «موسم 2026-2027» into
        # «2027-2026» (the hyphen splits the number run), so the digits are
        # drawn as their own left-to-right run, left of the word
        fs = FC.font("Bold", 38)
        word = FC.ar("موسم")
        wx = rx - d.textlength(word, font=fs)
        d.text((wx, 322 + dy), word, font=fs, fill=SOFT)
        d.text((wx - 14 - d.textlength(str(season), font=fs), 322 + dy), str(season), font=fs, fill=SOFT)
        if stamp:
            _text_r(FC, d, rx, 378 + dy, stamp, FC.font("Regular", 30), SOFT)

        px0, px1, py0, rh = X0, 620, 62, 84
        _rrect(img, [px0, py0, px1, py0 + 44 + len(rows) * rh + 16], 26, PANEL, PANEL_LINE)
        d = ImageDraw.Draw(img)
        _text_r(FC, d, px1 - 28, py0 + 12, head, FC.font("Bold", 22), SOFT)
        d.text((px0 + 28, py0 + 12), FC.ar(unit), font=FC.font("Bold", 22), fill=SOFT)
        for i, (pos, crest, name, value) in enumerate(rows):
            y = py0 + 48 + i * rh
            if i:
                d.line([(px0 + 24, y), (px1 - 24, y)], fill=(255, 255, 255, 40), width=1)
            cy = y + rh // 2
            fp = FC.font("ExtraBold", 34)
            s = str(pos)
            d.text((px1 - 52 - d.textlength(s, font=fp) / 2, cy - 22), s, font=fp, fill=SOFT)
            d.ellipse([px1 - 148, cy - 31, px1 - 86, cy + 31], fill=WHITE)
            im = FC.crest_image(crest, 46) if crest else None
            if im is not None:
                img.paste(im, (px1 - 117 - im.width // 2, cy - im.height // 2), im)
            _text_r(FC, d, px1 - 166, cy - 24, name, _fit(FC, d, name, "ExtraBold", 36, 270))
            s = str(value)
            fv = FC.font("ExtraBold", 44)
            d.text((px0 + 58 - d.textlength(s, font=fv) / 2, cy - 28), s, font=fv, fill=WHITE)
        _brand_row(FC, img, d)
        return _save(img, out)
    except Exception as ex:                                 # noqa: BLE001
        print(f"  ! og image {os.path.basename(out)} not drawn: {ex}")
        return None


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    from site_lib import h2h as HH
    from site_lib.config import load
    from site_lib.names import ar_team
    out = os.path.join(HERE, "data", "briefs")
    st = next(s for s in load("standings.json") if s.get("competition") == "Egyptian Premier League")
    cu = {ar_team(r["team"]): r.get("crest") for r in st["table"]}
    p = HH.PAIRS[0]
    hist = HH.load_history(p)
    g = HH.meetings(p, hist, {})
    t = HH.tally(g, p, HH.notes_for(p, hist))
    print(h2h(p["a"], p["b"], len(g), HH.ar_month_year(g[-1]["date"]), t["wins"][p["a"]], t["draws"],
              t["wins"][p["b"]], cu.get(p["a"]), cu.get(p["b"]), os.path.join(out, "og-h2h.jpg")))
    print(league("الدوري المصري", "جدول الترتيب",
                 [(r["pos"], r.get("crest"), ar_team(r["team"]), r.get("pts")) for r in st["table"][:5]],
                 "نقطة", "2026-2027", "", os.path.join(out, "og-league.jpg")))
