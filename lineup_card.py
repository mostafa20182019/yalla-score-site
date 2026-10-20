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
`fb_post.py --xi` renders this and posts it.

2026-10-20 (user: «نزل صورة ملعب عليه اللاعيبة وصورهم ... زى 365scores»):
each disc is the player's photo from the feed's athlete images
(imagecache.365scores.com, the same host our crests come from), ringed in
the kit colour with the number in a small badge; a player the feed has no
photo of (it answers its default silhouette) keeps the numbered disc. And
a side the feed lists WITHOUT field positions (Zamalek that day: eleven
names, no formation yet) no longer sends the post out as text: the eleven
are laid out from the announced formation (4-3-3 -> rows of 4, 3, 3 in the
feed's order) or, with no formation either, from their position groups
(defenders / midfielders / attackers), and the foot of the card says the
arrangement is approximate. None only when a side is short of eleven names.
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

# the pitch rectangle on the card: the header above it was compacted on
# 2026-10-20 so that five lines of photo discs (keeper + four) fit a half
PITCH = (60, 292, W - 60, H - 80)                       # x0, y0, x1, y1
R = 33                                                  # the photo disc radius
HEADSHOT = ("https://imagecache.365scores.com/image/upload/"
            "f_png,w_120,h_120,c_limit,q_auto:eco,dpr_2,d_Athletes:default.png,r_max,c_thumb,g_face,z_0.65/"
            "v{v}/Athletes/{id}")
POS_ROWS = ((2, "DF"), (3, "MF"), (4, "FW"))            # the feed's position ids, keeper = 1


def _s365_game(gid):
    """The game/ detail from 365scores (the runner's network; blocked at the
    office - use --fixture there)."""
    import fetch_data as fd
    return fd._s365(f"game/?appTypeId=5&langId=27&timezoneName=Africa/Cairo&gameId={gid}").get("game") or {}


def _badge(c):
    import fetch_data as fd
    return fd._s365_badge(c) if c.get("id") else None


def formation_rows(formation, n_out):
    """'4-2-3-1' -> [4, 2, 3, 1] when it accounts for exactly the n_out
    outfield players, else None."""
    try:
        rows = [int(x) for x in str(formation or "").replace("–", "-").split("-") if x.strip()]
    except ValueError:
        return None
    return rows if rows and all(r > 0 for r in rows) and sum(rows) == n_out else None


def derive_positions(players, formation):
    """Field coordinates for starters the feed lists without any: the keeper
    on the goal line, the outfield rows from the announced formation (in
    the feed's order, which runs defence -> attack) or, without one, from
    the position groups. Mutates the players (x, y) and returns True when
    it could place all of them."""
    gks = [p for p in players if p.get("pos") == 1]
    outs = [p for p in players if p.get("pos") != 1]
    if len(gks) != 1:
        return False
    rows = formation_rows(formation, len(outs))
    if rows:
        groups, i = [], 0
        for r in rows:
            groups.append(outs[i:i + r]); i += r
    else:
        groups = [[p for p in outs if p.get("pos") == pid] for pid, _ in POS_ROWS]
        groups = [g for g in groups if g]
        if sum(len(g) for g in groups) != len(outs):
            return False
    gks[0]["x"], gks[0]["y"] = 50.0, 0.0
    n = len(groups)
    for i, g in enumerate(groups):
        y = 100.0 * (i + 1) / n
        for j, p in enumerate(g):
            p["x"], p["y"] = 100.0 * (j + 0.5) / len(g), y
    return True


def parse(game):
    """{"comp", "comp_id", "start", "home": side, "away": side} or None.
    side = {"name", "formation", "colour", "alt", "badge", "derived",
    "players": [{"name", "no", "x", "y", "athlete", "img_v", "pos"}]} with
    exactly eleven named starters; positions from the feed when it has
    them, derived from the formation / position groups otherwise
    ("derived": True). None when a side is short of eleven names or the
    eleven cannot be placed."""
    members = {}
    for m in game.get("members") or []:
        members[m.get("id")] = m
    out = {"comp": (game.get("competitionDisplayName") or "").split(",")[-1].strip(),
           "comp_id": game.get("competitionId") or 0, "start": game.get("startTime") or ""}
    for key, side in (("home", "homeCompetitor"), ("away", "awayCompetitor")):
        c = game.get(side) or {}
        lu = c.get("lineups") or {}
        if not isinstance(lu, dict):
            return None
        players, positioned = [], bool(lu.get("hasFieldPositions"))
        for mm in lu.get("members") or []:
            if mm.get("status") != 1:
                continue
            m = members.get(mm.get("id") or mm.get("playerId") or mm.get("athleteId")) or {}
            name = (m.get("shortName") or m.get("name") or "").replace("\t", " ").strip()
            if not name:
                return None
            p = {"name": name, "no": m.get("jerseyNumber"), "athlete": m.get("athleteId"),
                 "img_v": m.get("imageVersion"), "pos": (mm.get("position") or {}).get("id")}
            yf = mm.get("yardFormation") or {}
            if yf.get("fieldLine") is None or yf.get("fieldSide") is None:
                positioned = False
            else:
                p["x"], p["y"] = float(yf["fieldSide"]), float(yf["fieldLine"])
            players.append(p)
        if len(players) != 11:
            return None
        formation = lu.get("formation") or ""
        if not positioned and not derive_positions(players, formation):
            return None
        out[key] = {"name": (c.get("name") or "").strip(), "formation": formation,
                    "colour": c.get("color"), "alt": c.get("awayColor"), "badge": _badge(c),
                    "derived": not positioned, "players": players}
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


# ------------------------------------------------------------ headshots
_HS = {}                                                # url -> bytes | None, per process


def fetch_bytes(url, timeout=10):
    """GET -> bytes (tests replace this)."""
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                                            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
                                               "Referer": "https://www.365scores.com/"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def headshot_url(p):
    return HEADSHOT.format(v=p.get("img_v") or 1, id=p["athlete"]) if p.get("athlete") else None


def headshots(players, size, workers=8):
    """{athlete id: RGBA disc of `size`} for the players the feed has a real
    photo of. The feed answers its default silhouette for the others
    (d_Athletes:default.png) - that is fetched once under athlete 0 and any
    photo identical to it counts as missing. A network error on a photo
    just leaves that player on the numbered disc."""
    from concurrent.futures import ThreadPoolExecutor
    want = [(p["athlete"], headshot_url(p)) for p in players if headshot_url(p)]
    if not want:
        return {}
    default_url = HEADSHOT.format(v=1, id=0)

    def get(url):
        if url not in _HS:
            try:
                _HS[url] = fetch_bytes(url)
            except Exception:                           # noqa: BLE001
                _HS[url] = None
        return _HS[url]
    with ThreadPoolExecutor(max_workers=workers) as ex:
        default = get(default_url)
        got = list(ex.map(get, [u for _, u in want]))
    out = {}
    for (aid, _), raw in zip(want, got):
        if not raw or raw == default:
            continue
        try:
            im = Image.open(io.BytesIO(raw)).convert("RGBA")
        except Exception:                               # noqa: BLE001
            continue
        im = im.resize((size, size), Image.LANCZOS)
        mask = Image.new("L", (size, size), 0)
        ImageDraw.Draw(mask).ellipse([0, 0, size - 1, size - 1], fill=255)
        disc = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        disc.paste(im, (0, 0), mask)
        out[aid] = disc
    return out


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
    padx = 90
    # the strip either side of halfway no disc enters: the top side's names
    # hang towards halfway, so its forwards stop earlier than the bottom side's
    gap = 72 if top else 42
    pady = 42 if top else 76                # the bottom keeper's name sits under his disc, inside the pitch
    my = (y0 + y1) / 2
    span = (my - y0) - pady - gap           # keeper line -> forward line, per half
    out = []
    for p in side["players"]:
        x = x0 + padx + (x1 - x0 - 2 * padx) * p["x"] / 100
        y = (y0 + pady + span * p["y"] / 100) if top else (y1 - pady - span * p["y"] / 100)
        out.append((x, y, p))
    return out


def render(data, out, photos_on=True):
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
    fb = FC.font("ExtraBold", 40)
    bn = FC.ar("يلا سكور")
    bw = d.textlength(bn, font=fb)
    bx0 = W / 2 - (bw + 64) / 2
    ball(52, int(bx0 + bw + 64 - 26), 52)
    d.text((bx0, 30), bn, font=fb, fill=WHITE)
    tv = FC.ar("التشكيل الرسمي")
    fh = FC.font("ExtraBold", 80)
    tx = W / 2 - d.textlength(tv, font=fh) / 2
    d.text((tx + 4, 88 + 6), tv, font=fh, fill=(4, 16, 36))
    d.text((tx, 88), tv, font=fh, fill=WHITE)
    when = ""
    try:
        from zoneinfo import ZoneInfo
        import matchup_card as MC
        dt = datetime.datetime.fromisoformat(data["start"].replace("Z", "+00:00")).astimezone(ZoneInfo("Africa/Cairo"))
        when = MC.when_ar(dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M"))
    except Exception:                                   # noqa: BLE001
        when = ""
    sub_ = " · ".join(x for x in (data["comp"] or "", when) if x)
    text_c(W // 2, 176, sub_, FC.font("Bold", 26), GOLD)
    ry = 222
    d.line([(90, ry), (W / 2 - 40, ry)], fill=WHITE, width=2)
    d.line([(W / 2 + 40, ry), (W - 90, ry)], fill=WHITE, width=2)
    ball(48, W // 2, ry)

    # the two club bars: home right (RTL), away left
    hy = 226
    for side, right in ((data["home"], True), (data["away"], False)):
        cx = W - 40 - 32 if right else 40 + 32
        crest(cx, hy + 26, 30, side)
        f = fit(side["name"], "ExtraBold", 30, 340)
        if right:
            text_r(cx - 44, hy + 2, side["name"], f)
            text_r(cx - 44, hy + 38, side["formation"], FC.font("Bold", 21), SOFT)
        else:
            text_l(cx + 44, hy + 2, side["name"], f)
            text_l(cx + 44, hy + 38, side["formation"], FC.font("Bold", 21), SOFT)

    _pitch(img, d)
    fn = FC.font("Bold", 20)
    fno = FC.font("ExtraBold", 26)
    fbadge = FC.font("ExtraBold", 15)
    photos = {} if not photos_on else headshots(data["home"]["players"] + data["away"]["players"], 2 * R - 6)
    for side, top in ((data["home"], True), (data["away"], False)):
        col = kit_colour(side, data.get("comp_id"))
        ink = WHITE if _lum(col) < 0.6 else (20, 24, 40)
        for x, y, p in _place(side, top):
            x, y = int(x), int(y)
            sh = Image.new("RGBA", (2 * R + 30, 2 * R + 30), (0, 0, 0, 0))
            ImageDraw.Draw(sh).ellipse([18, 21, 18 + 2 * R, 21 + 2 * R], fill=(0, 0, 0, 110))
            sh = sh.filter(ImageFilter.GaussianBlur(5))
            img.paste(sh, (x - R - 15, y - R - 15), sh)
            no = str(p["no"]) if p.get("no") not in (None, "") else ""
            ph = photos.get(p.get("athlete"))
            if ph is not None:
                # the photo inside a ring of the kit colour, the number in a
                # small badge at the lower left (365scores' arrangement)
                d.ellipse([x - R, y - R, x + R, y + R], fill=col, outline=WHITE, width=2)
                img.paste(ph, (x - ph.width // 2, y - ph.height // 2), ph)
                if no:
                    br = 13
                    bx, by = x - R + br - 2, y + R - br + 2
                    d.ellipse([bx - br, by - br, bx + br, by + br], fill=col, outline=WHITE, width=2)
                    d.text((bx - d.textlength(no, font=fbadge) / 2, by - 10), no, font=fbadge, fill=ink)
            else:
                d.ellipse([x - R, y - R, x + R, y + R], fill=col, outline=WHITE, width=3)
                if no:
                    d.text((x - d.textlength(no, font=fno) / 2, y - 17), no, font=fno, fill=ink)
            name = FC.ar(p["name"])
            f = fn
            while d.textlength(name, font=f) > 140 and f.size > 15:
                f = FC.font("Bold", f.size - 1)
            tw = d.textlength(name, font=f)
            lh = f.size + 8
            ov = Image.new("RGBA", (int(tw) + 20, lh), (0, 0, 0, 0))
            ImageDraw.Draw(ov).rounded_rectangle([0, 0, int(tw) + 19, lh - 1], 7, fill=(0, 0, 0, 150))
            img.paste(ov, (int(x - tw / 2) - 10, y + R + 2), ov)
            d.text((x - tw / 2, y + R + 3), name, font=f, fill=WHITE)

    text_l(40, H - 52, "yallascore.site", FC.font("Bold", 22), SOFT)
    note = ("ترتيب اللاعبين تقريبي حسب الخطة المعلنة" if data["home"].get("derived") or data["away"].get("derived")
            else "التشكيل كما أعلنه الناديان قبل المباراة")
    text_r(W - 40, H - 52, note, FC.font("Regular", 22), DIM)
    if out:
        img.save(out, quality=90, optimize=True)
    return img


def render_bytes(data, photos_on=True):
    img = render(data, None, photos_on)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90, optimize=True)
    return buf.getvalue()


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", help="365scores game id")
    ap.add_argument("--fixture", help="a saved game/ detail JSON instead of the network")
    ap.add_argument("--out", default=os.path.join(HERE, "data", "briefs", "xi.jpg"))
    ap.add_argument("--no-photos", action="store_true", help="numbered discs only (offline)")
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
        sys.exit("no full XI on both sides yet")
    render(data, a.out, not a.no_photos)
    print(a.out, data["home"]["name"], data["home"]["formation"], "x", data["away"]["name"], data["away"]["formation"])


if __name__ == "__main__":
    main()
