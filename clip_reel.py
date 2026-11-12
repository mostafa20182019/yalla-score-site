#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Elgoon — the CLIP reel (2026-11-09): a historic match retold from REAL,
free-licensed footage (Wikimedia Commons, CC BY), cut into a vertical
1080x1920 reel of 28-40 seconds.

    python clip_reel.py --script clips/japan-germany-2022.json --out r.mp4 --sheet r.png --caption r.txt
    python clip_reel.py --script clips/japan-germany-2022.json --png previews/    # one frame per clip, no ffmpeg

Why a third reel generator next to fb_reel.py (tonight's score) and
moment_reel.py (typography + one photo): a moment people remember travels
further with the crowd's own roar under it. Footage is allowed ONLY when it
is free-licensed (the file's Commons page says so) and credited on the frame
for as long as it plays - CC BY demands attribution - and in the caption.
Broadcast footage never qualifies.

Design (option B of the brief): the 16:9 crowd footage sits inside a rounded
panel on the brand canvas with the text above and below it, instead of a
9:16 centre crop. A centre crop keeps a third of a shot filmed from the
stands and has to upscale it 1.8x (soft, and the Japan clip is 15 fps); the
panel keeps 70 % of the frame at native sharpness, and the panel's crop
window is chosen per clip to leave the uploader's watermark (top-left
corner) outside the picture. Everything is in the Reels safe band (fb_reel:
12 %..75 % of the height): the wordmark, the headline, the footage, the
score strip (home on the RIGHT, its goals right of the dash - the RTL rule),
the scorer line and the credit.

The JSON in clips/ carries the story (clips with in/out, the overlay
lines, the score after each clip, the outro, the caption); the video files
themselves stay out of git (clips/video/ is ignored) - the script resolves
the file name against --video-dir and prints the Commons URL when it is
missing. Everything visual comes from fb_cards.py / fb_reel.py /
moment_reel.py so the reel cannot drift from the cards.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")

import fb_cards as C          # noqa: E402
import fb_reel as R           # noqa: E402
import moment_reel as M       # noqa: E402

W, H, FPS = R.W, R.H, R.OUT_FPS
TOP, BOTTOM = M.TOP, M.BOTTOM                  # the Reels safe band
SOFT, DIM, GOLD = M.SOFT, M.DIM, M.GOLD
# the vertical layout, top to bottom, all inside TOP..BOTTOM (230..1440)
LOGO_H, LOGO_Y = 80, 278                       # wordmark 238..318
HEAD_Y = 340                                   # the headline (one line, ExtraBold)
PANEL = (40, 450, 1040, 1210)                  # the footage: 1000 x 760 (about 4:3)
PANEL_R = 36
STRIP_Y, STRIP_H = 1240, 96                    # the score strip (white pill)
INFO_Y = 1352                                  # the scorer / date line
CREDIT_Y = 1408                                # the licence credit, Latin, small
# 10-15 s (user rule 2026-11-10: every reel is 15 s or less); was 28-40 when the clip reels began (2026-11-09)
MIN_SECS, MAX_SECS = 10.0, 15.0
MAX_CLIP_SECS = 15.0
TEXT_FADE = 0.4
OUTRO_ZOOM = 0.05
FLAGS = {
    # national flags are plain geometry - drawn here, no file to license
    "de": [("rect", (0, 0, 1, 1 / 3), (0, 0, 0)), ("rect", (0, 1 / 3, 1, 2 / 3), (221, 0, 0)),
           ("rect", (0, 2 / 3, 1, 1), (255, 206, 0))],
    "jp": [("rect", (0, 0, 1, 1), (255, 255, 255)), ("disc", (0.5, 0.5, 0.3), (188, 0, 45))],
}


# ---------------------------------------------------------------- pieces
def flag(code, w=72, h=50):
    """A rounded flag chip for the score strip, or None for an unknown code."""
    spec = FLAGS.get((code or "").lower())
    if not spec:
        return None
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for kind, geo, col in spec:
        if kind == "rect":
            d.rectangle((geo[0] * w, geo[1] * h, geo[2] * w - 1, geo[3] * h - 1), fill=col)
        else:
            cx, cy, r = geo[0] * w, geo[1] * h, geo[2] * h
            d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=col)
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), 8, fill=255)
    im.putalpha(mask)
    # a hairline so the white of Japan's flag reads on the white strip
    ImageDraw.Draw(im).rounded_rectangle((0, 0, w - 1, h - 1), 8, outline=(200, 212, 224, 255), width=2)
    return im


