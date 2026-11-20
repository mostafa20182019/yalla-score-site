#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Elgoon - the cards of two social kinds (story_social.py, 2026-11-19):

  «رقم الليلة»   one huge number, the two shot counts, the result
  «سؤال الجون»   five results as five tiles, the league as the only hint -
                 no crest and no name: the card must not give the answer away

A picture is read where a text post is scrolled past (the social review asked
for both as cards). Same family as the day card: its dark blue, the wordmark
in the corner, a red tag saying what the card is. Every word and number on
the card comes from the event story_social built - nothing is computed here.

    python social_card.py --dry            # today's events of the two kinds -> social-<kind>.jpg

fb_post.post_event posts the card with the event's text as its caption, and
falls back to the text alone when the card cannot be drawn.
"""
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
from PIL import Image, ImageDraw, ImageFilter          # noqa: E402

import day_card as DC                                  # noqa: E402

W, H = DC.W, DC.H
WHITE, SOFT, DIM, RED, GOLD = DC.WHITE, DC.SOFT, DC.DIM, DC.RED, DC.GOLD
BLUE, INK = (31, 148, 211), (16, 62, 108)
CARD_KINDS = ("night-number", "goon-question")
# a win is the dark ink of the family: on the light background the site's blue tile vanished (2026-11-20)
TILE = {"W": ("فوز", INK + (255,), WHITE), "D": ("تعادل", (255, 255, 255, 60), WHITE), "L": ("خسارة", (255, 255, 255, 235), INK)}


class _Canvas:
    def __init__(self, tag):
        import fb_cards as FC
        self.FC = FC
        self.img = Image.new("RGB", (W, H))
        self.d = d = ImageDraw.Draw(self.img)
        for y in range(H):
            t = y / (H - 1)
            d.line([(0, y), (W, y)], fill=tuple(round(p + (q - p) * t) for p, q in zip(DC.LIGHT_TOP, DC.LIGHT_BOT)))
        glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(glow).ellipse([W // 2 - 420, 160, W // 2 + 420, 860], fill=(31, 148, 211, 80))
        glow = glow.filter(ImageFilter.GaussianBlur(120))
        self.img.paste(glow, (0, 0), glow)
        FC.wordmark_at(self.img, W - 40, 66, 64, anchor="rm")
        f = FC.font("ExtraBold", 30)
        tw = d.textlength(FC.ar(tag), font=f)
        self.rrect([40, 40, 40 + tw + 44, 94], 27, RED + (255,))
        self.left(62, 47, tag, f)

    def rrect(self, box, r, fill, outline=None, width=2):
        ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(ov).rounded_rectangle(box, r, fill=fill, outline=outline, width=width)
        self.img.paste(ov, (0, 0), ov)

    def fit(self, s, weight, size, max_w, min_size=18):
        f = self.FC.font(weight, size)
        while self.d.textlength(self.FC.ar(s), font=f) > max_w and size > min_size:
            size -= 2
            f = self.FC.font(weight, size)
        return f

    def centre(self, cx, y, s, f, fill=WHITE):
        s = self.FC.ar(s)
        self.d.text((cx - self.d.textlength(s, font=f) / 2, y), s, font=f, fill=fill)

    def left(self, x, y, s, f, fill=WHITE):
        self.d.text((x, y), self.FC.ar(s), font=f, fill=fill)

    def right(self, xr, y, s, f, fill=WHITE):
        s = self.FC.ar(s)
        self.d.text((xr - self.d.textlength(s, font=f), y), s, font=f, fill=fill)

    def mid(self, cx, cy, s, f, fill=WHITE):
        """Latin / digits centred on a point (no shaping)."""
        bx = self.d.textbbox((0, 0), s, font=f)
        self.d.text((cx - (bx[0] + bx[2]) / 2, cy - (bx[1] + bx[3]) / 2), s, font=f, fill=fill)

    def crest(self, cx, cy, r, name, url):
        im = None
        try:
            im = self.FC.crest_image(url, int(2 * r * 0.78)) if url else None
        except Exception:                               # noqa: BLE001
            im = None
        self.d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=WHITE)
        if im is not None:
            self.img.paste(im, (cx - im.width // 2, cy - im.height // 2), im)
        else:
            f = self.FC.font("ExtraBold", int(r * 0.9))
            s = self.FC.ar((name or "?").strip()[:1])
            self.d.text((cx - self.d.textlength(s, font=f) / 2, cy - r * 0.6), s, font=f, fill=INK)

    def foot(self, note):
        self.left(40, H - 46, "elgoon.com", self.FC.font("Bold", 24), SOFT)
        self.right(W - 40, H - 44, note, self.FC.font("Regular", 22), DIM)


def render_number(ev):
    """«رقم الليلة»: ev = story_social.night_number()'s event (number, shots,
    match with the two names, the score and the badges, lines)."""
    c = _Canvas("رقم الليلة")
    m = ev["match"]
    n = str(ev["number"])
    c.mid(W // 2, 400, n, c.FC.font("ExtraBold", 430 if len(n) < 3 else 320))
    y = 660
    for ln in ev["lines"][1:2]:                         # «ميلان سدد 7 مرات فقط. إنتر سدد 19 مرة.»
        for part in [p.strip() for p in ln.split(". ") if p.strip()]:
            part = part.rstrip(".")
            c.centre(W // 2, y, part, c.fit(part, "ExtraBold", 54, W - 120, 28))
            y += 84
    # the result strip
    y0 = 880
    c.rrect([40, y0, W - 40, y0 + 190], 28, (255, 255, 255, 26), (255, 255, 255, 70), 2)
    cy = y0 + 95
    c.crest(W - 40 - 30 - 62, cy, 62, m["home"], m.get("home_badge"))
    c.crest(40 + 30 + 62, cy, 62, m["away"], m.get("away_badge"))
    c.rrect([W // 2 - 110, cy - 46, W // 2 + 110, cy + 46], 18, (255, 255, 255, 240))
    c.mid(W // 2, cy, f"{m['away_score']} - {m['home_score']}", c.FC.font("ExtraBold", 66), INK)   # HOME on the right
    side_w = W // 2 - 110 - (40 + 30 + 124 + 16) - 12
    fh, fa = c.fit(m["home"], "ExtraBold", 40, side_w), c.fit(m["away"], "ExtraBold", 40, side_w)
    c.right(W - 40 - 30 - 124 - 16, cy - fh.size * 0.62, m["home"], fh)
    c.left(40 + 30 + 124 + 16, cy - fa.size * 0.62, m["away"], fa)
    q = ev["lines"][-1].rstrip(".")                     # «فعالية أم حظ؟ اكتب رأيك.»
    c.centre(W // 2, 1130, q, c.fit(q, "ExtraBold", 56, W - 120, 30), GOLD)
    c.foot("الرقم: عدد تسديدات الفائز")
    return c.img


def render_question(ev):
    """«سؤال الجون»: ev = story_social.goon_question()'s event (results,
    competition, lines). The answer is NOT drawn - not its name, not its crest."""
    from site_lib.names import comp_label
    c = _Canvas("سؤال الجون")
    c.centre(W // 2, 190, "من هو الفريق؟", c.FC.font("ExtraBold", 120))
    hint = f"فريق من {comp_label(ev.get('competition'))}"
    c.centre(W // 2, 380, hint, c.fit(hint, "ExtraBold", 56, W - 120, 30), GOLD)
    c.centre(W // 2, 490, f"آخر {len(ev['results'])} مباريات له في الدوري، الأقدم على اليمين", c.FC.font("Bold", 30), SOFT)
    res = ev["results"]
    n = len(res)
    gap, tw = 16, (W - 80 - 16 * (n - 1)) // n
    y0, th = 580, 300
    fw = c.FC.font("ExtraBold", 40)
    fs = c.FC.font("ExtraBold", 72)
    for i, r in enumerate(res):                          # oldest on the RIGHT: the order an Arabic reader follows
        x1 = W - 40 - i * (tw + gap)
        x0 = x1 - tw
        word, fill, ink = TILE[r["mark"]]
        c.rrect([x0, y0, x1, y0 + th], 26, fill, (255, 255, 255, 120), 2)
        s = c.FC.ar(word)
        c.d.text(((x0 + x1) / 2 - c.d.textlength(s, font=fw) / 2, y0 + 44), s, font=fw, fill=ink)
        c.mid((x0 + x1) / 2, y0 + 196, f"{r['gf']}-{r['ga']}", fs, ink)
    c.centre(W // 2, 950, "أهداف الفريق هي الرقم الأول في كل نتيجة", c.FC.font("Bold", 28), DIM)
    c.centre(W // 2, 1040, "اكتب إجابتك في التعليقات", c.FC.font("ExtraBold", 60))
    c.centre(W // 2, 1150, "الإجابة غدًا مع السؤال الجديد", c.FC.font("Bold", 36), SOFT)
    c.foot("من نتائج الدوري في بياناتنا")
    return c.img


RENDER = {"night-number": render_number, "goon-question": render_question}


def render(ev, out=None):
    img = RENDER[ev["kind"]](ev)
    if out:
        img.save(out, quality=90, optimize=True)
    return img


def render_movers(ev, out=None):
    """«حركة الجدول» as a still: for a round in which fewer than four clubs
    moved (movers_reel.REEL_MIN_MOVES). ev = story_social.round_movers()'s
    event: competition, round, moves [{team, before, after, crest}]."""
    from site_lib.names import comp_label
    c = _Canvas("حركة الجدول")
    label = comp_label(ev["competition"])
    c.centre(W // 2, 190, label, c.fit(label, "ExtraBold", 76, W - 120, 40))
    c.centre(W // 2, 300, f"بعد الجولة {ev['round']}", c.FC.font("Bold", 44), GOLD)
    moves = ev["moves"][:4]
    rh = 250
    top = 430 + (760 - rh * len(moves)) // 2
    for i, mv in enumerate(moves):
        y0 = top + i * rh
        cy = y0 + (rh - 24) // 2
        up = mv["after"] < mv["before"]
        col = (22, 163, 74) if up else RED
        c.rrect([40, y0, W - 40, y0 + rh - 24], 30, (255, 255, 255, 30), (255, 255, 255, 70), 2)
        c.crest(W - 40 - 34 - 76, cy, 76, mv["team"], mv.get("crest"))
        edge = W - 40 - 34 - 152 - 24
        c.right(edge, cy - 66, mv["team"], c.fit(mv["team"], "ExtraBold", 60, edge - 330, 30))
        sub = f"من المركز {mv['before']} إلى {mv['after']}"
        c.right(edge, cy + 14, sub, c.FC.font("Bold", 36), SOFT)
        # the chip: which way, and how many places
        c.rrect([70, cy - 62, 290, cy + 62], 38, col + (255,))
        tx, tw = 228, 26
        tri = ([(tx, cy - tw), (tx - tw, cy + tw * 0.75), (tx + tw, cy + tw * 0.75)] if up
               else [(tx, cy + tw), (tx - tw, cy - tw * 0.75), (tx + tw, cy - tw * 0.75)])
        c.d.polygon(tri, fill=WHITE)
        c.mid(138, cy, str(abs(mv["before"] - mv["after"])), c.FC.font("ExtraBold", 78))
    c.foot("الترتيب قبل الجولة وبعدها")
    if out:
        c.img.save(out, "JPEG", quality=90, optimize=True)
    return c.img


def render_movers_bytes(ev):
    buf = io.BytesIO()
    render_movers(ev).save(buf, "JPEG", quality=90, optimize=True)
    return buf.getvalue()


def render_bytes(ev):
    buf = io.BytesIO()
    render(ev).save(buf, "JPEG", quality=90, optimize=True)
    return buf.getvalue()


def main():
    import story_events as SE
    evs = [e for e in SE.detect() if e["kind"] in CARD_KINDS]
    if not evs:
        print("no «رقم الليلة» / «سؤال الجون» event on today's data"); return 0
    for e in evs:
        out = f"social-{e['kind']}.jpg"
        render(e, out)
        print(f"wrote {out} ({e['ref']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
