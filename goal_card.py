#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The goal graphic of the «⚽ هدف!» Facebook post (user, 2026-10-17, from a
Btolat example: «جووووول», the scoring club's crest in a glass circle, the
scorer and minute, the score strip with both crests).

    python goal_card.py --game 4854774 --side h --player "عمر الساعي" --minute 66 \
        --home "كيتارا" --away "الأهلي" --hs 1 --as 1 --comp 627 --out goal.jpg
    python goal_card.py --fixture tests/fixtures/game_4742043_lineups.json ... (offline)

The crests come from the game/ detail (competitor id + imageVersion -> the
365scores badge URL, read at 400 px). 1080x1350 portrait, the brand canvas.
"""
import argparse
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from PIL import Image, ImageDraw, ImageFilter          # noqa: E402

W, H = 1080, 1080                                  # square, like the reference
TOP, BOT = (16, 62, 108), (5, 20, 40)
WHITE, SOFT, DIM = (255, 255, 255), (205, 222, 238), (150, 172, 196)
GOLD, ORANGE = (246, 192, 60), (232, 93, 4)
COMP_AR = {552: "الدوري المصري", 624: "دوري أبطال أفريقيا", 627: "كأس الكونفدرالية الأفريقية",
           588: "تصفيات كأس أمم أفريقيا", 7: "الدوري الإنجليزي", 11: "الدوري الإسباني",
           17: "الدوري الإيطالي", 25: "الدوري الألماني", 35: "الدوري الفرنسي", 78: "الدوري التركي",
           649: "الدوري السعودي", 572: "دوري أبطال أوروبا", 573: "الدوري الأوروبي", 7016: "دوري الأمم الأوروبية"}


def _badge(c):
    import fetch_data as fd
    return fd._s365_badge(c) if c and c.get("id") else None


def badges_for(game):
    """(home badge url, away badge url) from a game/ detail, None where absent."""
    return (_badge(game.get("homeCompetitor") or {}), _badge(game.get("awayCompetitor") or {}))


def _s365_game(gid):
    import fetch_data as fd
    return fd._s365(f"game/?appTypeId=5&langId=27&timezoneName=Africa/Cairo&gameId={gid}").get("game") or {}


def _crest(url, size):
    from club_identity_card import _big_crest
    try:
        return _big_crest(url, size) if url else None
    except Exception:  # noqa: BLE001
        return None


_MINUTE = re.compile(r"^\d+(\+\d+)?$")


def minute_text(m):
    """«63» / «45+2» or '' - the minute chip and the «الدقيقة X» line take
    numbers only. 2026-10-24: a score-only goal seen during the break carried
    the Worker's break label «استراحة» as its minute; the caption read
    «الدقيقة استراحة» and the chip (drawn LTR, unshaped, digits expected)
    showed «ةحارتسا». An empty minute is honest; a wrong word is not."""
    m = str(m or "").strip().replace("'", "").replace("′", "")
    return m if _MINUTE.match(m) else ""


def render(ev, out=None):
    """ev = {side 'h'|'a', player, minute, tag, home, away, hs, as, comp,
    home_badge, away_badge}. Returns the PIL image (and saves to `out`).
    Layout = the user's reference (2026-10-17, «اعمل زيها بالظبط»): the brand
    centred at the top, the word, the crest in a glass circle, scorer +
    minute, a rule, then the score
    strip (name tags above the crests, the score between)."""
    import fb_cards as FC
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / (H - 1)
        d.line([(0, y), (W, y)], fill=tuple(round(p + (q - p) * t) for p, q in zip(TOP, BOT)))
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse([W // 2 - 360, 300, W // 2 + 360, 780], fill=(31, 148, 211, 90))
    glow = glow.filter(ImageFilter.GaussianBlur(110))
    img.paste(glow, (0, 0), glow)

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

    # the brand, centred at the top: the «الجون» wordmark
    FC.wordmark_at(img, W / 2, 62, 76)

    # the word, with a faint echo behind it
    word = "جووووول"
    fw = FC.font("ExtraBold", 176)
    wv = FC.ar(word)
    wx = W / 2 - d.textlength(wv, font=fw) / 2
    d.text((wx + 6, 118 + 10), wv, font=fw, fill=(4, 16, 36))
    d.text((wx, 118), wv, font=fw, fill=WHITE)

    # the scoring club's crest in a glass circle
    side = ev.get("side") or "h"
    badge = ev.get("home_badge") if side == "h" else ev.get("away_badge")
    cx, cy, R = W // 2, 520, 170
    glass = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glass)
    gd.ellipse([cx - R, cy - R, cx + R, cy + R], fill=(255, 255, 255, 46), outline=(255, 255, 255, 170), width=5)
    gd.ellipse([cx - R + 22, cy - R + 16, cx - R + 136, cy - R + 62], fill=(255, 255, 255, 40))
    img.paste(glass, (0, 0), glass)
    big = _crest(badge, 236)
    if big is not None:
        img.paste(big, (cx - big.width // 2, cy - big.height // 2), big)
    else:
        text_c(cx, cy - 36, (ev.get("home") if side == "h" else ev.get("away")) or "", FC.font("ExtraBold", 50))

    # scorer + minute
    y = 724
    name = ev.get("player") or ""
    minute = minute_text(ev.get("minute"))
    tag = {"ج": "ركلة جزاء", "عكسية": "هدف عكسي"}.get(ev.get("tag") or "", "")
    fn = fit(name, "ExtraBold", 54, 600, 30)
    nw = d.textlength(FC.ar(name), font=fn)
    fm = FC.font("ExtraBold", 38)
    mark = f"{minute}'" if minute else ""     # «67'» / «45+2'»: the minute mark, like the site's rows
    chip_w = max(104, int(d.textlength(mark, font=fm)) + 36) if minute else 0
    total = nw + (chip_w + 22 if minute else 0)
    x_right = W / 2 + total / 2
    # the name first (on the right), the minute after it (on its left) - the
    # Arabic reading order; until 2026-11-05 the chip came first («67 محمد صلاح»)
    text_r(x_right, y - 6, name, fn)
    if minute:
        xl = x_right - nw - 22 - chip_w
        d.rounded_rectangle([xl, y - 2, xl + chip_w, y + 60], 12, fill=ORANGE)
        d.text((xl + chip_w / 2 - d.textlength(mark, font=fm) / 2, y + 3), mark, font=fm, fill=WHITE)
    if tag:
        text_c(W // 2, y + 68, tag, FC.font("Bold", 26), GOLD)

    # the rule (one line - the dart in its middle went with the wordmark, 2026-11-07)
    ry = 826
    d.line([(90, ry), (W - 90, ry)], fill=WHITE, width=2)

    # the score strip: name tags above the crests, the score between
    sy = 968
    for lbl, bdg, right in ((ev.get("home"), ev.get("home_badge"), True), (ev.get("away"), ev.get("away_badge"), False)):
        bx2 = W - 110 - 62 if right else 110 + 62
        d.ellipse([bx2 - 62, sy - 62, bx2 + 62, sy + 62], fill=WHITE)
        cr = _crest(bdg, 100)
        if cr is not None:
            img.paste(cr, (bx2 - cr.width // 2, sy - cr.height // 2), cr)
        f = fit(lbl or "", "Bold", 28, 220, 18)
        tw = d.textlength(FC.ar(lbl or ""), font=f)
        d.rounded_rectangle([bx2 - tw / 2 - 14, sy - 62 - 54, bx2 + tw / 2 + 14, sy - 62 - 10], 10, fill=(31, 148, 211))
        text_c(bx2, sy - 62 - 50, lbl or "", f)
    score = f"{ev.get('as')} - {ev.get('hs')}"          # home sits on the right
    fs = FC.font("ExtraBold", 92)
    d.text((W / 2 - d.textlength(score, font=fs) / 2, sy - 58), score, font=fs, fill=WHITE)

    text_l(40, H - 44, "elgoon.com", FC.font("Bold", 22), SOFT)
    text_r(W - 40, H - 44, COMP_AR.get(int(ev.get("comp") or 0), ""), FC.font("Bold", 22), SOFT)
    if out:
        img.save(out, quality=90, optimize=True)
    return img


WHISTLE_TITLE = {"ht": "نهاية الشوط الأول", "ft": "انتهت المباراة", "ko": "انطلقت المباراة",
                 "sh": "انطلق الشوط الثاني"}


WW, WH = 1080, 1350                              # the whistle card = the match poster's canvas


def colors_for(game):
    """{'home': (color, awayColor), 'away': (...)} from a 365scores game/
    detail - the clubs' OWN colours, for a club our KITS table lacks
    (matchup_card.kit_from_feed). {} when the detail has none."""
    out = {}
    for side, k in (("home", "homeCompetitor"), ("away", "awayCompetitor")):
        c = (game or {}).get(k) or {}
        if c.get("color"):
            out[side] = (c.get("color"), c.get("awayColor"))
    return out


def render_whistle(ev, out=None):
    """The kick-off / half-time / full-time card in the MATCH POSTER's design
    (user, 2026-11-22, of match_poster.py's card: «عجبنى ال design and style
    الكارت ده - عايزك تعمل الكروت بالشكل ده», for the result, half-time and
    kick-off cards). Two halves, each ONLY in its own club's colours
    (match_poster.fills: our KITS table, then the feed's colours in
    ev['feed'], then a neutral slate - never an invented colour), the crests
    on white discs, the whistle on the red tag, the score in the dark pill on
    the seam, each side's scorers under its own club, the facts in the dark
    foot band. ev = {kind 'ko'|'ht'|'ft', home, away, hs, as, comp,
    home_badge, away_badge, goals: [{s, p, m, t}], optional comp_label,
    date (YYYY-MM-DD, default today in Cairo), feed}."""
    import datetime
    from zoneinfo import ZoneInfo
    import fb_cards as FC
    import match_poster as MP
    from site_lib.dates import day_month
    W_, H_ = WW, WH
    kind = ev.get("kind") or "ft"
    home, away = ev.get("home") or "", ev.get("away") or ""
    comp_txt = ev.get("comp_label") or COMP_AR.get(int(ev.get("comp") or 0), "")
    hf, af = MP.fills(home, away, comp_txt or None, ev.get("feed"))
    img = Image.new("RGB", (W_, H_))
    MP._half(img, W_ // 2, W_, hf)             # home on the right, as on every card
    MP._half(img, 0, W_ // 2, af)
    seam = Image.new("RGBA", (W_, H_), (0, 0, 0, 0))
    ImageDraw.Draw(seam).rectangle([W_ // 2 - 26, 0, W_ // 2 + 26, H_], fill=(0, 0, 0, 70))
    seam = seam.filter(ImageFilter.GaussianBlur(22))
    img.paste(seam, (0, 0), seam)
    d = ImageDraw.Draw(img)
    INK_ = MP.INK

    def ink(c):
        # by BRIGHTNESS, not MP._light's channel sum: Leeds' yellow sums to
        # 535 (not "light") yet white text on it did not read (preview of
        # Chelsea 1-4 Leeds, 2026-11-22)
        return INK_ if 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2] > 165 else WHITE

    def text_c(cx, y, s_, f, fill=WHITE):
        s_ = FC.ar(s_); d.text((cx - d.textlength(s_, font=f) / 2, y), s_, font=f, fill=fill)

    def fit(s_, weight, size, max_w, min_size=22):
        f = FC.font(weight, size)
        while d.textlength(FC.ar(s_), font=f) > max_w and size > min_size:
            size -= 2; f = FC.font(weight, size)
        return f

    # the head: the wordmark on a white pill, the whistle on the red tag
    d.rounded_rectangle([W_ // 2 - 150, 44, W_ // 2 + 150, 136], 46, fill=WHITE, outline=(214, 222, 232), width=3)
    FC.wordmark_at(img, W_ // 2, 90, 62, anchor="mm")
    title = WHISTLE_TITLE.get(kind, WHISTLE_TITLE["ft"])
    tf = FC.font("ExtraBold", 38)
    tw = d.textlength(FC.ar(title), font=tf)
    d.rounded_rectangle([W_ // 2 - tw / 2 - 30, 156, W_ // 2 + tw / 2 + 30, 222], 33, fill=MP.RED)
    text_c(W_ // 2, 164, title, tf)

    # the two crests on white discs, the names under them
    cy, r = 470, 170
    for name, badge, cx, fill in ((home, ev.get("home_badge"), W_ * 3 // 4, hf),
                                  (away, ev.get("away_badge"), W_ // 4, af)):
        sh = Image.new("RGBA", (W_, H_), (0, 0, 0, 0))
        ImageDraw.Draw(sh).ellipse([cx - r + 6, cy - r + 16, cx + r + 6, cy + r + 16], fill=(0, 0, 0, 110))
        sh = sh.filter(ImageFilter.GaussianBlur(16))
        img.paste(sh, (0, 0), sh)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=WHITE, outline=(214, 222, 232), width=4)
        cr = _crest(badge, int(2 * r * 0.72))
        if cr is not None:
            img.paste(cr, (cx - cr.width // 2, cy - cr.height // 2), cr)
        else:
            f1 = FC.font("ExtraBold", int(r * 0.9))
            s1 = FC.ar(name.strip()[:1] or "?")
            d.text((cx - d.textlength(s1, font=f1) / 2, cy - r * 0.6), s1, font=f1, fill=INK_)
        text_c(cx, cy + r + 30, name, fit(name, "ExtraBold", 66, W_ // 2 - 70, 30), ink(fill))

    # the score on the seam: a DARK pill with a white edge (it sits over two
    # colours, either of which may be white). Home on the right.
    hs, as_ = ev.get("hs"), ev.get("as")
    score = f"{as_ if as_ is not None else 0} - {hs if hs is not None else 0}"
    sf = FC.font("ExtraBold", 104)
    sw = d.textlength(score, font=sf)
    py0, py1 = 790, 930
    d.rounded_rectangle([W_ // 2 - sw / 2 - 44, py0, W_ // 2 + sw / 2 + 44, py1], 70, fill=INK_, outline=WHITE, width=5)
    bx = d.textbbox((0, 0), score, font=sf)
    d.text((W_ // 2 - (bx[0] + bx[2]) / 2, (py0 + py1) / 2 - (bx[1] + bx[3]) / 2), score, font=sf, fill=WHITE)

    # each side's scorers under its own club, in that half's ink
    goals = ev.get("goals") or []

    def line_of(g):
        t = {"ج": " (ج)", "عكسية": " (عكسي)"}.get(g.get("t") or "", "")
        mn = minute_text(g.get("m"))
        return f"{g.get('p') or ''} {mn}'{t}" if mn else f"{g.get('p') or ''}{t}"
    for side_, cx, fill in (("h", W_ * 3 // 4, hf), ("a", W_ // 4, af)):
        rows = [line_of(g) for g in goals if g.get("s") == side_ and g.get("p")]
        if len(rows) > 4:
            rows = rows[:3] + [f"+{len(rows) - 3}"]
        yy = 958
        for row in rows:
            f = fit(row, "Bold", 34, W_ // 2 - 110, 22)
            rw = d.textlength(FC.ar(row), font=f)
            x_r = cx + rw / 2
            d.ellipse([x_r + 12, yy + 16, x_r + 26, yy + 30], fill=ink(fill))
            text_c(cx, yy, row, f, ink(fill))
            yy += 54

    # the foot: a dark band, so the facts read whatever the two colours are
    band = Image.new("RGBA", (W_, H_), (0, 0, 0, 0))
    ImageDraw.Draw(band).rectangle([0, 1196, W_, H_], fill=(8, 18, 40, 215))
    img.paste(band, (0, 0), band)
    date = ev.get("date") or datetime.datetime.now(ZoneInfo("Africa/Cairo")).date().isoformat()
    try:
        day = day_month(date, weekday=True)
    except Exception:                                       # noqa: BLE001 - an odd date string
        day = ""
    line1 = " · ".join(x for x in (comp_txt, day) if x)
    if line1:
        text_c(W_ // 2, 1216, line1, fit(line1, "ExtraBold", 40, W_ - 100), WHITE)
    # one script a line (an Arabic sentence with a Latin address came out in
    # the wrong order on the poster)
    line2 = "تابع المباراة لحظة بلحظة على الموقع" if kind in ("ko", "sh") else "elgoon.com"
    text_c(W_ // 2, 1280, line2, fit(line2, "Bold", 32, W_ - 100), (214, 226, 240))
    if out:
        img.save(out, quality=90, optimize=True)
    return img


def render_whistle_bytes(ev):
    img = render_whistle(ev)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90, optimize=True)
    return buf.getvalue()


def render_bytes(ev):
    img = render(ev)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90, optimize=True)
    return buf.getvalue()


def event_from_args(a, game):
    hb, ab = badges_for(game)
    return {"side": a.side, "player": a.player, "minute": a.minute, "tag": a.tag,
            "home": a.home or (game.get("homeCompetitor") or {}).get("name", ""),
            "away": a.away or (game.get("awayCompetitor") or {}).get("name", ""),
            "hs": a.hs, "as": a.as_, "comp": a.comp or game.get("competitionId") or 0,
            "home_badge": hb, "away_badge": ab}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--game"); ap.add_argument("--fixture")
    ap.add_argument("--side", default="h"); ap.add_argument("--player", default="")
    ap.add_argument("--minute", default=""); ap.add_argument("--tag", default="")
    ap.add_argument("--home", default=""); ap.add_argument("--away", default="")
    ap.add_argument("--hs", type=int, default=0); ap.add_argument("--as", dest="as_", type=int, default=0)
    ap.add_argument("--comp", type=int, default=0)
    ap.add_argument("--out", default=os.path.join(HERE, "data", "briefs", "goal.jpg"))
    a = ap.parse_args()
    if a.fixture:
        game = json.load(open(a.fixture, encoding="utf-8")).get("game") or {}
    elif a.game:
        game = _s365_game(a.game)
    else:
        game = {}
    render(event_from_args(a, game), a.out)
    print(a.out)


if __name__ == "__main__":
    main()
