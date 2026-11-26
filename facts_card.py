#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""«أرقام قبل المباراة» / «أرقام بعد المباراة» as a CARD (user, 2026-11-26:
«ابدأ بـ 2 وبعدها 1» - the facts were a text post; an image travels further
on the page, and «اليوزر بيحب يشوف المعلومات من الصور»).

1080x1350, the cards' family (form_card / day_card: the blue gradient, the
wordmark, Almarai, the white crest discs). No club colour: the card is about
TWO sides, and one side's colour over the other's name breaks the colour
rule. The home side on the RIGHT as on every card; a score keeps the home
goals on the right of the dash.

Everything drawn is the event story_events built from site_lib/prefacts.py -
`ev["card"]`: the two names and crests, the kick-off or the score, the
competition, the sentences, and the count of the last meetings. Nothing is
worded here. The count is drawn as three numbers, so its sentence is left
out of the list.

    python facts_card.py --date 2026-11-28 --out-dir /tmp/facts      # every event of that day, a local look
"""
import io
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
TITLES = {"before": "أرقام قبل المباراة", "after": "أرقام بعد المباراة"}
MAX_FACTS = 5
FACTS_BOTTOM = H - 90


def wrap(d, text, font, max_w, ar):
    """The sentence as lines no wider than max_w (measured as drawn)."""
    lines, cur = [], ""
    for word in str(text).split():
        nxt = (cur + " " + word).strip()
        if cur and d.textlength(ar(nxt), font=font) > max_w:
            lines.append(cur)
            cur = word
        else:
            cur = nxt
    if cur:
        lines.append(cur)
    return lines


def shown_facts(card):
    """The sentences the list draws: the count of the meetings is the strip
    of three numbers, so its own sentence is not repeated."""
    facts = list(card.get("facts") or [])
    if card.get("tally") and card["tally"][0] >= 3:
        facts = [s for s in facts if not (s.startswith("آخر ") and "بين الفريقين:" in s)]
    return facts[:MAX_FACTS]


def render(ev, out=None):
    import fb_cards as FC
    import fb_reel as R
    c = ev["card"]
    img = Image.new("RGB", (W, H))
    px = img.load()
    for y in range(H):
        t = y / (H - 1)
        col = tuple(int(TOP[i] + (BOT[i] - TOP[i]) * t) for i in range(3))
        for x in range(W):
            px[x, y] = col
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse([W // 2 - 460, 40, W // 2 + 460, 560], fill=(60, 150, 220, 80))
    glow = glow.filter(ImageFilter.GaussianBlur(140))
    img.paste(glow, (0, 0), glow)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 10], fill=GOLD)

    def text_c(cx, y, s, f, fill=WHITE):
        s = FC.ar(s); d.text((cx - d.textlength(s, font=f) / 2, y), s, font=f, fill=fill)

    def text_r(xr, y, s, f, fill=WHITE):
        s = FC.ar(s); d.text((xr - d.textlength(s, font=f), y), s, font=f, fill=fill)

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
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=WHITE)
        R.crest_at(img, url, name, int(2 * r * 0.78), cx, cy)

    # brand, title, competition
    FC.wordmark_at(img, W - 40, 62, 60, anchor="rm")
    d.text((40, 46), "elgoon.com", font=FC.font("Bold", 24), fill=SOFT)
    text_c(W // 2, 118, TITLES[c["mode"]], FC.font("ExtraBold", 58), GOLD)
    text_c(W // 2, 198, c.get("comp") or "", FC.font("Bold", 28), SOFT)

    # the two sides: home on the RIGHT; the kick-off or the score between them
    CR, cy = 84, 350
    hx, ax = W - 190, 190
    crest(hx, cy, CR, c["home"], c.get("home_badge"))
    crest(ax, cy, CR, c["away"], c.get("away_badge"))
    text_c(hx, cy + CR + 14, c["home"], fit(c["home"], "ExtraBold", 38, 330, 20))
    text_c(ax, cy + CR + 14, c["away"], fit(c["away"], "ExtraBold", 38, 330, 20))
    if c["mode"] == "after":
        sc = f"{c['away_score']} - {c['home_score']}"          # home goals RIGHT of the dash
        f = FC.font("ExtraBold", 96)
        bx = d.textbbox((0, 0), sc, font=f)
        d.text((W / 2 - (bx[0] + bx[2]) / 2, cy - (bx[1] + bx[3]) / 2), sc, font=f, fill=WHITE)
        text_c(W // 2, cy + 70, "انتهت", FC.font("Bold", 26), SOFT)
    else:
        f = FC.font("ExtraBold", 76)
        t = c.get("time") or "×"
        bx = d.textbbox((0, 0), t, font=f)
        d.text((W / 2 - (bx[0] + bx[2]) / 2, cy - (bx[1] + bx[3]) / 2 - 12), t, font=f, fill=WHITE)
        text_c(W // 2, cy + 50, c.get("day") or "", fit(c.get("day") or "", "Bold", 26, 300, 16), SOFT)

    y = cy + CR + 90
    # the last meetings as three numbers: the home side's wins on the right
    tl = c.get("tally")
    if tl and tl[0] >= 3:
        n, wh, wa, dr = tl
        cap = f"آخر {n} مواجهات" if 3 <= n <= 10 else f"آخر {n} مواجهة"
        rrect([40, y, W - 40, y + 150], 18, (246, 192, 60, 22), (246, 192, 60, 110), 2)
        text_c(W // 2, y + 10, cap, FC.font("Bold", 24), GOLD)
        for cx, num, lab in ((W - 200, wh, f"فوز {c['home']}"), (W // 2, dr, "تعادل"), (200, wa, f"فوز {c['away']}")):
            fn = FC.font("ExtraBold", 60)
            bx = d.textbbox((0, 0), str(num), font=fn)
            d.text((cx - (bx[0] + bx[2]) / 2, y + 44), str(num), font=fn, fill=WHITE)
            text_c(cx, y + 110, lab, fit(lab, "Bold", 22, 300, 14), SOFT)
        y += 150 + 18

    # the sentences, one panel each; the font steps down until they all fit
    facts = shown_facts(c)
    PAD, GAP, TW = 22, 12, W - 80 - 2 * 22 - 26
    size = 40
    while True:
        f = FC.font("Bold", size)
        blocks = [wrap(d, s, f, TW, FC.ar) for s in facts]
        lh = int(size * 1.55)
        total = sum(len(b) * lh + 2 * PAD for b in blocks) + GAP * max(0, len(blocks) - 1)
        if total <= FACTS_BOTTOM - y or size <= 22:
            break
        size -= 2
    y += max(0, (FACTS_BOTTOM - y - total) // 2)             # the list sits in the middle of its room
    for b in blocks:
        bh = len(b) * lh + 2 * PAD
        if y + bh > FACTS_BOTTOM:
            break
        rrect([40, y, W - 40, y + bh], 16, CARD_FILL)
        d.rounded_rectangle([W - 40 - 14, y + 14, W - 40 - 8, y + bh - 14], 3, fill=GOLD)
        for i, line in enumerate(b):
            text_r(W - 40 - PAD - 14, y + PAD + i * lh - 4, line, f, WHITE)
        y += bh + GAP

    text_r(W - 40, H - 52, "الأرقام محسوبة من بيانات الجون", FC.font("Regular", 22), DIM)
    text_r(150, H - 54, "#الجون", FC.font("Bold", 24), SOFT)
    if out:
        os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
        img.save(out, quality=90, optimize=True)
    return img


def render_bytes(ev):
    buf = io.BytesIO()
    render(ev).convert("RGB").save(buf, "JPEG", quality=90, optimize=True)
    return buf.getvalue()


def main():
    import argparse
    import datetime
    import story_events as SE
    ap = argparse.ArgumentParser()
    ap.add_argument("--date")
    ap.add_argument("--out-dir", default="drafts/facts")
    a = ap.parse_args()
    today = datetime.date.fromisoformat(a.date) if a.date else None
    evs = [e for e in SE.detect(today=today) if e["kind"] in (SE.KIND_FACTS, SE.KIND_AFTER)]
    for ev in evs:
        out = os.path.join(a.out_dir, ev["ref"].replace(":", "-") + ".jpg")
        render(ev, out)
        print(out)
    if not evs:
        print("no facts event on that day")
    return 0


if __name__ == "__main__":
    sys.exit(main())
