# -*- coding: utf-8 -*-
"""story_events.py — news FROM THE DATA (user, 2026-11-08): «عايزك تطلع أخبار
من الداتا ... بعد انتهاء مباريات دور الـ32 إليك مواجهات دور الـ16 ... انتهاء
مباريات الدور الأول من الدوري ... حدث في مثل هذا اليوم ... وعايز أزوّد في الريلز».

Three detectors, each a pure function over the site's own data files, each
returning zero or more EVENTS - a dict with a stable `ref`, a `kind`, a
`title` and the finished Facebook `text`:

  cup_round_done   a cup round is over (every match FINISHED) and the next
                   round's pairings are in fixtures.json
                   -> «انتهى دور الـ32 من كأس مصر، إليك مواجهات دور الـ16»
  league_half_done the first half of a league is over (every club has played
                   n-1 matches) -> the top 5, the bottom 3, the top scorer
  on_this_day      a notable match of an earlier year on today's date (a
                   derby, a big score, a final) from results_archive.json /
                   matches_archive.json, or a moment in moments/*.json that
                   carries a `date` -> «في مثل هذا اليوم»

NOTHING IS WRITTEN FROM MEMORY. A fact that is not in the data files is not
written: the pairings come from fixtures.json, the table from standings.json,
the scorer from scorers.json, the old match from the archive. The wording is
the house voice: plain MSA, one fact per sentence, digits, `#الجون` plus the
competition's hashtag.

fb_post.py --events posts each event once through the store (kind = the
event's kind, ref = its ref), so the nightly dispatch can run it every night
and nothing goes out twice. --events --dry prints the texts.

The on-this-day match also becomes a MOMENT reel script (moment_reel.py):

    python story_events.py                   # dry-run every detector on today's data
    python story_events.py --moment 4804684  # write moments/<id>.json from an archived match
"""
import datetime
import glob
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from site_lib.arabic import _AR_DAYS, _AR_MONTHS            # noqa: E402
from site_lib.competitions import COMP_LABEL, COMP_SLUG     # noqa: E402
from site_lib.names import ar_team                          # noqa: E402

SITE = "https://elgoon.com"
DATA = os.path.join(HERE, "data")
MOMENTS = os.path.join(HERE, "moments")

KIND_CUP = "cup-round-done"
KIND_HALF = "league-half"
KIND_OTD = "on-this-day"
KIND_COACH = "coach-left"

# The cups whose rounds are STAGES (fixtures.json rounds carry a label such
# as «دور الـ 32»). A league cup with numbered group rounds is not one.
STAGED_CUPS = ("Egypt Cup",)
# «في مثل هذا اليوم» needs a match worth remembering. From the data only:
#   * a derby - both sides of one of these pairs (Arabic feed names, or the
#     football-data English names), in any order
#   * a big score - BIG_TOTAL goals or more
#   * a final - the stage label says so
DERBIES = (
    ("الأهلي", "الزمالك", "قمة الكرة المصرية"),
    ("Real Madrid", "Barcelona", "الكلاسيكو"),
    ("Manchester United", "Manchester City", "ديربي مانشستر"),
    ("Liverpool", "Manchester United", "كلاسيكو إنجلترا"),
    ("Liverpool", "Everton", "ديربي الميرسيسايد"),
    ("Arsenal", "Tottenham", "ديربي شمال لندن"),
    ("Internazionale", "Milan", "ديربي ميلانو"),
    ("Roma", "Lazio", "ديربي روما"),
    ("Atlético", "Real Madrid", "ديربي مدريد"),
    ("الهلال", "النصر", "ديربي الرياض"),
    ("غلطة سراي", "فنربخشة", "ديربي إسطنبول"),
)
BIG_TOTAL = 5
TOP_N, BOTTOM_N = 5, 3


# ---------------------------------------------------------------- the data
def _load(name):
    """A `results[0].items` export (matches, fixtures, standings, scorers) or
    the archive's flat list; [] when the file is missing."""
    p = os.path.join(DATA, name)
    if not os.path.exists(p):
        return []
    with io.open(p, encoding="utf-8") as f:
        doc = json.load(f)
    if isinstance(doc, dict) and isinstance(doc.get("results"), list):
        res = doc["results"]
        if res and isinstance(res[0], dict) and "items" in res[0]:
            return res[0]["items"]
        return res
    return doc if isinstance(doc, list) else []


