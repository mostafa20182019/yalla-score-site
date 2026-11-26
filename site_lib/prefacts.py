"""«أرقام قبل المباراة» - the facts a coming match stands on (2026-11-26).

The user, when the rewritten news was switched off: «نركز على ... احصائيات
(آخر 10 مواجهات بين الفريقين)، آخر مواجهة، بورنموث فاز في آخر 5 مباريات».
This is the site's own news now: COMPUTED, never written.

Two families, each a list of plain sentences (one fact a sentence, verb
first, past tense - the house wording rules):

  runs      what a side is on in THIS competition THIS season: wins / losses
            in a row, unbeaten, winless, clean sheets, no goal scored, wins
            at home / away. From the season's finished matches - and only
            when they are the WHOLE season of the side (the official table's
            `played` equals the matches we hold): a run counted over a list
            with a hole in it would be wrong.
            A run that covers every match of the season is said as that
            («فاز في كل مبارياته الخمس هذا الموسم»), never as «آخر 5»: where
            it began last season is not in our data.
  meetings  the last meetings of the two, from data/h2h_feed.json (the
            365scores head-to-head feed, h2h_feed.py) plus every finished
            meeting the build holds itself: the last one, the count of the
            last ten at most, who has not beaten whom. A result awarded by
            decision or an abandoned game is listed with its note and left
            out of every count.

Nothing here says «لأول مرة» or «في تاريخ» - the data does not go back far
enough to know.
"""
import datetime
import json
import os

from site_lib.arabic import _AR_MONTHS
from site_lib.config import DATA
from site_lib.names import ar_team, comp_label
from site_lib.stats import _cnt, _games
from site_lib.text import _lam

# a run is a fact from this length on
MIN_WINS, MIN_LOSSES, MIN_UNBEATEN, MIN_WINLESS = 3, 3, 5, 4
MIN_CLEAN, MIN_BLANK, MIN_HOME_WINS, MIN_AWAY_WINS = 3, 3, 4, 3
MIN_SEASON = 4            # «في كل مبارياته» needs this many matches
MEET_N = 10               # «آخر 10 مواجهات» at most
MEET_MIN = 3              # fewer meetings than this = no count, only the last one
MIN_DRAWS = 3             # a row of drawn meetings
MIN_NO_WIN = 4            # «لم يفز على» from this many meetings on
# how a feed game ended: these are real results, anything else is listed but not counted
PLAYED = ("انتهت", "بعد الوقت الإضافي", "بعد ركلات الترجيح", "")


# ------------------------------------------------------------------ runs
def _mark(m, raw):
    gf, ga = ((m["home_score"], m["away_score"]) if m.get("home") == raw
              else (m["away_score"], m["home_score"]))
    return ("W" if gf > ga else "L" if gf < ga else "D"), int(gf), int(ga)


def _tail(seq, ok):
    n = 0
    for x in reversed(seq):
        if not ok(x):
            break
        n += 1
    return n


def season_runs(raw, comp_matches, played=None):
    """The runs of `raw` over its finished matches in one competition
    (chronological), or {} when the list is not the side's whole season."""
    ms = [m for m in (comp_matches or []) if raw in (m.get("home"), m.get("away"))
          and m.get("home_score") is not None and m.get("away_score") is not None]
    if not ms or (played is not None and int(played or 0) != len(ms)):
        return {}
    rs = [_mark(m, raw) for m in ms]
    home = [r for m, r in zip(ms, rs) if m.get("home") == raw]
    away = [r for m, r in zip(ms, rs) if m.get("away") == raw]
    return {"p": len(rs),
            "wins": _tail(rs, lambda r: r[0] == "W"), "losses": _tail(rs, lambda r: r[0] == "L"),
            "unbeaten": _tail(rs, lambda r: r[0] != "L"), "winless": _tail(rs, lambda r: r[0] != "W"),
            "clean": _tail(rs, lambda r: r[2] == 0), "blank": _tail(rs, lambda r: r[1] == 0),
            "home_p": len(home), "home_wins": _tail(home, lambda r: r[0] == "W"),
            "away_p": len(away), "away_wins": _tail(away, lambda r: r[0] == "W")}


def _last(n):
    """«آخر 5 مباريات» / «آخر مباراتين»"""
    return "آخر " + _cnt(n, "مباراة", "مباراتين", "مباريات", "مباراة")


def _all(n):
    return f"كل مبارياته ({n})"


