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


# ---------------------------------------------------------------- the event shape
# One shape for every kind, so the same event can drive a Facebook post now
# and a short site article / the daily-article prompt later (the user,
# 2026-11-08: «أنا عايزك على طول تعمل أخبار بالشكل ده، يبقى إحنا بقى عندنا
# أخبار خاصة بينا» - a permanent editorial line, not a one-off):
#   kind, ref        the store key (posted exactly once)
#   title            one line, Arabic
#   competition      the raw competition name (COMP_LABEL has the Arabic)
#   lines            the facts, one per line, in posting order
#   link, link_label the page the post points at
#   tags             hashtags after #الجون
#   + the structured data the kind is made of: pairs / table / scorer / match /
#     record / article / moment - what an article writer needs, untouched
#   text             the finished post, render()ed from the above
def event(kind, ref, title, lines, link, link_label, tags, competition=None, **data):
    ev = {"kind": kind, "ref": ref, "title": title, "competition": competition,
          "lines": list(lines), "link": link, "link_label": link_label,
          "tags": [t for t in tags if t], **data}
    ev["text"] = render(ev)
    return ev


def render(ev):
    """The post: the fact lines, the link line, then «#الجون» + the tags."""
    out = list(ev.get("lines") or [])
    if ev.get("link"):
        out.append(f"{ev.get('link_label') or 'التفاصيل'}: {ev['link']}")
    out.append(" ".join(["#الجون"] + list(ev.get("tags") or [])).rstrip())
    return "\n".join(out)


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
            pairs = sorted(pairs, key=lambda m: ((m.get("kickoff") or "9999"), m.get("koff_time") or ""))
            events.append(event(
                KIND_CUP, ref, f"انتهى {done_lbl} من {comp_label(comp)}، إليك مواجهات {next_lbl}",
                cup_round_lines(comp, done_lbl, next_lbl, pairs),
                comp_url(comp), "المواعيد كاملة", [comp_tag(comp)], competition=comp,
                round_done=done_lbl, round_next=next_lbl, season=season,
                pairs=[{"match_id": m.get("match_id"), "home": ar_team(m.get("home")), "away": ar_team(m.get("away")),
                        "kickoff": m.get("kickoff"), "koff_time": m.get("koff_time")} for m in pairs]))
    return events


def cup_round_lines(comp, done_lbl, next_lbl, pairs):
    lines = [f"🏆 انتهى {done_lbl} من {comp_label(comp)}.",
             f"هذه مواجهات {next_lbl}:"]
    for m in pairs:
        h, a = _side_names(m)
        when = ""
        if m.get("kickoff"):
            when = " — " + ar_date(m["kickoff"], weekday=True, year=False)
            if m.get("koff_time"):
                when += f" {m['koff_time']}"
        lines.append(f"• {h} × {a}{when}")
    return lines


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
        rows = sorted(table, key=lambda r: int(r.get("pos") or 0))
        top = (scorers_by.get(comp) or [None])[0]
        scorer = ({"name": top["name"], "team": ar_team(top.get("team")), "goals": int(top.get("goals") or top.get("value"))}
                  if top and top.get("name") and (top.get("goals") or top.get("value")) else None)
        row = lambda r: {"pos": r.get("pos"), "team": ar_team(r.get("team")), "played": r.get("played"), "pts": r.get("pts"),
                         "won": r.get("won"), "draw": r.get("draw"), "lost": r.get("lost"), "gf": r.get("gf"), "ga": r.get("ga")}
        events.append(event(
            KIND_HALF, f"{comp}:{season}", f"انتهى الدور الأول من {comp_label(comp)}",
            league_half_lines(comp, rows, scorer), comp_url(comp, "standings"), "الجدول كاملًا",
            [comp_tag(comp)], competition=comp, season=season, rounds=n - 1,
            table={"top": [row(r) for r in rows[:TOP_N]], "bottom": [row(r) for r in rows[-BOTTOM_N:]]},
            scorer=scorer))
    return events