def merge_archive(*lists):
    """One row per match_id, the FIRST list winning: results_archive.json
    carries the goals, matches_archive.json only the score."""
    seen, out = set(), []
    for rows in lists:
        for m in rows or []:
            k = str(m.get("match_id"))
            if k in seen:
                continue
            seen.add(k)
            out.append(m)
    return out


def load_data():
    return {
        "matches": _load("matches.json"),
        "fixtures": _load("fixtures.json"),
        "standings": _load("standings.json"),
        "scorers": _load("scorers.json"),
        "archive": merge_archive(_load("results_archive.json"), _load("matches_archive.json")),
        "articles": _load("articles.json"),
        "moments": load_moments(),
    }


def load_moments(folder=None):
    out = []
    for p in sorted(glob.glob(os.path.join(folder or MOMENTS, "*.json"))):
        try:
            with io.open(p, encoding="utf-8") as f:
                out.append(json.load(f))
        except (OSError, ValueError):
            continue
    return out


# ---------------------------------------------------------------- helpers
def comp_label(comp):
    return COMP_LABEL.get(comp, comp or "")


def comp_tag(comp):
    return "#" + comp_label(comp).replace(" ", "_")


def comp_url(comp, page="fixtures"):
    slug = COMP_SLUG.get(comp)
    return f"{SITE}/{page}/{slug}.html" if slug else f"{SITE}/matches"


def ar_date(d, weekday=False, year=True):
    """«الأحد 8 نوفمبر 2026» from an ISO date; the string itself when it is
    not one."""
    try:
        dt = datetime.date.fromisoformat(str(d)[:10])
    except (TypeError, ValueError):
        return str(d or "")
    s = f"{dt.day} {_AR_MONTHS[dt.month]}" + (f" {dt.year}" if year else "")
    return f"{_AR_DAYS[dt.weekday()]} {s}" if weekday else s


def season_of(date):
    """«2026-27» for a date from August to December, «2025-26» for one from
    January to July - a season label derived from the kick-off, so a ref is
    the same whichever file the match came from."""
    try:
        dt = datetime.date.fromisoformat(str(date)[:10])
    except (TypeError, ValueError):
        return "0000"
    y = dt.year if dt.month >= 8 else dt.year - 1
    return f"{y}-{str(y + 1)[2:]}"


def _finished(m):
    """A final score. An archive row carries no status, so a row with both
    scores and no status counts; a row that says LIVE / UPCOMING never."""
    st = (m.get("status") or "").upper()
    if st and st != "FINISHED":
        return False
    return m.get("home_score") is not None and m.get("away_score") is not None


def _started(m):
    return _finished(m) or (m.get("status") or "").upper() in ("LIVE", "IN_PLAY", "PAUSED")


def _round_num(label):
    """«دور الـ 32» -> 32, «دور الـ16» -> 16, anything else -> None."""
    mm = re.search(r"\d+", label or "")
    return int(mm.group()) if mm else None


def round_name(label):
    """The stage as the post names it: «دور الـ32» (no space before the
    number, the way the user wrote it), the label itself otherwise."""
    n = _round_num(label)
    if n and "دور" in (label or ""):
        return f"دور الـ{n}"
    return (label or "").strip()


def _side_names(m):
    return ar_team(m.get("home") or ""), ar_team(m.get("away") or "")


def derby_of(m):
    """The derby's Arabic name when the match is one of DERBIES, else None."""
    h, a = (m.get("home") or ""), (m.get("away") or "")
    for x, y, name in DERBIES:
        if (x in h and y in a) or (y in h and x in a):
            return name
    return None


