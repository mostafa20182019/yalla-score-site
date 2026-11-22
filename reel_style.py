# -*- coding: utf-8 -*-
r"""Elgoon — the match RESULT reel in the new style (user, 2026-11-22).

The page's reels were getting no likes. Watched as a viewer scrolls: frame 0
was a logo and fading flags (nothing to stop the thumb), the body was a still
info slide with half the screen empty, and every reel carried the same
synthesised loop. The sample built that night (Chelsea 1-4 Leeds, then
Liverpool 4-0 Man United) was approved with «انا عايزك تعتمده بدل القديم».
This module is that sample, made automatic for fb_reel.py --auto:

    1  HOOK      the whole sentence readable on FRAME 0, huge, on the two
                 clubs' own colours (never a fade-in: the thumbnail is frame 0)
    2  SCORE     crests slide in, the score ticks goal by goal ON THE BEAT
                 with a flash, each scorer arrives with his goal
    3  NUMBERS   possession / big chances / shots on target, bars grow, and a
                 one-line verdict when the numbers say something plain
    4  TABLE     only when a side of the match sits top or in the direct
                 relegation places of a big league (rows, the zone in red)
    5  QUESTION  two answers to tap in the comments

Every word comes from the data and a fixed rule below (plan()); nothing is
written that the numbers do not say. The music is ours, made per reel
(128 BPM; its own key per match), and every cut and every goal lands on a
beat with an impact - the edit and the sound move together.

    python reel_style.py --match 560645 --out reel.mp4     # a local look
"""
import math
import os
import subprocess
import sys
import tempfile
import zlib

from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

W, H, FPS = 1080, 1920, 30
BPM = 128
BEAT = 60.0 / BPM
MAX_BEATS = 32                       # 15.0 s: the reel cap (user rule, 2026-11-10)
SR = 44100

INK = (14, 22, 48)
WHITE = (255, 255, 255)
ACC = (244, 243, 48)                 # the highlight yellow on the dark scenes
DARK_BG = INK

# big leagues whose table scene can say «منطقة الهبوط» (direct relegation places)
DROP = {"Premier League": 3, "Primera Division": 3, "Serie A": 3, "Bundesliga": 2, "Ligue 1": 2}
WORD = {3: "بثلاثية", 4: "برباعية", 5: "بخماسية", 6: "بسداسية", 7: "بسباعية", 8: "بثمانية"}
LATE_MIN = 85                        # a one-goal win decided from here on is «خطف»


# ================================================================ the words
def short(name):
    """«محمد صلاح» -> «صلاح»: the surname reads at a glance; one word stays."""
    w = (name or "").split()
    return " ".join(w[1:]) if len(w) >= 2 else (name or "")


def li(name):
    """«ل» + name, «للأهلي» for a name with the article."""
    return ("لل" + name[2:]) if name.startswith("ال") else ("ل" + name)


def _minute(m):
    try:
        return int(str(m or "").split("+")[0].strip("'"))
    except ValueError:
        return None


def hook(home, away, hs, as_, focus, goals):
    """Three lines, the whole story, true to the score. focus = 'h' / 'a':
    the side the page follows (the winner when both or neither)."""
    if hs == as_:
        return ["تعادل سلبي" if hs == 0 else "تعادل", f"{home} و{away}", f"{as_} - {hs}"]
    wside = "h" if hs > as_ else "a"
    W_, L_ = (home, away) if wside == "h" else (away, home)
    wg, lg = max(hs, as_), min(hs, as_)
    margin = wg - lg
    if focus == wside:
        if margin >= 3:
            return [W_, f"اكتسح {L_}", f"{WORD.get(wg, f'ب{wg} أهداف')}{' نظيفة' if lg == 0 else ''}!"]
        last = goals[-1] if goals else None
        lm = _minute(last[0]) if last else None
        if margin == 1 and last and last[1] == wside and lm is not None and lm >= LATE_MIN:
            return [W_, "خطف الفوز", f"في الدقيقة {last[0]}!"]
        return [W_, f"كسب {L_}", f"{wg} - {lg}"]
    # the side we follow lost
    if margin >= 3:
        return [L_, f"اتضرب {WORD.get(wg, f'ب{wg} أهداف')}", "في بيته!" if wside == "a" else f"قدام {W_}!"]
    return [L_, f"خسر قدام {W_}", f"{wg} - {lg}"]


