#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A GROUP-STAGE match as a vertical reel (2026-11-12, for Egypt v Malawi in
the AFCON 2027 qualifiers: «الطريق لأمم أفريقيا 2027»). The group's table,
computed here from the results in the data, then the match itself.

    hook   2.4 s  the two flags + «مصر على القمة…» / «والليلة نكمّل قدام مالاوي»
    table  5.5 s  «المجموعة بعد جولتين»: the rows drop in one after another
                  (position, flag, name, played, goal difference, points -
                  every number in its OWN slot, never through the bidi pass),
                  the focus team's row lit, a gold line under the last
                  qualifying place with «التأهل» on it
    match  3.9 s  home flag on the RIGHT (Arabic reads right to left), «×»,
                  the day, the Cairo time, the round and the competition
    outro  3.0 s  «توقعك كام؟» + the wordmark + elgoon.com (moment_reel's cta)

14.8 s - under the 15 s rule. The group = the two teams + every team either
of them meets in the same competition this season; the table counts only the
FINISHED matches that kicked off before this one. Order: points, then goal
difference, then goals scored; a tie in all three keeps alphabetical order
and SHARES the position (no order is invented). Same canvas, wordmark, safe
band, music and encoder as table_reel / scorers_reel / day_reel.

    python group_reel.py --match 4716606 --out r.mp4 --sheet r.png --caption r.txt
    python group_reel.py --match 4716607 --png frames/        # stills, no ffmpeg
"""
import argparse
import datetime
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from PIL import ImageDraw            # noqa: E402

import day_reel as D                 # noqa: E402
import fb_cards as C                 # noqa: E402
import fb_reel as R                  # noqa: E402
import moment_reel as M              # noqa: E402

W, H = M.W, M.H
HOOK, TABLE, MATCH, OUTRO = 2.4, 5.5, 3.9, 3.0
DONE = {"FINISHED", "AWARDED"}
FOCUS = "مصر"                        # the page's team: the hook is said from its side
# The competition as the reel names it, per season (the year is the finals',
# not in the feed), and how many teams of a group go through.
EDITION = {("Africa Cup of Nations Qualification", "2026-27"): ("تصفيات أمم أفريقيا 2027", "أمم أفريقيا 2027")}
QUALIFY = {"Africa Cup of Nations Qualification": 2}

# the table's geometry: panels 60..PANEL_R, clear of the Reels buttons (0.91 W = 983)
PANEL_R = 978
ROW_HALF = 72
ROW_YS = (610, 780, 990, 1160)       # a wider gap after the qualifying places for the line
X_POS, X_FLAG, X_NAME_R = 930, 838, 772
FLAG = 96
X_PL, X_GD, X_PTS = 410, 280, 140
MAX_W = W * 0.78                     # centred lines stay inside 119..961


# ---------------------------------------------------------------- data
def load_matches():
    """archive + current, one per match_id (the current file wins)."""
    import build_site as b
    out = {}
    for name in ("matches_archive.json", "matches.json"):
        for m in b.load(name):
            if m.get("match_id"):
                out[str(m["match_id"])] = m
    return list(out.values())


def find(matches, match_id):
    for m in matches:
        if str(m.get("match_id")) == str(match_id):
            return m
    raise SystemExit(f"match {match_id} not in the data")


def season_of(date):
    import story_events as SE
    return SE.season_of(date)


def _ko(m):
    return f"{m.get('kickoff') or ''}T{m.get('koff_time') or '00:00'}"


def group_matches(matches, match):
    """The match's group: the competition's matches of this season between
    the two teams and everyone either of them meets."""
    comp, season = match["competition"], season_of(match["kickoff"])
    same = [m for m in matches if m.get("competition") == comp and season_of(m.get("kickoff")) == season]
    pair = {match["home"], match["away"]}
    teams = set(pair)
    for m in same:
        if pair & {m["home"], m["away"]}:
            teams |= {m["home"], m["away"]}
    return [m for m in same if m["home"] in teams and m["away"] in teams], teams


def badges(ms):
    out = {}
    for m in ms:
        for side in ("home", "away"):
            if m.get(f"{side}_badge"):
                out.setdefault(m[side], m[f"{side}_badge"])
    return out


def table(matches, match):
    """[{pos, team, played, won, drawn, lost, gf, ga, gd, pts, badge}] before
    `match` kicks off: points, goal difference, goals scored; a full tie keeps
    alphabetical order and shares the position."""
    ms, teams = group_matches(matches, match)
    before = [m for m in ms if (m.get("status") or "") in DONE and _ko(m) < _ko(match)
              and m.get("home_score") is not None and m.get("away_score") is not None]
    rows = {t: dict(team=t, played=0, won=0, drawn=0, lost=0, gf=0, ga=0) for t in teams}
    for m in before:
        hs, as_ = int(m["home_score"]), int(m["away_score"])
        for t, f, a in ((m["home"], hs, as_), (m["away"], as_, hs)):
            r = rows[t]
            r["played"] += 1
            r["gf"] += f
            r["ga"] += a
            r["won" if f > a else "drawn" if f == a else "lost"] += 1
    bd = badges(ms)
    out = []
    for r in rows.values():
        r["gd"] = r["gf"] - r["ga"]
        r["pts"] = 3 * r["won"] + r["drawn"]
        r["badge"] = bd.get(r["team"])
        out.append(r)
    out.sort(key=lambda r: r["team"])                       # alphabetical first ...
    out.sort(key=lambda r: (-r["pts"], -r["gd"], -r["gf"]))  # ... kept by the stable sort on a tie
    for r in out:
        r["pos"] = 1 + sum(1 for o in out if (o["pts"], o["gd"], o["gf"]) > (r["pts"], r["gd"], r["gf"]))
    return out


def rounds_played(tab):
    return max((r["played"] for r in tab), default=0)


# ---------------------------------------------------------------- words
def rounds_words(n):
    return {1: "بعد الجولة الأولى", 2: "بعد جولتين"}.get(n, f"بعد {n} جولات" if 3 <= n <= 10 else f"بعد {n} جولة")


def points_gap(k):
    return {1: "بنقطة", 2: "بنقطتين"}.get(k, f"بـ{k} نقاط" if 3 <= k <= 10 else f"بـ{k} نقطة")


def ar_time(koff):
    """«21:00» -> ('9', 'مساءً')."""
    h, mi = (int(x) for x in (koff or "00:00").split(":")[:2])
    part = "صباحًا" if h < 12 else "ظهرًا" if h < 15 else "عصرًا" if h < 18 else "مساءً"
    h12 = h % 12 or 12
    return (f"{h12}:{mi:02d}" if mi else str(h12)), part


TODAY = None            # the posting day (Cairo); None = today. Tests pin it.
# Hand-written lines (2026-11-13, Sudan v Senegal: «السودان مازال لديه الفرصة
# ... نتمنى تحقيق نتيجة ايجابية»): --hook "a|b", --outro "a|b" and --lead
# replace the computed wording; the table and the match card stay computed.
HOOK_LINES = OUTRO_LINES = LEAD = TABLE_TITLE = None


def tonight(match):
    """«والليلة» / «والنهارده» on match day; «وغدًا» when the reel goes out the
    day before (user 2026-11-12: Egypt v Malawi posted on Thursday);
    «ويوم الجمعة» further ahead."""
    from site_lib.arabic import _AR_DAYS
    today = TODAY or datetime.datetime.now(C.CAIRO).date()
    day = datetime.date.fromisoformat(match["kickoff"])
    ahead = (day - today).days
    if ahead == 1:
        return "وغدًا"
    if ahead >= 2:
        return f"ويوم {_AR_DAYS[day.weekday()]}"
    return "والليلة" if int((match.get("koff_time") or "00:00")[:2]) >= 18 else "والنهارده"


def focus_of(match):
    return FOCUS if FOCUS in (match["home"], match["away"]) else match["home"]


def hook_lines(tab, match):
    """(«مصر على القمة…», «والليلة نكمّل قدام مالاوي») from the two rows."""
    if HOOK_LINES:
        return tuple(HOOK_LINES)
    me = focus_of(match)
    opp = match["away"] if me == match["home"] else match["home"]
    pts = {r["team"]: r["pts"] for r in tab}
    k = pts[me] - pts[opp]
    if me == FOCUS:
        # user 2026-11-12: not «مالاوي ورانا» - say where WE stand, not who chases us
        first, second = focus_words(tab, me, opp, k, points_gap)
        return first + "…", second(match)
    first = (f"{opp} ورا {me} {points_gap(k)}…" if k > 0 else
             f"{opp} قدام {me} {points_gap(-k)}…" if k < 0 else f"{opp} و{me} بنفس النقاط…")
    return first, f"{tonight(match)} المواجهة"


def focus_words(tab, me, opp, k, gapw):
    """The page's own team (FOCUS): «مصر على القمة» / «والليلة نكمّل قدام مالاوي»
    when it leads the group, otherwise the plain gap from its side."""
    top = bool(tab) and tab[0]["team"] == me
    if top:
        return f"{me} على القمة", lambda m: f"{tonight(m)} نكمّل قدام {opp}"
    first = (f"{me} فوق {opp} {gapw(k)}" if k > 0 else
             f"{opp} فوق {me} {gapw(-k)}" if k < 0 else f"{me} و{opp} بنفس النقاط")
    return first, lambda m: f"{tonight(m)} المواجهة"


def edition(match):
    from site_lib.names import comp_label
    return EDITION.get((match["competition"], season_of(match["kickoff"])),
                       (comp_label(match["competition"]),) * 2)


def day_words(match):
    from site_lib.arabic import _AR_DAYS, _AR_MONTHS
    d = datetime.date.fromisoformat(match["kickoff"])
    return _AR_DAYS[d.weekday()], d.day, _AR_MONTHS[d.month]


# ---------------------------------------------------------------- drawing
def centre_line(d, y, s, weight, size, fill, max_w=MAX_W):
    s = C.ar(s)
    C.draw_center(d, W / 2, y, s, C.fit(d, s, weight, size, max_w, 26), fill)


def slots(d, cx, y, parts, gap=18):
    """A line made of separate slots, laid out right to left: Arabic words
    and numbers each drawn on their own (a number never goes through bidi).
    parts = [(text, font, fill)] in reading order."""
    shaped = [(C.ar(s), f, c) for s, f, c in parts]
    ws = [C.text_w(d, s, f) for s, f, _ in shaped]
    x = cx + (sum(ws) + gap * (len(ws) - 1)) / 2
    for (s, f, c), w in zip(shaped, ws):
        bb = d.textbbox((0, 0), s, font=f)
        d.text((x - w - bb[0], y), s, font=f, fill=c)
        x -= w + gap


def versus(d, cx, cy, size, fill=None):
    """The «×» between the flags, drawn as two strokes: Almarai's glyph is
    a small multiplication sign that reads as a dot at reel size."""
    r, w = size / 2, max(6, int(size * 0.2))
    for a, b in (((cx - r, cy - r), (cx + r, cy + r)), ((cx - r, cy + r), (cx + r, cy - r))):
        d.line((a, b), fill=fill or M.GOLD, width=w)
        for x, y in (a, b):
            d.ellipse((x - w / 2, y - w / 2, x + w / 2, y + w / 2), fill=fill or M.GOLD)


def gd_text(gd):
    return f"+{gd}" if gd > 0 else str(gd)


def table_row(im, t, r, cy, t0, lit):
    from site_lib.names import ar_team
    e = M.ease(t, t0, M.FADE + 0.05)
    if e <= 0:
        return
    lay = M.layer()
    d = ImageDraw.Draw(lay)
    d.rounded_rectangle((60, cy - ROW_HALF, PANEL_R, cy + ROW_HALF), 28,
                        fill=(255, 255, 255, 64 if lit else 24),
                        outline=M.GOLD if lit else None, width=4 if lit else 0)
    C.draw_center(d, X_POS, cy - 34, str(r["pos"]), C.font("ExtraBold", 54), M.GOLD if lit else C.WHITE)
    R.crest_at(lay, r.get("badge"), ar_team(r["team"]), FLAG, X_FLAG, cy)
    nm = C.ar(ar_team(r["team"]))
    f = C.fit(d, nm, "ExtraBold", 46, X_NAME_R - X_PL - 70, 28)
    d.text((X_NAME_R - C.text_w(d, nm, f), cy - 28), nm, font=f, fill=C.WHITE)
    fs = C.font("Bold", 46)
    C.draw_center(d, X_PL, cy - 26, str(r["played"]), fs, M.SOFT)
    C.draw_center(d, X_GD, cy - 26, gd_text(r["gd"]), fs, M.SOFT)
    C.draw_center(d, X_PTS, cy - 40, str(r["pts"]), C.font("ExtraBold", 72), M.GOLD if lit else C.WHITE)
    M.put(im, lay, e, dy=-48 * (1 - e))                   # drops in from above


def qualify_line(im, t, y, t0):
    """The gold line under the last qualifying place, drawn right to left,
    with «التأهل» on it."""
    e = M.ease(t, t0, 0.45)
    if e <= 0:
        return
    lay = M.layer()
    d = ImageDraw.Draw(lay)
    x_r, x_l = PANEL_R, 60
    x = x_r - (x_r - x_l) * e
    d.rounded_rectangle((x, y - 3, x_r, y + 3), 3, fill=M.GOLD)
    s = C.ar("التأهل")
    f = C.font("ExtraBold", 34)
    tw = C.text_w(d, s, f)
    px = x_r - 40                                         # the label rides at the line's start (RTL)
    d.rounded_rectangle((px - tw - 36, y - 26, px, y + 26), 26, fill=M.GOLD)
    d.text((px - 18 - tw, y - 21), s, font=f, fill=C.BLUE_DARK)
    M.put(im, lay, M.ease(t, t0, 0.2))


def build(tab, match):
    from site_lib.names import ar_team
    bg = R.background()
    ctx = M.context({"home": {"name": ""}, "away": {"name": ""}})
    home, away = match["home"], match["away"]
    url = badges([match])
    me = focus_of(match)
    hooks = hook_lines(tab, match)        # 2 lines, or 3 when hand-written
    rounds = rounds_played(tab)
    q = QUALIFY.get(match["competition"], 0)
    comp_full, _ = edition(match)

    def flags(lay, size, y, xs=(W * 0.72, W * 0.28)):
        for side, x in zip((home, away), xs):          # home on the RIGHT
            R.crest_at(lay, url.get(side), ar_team(side), size, x, y)

    def hook(t):
        im = bg.copy()
        M.header(im)
        e = M.ease(t, 0.0, 0.45)
        lay = M.layer()
        flags(lay, 250, 650)
        d = ImageDraw.Draw(lay)
        versus(d, W / 2, 650, 64)
        M.put(im, lay, e, dy=M.SLIDE * (1 - e))
        # the first line white, the rest gold; a hand-written long line can be
        # split over a third line instead of shrinking (2026-11-13)
        white = 2 if len(hooks) == 4 else 1           # 4 lines = two sentences of two lines each
        for i, (s, col) in enumerate((h, C.WHITE if i < white else M.GOLD) for i, h in enumerate(hooks)):
            e = M.ease(t, 0.35 + i * M.STAGGER, M.FADE)
            if e > 0:
                lay = M.layer()
                centre_line(ImageDraw.Draw(lay), 900 + i * (120 if len(hooks) < 4 else 105), s, "ExtraBold", 84, col)
                M.put(im, lay, e, dy=M.SLIDE * (1 - e))
        return im

    def table_scene(t):
        im = bg.copy()
        M.header(im)
        d = ImageDraw.Draw(im)
        _tt = (TABLE_TITLE or f"المجموعة {rounds_words(rounds)}").split("|")
        if len(_tt) == 1:
            centre_line(d, 418, _tt[0], "ExtraBold", 50, C.WHITE)
        else:                     # «a|b»: the title, and a gold line under it (2026-11-13)
            centre_line(d, 380, _tt[0], "ExtraBold", 50, C.WHITE)
            centre_line(d, 434, _tt[1], "Bold", 40, M.GOLD)
        fh = C.font("Bold", 32)
        for x, s in ((X_PL, "لعب"), (X_GD, "الفرق"), (X_PTS, "نقاط")):
            C.draw_center(d, x, 496, C.ar(s), fh, M.SOFT)
        for i, r in enumerate(tab[:len(ROW_YS)]):
            table_row(im, t, r, ROW_YS[i], 0.1 + i * 0.35, r["team"] == me)
        n = min(len(tab), len(ROW_YS))
        if 0 < q < n:
            qualify_line(im, t, (ROW_YS[q - 1] + ROW_YS[q]) / 2, 0.1 + n * 0.35 + 0.1)
            e = M.ease(t, 0.1 + n * 0.35 + 0.5, M.FADE)
            if e > 0:
                lay = M.layer()
                word = {1: "الأول يتأهل", 2: "أول اتنين يتأهلوا"}.get(q, f"أول {q} يتأهلوا")
                centre_line(ImageDraw.Draw(lay), ROW_YS[n - 1] + ROW_HALF + 34, f"{word} للنهائيات",
                            "Bold", 38, M.SOFT)
                M.put(im, lay, e, dy=M.SLIDE * (1 - e))
        return im

    def match_scene(t):
        im = bg.copy()
        M.header(im)
        e = M.ease(t, 0.05, M.FADE)
        if e > 0:
            lay = M.layer()
            d = ImageDraw.Draw(lay)
            fr = C.font("Bold", 38)
            slots(d, W / 2, 440, [("الجولة", fr, M.SOFT), (str(match["round"]), fr, M.SOFT),
                                  ("·", fr, M.GOLD)] + [(w, fr, M.SOFT) for w in comp_full.split()[:-1]]
                  + [(comp_full.split()[-1], fr, M.SOFT)], gap=12)
            M.put(im, lay, e, dy=M.SLIDE * (1 - e))
        for side, x, t0 in ((home, W * 0.72, 0.2), (away, W * 0.28, 0.4)):
            e = M.ease(t, t0, 0.45)
            if e <= 0:
                continue
            lay = M.layer()
            R.crest_at(lay, url.get(side), ar_team(side), 290, x, 720)
            d = ImageDraw.Draw(lay)
            nm = C.ar(ar_team(side))
            C.draw_center(d, x, 900, nm, C.fit(d, nm, "ExtraBold", 60, W * 0.36, 30), C.WHITE)
            M.put(im, lay, e, dy=M.SLIDE * (1 - e))
        e = M.ease(t, 0.55, M.POP)
        if e > 0:
            lay = M.layer()
            versus(ImageDraw.Draw(lay), W / 2, 720, 72 * (1 + 0.25 * (1 - e)))
            M.put(im, lay, e)
        day, dn, mon = day_words(match)
        hh, part = ar_time(match.get("koff_time"))
        for i, parts in enumerate((
                [(day, "ExtraBold", 72, C.WHITE), (str(dn), "ExtraBold", 72, C.WHITE), (mon, "ExtraBold", 72, C.WHITE)],
                [(hh, "ExtraBold", 56, M.GOLD), (part, "ExtraBold", 56, M.GOLD), ("بتوقيت القاهرة", "Bold", 44, M.SOFT)])):
            e = M.ease(t, 0.8 + i * M.STAGGER, M.FADE)
            if e <= 0:
                continue
            lay = M.layer()
            d = ImageDraw.Draw(lay)
            slots(d, W / 2, 1040 + i * 112, [(s, C.font(w, z), c) for s, w, z, c in parts], gap=16)
            M.put(im, lay, e, dy=M.SLIDE * (1 - e))
        return im

    def outro(t):
        sc = {"kind": "cta", "secs": OUTRO, "lines": list(OUTRO_LINES or ["توقعك كام؟", "اكتبه في الكومنتات"])}
        return M.scene(sc, t, ctx)

    return [(hook, HOOK, True), (table_scene, TABLE, True), (match_scene, MATCH, True), (outro, OUTRO, False)]


# ---------------------------------------------------------------- caption
def caption(tab, match):
    from site_lib.names import ar_team
    me = focus_of(match)
    opp = match["away"] if me == match["home"] else match["home"]
    pts = {r["team"]: r["pts"] for r in tab}
    k = pts[me] - pts[opp]
    gap = {1: "بنقطة واحدة"}.get(abs(k), points_gap(abs(k)))
    second = f"{tonight(match)} الحسم"
    if me == FOCUS:
        first, nxt = focus_words(tab, me, opp, k, lambda n: {1: "بنقطة واحدة"}.get(n, points_gap(n)))
        second = nxt(match)
    else:
        first = (f"{opp} ورا {me} {gap}" if k > 0 else f"{opp} قدام {me} {gap}" if k < 0 else f"{opp} و{me} بنفس النقاط")
    flag = "🇪🇬" if FOCUS in (match["home"], match["away"]) else ""
    hh, part = ar_time(match.get("koff_time"))
    comp_full, _ = edition(match)
    h, a = ar_team(match["home"]), ar_team(match["away"])
    tags = ["#الجون"] + (["#منتخب_مصر"] if FOCUS in (match["home"], match["away"]) else []) + [
        f"#{h.replace(' ', '_')}_{a.replace(' ', '_')}", "#" + "_".join(comp_full.split()[:-1])]
    dname, dd, mname = day_words(match)
    when = "" if tonight(match) in ("والليلة", "والنهارده") else f"{dname} {dd} {mname}، "
    lines = [LEAD or f"{first}… {second} ⚽{flag}",
             f"{h} × {a} — {comp_full}، {when}الساعة {hh} {part}",
             ("تابع المباراة لحظة بلحظة على الجون 👇" if OUTRO_LINES else "توقعك كام؟ اكتبه في الكومنتات 👇"),
             "https://elgoon.com",
             " ".join(tags)]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--match", required=True, help="the match_id in data/matches.json")
    ap.add_argument("--out", help="the MP4")
    ap.add_argument("--sheet", help="also write a contact sheet PNG")
    ap.add_argument("--caption", help="write the post text here (default <out>-caption.txt)")
    ap.add_argument("--png", help="write stills (one per scene) into this folder, no MP4")
    ap.add_argument("--hook", help='2-4 hook lines, "a|b[|c[|d]]"; with 4 the first two are white (default: computed)')
    ap.add_argument("--outro", help='the two closing lines, "first|second" (default: «توقعك كام؟»)')
    ap.add_argument("--lead", help="the caption's first line (default: computed)")
    ap.add_argument("--table-title", help="the line over the table, or «title|second line» (default: «المجموعة بعد N جولات»)")
    ap.add_argument("--data", help="read the match files from this folder instead of data/")
    args = ap.parse_args()
    global HOOK_LINES, OUTRO_LINES, LEAD, TABLE_TITLE
    two = lambda v, flag, most=2: (lambda p: p if 2 <= len(p) <= most and all(p) else ap.error(f'{flag} needs "first|second"'))(
        [x.strip() for x in v.split("|")])
    HOOK_LINES = two(args.hook, "--hook", 4) if args.hook else None
    OUTRO_LINES = two(args.outro, "--outro") if args.outro else None
    LEAD = args.lead.strip() if args.lead else None
    TABLE_TITLE = args.table_title.strip() if args.table_title else None
    if args.data:
        import site_lib.config as _cfg
        _cfg.DATA = os.path.abspath(args.data)
    matches = load_matches()
    match = find(matches, args.match)
    tab = table(matches, match)
    for r in tab:
        print(f"{r['pos']}. {r['team']}  P{r['played']} W{r['won']} D{r['drawn']} L{r['lost']} "
              f"{r['gf']}-{r['ga']} ({gd_text(r['gd'])}) {r['pts']} pts")
    scenes = build(tab, match)
    secs = sum(s[1] for s in scenes)
    hook, tbl, mt, outro = (s[0] for s in scenes)
    stills = [("1-hook", hook(HOOK - 0.05)), ("2-table-mid", tbl(1.0)), ("3-table", tbl(TABLE - 0.05)),
              ("4-match", mt(MATCH - 0.05)), ("5-outro", outro(OUTRO - 0.05))]
    cap = caption(tab, match)
    if args.png:
        os.makedirs(args.png, exist_ok=True)
        for name, im in stills:
            im.save(os.path.join(args.png, f"{name}.png"))
        print(f"{len(stills)} stills -> {args.png}")
        print(cap)
        return 0
    if not args.out:
        ap.error("--out or --png")
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    ok = M.encode({"id": f"group-{args.match}"}, None, args.out, secs, frame_iter=D.frames(scenes))
    if args.sheet:
        M.contact_sheet([im for _, im in stills], args.sheet, cols=len(stills))
    with open(args.caption or os.path.splitext(args.out)[0] + "-caption.txt", "w", encoding="utf-8") as fh:
        fh.write(cap)
    print(f"{args.out}: {secs:.1f}s, {'UPLOADABLE' if ok else 'NOT uploadable'}")
    print(cap)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