def league_half_lines(comp, rows, scorer):
    lines = [f"📊 انتهى الدور الأول من {comp_label(comp)}.",
             f"الخماسي الأول بعد {len(rows) - 1} جولة:"]
    for r in rows[:TOP_N]:
        lines.append(f"{r.get('pos')}. {ar_team(r.get('team'))} — {r.get('pts')} نقطة")
    lines.append("المراكز الأخيرة:")
    for r in rows[-BOTTOM_N:]:
        lines.append(f"{r.get('pos')}. {ar_team(r.get('team'))} — {r.get('pts')} نقطة")
    if scorer:
        g = scorer["goals"]
        lines.append(f"⚽ الهداف: {scorer['name']} ({scorer['team']}) — {g} " + ("أهداف" if g > 2 else "هدف"))
    return lines


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
        return [event(KIND_OTD, ref, f"في مثل هذا اليوم: {ar_team(m['home'])} {m['home_score']}-{m['away_score']} {ar_team(m['away'])}",
                      otd_match_lines(m, why, years), f"{SITE}/m/{m['match_id']}", "تفاصيل المباراة",
                      [comp_tag(m.get("competition"))], competition=m.get("competition"),
                      match=m, why=why[0], why_label=str(why[1]), years_ago=years)]
    for mo in moments or []:
        d = str(mo.get("date") or "")[:10]
        if len(d) == 10 and d[5:] == md and int(d[:4]) < today.year and mo.get("otd_lines"):
            years = today.year - int(d[:4])
            return [event(KIND_OTD, ref, f"في مثل هذا اليوم: {mo.get('title') or mo['id']}",
                          otd_moment_lines(mo, years), SITE, "الريل كامل على صفحتنا",
                          [t for t in (mo.get("hashtags") or []) if t.startswith("#")],
                          moment=mo["id"], years_ago=years)]
    return []


def _years_ago(n):
    if n == 1:
        return "قبل عام"
    if n == 2:
        return "قبل عامين"
    return f"قبل {n} أعوام" if n <= 10 else f"قبل {n} عامًا"


def otd_match_lines(m, why, years):
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
    return lines


def otd_moment_lines(mo, years):
    lines = [f"📅 في مثل هذا اليوم {_years_ago(years)}، {ar_date(mo['date'])}:"]
    lines += [ln.strip() for ln in mo.get("otd_lines") or [] if ln.strip()]
    return lines


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
        r = nt_record(ms)
        events.append(event(KIND_COACH, str(a.get("article_id")), f"أرقام {name} مع {hit.group('team')}",
                            coach_record_lines(name, hit.group("team"), ms, r), f"{SITE}/a/{a.get('article_id')}",
                            "الخبر كاملًا", ["#منتخب_مصر"], competition=None, coach=name, team=hit.group("team"),
                            article={"article_id": a.get("article_id"), "title": title, "pub_date": a.get("pub_date")},
                            record={k: v for k, v in r.items() if k != "best"}, best=r["best"],
                            since=ms[0]["kickoff"], matches=ms))
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


def coach_record_lines(name, team, ms, r):
    lines = [f"📊 {name} يرحل عن تدريب {team}.",
             f"أرقامه في المباريات التي تغطيها بيانات الجون (منذ {ar_date(ms[0]['kickoff'])}):",
             f"{_n(r['p'], 'مباراة واحدة', 'مباراتان', 'مباريات')}: فوز {r['w']}، تعادل {r['d']}، خسارة {r['l']}.",
             f"الأهداف: {r['gf']} له، {r['ga']} عليه."]
    b = r["best"]
    if b:
        lines.append(f"أكبر فوز: {ar_team(b['home'])} {b['home_score']} - {b['away_score']} {ar_team(b['away'])} ({ar_date(b['kickoff'])}).")
    return lines


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


