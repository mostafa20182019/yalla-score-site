#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Elgoon — the MOMENT reel (2026-11-05): a historic football moment told as a
~16-second vertical video (1080x1920) of moving typography on the brand canvas.

    python moment_reel.py --script moments/salah-congo-2017.json --out /tmp/x.mp4 --sheet /tmp/x.png
    python moment_reel.py --script moments/salah-congo-2017.json --publish     # fb-post.yml moment=<id>

Why: the user (2026-11-05): «الريلز بتجيب متابعين ... ممكن ريلز ماتشات قديمة أو
لحظات مؤثرة». Reels is the one Facebook surface with organic reach left, and a
moment everyone remembers travels further than tonight's score.

What a moment reel is made of — and only of: short Arabic lines landing one
after another, a big number or score, the two crests from the site's cache,
ONE licensed photo (Wikimedia Commons, CC, credited on the frame AND in the
caption), the brand mark and our own music loop. **No broadcast footage,
ever, and no press photos**: match video and agency pictures belong to the
rights holders.

The script is a JSON file in moments/ (scenes, lines, photo, caption), so the
next moment is a new JSON, not new code. Every primitive comes from
fb_cards.py / fb_reel.py (fonts, the Arabic reshaper with its libraqm lesson,
crests, the Reels safe band, the encoder's settings, the upload), so a moment
reel cannot drift from the match reels.
"""
import argparse
import json
import math
import os
import subprocess
import sys

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")

import fb_cards as C          # noqa: E402
import fb_reel as R           # noqa: E402
import store                  # noqa: E402

W, H, FPS = R.W, R.H, R.OUT_FPS
TOP, BOTTOM = int(H * 0.12), R.SAFE_BOTTOM     # the Reels safe band (fb_reel)
SOFT = (222, 238, 248)
DIM = (170, 192, 214)
GOLD = (246, 192, 60)
KIND = R.KIND                                  # one dedup namespace for every reel
PUSH_IN = 0.045                                # per scene: a still that never moves is punished
STAGGER, FADE, SLIDE = 0.35, 0.30, 26          # the lines: one after another, up and in
POP = 0.30                                     # the big number: lands from 125% to 100%

KINDS = ("hook", "date", "teams", "goal", "climax", "finale", "cta")


# ---------------------------------------------------------------- helpers
def ease(t, start, dur):
    """0 before start, 1 after start+dur, smooth in between."""
    if dur <= 0:
        return 1.0 if t >= start else 0.0
    x = min(1.0, max(0.0, (t - start) / dur))
    return x * x * (3 - 2 * x)


def layer():
    return Image.new("RGBA", (W, H), (0, 0, 0, 0))


def put(im, lay, alpha=1.0, dx=0, dy=0):
    """Composite a transparent layer at `alpha` (0..1), shifted by (dx, dy)."""
    if alpha <= 0:
        return
    if alpha < 1:
        lay = lay.copy()
        lay.putalpha(lay.getchannel("A").point(lambda v: int(v * alpha)))
    im.paste(lay, (int(dx), int(dy)), lay)


def line_at(d, y, s, weight, size, fill, max_w=W * 0.88):
    s = C.ar(s)
    C.draw_center(d, W / 2, y, s, C.fit(d, s, weight, size, max_w, 28), fill)


def lines_block(im, t, lines, ys, weight="Bold", size=56, fill=C.WHITE, t0=0.35):
    """Each line fades in and slides up, one STAGGER after the previous."""
    for i, (s, y) in enumerate(zip(lines, ys)):
        e = ease(t, t0 + i * STAGGER, FADE)
        if e <= 0:
            continue
        lay = layer()
        line_at(ImageDraw.Draw(lay), y, s, weight, size, fill)
        put(im, lay, e, dy=SLIDE * (1 - e))


def big_at(im, t, s, y, size, t0=0.0, fill=C.WHITE):
    """The big number: pops in (125% -> 100%) while fading."""
    e = ease(t, t0, POP)
    if e <= 0:
        return
    k = 1 + 0.25 * (1 - e)
    lay = layer()
    d = ImageDraw.Draw(lay)
    s = C.ar(s)
    f = C.fit(d, s, "ExtraBold", int(size * k), W * 0.92, 40)
    tw = C.text_w(d, s, f)
    d.text((W / 2 - tw / 2, y - (k - 1) * size * 0.4), s, font=f, fill=fill)
    put(im, lay, e)


def score_block(im, t, hs, as_, home, away, y, t0=0.0, size=140, shake=False):
    """The score as two digits with the club names under them — home on the
    RIGHT (Arabic reads right to left, fb_cards rule 4), so a bare «2-1»
    string can never put Egypt's goals on the wrong side."""
    e = ease(t, t0, POP)
    if e <= 0:
        return
    lay = layer()
    d = ImageDraw.Draw(lay)
    f = C.font("ExtraBold", size)
    for val, x in ((hs, W / 2 + 190), (as_, W / 2 - 190)):
        C.draw_center(d, x, y, str(val), f, C.WHITE)
    C.draw_center(d, W / 2, y + size * 0.05, "-", C.font("ExtraBold", int(size * 0.7)), GOLD)
    nf = C.font("Bold", 36)
    for name, x in ((home, W / 2 + 190), (away, W / 2 - 190)):
        C.draw_center(d, x, y + size * 1.12, C.ar(name), nf, SOFT)
    dx = dy = 0
    if shake and t0 <= t < t0 + 0.35:
        k = (t - t0) / 0.35
        dx = 10 * (1 - k) * math.sin(t * 90)
        dy = 7 * (1 - k) * math.cos(t * 70)
    put(im, lay, e, dx, dy)


_photo = {}


def photo_panel(im, t, path, cx, cy, w, h, credit, t0=0.0):
    """ONE licensed photo in a rounded white-framed panel, cover-cropped from
    the TOP so a head is never sliced (the image rules in memory), its credit
    in small Latin type right under it (Almarai has no Cyrillic)."""
    key = (path, w, h)
    if key not in _photo:
        src = Image.open(path).convert("RGB")
        k = max(w / src.width, h / src.height)
        src = src.resize((max(1, int(src.width * k)), max(1, int(src.height * k))), Image.LANCZOS)
        x0 = (src.width - w) // 2
        src = src.crop((x0, 0, x0 + w, h))
        panel = Image.new("RGBA", (w + 12, h + 12), (0, 0, 0, 0))
        pd = ImageDraw.Draw(panel)
        pd.rounded_rectangle((0, 0, w + 11, h + 11), 42, fill=C.WHITE)
        mask = Image.new("L", (w, h), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), 36, fill=255)
        panel.paste(src, (6, 6), mask)
        _photo[key] = panel
    e = ease(t, t0, 0.45)
    if e <= 0:
        return
    panel = _photo[key]
    lay = layer()
    lay.paste(panel, (int(cx - panel.width / 2), int(cy - panel.height / 2)), panel)
    d = ImageDraw.Draw(lay)
    C.draw_center(d, cx, cy + h / 2 + 16, credit, C.font("Regular", 22), DIM)
    put(im, lay, e, dy=SLIDE * (1 - e))