# ---------------------------------------------------------------- (a) a cup round is complete
def cup_round_done(matches, fixtures, cups=STAGED_CUPS):
    """One event per staged cup whose round «دور الـN» is fully FINISHED
    while the next numbered round's pairings are already in fixtures.json
    and none of them has kicked off (a round that has started is not news).
    The preliminary round («تصفيات») is not a numbered round and never
    fires. matches.json is the fresher file, so a match's status there wins."""
    fresh = {str(m.get("match_id")): m for m in matches or []}
    events = []
    for fx in fixtures or []:
        comp = fx.get("competition")
        if comp not in cups:
            continue
        rounds = sorted((r for r in fx.get("rounds") or [] if r.get("matches")),
                        key=lambda r: r.get("round") or 0)
        for i, rd in enumerate(rounds[:-1]):
            nxt = rounds[i + 1]
            if not _round_num(rd.get("label")) or not _round_num(nxt.get("label")):
                continue
            ms = [fresh.get(str(m.get("match_id")), m) for m in rd["matches"]]
            if not ms or not all(_finished(m) for m in ms):
                continue
            pairs = [fresh.get(str(m.get("match_id")), m) for m in nxt["matches"]
                     if (m.get("home") or "").strip() and (m.get("away") or "").strip()]
            if not pairs or any(_started(m) for m in pairs):
                continue
            done_lbl, next_lbl = round_name(rd.get("label")), round_name(nxt.get("label"))
            season = season_of(min(m.get("kickoff") or "9999" for m in ms))
            ref = f"{comp}:R{_round_num(rd.get('label')) or rd.get('round')}:{season}"
            events.append({
                "kind": KIND_CUP, "ref": ref,
                "title": f"انتهى {done_lbl} من {comp_label(comp)}",
                "text": cup_round_text(comp, done_lbl, next_lbl, pairs),
                "pairs": pairs,
            })
    return events


def cup_round_text(comp, done_lbl, next_lbl, pairs):
    label = comp_label(comp)
    lines = [f"🏆 انتهى {done_lbl} من {label}.",
             f"هذه مواجهات {next_lbl}:"]
    for m in sorted(pairs, key=lambda m: ((m.get("kickoff") or "9999"), m.get("koff_time") or "")):
        h, a = _side_names(m)
        when = ""
        if m.get("kickoff"):
            when = " — " + ar_date(m["kickoff"], weekday=True, year=False)
            if m.get("koff_time"):
                when += f" {m['koff_time']}"
        lines.append(f"• {h} × {a}{when}")
    lines.append(f"المواعيد كاملة: {comp_url(comp)}")
    lines.append(f"#الجون {comp_tag(comp)}")
    return "\n".join(lines)


# ---------------------------------------------------------------- (b) the first half of a league
def league_half_done(standings, scorers, today=None):
    """One event per league whose every club has played n-1 matches (n
    clubs) - the first half. A club may already be one match into the
    second half (the calendar is never clean); more than that and the
    moment has passed, so nothing is posted late."""
    events = []
    today = today or datetime.date.today()
    scorers_by = {s.get("competition"): s.get("scorers") or [] for s in scorers or []}
    for st in standings or []:
        comp, table = st.get("competition"), st.get("table") or []
        if st.get("zeroed") or len(table) < 4:
            continue
        n = len(table)
        played = [int(r.get("played") or 0) for r in table]
        half = n - 1
        if min(played) < half or max(played) > half + 1:
            continue
        season = (st.get("season_label") or "").replace("/", "-") or season_of(today.isoformat())
        events.append({
            "kind": KIND_HALF, "ref": f"{comp}:{season}",
            "title": f"انتهى الدور الأول من {comp_label(comp)}",
            "text": league_half_text(comp, table, scorers_by.get(comp) or []),
        })
    return events