# ---------------------------------------------------------------- (e) a club's form before its next match
# User, 2026-11-09 (third example, an image from another page): a club's last
# twelve results as ✅/❌ marks with the next fixture under them - «برشلونة
# يدخل مواجهة فياريال بـ11 انتصارًا في آخر 12 مباراة». Two triggers, both
# from the data files only (the archive + matches.json for the results,
# matches.json + fixtures.json for the fixture):
#   club-form    a curated club (TEAM_PAGES = the ticker clubs with a page)
#                plays within FORM_WINDOW_H hours -> its last FORM_N finished
#                matches across competitions, W/D/L marks, goals, the run it
#                is on, the fixture. ref form:<slug>:<match_id>, so the post
#                goes out once before that match.
#   club-streak  a milestone the last match completed - STREAK_WIN wins in a
#                row, STREAK_WINLESS without a win, or the first defeat after
#                STREAK_WIN wins - with no fixture inside the window (the form
#                post would say it anyway). ref streak:<slug>:<last match_id>.
#                Only while the last match is STREAK_MAX_AGE_D days old at
#                most: a streak is news the night it happens, never later.
# The card (form_card.py) and the reel (form_reel.py) draw the same rows.
KIND_FORM = "club-form"
KIND_STREAK = "club-streak"
FORM_N, FORM_MAX, FORM_MIN = 8, 10, 5
FORM_WINDOW_H = 24
STREAK_WIN, STREAK_WINLESS = 5, 5
STREAK_MAX_AGE_D = 2
MARKS = {"W": "✅", "D": "➖", "L": "❌"}
CAIRO_TZ = "Africa/Cairo"


def form_clubs():
    from site_lib.clubs import TEAM_PAGES
    return TEAM_PAGES


def club_side(tp, m):
    """'h' / 'a' when the club plays in m (the ticker's token + scope rule:
    a Latin token is a substring, an Arabic one an exact name), else None."""
    from site_lib.names import _in_scope
    comp = m.get("competition") or ""
    for t, c in tp["match_tokens"]:
        if not _in_scope(c, comp):
            continue
        arabic = any("؀" <= ch <= "ۿ" for ch in t)
        for side in ("h", "a"):
            name = (m.get("home" if side == "h" else "away") or "").strip()
            if (t == name) if arabic else (t in name):
                return side
    return None


def results_pool(matches, archive):
    """Every finished match we hold, one row per match_id - matches.json
    first (its status is the freshest), then the archive."""
    fin = [m for m in matches or [] if _finished(m)]
    return merge_archive(fin, [m for m in archive or [] if _finished(m)])


def club_results(tp, pool):
    """The club's finished matches, oldest first."""
    out = [m for m in pool if club_side(tp, m)]
    out.sort(key=lambda m: (str(m.get("kickoff") or ""), m.get("koff_time") or ""))
    return out


def form_row(tp, m):
    """One result as the card prints it: the opponent, the club's goals
    first, the mark."""
    side = club_side(tp, m)
    hs, as_ = int(m["home_score"]), int(m["away_score"])
    gf, ga = (hs, as_) if side == "h" else (as_, hs)
    opp_raw = m.get("away") if side == "h" else m.get("home")
    return {"match_id": m.get("match_id"), "date": str(m.get("kickoff") or "")[:10],
            "competition": m.get("competition"), "comp_label": comp_label(m.get("competition")),
            "opponent": ar_team(opp_raw or ""), "opponent_badge": m.get("away_badge" if side == "h" else "home_badge"),
            "club_badge": m.get("home_badge" if side == "h" else "away_badge"),
            "home": side == "h", "gf": gf, "ga": ga,
            "mark": "W" if gf > ga else "D" if gf == ga else "L"}


def form_summary(rows, all_rows=None):
    """Wins / draws / losses / goals of the rows, the current run (the mark
    of the last match and how many in a row ended with it), the winless and
    unbeaten runs. The runs are counted over `all_rows` (every result we
    hold) when given: a club on 10 wins must not read «8 انتصارات متتالية»
    because the card shows eight rows. The archive began in August 2026, so
    a run that reaches its first row is the longest the data can vouch for."""
    marks = [r["mark"] for r in rows]
    s = {"p": len(rows), "w": marks.count("W"), "d": marks.count("D"), "l": marks.count("L"),
         "gf": sum(r["gf"] for r in rows), "ga": sum(r["ga"] for r in rows)}
    runs = [r["mark"] for r in (all_rows if all_rows is not None else rows)]
    def run(pred):
        n = 0
        for mk in reversed(runs):
            if not pred(mk):
                break
            n += 1
        return n
    s["run"] = (runs[-1], run(lambda mk: mk == runs[-1])) if runs else (None, 0)
    s["winless"] = run(lambda mk: mk != "W")
    s["unbeaten"] = run(lambda mk: mk != "L")
    return s