def punch(home, away, hs, as_, st):
    """The verdict line under the numbers, only when they say it plainly."""
    if hs == as_ or not st:
        return None
    wk, lk = ("h", "a") if hs > as_ else ("a", "h")
    W_, L_ = (home, away) if wk == "h" else (away, home)
    w, l = st.get(wk) or {}, st.get(lk) or {}
    if (l.get("poss") or 0) >= 55:
        return [f"الكورة مع {L_}..", f"والأهداف {li(W_)}"]
    bw, bl = w.get("big"), l.get("big")
    if bw is not None and bl is not None and bw >= 4 and bl <= 1:
        return [f"{bw} فرص محققة {li(W_)}..", f"و{L_} ولا فرصة!" if bl == 0 else f"و{L_} فرصة واحدة بس"]
    sw, sl = w.get("sot"), l.get("sot")
    if sw is not None and sl is not None and sw >= 6 and sw >= 2 * max(sl, 1):
        return [f"{sw} تسديدات على المرمى {li(W_)}..", f"و{L_} {sl} بس"]
    return None


def question(home, away, hs, as_, focus, goals):
    """(two lines, two answers)."""
    if hs == as_:
        return ["التعادل ده", "عادل؟"], ["أيوه", "لأ"]
    wside = "h" if hs > as_ else "a"
    W_, L_ = (home, away) if wside == "h" else (away, home)
    if focus != wside:
        if abs(hs - as_) >= 3:
            return ["مين المسؤول", f"عن خسارة {L_}؟"], ["المدرب", "اللاعيبة"]
        return [L_, "هيعوّض الماتش الجاي؟"], ["أيوه", "لأ"]
    tally = {}
    for g in goals:
        if g[1] == wside and g[2] and g[3] != "عكسي":
            tally[g[2]] = tally.get(g[2], 0) + 1
    top = sorted(tally, key=lambda n: -tally[n])
    if len(top) >= 2:
        return ["مين نجم", "الماتش؟"], top[:2]
    return [W_, "هيكمل كده؟"], ["أيوه", "لأ"]


def table_block(m, standings, ar):
    """{"title", "rows": [[pos, name, pts, ours]], "drop_from"} or None: a
    side of the match at the top, or in the direct drop places, of a big
    league's table."""
    comp = m.get("competition") or ""
    if comp not in DROP:
        return None
    tab = next((s.get("table") for s in standings or [] if s.get("competition") == comp), None)
    if not tab or len(tab) < 10:
        return None
    n, drop = len(tab), DROP[comp]
    pos = {r.get("team"): r.get("pos") for r in tab}
    for team in (m.get("home"), m.get("away")):
        p = pos.get(team)
        if not p:
            continue
        if p == 1:
            rows, title, dfrom = tab[:7], f"{ar(team)} في الصدارة", None
        elif p > n - drop:
            rows, title, dfrom = tab[-7:], f"{ar(team)} في منطقة الهبوط", n - drop + 1
        else:
            continue
        return {"title": title, "drop_from": dfrom,
                "rows": [[r["pos"], ar(r["team"]), r["pts"], r["team"] == team] for r in rows]}
    return None


def stats_rows(st, with_table):
    if not st:
        return []
    h, a = st.get("h") or {}, st.get("a") or {}
    rows = []
    for key, label, suf in (("poss", "الاستحواذ", "%"), ("big", "فرص محققة", ""), ("sot", "تسديدات على المرمى", "")):
        if h.get(key) is not None and a.get(key) is not None:
            rows.append([label, int(h[key]), int(a[key]), suf])
    if with_table and len(rows) > 2:
        rows = rows[1:]                      # two rows when the table follows: the reel stays under 15 s
    return rows


def plan(m, goals, st, standings, focus, ar, colours, badges):
    """Everything the renderer draws, as one dict (pure: tests read it).
    goals = [(minute, side, scorer, tag)], st = {"h": {...}, "a": {...}} or {}."""
    home, away = ar(m.get("home")), ar(m.get("away"))
    hs, as_ = int(m["home_score"]), int(m["away_score"])
    goals = [(mi, s, short(p), t) for mi, s, p, t in goals]
    tb = table_block(m, standings, ar)
    if focus not in ("h", "a"):                 # both sides ours, or neither: the winner's story
        focus = "h" if hs >= as_ else "a"
    q, opts = question(home, away, hs, as_, focus, goals)
    return {"home": home, "away": away, "hs": hs, "as": as_, "goals": goals,
            "hook": hook(home, away, hs, as_, focus, goals),
            "stats": stats_rows(st, bool(tb)), "punch": punch(home, away, hs, as_, st),
            "table": tb, "question": q, "options": list(opts),
            "home_color": list(colours[0]), "away_color": list(colours[1]),
            "home_badge": badges[0], "away_badge": badges[1],
            "seed": zlib.crc32(str(m.get("match_id")).encode()) % 1000,
            "key": zlib.crc32(str(m.get("match_id")).encode()) % 6 - 2}