def league_half_text(comp, table, scorers):
    label = comp_label(comp)
    rows = sorted(table, key=lambda r: int(r.get("pos") or 0))
    lines = [f"📊 انتهى الدور الأول من {label}.",
             f"الخماسي الأول بعد {len(rows) - 1} جولة:"]
    for r in rows[:TOP_N]:
        lines.append(f"{r.get('pos')}. {ar_team(r.get('team'))} — {r.get('pts')} نقطة")
    lines.append("المراكز الأخيرة:")
    for r in rows[-BOTTOM_N:]:
        lines.append(f"{r.get('pos')}. {ar_team(r.get('team'))} — {r.get('pts')} نقطة")
    top = scorers[0] if scorers else None
    if top and top.get("name") and (top.get("goals") or top.get("value")):
        g = top.get("goals") or top.get("value")
        lines.append(f"⚽ الهداف: {top['name']} ({ar_team(top.get('team'))}) — {g} أهداف" if int(g) > 2
                     else f"⚽ الهداف: {top['name']} ({ar_team(top.get('team'))}) — {g} هدف")
    lines.append(f"الجدول كاملًا: {comp_url(comp, 'standings')}")
    lines.append(f"#الجون {comp_tag(comp)}")
    return "\n".join(lines)


# ---------------------------------------------------------------- (c) on this day
def notable(m):
    """Why the match is worth a post: ('derby', name) / ('final', label) /
    ('big', total goals) / None. Data only."""
    if not _finished(m):
        return None
    d = derby_of(m)
    if d:
        return ("derby", d)
    stage = (m.get("stage") or m.get("label") or "")
    if "نهائي" in stage and "نصف" not in stage and "ربع" not in stage:
        return ("final", stage)
    total = int(m.get("home_score") or 0) + int(m.get("away_score") or 0)
    if total >= BIG_TOTAL:
        return ("big", total)
    return None


def on_this_day(archive, moments, today=None):
    """At most one event for today's date: the best notable archived match
    of an EARLIER year, else a moment in moments/*.json whose `date` falls
    on this day. ref = on-this-day:<YYYY-MM-DD> of today, so each year's
    post is its own and a second run the same night is a no-op."""
    today = today or datetime.date.today()
    md = today.strftime("%m-%d")
    ref = f"{today.isoformat()}"
    best = None
    for m in archive or []:
        k = str(m.get("kickoff") or "")[:10]
        if len(k) != 10 or k[5:] != md or int(k[:4]) >= today.year:
            continue
        why = notable(m)
        if not why:
            continue
        score = {"derby": 3, "final": 2, "big": 1}[why[0]] * 100 + int(m.get("home_score") or 0) + int(m.get("away_score") or 0)
        if best is None or score > best[0]:
            best = (score, m, why)
    if best:
        _, m, why = best
        years = today.year - int(str(m["kickoff"])[:4])
        return [{"kind": KIND_OTD, "ref": ref, "title": f"في مثل هذا اليوم: {ar_team(m['home'])} {m['home_score']}-{m['away_score']} {ar_team(m['away'])}",
                 "text": otd_match_text(m, why, years), "match": m}]
    for mo in moments or []:
        d = str(mo.get("date") or "")[:10]
        if len(d) == 10 and d[5:] == md and int(d[:4]) < today.year and mo.get("otd_lines"):
            years = today.year - int(d[:4])
            return [{"kind": KIND_OTD, "ref": ref, "title": f"في مثل هذا اليوم: {mo.get('title') or mo['id']}",
                     "text": otd_moment_text(mo, years), "moment": mo["id"]}]
    return []


def _years_ago(n):
    if n == 1:
        return "قبل عام"
    if n == 2:
        return "قبل عامين"
    return f"قبل {n} أعوام" if n <= 10 else f"قبل {n} عامًا"


def otd_match_text(m, why, years):
    h, a = _side_names(m)
    lines = [f"📅 في مثل هذا اليوم {_years_ago(years)}، {ar_date(m['kickoff'])}:",
             f"{h} {m['home_score']} - {m['away_score']} {a} في {comp_label(m.get('competition'))}."]
    if why[0] == "derby":
        lines.append(f"المباراة هي {why[1]}.")
    elif why[0] == "final":
        lines.append(f"المباراة كانت {why[1]}.")
    else:
        lines.append(f"المباراة شهدت {why[1]} أهداف.")
    goals = [g for g in (m.get("goals") or []) if g.get("player")]
    if goals:
        by = {"h": [], "a": []}
        for g in goals:
            by.setdefault(g.get("side") or "h", by["h"]).append(
                f"{g['player'].strip()} {g['minute']}'" if g.get("minute") else g["player"].strip())
        if by["h"]:
            lines.append(f"أهداف {h}: " + "، ".join(by["h"]) + ".")
        if by["a"]:
            lines.append(f"أهداف {a}: " + "، ".join(by["a"]) + ".")
    lines.append(f"تفاصيل المباراة: {SITE}/m/{m['match_id']}")
    lines.append(f"#الجون {comp_tag(m.get('competition'))}")
    return "\n".join(lines)


