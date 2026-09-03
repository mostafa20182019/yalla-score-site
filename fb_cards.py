#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Yalla Score - Facebook result-card generator.

Renders one 1200x630 PNG per FINISHED match of the curated clubs (TICKER_TEAMS)
from OUR data (data/matches.json + data/goal_events.json): club crests, final
score, scorers, competition, date, and the site brand. Everything on the card
is our own data and design (crests come from the same cache the site serves),
so there is nothing to license. Facebook ranks a native image far above a bare
link post, so the link goes in the post text / first comment.

Usage (from this folder, full python path on this machine):
  python fb_cards.py                    # curated clubs, finished in the last 36h
  python fb_cards.py --hours 72         # widen the window
  python fb_cards.py --match 4804606    # one match, any status/club
  python fb_cards.py --all-finished     # every finished curated match (testing)
  python fb_cards.py --out some/dir     # default: media/cards (git-ignored)
  python fb_cards.py --post --hours 6   # CI: render + publish each new card to the
                                        # Facebook page (Graph API /me/photos);
                                        # inert without FB_PAGE_TOKEN, dedup via
                                        # data/fb_posted.json (committed back)

Output per match: media/cards/<match_id>.png + a ready post text in
media/cards/<match_id>.txt (title line, hashtags, link to the match page).
"""
import argparse, datetime, io, json, os, sys, time, uuid
import urllib.error, urllib.request
from zoneinfo import ZoneInfo

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build_site as b                      # data loaders, crest cache, Arabic names

from PIL import Image, ImageDraw, ImageFont, ImageFilter
import arabic_reshaper
from bidi.algorithm import get_display

# ---------------------------------------------------------------- brand
W, H = 1200, 630
BLUE = (31, 148, 211)        # #1f94d3 — site brand
BLUE_DARK = (12, 78, 118)
WHITE = (255, 255, 255)
INK = (20, 32, 44)
MUTED = (96, 112, 128)
RED = (214, 40, 57)
FONTS = os.path.join(HERE, "assets-src", "fonts")
CAIRO = ZoneInfo("Africa/Cairo")

# Almarai ships NO isolated presentation forms (U+FE8D etc. render as boxes),
# so the reshaper must emit the plain base letter for isolated positions;
# initial/medial/final forms are all present.
_reshaper = arabic_reshaper.ArabicReshaper({
    "delete_harakat": True, "support_ligatures": True,
    "use_unshaped_instead_of_isolated": True,
})

def font(weight, size):
    # BASIC layout on every platform. Linux Pillow wheels ship libraqm, which
    # shapes + reorders Arabic ITSELF; fed our already-reshaped, already-
    # reversed string it reversed it again — the first card posted from the
    # GitHub runner (Ahly 1-0 Smouha, 2026-09-03) came out mirrored with
    # disconnected letters while the same code rendered fine on Windows (no
    # raqm). One engine + our own reshaper/bidi = identical output everywhere.
    return ImageFont.truetype(os.path.join(FONTS, f"Almarai-{weight}.ttf"), size,
                              layout_engine=ImageFont.Layout.BASIC)

def ar(text):
    """Shape + reorder Arabic for PIL (which draws logical order verbatim).
    Latin/digit-only strings pass through unchanged."""
    text = str(text or "")
    if not any("؀" <= ch <= "ۿ" for ch in text):
        return text
    return get_display(_reshaper.reshape(text))

def text_w(draw, s, f):
    l, t, r, bt = draw.textbbox((0, 0), s, font=f)
    return r - l

def draw_center(draw, cx, y, s, f, fill):
    draw.text((cx - text_w(draw, s, f) / 2, y), s, font=f, fill=fill)

def fit(draw, s, weight, size, max_w, min_size=24):
    """Largest font size (<= size) that fits max_w."""
    while size > min_size:
        f = font(weight, size)
        if text_w(draw, s, f) <= max_w:
            return f
        size -= 2
    return font(weight, min_size)

# ---------------------------------------------------------------- crests
def crest_image(url, size):
    """Club crest from the site's crest cache (downloading through build_site's
    local_crest when absent). SVG crests can't be rasterised here → None."""
    if not url:
        return None
    b.local_crest(url)                       # ensures the file is cached when possible
    path = os.path.join(b.CRESTS_CACHE, b._crest_name(url))
    if not os.path.exists(path) or path.lower().endswith(".svg"):
        return None
    try:
        im = Image.open(path).convert("RGBA")
    except Exception:
        return None
    im.thumbnail((size, size), Image.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.paste(im, ((size - im.width) // 2, (size - im.height) // 2), im)
    return canvas

def crest_placeholder(name, size):
    """White disc with the club's first letter — for clubs whose crest is SVG."""
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse((0, 0, size - 1, size - 1), fill=WHITE)
    letter = ar((name or "?").strip()[:1])
    f = font("ExtraBold", int(size * 0.5))
    l, t, r, bt = d.textbbox((0, 0), letter, font=f)
    d.text(((size - (r - l)) / 2 - l, (size - (bt - t)) / 2 - t), letter, font=f, fill=BLUE)
    return im

# ---------------------------------------------------------------- data
def finished_matches(matches, hours=None, only_curated=True):
    now = datetime.datetime.now(CAIRO)
    out = []
    for m in matches:
        if (m.get("status") or "") != "FINISHED":
            continue
        if m.get("home_score") is None or m.get("away_score") is None:
            continue
        if only_curated and not b._is_ticker_team(m):
            continue
        if hours is not None:
            try:
                ko = datetime.datetime.fromisoformat(
                    f"{m['kickoff']}T{m.get('koff_time') or '00:00'}:00").replace(tzinfo=CAIRO)
            except Exception:
                continue
            if (now - ko).total_seconds() > hours * 3600:
                continue
        out.append(m)
    out.sort(key=lambda m: (m.get("kickoff") or "", m.get("koff_time") or ""), reverse=True)
    return out

def scorers_for(m, ge_idx):
    """[(side, 'player  min'), ...] from goal_events, via build_site's matcher
    (handles the reversed home/away disagreement between sources)."""
    goals = b.match_goals(ge_idx, m) or []
    rows = []
    for g in goals:
        tag = f" ({g['tag']})" if g.get("tag") else ""
        mn = f" {g['minute']}'" if g.get("minute") else ""   # ASCII ' — Almarai has no U+2032 prime
        rows.append((g["side"], f"{g['player']}{tag}{mn}"))
    return rows

def ar_date(kick):
    try:
        d = datetime.date.fromisoformat(kick)
    except Exception:
        return kick or ""
    return f"{b._AR_DAYS[d.weekday()]} {d.day} {b._AR_MONTHS[d.month]}"

# ---------------------------------------------------------------- card
def render_card(m, ge_idx):
    im = Image.new("RGB", (W, H), BLUE)
    # vertical gradient: brand blue at the top → deep blue at the bottom
    grad = Image.new("RGB", (1, H))
    for y in range(H):
        t = y / (H - 1)
        grad.putpixel((0, y), tuple(int(BLUE[i] * (1 - t) + BLUE_DARK[i] * t) for i in range(3)))
    im.paste(grad.resize((W, H)))
    d = ImageDraw.Draw(im)

    # soft white "pitch" panel
    panel = (48, 118, W - 48, H - 96)
    d.rounded_rectangle(panel, radius=28, fill=WHITE)

    # header: competition (right, RTL start) + date (left)
    comp = ar(b.comp_label(m.get("competition") or ""))
    f_h = font("Bold", 34)
    d.text((W - 60 - text_w(d, comp, f_h), 48), comp, font=f_h, fill=WHITE)
    date = ar(ar_date(m.get("kickoff")))
    d.text((60, 52), date, font=font("Regular", 30), fill=(225, 238, 247))

    # teams: HOME on the right (RTL), AWAY on the left
    home, away = b.ar_team(m.get("home")), b.ar_team(m.get("away"))
    crest_sz = 170
    cx_home, cx_away = W - 48 - 260, 48 + 260
    top = panel[1] + 36
    for cx, name, url in ((cx_home, home, m.get("home_badge")), (cx_away, away, m.get("away_badge"))):
        cr = crest_image(url, crest_sz) or crest_placeholder(name, crest_sz)
        im.paste(cr, (int(cx - crest_sz / 2), top), cr)
        f_n = fit(d, ar(name), "Bold", 40, 380)
        draw_center(d, cx, top + crest_sz + 18, ar(name), f_n, INK)

    # score pill in the middle
    hs, aws = int(m["home_score"]), int(m["away_score"])
    f_s = font("ExtraBold", 132)
    # RTL card: HOME sits on the right, so its number must be on the right too
    score = f"{aws}  -  {hs}" if hs < 10 and aws < 10 else f"{aws} - {hs}"
    sw = text_w(d, score, f_s)
    pill = (W / 2 - sw / 2 - 34, top + 14, W / 2 + sw / 2 + 34, top + 14 + 168)
    d.rounded_rectangle(pill, radius=40, fill=(238, 245, 250))
    d.text((W / 2 - sw / 2, top + 14 + 8), score, font=f_s, fill=INK)
    ft = ar("انتهت المباراة")
    f_ft = font("Regular", 26)
    draw_center(d, W / 2, pill[3] + 10, ft, f_ft, MUTED)

    # scorers under each team (max 4 per side)
    rows = scorers_for(m, ge_idx)
    f_g = font("Regular", 27)
    y0 = top + crest_sz + 18 + 52 + 14
    for side, cx in (("h", cx_home), ("a", cx_away)):
        y = y0
        for s, txt in [r for r in rows if r[0] == side][:4]:
            line = ar(txt)
            d.ellipse((cx + 186, y + 10, cx + 198, y + 22), fill=RED)  # goal dot on the right edge
            d.text((cx + 176 - text_w(d, line, f_g), y), line, font=f_g, fill=INK)
            y += 36

    # footer brand
    f_b = font("ExtraBold", 40)
    brand = ar("يلا سكور")
    bw = text_w(d, brand, f_b)
    bx = W - 60 - bw
    d.text((bx, H - 74), brand, font=f_b, fill=WHITE)
    d.ellipse((bx - 56, H - 70, bx - 16, H - 30), fill=WHITE)      # brand disc (favicon v3)
    d.text((60, H - 66), "yallascore.site", font=font("Bold", 30), fill=(225, 238, 247))
    return im

def post_text(m):
    home, away = b.ar_team(m.get("home")), b.ar_team(m.get("away"))
    comp = b.comp_label(m.get("competition") or "")
    tags = ["#يلا_سكور"]
    for t in (home, away):
        tags.append("#" + t.replace(" ", "_"))
    tags.append("#" + comp.replace(" ", "_"))
    return (f"⚽ {home} {m['home_score']} - {m['away_score']} {away} | {comp}\n\n"
            f"تفاصيل المباراة والهدافون 👇\n{b.SITE_BASE}{b.match_url(m)}\n\n"
            + " ".join(tags) + "\n")


# ---------------------------------------------------------------- Facebook
GRAPH_PHOTOS = "https://graph.facebook.com/v23.0/me/photos"
STATE_FILE = os.path.join(HERE, "data", "fb_posted.json")   # committed back by publish.yml
STATE_KEEP_DAYS = 7
MAX_ATTEMPTS = 3

def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            st = json.load(f)
    except Exception:
        st = {}
    st.setdefault("posted", {})
    st.setdefault("failed", {})
    # prune: a match id older than a week can never be re-posted anyway
    cutoff = time.time() - STATE_KEEP_DAYS * 86400
    st["posted"] = {k: v for k, v in st["posted"].items() if v.get("ts", 0) >= cutoff}
    return st

def save_state(st):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=1)

def multipart(fields, files):
    """Minimal multipart/form-data encoder (stdlib only, like fb_post.py).
    files = {name: (filename, bytes, content_type)}."""
    boundary = "----yalla" + uuid.uuid4().hex
    out = io.BytesIO()
    for k, v in fields.items():
        out.write(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n'.encode())
        out.write(str(v).encode("utf-8") + b"\r\n")
    for k, (fn, data, ctype) in files.items():
        out.write((f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"; '
                   f'filename="{fn}"\r\nContent-Type: {ctype}\r\n\r\n').encode())
        out.write(data + b"\r\n")
    out.write(f"--{boundary}--\r\n".encode())
    return out.getvalue(), f"multipart/form-data; boundary={boundary}"

def post_photo(token, png_bytes, caption):
    """Upload the card as a page photo with the post text as caption.
    Returns the Graph post/photo id, raises on failure."""
    body, ctype = multipart({"caption": caption, "access_token": token},
                            {"source": ("card.png", png_bytes, "image/png")})
    req = urllib.request.Request(GRAPH_PHOTOS, data=body,
                                 headers={"Content-Type": ctype, "Content-Length": str(len(body))})
    with urllib.request.urlopen(req, timeout=60) as r:
        resp = json.load(r)
    return resp.get("post_id") or resp.get("id")

def post_cards(picked, ge_idx, out_dir):
    """CI entry: render + publish every not-yet-posted card in `picked`.
    Never raises - a social error must not fail the publish workflow."""
    token = os.environ.get("FB_PAGE_TOKEN", "").strip()
    st = load_state()
    todo = [m for m in picked
            if str(m["match_id"]) not in st["posted"]
            and st["failed"].get(str(m["match_id"]), 0) < MAX_ATTEMPTS]
    if not todo:
        print("fb cards: nothing new to post")
        return
    if not token:
        # inert until the FB_PAGE_TOKEN secret exists; state untouched so the
        # first run WITH a token posts only what is still inside the window
        print(f"FB_PAGE_TOKEN not set - {len(todo)} card(s) would be posted, skipping")
        return
    os.makedirs(out_dir, exist_ok=True)
    for m in todo:
        mid = str(m["match_id"])
        try:
            card = render_card(m, ge_idx)
            buf = io.BytesIO()
            card.save(buf, "PNG", optimize=True)
            card.save(os.path.join(out_dir, f"{mid}.png"), "PNG", optimize=True)
            pid = post_photo(token, buf.getvalue(), post_text(m))
            st["posted"][mid] = {"ts": time.time(), "post_id": pid,
                                 "h": m.get("home"), "a": m.get("away"),
                                 "s": f"{m['home_score']}-{m['away_score']}"}
            st["failed"].pop(mid, None)
            print(f"posted card {mid} {b.ar_team(m['home'])} {m['home_score']}-{m['away_score']} "
                  f"{b.ar_team(m['away'])} -> {pid}")
        except urllib.error.HTTPError as e:
            st["failed"][mid] = st["failed"].get(mid, 0) + 1
            print(f"card {mid} FAILED: HTTP {e.code} {e.read().decode('utf-8', 'replace')[:300]}")
        except Exception as e:  # noqa: BLE001
            st["failed"][mid] = st["failed"].get(mid, 0) + 1
            print(f"card {mid} FAILED: {e}")
    save_state(st)

# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="Facebook result cards from Yalla Score data")
    ap.add_argument("--hours", type=float, default=36, help="finished within the last N hours (default 36)")
    ap.add_argument("--match", type=int, help="render this match_id only (any club/status)")
    ap.add_argument("--all-finished", action="store_true", help="ignore the time window")
    ap.add_argument("--out", default=os.path.join(HERE, "media", "cards"))
    ap.add_argument("--post", action="store_true",
                    help="publish new cards to the Facebook page (needs FB_PAGE_TOKEN; dedup in data/fb_posted.json)")
    args = ap.parse_args()

    matches = b.load("matches.json")
    ge_idx = b.goal_events_index(b.load("goal_events.json"))
    if args.match:
        picked = [m for m in matches if m.get("match_id") == args.match]
    elif args.all_finished:
        picked = finished_matches(matches, None)
    else:
        picked = finished_matches(matches, args.hours)
    if args.post:
        post_cards(picked, ge_idx, args.out)
        return 0
    if not picked:
        print("no matches to render")
        return 0
    os.makedirs(args.out, exist_ok=True)
    for m in picked:
        card = render_card(m, ge_idx)
        png = os.path.join(args.out, f"{m['match_id']}.png")
        card.save(png, "PNG", optimize=True)
        with open(os.path.join(args.out, f"{m['match_id']}.txt"), "w", encoding="utf-8") as f:
            f.write(post_text(m))
        print(f"{m['match_id']}  {b.ar_team(m['home'])} {m['home_score']}-{m['away_score']} "
              f"{b.ar_team(m['away'])}  -> {png}")
    print(f"{len(picked)} card(s) in {args.out}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
