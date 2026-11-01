#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Yalla Score — vertical match reel (1080x1920) from OUR data and design.

    python fb_reel.py --match 560586              # preview: the card as a PNG
    python fb_reel.py --match 560586 --mp4        # the MP4: the card + music

Why a reel: on a page this size, Reels is the one Facebook surface with organic
reach left, and the site's bottleneck is distribution, not content
(7 pages indexed, 732 «Discovered – not indexed» — see the indexing note).

What is in it (since 2026-11-01, the user's ask): ONE still card - the two
crests and names, home on the right, and the final score - held ten seconds
under music (our own generated loop, or a royalty-free file from music/).
Before that it was a 17-second animation with scorers, ratings and the table.
**No broadcast footage, ever**: match video is licensed to the rights
holders, and an AdSense review is not the moment to borrow any.

It reuses fb_cards.py for every primitive (fonts, the Arabic reshaper with its
libraqm lesson, crests) so a reel cannot drift from the cards.

Assembling the MP4 needs ffmpeg: the GitHub runner installs it, the laptop
uses the binary from `pip install imageio-ffmpeg`.
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
import zlib

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
OUT_FPS = 30                  # Reels wants a normal frame rate

W, H = 1080, 1920
# One still card held REEL_SECS under music (user, 2026-11-01). It was a
# five-scene animation (intro, score, scorers, rating, table) at 12 fps.
REEL_SECS = 10.0


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


# ---------------------------------------------------------------- the card
def card(ctx):
    """The whole reel: ONE still (user, 2026-11-01: «يكون عبارة عن صورة فقط
    فيها الفريقين والنتيجة»). Home on the RIGHT - Arabic reads right to left,
    so the first-named club sits where the eye starts - and its goals on the
    right of the score box too («صاحب الارض يكون على اليمين»). The animated
    five-scene reel (intro, score, scorers, rating, table) is gone."""
    im = ctx["bg"].copy()
    d = ImageDraw.Draw(im)
    header(d, ctx["comp"], ctx["round"])
    size, y = 300, H * 0.36
    for x, key, name in ((W * 0.74, "home", ctx["home"]), (W * 0.26, "away", ctx["away"])):
        crest_at(im, ctx["m"].get(f"{key}_badge"), name, size, x, y)
        C.draw_center(d, x, y + size * 0.62, C.ar(name),
                      C.fit(d, C.ar(name), "ExtraBold", 54, W * 0.44), C.WHITE)
    sy, box, fs = H * 0.60, 280, 170
    d.rounded_rectangle((W / 2 - box, sy - 130, W / 2 + box, sy + 150), 40, fill=C.WHITE)
    for val, x in ((ctx["hs"], W / 2 + box * 0.5), (ctx["as"], W / 2 - box * 0.5)):
        C.draw_center(d, x, sy - fs * 0.42, str(val), C.font("ExtraBold", fs), C.INK)
    C.draw_center(d, W / 2, sy - 40, "-", C.font("ExtraBold", 100), (190, 205, 215))
    C.draw_center(d, W / 2, sy + 190, C.ar(f"انتهت · {ctx['when']}"), C.font("Bold", 38),
                  (226, 240, 250))
    # the scorers (user, same day: «ضيف كمان مسجلى الاهداف»): each club's under
    # its own side, home right, one row per player with all his minutes
    cols = goal_columns(ctx["scorers"])
    gy = sy + 270
    for x, key in ((W * 0.74, "h"), (W * 0.26, "a")):
        rows = cols.get(key) or []
        shown = rows[:MAX_GOAL_ROWS] if len(rows) <= MAX_GOAL_ROWS else rows[:MAX_GOAL_ROWS - 1]
        for i, (name, mins) in enumerate(shown):
            line = C.ar(f"{name} {mins}".strip())
            C.draw_center(d, x, gy + i * 58, line, C.fit(d, line, "Bold", 38, W * 0.44, 26),
                          C.WHITE)
        if len(rows) > len(shown):
            C.draw_center(d, x, gy + len(shown) * 58, C.ar(f"+{len(rows) - len(shown)}"),
                          C.font("Bold", 34), (222, 238, 248))
    footer(d)
    return im


MAX_GOAL_ROWS = 5                 # per club; a sixth scorer becomes «+n»


def goal_columns(scorers):
    """{'h': [(name, "12' 45+2'"), ...], 'a': [...]}: one row per SCORER, in
    the order of his first goal, with every minute side by side (a hat-trick is
    one row, not three). A goal without a minute still names the scorer; a
    goal with an unknown side is dropped rather than put under the wrong club."""
    cols = {"h": [], "a": []}
    for side, name, minute in scorers:
        if side not in cols:
            continue
        row = next((r for r in cols[side] if r[0] == name), None)
        if row is None:
            row = [name, []]
            cols[side].append(row)
        if minute:
            row[1].append(minute.rstrip("'") + "'")
    return {k: [(n, " ".join(ms)) for n, ms in v] for k, v in cols.items()}


# ---------------------------------------------------------------- the music
# «وضيف موسيقى» (user, 2026-11-01). The tracks are the files in music/, one
# picked per match id so consecutive reels vary. Every one must be
# royalty-free: Facebook mutes or blocks a reel carrying a copyrighted song.
# music/yalla-loop.m4a is OUR OWN, made by compose() below
# (`python fb_reel.py --compose music/yalla-loop.m4a`) - committed rather
# than made per run, because compose needs numpy and the runner does not
# install it. With music/ empty: compose if numpy is there, else the silent
# track Reels needs (None -> anullsrc in encode).
MUSIC_DIR = os.path.join(HERE, "music")
MUSIC_EXT = (".mp3", ".m4a", ".aac", ".wav", ".ogg")
SR = 44100


def music_track(seed, tmp_dir, secs=REEL_SECS):
    files = (sorted(f for f in os.listdir(MUSIC_DIR) if f.lower().endswith(MUSIC_EXT))
             if os.path.isdir(MUSIC_DIR) else [])
    if files:
        return os.path.join(MUSIC_DIR, files[zlib.crc32(str(seed).encode()) % len(files)])
    path = os.path.join(tmp_dir, "music.wav")
    try:
        compose(path, secs)
    except ImportError:
        print("  music/ is empty and numpy is missing: silent track")
        return None
    return path


def compose(path, secs=REEL_SECS, bpm=120):
    """An upbeat 120 BPM loop - kick, clap, hats, bass, pad and a plucked
    arpeggio over C-G-Am-F - synthesised here, written as 16-bit stereo WAV.
    Deterministic (fixed noise seed): every reel carries the same jingle."""
    import numpy as np                              # noqa: PLC0415
    import wave                                     # noqa: PLC0415
    n = int(secs * SR)
    left, right = np.zeros(n), np.zeros(n)
    rng = np.random.default_rng(7)
    beat = 60.0 / bpm
    bar = 4 * beat

    def hz(midi):
        return 440.0 * 2 ** ((midi - 69) / 12)

    def at(sig, start, pan=0.0):
        i = int(start * SR)
        if i >= n:
            return
        sig = sig[:n - i]
        left[i:i + len(sig)] += sig * (1 - max(pan, 0))
        right[i:i + len(sig)] += sig * (1 + min(pan, 0))

    def tt(dur):
        return np.arange(int(dur * SR)) / SR

    def tone(f, dur, decay, harm=(1.0,), detune=0.0):
        t = tt(dur)
        s = sum(a * np.sin(2 * np.pi * f * (k + 1) * (1 + detune) * t) for k, a in enumerate(harm))
        return s * np.exp(-t * decay)

    t = tt(0.28)
    kick = np.sin(2 * np.pi * np.cumsum(45 + 110 * np.exp(-t * 30)) / SR) * np.exp(-t * 14)
    t = tt(0.18)
    noise = rng.standard_normal(len(t))
    clap = (np.diff(noise, prepend=0) * 0.5 + np.sin(2 * np.pi * 190 * t)) * np.exp(-t * 26)
    t = tt(0.05)
    hat = np.diff(np.diff(rng.standard_normal(len(t)), prepend=0), prepend=0) * np.exp(-t * 90)

    prog = [(36, (60, 64, 67)), (43, (59, 62, 67)), (45, (57, 60, 64)), (41, (57, 60, 65))]
    for bi in range(int(secs / bar) + 1):
        root, chord = prog[bi % len(prog)]
        t0 = bi * bar
        for q in range(4):
            at(kick * 0.9, t0 + q * beat)
            if q % 2:
                at(clap * 0.35, t0 + q * beat)
        for e in range(8):
            at(hat * 0.12, t0 + e * beat / 2 + beat / 4, pan=0.3)
            at(tone(hz(root), beat / 2 * 0.9, 7, harm=(1, .5, .33, .25, .2)) * 0.22,
               t0 + e * beat / 2)
        for k, m in enumerate(chord):                # the pad, wide
            t = tt(bar)
            env = np.minimum(t / 0.25, 1) * np.exp(-t * 0.4)
            at(np.sin(2 * np.pi * hz(m) * t) * env * 0.06, t0, pan=-0.5 + k * 0.5)
            at(np.sin(2 * np.pi * hz(m) * 1.004 * t) * env * 0.04, t0, pan=0.5 - k * 0.5)
        arp = [chord[0] + 12, chord[1] + 12, chord[2] + 12, chord[1] + 12]
        for s in range(16):
            at(tone(hz(arp[s % 4]), beat / 4 * 1.6, 11, harm=(1, .35, .15)) * 0.11,
               t0 + s * beat / 4, pan=0.25 if s % 2 else -0.25)
    mix = np.stack([left, right], axis=1)
    fade = int(1.2 * SR)
    mix[-fade:] *= np.linspace(1, 0, fade)[:, None]
    mix = np.tanh(mix / (np.abs(mix).max() or 1) * 1.4) * 0.89
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((mix * 32767).astype("<i2").tobytes())


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


# ---------------------------------------------------------------- encoding
def ffmpeg():
    """ffmpeg on PATH (the GitHub runner), else the binary the imageio-ffmpeg
    wheel ships (pip install imageio-ffmpeg - the laptop, 2026-10-08), else None."""
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg                       # noqa: PLC0415
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:                               # noqa: BLE001
        return None


def encode(im, path, seed="", secs=REEL_SECS):
    """Write an MP4 the Reels API accepts. Returns True when it is uploadable.

    The card held `secs` seconds under the music: H.264 / yuv420p / 30 fps,
    faststart, AAC stereo. Reels refuses a file with no audio stream, and the
    music IS that stream now (it was a silent track before 2026-11-01). A
    short user track loops (-stream_loop) instead of cutting the video;
    the sound fades in and out.

    No ffmpeg (this laptop without imageio-ffmpeg) = no MP4 and it says so,
    rather than writing a preview that pretends to be publishable."""
    exe = ffmpeg()
    if not exe:
        print("  no ffmpeg: pip install imageio-ffmpeg (laptop) or apt ffmpeg (runner)")
        return False
    tmp = tempfile.mkdtemp(prefix="reel-")
    try:
        png = os.path.join(tmp, "card.png")
        im.save(png)
        audio = music_track(seed, tmp, secs)
        a_in = (["-stream_loop", "-1", "-i", audio] if audio
                else ["-f", "lavfi", "-i", f"anullsrc=r={SR}:cl=stereo"])
        cmd = [exe, "-y", "-loglevel", "error",
               "-loop", "1", "-framerate", str(OUT_FPS), "-i", png, *a_in,
               "-map", "0:v", "-map", "1:a", "-t", f"{secs:.2f}",
               "-c:v", "libx264", "-preset", "medium", "-tune", "stillimage", "-crf", "20",
               "-pix_fmt", "yuv420p", "-r", str(OUT_FPS), "-profile:v", "high",
               "-af", f"afade=t=in:d=0.3,afade=t=out:st={secs - 1.5:.2f}:d=1.5",
               "-c:a", "aac", "-b:a", "128k", "-ar", str(SR), "-ac", "2",
               "-movflags", "+faststart", path]
        subprocess.run(cmd, check=True)
        return True
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


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

    Until 2026-11-01 a reel also needed NAMED scorers (a 4-0 whose goals scene
    was skipped read as broken). The reel is now the score card alone, so any
    finished curated match qualifies; the score is still verified against
    365scores before the claim (auto)."""
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
        if m.get("home_score") is None or m.get("away_score") is None:
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
            if not encode(card(ctx), path, seed=mid):
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
    ap.add_argument("--png", action="store_true", help="write the card as a PNG")
    ap.add_argument("--mp4", action="store_true", help="write the MP4 (card + music)")
    ap.add_argument("--compose", metavar="PATH", help="write our own music loop (.wav or .m4a)")
    ap.add_argument("--auto", action="store_true", help="publish the newest eligible reel")
    ap.add_argument("--dry", action="store_true", help="say what --auto would do")
    ap.add_argument("--plan", action="store_true", help="print yes/no for the workflow")
    ap.add_argument("--out", default=os.path.join(HERE, "media", "reels"))
    args = ap.parse_args()
    if args.plan:
        return plan()
    if args.compose:
        wav = args.compose if args.compose.lower().endswith(".wav") else args.compose + ".wav"
        compose(wav, REEL_SECS)
        if wav != args.compose:          # .m4a: AAC is a tenth of the WAV's size
            subprocess.run([ffmpeg(), "-y", "-loglevel", "error", "-i", wav, "-c:a", "aac",
                            "-b:a", "128k", args.compose], check=True)
            os.remove(wav)
        print(f"music → {args.compose}  ({os.path.getsize(args.compose) / 1024:.0f} KB)")
        return 0
    if args.auto or args.dry:
        return auto(dry=args.dry, out_dir=args.out)
    if not args.match:
        ap.print_help()
        return 0
    os.makedirs(args.out, exist_ok=True)
    ctx = context(args.match)
    im = card(ctx)
    print(f"{ctx['home']} {ctx['hs']}-{ctx['as']} {ctx['away']} ({REEL_SECS:.0f}s)")
    if args.png or not args.mp4:
        png = os.path.join(args.out, f"{args.match}.png")
        im.save(png)
        print(f"png → {png}")
    if args.mp4:
        mp4 = os.path.join(args.out, f"{args.match}.mp4")
        if encode(im, mp4, seed=args.match):
            print(f"mp4 → {mp4}  ({os.path.getsize(mp4) / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
