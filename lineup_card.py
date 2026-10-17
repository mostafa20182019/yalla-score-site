#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The official line-ups on a pitch - the photo of the «📋 التشكيل الرسمي»
Facebook post (user, 2026-10-17: «ينفع تحط صورة ملعب واللاعيبة اللى فى
التشكيلة متوزعين فيها؟»).

    python lineup_card.py --game 4742043 --out xi.jpg
    python lineup_card.py --fixture tests/fixtures/game_4742043_lineups.json --out xi.jpg

Everything on the card comes from 365scores' game/ detail: each starter
carries `yardFormation {fieldLine 0..100, fieldSide 0..100}` (the feed's own
pitch coordinates), a jersey number and a short name; the competitor carries
its colours. A 1080x1350 portrait: header (competition, date), the two
clubs' bars (crest, name, formation), a vertical pitch with the home side in
the top half (keeper at the top edge) and the away side in the bottom half
(keeper at the bottom), one disc per starter in the kit colour with the
number inside and the name beneath, the brand row at the foot.

The Worker (liveposts.js) knows the moment both XIs are announced; it holds
the "xi" lock and dispatches fb-post.yml with `xi=<game id>`, and
`fb_post.py --xi` renders this and posts it. No field positions on either
side = None, and the caller falls back to the text post.
"""
import argparse
import datetime
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from PIL import Image, ImageDraw, ImageFilter          # noqa: E402

W, H = 1080, 1350
TOP, BOT = (16, 62, 108), (5, 20, 40)                  # the brand canvas (day_card's)
WHITE, SOFT, DIM = (255, 255, 255), (205, 222, 238), (150, 172, 196)
GOLD = (246, 192, 60)
GRASS_A, GRASS_B = (34, 120, 68), (30, 108, 60)        # mown stripes
LINE = (235, 245, 238)

# the pitch rectangle on the card
PITCH = (60, 372, W - 60, H - 80)                       # x0, y0, x1, y1 - under the restyled header (2026-10-17)


def _s365_game(gid):
    """The game/ detail from 365scores (the runner's network; blocked at the
    office - use --fixture there)."""
    import fetch_data as fd
    return fd._s365(f"game/?appTypeId=5&langId=27&timezoneName=Africa/Cairo&gameId={gid}").get("game") or {}


def _badge(c):
    import fetch_data as fd
    return fd._s365_badge(c) if c.get("id") else None


def parse(game):
    """{"comp", "comp_id", "start", "home": side, "away": side} or None.
    side = {"name", "formation", "colour", "alt", "badge", "players":
    [{"name", "no", "x", "y"}]} with exactly eleven positioned starters."""
    members = {}
    for m in game.get("members") or []:
        members[m.get("id")] = m
    out = {"comp": (game.get("competitionDisplayName") or "").split(",")[-1].strip(),
           "comp_id": game.get("competitionId") or 0, "start": game.get("startTime") or ""}
    for key, side in (("home", "homeCompetitor"), ("away", "awayCompetitor")):
        c = game.get(side) or {}
        lu = c.get("lineups") or {}
        if not isinstance(lu, dict) or not lu.get("hasFieldPositions"):
            return None
        players = []
        for mm in lu.get("members") or []:
            if mm.get("status") != 1:
                continue
            yf = mm.get("yardFormation") or {}
            if yf.get("fieldLine") is None or yf.get("fieldSide") is None:
                return None
            m = members.get(mm.get("id") or mm.get("playerId") or mm.get("athleteId")) or {}
            name = (m.get("shortName") or m.get("name") or "").replace("\t", " ").strip()
            if not name:
                return None
            players.append({"name": name, "no": m.get("jerseyNumber"),
                            "x": float(yf["fieldSide"]), "y": float(yf["fieldLine"])})
        if len(players) != 11:
            return None
        out[key] = {"name": (c.get("name") or "").strip(), "formation": lu.get("formation") or "",
                    "colour": c.get("color"), "alt": c.get("awayColor"), "badge": _badge(c),
                    "players": players}
    return out


def parse_names(game):
    """Like parse() but without positions - eleven named starters per side,
    for the text fallback. None when either side is short."""
    members = {m.get("id"): m for m in game.get("members") or []}
    out = {"comp": (game.get("competitionDisplayName") or "").split(",")[-1].strip()}
    for key, side in (("home", "homeCompetitor"), ("away", "awayCompetitor")):
        c = game.get(side) or {}
        lu = c.get("lineups") or {}
        if not isinstance(lu, dict):
            return None
        names = []
        for mm in lu.get("members") or []:
            if mm.get("status") != 1:
                continue
            m = members.get(mm.get("id") or mm.get("playerId") or mm.get("athleteId")) or {}
            n = (m.get("name") or m.get("shortName") or "").replace("\t", " ").strip()
            if n:
                names.append({"name": n})
        if len(names) != 11:
            return None
        out[key] = {"name": (c.get("name") or "").strip(), "formation": lu.get("formation") or "", "players": names}
    return out


# ------------------------------------------------------------------ drawing
def _hex(h):
    h = (h or "").strip().lstrip("#")
    try:
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) if len(h) == 6 else None
    except ValueError:
        return None


def _lum(c):
    return (0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]) / 255


def kit_colour(side, comp_id=None):
    """The disc colour: our KITS table when the club is in it (matchup_card),
    else the feed's main colour; a colour too close to the grass takes the
    feed's alternate."""
    import matchup_card as MC
    kit = MC.KITS.get(side["name"])
    col = kit[1][0] if kit else (_hex(side.get("colour")) or (235, 235, 235))
    if abs(col[1] - 115) < 45 and col[0] < 90 and col[2] < 100:     # a green kit on green grass
        col = _hex(side.get("alt")) or (255, 255, 255)
    return col


