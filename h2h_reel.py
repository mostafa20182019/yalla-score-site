#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The head-to-head REEL (2026-10-08, user: «اعمل reel باستخدام الصورة اللى انت
عملتها الخاصة باخر 10 مواجهات»): the H2H infographic (h2h_card.py) told as a
14-second vertical video - crests, the tally counting up, the ten meetings
landing one by one newest first, the last win of each side, the site.

Same data path as the card (365scores head-to-head, official scores only),
same brand canvas and encoder as the result reels (fb_reel.py): H.264 +
silent AAC through ffmpeg when one is available (the GitHub runner, or the
imageio-ffmpeg wheel locally), else a cv2 PREVIEW that is not uploadable.

    python h2h_reel.py --match 4804684 --out /tmp/h2h.mp4 [--sheet /tmp/sheet.png]
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from PIL import Image, ImageDraw                     # noqa: E402
import fb_cards as C                                 # noqa: E402
import fb_reel as R                                  # noqa: E402
import h2h_card as HC                                # noqa: E402

W, H, FPS = R.W, R.H, R.FPS
GOLD = (246, 192, 60)
SOFT = (222, 238, 248)
DIM = (170, 192, 214)
SCENES = [("intro", 2.5), ("tally", 3.0), ("meetings", 6.0), ("cta", 2.5)]
SAFE_BOTTOM = 340          # Facebook lays the caption + buttons over the bottom of a Reel


def footer(d):
    C.draw_center(d, W / 2, H - SAFE_BOTTOM - 60, C.ar("التحليل الكامل بالأرقام"), C.font("Bold", 34), SOFT)
    C.draw_center(d, W / 2, H - SAFE_BOTTOM - 10, "yallascore.site", C.font("ExtraBold", 40), C.WHITE)


def _count(d, cx, y, n, t, size, col):
    """A number counting up to n over the first 60% of its scene."""
    k = R.ease(min(1.0, t / 0.6))
    s = str(int(round(n * k)))
    f = C.font("ExtraBold", size)
    d.text((cx - d.textlength(s, font=f) / 2, y), s, font=f, fill=col)


def scene_intro(t, ctx):
    im = ctx["bg"].copy()
    d = ImageDraw.Draw(im)
    R.header(d, ctx["comp"], None)
    p = R.ease(t / 1.2)
    size, y = 320, H * 0.40
    R.crest_at(im, ctx["m"].get("home_badge"), ctx["h"], size, R.lerp(-size, W * 0.72, p), y)   # home RIGHT
    R.crest_at(im, ctx["m"].get("away_badge"), ctx["a"], size, R.lerp(W + size, W * 0.28, p), y)
    if t > 0.6:
        a = R.ease((t - 0.6) / 0.6)
        for cx, name in ((W * 0.72, ctx["h"]), (W * 0.28, ctx["a"])):
            f = C.fit(d, C.ar(name), "ExtraBold", 52, W * 0.42)
            C.draw_center(d, cx, y + size * 0.62, C.ar(name), f, C.WHITE if a > 0.5 else SOFT)
    if t > 1.0:
        k = R.ease((t - 1.0) / 0.8)
        C.draw_center(d, W / 2, H * 0.66 + (1 - k) * 40, C.ar(f"آخر {ctx['n']} مواجهات"),
                      C.font("ExtraBold", 92), C.WHITE)
        C.draw_center(d, W / 2, H * 0.66 + 130 + (1 - k) * 40, C.ar(ctx["when"] or "بينهما"),
                      C.font("Bold", 40), GOLD)
    footer(d)
    return im


