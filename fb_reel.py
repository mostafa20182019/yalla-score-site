#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Yalla Score — vertical match reel (1080x1920) from OUR data and design.

    python fb_reel.py --match 560586 --gif        # preview: a GIF + a contact sheet
    python fb_reel.py --match 560586 --frames out # the PNG frames (for ffmpeg)

Why a reel: on a page this size, Reels is the one Facebook surface with organic
reach left, and the site's bottleneck is distribution, not content
(7 pages indexed, 732 «Discovered – not indexed» — see the indexing note).

What is in it: the crests from the site's own cache, the final score, the
scorers with their minutes, the match ratings and the table line — the same
numbers the match page shows. **No broadcast footage, ever**: match video is
licensed to the rights holders, and an AdSense review is not the moment to
borrow any.

It reuses fb_cards.py for every primitive (fonts, the Arabic reshaper with its
libraqm lesson, crests, scorers) so a reel cannot drift from the cards.

Assembling the MP4 needs ffmpeg, which GitHub runners have and this machine
does not — hence --gif, which needs nothing but Pillow and is what a preview
is for.
"""
import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")

import build_site as b       # noqa: E402
import fb_cards as C         # noqa: E402  - fonts, Arabic, crests, AND the
                             #               finished/verified match rules
import store                 # noqa: E402  - claim-then-post, same as everything else

KIND = "reel"                 # its own dedup namespace next to article/card/tg
GRAPH = "https://graph.facebook.com/v23.0"
MAX_AGE_H = 20                # a reel of a two-day-old match is not a reel
MAX_PER_RUN = 1               # one reel a run; the page is not a video channel
OUT_FPS = 30                  # Reels wants a normal frame rate, not our 12

W, H = 1080, 1920
FPS = 12
SCENES = [("intro", 2.0), ("score", 3.5), ("scorers", 3.5), ("rating", 2.5), ("cta", 2.0)]


# ---------------------------------------------------------------- easing
def ease(t):
    """0..1 → 0..1, fast then settling. Linear motion looks mechanical."""
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def lerp(a, b, t):
    return a + (b - a) * t


# ---------------------------------------------------------------- canvas
def background():
    """The brand gradient, once — every frame is pasted onto a copy."""
    im = Image.new("RGB", (W, H), C.BLUE_DARK)
    top = Image.new("RGB", (W, H), C.BLUE)
    mask = Image.linear_gradient("L").resize((W, H))
    im = Image.composite(im, top, mask)
    d = ImageDraw.Draw(im)
    # a soft glow behind the middle, so white text never sits on flat colour
    glow = Image.new("L", (W, H), 0)
    ImageDraw.Draw(glow).ellipse((-200, H * 0.18, W + 200, H * 0.72), fill=90)
    im = Image.composite(Image.new("RGB", (W, H), (255, 255, 255)), im,
                         glow.filter(ImageFilter.GaussianBlur(160)))
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, W, 8), fill=C.WHITE)
    return im


def header(d, comp, rnd):
    f = C.font("ExtraBold", 44)
    C.draw_center(d, W / 2, 70, C.ar("يلا سكور"), f, C.WHITE)
    sub = comp + (f" · الجولة {rnd}" if rnd else "")
    C.draw_center(d, W / 2, 140, C.ar(sub), C.font("Bold", 34), (222, 238, 248))


def footer(d, alpha=255):
    C.draw_center(d, W / 2, H - 120, C.ar("التحليل الكامل بالأرقام"),
                  C.font("Bold", 34), (222, 238, 248))
    C.draw_center(d, W / 2, H - 70, "yallascore.site", C.font("ExtraBold", 40), C.WHITE)


def crest_at(im, url, name, size, cx, cy, alpha=255):
    cr = C.crest_image(url, size) or C.crest_placeholder(name, size)
    if alpha < 255:
        cr = cr.copy()
        a = cr.getchannel("A").point(lambda v: v * alpha // 255)
        cr.putalpha(a)
    im.paste(cr, (int(cx - size / 2), int(cy - size / 2)), cr)


# ---------------------------------------------------------------- scenes
def scene_intro(t, ctx):
    """Crests slide in from the edges, names fade under them."""
    im = ctx["bg"].copy()
    d = ImageDraw.Draw(im)
    header(d, ctx["comp"], ctx["round"])
    p = ease(t / 1.4)
    size = 300
    y = H * 0.40
    crest_at(im, ctx["m"].get("home_badge"), ctx["home"], size,
             lerp(-size, W * 0.28, p), y)
    crest_at(im, ctx["m"].get("away_badge"), ctx["away"], size,
             lerp(W + size, W * 0.72, p), y)
    if t > 0.7:
        a = int(255 * ease((t - 0.7) / 0.7))
        nf = C.fit(d, C.ar(ctx["home"]), "ExtraBold", 52, W * 0.42)
        C.draw_center(d, W * 0.28, y + size * 0.62, C.ar(ctx["home"]), nf, (255, 255, 255, a))
        nf = C.fit(d, C.ar(ctx["away"]), "ExtraBold", 52, W * 0.42)
        C.draw_center(d, W * 0.72, y + size * 0.62, C.ar(ctx["away"]), nf, (255, 255, 255, a))
    footer(d)
    return im


def scene_score(t, ctx):
    """The score lands digit by digit, then holds."""
    im = ctx["bg"].copy()
    d = ImageDraw.Draw(im)
    header(d, ctx["comp"], ctx["round"])
    size = 230
    y = H * 0.32
    crest_at(im, ctx["m"].get("home_badge"), ctx["home"], size, W * 0.24, y)
    crest_at(im, ctx["m"].get("away_badge"), ctx["away"], size, W * 0.76, y)
    C.draw_center(d, W * 0.24, y + size * 0.62, C.ar(ctx["home"]),
                  C.fit(d, C.ar(ctx["home"]), "Bold", 44, W * 0.40), C.WHITE)
    C.draw_center(d, W * 0.76, y + size * 0.62, C.ar(ctx["away"]),
                  C.fit(d, C.ar(ctx["away"]), "Bold", 44, W * 0.40), C.WHITE)
    # the score: home digit at 0.3s, away at 0.9s, each popping in
    sy = H * 0.56
    box = 260
    d.rounded_rectangle((W / 2 - box, sy - 110, W / 2 + box, sy + 130), 36, fill=C.WHITE)
    for i, (val, x) in enumerate(((ctx["hs"], W / 2 - box * 0.48),
                                  (ctx["as"], W / 2 + box * 0.48))):
        start = 0.3 + i * 0.6
        if t < start:
            continue
        k = ease((t - start) / 0.45)
        fs = int(lerp(60, 150, k))
        C.draw_center(d, x, sy - fs * 0.42, str(val), C.font("ExtraBold", fs), C.INK)
    C.draw_center(d, W / 2, sy - 40, "-", C.font("ExtraBold", 90), (190, 205, 215))
    if t > 1.9:
        C.draw_center(d, W / 2, sy + 160, C.ar(ctx["when"]), C.font("Bold", 34),
                      (226, 240, 250))
    footer(d)
    return im


def scene_scorers(t, ctx):
    """Each scorer slides up in turn: name, minute, and which side."""
    im = ctx["bg"].copy()
    d = ImageDraw.Draw(im)
    header(d, ctx["comp"], ctx["round"])
    C.draw_center(d, W / 2, H * 0.22, C.ar("مسجلو الأهداف"), C.font("ExtraBold", 56), C.WHITE)
    rows = ctx["scorers"][:6]
    for i, (side, name, minute) in enumerate(rows):
        start = 0.25 * i
        if t < start:
            continue
        k = ease(min(1.0, (t - start) / 0.5))
        y = H * 0.32 + i * 130 + (1 - k) * 60
        pad = 60
        d.rounded_rectangle((pad, y, W - pad, y + 104), 26,
                            fill=(255, 255, 255) if k > 0.5 else (235, 245, 252))
        club = ctx["home"] if side == "h" else ctx["away"]
        f = C.fit(d, C.ar(name), "ExtraBold", 46, W * 0.52)
        d.text((W - pad - 40 - C.text_w(d, C.ar(name), f), y + 26), C.ar(name), font=f, fill=C.INK)
        mt = f"{minute}'" if minute else ""
        d.text((pad + 40, y + 30), mt, font=C.font("ExtraBold", 44), fill=C.BLUE)
        cf = C.font("Bold", 30)
        d.text((pad + 150, y + 38), C.ar(club), font=cf, fill=C.MUTED)
    footer(d)
    return im


def scene_rating(t, ctx):
    """Best player of the match and the two team averages."""
    im = ctx["bg"].copy()
    d = ImageDraw.Draw(im)
    header(d, ctx["comp"], ctx["round"])
    r = ctx["rating"]
    C.draw_center(d, W / 2, H * 0.24, C.ar("الأفضل في اللقاء"), C.font("ExtraBold", 54), C.WHITE)
    k = ease(min(1.0, t / 0.6))
    box_h = int(300 * k)
    d.rounded_rectangle((90, H * 0.33, W - 90, H * 0.33 + box_h), 34, fill=C.WHITE)
    if k > 0.6:
        C.draw_center(d, W / 2, H * 0.36, C.ar(r["best"]["name"]),
                      C.fit(d, C.ar(r["best"]["name"]), "ExtraBold", 62, W * 0.7), C.INK)
        C.draw_center(d, W / 2, H * 0.36 + 90, C.ar(r["best"]["club"]),
                      C.font("Bold", 40), C.MUTED)
        C.draw_center(d, W / 2, H * 0.36 + 150, f'{r["best"]["rt"]:.1f}',
                      C.font("ExtraBold", 72), C.BLUE)
    if t > 1.0:
        a = ease((t - 1.0) / 0.6)
        y = H * 0.62
        C.draw_center(d, W / 2, y, C.ar("متوسط تقييم التشكيلة"), C.font("Bold", 36),
                      (226, 240, 250))
        for i, s in enumerate(r["sides"]):
            x = W * (0.28 if i == 0 else 0.72)
            C.draw_center(d, x, y + 70, C.ar(s["club"]),
                          C.fit(d, C.ar(s["club"]), "Bold", 40, W * 0.40), C.WHITE)
            C.draw_center(d, x, y + 130, f'{s["avg"]:.1f}',
                          C.font("ExtraBold", int(64 * a)), C.WHITE)
    footer(d)
    return im


def scene_cta(t, ctx):
    im = ctx["bg"].copy()
    d = ImageDraw.Draw(im)
    header(d, ctx["comp"], ctx["round"])
    lines = ctx["table"] or [ctx["headline"]]
    C.draw_center(d, W / 2, H * 0.26, C.ar("بعد هذه النتيجة" if ctx["table"] else "التفاصيل"),
                  C.font("ExtraBold", 54), C.WHITE)
    y = H * 0.36
    f = C.font("Bold", 38)
    for i, line in enumerate(lines[:2]):
        if t < 0.3 * i:
            continue
        k = ease(min(1.0, (t - 0.3 * i) / 0.5))
        for chunk in wrap(d, line, f, W - 240, lines=3):
            # a white card with DARK text: white-on-white drew four empty bars
            # in the first preview, and an RGB canvas ignores the alpha in a
            # fill colour, so there is no translucent shortcut here
            slide = int((1 - k) * 40)
            d.rounded_rectangle((90, y - 14 + slide, W - 90, y + 64 + slide), 20, fill=C.WHITE)
            C.draw_center(d, W / 2, y + slide, chunk, f, C.INK)
            y += 92
        y += 24
    k = ease(min(1.0, max(0.0, (t - 0.9) / 0.6)))
    if k > 0.02:
        C.draw_center(d, W / 2, H * 0.76, C.ar("التحليل الكامل بالأرقام على"),
                      C.font("Bold", max(1, int(42 * k))), (226, 240, 250))
        C.draw_center(d, W / 2, H * 0.76 + 70, "yallascore.site",
                      C.font("ExtraBold", max(1, int(68 * k))), C.WHITE)
    return im                      # no footer here: it would say the same twice


def wrap(d, s, f, max_w, lines=3):
    """Greedy wrap on LOGICAL Arabic; each line is shaped on the way out.

    Wrapping the shaped string instead put the end of the sentence on the first
    line: C.ar() returns visual order, so its leading words are the ones that
    print leftmost - the tail. Split first, shape after."""
    words, out, cur = (s or "").split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if C.text_w(d, C.ar(t), f) <= max_w or not cur:
            cur = t
        else:
            out.append(cur)
            cur = w
    if cur:
        out.append(cur)
    return [C.ar(x) for x in out[:lines]]


SCENE_FN = {"intro": scene_intro, "score": scene_score, "scorers": scene_scorers,
            "rating": scene_rating, "cta": scene_cta}


# ---------------------------------------------------------------- data
def context(match_id):
    ms = {str(m.get("match_id")): m for m in b.load("matches_archive.json") + b.load("matches.json")
          if m.get("match_id")}
    m = ms.get(str(match_id))
    if not m:
        raise SystemExit(f"match {match_id} not in the data")
    ge = b.goals_index()
    md = b.match_details_index(b.load("match_details.json"))
    det = b.match_details_for(md, m)
    home, away = b.ar_team(m.get("home")), b.ar_team(m.get("away"))
    goals = b.match_goals(ge, m) or []
    scorers = [(g.get("side"), g.get("player"), (g.get("minute") or "").strip())
               for g in goals if g.get("player")]
    rating = b.match_ratings(det[0], det[1], home, away) if det else None
    st = {s.get("competition"): s for s in b.load("standings.json")}
    forms = b.team_form(b.load("fixtures.json"), b.load("standings.json"))
    fin = b._finished_by_comp(b.load("fixtures.json")).get(m.get("competition")) or []
    table = b.table_after(m, st.get(m.get("competition")), forms.get(m.get("competition")),
                          fin, home, away)
    return {"m": m, "home": home, "away": away, "hs": m.get("home_score"),
            "as": m.get("away_score"), "comp": b.comp_label(m.get("competition") or ""),
            "round": m.get("round"), "when": b.fmt_day(m.get("kickoff")),
            "scorers": scorers, "rating": rating, "table": table,
            "headline": f'{home} {m.get("home_score")}-{m.get("away_score")} {away}',
            "bg": background()}


def frames(ctx):
    out = []
    for name, secs in SCENES:
        if name == "scorers" and not ctx["scorers"]:
            continue
        if name == "rating" and not ctx["rating"]:
            continue
        for i in range(int(secs * FPS)):
            out.append(SCENE_FN[name](i / FPS, ctx))
    return out


# ---------------------------------------------------------------- encoding
def ffmpeg():
    return shutil.which("ffmpeg")


def encode(fs, path):
    """Write an MP4 the Reels API accepts. Returns True when it is uploadable.

    H.264 / yuv420p / 30 fps, faststart, and a SILENT AAC track: Reels is a
    video surface and a file with no audio stream is rejected outright, so the
    track is muxed in rather than hoped for.

    ffmpeg is on the GitHub runner and not on this machine, so there is a cv2
    fallback — and it says so, because what cv2 writes here (MPEG-4 Part 2, no
    audio) is fine to LOOK at and would be refused on upload. A preview that
    pretends to be publishable is worse than no preview."""
    tmp = tempfile.mkdtemp(prefix="reel-")
    try:
        for i, im in enumerate(fs):
            im.save(os.path.join(tmp, f"{i:04d}.png"))
        exe = ffmpeg()
        if exe:
            cmd = [exe, "-y", "-loglevel", "error",
                   "-framerate", str(FPS), "-i", os.path.join(tmp, "%04d.png"),
                   "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                   "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                   "-pix_fmt", "yuv420p", "-r", str(OUT_FPS), "-profile:v", "high",
                   "-c:a", "aac", "-b:a", "64k", "-shortest",
                   "-movflags", "+faststart", path]
            subprocess.run(cmd, check=True)
            return True
        return _encode_preview(fs, path)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _encode_preview(fs, path):
    try:
        import cv2                                  # noqa: PLC0415
        import numpy as np                          # noqa: PLC0415
    except Exception:                               # noqa: BLE001
        print("  no ffmpeg and no cv2: install ffmpeg to write an MP4")
        return False
    vw = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), FPS, (W, H))
    for im in fs:
        vw.write(cv2.cvtColor(np.array(im), cv2.COLOR_RGB2BGR))
    vw.release()
    print("  WARNING: written by cv2 (no ffmpeg) — preview only, NOT uploadable")
    return False


# ---------------------------------------------------------------- Facebook
def _get(url):
    with urllib.request.urlopen(urllib.request.Request(url), timeout=30) as r:
        return json.load(r)


def _post(url, fields):
    import urllib.parse                             # noqa: PLC0415
    data = urllib.parse.urlencode(fields).encode()
    with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=60) as r:
        return json.load(r)


def page_id(token):
    """/me/video_reels does not exist — the Reels endpoint wants the real id."""
    return str(_get(f"{GRAPH}/me?fields=id&access_token={token}").get("id") or "")


def post_reel(token, path, description):
    """start → upload the bytes → finish. Returns the video id.

    Not the feed endpoint fb_post.py uses: a reel is a resumable upload to a
    URL the API hands back, authenticated with an OAuth header rather than a
    query parameter."""
    pid = page_id(token)
    if not pid:
        raise RuntimeError("could not read the page id from the token")
    start = _post(f"{GRAPH}/{pid}/video_reels",
                  {"upload_phase": "start", "access_token": token})
    vid, up = start.get("video_id"), start.get("upload_url")
    if not (vid and up):
        raise RuntimeError(f"reel start refused: {str(start)[:200]}")
    blob = open(path, "rb").read()
    req = urllib.request.Request(up, data=blob, headers={
        "Authorization": f"OAuth {token}",
        "offset": "0",
        "file_size": str(len(blob)),
        "Content-Type": "application/octet-stream",
    })
    with urllib.request.urlopen(req, timeout=600) as r:
        out = json.load(r)
    if not out.get("success", True):
        raise RuntimeError(f"reel upload refused: {str(out)[:200]}")
    fin = _post(f"{GRAPH}/{pid}/video_reels",
                {"upload_phase": "finish", "video_id": vid,
                 "video_state": "PUBLISHED", "description": description,
                 "access_token": token})
    if not fin.get("success", True):
        raise RuntimeError(f"reel finish refused: {str(fin)[:200]}")
    return vid


# ---------------------------------------------------------------- picking
def candidates(hours=MAX_AGE_H, limit=4):
    """Finished curated matches, newest first, that are worth a reel.

    The cheap filters run first because --plan runs on every publish: dedup
    (matches.json and matches_archive.json overlap), then finished + curated +
    inside the window, and only then the per-match context.

    Worth a reel = we can NAME the goals. طرابزون 4-0 غلطة سراي passed an
    earlier "scorers or ratings" rule with zero named scorers, and a reel that
    announces four goals and then skips the goals scene reads as broken."""
    seen, ms = set(), []
    for m in b.load("matches_archive.json") + b.load("matches.json"):
        mid = str(m.get("match_id") or "")
        if not mid or mid in seen:
            continue
        seen.add(mid)
        ms.append(m)
    out = []
    for m in C.finished_matches(ms, hours=hours, only_curated=True)[:limit]:
        try:
            ctx = context(str(m["match_id"]))
        except SystemExit:
            continue
        goals = (m.get("home_score") or 0) + (m.get("away_score") or 0)
        if goals and not ctx["scorers"]:
            continue
        if not (ctx["scorers"] or ctx["rating"]):
            continue
        out.append((m, ctx))
    return out


def enabled():
    """Publishing to the page is the user's switch, not mine."""
    return (os.environ.get("FB_REELS", "").strip().lower() in ("1", "true", "yes", "on"))


