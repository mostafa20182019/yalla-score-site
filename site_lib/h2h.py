"""Head-to-head pages (/h2h/<slug>) - the data side (2026-11-13).

«مواجهات الأهلي والزمالك» is searched all year, not only on derby day, and
the site had no page for it. The page is COMPUTED, never written: every
number and sentence comes from the meetings list below.

Where the meetings come from, in this order:
  data/h2h_history.json   the 365scores head-to-head feed, saved by
                          h2h_history.py (in git; it only ever grows)
  our own match data      every finished meeting the build knows (m_all) that
                          the file does not hold yet - so a new derby joins
                          the page on the next publish, with no fetch
  data/h2h_notes.json     hand-checked facts the feed cannot know: a result
                          awarded by decision (its goals are not counted), a
                          draw settled on penalties

The page says how many meetings it holds and since when. It never claims an
all-time record: the feed starts in 2022.

Slugs are indexed URLs - never rename one. A new pair = one line in PAIRS
and one run of h2h_history.py.
"""
import datetime
import json
import os

from site_lib.arabic import _AR_MONTHS
from site_lib.config import DATA
from site_lib.names import ar_team, comp_label

# `game` = any 365scores game id between the two (the feed is asked by game).
PAIRS = [
    {"slug": "al-ahly-zamalek", "a": "الأهلي", "b": "الزمالك",
     "a_slug": "al-ahly", "b_slug": "zamalek",
     "league": "Egyptian Premier League", "game": 4804684},
]


def pair_key(a, b):
    """The key both data files use: the two Arabic names, sorted."""
    return "|".join(sorted((a, b)))


def pair_for_club(slug):
    """The first pair this club page belongs to, or None."""
    for p in PAIRS:
        if slug in (p["a_slug"], p["b_slug"]):
            return p
    return None


def _load(name):
    try:
        with open(os.path.join(DATA, name), encoding="utf-8") as f:
            return json.load(f).get("pairs") or {}
    except (OSError, ValueError):
        return {}


def load_history(pair):
    """[{id, date, comp, home, away, hg, ag}] saved from the feed, or []."""
    return list((_load("h2h_history.json").get(pair_key(pair["a"], pair["b"])) or {}).get("games") or [])


def load_notes(pair):
    """{date: {note, played, winner}} for this pair, or {}."""
    return (_load("h2h_notes.json").get(pair_key(pair["a"], pair["b"])) or {}).get("games") or {}


def is_pair(pair, home, away):
    return {ar_team(home), ar_team(away)} == {pair["a"], pair["b"]}


def meetings(pair, history, m_all):
    """Every played meeting, newest first: the saved feed plus our own
    finished matches the file does not hold (matched by id, then by date).
    Each game: {id, date, comp, home, away, hg, ag, ours} - `ours` is the
    match id when the site has a page for it."""
    out, ids, dates = [], set(), set()
    ours = {}
    for m in (m_all or {}).values():
        if is_pair(pair, m.get("home"), m.get("away")) and m.get("match_id"):
            ours[str(m["match_id"])] = m
    for g in history:
        if g.get("hg") is None or g.get("ag") is None or not g.get("date"):
            continue
        gid = str(g.get("id") or "")
        out.append({"id": gid, "date": g["date"][:10], "comp": g.get("comp") or "",
                    "home": ar_team(g.get("home")), "away": ar_team(g.get("away")),
                    "hg": int(g["hg"]), "ag": int(g["ag"]),
                    "ours": gid if gid in ours else None})
        ids.add(gid)
        dates.add(g["date"][:10])
    for mid, m in ours.items():
        if (m.get("status") or "").upper() != "FINISHED":
            continue
        if m.get("home_score") is None or m.get("away_score") is None:
            continue
        d = (m.get("kickoff") or "")[:10]
        if mid in ids or d in dates or not d:
            continue
        out.append({"id": mid, "date": d, "comp": comp_label(m.get("competition")),
                    "home": ar_team(m.get("home")), "away": ar_team(m.get("away")),
                    "hg": int(m["home_score"]), "ag": int(m["away_score"]), "ours": mid})
    out.sort(key=lambda g: g["date"], reverse=True)
    return out