def scene_tally(t, ctx):
    im = ctx["bg"].copy()
    d = ImageDraw.Draw(im)
    R.header(d, ctx["comp"], None)
    h, a, w, draws, gf = ctx["h"], ctx["a"], ctx["wins"], ctx["draws"], ctx["goals"]
    C.draw_center(d, W / 2, H * 0.19, C.ar(f"في آخر {ctx['n']} مواجهات"), C.font("Bold", 44), SOFT)
    y = H * 0.27
    for cx, n, label, col in ((W * 0.78, w[h], f"فوز {h}", GOLD), (W * 0.5, draws, "تعادل", C.WHITE),
                              (W * 0.22, w[a], f"فوز {a}", GOLD)):
        _count(d, cx, y, n, t, 150, col)
        f = C.fit(d, C.ar(label), "Bold", 36, W * 0.26)
        C.draw_center(d, cx, y + 190, C.ar(label), f, SOFT)
    d.line([(W * 0.36, y + 20), (W * 0.36, y + 170)], fill=(90, 130, 170), width=3)
    d.line([(W * 0.64, y + 20), (W * 0.64, y + 170)], fill=(90, 130, 170), width=3)
    if t > 1.2:
        k = R.ease((t - 1.2) / 0.8)
        yy = H * 0.56 + (1 - k) * 60
        C.draw_center(d, W / 2, yy, C.ar("الأهداف المسجّلة"), C.font("ExtraBold", 54), C.WHITE)
        sub = (f"في {ctx['played']} مباريات لُعبت داخل الملعب" if ctx["played"] < ctx["n"]
               else f"في {ctx['n']} مباريات بالنتائج الرسمية")
        C.draw_center(d, W / 2, yy + 66, C.ar(sub), C.font("Regular", 28), DIM)
        for cx, name in ((W * 0.72, h), (W * 0.28, a)):
            d.rounded_rectangle((cx - 170, yy + 120, cx + 170, yy + 290), 26, fill=(10, 40, 70))
            _count(d, cx, yy + 122, gf[name], t - 1.2, 96, C.WHITE)
            f = C.fit(d, C.ar(f"سجّل {name}"), "Bold", 32, 320)
            C.draw_center(d, cx, yy + 232, C.ar(f"سجّل {name}"), f, SOFT)
    footer(d)
    return im


def scene_meetings(t, ctx):
    im = ctx["bg"].copy()
    d = ImageDraw.Draw(im)
    R.header(d, ctx["comp"], None)
    games = ctx["games"]
    n = len(games)
    step = 4.8 / max(1, n)                      # all rows are in by 4.8s, then they hold
    RH = 118
    y0 = 230 + (10 - n) * RH // 2
    fn, fs, fd = C.font("ExtraBold", 40), C.font("ExtraBold", 44), C.font("Bold", 24)
    for i, g in enumerate(games):
        if t < i * step:
            break
        k = R.ease((t - i * step) / 0.35)
        y = y0 + i * RH
        x_off = int((1 - k) * 120)
        d.rounded_rectangle((60 + x_off, y, W - 60 + x_off, y + RH - 12), 20, fill=(10, 40, 70))
        nb = 40
        d.ellipse((W - 60 + x_off - nb - 14, y + 10, W - 60 + x_off - 14, y + 10 + nb), fill=GOLD)
        s = str(i + 1)
        d.text((W - 60 + x_off - 14 - nb / 2 - d.textlength(s, font=fd) / 2, y + 16), s, font=fd, fill=(20, 30, 50))
        from site_lib.names import ar_team
        gh, ga = ar_team(g["home"]), ar_team(g["away"])
        gn = ctx["notes"].get(g["date"]) or {}
        # the note (awarded / penalties) rides on the header line in gold: the
        # row has no room under the score, and the header is where the eye
        # reads the context anyway
        head = C.ar(f"{g['comp']} · {HC.ar_date(g['date'])}")
        f = fd
        while d.textlength(head, font=f) > W - 260 - (160 if gn.get("note") else 0) and f.size > 16:
            f = C.font("Bold", f.size - 1)
        xr = W - 60 + x_off - nb - 30
        d.text((xr - d.textlength(head, font=f), y + 14), head, font=f, fill=DIM)
        if gn.get("note"):
            nt = C.ar(gn["note"])
            d.text((xr - d.textlength(head, font=f) - 18 - d.textlength(nt, font=f), y + 14), nt, font=f, fill=GOLD)
        hw = g["hg"] > g["ag"] or gn.get("winner") == gh
        aw = g["ag"] > g["hg"] or gn.get("winner") == ga
        mid = W / 2 + x_off
        fnm = C.fit(d, C.ar(max(gh, ga, key=len)), "ExtraBold", 40, 300)
        d.text((mid + 90, y + 50), C.ar(gh), font=fnm, fill=C.WHITE if hw else SOFT)      # home RIGHT
        d.text((mid - 90 - d.textlength(C.ar(ga), font=fnm), y + 50), C.ar(ga), font=fnm, fill=C.WHITE if aw else SOFT)
        sc = f"{g['ag']} - {g['hg']}"
        d.rounded_rectangle((mid - 72, y + 48, mid + 72, y + 100), 14, fill=(0, 0, 0))
        d.text((mid - d.textlength(sc, font=fs) / 2, y + 48), sc, font=fs, fill=C.WHITE)
    footer(d)
    return im