def otd_moment_text(mo, years):
    lines = [f"📅 في مثل هذا اليوم {_years_ago(years)}، {ar_date(mo['date'])}:"]
    lines += [ln.strip() for ln in mo.get("otd_lines") or [] if ln.strip()]
    lines.append(f"الريل كامل على صفحتنا. {SITE}")
    lines.append("#الجون " + " ".join(t for t in (mo.get("hashtags") or []) if t.startswith("#")))
    return "\n".join(ln.rstrip() for ln in lines)


# ---------------------------------------------------------------- (d) a coach leaves the national team
# User, 2026-11-08 (second example): «خبر ان حسام حسن مشى من تدريب المنتخب،
# نعمل بوست عن ارقامه مع المنتخب». The trigger is one of OUR articles (the
# writer already checked two sources); the numbers are the national team's
# matches in the archive - and only those. The archive began in August 2026,
# so the post says which window the numbers cover instead of pretending to
# be a career record.
COACH_LEFT_RE = (
    re.compile(r"^(?P<name>[^.،:]{3,40}?)\s+(?:يرحل|يغادر|يستقيل)\s+(?:عن|من)\s+تدريب\s+(?P<team>منتخب مصر)"),
    re.compile(r"(?:رحيل|إقالة|استقالة)\s+(?P<name>[^.،:]{3,40}?)\s+(?:عن|من)\s+تدريب\s+(?P<team>منتخب مصر)"),
    re.compile(r"(?:إنهاء|ينهي)\s+(?:مهمة|عقد)\s+(?P<name>[^.،:]{3,40}?)\s+(?:مع|من)\s+(?P<team>منتخب مصر)"),
)
NT_NAME = "مصر"
COACH_MAX_AGE_D = 2


def coach_left(articles, archive, today=None):
    today = today or datetime.date.today()
    cut = (today - datetime.timedelta(days=COACH_MAX_AGE_D)).isoformat()
    events = []
    for a in articles or []:
        title = (a.get("title") or "").strip()
        if (a.get("pub_date") or "") < cut:
            continue
        hit = next((rx.search(title) for rx in COACH_LEFT_RE if rx.search(title)), None)
        if not hit:
            continue
        name = hit.group("name").strip()
        ms = sorted((m for m in archive or []
                     if NT_NAME in ((m.get("home") or "").strip(), (m.get("away") or "").strip())
                     and _finished(m) and str(m.get("kickoff") or "")[:10] <= (a.get("pub_date") or "")),
                    key=lambda m: m.get("kickoff") or "")
        if not ms:
            continue
        events.append({"kind": KIND_COACH, "ref": str(a.get("article_id")),
                       "title": f"أرقام {name} مع {hit.group('team')}",
                       "text": coach_record_text(name, hit.group("team"), ms, a), "matches": ms})
    return events


def nt_record(ms):
    w = d = l = gf = ga = 0
    best = None
    for m in ms:
        home = (m.get("home") or "").strip() == NT_NAME
        f, ag = (m["home_score"], m["away_score"]) if home else (m["away_score"], m["home_score"])
        gf, ga = gf + int(f), ga + int(ag)
        if f > ag:
            w += 1
            if best is None or int(f) - int(ag) > best[0]:
                best = (int(f) - int(ag), m)
        elif f == ag:
            d += 1
        else:
            l += 1
    return {"p": len(ms), "w": w, "d": d, "l": l, "gf": gf, "ga": ga, "best": best[1] if best else None}


def _n(n, one, two, many):
    """«مباراة واحدة» / «مباراتان» / «3 مباريات» / «11 مباراة»."""
    if n == 1:
        return one
    if n == 2:
        return two
    return f"{n} {many}" if 3 <= n <= 10 else f"{n} {one.split()[0]}"