def winner(g):
    """The club that won this game on the official score, or None for a draw."""
    if g["hg"] > g["ag"]:
        return g["home"]
    if g["ag"] > g["hg"]:
        return g["away"]
    return None


def was_played(g, notes):
    return (notes.get(g["date"]) or {}).get("played", True)


def tally(games, pair, notes):
    """{wins: {a, b}, draws, goals: {a, b}, awarded} - the goals of a result
    awarded by decision are not counted; the result itself is."""
    a, b = pair["a"], pair["b"]
    wins, goals, draws, awarded = {a: 0, b: 0}, {a: 0, b: 0}, 0, 0
    for g in games:
        w = winner(g)
        if w:
            wins[w] += 1
        else:
            draws += 1
        if was_played(g, notes):
            goals[g["home"]] += g["hg"]
            goals[g["away"]] += g["ag"]
        else:
            awarded += 1
    return {"wins": wins, "draws": draws, "goals": goals, "awarded": awarded}


def comp_base(name):
    """«الدوري المصري - المرحلة النهائية» -> «الدوري المصري»: the competition
    without its stage, so one table row holds one competition."""
    return (name or "").split(" - ")[0].strip() or "أخرى"


def by_competition(games, pair):
    """[(competition, games, wins a, draws, wins b)] most meetings first."""
    a, b = pair["a"], pair["b"]
    rows = {}
    for g in games:
        r = rows.setdefault(comp_base(g["comp"]), [0, 0, 0, 0])
        r[0] += 1
        w = winner(g)
        r[1 if w == a else (3 if w == b else 2)] += 1
    return sorted(((c, *r) for c, r in rows.items()), key=lambda x: (-x[1], x[0]))


def biggest_win(games, notes):
    """The played game with the widest margin (the newest one on a tie)."""
    best = None
    for g in games:                                  # newest first
        if not was_played(g, notes) or winner(g) is None:
            continue
        if best is None or abs(g["hg"] - g["ag"]) > abs(best["hg"] - best["ag"]):
            best = g
    return best


def last_win(games, club):
    for g in games:
        if winner(g) == club:
            return g
    return None


def unbeaten_run(games, pair):
    """(club, n): the club that has not lost any of the newest n meetings,
    when the newest decided game was its win. (None, 0) otherwise."""
    lead = next((winner(g) for g in games if winner(g)), None)
    if not lead:
        return None, 0
    n = 0
    for g in games:
        if winner(g) not in (lead, None):
            break
        n += 1
    return lead, n


def next_meeting(pair, m_all, today):
    """Our next scheduled match between the two, or None."""
    up = [m for m in (m_all or {}).values()
          if is_pair(pair, m.get("home"), m.get("away"))
          and (m.get("status") or "").upper() in ("UPCOMING", "LIVE")
          and (m.get("kickoff") or "") >= today]
    return min(up, key=lambda m: m.get("kickoff") or "") if up else None


def ar_date(iso):
    """«11 أكتوبر 2026»"""
    try:
        d = datetime.date.fromisoformat((iso or "")[:10])
    except ValueError:
        return iso or ""
    return f"{d.day} {_AR_MONTHS[d.month]} {d.year}"


def ar_month_year(iso):
    """«يوليو 2022»"""
    try:
        d = datetime.date.fromisoformat((iso or "")[:10])
    except ValueError:
        return iso or ""
    return f"{_AR_MONTHS[d.month]} {d.year}"


def score_line(g):
    """«الزمالك 0 - 2 الأهلي» - the score with SPACES, so the numbers stay on
    their own sides in a right-to-left sentence."""
    return f"{g['home']} {g['hg']} - {g['ag']} {g['away']}"
