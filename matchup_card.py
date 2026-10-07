#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Matchup cards - the article image for an important match (2026-10-08).

User: «اعمل قالب صورة المواجهة للماتشات المهمة», after approving the first
one by hand for the Zamalek x Al Ahly analysis (article 687).

A 1600x680 card in the site's brand: blue gradient, a faint halfway line and
centre circle, each club as a DISC IN ITS COLOURS - never its crest (club
crests are trademarks; the site uses only free-licensed or its own images),
the two names, the competition and round in the middle, date / time / venue
underneath, «يلا سكور» + the URL in the corners. The middle shows «×» before
kick-off and the score once the match is over (a report).

Everything a reader must see sits inside the article-hero crop (the middle
1600x414 band: the hero renders 1544x400); the brand corners are for the
Facebook / Telegram / card previews, where the whole image shows.

Kits are FACTS (a club's colours), keyed by the site's Arabic names. A club
we have no kit for gets a neutral disc - never an invented colour. When the
two primary colours are too close (red v red), the away side wears its
alternate kit, the way the match itself would.

    python matchup_card.py --match 4804684              # from data/matches.json
    python matchup_card.py --demo                       # writes /tmp-ish demo cards
"""
import argparse
import datetime
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from PIL import Image, ImageDraw, ImageFilter          # noqa: E402

W, H = 1600, 680
TOP, BOT = (31, 148, 211), (12, 66, 104)
WHITE = (255, 255, 255)
SOFT = (220, 236, 248)

# kit = (pattern, colours, alternate kit[, accent])
#   solid  (c,)            bands  (base, band) two horizontal bands
#   vstripes (a, b)        halves (left, right)   diag (upper-left, lower-right)
NAVY = (16, 34, 74)
KITS = {
    # Egypt
    "الأهلي": ("solid", [(192, 12, 36)], ("solid", [(255, 255, 255)])),
    "الزمالك": ("bands", [(255, 255, 255), (200, 16, 46)], ("solid", [(200, 16, 46)])),
    "بيراميدز": ("solid", [(23, 44, 105)], ("solid", [(255, 255, 255)])),
    "المصري": ("solid", [(0, 132, 61)], ("solid", [(255, 255, 255)])),
    # England
    "أرسنال": ("halves", [(219, 0, 7), (255, 255, 255)], ("solid", [(255, 255, 255)])),
    "ليفربول": ("solid", [(200, 16, 46)], ("solid", [(255, 255, 255)])),
    "تشيلسي": ("solid", [(3, 70, 148)], ("solid", [(255, 255, 255)])),
    "مانشستر يونايتد": ("solid", [(218, 41, 28)], ("solid", [(255, 255, 255)])),
    "مانشستر سيتي": ("solid", [(108, 171, 221)], ("solid", [(28, 44, 91)])),
    "توتنهام هوتسبر": ("solid", [(255, 255, 255)], ("solid", [(19, 34, 87)]), (19, 34, 87)),
    # Spain
    "ريال مدريد": ("solid", [(255, 255, 255)], ("solid", [(29, 29, 27)]), (212, 175, 55)),
    "برشلونة": ("vstripes", [(0, 77, 152), (165, 0, 68)], ("solid", [(255, 237, 2)])),
    "أتلتيكو مدريد": ("vstripes", [(203, 53, 36), (255, 255, 255)], ("solid", [(39, 46, 97)])),
    # Italy
    "إنتر ميلان": ("vstripes", [(0, 104, 168), (20, 20, 20)], ("solid", [(255, 255, 255)])),
    "ميلان": ("vstripes", [(251, 9, 11), (20, 20, 20)], ("solid", [(255, 255, 255)])),
    "يوفنتوس": ("vstripes", [(20, 20, 20), (255, 255, 255)], ("solid", [(255, 205, 0)])),
    "نابولي": ("solid", [(18, 160, 215)], ("solid", [(255, 255, 255)])),
    "روما": ("solid", [(142, 31, 47)], ("solid", [(255, 255, 255)])),
    "لاتسيو": ("solid", [(135, 216, 247)], ("solid", [(255, 255, 255)])),
    # France
    "باريس سان جيرمان": ("bands", [NAVY, (218, 41, 28)], ("solid", [(255, 255, 255)])),
    "أولمبيك ليون": ("solid", [(255, 255, 255)], ("solid", [(20, 40, 110)]), (218, 41, 28)),
    "أولمبيك مارسيليا": ("solid", [(255, 255, 255)], ("solid", [(43, 169, 224)]), (43, 169, 224)),
    "موناكو": ("diag", [(227, 6, 19), (255, 255, 255)], ("solid", [(20, 20, 20)])),
    # Germany
    "بايرن ميونخ": ("solid", [(220, 5, 45)], ("solid", [(255, 255, 255)])),
    "بوروسيا دورتموند": ("solid", [(253, 225, 0)], ("solid", [(20, 20, 20)])),
    "باير ليفركوزن": ("halves", [(227, 34, 25), (20, 20, 20)], ("solid", [(255, 255, 255)])),
    "بوروسيا مونشنجلادباخ": ("solid", [(255, 255, 255)], ("solid", [(20, 20, 20)]), (0, 150, 64)),
    # Saudi - «الأهلي» there is Al-Ahli Jeddah: resolved by competition below
    "الهلال": ("solid", [(20, 80, 170)], ("solid", [(255, 255, 255)])),
    "النصر": ("solid", [(255, 210, 0)], ("solid", [(10, 40, 110)])),
    "الاتحاد": ("vstripes", [(255, 210, 0), (20, 20, 20)], ("solid", [(255, 255, 255)])),
    # Turkey (and the UCL feed's spelling of Galatasaray)
    "غلطة سراي": ("halves", [(169, 4, 50), (253, 185, 18)], ("solid", [(255, 255, 255)])),
    "جالطة سراي": ("halves", [(169, 4, 50), (253, 185, 18)], ("solid", [(255, 255, 255)])),
    "فنربخشة": ("vstripes", [(0, 45, 114), (255, 237, 0)], ("solid", [(255, 255, 255)])),
    "بشكتاش": ("halves", [(20, 20, 20), (255, 255, 255)], ("solid", [(255, 255, 255)])),
    "طرابزون سبور": ("vstripes", [(123, 31, 48), (135, 206, 235)], ("solid", [(255, 255, 255)])),
}
KITS_BY_COMP = {("Saudi Pro League", "الأهلي"): ("solid", [(11, 138, 62)], ("solid", [(255, 255, 255)]))}
NEUTRAL = ("solid", [(176, 190, 204)], ("solid", [(120, 136, 152)]))


def kit_for(name, comp=None):
    return KITS_BY_COMP.get((comp, name)) or KITS.get(name) or NEUTRAL


def _accent(kit):
    return kit[3] if len(kit) > 3 else None


def _dist(a, b):
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


def kits(home, away, comp=None):
    """(home kit, away kit) - the away side switches to its alternate when
    the two main colours would be hard to tell apart."""
    hk, ak = kit_for(home, comp), kit_for(away, comp)
    if _dist(hk[1][0], ak[1][0]) < 90:
        # the alternate kit, trimmed in the club's own main colour so a plain
        # white disc still says who it is
        ak = (ak[2][0], ak[2][1], ak[2], ak[1][0])
    return hk, ak


def _fonts():
    import fb_cards as FC
    return FC


def _disc(img, d, cx, cy, r, kit):
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(sh).ellipse([cx - r + 6, cy - r + 14, cx + r + 6, cy + r + 14], fill=(0, 0, 0, 90))
    img.paste(sh.filter(ImageFilter.GaussianBlur(12)), (0, 0), sh.filter(ImageFilter.GaussianBlur(12)))
    pat, cols = kit[0], kit[1]
    disc = Image.new("RGB", (2 * r, 2 * r), cols[0])
    dd = ImageDraw.Draw(disc)
    if pat == "bands":
        for y0 in (int(r * 0.62), int(r * 0.98)):
            dd.rectangle([0, y0, 2 * r, y0 + int(r * 0.22)], fill=cols[1])
    elif pat == "vstripes":
        n = 7
        w = 2 * r / n
        for i in range(n):
            if i % 2:
                dd.rectangle([int(i * w), 0, int((i + 1) * w), 2 * r], fill=cols[1])
    elif pat == "halves":
        dd.rectangle([r, 0, 2 * r, 2 * r], fill=cols[1])
    elif pat == "diag":
        dd.polygon([(2 * r, 0), (2 * r, 2 * r), (0, 2 * r)], fill=cols[1])
    acc = _accent(kit)
    if acc and pat == "solid" and sum(cols[0]) > 600:   # a light disc gets an inner trim ring
        dd.ellipse([int(r * 0.16), int(r * 0.16), int(r * 1.84), int(r * 1.84)], outline=acc, width=max(10, r // 9))
    mask = Image.new("L", (2 * r, 2 * r), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, 2 * r - 1, 2 * r - 1], fill=255)
    img.paste(disc, (cx - r, cy - r), mask)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=WHITE, width=8)


def _text_c(d, FC, cx, y, s, f, fill=WHITE, max_w=None, size=None, weight=None):
    """Centred Arabic text; shrinks (when weight/size are given) to fit max_w."""
    t = FC.ar(s)
    if max_w and size and weight:
        while d.textlength(t, font=f) > max_w and size > 26:
            size -= 4
            f = FC.font(weight, size)
    d.text((cx - d.textlength(t, font=f) / 2, y), t, font=f, fill=fill)


def render(home, away, out, comp=None, comp_label="", round_label="", when="", venue="",
           score=None, top_label=None):
    """Write the card to `out` (.jpg or .png). `score` = (home, away) for a
    finished match, else the middle shows «×»."""
    FC = _fonts()
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / (H - 1)
        d.line([(0, y), (W, y)], fill=tuple(round(a + (b - a) * t) for a, b in zip(TOP, BOT)))
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(ov)
    od.line([(W // 2, 0), (W // 2, H)], fill=(255, 255, 255, 40), width=3)
    od.ellipse([W // 2 - 230, H // 2 - 230, W // 2 + 230, H // 2 + 230], outline=(255, 255, 255, 40), width=3)
    img.paste(ov, (0, 0), ov)

    hk, ak = kits(home, away, comp)
    CY, R = 262, 108
    _disc(img, d, 1150, CY, R, hk)                   # home on the RIGHT (RTL)
    _disc(img, d, 450, CY, R, ak)
    _text_c(d, FC, 1150, CY + R + 14, home, FC.font("ExtraBold", 66), max_w=440, size=66, weight="ExtraBold")
    _text_c(d, FC, 450, CY + R + 14, away, FC.font("ExtraBold", 66), max_w=440, size=66, weight="ExtraBold")
    if top_label or comp_label:
        _text_c(d, FC, W // 2, 150, top_label or comp_label, FC.font("Bold", 40), SOFT,
                max_w=400, size=40, weight="Bold")
    if score is not None:
        mid = f"{score[1]} - {score[0]}"             # drawn LTR: away on the left, home on the right
        f = FC.font("ExtraBold", 100)
        d.text((W // 2 - d.textlength(mid, font=f) / 2, CY - 60), mid, font=f, fill=WHITE)
    else:
        _text_c(d, FC, W // 2, CY - 70, "×", FC.font("ExtraBold", 120))
    under = " · ".join(x for x in ((comp_label if top_label else ""), round_label) if x)
    if under:
        _text_c(d, FC, W // 2, CY + 72, under, FC.font("Bold", 34), SOFT, max_w=420, size=34, weight="Bold")
    bottom = " · ".join(x for x in (when, venue) if x)
    if bottom:
        _text_c(d, FC, W // 2, 478, bottom, FC.font("Regular", 34), (235, 244, 251),
                max_w=1100, size=34, weight="Regular")
    icon = Image.open(os.path.join(HERE, "assets-src", "app-icon-1024.png")).convert("RGB")
    ball = icon.crop((218, 105, 806, 693)).resize((70, 70), Image.LANCZOS)
    m = Image.new("L", (70, 70), 0)
    ImageDraw.Draw(m).ellipse([0, 0, 69, 69], fill=255)
    img.paste(ball, (W - 110, 34), m)
    fb = FC.font("ExtraBold", 40)
    s = FC.ar("يلا سكور")
    d.text((W - 126 - d.textlength(s, font=fb), 44), s, font=fb, fill=WHITE)
    d.text((40, H - 62), "yallascore.site", font=FC.font("Bold", 28), fill=SOFT)
    if out.lower().endswith((".jpg", ".jpeg")):
        img.save(out, quality=90, optimize=True)
    else:
        img.save(out)
    return out


def when_ar(kickoff, koff_time):
    """«الأحد 11 أكتوبر · 8 مساءً» from the match's Cairo date and time."""
    from site_lib.arabic import _AR_DAYS, _AR_MONTHS
    try:
        dd = datetime.date.fromisoformat(kickoff[:10])
    except (TypeError, ValueError):
        return ""
    s = f"{_AR_DAYS[dd.weekday()]} {dd.day} {_AR_MONTHS[dd.month]}"
    try:
        hh, mm = (int(x) for x in (koff_time or "").split(":")[:2])
    except ValueError:
        return s
    h12 = hh % 12 or 12
    part = "صباحًا" if hh < 12 else "مساءً"
    return f"{s} · {h12}{':' + format(mm, '02d') if mm else ''} {part}"


def for_match(m, out, venue="", top_label=None):
    """The card for one match dict (matches.json shape)."""
    from site_lib.names import ar_team, comp_label
    comp = m.get("competition")
    done = (m.get("status") or "").upper() == "FINISHED" and m.get("home_score") is not None
    return render(ar_team(m.get("home")), ar_team(m.get("away")), out, comp=comp,
                  comp_label=comp_label(comp), round_label=(f"الجولة {m['round']}" if m.get("round") else ""),
                  when=when_ar(m.get("kickoff"), m.get("koff_time")), venue=venue,
                  score=(int(m["home_score"]), int(m["away_score"])) if done else None, top_label=top_label)


def card_name(m):
    """Unique media/ filename per match AND kind (preview vs result)."""
    done = (m.get("status") or "").upper() == "FINISHED"
    return f"matchup-{m.get('match_id')}-{'result' if done else 'preview'}.jpg"


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--match")
    ap.add_argument("--out")
    ap.add_argument("--demo", action="store_true")
    a = ap.parse_args()
    if a.match:
        from site_lib.config import load
        m = next((x for x in load("matches.json") + load("matches_archive.json")
                  if str(x.get("match_id")) == str(a.match)), None)
        if not m:
            sys.exit(f"match {a.match} not found")
        print(for_match(m, a.out or os.path.join(HERE, "media", card_name(m))))