def team_badge(lay, team, size, cx, cy):
    """The flag when the team has one, else the crest from the site's cache."""
    f = flag(team.get("flag"), size, int(size * 0.7))
    if f is not None:
        lay.paste(f, (int(cx - f.width / 2), int(cy - f.height / 2)), f)
    else:
        R.crest_at(lay, team.get("url"), team.get("name"), size, cx, cy)


def base_image(ctx):
    """The canvas every frame starts from: the brand gradient + the wordmark."""
    im = ctx["bg"].copy()
    R.logo_at(im, W / 2, LOGO_Y, LOGO_H)
    return im


def mask_image(ctx):
    """Pasted OVER the footage: the canvas with a rounded hole where the
    footage is, plus a thin white frame - so the clip gets rounded corners."""
    im = base_image(ctx).convert("RGBA")
    hole = Image.new("L", (W, H), 255)
    ImageDraw.Draw(hole).rounded_rectangle(PANEL, PANEL_R, fill=0)
    im.putalpha(hole)
    d = ImageDraw.Draw(im)
    x0, y0, x1, y1 = PANEL
    d.rounded_rectangle((x0 - 6, y0 - 6, x1 + 5, y1 + 5), PANEL_R + 6, outline=(255, 255, 255, 255), width=6)
    return im