def auto(dry=False, out_dir=None):
    """What publish.yml runs. Never raises: a social error must not fail a
    publish. Silent and exit 0 when the switch is off or the token is absent."""
    out_dir = out_dir or os.path.join(HERE, "media", "reels")
    token = os.environ.get("FB_PAGE_TOKEN", "").strip()
    posted = _posted()
    if posted is None:
        return 0                     # no dedup, no post - the next run tries again
    todo = [(m, c) for m, c in candidates() if str(m["match_id"]) not in posted]
    if not todo:
        print("reel: nothing new")
        return 0
    if dry or not enabled() or not token:
        why = ("dry run" if dry else
               "FB_REELS is off" if not enabled() else "FB_PAGE_TOKEN not set")
        print(f"reel: {len(todo)} match(es) would get one ({why})")
        for m, c in todo[:MAX_PER_RUN]:
            print(f"  {m['match_id']}: {c['home']} {c['hs']}-{c['as']} {c['away']}")
        return 0
    os.makedirs(out_dir, exist_ok=True)
    live = C.fetch_live()
    for m, ctx in todo[:MAX_PER_RUN]:
        mid = str(m["match_id"])
        # the score is verified BEFORE the claim, exactly like the cards: a
        # deferral is the common path and claim-then-release on every run is
        # churn. Never publish a number 365scores has not confirmed.
        ok, why = C.score_verified(m, live)
        if not ok:
            print(f"reel {mid} deferred: {why}")
            continue
        if not store.claim(KIND, mid, title=f'{ctx["home"]} - {ctx["away"]}',
                           score=f'{ctx["hs"]}-{ctx["as"]}'):
            print(f"reel {mid}: another run holds it")
            continue
        path = os.path.join(out_dir, f"{mid}.mp4")
        try:
            if not encode(frames(ctx), path):
                print(f"reel {mid}: no usable encoder, deferring")
                store.release(KIND, mid)
                continue
            vid = post_reel(token, path, C.post_text(m))
            store.record_post(KIND, mid, vid, title=f'{ctx["home"]} - {ctx["away"]}',
                              score=f'{ctx["hs"]}-{ctx["as"]}')
            print(f"reel {mid}: published as {vid} — {ctx['home']} {ctx['hs']}-{ctx['as']} {ctx['away']}")
        except urllib.error.HTTPError as e:
            store.release(KIND, mid)
            print(f"reel {mid} FAILED: HTTP {e.code} {e.read().decode('utf-8', 'replace')[:300]}")
        except Exception as e:                       # noqa: BLE001
            store.release(KIND, mid)
            print(f"reel {mid} FAILED: {e}")
    return 0