def crest(im, t, side, ctx, size, cx, cy, t0=0.0, alpha=1.0):
    e = ease(t, t0, 0.45)
    if e <= 0:
        return
    lay = layer()
    R.crest_at(lay, ctx[side]["url"], ctx[side]["name"], size, cx, cy)
    put(im, lay, e * alpha, dy=SLIDE * (1 - e))


def header(d):
    C.draw_center(d, W / 2, 215, C.ar("الجون"), C.font("ExtraBold", 44), C.WHITE)


# ---------------------------------------------------------------- the scenes
def scene(sc, t, ctx):
    """One frame of a scene at local time t (seconds)."""
    im = ctx["bg"].copy()
    header(ImageDraw.Draw(im))
    kind, lines = sc["kind"], sc.get("lines") or []
    home, away = ctx["home"]["name"], ctx["away"]["name"]
    if kind == "hook":
        big_at(im, t, sc["big"], 560, 240)
        lines_block(im, t, lines, (960, 1050), size=60, t0=0.4)
    elif kind == "date":
        crest(im, t, "home", ctx, 340, W / 2, 620)
        lines_block(im, t, lines, (900, 985), weight="ExtraBold", size=60, t0=0.3)
    elif kind == "teams":
        lines_block(im, t, lines[:1], (330,), weight="ExtraBold", size=68, t0=0.1)
        for side, x, t0 in (("home", W * 0.72, 0.35), ("away", W * 0.28, 0.55)):
            crest(im, t, side, ctx, 300, x, 700, t0=t0)
            e = ease(t, t0 + 0.2, FADE)
            if e > 0:
                lay = layer()
                d = ImageDraw.Draw(lay)
                nm = C.ar(ctx[side]["name"])
                C.draw_center(d, x, 890, nm, C.fit(d, nm, "ExtraBold", 54, W * 0.40), C.WHITE)
                put(im, lay, e)
        lines_block(im, t, lines[1:], (1110,), size=50, fill=SOFT, t0=0.9)
    elif kind in ("goal", "climax"):
        if sc.get("photo"):
            photo_panel(im, t, ctx["photo"], W / 2, 620, 560, 660, ctx["credit"])
        elif sc.get("crest"):
            crest(im, t, sc["crest"], ctx, 340, W / 2, 620)
        n = len(lines)
        ys = tuple(1000 + i * (70 if n <= 2 else 62) for i in range(n))
        lines_block(im, t, lines, ys, size=52 if n <= 2 else 48, t0=0.3)
        hs, as_ = sc["score"]
        t_score = 0.3 + n * STAGGER + 0.15
        score_block(im, t, hs, as_, home, away, 1150 if n <= 2 else 1195,
                    t0=t_score, shake=bool(sc.get("shake")))
        if sc.get("dim"):
            k = 0.35 * ease(t, 0.0, 0.6)
            im = Image.blend(im, Image.new("RGB", (W, H), (0, 0, 0)), k)
    elif kind == "finale":
        crest(im, t, "home", ctx, 900, W / 2, 860, alpha=0.18)
        lines_block(im, t, lines, (400, 490), weight="ExtraBold", size=64, t0=0.1)
        big_at(im, t, sc["big"], 640, 280, t0=0.1 + len(lines) * STAGGER)
    elif kind == "cta":
        R.mark_at(im, W / 2, 560, 280)
        lines_block(im, t, lines[:1], (770,), weight="ExtraBold", size=64, t0=0.05)
        lines_block(im, t, lines[1:], (870,), size=50, fill=SOFT, t0=0.35)
        e = ease(t, 0.5, FADE)
        if e > 0:
            lay = layer()
            C.draw_center(ImageDraw.Draw(lay), W / 2, 990, "elgoon.com", C.font("ExtraBold", 64), C.WHITE)
            put(im, lay, e)
    else:
        raise ValueError(f"unknown scene kind {kind!r}")
    # the slow push-in, restarted every scene
    z = 1 + PUSH_IN * min(1.0, t / max(0.1, sc["secs"]))
    if z > 1.0005:
        cw, ch = W / z, H / z
        im = im.crop((int((W - cw) / 2), int((H - ch) / 2),
                      int((W + cw) / 2), int((H + ch) / 2))).resize((W, H), Image.BILINEAR)
    return im