def coach_record_text(name, team, ms, art):
    r = nt_record(ms)
    lines = [f"📊 {name} يرحل عن تدريب {team}.",
             f"أرقامه في المباريات التي تغطيها بيانات الجون (منذ {ar_date(ms[0]['kickoff'])}):",
             f"{_n(r['p'], 'مباراة واحدة', 'مباراتان', 'مباريات')}: فوز {r['w']}، تعادل {r['d']}، خسارة {r['l']}.",
             f"الأهداف: {r['gf']} له، {r['ga']} عليه."]
    b = r["best"]
    if b:
        lines.append(f"أكبر فوز: {ar_team(b['home'])} {b['home_score']} - {b['away_score']} {ar_team(b['away'])} ({ar_date(b['kickoff'])}).")
    lines.append(f"الخبر كاملًا: {SITE}/a/{art.get('article_id')}")
    lines.append("#الجون #منتخب_مصر")
    return "\n".join(lines)


# ---------------------------------------------------------------- a MOMENT reel from an archived match
def _running_scores(goals):
    hs = as_ = 0
    out = []
    for g in goals:
        if (g.get("side") or "h") == "a":
            as_ += 1
        else:
            hs += 1
        out.append((g, hs, as_))
    return out


def moment_script(m, mid=None):
    """A moment_reel.py script from ONE archived match with its goals - the
    scenes say only what the row says (date, competition, sides, goals,
    final score). None when the match has no scorer data (a reel of a
    score alone says nothing). Passes moment_reel.validate: 6-8 scenes,
    14-17.5 s, lines of six words or fewer, no photo."""
    goals = [g for g in (m.get("goals") or []) if g.get("player")]
    if not _finished(m) or not goals:
        return None
    h, a = _side_names(m)
    comp = comp_label(m.get("competition"))
    why = notable(m)
    hook_lines = [f"{h} × {a}", why[1] if why and why[0] == "derby" else comp]
    runs = _running_scores(goals)
    picked = runs if len(runs) <= 3 else [runs[0]] + runs[-2:]
    scenes = [
        {"kind": "hook", "secs": 2.5, "big": f"{m['home_score']}-{m['away_score']}", "lines": hook_lines},
        {"kind": "date", "secs": 2.0, "lines": [ar_date(m["kickoff"]), comp]},
        {"kind": "teams", "secs": 2.0, "lines": [f"{h} × {a}", comp]},
    ]
    for i, (g, hs, as_) in enumerate(picked):
        side = "a" if (g.get("side") or "h") == "a" else "h"
        last = i == len(picked) - 1
        who = g["player"].strip()
        lines = [f"الدقيقة {g['minute']}" if g.get("minute") else "هدف", f"{who} يسجّل"]
        if (g.get("tag") or "") == "ج":
            lines[1] = f"{who} من ركلة جزاء"
        scenes.append({"kind": "climax" if last else "goal", "secs": 2.5 if last else 2.0,
                       "lines": lines, "score": [hs, as_], "crest": "home" if side == "h" else "away",
                       **({"shake": True} if last else {})})
    scenes.append({"kind": "finale", "secs": 3.0, "big": f"{m['home_score']}-{m['away_score']}",
                   "lines": [f"{h} × {a}", ar_date(m["kickoff"])]})
    scenes.append({"kind": "cta", "secs": 1.5, "lines": ["فاكر المباراة دي؟", "تابع الجون"]})
    mid = mid or f"m{m['match_id']}-{str(m['kickoff'])[:10]}"
    why_line = {"derby": f"{why[1]}.", "final": f"{why[1]}.", "big": f"{why[1]} أهداف في مباراة واحدة."}.get(why[0]) if why else ""
    caption = "\n".join(x for x in [
        f"{h} {m['home_score']}-{m['away_score']} {a} — {ar_date(m['kickoff'])}.",
        why_line, f"{comp}.", f"تفاصيل المباراة: {SITE}/m/{m['match_id']}",
        f"#الجون {comp_tag(m.get('competition'))} #{h.replace(' ', '_')} #{a.replace(' ', '_')}"] if x)
    return {
        "id": mid,
        "title": f"{h} {m['home_score']}-{m['away_score']} {a} — {ar_date(m['kickoff'])}",
        "date": str(m["kickoff"])[:10],
        "facts": f"From data/results_archive.json match {m['match_id']}: {m.get('home')} {m['home_score']}-{m['away_score']} "
                 f"{m.get('away')}, {m['kickoff']}, {m.get('competition')}; goals as recorded there.",
        "home": {"name": h, "url": m.get("home_badge") or ""},
        "away": {"name": a, "url": m.get("away_badge") or ""},
        "scenes": scenes,
        "music_dip": [sum(float(s["secs"]) for s in scenes[:-3]), sum(float(s["secs"]) for s in scenes[:-2])],
        "caption": caption,
        "otd_lines": [f"{h} {m['home_score']} - {m['away_score']} {a} في {comp}."] + ([why_line] if why_line else []),
        "hashtags": [comp_tag(m.get("competition"))],
    }