def _wins(n):
    """«انتصار واحد» / «انتصارين» / «5 انتصارات» / «11 انتصارًا» - the
    genitive after «بـ» and «آخر»."""
    return {1: "انتصار واحد", 2: "انتصارين"}.get(n) or (f"{n} انتصارات" if n <= 10 else f"{n} انتصارًا")


def _matches(n):
    return {1: "مباراة واحدة", 2: "مباراتين"}.get(n) or (f"{n} مباريات" if n <= 10 else f"{n} مباراة")


def _in_a_row(n):
    return {2: "متتاليين"}.get(n) or ("متتالية" if n <= 10 else "متتاليًا")


def _bi(phrase):
    """«بـ5 انتصارات» before a digit, «بانتصار واحد» before a letter."""
    return ("بـ" if phrase[:1].isdigit() else "ب") + phrase


def form_headline(club, opp, s):
    """The one line: the REAL run first (wins in a row, or no win in N), else
    the wins in the window. Digits, nothing added."""
    mk, n = s["run"]
    if mk == "W" and n >= 2:
        tail = f"{_bi(_wins(n))} {_in_a_row(n)}"
    elif s["winless"] >= 3:
        tail = f"بلا فوز في آخر {_matches(s['winless'])}"
    else:
        tail = f"{_bi(_wins(s['w']))} في آخر {_matches(s['p'])}" if s["w"] else f"بلا فوز في آخر {_matches(s['p'])}"
    return f"{club} يدخل مواجهة {opp} {tail}"


def _kick_dt(m):
    """The kick-off as a Cairo datetime (koff_time is Cairo in every file);
    noon when the file has no time. None without a date."""
    from zoneinfo import ZoneInfo
    try:
        dd = datetime.date.fromisoformat(str(m.get("kickoff") or "")[:10])
        hh, mm = (int(x) for x in (m.get("koff_time") or "12:00").split(":")[:2])
    except (TypeError, ValueError):
        return None
    return datetime.datetime(dd.year, dd.month, dd.day, hh, mm, tzinfo=ZoneInfo(CAIRO_TZ))


def _now(today=None):
    """detect() hands the detectors a DATE (tests, --date): that day from
    midnight Cairo. The nightly run hands None: the Cairo clock."""
    from zoneinfo import ZoneInfo
    if today is None:
        return datetime.datetime.now(ZoneInfo(CAIRO_TZ))
    if isinstance(today, datetime.datetime):
        return today if today.tzinfo else today.replace(tzinfo=ZoneInfo(CAIRO_TZ))
    return datetime.datetime(today.year, today.month, today.day, tzinfo=ZoneInfo(CAIRO_TZ))


def upcoming_pool(matches, fixtures):
    """Every match not yet played, one row per match_id, matches.json first."""
    rows = [m for f in fixtures or [] for rd in f.get("rounds") or [] for m in rd.get("matches") or []]
    pool = merge_archive(matches or [], rows)
    return [m for m in pool if not _started(m)
            and (m.get("status") or "UPCOMING").upper() not in ("POSTPONED", "CANCELLED", "SUSPENDED")]


def next_fixture(tp, pool, now, hours=FORM_WINDOW_H):
    """The club's first match kicking off within `hours` of now, or None."""
    best = None
    for m in pool:
        if not club_side(tp, m):
            continue
        k = _kick_dt(m)
        if not k or k < now or k > now + datetime.timedelta(hours=hours):
            continue
        if best is None or k < _kick_dt(best):
            best = m
    return best