def scene_cta(t, ctx):
    im = ctx["bg"].copy()
    d = ImageDraw.Draw(im)
    R.header(d, ctx["comp"], None)
    y = H * 0.20
    f = C.font("Bold", 40)
    facts = ([ctx["finals"]] if ctx.get("finals") else []) + [
        (f"آخر فوز لـ{name}: {HC.ar_date(ctx['last'][name])}" if ctx["last"].get(name)
         else f"{name} بلا فوز في هذه المواجهات") for name in (ctx["h"], ctx["a"])]
    for i, line in enumerate(facts[:3]):
        if t < 0.25 * i:
            continue
        k = R.ease(min(1.0, (t - 0.25 * i) / 0.5))
        for chunk in R.wrap(d, line, f, W - 200, lines=2):
            slide = int((1 - k) * 40)
            d.rounded_rectangle((70, y - 14 + slide, W - 70, y + 66 + slide), 20, fill=C.WHITE)
            C.draw_center(d, W / 2, y + slide, chunk, f, C.INK)
            y += 96
        y += 20
    k = R.ease(min(1.0, max(0.0, (t - 0.8) / 0.6)))
    if k > 0.02:
        C.draw_center(d, W / 2, H * 0.60, C.ar("التوقع والتحليل الكامل على"),
                      C.font("Bold", max(1, int(44 * k))), SOFT)
        C.draw_center(d, W / 2, H * 0.60 + 76, "yallascore.site",
                      C.font("ExtraBold", max(1, int(72 * k))), C.WHITE)
        if ctx["when"]:
            C.draw_center(d, W / 2, H * 0.60 + 190, C.ar(ctx["when"]), C.font("Bold", 36), GOLD)
    return im


SCENE_FN = {"intro": scene_intro, "tally": scene_tally, "meetings": scene_meetings, "cta": scene_cta}


def context(m, games):
    import matchup_card as MC
    from site_lib.names import ar_team, comp_label
    h, a = ar_team(m.get("home")), ar_team(m.get("away"))
    notes = HC.load_notes(h, a)
    w, draws, gf, last, played = HC.tally(games, h, a, notes)
    return {"m": m, "h": h, "a": a, "games": games, "n": len(games), "wins": w, "draws": draws,
            "goals": gf, "last": last, "played": played, "notes": notes.get("games") or {},
            "finals": notes.get("finals"), "comp": comp_label(m.get("competition")),
            "when": MC.when_ar(m.get("kickoff"), m.get("koff_time")), "bg": R.background()}


def frames(ctx):
    out = []
    for name, secs in SCENES:
        for i in range(int(secs * FPS)):
            out.append(SCENE_FN[name](i / FPS, ctx))
    return out


def contact_sheet(fs, path, cols=4, every=None):
    """A grid of frames to eyeball the reel without playing it."""
    every = every or max(1, len(fs) // 12)
    pick = fs[::every][:12]
    tw, th = 270, 480
    sheet = Image.new("RGB", (cols * tw, ((len(pick) + cols - 1) // cols) * th), (20, 20, 20))
    for i, im in enumerate(pick):
        sheet.paste(im.resize((tw, th), Image.LANCZOS), ((i % cols) * tw, (i // cols) * th))
    sheet.save(path)
    return path


def caption(ctx):
    h, a = ctx["h"], ctx["a"]
    lines = [f"آخر {ctx['n']} مواجهات بين {h} و{a} في 14 ثانية 🎬",
             f"{h} فاز {ctx['wins'][h]} · تعادل {ctx['draws']} · {a} فاز {ctx['wins'][a]}"]
    if ctx.get("finals"):
        lines.append(f"🏟️ {ctx['finals']}")
    lines += [
             f"التوقع والتحليل الكامل: https://yallascore.site/m/{ctx['m'].get('match_id')}",
             f"#يلا_سكور #{h.replace(' ', '_')} #{a.replace(' ', '_')}"]
    return "\n".join(lines)


def build(m, out, sheet=None, games=None):
    games = games if games is not None else HC.h2h_games(m)
    if len(games) < HC.MIN_GAMES:
        return None
    ctx = context(m, games)
    fs = frames(ctx)
    ok = R.encode(fs, out)
    if sheet:
        contact_sheet(fs, sheet)
    return {"uploadable": ok, "frames": len(fs), "seconds": len(fs) / FPS, "caption": caption(ctx)}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--match", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--sheet")
    args = ap.parse_args()
    import match_brief as MB
    d = MB.load_all()
    m = next((x for x in d["matches"] if str(x.get("match_id")) == str(args.match)), None)
    if not m:
        sys.exit(f"match {args.match} is not in matches.json")
    r = build(m, args.out, args.sheet)
    if not r:
        sys.exit("too few meetings on record")
    print(f"{args.out}: {r['seconds']:.1f}s, {r['frames']} frames, {'UPLOADABLE' if r['uploadable'] else 'preview only'}")
    print(r["caption"])