# ---------------------------------------------------------------- all of it
def detect(data=None, today=None):
    """Every event on today's data, in posting order."""
    d = data or load_data()
    return (cup_round_done(d.get("matches"), d.get("fixtures"))
            + league_half_done(d.get("standings"), d.get("scorers"), today)
            + coach_left(d.get("articles"), d.get("archive"), today)
            + on_this_day(d.get("archive"), d.get("moments"), today))


def _find_match(mid, data):
    for m in data.get("archive") or []:
        if str(m.get("match_id")) == str(mid):
            return m
    return None


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    data = load_data()
    if "--moment" in argv:
        mid = argv[argv.index("--moment") + 1]
        m = _find_match(mid, data)
        if not m:
            print(f"match {mid} is not in the archive"); return 1
        script = moment_script(m, mid=argv[argv.index("--id") + 1] if "--id" in argv else None)
        if not script:
            print(f"match {mid} has no scorer data - no reel"); return 1
        out = os.path.join(MOMENTS, f"{script['id']}.json")
        with io.open(out, "w", encoding="utf-8", newline="\n") as f:
            json.dump(script, f, ensure_ascii=False, indent=2); f.write("\n")
        print(f"wrote {out} ({len(script['scenes'])} scenes, {sum(s['secs'] for s in script['scenes']):.1f} s)")
        print(script["caption"])
        return 0
    today = datetime.date.fromisoformat(argv[argv.index("--date") + 1]) if "--date" in argv else None
    evs = detect(data, today)
    print(f"story_events ({(today or datetime.date.today()).isoformat()}): {len(evs)} event(s)")
    for ev in evs:
        print(f"\n== {ev['kind']} / {ev['ref']}\n{ev['text']}")
    if "--why" in argv or not evs:
        # say WHY, so a dry-run on a quiet day is still a report
        for fx in data["fixtures"]:
            if fx.get("competition") in STAGED_CUPS:
                for rd in fx.get("rounds") or []:
                    ms = rd.get("matches") or []
                    fin = sum(1 for m in ms if _finished(m))
                    print(f"  {fx['competition']} {rd.get('label') or rd.get('round')}: {fin}/{len(ms)} finished")
        for st in data["standings"]:
            t = st.get("table") or []
            if t and not st.get("zeroed"):
                pl = [int(r.get("played") or 0) for r in t]
                print(f"  {st['competition']}: {len(t)} clubs, played {min(pl)}-{max(pl)} of {len(t) - 1} first-half rounds")
        nt = [m for m in data["archive"] if NT_NAME in ((m.get("home") or "").strip(), (m.get("away") or "").strip()) and _finished(m)]
        print(f"  coach-left: {len(nt)} finished {NT_NAME} match(es) in the archive"
              + (f" ({min(m['kickoff'] for m in nt)} .. {max(m['kickoff'] for m in nt)})" if nt else ""))
        print(f"  on-this-day: no notable match of an earlier year on {(today or datetime.date.today()).strftime('%m-%d')} "
              f"in {len(data['archive'])} archived rows, no dated moment")
    return 0


if __name__ == "__main__":
    sys.exit(main())