def _club_tag(name):
    return "#" + (name or "").strip().replace(" ", "_")


def form_lines(tp, s, nxt, rows):
    h, a = _side_names(nxt)
    opp = a if club_side(tp, nxt) == "h" else h
    k = _kick_dt(nxt)
    when = ar_date(nxt.get("kickoff"), weekday=True, year=False) + (f" الساعة {k:%H:%M} بتوقيت القاهرة" if nxt.get("koff_time") else "")
    return [f"📊 {form_headline(tp['name'], opp, s)}.",
            f"آخر {_matches(s['p'])}: فوز {s['w']}، تعادل {s['d']}، خسارة {s['l']}.",
            f"الأهداف: {s['gf']} له، {s['ga']} عليه.",
            f"{comp_label(nxt.get('competition'))}: {h} × {a}، {when}."]


def club_form_before_match(matches, fixtures, archive, today=None, n=FORM_N, hours=FORM_WINDOW_H):
    """One event per curated club whose next match kicks off within `hours`
    (the fixture's own kick-off, Cairo) and that has FORM_MIN finished
    matches on record: its last `n` (FORM_MAX at most) as rows."""
    n = max(1, min(int(n or FORM_N), FORM_MAX))
    now = _now(today)
    pool, up = results_pool(matches, archive), upcoming_pool(matches, fixtures)
    events = []
    for tp in form_clubs():
        nxt = next_fixture(tp, up, now, hours)
        if not nxt:
            continue
        res = club_results(tp, pool)
        if len(res) < FORM_MIN:
            continue
        rows = [form_row(tp, m) for m in res[-n:]]
        s = form_summary(rows, [form_row(tp, m) for m in res])
        h, a = _side_names(nxt)
        opp = a if club_side(tp, nxt) == "h" else h
        events.append(event(
            KIND_FORM, f"form:{tp['slug']}:{nxt.get('match_id')}", form_headline(tp["name"], opp, s),
            form_lines(tp, s, nxt, rows), f"{SITE}/m/{nxt.get('match_id')}", "تفاصيل المباراة",
            [_club_tag(tp["name"]), _club_tag(opp)], competition=nxt.get("competition"),
            club={"slug": tp["slug"], "name": tp["name"], "badge": rows[-1]["club_badge"]},
            rows=rows, record={k: v for k, v in s.items() if k != "run"}, run=list(s["run"]),
            next={"match_id": nxt.get("match_id"), "home": h, "away": a, "home_badge": nxt.get("home_badge"),
                  "away_badge": nxt.get("away_badge"), "kickoff": nxt.get("kickoff"), "koff_time": nxt.get("koff_time"),
                  "competition": nxt.get("competition"), "club_home": club_side(tp, nxt) == "h"}))
    return events


def streak_milestone(rows):
    """('wins', n) / ('winless', n) / ('first-loss', n) / None - what the
    last row completed, from the marks of EVERY result held."""
    marks = [r["mark"] for r in rows]
    if not marks:
        return None
    s = form_summary(rows)
    mk, n = s["run"]
    if mk == "W" and n >= STREAK_WIN:
        return ("wins", n)
    if mk == "L" and len(marks) > 1:
        before = form_summary(rows[:-1])["run"]
        if before[0] == "W" and before[1] >= STREAK_WIN:
            return ("first-loss", before[1])
    if s["winless"] >= STREAK_WINLESS:
        return ("winless", s["winless"])
    return None


def streak_lines(tp, kind, n, last, s):
    club, opp = tp["name"], last["opponent"]
    res = f"{club} {last['gf']} - {last['ga']} {opp}"
    if kind == "wins":
        head = f"📊 {club} يحقق {_wins(n)} {_in_a_row(n)}."
    elif kind == "first-loss":
        head = f"📊 {club} يخسر لأول مرة بعد {_wins(n)} {_in_a_row(n)}."
    else:
        head = f"📊 {club} بلا فوز في آخر {_matches(n)}."
    return [head,
            f"آخر مباراة: {res} في {last['comp_label']} ({ar_date(last['date'])}).",
            f"آخر {_matches(s['p'])}: فوز {s['w']}، تعادل {s['d']}، خسارة {s['l']}.",
            f"الأهداف: {s['gf']} له، {s['ga']} عليه."]


