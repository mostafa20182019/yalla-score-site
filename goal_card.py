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


def render(ev, out=None):
    """ev = {side 'h'|'a', player, minute, tag, home, away, hs, as, comp,
    home_badge, away_badge}. Returns the PIL image (and saves to `out`).
    Layout = the user's reference (2026-10-17, «اعمل زيها بالظبط»): the brand
    centred at the top, the word, the crest in a glass circle, scorer +
    minute, a rule with the site's ball logo in its middle, then the score
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

    icon = Image.open(os.path.join(HERE, "assets-src", "app-icon-1024.png")).convert("RGB")
    def ball(size, cx, cy):
        b = icon.crop((218, 105, 806, 693)).resize((size, size), Image.LANCZOS)
        m = Image.new("L", (size, size), 0)
        ImageDraw.Draw(m).ellipse([0, 0, size - 1, size - 1], fill=255)
        img.paste(b, (cx - size // 2, cy - size // 2), m)

    # the brand, centred at the top (ball + name)
    fb = FC.font("ExtraBold", 44)
    bn = FC.ar("يلا سكور")
    bw = d.textlength(bn, font=fb)
    bx = W / 2 - (bw + 70) / 2
    ball(58, int(bx + bw + 70 - 29), 62)
    d.text((bx, 38), bn, font=fb, fill=WHITE)

    # the word, with a faint echo behind it
    word = "جووووول"
    fw = FC.font("ExtraBold", 176)
    wv = FC.ar(word)
    wx = W / 2 - d.textlength(wv, font=fw) / 2
    d.text((wx + 6, 118 + 10), wv, font=fw, fill=(4, 16, 36))
    d.text((wx, 118), wv, font=fw, fill=WHITE)
    echo = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ed = ImageDraw.Draw(echo)
    fe = FC.font("ExtraBold", 110)
    for yy in (360, 480, 600):
        ed.text((W / 2 - ed.textlength(wv, font=fe) / 2, yy), wv, font=fe, fill=(255, 255, 255, 14))
    img.paste(echo, (0, 0), echo)

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
    minute = str(ev.get("minute") or "").replace("'", "")
    tag = {"ج": "ركلة جزاء", "عكسية": "هدف عكسي"}.get(ev.get("tag") or "", "")
    fn = fit(name, "ExtraBold", 54, 600, 30)
    nw = d.textlength(FC.ar(name), font=fn)
    chip_w = 104 if minute else 0
    total = nw + (chip_w + 22 if minute else 0)
    x_right = W / 2 + total / 2
    if minute:
        d.rounded_rectangle([x_right - chip_w, y - 2, x_right, y + 60], 12, fill=ORANGE)
        fm = FC.font("ExtraBold", 38)
        d.text((x_right - chip_w / 2 - d.textlength(minute, font=fm) / 2, y + 3), minute, font=fm, fill=WHITE)
        x_right -= chip_w + 22
    text_r(x_right, y - 6, name, fn)
    if tag:
        text_c(W // 2, y + 68, tag, FC.font("Bold", 26), GOLD)

    # the rule with the site's ball in its middle
    ry = 826
    d.line([(90, ry), (W / 2 - 46, ry)], fill=WHITE, width=2)
    d.line([(W / 2 + 46, ry), (W - 90, ry)], fill=WHITE, width=2)
    ball(56, W // 2, ry)

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

    text_l(40, H - 44, "yallascore.site", FC.font("Bold", 22), SOFT)
    text_r(W - 40, H - 44, COMP_AR.get(int(ev.get("comp") or 0), ""), FC.font("Bold", 22), SOFT)
    if out:
        img.save(out, quality=90, optimize=True)
    return img


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