def context(script):
    photo = script.get("photo") or {}
    return {"bg": R.background(), "home": script["home"], "away": script["away"],
            "photo": os.path.join(HERE, photo["file"]) if photo.get("file") else None,
            "credit": photo.get("credit") or ""}


def validate(script):
    """What the social brief fixed: 6-8 scenes, 14-17 s, short lines, a
    known kind each, the photo on disk and credited."""
    scs = script.get("scenes") or []
    assert 6 <= len(scs) <= 8, f"{len(scs)} scenes (6-8)"
    total = sum(float(s["secs"]) for s in scs)
    assert 14 <= total <= 17.5, f"{total:.1f} s (14-17.5)"
    for s in scs:
        assert s["kind"] in KINDS, f"scene kind {s['kind']!r}"
        for ln in s.get("lines") or []:
            assert len(ln.split()) <= 6, f"line too long: {ln}"
        if s["kind"] in ("goal", "climax"):
            assert "score" in s and len(s["score"]) == 2, "goal scene without a score"
        if s.get("photo"):
            ph = script.get("photo") or {}
            assert ph.get("file") and os.path.exists(os.path.join(HERE, ph["file"])), "photo missing"
            assert ph.get("credit") and ph.get("source"), "a photo needs its credit and source"
    assert script.get("caption"), "no caption"
    return total


def frames(script, ctx):
    for sc in script["scenes"]:
        n = int(round(float(sc["secs"]) * FPS))
        for i in range(n):
            yield scene(sc, i / FPS, ctx)