def club_streak(matches, fixtures, archive, today=None, n=FORM_N):
    """One event per curated club whose LAST match (at most STREAK_MAX_AGE_D
    days ago) completed a milestone, when no fixture of its own falls inside
    the form window - that post carries the run."""
    n = max(1, min(int(n or FORM_N), FORM_MAX))
    now = _now(today)
    cut = (now.date() - datetime.timedelta(days=STREAK_MAX_AGE_D)).isoformat()
    pool, up = results_pool(matches, archive), upcoming_pool(matches, fixtures)
    events = []
    for tp in form_clubs():
        res = club_results(tp, pool)
        if len(res) < FORM_MIN or str(res[-1].get("kickoff") or "")[:10] < cut:
            continue
        if next_fixture(tp, up, now):
            continue
        all_rows = [form_row(tp, m) for m in res]
        rows = all_rows[-n:]
        hit = streak_milestone(all_rows)
        if not hit:
            continue
        kind, k = hit
        s, last = form_summary(rows, all_rows), rows[-1]
        title = streak_lines(tp, kind, k, last, s)[0].lstrip("📊 ").rstrip(".")
        events.append(event(
            KIND_STREAK, f"streak:{tp['slug']}:{last['match_id']}", title,
            streak_lines(tp, kind, k, last, s), f"{SITE}/m/{last['match_id']}", "تفاصيل المباراة",
            [_club_tag(tp["name"]), _club_tag(last["opponent"])], competition=last["competition"],
            club={"slug": tp["slug"], "name": tp["name"], "badge": last["club_badge"]},
            rows=rows, record={kk: v for kk, v in s.items() if kk != "run"}, run=list(s["run"]),
            milestone={"kind": kind, "n": k}, next=None))
    return events


# ---------------------------------------------------------------- all of it
# THE REGISTRY: one entry per event kind, in posting order. A new kind is a
# new pure function (data, today) -> [event(...)] and one line here, plus a
# numbered case in tests/test_fb_post.py. Everything else - the store dedup,
# the nightly run, the FB_EVENTS switch, --dry, --pending - is shared.
DETECTORS = [
    (KIND_CUP, lambda d, today: cup_round_done(d.get("matches"), d.get("fixtures"))),
    (KIND_HALF, lambda d, today: league_half_done(d.get("standings"), d.get("scorers"), today)),
    (KIND_COACH, lambda d, today: coach_left(d.get("articles"), d.get("archive"), today)),
    (KIND_OTD, lambda d, today: on_this_day(d.get("archive"), d.get("moments"), today)),
    (KIND_FORM, lambda d, today: club_form_before_match(d.get("matches"), d.get("fixtures"), d.get("archive"), today)),
    (KIND_STREAK, lambda d, today: club_streak(d.get("matches"), d.get("fixtures"), d.get("archive"), today)),
]


def detect(data=None, today=None):
    """Every event on today's data, in posting order."""
    d = data or load_data()
    out = []
    for _, fn in DETECTORS:
        out += fn(d, today)
    return out


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
        now, up = _now(today), upcoming_pool(data["matches"], data["fixtures"])
        pool = results_pool(data["matches"], data["archive"])
        for tp in form_clubs():
            res = club_results(tp, pool)
            nxt = next_fixture(tp, up, now, 24 * 30)
            rows = [form_row(tp, m) for m in res]
            marks = "".join(MARKS[r["mark"]] for r in rows[-FORM_N:])
            print(f"  club-form {tp['slug']}: {len(res)} results, last {FORM_N} {marks}, "
                  + (f"next {nxt.get('kickoff')} {nxt.get('koff_time') or ''} {ar_team(nxt.get('home'))} × {ar_team(nxt.get('away'))}"
                     if nxt else "no fixture in 30 days")
                  + (f", streak {streak_milestone(rows)}" if rows and streak_milestone(rows) else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
