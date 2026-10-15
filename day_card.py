#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A day's fixtures of ONE competition as a 1080x1350 Facebook photo (user ask
2026-10-12: «اعمل صورة لمواجهات غدا فى دورى الابطال»).

Everything on it comes from data/matches.json: the clubs (Arabic names from
AR_TEAM), their crests, kick-off times (Cairo), the round, and the TV channel
from COMP_TV. Same blue, brand and card primitives as h2h_card.py.

    python day_card.py                                   # tomorrow, Champions League
    python day_card.py --date 2026-10-13 --comp "UEFA Champions League" --out day.jpg
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
CARD_FILL = (255, 255, 255, 22)
MAX_ROWS = 9           # one card; a bigger day gets the first nine by kick-off


def day_matches(matches, date, comp):
    out = [m for m in matches if (m.get("kickoff") or "")[:10] == date
           and m.get("competition") == comp]
    out.sort(key=lambda m: (m.get("koff_time") or "", m.get("home") or ""))
    return out


def render(ms, date, comp, out, part=None, parts=1):
    """part/parts (2026-10-15, the Europa League's 18-match Thursdays): page
    `part` of `parts`, nine matches each, the subtitle says which."""
    import fb_cards as FC
    import matchup_card as MC
    from site_lib.names import ar_team, comp_label
    from site_lib.competitions import COMP_TV
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / (H - 1)
        d.line([(0, y), (W, y)], fill=tuple(round(p + (q - p) * t) for p, q in zip(TOP, BOT)))
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse([W // 2 - 420, 60, W // 2 + 420, 700], fill=(31, 148, 211, 70))
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
    def fit(s, weight, size, max_w, min_size=18):
        f = FC.font(weight, size)
        while d.textlength(FC.ar(s), font=f) > max_w and size > min_size:
            size -= 2; f = FC.font(weight, size)
        return f
    def crest(cx, cy, r, name, url):
        im = None
        try:
            im = FC.crest_image(url, int(2 * r * 0.78)) if url else None
        except Exception:                               # noqa: BLE001
            im = None
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=WHITE)
        if im is not None:
            img.paste(im, (cx - im.width // 2, cy - im.height // 2), im)
        else:
            f = FC.font("ExtraBold", int(r * 0.9))
            s = FC.ar((name or "?").strip()[:1])
            d.text((cx - d.textlength(s, font=f) / 2, cy - r * 0.6), s, font=f, fill=(16, 62, 108))

    # brand + title
    icon = Image.open(os.path.join(HERE, "assets-src", "app-icon-1024.png")).convert("RGB")
    ball = icon.crop((218, 105, 806, 693)).resize((52, 52), Image.LANCZOS)
    bm = Image.new("L", (52, 52), 0)
    ImageDraw.Draw(bm).ellipse([0, 0, 51, 51], fill=255)
    img.paste(ball, (W - 52 - 40, 36), bm)
    text_r(W - 40 - 52 - 12, 40, "يلا سكور", FC.font("ExtraBold", 34))
    when = MC.when_ar(date, None)
    text_l(40, 46, when, FC.font("Bold", 26), SOFT)
    label = comp_label(comp)
    text_c(W // 2, 96, f"مباريات {label}", fit(f"مباريات {label}", "ExtraBold", 72, W - 80, 40))
    rnd = next((m.get("round") for m in ms if m.get("round")), None)
    sub = " · ".join(x for x in (when, f"الجولة {rnd}" if rnd else "",
                                  f"الجزء {part} من {parts}" if parts > 1 else "",
                                  "التوقيت بتوقيت القاهرة") if x)
    text_c(W // 2, 192, sub, FC.font("Bold", 30), GOLD)

    # the rows
    rows = ms[(part - 1) * MAX_ROWS:part * MAX_ROWS] if part else ms[:MAX_ROWS]
    n = max(len(rows), 1)
    GAP = 8
    CH = min(96, (936 - GAP * n) // n)
    y = 262
    R = 34
    fn = FC.font("ExtraBold", 30)
    ft = FC.font("ExtraBold", 28)
    for m in rows:
        rrect([40, y, W - 40, y + CH], 18, CARD_FILL, None, 1)
        cy = y + CH // 2
        h, a = ar_team(m.get("home")), ar_team(m.get("away"))
        crest(W - 40 - 16 - R, cy, R, h, m.get("home_badge"))
        crest(40 + 16 + R, cy, R, a, m.get("away_badge"))
        # time pill in the middle
        t = m.get("koff_time") or "--:--"
        rrect([W // 2 - 62, cy - 22, W // 2 + 62, cy + 22], 12, (0, 0, 0, 90))
        d.text((W // 2 - d.textlength(t, font=ft) / 2, cy - 21), t, font=ft, fill=GOLD)
        side_w = W // 2 - 62 - (40 + 16 + 2 * R + 14) - 10
        fh = fit(h, "ExtraBold", 30, side_w, 18)
        fa = fit(a, "ExtraBold", 30, side_w, 18)
        text_r(W - 40 - 16 - 2 * R - 14, cy - fh.size * 0.62, h, fh, WHITE)   # home RIGHT
        text_l(40 + 16 + 2 * R + 14, cy - fa.size * 0.62, a, fa, WHITE)       # away LEFT
        y += CH + GAP
    if len(ms) > MAX_ROWS and not part:
        text_c(W // 2, y + 4, f"و{len(ms) - MAX_ROWS} مباريات أخرى في الموقع", FC.font("Bold", 24), DIM)

    # footer: the channel + the site
    fy = 262 + 9 * (96 + GAP) + 10
    tv = COMP_TV.get(comp)
    if tv:
        rrect([40, fy, W - 40, fy + 60], 18, (246, 192, 60, 26), (246, 192, 60, 120), 2)
        text_c(W // 2, fy + 10, f"القنوات الناقلة: {tv}", FC.font("Bold", 30), WHITE)
    text_l(40, H - 46, "yallascore.site", FC.font("Bold", 24), SOFT)
    text_r(W - 40, H - 44, "المواعيد: الجدول الرسمي · قد تتغير", FC.font("Regular", 22), DIM)
    img.save(out, quality=90, optimize=True)
    return {"n": len(ms), "rows": len(rows)}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="YYYY-MM-DD (default: tomorrow, Cairo)")
    ap.add_argument("--comp", default="UEFA Champions League")
    ap.add_argument("--out", default=os.path.join(HERE, "data", "briefs", "day.jpg"))
    ap.add_argument("--part", type=int, help="page N of a day bigger than nine matches (default: every page, <out>-N.jpg)")
    args = ap.parse_args()
    import match_brief as MB
    from site_lib.config import load
    date = args.date
    if not date:
        from zoneinfo import ZoneInfo
        date = (datetime.datetime.now(ZoneInfo("Africa/Cairo")) + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    dd = MB.load_all()
    ms = day_matches(dd["matches"], date, args.comp)
    if not ms:
        sys.exit(f"no {args.comp} matches on {date} in matches.json")
    parts = -(-len(ms) // MAX_ROWS)
    if parts == 1:
        print(args.out, render(ms, date, args.comp, args.out))
    elif args.part:
        print(args.out, render(ms, date, args.comp, args.out, args.part, parts))
    else:
        stem, ext = os.path.splitext(args.out)
        for k in range(1, parts + 1):
            out = f"{stem}-{k}{ext}"
            print(out, render(ms, date, args.comp, out, k, parts))
