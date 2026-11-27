# -*- coding: utf-8 -*-
r"""«بوستر المباراة» - a match-day poster in the two clubs' OWN colours.

    python match_poster.py --date 2026-11-23 --out poster.jpg     # the day's match, a local look
    python match_poster.py --auto --publish                       # the page (FB_POSTER=on)

WHY (designer review 2026-11-20; user: «اعمل 18»): every card on the page is
the same blue. Nothing carried the colour a fan reacts to. This is ONE poster
a day at most, for the day's match (day_card.day_hero: two of our clubs first,
then one, then Egypt, then an Arab nation), and only when at least one side is
a curated club or the national team - a poster for a match nobody here
follows is noise.

THE COLOUR RULE (yalla-score-image-club-colours: never a rival club's
colours): the card is two halves, the home side on the right as on every
card, and each half is filled ONLY from its own club's kit
(matchup_card.kit_for: our table, then the feed's own club colours, then a
neutral grey - never an invented colour). A club that plays in white takes
its trim colour, as its disc does. When the two fills would be hard to tell
apart (الأهلي's red beside ليفربول's), the away half is its LIGHT colour with
dark ink - still its own.

The text is facts only: the two names, the competition, the day, the
kick-off (Cairo) and the channel when it is a verified one (match_tv). Behind
its own switch, FB_POSTER, like every new kind: until the repo variable is
"on" the run prints the caption and posts nothing.
"""
import argparse
import datetime
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from PIL import Image, ImageDraw, ImageFilter      # noqa: E402

import day_card as DC                              # noqa: E402
import matchup_card as MC                          # noqa: E402

W, H = 1080, 1350
WHITE, INK = (255, 255, 255), (16, 34, 74)
RED = DC.RED
KIND = "poster"
NEUTRAL_FILL = (88, 104, 124)


def _light(c):
    return sum(c) > 560


def _dist(a, b):
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


def own_colours(kit):
    """Every colour the club's kit holds, the main ones first: its pattern's
    colours, its trim, then its alternate kit's."""
    out = list(kit[1])
    if len(kit) > 3 and kit[3]:
        out.append(tuple(kit[3]))
    out += list(kit[2][1])
    seen, res = set(), []
    for c in out:
        c = tuple(c)
        if c not in seen:
            seen.add(c)
            res.append(c)
    return res


def fills(home, away, comp=None, feed=None):
    """(home fill, away fill): each from its own club's colours, its MAIN
    colour first - a white club stands on white (the names turn navy, see
    ink()), not on its trim: Zamalek's half in its red band read as Al Ahly's
    (review 2026-11-26), Real Madrid's as gold. Two light halves side by side
    are not a poster: then the away side takes a colour of its own that is
    not light, and only when it has none the neutral slate. If the two are
    close, the away side takes another colour of its own."""
    feed = feed or {}
    hk, ak = MC.kit_for(home, comp, feed.get("home")), MC.kit_for(away, comp, feed.get("away"))
    hc, ac = own_colours(hk), own_colours(ak)
    # only for a club in OUR table, where the first colour is the club's
    # identity by hand; a feed kit keeps its first colour that is not light
    # (Leeds in its yellow, as approved 2026-11-22)
    def main(name, cols):
        if cols and (MC.KITS.get(name) or MC._kit_by_comp(comp, name)):
            return cols[0]
        return next((c for c in cols if not _light(c)), NEUTRAL_FILL)
    hf, af = main(home, hc), main(away, ac)
    if _light(hf) and _light(af):
        af = next((c for c in ac if not _light(c)), NEUTRAL_FILL)
    if _dist(hf, af) < 110:
        other = next((c for c in ac if not _light(c) and _dist(c, hf) >= 110), None)
        light = next((c for c in ac if _light(c) and _dist(c, hf) >= 110), None)
        af = other or light or af
    return hf, af


def _shade(c, k):
    return tuple(max(0, min(255, round(v * k))) for v in c)


def _half(img, x0, x1, c):
    """One half: the club's colour, a little darker towards the bottom."""
    d = ImageDraw.Draw(img)
    for y in range(H):
        d.line([(x0, y), (x1, y)], fill=_shade(c, 1.06 - 0.34 * (y / (H - 1))))