def run_facts(club, r, comp_txt, at_home=None):
    """[(weight, sentence)] for one side, the strongest first. `at_home`:
    True / False adds the side's run at home / away for THIS match."""
    if not r:
        return []
    out, p = [], r["p"]
    inn = f"في {comp_txt}"

    def said(n, verb_last, verb_all, tail=""):
        if n == p and p >= MIN_SEASON:
            return f"{verb_all} {club} {_all(p)} {inn} هذا الموسم{tail}."
        return f"{verb_last} {club} {_last(n)} له {inn}{tail}."

    w, l, ub, wl = r["wins"], r["losses"], r["unbeaten"], r["winless"]
    if w >= MIN_WINS:
        out.append((w * 3, (f"فاز {club} في {_all(p)} {inn} هذا الموسم." if w == p and p >= MIN_SEASON
                            else f"فاز {club} في {_last(w)} له {inn}.")))
    # the longer run is said beside the shorter one only when it adds two
    # matches to it - or when it is the whole season, which is its own fact
    if ub >= MIN_UNBEATEN and (ub >= w + 2 or (ub == p and ub > w)):
        out.append((ub * 2, (f"لم يخسر {club} أي مباراة {inn} هذا الموسم ({_games(p)})." if ub == p
                             else f"لم يخسر {club} في {_last(ub)} له {inn}.")))
    if l >= MIN_LOSSES:
        out.append((l * 3, said(l, "خسر", "خسر")))
    if wl >= MIN_WINLESS and (wl >= l + 2 or (wl == p and wl > l)):
        out.append((wl * 2, (f"لم يفز {club} بأي مباراة {inn} هذا الموسم ({_games(p)})." if wl == p
                             else f"لم يفز {club} في {_last(wl)} له {inn}.")))
    if r["clean"] >= MIN_CLEAN:
        out.append((r["clean"] * 2, f"لم يستقبل {club} أي هدف في {_last(r['clean'])} له {inn}."))
    if r["blank"] >= MIN_BLANK:
        out.append((r["blank"] * 2, f"لم يسجل {club} أي هدف في {_last(r['blank'])} له {inn}."))
    if at_home is True and r["home_wins"] >= MIN_HOME_WINS and r["home_wins"] > w:
        hw = r["home_wins"]
        out.append((hw * 2, (f"فاز {club} في كل مبارياته على ملعبه ({hw}) {inn} هذا الموسم." if hw == r["home_p"]
                             else f"فاز {club} في {_last(hw)} له على ملعبه {inn}.")))
    if at_home is False and r["away_wins"] >= MIN_AWAY_WINS and r["away_wins"] > w:
        aw = r["away_wins"]
        out.append((aw * 2, (f"فاز {club} في كل مبارياته خارج ملعبه ({aw}) {inn} هذا الموسم." if aw == r["away_p"]
                             else f"فاز {club} في {_last(aw)} له خارج ملعبه {inn}.")))
    return sorted(out, key=lambda x: -x[0])


# ------------------------------------------------------------------ meetings
def load_feed():
    try:
        with open(os.path.join(DATA, "h2h_feed.json"), encoding="utf-8") as f:
            return (json.load(f) or {}).get("pairs") or {}
    except (OSError, ValueError):
        return {}


def ar_date(iso):
    try:
        d = datetime.date.fromisoformat((iso or "")[:10])
    except ValueError:
        return iso or ""
    return f"{d.day} {_AR_MONTHS[d.month]} {d.year}"


def meetings(home, away, feed, fin_all=None, before=None):
    """The played meetings of the two raw names, newest first, each
    {date, comp, home, away, hg, ag, status, counted} with OUR raw names.
    `before`: only meetings before this ISO day (the coming match's own)."""
    rec = (feed or {}).get("|".join(sorted([home or "", away or ""]))) or {}
    side = {"a": rec.get("a"), "b": rec.get("b")}
    out = []
    for g in rec.get("games") or []:
        h = side.get(g.get("home"))
        if h not in (home, away):
            continue
        out.append({"date": g.get("date") or "", "comp": g.get("comp") or "",
                    "home": h, "away": away if h == home else home,
                    "hg": int(g["hg"]), "ag": int(g["ag"]), "status": g.get("status") or "",
                    "counted": (g.get("status") or "") in PLAYED})
    have = {g["date"] for g in out}
    for m in fin_all or []:                      # the build's own, not in the feed yet
        if {m.get("home"), m.get("away")} != {home, away} or m.get("home_score") is None:
            continue
        d = str(m.get("kickoff") or "")[:10]
        if d and d not in have:
            have.add(d)
            out.append({"date": d, "comp": comp_label(m.get("competition") or ""),
                        "home": m["home"], "away": m["away"], "hg": int(m["home_score"]),
                        "ag": int(m["away_score"]), "status": "", "counted": True})
    if before:
        out = [g for g in out if g["date"] < str(before)[:10]]
    return sorted(out, key=lambda g: g["date"], reverse=True)