def _pitch(img, d):
    x0, y0, x1, y1 = PITCH
    stripes = 12
    sh = (y1 - y0) / stripes
    for i in range(stripes):
        d.rectangle([x0, y0 + i * sh, x1, y0 + (i + 1) * sh], fill=GRASS_A if i % 2 == 0 else GRASS_B)
    lw = 4
    d.rectangle([x0, y0, x1, y1], outline=LINE, width=lw)
    my = (y0 + y1) // 2
    d.line([(x0, my), (x1, my)], fill=LINE, width=lw)
    cx = (x0 + x1) // 2
    d.ellipse([cx - 90, my - 90, cx + 90, my + 90], outline=LINE, width=lw)
    d.ellipse([cx - 6, my - 6, cx + 6, my + 6], fill=LINE)
    pw, ph = 420, 120                                   # penalty boxes
    gw, gh = 180, 48                                    # goal areas
    for top in (True, False):
        yy = y0 if top else y1
        s = 1 if top else -1
        box = lambda w, h: [cx - w // 2, min(yy, yy + s * h), cx + w // 2, max(yy, yy + s * h)]
        d.rectangle(box(pw, ph), outline=LINE, width=lw)
        d.rectangle(box(gw, gh), outline=LINE, width=lw)
        d.ellipse([cx - 6, yy + s * 82 - 6, cx + 6, yy + s * 82 + 6], fill=LINE)


def _place(side, top):
    """pixel (x, y) per player: the feed's fieldSide across the pitch, its
    fieldLine from the keeper's goal line towards the halfway line."""
    x0, y0, x1, y1 = PITCH
    padx, pady, gap = 90, 54, 66            # gap = the strip either side of halfway no disc enters
    my = (y0 + y1) / 2
    span = (my - y0) - pady - gap           # keeper line -> forward line, per half
    out = []
    for p in side["players"]:
        x = x0 + padx + (x1 - x0 - 2 * padx) * p["x"] / 100
        y = (y0 + pady + span * p["y"] / 100) if top else (y1 - pady - span * p["y"] / 100)
        out.append((x, y, p))
    return out


def render(data, out):
    import fb_cards as FC
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / (H - 1)
        d.line([(0, y), (W, y)], fill=tuple(round(p + (q - p) * t) for p, q in zip(TOP, BOT)))

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
    def crest(cx, cy, r, side):
        im = None
        try:
            im = FC.crest_image(side.get("badge"), int(2 * r * 0.78)) if side.get("badge") else None
        except Exception:                               # noqa: BLE001
            im = None
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=WHITE)
        if im is not None:
            img.paste(im, (cx - im.width // 2, cy - im.height // 2), im)
        else:
            f = FC.font("ExtraBold", int(r * 0.9))
            s = FC.ar((side["name"] or "?").strip()[:1])
            d.text((cx - d.textlength(s, font=f) / 2, cy - r * 0.6), s, font=f, fill=TOP)

    # the header in the goal card's style (user, 2026-10-17: «نفس الصورة لبوست
    # التشكيلة»): the brand centred at the top, the big shadowed headline,
    # the rule with the ball logo, then the two clubs (crest, name, formation)
    icon = Image.open(os.path.join(HERE, "assets-src", "app-icon-1024.png")).convert("RGB")
    def ball(size, bx, by):
        b = icon.crop((218, 105, 806, 693)).resize((size, size), Image.LANCZOS)
        m = Image.new("L", (size, size), 0)
        ImageDraw.Draw(m).ellipse([0, 0, size - 1, size - 1], fill=255)
        img.paste(b, (bx - size // 2, by - size // 2), m)
    fb = FC.font("ExtraBold", 44)
    bn = FC.ar("يلا سكور")
    bw = d.textlength(bn, font=fb)
    bx0 = W / 2 - (bw + 70) / 2
    ball(58, int(bx0 + bw + 70 - 29), 62)
    d.text((bx0, 38), bn, font=fb, fill=WHITE)
    tv = FC.ar("التشكيل الرسمي")
    fh = FC.font("ExtraBold", 112)
    tx = W / 2 - d.textlength(tv, font=fh) / 2
    d.text((tx + 5, 112 + 8), tv, font=fh, fill=(4, 16, 36))
    d.text((tx, 112), tv, font=fh, fill=WHITE)
    when = ""
    try:
        from zoneinfo import ZoneInfo
        import matchup_card as MC
        dt = datetime.datetime.fromisoformat(data["start"].replace("Z", "+00:00")).astimezone(ZoneInfo("Africa/Cairo"))
        when = MC.when_ar(dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M"))
    except Exception:                                   # noqa: BLE001
        when = ""
    sub_ = " · ".join(x for x in (data["comp"] or "", when) if x)
    text_c(W // 2, 236, sub_, FC.font("Bold", 28), GOLD)
    ry = 292
    d.line([(90, ry), (W / 2 - 46, ry)], fill=WHITE, width=2)
    d.line([(W / 2 + 46, ry), (W - 90, ry)], fill=WHITE, width=2)
    ball(56, W // 2, ry)

    # the two club bars: home right (RTL), away left
    hy = 304
    for side, right in ((data["home"], True), (data["away"], False)):
        cx = W - 40 - 32 if right else 40 + 32
        crest(cx, hy + 26, 32, side)
        f = fit(side["name"], "ExtraBold", 32, 340)
        if right:
            text_r(cx - 46, hy + 2, side["name"], f)
            text_r(cx - 46, hy + 40, side["formation"], FC.font("Bold", 22), SOFT)
        else:
            text_l(cx + 46, hy + 2, side["name"], f)
            text_l(cx + 46, hy + 40, side["formation"], FC.font("Bold", 22), SOFT)

    _pitch(img, d)
    R = 27
    fn = FC.font("Bold", 23)
    fno = FC.font("ExtraBold", 24)
    for side, top in ((data["home"], True), (data["away"], False)):
        col = kit_colour(side, data.get("comp_id"))
        ink = WHITE if _lum(col) < 0.6 else (20, 24, 40)
        for x, y, p in _place(side, top):
            x, y = int(x), int(y)
            sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            ImageDraw.Draw(sh).ellipse([x - R + 3, y - R + 6, x + R + 3, y + R + 6], fill=(0, 0, 0, 110))
            sh = sh.filter(ImageFilter.GaussianBlur(5))
            img.paste(sh, (0, 0), sh)
            d.ellipse([x - R, y - R, x + R, y + R], fill=col, outline=WHITE, width=3)
            no = str(p["no"]) if p.get("no") not in (None, "") else ""
            if no:
                d.text((x - d.textlength(no, font=fno) / 2, y - 16), no, font=fno, fill=ink)
            name = FC.ar(p["name"])
            f = fn
            while d.textlength(name, font=f) > 150 and f.size > 16:
                f = FC.font("Bold", f.size - 2)
            tw = d.textlength(name, font=f)
            ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            ImageDraw.Draw(ov).rounded_rectangle([x - tw / 2 - 8, y + R + 4, x + tw / 2 + 8, y + R + 4 + f.size + 10], 8, fill=(0, 0, 0, 150))
            img.paste(ov, (0, 0), ov)
            d.text((x - tw / 2, y + R + 7), name, font=f, fill=WHITE)

    text_l(40, H - 52, "yallascore.site", FC.font("Bold", 22), SOFT)
    text_r(W - 40, H - 52, "التشكيل كما أعلنه الناديان قبل المباراة", FC.font("Regular", 22), DIM)
    if out:
        img.save(out, quality=90, optimize=True)
    return img


def render_bytes(data):
    img = render(data, None)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90, optimize=True)
    return buf.getvalue()


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", help="365scores game id")
    ap.add_argument("--fixture", help="a saved game/ detail JSON instead of the network")
    ap.add_argument("--out", default=os.path.join(HERE, "data", "briefs", "xi.jpg"))
    a = ap.parse_args()
    if a.fixture:
        with open(a.fixture, encoding="utf-8") as fh:
            game = json.load(fh).get("game") or {}
    elif a.game:
        game = _s365_game(a.game)
    else:
        sys.exit("--game or --fixture")
    data = parse(game)
    if not data:
        sys.exit("no positioned XI on both sides yet")
    render(data, a.out)
    print(a.out, data["home"]["name"], data["home"]["formation"], "x", data["away"]["name"], data["away"]["formation"])


if __name__ == "__main__":
    main()