def render(m, out=None, feed=None):
    """The poster for one match dict (matches.json shape). Returns the JPEG
    bytes; also written to `out` when given."""
    import fb_cards as FC
    from site_lib.competitions import match_tv
    from site_lib.dates import day_month
    from site_lib.names import ar_team_in, comp_label
    comp = m.get("competition")
    home, away = ar_team_in(m.get("home"), comp), ar_team_in(m.get("away"), comp)
    hf, af = fills(MC_name(m, "home"), MC_name(m, "away"), comp, feed)
    img = Image.new("RGB", (W, H))
    _half(img, W // 2, W, hf)            # home on the right, as on every card
    _half(img, 0, W // 2, af)
    d = ImageDraw.Draw(img)
    # the seam: a soft shadow, then the kick-off on a white disc over it
    seam = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(seam).rectangle([W // 2 - 26, 0, W // 2 + 26, H], fill=(0, 0, 0, 70))
    seam = seam.filter(ImageFilter.GaussianBlur(22))
    img.paste(seam, (0, 0), seam)

    def ink(c):
        # by brightness, not the channel sum: a club yellow (Villarreal,
        # Leeds) sums under _light yet white on it does not read
        return INK if 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2] > 165 else WHITE

    def text_c(cx, y, s, f, fill):
        s = FC.ar(s)
        d.text((cx - d.textlength(s, font=f) / 2, y), s, font=f, fill=fill)

    def fit(s, weight, size, max_w, min_size=26):
        f = FC.font(weight, size)
        while d.textlength(FC.ar(s), font=f) > max_w and size > min_size:
            size -= 2
            f = FC.font(weight, size)
        return f

    # the head: our wordmark on a white pill (it must read on any club colour)
    d.rounded_rectangle([W // 2 - 150, 44, W // 2 + 150, 136], 46, fill=WHITE, outline=(214, 222, 232), width=3)
    FC.wordmark_at(img, W // 2, 90, 62, anchor="mm")
    tag = "مباراة اليوم"
    tf = FC.font("ExtraBold", 34)
    tw = d.textlength(FC.ar(tag), font=tf)
    d.rounded_rectangle([W // 2 - tw / 2 - 26, 158, W // 2 + tw / 2 + 26, 218], 30, fill=RED)
    text_c(W // 2, 166, tag, tf, WHITE)

    cy, r = 560, 190
    for name, badge, cx, fill in ((home, m.get("home_badge"), W * 3 // 4, hf), (away, m.get("away_badge"), W // 4, af)):
        sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(sh).ellipse([cx - r + 6, cy - r + 16, cx + r + 6, cy + r + 16], fill=(0, 0, 0, 110))
        sh = sh.filter(ImageFilter.GaussianBlur(16))
        img.paste(sh, (0, 0), sh)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=WHITE, outline=(214, 222, 232), width=4)
        im = None
        try:
            im = FC.crest_image(badge, int(2 * r * 0.72)) if badge else None
        except Exception:                                   # noqa: BLE001 - offline, an odd file
            im = None
        if im is not None:
            img.paste(im, (cx - im.width // 2, cy - im.height // 2), im)
        else:
            f1 = FC.font("ExtraBold", int(r * 0.9))
            s1 = FC.ar(FC.initial(name))
            d.text((cx - d.textlength(s1, font=f1) / 2, cy - r * 0.6), s1, font=f1, fill=INK)
        text_c(cx, cy + r + 44, name, fit(name, "ExtraBold", 72, W // 2 - 70), ink(fill))

    # the kick-off, on the seam
    ko = str(m.get("koff_time") or "")
    if ko:
        kf = FC.font("ExtraBold", 92)
        kw = d.textlength(ko, font=kf)
        # a DARK pill with a white edge: it sits on the seam, over two
        # colours either of which may be white
        d.rounded_rectangle([W // 2 - kw / 2 - 40, 1010, W // 2 + kw / 2 + 40, 1140], 64, fill=INK, outline=WHITE, width=5)
        bx = d.textbbox((0, 0), ko, font=kf)
        d.text((W // 2 - (bx[0] + bx[2]) / 2, 1075 - (bx[1] + bx[3]) / 2), ko, font=kf, fill=WHITE)
    # the foot: a dark band, so the facts read whatever the two colours are
    band = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(band).rectangle([0, 1196, W, H], fill=(8, 18, 40, 215))
    img.paste(band, (0, 0), band)
    tv = m.get("channel") or match_tv(m)
    line1 = f"{comp_label(comp)} · {day_month(m.get('kickoff'), weekday=True)}"
    text_c(W // 2, 1216, line1, fit(line1, "ExtraBold", 40, W - 100), WHITE)
    # one script a line: an Arabic sentence with a Latin channel name and a
    # Latin address in it came out in the wrong order
    line2 = "بتوقيت القاهرة" + (f" · على {tv.split(' (')[0]}" if tv else "")
    text_c(W // 2, 1280, line2, fit(line2, "Bold", 32, W - 100), (214, 226, 240))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90, optimize=True)
    data = buf.getvalue()
    if out:
        os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
        with open(out, "wb") as fh:
            fh.write(data)
    return data


def MC_name(m, side):
    """The name our KITS table is keyed on: the site's Arabic name."""
    from site_lib.names import ar_team
    return ar_team(m.get(side))


def ours(m):
    """True when one side is a curated club or the national team's page."""
    from site_lib.clubs import MATCH_PIECE_PAGES
    from site_lib.names import _team_match
    return any(_team_match(tp, m) for tp in MATCH_PIECE_PAGES)


def pick(matches, date):
    """The day's poster match: today's hero among the matches still to be
    played, when one of ours is in it - else None."""
    ms = [m for m in matches or []
          if str(m.get("kickoff") or "")[:10] == date and (m.get("status") or "").upper() == "UPCOMING"
          and m.get("home") and m.get("away") and m.get("koff_time")]
    ms = [m for m in ms if ours(m)]
    if not ms:
        return None
    h = DC.day_hero(ms)
    return next((m for m in ms if h is not None and m.get("match_id") == h.get("match_id")), ms[0])


def caption(m):
    from site_lib.competitions import match_tv
    from site_lib.dates import day_month
    from site_lib.names import ar_team_in, comp_label
    comp = m.get("competition")
    h, a = ar_team_in(m.get("home"), comp), ar_team_in(m.get("away"), comp)
    tv = m.get("channel") or match_tv(m)
    lines = [f"🔥 {h} × {a}",
             f"{comp_label(comp)} · {day_month(m.get('kickoff'), weekday=True)} · {m.get('koff_time')} بتوقيت القاهرة"
             + (f" · 📺 {tv}" if tv else ""),
             "",
             "بتشجع مين؟ اكتب اسم فريقك في الكومنتات 👇",
             "",
             f"تفاصيل المباراة لحظة بلحظة: https://elgoon.com/m/{m.get('match_id')}",
             f"#الجون #{h.replace(' ', '_')} #{a.replace(' ', '_')}"]
    return "\n".join(lines)


def armed():
    return (os.environ.get("FB_POSTER", "") or "").strip().lower() == "on"


def publish(m, date, feed=None):
    """Claim-then-post, kind 'poster' / the date: one poster a day. 0 = done
    or nothing to do, 1 = the post failed."""
    import fb_post as P
    import store
    token = os.environ.get("FB_PAGE_TOKEN", "").strip()
    if not armed() or not token:
        print("poster: FB_POSTER is not on" if not armed() else "poster: FB_PAGE_TOKEN not set", "- printed, not posted")
        print(caption(m))
        return 0
    rec = store.get_post(KIND, date)
    if rec and rec.get("post_id"):
        print(f"poster {date}: already posted ({rec['post_id']})")
        return 0
    if not store.claim(KIND, date, title=f"{m.get('home')} x {m.get('away')}"):
        print(f"poster {date}: claimed by another run")
        return 0
    try:
        pid = P.post_photo(token, render(m, feed=feed), caption(m))
        store.record_post(KIND, date, pid, title=f"{m.get('home')} x {m.get('away')}")
        print(f"posted poster {date}: {pid}")
        return 0
    except Exception as e:  # noqa: BLE001
        store.release(KIND, date)
        print(f"poster {date}: post FAILED: {e}")
        return 1


def main():
    import match_brief as MB
    from zoneinfo import ZoneInfo
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="YYYY-MM-DD (default: today, Cairo)")
    ap.add_argument("--out", help="write the JPEG here")
    ap.add_argument("--auto", action="store_true", help="the day's match, if one of ours plays")
    ap.add_argument("--publish", action="store_true")
    args = ap.parse_args()
    date = args.date or datetime.datetime.now(ZoneInfo("Africa/Cairo")).date().isoformat()
    m = pick(MB.load_all()["matches"], date)
    if not m:
        print(f"poster {date}: none of our clubs has a match to play - nothing")
        return 0
    # each club's real colours from the 365scores feed (a club our KITS table
    # lacks was a grey half - user, 2026-11-22: «اعمل البوستر كمان بألوان
    # الفرق الحقيقية»); {} offline, then the table / neutral slate as before
    import fb_cards as FC
    feed = FC._feed_colors(m)
    if args.out:
        render(m, args.out, feed)
        print(f"wrote {args.out}")
        print(caption(m))
    if args.publish:
        return publish(m, date, feed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