def _won(g):
    return g["home"] if g["hg"] > g["ag"] else g["away"] if g["ag"] > g["hg"] else None


def tally(games, home, away, n=MEET_N):
    """(n counted, wins of home, wins of away, draws) over the last `n`
    counted meetings."""
    gs = [g for g in games if g["counted"]][:n]
    wh = sum(1 for g in gs if _won(g) == home)
    wa = sum(1 for g in gs if _won(g) == away)
    return len(gs), wh, wa, len(gs) - wh - wa


def _n_wins(n):
    """the nominative count of a list: «فوزان للأهلي», not «فوزين»"""
    return _cnt(n, "فوز واحد", "فوزان", "انتصارات", "فوزًا")


def _n_draws(n):
    return _cnt(n, "تعادل واحد", "تعادلان", "تعادلات", "تعادلًا")


def _meet(n):
    return _cnt(n, "مواجهة", "مواجهتين", "مواجهات", "مواجهة")


def meeting_facts(home, away, games):
    """[(weight, sentence)] about the two sides' meetings."""
    gs = [g for g in games if g["counted"]]
    if not gs:
        return []
    h_ar, a_ar = ar_team(home), ar_team(away)
    out, last = [], gs[0]
    who = _won(last)
    res = (f"بفوز {ar_team(who)} {max(last['hg'], last['ag'])}-{min(last['hg'], last['ag'])}" if who
           else f"بالتعادل {last['hg']}-{last['ag']}")
    note = " بعد ركلات الترجيح" if "ركلات" in last["status"] and not who else ""
    where = f" في {last['comp']}" if last["comp"] else ""
    out.append((4, f"انتهت آخر مواجهة بين الفريقين {res}{note}{where} ({ar_date(last['date'])})."))
    n, wh, wa, dr = tally(gs, home, away)
    if n >= MEET_MIN:
        bits = [f"{_n_wins(wh)} {_lam(h_ar)}" if wh else "", f"{_n_wins(wa)} {_lam(a_ar)}" if wa else "",
                _n_draws(dr) if dr else ""]
        out.append((n, f"آخر {_meet(n)} بين الفريقين: " + "، ".join(b for b in bits if b) + "."))
        # who has not beaten whom over the same meetings: the longer of the
        # two runs only (a row of draws would say it twice, once each way)
        last_n = gs[:MEET_N]
        draws = 0
        for g in last_n:
            if _won(g):
                break
            draws += 1
        if draws >= MIN_DRAWS:
            out.append((draws * 2, f"انتهت آخر {_meet(draws)} بين الفريقين بالتعادل."))
        runs = []
        for over, loser_raw in ((h_ar, away), (a_ar, home)):
            k = 0
            for g in last_n:
                if _won(g) == loser_raw:
                    break
                k += 1
            runs.append((k, ar_team(loser_raw), over))
        k, loser, over = max(runs, key=lambda x: x[0])
        if k >= MIN_NO_WIN and k > draws:
            out.append((k * 2, f"لم يفز {loser} على {over} في آخر {_meet(k)} بينهما."))
    return out