def timeline(cfg):
    """Scene starts in beats. Goals tick one a beat (half a beat past six)."""
    n = len(cfg["goals"])
    step = 1.0 if n <= 6 else 0.5
    s_stats = max(11, math.ceil(6 + n * step) + 1)
    st = cfg["stats"]
    tb = cfg["table"]
    if st:
        srow = 1 if tb else 2
        s_punch = s_stats + 1 + srow * len(st)
        s_after = s_punch + (2 if cfg["punch"] else 0)
    else:
        srow, s_punch, s_after = 0, s_stats, s_stats
    s_table = s_after if tb else None
    s_q = (s_table + 7) if tb else s_after
    total = s_q + 6
    return {"step": step, "stats": s_stats if st else None, "srow": srow, "punch": s_punch,
            "table": s_table, "q": s_q, "total": total}


# ================================================================ drawing
def _fc():
    import fb_cards as FC                    # noqa: PLC0415
    return FC


def ink(c):
    return INK if 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2] > 165 else WHITE


def bright(c):
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2] > 60


def ease(x):                                 # ease-out-back: a small overshoot, then rest
    x = max(0.0, min(1.0, x))
    c1 = 1.70158
    return 1 + (c1 + 1) * (x - 1) ** 3 + c1 * (x - 1) ** 2


def lin(x):
    return max(0.0, min(1.0, x))


_TXT = {}