def _posted():
    """The set of matches already reeled, or None when the store cannot say.

    None is not an empty set. Treating an unreachable store as "nothing posted
    yet" would publish a second reel of a match that already has one — and the
    store IS unreachable sometimes: on 2026-09-20 D1's free-tier daily row-read
    limit refused every query from 15:00 Cairo onward."""
    try:
        return store.posted_ids(KIND)
    except Exception as e:                                   # noqa: BLE001
        print(f"reel: the store cannot be read ({str(e)[:120]}) - deferring")
        return None


def plan():
    """One line for the workflow: is there a reel to make this run? Printing an
    answer costs nothing; installing ffmpeg on every publish run would."""
    posted = _posted()
    todo = [] if posted is None else [m for m, _ in candidates()
                                      if str(m["match_id"]) not in posted]
    print("yes" if (todo and enabled()) else "no")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--match", help="render this match only")
    ap.add_argument("--gif", action="store_true", help="preview GIF + contact sheet")
    ap.add_argument("--mp4", action="store_true", help="write the MP4")
    ap.add_argument("--frames", help="write the PNG frames to this directory")
    ap.add_argument("--auto", action="store_true", help="publish the newest eligible reel")
    ap.add_argument("--dry", action="store_true", help="say what --auto would do")
    ap.add_argument("--plan", action="store_true", help="print yes/no for the workflow")
    ap.add_argument("--out", default=os.path.join(HERE, "media", "reels"))
    args = ap.parse_args()
    if args.plan:
        return plan()
    if args.auto or args.dry:
        return auto(dry=args.dry, out_dir=args.out)
    if not args.match:
        ap.print_help()
        return 0
    os.makedirs(args.out, exist_ok=True)
    ctx = context(args.match)
    fs = frames(ctx)
    print(f"{len(fs)} frames ({len(fs) / FPS:.1f}s) — {ctx['home']} {ctx['hs']}-{ctx['as']} {ctx['away']}")
    if args.frames:
        os.makedirs(args.frames, exist_ok=True)
        for i, im in enumerate(fs):
            im.save(os.path.join(args.frames, f"{i:04d}.png"))
        print(f"frames → {args.frames}")
    if args.gif:
        small = [f.resize((W // 3, H // 3), Image.LANCZOS) for f in fs[::2]]
        gif = os.path.join(args.out, f"{args.match}.gif")
        small[0].save(gif, save_all=True, append_images=small[1:],
                      duration=int(2000 / FPS), loop=0, optimize=True)
        print(f"gif → {gif}  ({os.path.getsize(gif) / 1024:.0f} KB)")
        # a contact sheet, so the motion can be judged in one still
        picks = [fs[int(len(fs) * p)] for p in (0.05, 0.18, 0.32, 0.45, 0.58, 0.72, 0.85, 0.97)]
        cols, cw = 4, W // 4
        sheet = Image.new("RGB", (cols * cw, 2 * (H // 4)), (12, 20, 28))
        for i, im in enumerate(picks):
            sheet.paste(im.resize((cw, H // 4), Image.LANCZOS), ((i % cols) * cw, (i // cols) * (H // 4)))
        sh = os.path.join(args.out, f"{args.match}-sheet.jpg")
        sheet.save(sh, quality=88)
        print(f"sheet → {sh}")
    if args.mp4:
        mp4 = os.path.join(args.out, f"{args.match}.mp4")
        ok = encode(fs, mp4)
        print(f"mp4 → {mp4}  ({os.path.getsize(mp4) / 1024:.0f} KB)"
              + ("" if ok else "  [preview only]"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