def contact_sheet(ims, path, cols=4):
    pick = ims[:: max(1, len(ims) // 12)][:12]
    tw, th = 270, 480
    sheet = Image.new("RGB", (cols * tw, ((len(pick) + cols - 1) // cols) * th), (20, 20, 20))
    for i, im in enumerate(pick):
        sheet.paste(im.resize((tw, th), Image.LANCZOS), ((i % cols) * tw, (i // cols) * th))
    sheet.save(path)


def encode(script, ctx, path, secs):
    """Frames piped raw into ffmpeg: H.264 / yuv420p / 30 fps / faststart,
    the music loop as the AAC track (Reels refuses a silent-less file), a
    volume dip where the script marks the low point, fades in and out."""
    exe = R.ffmpeg()
    if not exe:
        print("  no ffmpeg: pip install imageio-ffmpeg (laptop) or apt ffmpeg (runner)")
        return False
    import tempfile
    tmp = tempfile.mkdtemp(prefix="moment-")
    try:
        audio = R.music_track(script["id"], tmp, secs)
        a_in = (["-stream_loop", "-1", "-i", audio] if audio
                else ["-f", "lavfi", "-i", f"anullsrc=r={R.SR}:cl=stereo"])
        af = []
        dip = script.get("music_dip")
        if dip:
            af.append(f"volume=enable='between(t,{dip[0]},{dip[1]})':volume=0.35")
        af += ["afade=t=in:d=0.3", f"afade=t=out:st={secs - 1.5:.2f}:d=1.5"]
        cmd = [exe, "-y", "-loglevel", "error",
               "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
               *a_in,
               "-map", "0:v", "-map", "1:a", "-t", f"{secs:.2f}",
               "-c:v", "libx264", "-preset", "medium", "-crf", "20",
               "-pix_fmt", "yuv420p", "-r", str(FPS), "-profile:v", "high",
               "-af", ",".join(af),
               "-c:a", "aac", "-b:a", "128k", "-ar", str(R.SR), "-ac", "2",
               "-movflags", "+faststart", path]
        p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        for im in frames(script, ctx):
            p.stdin.write(im.tobytes())
        p.stdin.close()
        if p.wait() != 0:
            raise RuntimeError("ffmpeg failed")
        return True
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


def caption(script):
    cap = script["caption"].rstrip("\n")
    ph = script.get("photo") or {}
    if ph.get("credit_ar"):
        cap += "\n" + ph["credit_ar"]
    return cap + "\n"


def publish(script, path):
    """The same three-phase upload and claim-then-post as the match reels:
    kind 'reel', ref 'moment:<id>' — one post per moment, ever."""
    token = os.environ.get("FB_PAGE_TOKEN", "").strip()
    if not token:
        print("FB_PAGE_TOKEN not set: rendered, not published")
        return 2
    ref = f"moment:{script['id']}"
    if not store.claim(KIND, ref, title=script.get("title")):
        print(f"moment {script['id']}: already published or held by another run")
        return 0
    try:
        vid = R.post_reel(token, path, caption(script))
        store.record_post(KIND, ref, vid, title=script.get("title"))
        print(f"moment {script['id']}: published as {vid}")
        return 0
    except Exception as e:                                   # noqa: BLE001
        store.release(KIND, ref)
        print(f"moment {script['id']} FAILED: {e}")
        return 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--script", required=True, help="moments/<id>.json")
    ap.add_argument("--out", help="the MP4 (default media/reels/moment-<id>.mp4)")
    ap.add_argument("--sheet", help="also write a 12-frame contact sheet PNG")
    ap.add_argument("--png", help="write ONE frame per scene (at its end) into this folder, no MP4")
    ap.add_argument("--publish", action="store_true", help="upload to the page (needs FB_PAGE_TOKEN)")
    args = ap.parse_args()
    script = json.load(open(args.script, encoding="utf-8"))
    secs = validate(script)
    ctx = context(script)
    if args.png:
        os.makedirs(args.png, exist_ok=True)
        for i, sc in enumerate(script["scenes"]):
            scene(sc, float(sc["secs"]) - 0.05, ctx).save(os.path.join(args.png, f"{i + 1}-{sc['kind']}.png"))
        print(f"{len(script['scenes'])} scene stills → {args.png}")
        return 0
    out = args.out or os.path.join(HERE, "media", "reels", f"moment-{script['id']}.mp4")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    ok = encode(script, ctx, out, secs)
    if args.sheet:
        contact_sheet([scene(sc, min(float(sc["secs"]) - 0.05, k) , ctx)
                       for sc in script["scenes"] for k in (0.6, 1.2)][:12], args.sheet)
    print(f"{out}: {secs:.1f}s, {'UPLOADABLE' if ok else 'NOT uploadable'}")
    print(caption(script))
    if args.publish:
        if not ok:
            print("not publishing a file ffmpeg did not write")
            return 1
        return publish(script, out)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