# ------------------------------------------------------------------ a match
def match_facts(m, comp_matches, table, feed, fin_all=None, run_sides=("home", "away")):
    """{"lines": [sentence], "weight": n, "games": [meeting], "tally": (...)}
    for one coming match. `comp_matches`: the competition's finished matches;
    `table`: its official rows (or None - then no runs)."""
    home, away = m.get("home"), m.get("away")
    h_ar, a_ar = ar_team(home), ar_team(away)
    comp_txt = comp_label(m.get("competition") or "")
    rows = {r.get("team"): r for r in (table or [])}
    facts = []
    for k, raw, club, at_home in (("home", home, h_ar, True), ("away", away, a_ar, False)):
        row = rows.get(raw)
        if not row or k not in run_sides:
            continue
        facts += run_facts(club, season_runs(raw, comp_matches, row.get("played")), comp_txt, at_home)
    games = meetings(home, away, feed, fin_all, before=m.get("kickoff"))
    meet = meeting_facts(home, away, games)
    runs = sorted(facts, key=lambda x: -x[0])
    both = runs + meet
    lines = [s for _w, s in runs] + [s for _w, s in meet]
    return {"lines": lines, "runs": [s for _w, s in runs], "meet": [s for _w, s in meet],
            "weight": sum(w for w, _s in both),
            "top": max(both, key=lambda x: x[0])[1] if both else "",
            "topw": max((w for w, _s in both), default=0),
            "games": games[:MEET_N], "tally": tally(games, home, away)}


# ------------------------------------------------------------------ the build's own
# registered once by build_site.build() before the first page (setup), read by
# the match pages, the home page's side column and /news
NEWS_SKIP = {"Egyptian Second Division", "Iraq Stars League", "Syrian Premier League",
             "Libyan Premier League", "FIFA U-17 World Cup"}
NEWS_MIN_WEIGHT = 12      # a match is news from this much on (a run of 4, or six meetings and the last one)
NEWS_N = 6
NEWS_BONUS, NEWS_CURATED, NEWS_TODAY, NEWS_TOP = 15, 30, 10, 4
_CTX = {}
_MEMO = {}


def next_kickoffs(fixtures, matches=None):
    """{(competition, raw name): the kick-off day of the side's NEXT match
    there} - a run is said on that match's page only: on a later one the
    side plays again first, and the run would be an old one by then."""
    out = {}
    def see(comp, m):
        d = str(m.get("kickoff") or "")[:10]
        if not d or m.get("status") in ("FINISHED", "POSTPONED", "CANCELLED") or m.get("home_score") is not None:
            return
        for k in ("home", "away"):
            key = (comp, m.get(k))
            if m.get(k) and (key not in out or d < out[key]):
                out[key] = d
    for f in fixtures or []:
        for rd in f.get("rounds") or []:
            for m in rd.get("matches") or []:
                see(f.get("competition"), m)
    for m in matches or []:
        see(m.get("competition"), m)
    return out


def setup(fixtures, bycomp, standings, feed=None, matches=None):
    """Register the season's finished matches, the official tables and the
    meetings feed. Returns how many pairs the feed holds."""
    from site_lib.stats import _finished_by_comp
    fin = _finished_by_comp(fixtures or [], bycomp)
    _CTX.clear()
    _MEMO.clear()
    _CTX.update(
        fin=fin,
        fin_all=sorted((x for ms in fin.values() for x in ms), key=lambda x: x.get("kickoff") or ""),
        tables={s.get("competition"): s.get("table") for s in standings or []
                if s.get("table") and not s.get("zeroed") and not s.get("past")},
        feed=load_feed() if feed is None else feed,
        nxt=next_kickoffs(fixtures, matches))
    return len(_CTX["feed"])


def for_match(m):
    """match_facts() of a coming match on the registered data ({} before setup)."""
    if not _CTX or not m.get("home") or not m.get("away"):
        return {}
    key = m.get("match_id") or (m.get("home"), m.get("away"), m.get("kickoff"))
    if key not in _MEMO:
        comp = m.get("competition")
        day = str(m.get("kickoff") or "")[:10]
        # a side's runs only on its NEXT match in the competition
        sides = {k for k in ("home", "away") if _CTX["nxt"].get((comp, m.get(k)), day) >= day}
        _MEMO[key] = match_facts(m, _CTX["fin"].get(comp), _CTX["tables"].get(comp), _CTX["feed"],
                                 _CTX["fin_all"], run_sides=sides)
    return _MEMO[key]