def text_img(s, weight, size, fill, stroke=0):
    k = (s, weight, size, tuple(fill), stroke)
    if k in _TXT:
        return _TXT[k]
    FC = _fc()
    f = FC.font(weight, size)
    t = FC.ar(s)
    d = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    l, tp, r, b = d.textbbox((0, 0), t, font=f, stroke_width=stroke)
    im = Image.new("RGBA", (r - l + 8, b - tp + 8), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((4 - l, 4 - tp), t, font=f, fill=tuple(fill), stroke_width=stroke, stroke_fill=INK)
    _TXT[k] = im
    return im


def fit_text(s, weight, size, fill, max_w, stroke=0):
    im = text_img(s, weight, size, fill, stroke)
    while im.width > max_w and size > 30:
        size -= 4
        im = text_img(s, weight, size, fill, stroke)
    return im


def paste_c(base, im, cx, cy, scale=1.0, alpha=1.0):
    if scale <= 0.01 or alpha <= 0.01:
        return
    if abs(scale - 1) > 0.01:
        im = im.resize((max(1, int(im.width * scale)), max(1, int(im.height * scale))), Image.LANCZOS)
    if alpha < 0.99:
        im = im.copy()
        im.putalpha(im.getchannel("A").point(lambda v: int(v * alpha)))
    base.alpha_composite(im, (int(cx - im.width / 2), int(cy - im.height / 2)))


def scorer_row(name, minute, fill, max_w, size=58):
    """«آرونسون 90+1'»: the minute is drawn on its OWN, left of the name. Run
    through the Arabic bidi with the name, «90+1» came out «1+90'» (and a
    left-to-right mark put the apostrophe on the wrong side of every minute)."""
    while True:
        nm = text_img(name, "ExtraBold", size, fill)
        if not minute:
            row = nm
        else:
            mn = text_img(f"{minute}'", "ExtraBold", size, fill)
            row = Image.new("RGBA", (mn.width + 14 + nm.width, max(mn.height, nm.height)), (0, 0, 0, 0))
            row.alpha_composite(mn, (0, (row.height - mn.height) // 2))
            row.alpha_composite(nm, (mn.width + 14, (row.height - nm.height) // 2))
        if row.width <= max_w or size <= 30:
            return row
        size -= 4


def pill(w, h, fill, outline=None):
    im = Image.new("RGBA", (w + 12, h + 12), (0, 0, 0, 0))
    ImageDraw.Draw(im).rounded_rectangle([6, 6, w + 6, h + 6], h // 2, fill=fill,
                                         outline=outline, width=6 if outline else 0)
    return im


class Reel:
    """The assets once, then frame(i) for every frame."""

    def __init__(self, cfg):
        FC = _fc()
        self.c = cfg
        self.t = timeline(cfg)
        self.hc, self.ac = tuple(cfg["home_color"]), tuple(cfg["away_color"])
        # the split ground: home on the right, a diagonal seam with a shadow
        bg = Image.new("RGBA", (W, H), self.ac + (255,))
        d = ImageDraw.Draw(bg)
        d.polygon([(W / 2 + 260, 0), (W, 0), (W, H), (W / 2 - 260, H)], fill=self.hc + (255,))
        sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(sh).line([(W / 2 + 260, 0), (W / 2 - 260, H)], fill=(0, 0, 0, 120), width=40)
        bg.alpha_composite(sh.filter(ImageFilter.GaussianBlur(18)))
        self.bg = bg
        self.dark = Image.new("RGBA", (W, H), DARK_BG + (255,))
        # the wordmark on a white pill with a dark edge (it must read on white too)
        logo = Image.new("RGBA", (W, 200), (0, 0, 0, 0))
        lp = pill(380, 120, WHITE, INK)
        logo.alpha_composite(lp, (W // 2 - lp.width // 2, 40))
        tmp = Image.new("RGB", (W, 200), WHITE)
        FC.wordmark_at(tmp, W // 2, 106, 80, anchor="mm")
        mask = Image.new("L", (W, 200), 0)
        ImageDraw.Draw(mask).rounded_rectangle([W // 2 - 184, 52, W // 2 + 184, 160], 54, fill=255)
        logo.paste(tmp.convert("RGBA"), (0, 0), mask)
        self.logo = logo
        hk = cfg["hook"]
        self.hook = [fit_text(hk[0], "ExtraBold", 230, WHITE, 980, stroke=10),
                     fit_text(hk[1], "ExtraBold", 150, ACC, 1000, stroke=10),
                     fit_text(hk[2], "ExtraBold", 190, WHITE, 980, stroke=10)]
        self.hd, self.ad = self._disc(cfg["home_badge"], cfg["home"]), self._disc(cfg["away_badge"], cfg["away"])
        self.small = [self._crest(cfg["home_badge"], 130), self._crest(cfg["away_badge"], 130)]
        self.name_h = fit_text(cfg["home"], "ExtraBold", 84, ink(self.hc), 470)
        self.name_a = fit_text(cfg["away"], "ExtraBold", 84, ink(self.ac), 470)
        self.stat_t = text_img("الأرقام بتقول إيه؟", "ExtraBold", 96, WHITE)
        p = cfg["punch"] or ["", ""]
        self.punch = [fit_text(p[0], "ExtraBold", 92, WHITE, 1000), fit_text(p[1], "ExtraBold", 110, ACC, 1000)]
        q = cfg["question"]
        self.q1 = fit_text(q[0], "ExtraBold", 170, WHITE, 1000)
        self.q2 = fit_text(q[1], "ExtraBold", 140, ACC, 1000)
        self.opts = [fit_text(o, "ExtraBold", 80, INK, 320) for o in cfg["options"]]
        self.cta = fit_text("اكتب رأيك في الكومنتات", "Bold", 64, WHITE, 1000)
        tb = cfg["table"]
        self.tab_t = fit_text(tb["title"], "ExtraBold", 96, WHITE, 1000) if tb else None
        self.zone_t = text_img("منطقة الهبوط", "ExtraBold", 54, (255, 110, 125))

    def _crest(self, url, size):
        FC = _fc()
        try:
            import fb_reel as R                      # noqa: PLC0415 - the 300px 365 crest + fill_box
            cr = FC.crest_image(R.big_badge(url), size) or FC.crest_image(url, size)
            return R.fill_box(cr.convert("RGBA"), size) if cr is not None else None
        except Exception:                             # noqa: BLE001 - offline, an odd file
            return None

    def _disc(self, url, name):
        r = 170
        im = Image.new("RGBA", (2 * r + 40, 2 * r + 40), (0, 0, 0, 0))
        sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
        ImageDraw.Draw(sh).ellipse([26, 34, 2 * r + 26, 2 * r + 34], fill=(0, 0, 0, 120))
        im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(12)))
        ImageDraw.Draw(im).ellipse([20, 20, 2 * r + 20, 2 * r + 20], fill=WHITE)
        c = self._crest(url, int(r * 1.35))
        if c is not None:
            im.alpha_composite(c, (20 + r - c.width // 2, 20 + r - c.height // 2))
        else:
            paste_c(im, text_img((name or "?")[:1], "ExtraBold", 170, INK), 20 + r, 20 + r)
        return im

    # ------------------------------------------------------------ scenes
    def frame(self, i):
        b = (i / FPS) / BEAT
        t = self.t
        if b < 4:
            return self._hook(b)
        if b < (t["stats"] or t["table"] or t["q"]):
            return self._score(b)
        if t["stats"] and b < (t["table"] or t["q"]):
            return self._stats(b)
        if t["table"] and b < t["q"]:
            return self._table(b)
        return self._question(b)

    def _hook(self, b):
        img = self.bg.copy()
        throb = 1.0 + 0.06 * math.exp(-((b % 1) * 6))
        for im, y in zip(self.hook, (560, 860, 1120)):
            paste_c(img, im, W / 2, y, throb)              # all three lines from frame 0
        img.alpha_composite(self.logo, (0, 40))
        return img

    def _score(self, b):
        c, step = self.c, self.t["step"]
        goals = c["goals"]
        img = self.bg.copy()
        img.alpha_composite(self.logo, (0, 40))
        s = ease((b - 4) * 1.6)
        paste_c(img, self.hd, W * 3 / 4 + (1 - s) * 600, 560)
        paste_c(img, self.ad, W / 4 - (1 - s) * 600, 560)
        paste_c(img, self.name_h, W * 3 / 4, 800, alpha=lin((b - 4.5) * 2))
        paste_c(img, self.name_a, W / 4, 800, alpha=lin((b - 4.5) * 2))
        n = int(max(0, min(len(goals), math.floor((b - 6) / step) + 1))) if b >= 6 else 0
        hs = sum(1 for g in goals[:n] if g[1] == "h")
        as_ = n - hs
        if not goals:                                       # 0-0: the score stands from the start
            hs, as_ = c["hs"], c["as"]
        ph = ((b - 6) / step) % 1
        pop = 1.0 + (0.35 * math.exp(-ph * 7) if 6 <= b < 6 + len(goals) * step else 0)
        paste_c(img, pill(560, 280, INK + (255,), WHITE), W / 2, 1050)
        paste_c(img, text_img(f"{as_} - {hs}", "ExtraBold", 250, WHITE), W / 2, 1050, pop)
        shown = {"h": 0, "a": 0}
        extra = {"h": 0, "a": 0}
        for k, (m, side, who, tag) in enumerate(goals[:n]):
            if shown[side] >= 4:
                extra[side] += 1
                continue
            col = self.hc if side == "h" else self.ac
            tg = {"ج": " (ج)", "عكسي": " (عكسي)"}.get(tag, "")
            row = scorer_row(f"{who}{tg}", m, ink(col), 440)
            x = W * 3 / 4 if side == "h" else W / 4
            y = 1250 + shown[side] * 84
            shown[side] += 1
            band = pill(row.width + 36, 66, (255, 255, 255, 150) if ink(col) == INK else (0, 0, 0, 110))
            ap = lin((b - 6 - k * step) * 4)
            paste_c(img, band, x, y, alpha=ap)
            paste_c(img, row, x + (1 - ap) * (120 if side == "h" else -120), y, alpha=ap)
        for side, x in (("h", W * 3 / 4), ("a", W / 4)):
            if extra[side]:
                paste_c(img, text_img(f"+{extra[side]}", "ExtraBold", 54, ink(self.hc if side == "h" else self.ac)),
                        x, 1250 + 4 * 84)
        if 6 <= b < 6 + len(goals) * step and ph < 0.12:
            img.alpha_composite(Image.new("RGBA", (W, H), (255, 255, 255, int(150 * (1 - ph / 0.12)))))
        return img

    def _stats(self, b):
        c, t = self.c, self.t
        img = self.dark.copy()
        img.alpha_composite(self.logo, (0, 40))
        paste_c(img, self.stat_t, W / 2, 330, ease((b - t["stats"]) * 2))
        for cr, x in zip(self.small, (W - 180, 180)):
            if cr is not None:
                img.alpha_composite(cr, (int(x - cr.width / 2), 440))
        gap = 300 if c["table"] else 260
        for k, (label, hv, av, suf) in enumerate(c["stats"]):
            st = t["stats"] + 1 + t["srow"] * k
            if b < st:
                continue
            y = 640 + k * gap
            g = lin((b - st) * 1.4)
            paste_c(img, text_img(label, "Bold", 60, (200, 212, 235)), W / 2, y)
            paste_c(img, text_img(f"{round(hv * g)}{suf}", "ExtraBold", 100, WHITE), W - 120, y + 110)
            paste_c(img, text_img(f"{round(av * g)}{suf}", "ExtraBold", 100,
                                  self.ac if bright(self.ac) else WHITE), 120, y + 110)
            mx = max(hv, av, 1)
            full = W / 2 - 250
            hw, aw = full * hv / mx * g, full * av / mx * g
            d = ImageDraw.Draw(img)
            d.rounded_rectangle([W / 2 + 8, y + 92, W / 2 + 8 + max(hw, 16), y + 128], 18,
                                fill=self.hc if bright(self.hc) else (90, 110, 160))
            d.rounded_rectangle([W / 2 - 8 - max(aw, 16), y + 92, W / 2 - 8, y + 128], 18,
                                fill=self.ac if bright(self.ac) else (90, 110, 160))
        if c["punch"] and b >= t["punch"]:
            paste_c(img, self.punch[0], W / 2, 1460, ease((b - t["punch"]) * 2.5))
            paste_c(img, self.punch[1], W / 2, 1580, ease((b - t["punch"] - 0.5) * 2.5))
        return img

    def _table(self, b):
        tb, s0 = self.c["table"], self.t["table"]
        img = self.dark.copy()
        img.alpha_composite(self.logo, (0, 40))
        paste_c(img, self.tab_t, W / 2, 300, ease((b - s0) * 2.5))
        top, rh = 430, 118
        rows = tb["rows"]
        zone = [k for k, r in enumerate(rows) if tb["drop_from"] and r[0] >= tb["drop_from"]]
        if zone:
            a = lin((b - s0 - 1.5) * 2)
            z = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            ImageDraw.Draw(z).rounded_rectangle([40, top + zone[0] * rh - 10, W - 40, top + (zone[-1] + 1) * rh + 4], 26,
                                                fill=(200, 20, 40, int(95 * a)), outline=(255, 70, 90, int(255 * a)), width=5)
            img.alpha_composite(z)
            paste_c(img, self.zone_t, W / 2, top + (zone[-1] + 1) * rh + 62, alpha=a)
        for k, (pos, name, pts, ours) in enumerate(rows):
            a = ease((b - s0 - 0.5 - k * 0.18) * 3)
            if a <= 0.01:
                continue
            y = top + k * rh + rh / 2
            pulse = 1.0 + (0.07 * abs(math.sin((b - s0 - 3) * math.pi)) if ours and b > s0 + 3 else 0)
            row = Image.new("RGBA", (W - 120, rh - 16), (0, 0, 0, 0))
            d = ImageDraw.Draw(row)
            d.rounded_rectangle([0, 0, row.width - 1, row.height - 1], 24,
                                fill=(255, 255, 255, 255) if ours else (255, 255, 255, 26))
            col = INK if ours else WHITE
            pi = text_img(str(pos), "ExtraBold", 64, col)
            row.alpha_composite(pi, (row.width - 40 - pi.width, (row.height - pi.height) // 2))
            ni = fit_text(name, "ExtraBold", 60, col, 560)
            row.alpha_composite(ni, (row.width - 150 - ni.width, (row.height - ni.height) // 2))
            pt = text_img(str(pts), "ExtraBold", 64, col)
            lab = text_img("نقطة", "Bold", 40, col)
            row.alpha_composite(pt, (40 + lab.width + 14, (row.height - pt.height) // 2))
            row.alpha_composite(lab, (40, (row.height - lab.height) // 2 + 6))
            paste_c(img, row, W / 2 + (1 - a) * 500, y, pulse)
        return img

    def _question(self, b):
        q = self.t["q"]
        img = self.dark.copy()
        stripe = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(stripe).polygon([(0, 1500), (W, 1380), (W, 1440), (0, 1560)], fill=self.ac + (255,))
        ImageDraw.Draw(stripe).polygon([(0, 1560), (W, 1440), (W, 1500), (0, 1620)], fill=self.hc + (255,))
        img.alpha_composite(stripe)
        img.alpha_composite(self.logo, (0, 40))
        paste_c(img, self.q1, W / 2, 520, ease((b - q) * 2.5))
        paste_c(img, self.q2, W / 2, 720, ease((b - q - 0.5) * 2.5))
        for k, (o, x) in enumerate(zip(self.opts, (W * 3 / 4 + 20, W / 4 - 20))):
            a = ease((b - q - 2 - k * 0.5) * 2.5)
            paste_c(img, pill(360, 140, WHITE), x, 1000, a)
            paste_c(img, o, x, 1000, a)
        paste_c(img, text_img("ولا", "ExtraBold", 70, WHITE), W / 2, 1000, lin((b - q - 2.5) * 3))
        paste_c(img, self.cta, W / 2, 1260, lin((b - q - 4) * 3))
        a = lin((b - q - 4.5) * 3)
        if a > 0:
            ar_ = Image.new("RGBA", (120, 90), (0, 0, 0, 0))
            ImageDraw.Draw(ar_).polygon([(10, 10), (110, 10), (60, 80)], fill=ACC)
            paste_c(img, ar_, W / 2, 1330 + 18 * math.sin(b * math.pi), alpha=a)
        return img


# ================================================================ the music
def music(cfg, path, secs):
    """128 BPM in a minor key (its own key per match): kick, claps, hats, a
    driving bass, stab chords, a riser into the score and into the question,
    and an IMPACT on every scene cut and every goal tick."""
    import numpy as np                                   # noqa: PLC0415
    import wave                                          # noqa: PLC0415
    t_ = timeline(cfg)
    n = int(secs * SR) + SR // 2
    L, R = np.zeros(n), np.zeros(n)
    rng = np.random.default_rng(cfg.get("seed", 22))
    key = cfg.get("key", 0)

    def tt(d):
        return np.arange(int(d * SR)) / SR

    def at(sig, start, gain=1.0, pan=0.0):
        i = int(start * SR)
        if i >= n:
            return
        sig = sig[:n - i] * gain
        L[i:i + len(sig)] += sig * (1 - max(pan, 0))
        R[i:i + len(sig)] += sig * (1 + min(pan, 0))

    def hz(m):
        return 440.0 * 2 ** ((m + key - 69) / 12)

    def saw(f, d, decay):
        x = tt(d)
        return sum(np.sin(2 * np.pi * f * k * x) / k for k in range(1, 9)) * np.exp(-x * decay)

    x = tt(0.3)
    kick = np.sin(2 * np.pi * np.cumsum(48 + 140 * np.exp(-x * 35)) / SR) * np.exp(-x * 11)
    x = tt(0.2)
    clap = np.diff(rng.standard_normal(len(x)), prepend=0) * 0.6 * np.exp(-x * 22)
    x = tt(0.04)
    hat = np.diff(np.diff(rng.standard_normal(len(x)), prepend=0), prepend=0) * np.exp(-x * 110) * 0.35
    x = tt(1.4)
    boom = (np.sin(2 * np.pi * np.cumsum(38 + 90 * np.exp(-x * 6)) / SR) * np.exp(-x * 2.6)
            + rng.standard_normal(len(x)) * np.exp(-x * 9) * 0.5)
    prog = [(45, (57, 60, 64)), (41, (53, 57, 60)), (48, (55, 60, 64)), (43, (55, 59, 62))]
    total = t_["total"]
    for bt in range(total):
        s = bt * BEAT
        intro = bt < 4
        at(kick, s, 0.7 if intro else 0.9)
        if bt % 2 == 1:
            at(clap, s, 0.5)
        for q in range(4):
            if not intro or q % 2 == 0:
                at(hat, s + q * BEAT / 4, 0.8 if q % 2 else 0.5, pan=0.3)
        root, chord = prog[(bt // 4) % 4]
        for e in range(2):
            at(saw(hz(root - 12 + (12 if e else 0)), BEAT / 2, 9) * 0.22, s + e * BEAT / 2)
        if bt % 4 in (0, 3):
            for k, mm in enumerate(chord):
                at(saw(hz(mm), BEAT * 0.9, 5) * 0.07, s, pan=(k - 1) * 0.5)
    for a, z in ((2, 4), (t_["q"] - 2, t_["q"])):
        d = (z - a) * BEAT
        x = tt(d)
        r = rng.standard_normal(len(x)) * (x / d) ** 2 * 0.35
        at(r + np.sin(2 * np.pi * np.cumsum(200 + 900 * (x / d) ** 2) / SR) * (x / d) * 0.15, a * BEAT)
    cuts = [0, 4, t_["stats"], t_["table"], t_["q"]]
    for bt in [c for c in cuts if c is not None]:
        at(boom, bt * BEAT, 0.9)
    for k in range(len(cfg["goals"])):
        at(boom, (6 + k * t_["step"]) * BEAT, 0.55)
    mix = np.tanh(np.stack([L, R], 1) * 0.9)[:int(secs * SR)]
    fade = int(0.4 * SR)
    mix[-fade:] *= np.linspace(1, 0, fade)[:, None]
    pcm = (mix / max(1e-9, float(np.abs(mix).max())) * 0.92 * 32767).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


# ================================================================ the MP4
def render(cfg, out, exe, sheet=None):
    """Write the MP4 (H.264 yuv420p 30 fps + AAC, faststart). Returns True.
    sheet = a path: also save five frames side by side (a contact sheet)."""
    t = timeline(cfg)
    assert t["total"] <= MAX_BEATS, f"{t['total']} beats is over the 15 s cap"
    secs = t["total"] * BEAT
    nfr = int(round(secs * FPS))
    reel = Reel(cfg)
    tmp = tempfile.mkdtemp(prefix="reelstyle-")
    wav = os.path.join(tmp, "music.wav")
    try:
        music(cfg, wav, secs)
        cmd = [exe, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
               "-r", str(FPS), "-i", "-", "-i", wav, "-c:v", "libx264", "-preset", "medium", "-crf", "21",
               "-maxrate", "2500k", "-bufsize", "5000k", "-pix_fmt", "yuv420p", "-profile:v", "high",
               "-c:a", "aac", "-b:a", "160k", "-ar", str(SR), "-ac", "2", "-shortest",
               "-movflags", "+faststart", out]
        p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        marks = {0, int(5.0 * FPS), int((t["stats"] or 0) * BEAT * FPS + 40),
                 int((t["table"] or t["q"]) * BEAT * FPS + 50), nfr - 10}
        keep = []
        try:
            for i in range(nfr):
                im = reel.frame(i).convert("RGB")
                if sheet and i in marks:
                    keep.append(im.resize((360, 640)))
                p.stdin.write(im.tobytes())
        finally:
            p.stdin.close()
            p.wait()
        if p.returncode:
            raise RuntimeError(f"ffmpeg exited {p.returncode}")
        if sheet and keep:
            sh = Image.new("RGB", (370 * len(keep), 640), WHITE)
            for k, im in enumerate(keep):
                sh.paste(im, (k * 370, 0))
            sh.save(sheet, quality=85)
        return True
    finally:
        import shutil                                    # noqa: PLC0415
        shutil.rmtree(tmp, ignore_errors=True)


# ================================================================ data
def focus_side(m):
    """'h' / 'a': the side the page follows; None for both or neither."""
    from site_lib import names as N                      # noqa: PLC0415
    comp = m.get("competition") or ""
    hit = {s for s, key in (("h", "home"), ("a", "away"))
           if any(N._tok_hit(t, {"home": m.get(key), "away": ""}) and N._in_scope(c, comp)
                  for t, c in N.TICKER_TEAMS)}
    return next(iter(hit)) if len(hit) == 1 else None


def match_stats_for(m):
    """{"h": {...}, "a": {...}} from data/match_stats.json, else straight from
    365scores (the row lands there a refresh or two after the whistle); {}
    when neither has it - the reel then skips its numbers scene."""
    try:
        import match_stats as MS                         # noqa: PLC0415
        row = MS.load().get(str(m.get("match_id")))
        if row and row.get("h") and row.get("a"):
            return {"h": row["h"], "a": row["a"]}
    except Exception:                                    # noqa: BLE001
        pass
    try:
        import fetch_data as fd                          # noqa: PLC0415
        import match_brief as MB                         # noqa: PLC0415
        import match_stats as MS                         # noqa: PLC0415
        gid = MB.resolve_s365_game(m)
        if gid:
            st, _ = MS.parse_stats(fd._s365(f"game/stats/?appTypeId=5&langId=27&timezoneName=Africa/Cairo&games={gid}"))
            if st.get("h") and st.get("a"):
                return st
    except Exception:                                    # noqa: BLE001
        pass
    return {}


def cfg_for(m):
    """The plan for one finished match from the site's own data."""
    import build_site as b                               # noqa: PLC0415
    import fb_cards as FC                                # noqa: PLC0415
    import match_poster as MP                            # noqa: PLC0415
    ge = b.goals_index()
    goals = []
    for g in b.match_goals(ge, m) or []:
        if g.get("side") not in ("h", "a"):
            continue
        tag = {"ج": "ج", "عكسية": "عكسي"}.get(g.get("tag") or "", "")
        goals.append(((g.get("minute") or "").strip().rstrip("'"), g["side"], g.get("player") or "", tag))
    goals.sort(key=lambda g: (_minute(g[0]) is None, _minute(g[0]) or 0))
    # a goal list that does not add up to the score is not drawn goal by goal
    if sum(1 for g in goals if g[1] == "h") != m["home_score"] or sum(1 for g in goals if g[1] == "a") != m["away_score"]:
        goals = []
    colours = MP.fills(MP.MC_name(m, "home"), MP.MC_name(m, "away"), m.get("competition"), FC._feed_colors(m))
    return plan(m, goals, match_stats_for(m), b.load("standings.json"), focus_side(m), b.ar_team,
                colours, (m.get("home_badge"), m.get("away_badge")))


def main():
    import argparse                                      # noqa: PLC0415
    import json                                          # noqa: PLC0415
    import build_site as b                               # noqa: PLC0415
    import fb_reel as R                                  # noqa: PLC0415
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--match", required=True)
    ap.add_argument("--out", required=True, help="the MP4 (an ABSOLUTE path is safest)")
    args = ap.parse_args()
    m = next((x for x in b.load("matches_archive.json") + b.load("matches.json")
              if str(x.get("match_id")) == str(args.match)), None)
    if not m or m.get("home_score") is None:
        raise SystemExit(f"match {args.match}: not in the data or not played")
    cfg = cfg_for(m)
    print(json.dumps({k: v for k, v in cfg.items() if k not in ("home_badge", "away_badge")}, ensure_ascii=False))
    render(cfg, args.out, R.ffmpeg(), sheet=os.path.splitext(args.out)[0] + "-sheet.jpg")
    print(f"wrote {args.out}  ({timeline(cfg)['total'] * BEAT:.1f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
