#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A club's FORM card (user example 2026-11-09, an image from another page: a
club's last results as ✅/❌ marks, a photo, the next fixture under them).

1080x1350, the cards' family (day_card / h2h_card: the blue gradient, the
wordmark, Almarai, the white crest discs) with the CLUB's own colour as the
accent - the top rule, the glow, the ring around its crest - from the kit
table in matchup_card (facts, never an invented colour). One row per result,
newest at the top: the mark (a green ✅ / grey ➖ / red ❌ disc, drawn, not a
font glyph), the opponent's crest and name, the score with the club's goals
on the RIGHT of the dash (the RTL rule of every card), the competition and
the date small on the left. The next fixture closes the card: both crests,
the Arabic day and date, the Cairo time.

The photo, when there is one, comes ONLY from team-photos/<slug>/ (the
editor's folder, credited in data/team_photos.json) - a non-person picture
(stadium, fans, kit), never a player, since no player is named: the living-
story and identity rules. Without one the card is crest-only. Press photos
are a copyright no-go and never looked for.

Everything on the card is the event story_events.club_form_before_match
built from the data files: the rows, the record, the fixture.

    python form_card.py --club barcelona --out /tmp/form-barcelona.png        # the next fixture, any day
    python form_card.py --club al-ahly --out x.png --no-photo                  # crest-only on purpose
    python form_card.py --all --out-dir media/form                             # one per curated club
"""
import argparse
import datetime
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
from PIL import Image, ImageDraw, ImageFilter          # noqa: E402

W, H = 1080, 1350
TOP, BOT = (16, 62, 108), (5, 20, 40)
WHITE, SOFT, DIM = (255, 255, 255), (205, 222, 238), (150, 172, 196)
GOLD = (246, 192, 60)
CARD_FILL = (255, 255, 255, 22)
GREEN, GREY, RED = (46, 174, 96), (150, 160, 172), (214, 40, 57)
MARK_FILL = {"W": GREEN, "D": GREY, "L": RED}
PHOTOS_JSON = os.path.join(HERE, "data", "team_photos.json")
DESIGN_CREDIT = "تصميم الجون"


# ---------------------------------------------------------------- the club's colour and photo
def _near_white(c):
    return min(c[:3]) > 200


def club_colour(name):
    """The club's accent from matchup_card's kit table: the first kit colour
    that is not white, else the kit's accent, else the alternate kit, else
    the brand blue (a club without a kit gets no invented colour)."""
    import matchup_card as MC
    kit = MC.KITS.get(name)
    if not kit:
        return (31, 148, 211)
    for c in kit[1]:
        if not _near_white(c):
            return tuple(c)
    if len(kit) > 3 and kit[3]:
        return tuple(kit[3])
    for c in kit[2][1]:
        if not _near_white(c):
            return tuple(c)
    return (31, 148, 211)


def club_photo(slug, photos=None):
    """The editor's non-person photo of the club - {path, credit} - or None.
    A real photograph before one of our own designs; the newest first, the
    widest next. Only files that still exist in team-photos/<slug>/."""
    if photos is None:
        try:
            with io.open(PHOTOS_JSON, encoding="utf-8") as f:
                photos = json.load(f).get("photos") or []
        except (OSError, ValueError):
            return None
    cands = []
    for p in photos:
        if p.get("slug") != slug or p.get("is_person"):
            continue
        src = p.get("source") or ""
        if not src.startswith(f"team-photos/{slug}/"):
            continue
        path = os.path.join(HERE, *src.split("/"))
        if not os.path.exists(path):
            continue
        design = DESIGN_CREDIT in (p.get("credit") or "")
        cands.append(((1 if design else 0), -(p.get("width") or 0), p["file"], path, p.get("credit") or ""))
    if not cands:
        return None
    cands.sort()                                         # a photograph before a design; the widest first; then the name
    best = cands[0]
    return {"path": best[3], "credit": best[4], "file": best[2]}


# ---------------------------------------------------------------- drawing
def _gradient(img, top, bot):
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / (H - 1)
        d.line([(0, y), (W, y)], fill=tuple(round(p + (q - p) * t) for p, q in zip(top, bot)))


def draw_mark(img, cx, cy, r, mark):
    """✅ / ➖ / ❌ as a coloured disc with a drawn glyph (Almarai has no emoji)."""
    d = ImageDraw.Draw(img)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=MARK_FILL[mark])
    w = max(3, r // 4)
    if mark == "W":
        d.line([(cx - r * 0.45, cy + r * 0.02), (cx - r * 0.12, cy + r * 0.38), (cx + r * 0.5, cy - r * 0.38)], fill=WHITE, width=w, joint="curve")
    elif mark == "D":
        d.line([(cx - r * 0.45, cy), (cx + r * 0.45, cy)], fill=WHITE, width=w)
    else:
        d.line([(cx - r * 0.4, cy - r * 0.4), (cx + r * 0.4, cy + r * 0.4)], fill=WHITE, width=w)
        d.line([(cx - r * 0.4, cy + r * 0.4), (cx + r * 0.4, cy - r * 0.4)], fill=WHITE, width=w)


def photo_strip(img, path, y0, y1, colour):
    """The photo across the width between y0 and y1, cover-cropped, dimmed
    and dissolving into the canvas at its bottom so the rows read."""
    try:
        ph = Image.open(path).convert("RGB")
    except (OSError, ValueError):
        return False
    bw, bh = W, y1 - y0
    k = max(bw / ph.width, bh / ph.height)
    ph = ph.resize((max(1, round(ph.width * k)), max(1, round(ph.height * k))), Image.LANCZOS)
    ph = ph.crop(((ph.width - bw) // 2, max(0, (ph.height - bh) // 3), (ph.width - bw) // 2 + bw, max(0, (ph.height - bh) // 3) + bh))
    ph = Image.blend(ph, Image.new("RGB", ph.size, tuple(int(c * 0.35) for c in colour)), 0.42)
    mask = Image.new("L", ph.size, 255)
    md = ImageDraw.Draw(mask)
    fade = int(bh * 0.55)
    for i in range(fade):
        md.line([(0, bh - fade + i), (bw, bh - fade + i)], fill=int(255 * (1 - i / fade) ** 1.6))
    md.rectangle([0, 0, bw, int(bh * 0.08)], fill=0)
    for i in range(int(bh * 0.08), int(bh * 0.22)):
        md.line([(0, i), (bw, i)], fill=int(255 * (i - bh * 0.08) / (bh * 0.14)))
    img.paste(ph, (0, y0), mask)
    return True


def render(ev, out=None, photo=None, use_photo=True):
    """Draw the card for one club-form / club-streak event. `photo` = a
    {path, credit} to force (tests); use_photo=False = crest-only."""
    import fb_cards as FC
    import fb_reel as R
    from site_lib.names import ar_team
    club, rows, rec, nxt = ev["club"], ev["rows"], ev["record"], ev.get("next")
    rows = list(reversed(rows))                          # newest at the top
    colour = club_colour(club["name"])
    img = Image.new("RGB", (W, H))
    _gradient(img, TOP, BOT)
    ph = photo if photo is not None else (club_photo(club["slug"]) if use_photo else None)
    if not use_photo:
        ph = None
    has_photo = bool(ph and photo_strip(img, ph["path"], 0, 470, colour))
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse([W // 2 - 460, -80, W // 2 + 460, 520], fill=colour + (60 if has_photo else 90,))
    glow = glow.filter(ImageFilter.GaussianBlur(140))
    img.paste(glow, (0, 0), glow)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 10], fill=colour)              # the club's rule

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
    def fit(s, weight, size, max_w, min_size=18):
        f = FC.font(weight, size)
        while d.textlength(FC.ar(s), font=f) > max_w and size > min_size:
            size -= 2; f = FC.font(weight, size)
        return f
    def crest(cx, cy, r, name, url, ring=None):
        if ring:
            d.ellipse([cx - r - 6, cy - r - 6, cx + r + 6, cy + r + 6], fill=ring)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=WHITE)
        R.crest_at(img, url, name, int(2 * r * 0.78), cx, cy)

    # brand + date
    FC.wordmark_at(img, W - 40, 62, 60, anchor="rm")
    today = datetime.datetime.now(datetime.timezone.utc).astimezone(datetime.timezone(datetime.timedelta(hours=2)))
    text_l(40, 46, f"{today.day} {__import__('site_lib.arabic', fromlist=['_AR_MONTHS'])._AR_MONTHS[today.month]} {today.year}", FC.font("Bold", 24), SOFT)

    # the club: crest in its ring on the RIGHT, the title and the headline to its left
    CR = 92
    crest(W - 40 - CR - 8, 250, CR, club["name"], club.get("badge"), ring=colour)
    n = rec["p"]
    title = f"آخر {n} مباريات" if 3 <= n <= 10 else f"آخر {n} مباراة"
    left_w = W - 40 - 2 * CR - 60 - 40
    text_r(W - 40 - 2 * CR - 60, 150, club["name"], fit(club["name"], "ExtraBold", 72, left_w, 40), WHITE)
    text_r(W - 40 - 2 * CR - 60, 240, title, FC.font("ExtraBold", 44), GOLD)
    tally = f"فوز {rec['w']} · تعادل {rec['d']} · خسارة {rec['l']}"
    text_r(W - 40 - 2 * CR - 60, 300, tally, FC.font("Bold", 30), SOFT)
    text_r(W - 40 - 2 * CR - 60, 342, f"الأهداف: {rec['gf']} له، {rec['ga']} عليه", FC.font("Bold", 26), DIM)

    # the rows (newest first)
    k = len(rows)
    GAP = 8
    y0, y1 = 400, 1130
    RH = min(92, (y1 - y0 - GAP * k) // k)
    y = y0
    MR = 24 if RH >= 80 else 20                          # the mark disc
    OR = 30 if RH >= 80 else 24                          # the opponent's crest
    fname = FC.font("ExtraBold", 30 if RH >= 80 else 26)
    fscore = FC.font("ExtraBold", 32 if RH >= 80 else 27)
    fsmall = FC.font("Bold", 20 if RH >= 80 else 17)
    for r in rows:
        rrect([40, y, W - 40, y + RH], 16, CARD_FILL)
        cy = y + RH // 2
        draw_mark(img, W - 40 - 18 - MR, cy, MR, r["mark"])
        crest(W - 40 - 18 - 2 * MR - 22 - OR, cy, OR, r["opponent"], r.get("opponent_badge"))
        name_r = W - 40 - 18 - 2 * MR - 22 - 2 * OR - 14
        pill_w = 120
        px0, px1 = W // 2 - pill_w // 2 - 40, W // 2 + pill_w // 2 - 40
        name_w = name_r - px1 - 16
        f = fit(r["opponent"], "ExtraBold", fname.size, name_w, 18)
        text_r(name_r, cy - f.size * 0.62, r["opponent"], f, WHITE)
        # the score: the club's goals RIGHT of the dash, the opponent's left
        rrect([px0, cy - 22, px1, cy + 22], 12, (255, 255, 255, 230))
        sc = f"{r['ga']} - {r['gf']}"
        bx = d.textbbox((0, 0), sc, font=fscore)
        d.text(((px0 + px1) / 2 - (bx[0] + bx[2]) / 2, cy - (bx[1] + bx[3]) / 2), sc, font=fscore, fill=TOP)
        # competition + date, small, on the left, with «أرضه» / «خارج أرضه»
        where = "في ملعبه" if r.get("home") else "خارج ملعبه"
        text_r(px0 - 18, cy - fsmall.size * 1.25, r["comp_label"], fsmall, SOFT)
        try:
            dd = datetime.date.fromisoformat(r["date"])
            from site_lib.arabic import _AR_MONTHS
            when = f"{dd.day} {_AR_MONTHS[dd.month]}"
        except (TypeError, ValueError):
            when = r["date"]
        text_r(px0 - 18, cy + fsmall.size * 0.15, f"{when} · {where}", fsmall, DIM)
        y += RH + GAP

    # the next fixture
    fy = y + 12
    if nxt:
        rrect([40, fy, W - 40, fy + 150], 18, (246, 192, 60, 22), (246, 192, 60, 110), 2)
        text_c(W // 2, fy + 12, "المباراة القادمة", FC.font("Bold", 24), GOLD)
        cy = fy + 92
        h, a = ar_team(nxt["home"]), ar_team(nxt["away"])
        crest(W - 40 - 24 - 34, cy, 34, h, nxt.get("home_badge"))
        crest(40 + 24 + 34, cy, 34, a, nxt.get("away_badge"))
        fh = fit(h, "ExtraBold", 32, 250, 18); fa = fit(a, "ExtraBold", 32, 250, 18)
        text_r(W - 40 - 24 - 68 - 14, cy - fh.size * 0.62, h, fh, WHITE)
        text_l(40 + 24 + 68 + 14, cy - fa.size * 0.62, a, fa, WHITE)
        import story_events as SE
        kk = SE._kick_dt(nxt)
        when = SE.ar_date(nxt.get("kickoff"), weekday=True, year=False)
        if nxt.get("koff_time") and kk:
            when += f" · {kk:%H:%M} بتوقيت القاهرة"
        text_c(W // 2, cy - 34, when, fit(when, "Bold", 24, 300, 16), WHITE)
        text_c(W // 2, cy + 6, SE.comp_label(nxt.get("competition")), FC.font("Bold", 20), SOFT)
    else:
        rrect([40, fy, W - 40, fy + 150], 18, CARD_FILL)
        text_c(W // 2, fy + 50, ev.get("title") or "", fit(ev.get("title") or "", "ExtraBold", 40, W - 120, 24), WHITE)

    # footer: the site, the photo credit
    text_l(40, H - 46, "elgoon.com", FC.font("Bold", 24), SOFT)
    foot = "النتائج من بيانات الجون · " + ("الصورة: " + ph["credit"].split("—")[0].replace("صورة:", "").replace("الصورة:", "").strip() if has_photo else "الأحدث في الأعلى")
    text_r(W - 40, H - 44, foot, fit(foot, "Regular", 20, W - 260, 14), DIM)
    if out:
        os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
        img.save(out, quality=90, optimize=True)
    return img


def render_bytes(ev, **kw):
    img = render(ev, None, **kw)
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=90, optimize=True)
    return buf.getvalue()


# ---------------------------------------------------------------- a sample from the real data
def sample_event(slug, data=None, today=None, n=None, hours=24 * 30):
    """The club-form event for `slug` with the window widened to its NEXT
    fixture (default a month), so a card can be looked at on any day."""
    import story_events as SE
    d = data or SE.load_data()
    tps = [tp for tp in SE.form_clubs() if tp["slug"] == slug]
    if not tps:
        sys.exit(f"no curated club with slug {slug!r} (one of {', '.join(tp['slug'] for tp in SE.form_clubs())})")
    evs = SE.club_form_before_match(d["matches"], d["fixtures"], d["archive"], today, n or SE.FORM_N, hours, clubs=tps)
    return evs[0] if evs else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--club", help="a curated club's slug (barcelona, real-madrid, al-ahly, zamalek, ...)")
    ap.add_argument("--all", action="store_true", help="every curated club with a fixture in the next 30 days")
    ap.add_argument("--out", help="the PNG/JPG to write")
    ap.add_argument("--out-dir", default=os.path.join(HERE, "media", "form"))
    ap.add_argument("--n", type=int, help=f"rows (default {8}, max 10)")
    ap.add_argument("--date", help="YYYY-MM-DD: look for the fixture from that day")
    ap.add_argument("--no-photo", action="store_true", help="crest-only on purpose")
    args = ap.parse_args()
    import story_events as SE
    today = datetime.date.fromisoformat(args.date) if args.date else None
    slugs = [tp["slug"] for tp in SE.form_clubs()] if args.all else [args.club]
    if not slugs or not slugs[0]:
        ap.error("--club <slug> or --all")
    d = SE.load_data()
    rc = 0
    for slug in slugs:
        ev = sample_event(slug, d, today, args.n)
        if not ev:
            print(f"{slug}: no fixture in the next 30 days or too few results"); rc = 1; continue
        out = args.out if (args.out and not args.all) else os.path.join(args.out_dir, f"form-{slug}.png")
        render(ev, out, use_photo=not args.no_photo)
        ph = None if args.no_photo else club_photo(slug)
        print(f"{out}: {ev['title']} ({'photo ' + ph['file'] if ph else 'crest-only'})")
        print(ev["text"]); print()
    return rc


if __name__ == "__main__":
    sys.exit(main())