def section_html(m):
    """The match page's «أرقام قبل المباراة»: the sentences, then the
    meetings one by one. '' when there is nothing to say."""
    from site_lib.matchdata import score_pill
    from site_lib.text import esc
    f = for_match(m)
    if not f or not f.get("lines"):
        return ""
    h_ar, a_ar = ar_team(m.get("home")), ar_team(m.get("away"))
    out = [f'<section class="minfo pf"><h2>أرقام قبل مباراة {esc(h_ar)} و{esc(a_ar)}</h2>',
           '<ul class="pf-l">', "".join(f"<li>{esc(s)}</li>" for s in f["lines"]), "</ul>"]
    games = f.get("games") or []
    if len(games) >= 2:
        out.append(f'<h3 class="pf-h">آخر {esc(_meet(len(games)))} بين الفريقين</h3><ol class="h2h-list">')
        for g in games:
            who = _won(g) if g["counted"] else None
            note = "" if g["status"] in ("انتهت", "") else f'<span class="h2h-note">{esc(g["status"])}</span>'
            out.append(
                '<li class="h2h-g">'
                f'<span class="h2h-d"><time datetime="{esc(g["date"])}">{esc(ar_date(g["date"]))}</time>'
                + (f' · {esc(g["comp"])}' if g["comp"] else "") + '</span>'
                f'<span class="h2h-r"><b class="h2h-n{" w" if who == g["home"] else ""}">{esc(ar_team(g["home"]))}</b>'
                f'{score_pill(g["hg"], g["ag"], "h2h-sc")}'
                f'<b class="h2h-n{" w" if who == g["away"] else ""}">{esc(ar_team(g["away"]))}</b></span>{note}</li>')
        out.append("</ol>")
    out.append('<p class="pd-note">الأرقام محسوبة من نتائج الموسم وجدول البطولة الرسمي'
               + ("، والمواجهات السابقة من بيانات 365Scores" if games else "")
               + '. تُحدَّث تلقائيًا حتى صافرة البداية.</p></section>')
    return "".join(out)


def day_news(matches, today, days=1, n=NEWS_N):
    """The coming matches of today .. today+days worth a line of news: each
    {"m", "t" (its strongest fact), "weight"}, today's first, then by weight."""
    from site_lib.competitions import LEAGUE_BAR
    from site_lib.names import _is_ticker_team
    try:
        lim = (datetime.date.fromisoformat(today) + datetime.timedelta(days=days)).isoformat()
    except ValueError:
        return []
    out = []
    for m in matches or []:
        d = str(m.get("kickoff") or "")[:10]
        if m.get("status") != "UPCOMING" or not (today <= d <= lim) or m.get("competition") in NEWS_SKIP:
            continue
        f = for_match(m)
        if not f or f.get("weight", 0) < NEWS_MIN_WEIGHT or not f.get("top"):
            continue
        # WHICH matches first: the ones the readers came for - a curated
        # club, a side of the table's top NEWS_TOP, a league of the home
        # page's bar - then the strength of the fact itself. The sum of a
        # match's facts is not interest: two sides on losing runs in a small
        # league must not push Chelsea off a list of six.
        pos = {r.get("team"): int(r.get("pos") or 99) for r in _CTX["tables"].get(m.get("competition")) or []}
        rank = (f["topw"]
                + (NEWS_CURATED if _is_ticker_team(m) else 0)
                + (NEWS_BONUS if m.get("competition") in LEAGUE_BAR else 0)
                + (NEWS_BONUS if min(pos.get(m.get("home"), 99), pos.get(m.get("away"), 99)) <= NEWS_TOP else 0)
                + (NEWS_TODAY if d == today else 0))
        out.append({"m": m, "t": f["top"], "weight": f["weight"], "rank": rank, "day": d})
    out.sort(key=lambda x: -x["rank"])
    return out[:n]


def news_html(matches, today, heading="أرقام قبل المباريات", cls="pf-news"):
    """The block of day_news() for the home page's side column and /news."""
    from site_lib.crests import local_crest
    from site_lib.text import esc
    from site_lib.urls import match_url
    items = []
    for it in day_news(matches, today):
        m = it["m"]
        if not match_url(m):
            continue
        cr = "".join(f'<img src="{esc(local_crest(m[k]))}" alt="" width="20" height="20" loading="lazy" decoding="async">'
                     for k in ("home_badge", "away_badge") if m.get(k))
        when = ("اليوم" if it["day"] == today else "غدًا") + (f' {m["koff_time"]}' if m.get("koff_time") else "")
        items.append(
            f'<a class="pf-i" href="{esc(match_url(m))}"><b class="pf-t">{esc(it["t"])}</b>'
            f'<span class="pf-m"><span class="pf-c">{cr}</span>{esc(ar_team(m.get("home")))} × {esc(ar_team(m.get("away")))}'
            f' · {esc(when)}</span></a>')
    if not items:
        return ""
    return f'<section class="{cls}"><h2 class="mp-h">{esc(heading)}</h2>{"".join(items)}</section>'