def score_strip(d, lay, ctx, hs, as_):
    """The white pill: [home flag] home  hs - as  away [away flag], home on the
    RIGHT and its goals right of the dash (fb_cards rule 4)."""
    cy = STRIP_Y + STRIP_H / 2
    fs = C.font("ExtraBold", 64)
    nf = C.font("Bold", 40)
    home, away = ctx["home"], ctx["away"]
    hn, an = C.ar(home["name"]), C.ar(away["name"])
    gap, badge = 26, 64
    hw, aw = C.text_w(d, hn, nf), C.text_w(d, an, nf)
    sw = C.text_w(d, f"{hs}", fs) + C.text_w(d, f"{as_}", fs) + 110
    total = badge + gap + hw + gap + sw + gap + aw + gap + badge
    x0 = W / 2 - total / 2 - 36
    d.rounded_rectangle((x0, STRIP_Y, x0 + total + 72, STRIP_Y + STRIP_H), STRIP_H // 2, fill=C.WHITE)
    x = x0 + 36 + total                    # walk from the right edge: home first
    team_badge(lay, home, badge, x - badge / 2, cy)
    x -= badge + gap
    d.text((x - hw, cy - 26), hn, font=nf, fill=C.INK)
    x -= hw + gap
    C.draw_center(d, x - 28, cy - 42, str(hs), fs, C.INK)          # home goals RIGHT of the dash
    C.draw_center(d, x - sw / 2, cy - 42, "-", fs, (150, 170, 185))
    C.draw_center(d, x - sw + 28, cy - 42, str(as_), fs, C.INK)
    x -= sw + gap
    d.text((x - aw, cy - 26), an, font=nf, fill=C.INK)
    x -= aw + gap
    team_badge(lay, away, badge, x - badge / 2, cy)


def text_layer(clip, ctx):
    """Everything drawn over the footage for one clip: the headline above
    the panel, the score strip, the scorer/date line and the credit below."""
    lay = M.layer()
    d = ImageDraw.Draw(lay)
    lines = clip.get("overlay_lines") or []
    if lines:
        s = C.ar(lines[0])
        C.draw_center(d, W / 2, HEAD_Y, s, C.fit(d, s, "ExtraBold", 60, W * 0.86, 36), C.WHITE)
    if clip.get("score"):
        score_strip(d, lay, ctx, *clip["score"])
    if len(lines) > 1:
        s = C.ar(lines[1])
        C.draw_center(d, W / 2, INFO_Y, s, C.fit(d, s, "Bold", 40, W * 0.86, 26), SOFT)
    credit = ctx["credit"]
    C.draw_center(d, W / 2, CREDIT_Y, credit, C.fit(d, credit, "Regular", 24, W * 0.9, 16), DIM)
    return lay


def panel_size():
    return PANEL[2] - PANEL[0], PANEL[3] - PANEL[1]


def crop_box(clip, src_w=None, src_h=None):
    """The source window (x, y, w, h) the panel shows: the panel's aspect,
    `h` source pixels tall, placed at (x, y). Clamped inside the frame.
    The source size is the clip's "src": [w, h] (a vertical phone clip, e.g.
    the 2160x3840 Mbappé file, 2026-11-12), else 1920x1080."""
    pw, ph = panel_size()
    sw, sh = clip.get("src") or (1920, 1080)
    src_w, src_h = src_w or int(sw), src_h or int(sh)
    c = clip.get("crop") or {}
    h = int(c.get("h") or src_h)
    w = int(round(h * pw / ph))
    if w > src_w:
        w, h = src_w, int(round(src_w * ph / pw))
    x = max(0, min(int(c.get("x") or 0), src_w - w))
    y = max(0, min(int(c.get("y") or 0), src_h - h))
    return x, y, w, h


def overlay_frame(clip, ctx, footage=None):
    """One finished frame of a clip: canvas, the footage (a PIL image already
    cropped, or a flat stand-in), the rounded mask, the text. What --png
    writes and what the test measures."""
    im = base_image(ctx)
    pw, ph = panel_size()
    if footage is None:
        footage = Image.new("RGB", (pw, ph), (60, 90, 70))
    im.paste(footage.resize((pw, ph), Image.LANCZOS), (PANEL[0], PANEL[1]))
    m = ctx["mask"]
    im.paste(m, (0, 0), m)
    t = text_layer(clip, ctx)
    im.paste(t, (0, 0), t)
    return im


def outro_image(script, ctx, scale=1):
    """The closing card: the big wordmark, the title line, the final score
    (moment_reel.score_block - home on the right), elgoon.com. `scale` 2
    renders it double size for the encoder's push-in."""
    im = ctx["bg"].copy()
    o = script["outro"]
    R.logo_at(im, W / 2, 520, 260)
    d = ImageDraw.Draw(im)
    lines = o.get("lines") or []
    if lines:
        s = C.ar(lines[0])
        C.draw_center(d, W / 2, 720, s, C.fit(d, s, "ExtraBold", 64, W * 0.88, 36), C.WHITE)
    if o.get("score"):
        M.score_block(im, 9.0, o["score"][0], o["score"][1], ctx["home"]["name"], ctx["away"]["name"], 840)
    if len(lines) > 1:
        s = C.ar(lines[1])
        C.draw_center(d, W / 2, 1150, s, C.fit(d, s, "Bold", 40, W * 0.86, 26), SOFT)
    C.draw_center(d, W / 2, 1250, "elgoon.com", C.font("ExtraBold", 64), C.WHITE)
    credit = ctx["credit"]
    C.draw_center(d, W / 2, CREDIT_Y, credit, C.fit(d, credit, "Regular", 24, W * 0.9, 16), DIM)
    if scale != 1:
        im = im.resize((W * scale, H * scale), Image.LANCZOS)
    return im


# ---------------------------------------------------------------- script
def context(script):
    ctx = {"bg": R.background(), "home": script["home"], "away": script["away"],
           "credit": script["credit"]}
    ctx["mask"] = mask_image(ctx)
    return ctx


def clip_secs(clip):
    return float(clip["out"]) - float(clip["in"])


def total_secs(script):
    return sum(clip_secs(c) for c in script["clips"]) + float(script["outro"]["secs"])


def validate(script):
    """What the brief fixed, checked without ffmpeg: every clip is credited
    with a free licence and its Commons page, in < out and no clip longer
    than MAX_CLIP_SECS, the whole reel 28-40 s, the headline six words or
    fewer, a hook line, the credit on the frame and in the caption."""
    clips = script.get("clips") or []
    assert clips, "no clips"
    assert script.get("credit") and "CC BY" in script["credit"], "the on-frame credit must name the CC BY licence"
    assert script.get("credit_ar"), "the caption needs the Arabic credit line"
    assert script.get("outro") and float(script["outro"]["secs"]) > 0, "no outro"
    for i, c in enumerate(clips, 1):
        assert c.get("file"), f"clip {i}: no file"
        assert c.get("source_url", "").startswith("https://commons.wikimedia.org/"), f"clip {i}: source must be a Commons page"
        assert "CC" in (c.get("licence") or ""), f"clip {i}: licence must be a Creative Commons licence"
        assert c.get("credit"), f"clip {i}: no credit"
        assert 0 <= float(c["in"]) < float(c["out"]), f"clip {i}: in/out"
        assert clip_secs(c) <= MAX_CLIP_SECS, f"clip {i}: {clip_secs(c):.1f} s is longer than {MAX_CLIP_SECS:.0f}"
        lines = c.get("overlay_lines") or []
        assert lines, f"clip {i}: no overlay line"
        assert len(lines[0].split()) <= 6, f"clip {i}: headline longer than six words: {lines[0]}"
        if c.get("score") is not None:
            assert len(c["score"]) == 2, f"clip {i}: score needs two numbers"
    total = total_secs(script)
    assert MIN_SECS <= total <= MAX_SECS, f"{total:.1f} s (the brief wants {MIN_SECS:.0f}-{MAX_SECS:.0f})"
    assert script.get("caption") and "#الجون" in script["caption"], "the caption must carry #الجون"
    return total


def resolve(clip, video_dir):
    """The clip's file on disk, or None (the caller prints the source URL)."""
    f = clip["file"]
    path = f if os.path.isabs(f) else os.path.join(video_dir, f)
    return path if os.path.exists(path) else None


def caption(script):
    return script["caption"].rstrip("\n") + "\n" + script["credit_ar"] + "\n"


# ---------------------------------------------------------------- ffmpeg
def grab(exe, path, at, box):
    """One cropped frame of a source clip as a PIL image (previews / sheet)."""
    x, y, w, h = box
    out = subprocess.run([exe, "-loglevel", "error", "-ss", f"{at:.2f}", "-i", path,
                          "-vf", f"crop={w}:{h}:{x}:{y}", "-frames:v", "1", "-f", "image2pipe",
                          "-vcodec", "png", "-"], capture_output=True, check=True).stdout
    import io
    return Image.open(io.BytesIO(out)).convert("RGB")


def encode(script, ctx, out, video_dir):
    """The whole reel in ONE ffmpeg graph: each clip is seeked, cropped to
    its window, scaled into the panel over the canvas, masked to rounded
    corners and topped with its text layer (fading in); the clips' own crowd
    audio is kept (faded at the cuts) and the page's music loop sits under it
    at `music.under`, rising for the outro; the outro is a still with the
    match reels' push-in. H.264 / yuv420p / 30 fps / faststart, AAC - the
    same container the Reels API has accepted from fb_reel.py."""
    exe = R.ffmpeg()
    if not exe:
        print("  no ffmpeg: pip install imageio-ffmpeg (laptop) or apt ffmpeg (runner)")
        return False
    tmp = tempfile.mkdtemp(prefix="clipreel-")
    try:
        base, mask = os.path.join(tmp, "base.png"), os.path.join(tmp, "mask.png")
        base_image(ctx).save(base)
        ctx["mask"].save(mask)
        outro = os.path.join(tmp, "outro.png")
        outro_image(script, ctx, scale=2).save(outro)
        pw, ph = panel_size()
        px, py = PANEL[0], PANEL[1]
        inputs = ["-loop", "1", "-framerate", str(FPS), "-i", base,
                  "-loop", "1", "-framerate", str(FPS), "-i", mask]
        chain, segs = [], []
        n_in = 2
        for i, clip in enumerate(script["clips"]):
            path = resolve(clip, video_dir)
            if not path:
                print(f"  missing {clip['file']} - download it from {clip['source_url']} into {video_dir}")
                return False
            secs = clip_secs(clip)
            tl = os.path.join(tmp, f"text{i}.png")
            text_layer(clip, ctx).save(tl)
            inputs += ["-ss", f"{float(clip['in']):.3f}", "-t", f"{secs:.3f}", "-i", path,
                       "-loop", "1", "-framerate", str(FPS), "-i", tl]
            vi, ti = n_in, n_in + 1
            n_in += 2
            x, y, w, h = crop_box(clip)
            chain.append(f"[{vi}:v]fps={FPS},crop={w}:{h}:{x}:{y},scale={pw}:{ph}:flags=lanczos,"
                         f"setpts=PTS-STARTPTS,trim=duration={secs:.3f}[c{i}]")
            chain.append(f"[0:v][c{i}]overlay={px}:{py}:shortest=1[b{i}]")
            chain.append(f"[b{i}][1:v]overlay=0:0:shortest=1[m{i}]")
            # the hook is on the very first frame (no fade-in for clip 1): the
            # first second decides whether a reel is watched
            fade_in = f"fade=t=in:st=0:d={TEXT_FADE}:alpha=1," if i else ""
            chain.append(f"[{ti}:v]format=rgba,{fade_in}"
                         f"fade=t=out:st={max(0.0, secs - 0.25):.2f}:d=0.25:alpha=1[t{i}]")
            chain.append(f"[m{i}][t{i}]overlay=0:0:shortest=1,format=yuv420p[v{i}]")
            chain.append(f"[{vi}:a]atrim=0:{secs:.3f},asetpts=PTS-STARTPTS,"
                         f"aformat=sample_fmts=fltp:sample_rates={R.SR}:channel_layouts=stereo,"
                         f"afade=t=in:d=0.25,afade=t=out:st={max(0.0, secs - 0.4):.2f}:d=0.4,"
                         f"apad=whole_dur={secs:.3f}[a{i}]")
            segs.append(f"[v{i}][a{i}]")
        o_secs = float(script["outro"]["secs"])
        o_frames = int(round(o_secs * FPS))
        inputs += ["-loop", "1", "-framerate", str(FPS), "-i", outro]
        oi = n_in
        n_in += 1
        chain.append(f"[{oi}:v]zoompan=z='1+{OUTRO_ZOOM}*on/{o_frames}':x='iw/2-(iw/zoom/2)':"
                     f"y='ih/2-(ih/zoom/2)':d={o_frames}:s={W}x{H}:fps={FPS},"
                     f"trim=duration={o_secs:.3f},setpts=PTS-STARTPTS,"
                     f"fade=t=in:d=0.4,format=yuv420p[vo]")
        chain.append(f"anullsrc=r={R.SR}:cl=stereo,atrim=0:{o_secs:.3f}[ao]")
        segs.append("[vo][ao]")
        total = total_secs(script)
        chain.append("".join(segs) + f"concat=n={len(segs)}:v=1:a=1[vc][ac]")
        music = script.get("music") or {}
        mpath = os.path.join(HERE, music.get("file") or "music/yalla-loop.m4a")
        a_out = "[ac]"
        if os.path.exists(mpath):
            inputs += ["-stream_loop", "-1", "-i", mpath]
            under, up = float(music.get("under", 0.14)), float(music.get("outro", 0.6))
            t_out = total - o_secs
            chain.append(f"[{n_in}:a]aformat=sample_fmts=fltp:sample_rates={R.SR}:channel_layouts=stereo,"
                         f"volume='if(gte(t,{t_out:.3f}),{up},{under})':eval=frame,"
                         f"atrim=0:{total:.3f}[mu]")
            chain.append("[ac][mu]amix=inputs=2:duration=first:normalize=0[am]")
            a_out = "[am]"
            n_in += 1
        chain.append(f"{a_out}alimiter=limit=0.95,afade=t=out:st={total - 1.5:.2f}:d=1.5[a]")
        cmd = [exe, "-y", "-loglevel", "error", *inputs,
               "-filter_complex", ";".join(chain),
               "-map", "[vc]", "-map", "[a]", "-t", f"{total:.3f}",
               "-c:v", "libx264", "-preset", "medium", "-crf", "20",
               "-pix_fmt", "yuv420p", "-r", str(FPS), "-profile:v", "high",
               "-c:a", "aac", "-b:a", "128k", "-ar", str(R.SR), "-ac", "2",
               "-movflags", "+faststart", out]
        subprocess.run(cmd, check=True)
        return True
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def sheet_from_mp4(exe, mp4, path, n=12, cols=4):
    """n frames of the FINISHED file, evenly spaced, tiled - the proof the
    user looks at (watermark gone, text legible, nothing under the safe band)."""
    out = subprocess.run([exe, "-loglevel", "error", "-i", mp4, "-vf",
                          f"select='not(mod(n\\,{max(1, int(round(_duration(exe, mp4) * FPS / n)))}))',"
                          f"scale=270:480,tile={cols}x{(n + cols - 1) // cols}:padding=4:margin=4",
                          "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "-"],
                         capture_output=True, check=True).stdout
    import io
    Image.open(io.BytesIO(out)).convert("RGB").save(path)


def _duration(exe, path):
    """Seconds, from ffmpeg's own banner (the imageio wheel has no ffprobe)."""
    import re
    p = subprocess.run([exe, "-i", path], capture_output=True, text=True, encoding="utf-8", errors="replace")
    m = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", p.stderr)
    return int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3]) if m else 0.0


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--script", required=True, help="clips/<id>.json")
    ap.add_argument("--video-dir", default=os.path.join(HERE, "clips", "video"),
                    help="where the clips' files are (git-ignored; default clips/video)")
    ap.add_argument("--out", help="the MP4 (default media/reels/clip-<id>.mp4)")
    ap.add_argument("--sheet", help="also write a 12-frame contact sheet of the finished MP4")
    ap.add_argument("--caption", help="also write the caption text file")
    ap.add_argument("--png", help="write one preview frame per clip (+ the outro) into this folder, no MP4")
    args = ap.parse_args()
    script = json.load(open(args.script, encoding="utf-8"))
    total = validate(script)
    ctx = context(script)
    if args.png:
        os.makedirs(args.png, exist_ok=True)
        exe = R.ffmpeg()
        for i, clip in enumerate(script["clips"], 1):
            path = resolve(clip, args.video_dir)
            footage = None
            if exe and path:
                footage = grab(exe, path, (float(clip["in"]) + float(clip["out"])) / 2, crop_box(clip))
            elif not path:
                print(f"  missing {clip['file']} - {clip['source_url']}")
            overlay_frame(clip, ctx, footage).save(os.path.join(args.png, f"{i}-clip.png"))
        outro_image(script, ctx).save(os.path.join(args.png, "outro.png"))
        print(f"{len(script['clips'])} clip frames + outro → {args.png}")
        return 0
    out = args.out or os.path.join(HERE, "media", "reels", f"clip-{script['id']}.mp4")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    ok = encode(script, ctx, out, args.video_dir)
    if ok and args.sheet:
        sheet_from_mp4(R.ffmpeg(), out, args.sheet)
    if args.caption:
        open(args.caption, "w", encoding="utf-8").write(caption(script))
    print(f"{out}: {total:.1f}s, {'UPLOADABLE' if ok else 'NOT uploadable'}")
    print(caption(script))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
