# -*- coding: utf-8 -*-
"""story_social.py — the social review's post kinds (football-social, 2026-11-19).

Four more «أخبار من الداتا» kinds for story_events.DETECTORS. Each is a pure
function over the site's own data files, each returns story_events events,
each goes out once through the store like every other kind:

  night_number    «رقم الليلة»: ONE finished match of the day (the leagues
                  of the bar or one of our clubs) whose result
                  went against its own numbers (the winner had fewer shots
                  and at least XG_GAP less xG) -> one number, the result,
                  one question.
  round_scenario  «سيناريو الجولة»: the evening before a league round, the
                  top of the table and the door to the calculator
                  (/calc/<slug>) - «اختار نتايجك», never «توقّع واكسب»: no
                  points, no prizes, nothing that looks like betting.
  sudan_corner    «ركن السودان»: every Friday evening, الهلال السوداني's
                  record in the CAF Champions League and its next match,
                  then منتخب السودان's next match.
  goon_question   «سؤال الجون»: every afternoon, a team to guess from its
                  last five league results. The answer goes out as the first
                  line of the NEXT day's question (fb_post adds it only when
                  yesterday's question is on record).

  round_movers    «الصاعد والهابط»: the evening after a league round ended,
                  the sides that climbed or dropped two places or more -
                  only the sides whose place before the round is certain.
  abroad_week     «محترفونا هذا الأسبوع»: Monday, the week's goals of the
                  players listed by hand in abroad_players.json.

THE SWITCH: these kinds are SOCIAL_KINDS in fb_post.py and stay printed, not
posted, until the repo variable FB_SOCIAL is "on" - the user reads a new
kind's wording before it goes live (his firm rule).

NOTHING IS WRITTEN FROM MEMORY: every name, score, number and date comes
from the data files. A fact that is not there is not written.
"""
import datetime
import hashlib

KIND_NUMBER = "night-number"
KIND_SCENARIO = "round-scenario"
KIND_SUDAN = "sudan-corner"
KIND_QUESTION = "goon-question"
KIND_MOVERS = "round-movers"
KIND_ABROAD = "abroad-week"
# «الصاعد والهابط» is a REEL since 2026-11-20 (movers_reel.py posts it nightly
# with this event's text as its caption) - no longer a text post of its own
SOCIAL_KINDS = (KIND_NUMBER, KIND_SCENARIO, KIND_SUDAN, KIND_QUESTION, KIND_ABROAD)

# ---- «رقم الليلة»
XG_GAP = 1.0                 # the loser's xG minus the winner's, at least
SHOTS_RATIO = 1.5            # ...and the loser shot this many times the winner's shots
NUMBER_FROM_H = 23           # Cairo: after the evening's matches
# ---- «سيناريو الجولة»
SCENARIO_COMPS = ("Egyptian Premier League",)
SCENARIO_FROM_H = 19         # Cairo, the day before the round's first match
SCENARIO_MIN_PLAYED = 5      # the calculator's own floor (site_lib/calc.MIN_MATCHES)
# ---- «ركن السودان»
SUDAN_WEEKDAY, SUDAN_FROM_H = 4, 20      # Friday 20:00 Cairo = 21:00 Khartoum
SUDAN_COMP = "CAF Champions League"
SUDAN_AHEAD_D = 21           # a next match further away than this is not said
# ---- «سؤال الجون»
QUESTION_FROM_H = 14
QUESTION_N = 5
QUESTION_COMPS = ("Egyptian Premier League", "Premier League", "Primera Division", "Saudi Pro League",
                  "Serie A", "Turkish Super Lig", "Bundesliga")


def _se():
    import story_events as SE
    return SE


def _cairo_day(now):
    return now.date()


def _is_clock(today):
    """detect() hands a DATE in tests and --date (the whole day counts) and
    None on the real run (the Cairo clock decides)."""
    return today is None or isinstance(today, datetime.datetime)


def _after(now, today, hour):
    return (not _is_clock(today)) or now.hour >= hour


def _shots(n):
    n = int(n)
    return "مرة واحدة" if n == 1 else "مرتين" if n == 2 else f"{n} مرات" if n <= 10 else f"{n} مرة"


# ---------------------------------------------------------------- «رقم الليلة»
def night_number(matches, archive, stats, today=None):
    """At most ONE event a day: the finished match of today (Cairo) whose
    winner was out-shot SHOTS_RATIO to one and trailed by XG_GAP in xG; the
    widest xG gap wins. The score is the confirmed one (matches.json / the
    archive), never the stats file's."""
    SE = _se()
    now = SE._now(today)
    if not _after(now, today, NUMBER_FROM_H):
        # a match that ended before midnight is still tonight's until 03:00
        if not (_is_clock(today) and now.hour < 3):
            return []
        now = now - datetime.timedelta(days=1)
    day = _cairo_day(now).isoformat()
    by_id = {str(s.get("match_id")): s for s in stats or [] if s.get("status") == "ok"}
    from site_lib.competitions import LEAGUE_BAR
    from site_lib.names import _is_ticker_team
    best = None
    for m in SE.results_pool(matches, archive):
        if str(m.get("kickoff") or "")[:10] != day:
            continue
        # a match the page's reader knows: the leagues of the bar, or one of our clubs
        if m.get("competition") not in LEAGUE_BAR and not _is_ticker_team(m):
            continue
        s = by_id.get(str(m.get("match_id")))
        if not s:
            continue
        hs, as_ = int(m["home_score"]), int(m["away_score"])
        if hs == as_:
            continue
        w, l = ("h", "a") if hs > as_ else ("a", "h")
        try:
            wx, lx = float(s[w]["xg"]), float(s[l]["xg"])
            wsh, lsh = int(s[w]["shots"]), int(s[l]["shots"])
        except (KeyError, TypeError, ValueError):
            continue
        if lx - wx < XG_GAP or wsh < 1 or lsh < wsh * SHOTS_RATIO:
            continue
        if best is None or lx - wx > best[0]:
            best = (lx - wx, m, w, wsh, lsh)
    if not best:
        return []
    _, m, w, wsh, lsh = best
    h, a = SE._side_names(m)
    win, lose = (h, a) if w == "h" else (a, h)
    hs, as_ = int(m["home_score"]), int(m["away_score"])
    wg, lg = max(hs, as_), min(hs, as_)
    only = " فقط" if wsh <= 10 else ""
    lines = [f"🔢 رقم الليلة: {wsh}",
             f"{win} سدد {_shots(wsh)}{only}. {lose} سدد {_shots(lsh)}.",
             f"النتيجة: {win} {wg}-{lg} {lose}.",
             "فعالية أم حظ؟ اكتب رأيك."]
    return [SE.event(KIND_NUMBER, day, f"رقم الليلة: {win} {wg}-{lg} {lose}", lines,
                     f"{SE.SITE}/m/{m.get('match_id')}" if m.get("match_id") else SE.SITE + "/", "أرقام المباراة",
                     [SE.comp_tag(m.get("competition")), SE._club_tag(win), SE._club_tag(lose)],
                     competition=m.get("competition"),
                     match={"match_id": m.get("match_id"), "home": h, "away": a, "home_score": hs, "away_score": as_,
                            "home_badge": m.get("home_badge"), "away_badge": m.get("away_badge")},
                     number=wsh, shots={"winner": wsh, "loser": lsh})]


# ---------------------------------------------------------------- «سيناريو الجولة»
def _pts(n):
    n = int(n)
    return "نقطة واحدة" if n == 1 else "نقطتين" if n == 2 else f"{n} نقاط" if n <= 10 else f"{n} نقطة"


def round_scenario(matches, fixtures, standings, today=None, comps=SCENARIO_COMPS):
    """One event per league round, the evening BEFORE its first match: the
    round = the lowest-numbered one in fixtures.json with no match started;
    it fires only on the day before its earliest kick-off. The link is the
    calculator's page."""
    SE = _se()
    from site_lib.competitions import COMP_SLUG
    now = SE._now(today)
    if not _after(now, today, SCENARIO_FROM_H):
        return []
    tomorrow = (_cairo_day(now) + datetime.timedelta(days=1)).isoformat()
    fresh = {str(m.get("match_id")): m for m in matches or []}
    tables = {s.get("competition"): s for s in standings or []}
    events = []
    for fx in fixtures or []:
        comp = fx.get("competition")
        if comp not in comps or not COMP_SLUG.get(comp):
            continue
        st = tables.get(comp) or {}
        table = sorted(st.get("table") or [], key=lambda r: int(r.get("pos") or 0))
        if st.get("zeroed") or len(table) < 4 or max(int(r.get("played") or 0) for r in table) < SCENARIO_MIN_PLAYED:
            continue
        for rd in sorted((r for r in fx.get("rounds") or [] if r.get("matches")), key=lambda r: r.get("round") or 0):
            ms = [fresh.get(str(m.get("match_id")), m) for m in rd["matches"]]
            if any(SE._started(m) for m in ms):
                continue
            first = min((str(m.get("kickoff") or "9999")[:10] for m in ms))
            if first != tomorrow:
                break                       # the next round is not tomorrow: nothing to say today
            rn = rd.get("round")
            top = table[:3]
            lines = [f"🧮 الجولة {rn} من {SE.comp_label(comp)} تبدأ غدًا."]
            order = ("أول", "ثاني", "ثالث")
            for i, r in enumerate(top):
                lines.append(f"{SE.ar_team(r.get('team'))} {order[i]} الجدول بـ{_pts(r.get('pts'))}.")
            lines += ["اختر نتائج الجولة وشاهد الترتيب بعدها.",
                      "صوّر جدولك وأرسله في التعليقات."]
            season = SE.season_of(first)
            events.append(SE.event(
                KIND_SCENARIO, f"{comp}:R{rn}:{season}", f"الجولة {rn} من {SE.comp_label(comp)}: اختر نتائجك",
                lines, f"{SE.SITE}/calc/{COMP_SLUG[comp]}", "حاسبة الترتيب",
                [SE.comp_tag(comp)] + [SE._club_tag(SE.ar_team(r.get("team"))) for r in top[:2]],
                competition=comp, round=rn, season=season,
                table=[{"pos": r.get("pos"), "team": SE.ar_team(r.get("team")), "pts": r.get("pts")} for r in top],
                pairs=[{"match_id": m.get("match_id"), "home": SE.ar_team(m.get("home")), "away": SE.ar_team(m.get("away")),
                        "kickoff": m.get("kickoff"), "koff_time": m.get("koff_time")} for m in ms]))
            break
    return events


# ---------------------------------------------------------------- «ركن السودان»
def _next_line(SE, tp, up, now, days=SUDAN_AHEAD_D):
    nxt = SE.next_fixture(tp, up, now, 24 * days)
    if not nxt:
        return None, None
    h, a = SE._side_names(nxt)
    k = SE._kick_dt(nxt)
    when = SE.ar_date(nxt.get("kickoff"), weekday=True, year=False)
    if nxt.get("koff_time"):
        when += f" الساعة {k:%H:%M} بتوقيت القاهرة"
    return nxt, f"{h} × {a}، {when}."


def sudan_corner(matches, fixtures, archive, today=None):
    """Friday evening, once a week: الهلال السوداني in this season's CAF
    Champions League (played / won / drawn / lost, goals for and against,
    every number counted from our own rows) and its next match; then منتخب
    السودان's next match. Nothing to say (no result this season and no
    match ahead) -> no post."""
    SE = _se()
    from site_lib.clubs import TEAM_PAGES
    now = SE._now(today)
    if now.weekday() != SUDAN_WEEKDAY or not _after(now, today, SUDAN_FROM_H):
        return []
    by = {tp["slug"]: tp for tp in TEAM_PAGES}
    hilal, nt = by.get("al-hilal-sudan"), by.get("sudan")
    if not hilal:
        return []
    season = SE.season_of(_cairo_day(now).isoformat())
    pool, up = SE.results_pool(matches, archive), SE.upcoming_pool(matches, fixtures)
    rows = [SE.form_row(hilal, m) for m in SE.club_results(hilal, pool)
            if m.get("competition") == SUDAN_COMP and SE.season_of(m.get("kickoff")) == season]
    lines = []
    if rows:
        w, d, l = (sum(1 for r in rows if r["mark"] == k) for k in "WDL")
        gf, ga = sum(r["gf"] for r in rows), sum(r["ga"] for r in rows)
        n = len(rows)
        played = "مباراة واحدة" if n == 1 else "مباراتين" if n == 2 else f"{n} مباريات" if n <= 10 else f"{n} مباراة"
        lines.append(f"🇸🇩 {hilal['name']} لعب {played} في {SE.comp_label(SUDAN_COMP)} هذا الموسم.")
        lines.append(f"فوز {w}، تعادل {d}، خسارة {l}.")
        lines.append(f"سجل {gf} واستقبل {ga}." if ga else f"سجل {gf} ولم تستقبل شباكه أي هدف.")
    nxt, nline = _next_line(SE, hilal, up, now)
    if nline:
        lines.append(f"المباراة القادمة: {nline}")
    nt_nxt, nt_line = _next_line(SE, nt, up, now) if nt else (None, None)
    if nt_line:
        lines.append(f"منتخب السودان: {nt_line}")
    if not rows and not nxt and not nt_nxt:
        return []
    iso = _cairo_day(now).isocalendar()
    return [SE.event(KIND_SUDAN, f"{iso[0]}-W{iso[1]:02d}", "ركن السودان: الهلال السوداني ومنتخب السودان", lines,
                     f"{SE.SITE}/team/al-hilal-sudan", "صفحة الهلال السوداني",
                     ["#الهلال_السوداني", "#السودان", SE.comp_tag(SUDAN_COMP)], competition=SUDAN_COMP,
                     record={"played": len(rows), "rows": rows[-10:]},
                     next_match=({"match_id": nxt.get("match_id"), "kickoff": nxt.get("kickoff"),
                                  "koff_time": nxt.get("koff_time")} if nxt else None))]


# ---------------------------------------------------------------- «سؤال الجون»
def _league_rows(pool, comp):
    """team (Arabic) -> its finished league results, oldest first, as
    (mark, goals for, goals against)."""
    SE = _se()
    out = {}
    ms = sorted((m for m in pool if m.get("competition") == comp),
                key=lambda m: (str(m.get("kickoff") or ""), m.get("koff_time") or ""))
    for m in ms:
        hs, as_ = int(m["home_score"]), int(m["away_score"])
        h, a = SE._side_names(m)
        out.setdefault(h, []).append(("W" if hs > as_ else "D" if hs == as_ else "L", hs, as_))
        out.setdefault(a, []).append(("W" if as_ > hs else "D" if hs == as_ else "L", as_, hs))
    return out


def question_of(pool, day, comps=QUESTION_COMPS, n=QUESTION_N):
    """The day's riddle: (competition, team, its last n results) - chosen by
    the DATE alone (the competition by the day's number, the team by a hash
    of the date over the names in alphabetical order), so yesterday's answer
    can be worked out again today. A league changes every day; a team with
    fewer than n results is stepped over. None when no league has one."""
    for step in range(len(comps)):
        comp = comps[(day.toordinal() + step) % len(comps)]
        rows = _league_rows(pool, comp)
        names = sorted(t for t, r in rows.items() if len(r) >= n)
        if not names:
            continue
        i = int(hashlib.md5(day.isoformat().encode()).hexdigest(), 16) % len(names)
        return comp, names[i], rows[names[i]][-n:]
    return None


_MARK = {"W": "فوز", "D": "تعادل", "L": "خسارة"}


def goon_question(matches, archive, today=None):
    """One riddle a day from QUESTION_FROM_H (Cairo). The event carries
    `prev_ref` and `prev_line` (yesterday's answer): fb_post puts the line
    first only when yesterday's question is on record in the store."""
    SE = _se()
    now = SE._now(today)
    if not _after(now, today, QUESTION_FROM_H):
        return []
    day = _cairo_day(now)
    pool = SE.results_pool(matches, archive)
    q = question_of(pool, day)
    if not q:
        return []
    comp, team, res = q
    seq = "، ".join(f"{_MARK[k]} {gf}-{ga}" for k, gf, ga in res)
    lines = ["❓ سؤال الجون",
             f"فريق من {SE.comp_label(comp)}.",
             f"آخر {len(res)} مباريات له في الدوري بالترتيب: {seq}.",
             "من هو الفريق؟ اكتب إجابتك في التعليقات.",
             "الإجابة غدًا مع السؤال الجديد."]
    prev = day - datetime.timedelta(days=1)
    pq = question_of(pool, prev)
    return [SE.event(KIND_QUESTION, day.isoformat(), "سؤال الجون", lines, None, None,
                     ["#سؤال_الجون", SE.comp_tag(comp)], competition=comp, answer=team,
                     results=[{"mark": k, "gf": gf, "ga": ga} for k, gf, ga in res],
                     prev_ref=prev.isoformat(), prev_line=(f"✅ إجابة سؤال أمس: {pq[1]}." if pq else None))]


def with_prev(ev, on_record):
    """The post's text: yesterday's answer first when yesterday's question
    was really posted (on_record(kind, ref) -> bool)."""
    if ev.get("prev_line") and ev.get("prev_ref") and on_record(ev["kind"], ev["prev_ref"]):
        return ev["prev_line"] + "\n\n" + ev["text"]
    return ev["text"]


# ---------------------------------------------------------------- «الصاعد والهابط»
MOVERS_COMPS = ("Egyptian Premier League", "Turkish Super Lig", "Premier League", "Primera Division",
                "Saudi Pro League")
MOVERS_FROM_H = 21           # Cairo, the day after the round's last match
MOVERS_MIN = 2               # a move of one place is not a story
MOVERS_EACH = 2              # the two biggest climbs and the two biggest drops
MOVERS_MAX = 2               # leagues an evening


def _places(n):
    n = int(n)
    return "مركزًا واحدًا" if n == 1 else "مركزين" if n == 2 else f"{n} مراكز" if n <= 10 else f"{n} مركزًا"


def round_moves(table, round_matches):
    """[(team, before, after)] for the sides whose place BEFORE the round is
    certain. after = the official position. before is rebuilt by taking the
    round's own points off the official table - and a side level on points
    with another before the round has no certain place (the tie-breakers
    are the league's, not ours), so it is left out. [] when a side of the
    round is not in the table."""
    SE = _se()
    rows = {SE.ar_team(r.get("team") or ""): r for r in table or [] if r.get("team")}
    got = {t: 0 for t in rows}
    for m in round_matches:
        h, a = SE._side_names(m)
        if h not in rows or a not in rows or not SE._finished(m):
            return []
        hs, as_ = int(m["home_score"]), int(m["away_score"])
        got[h] += 3 if hs > as_ else 1 if hs == as_ else 0
        got[a] += 3 if as_ > hs else 1 if hs == as_ else 0
    before = {t: int(rows[t].get("pts") or 0) - got[t] for t in rows}
    if any(v < 0 for v in before.values()):
        return []
    out = []
    for t, p in before.items():
        if sum(1 for u, q in before.items() if u != t and q == p):
            continue
        out.append((t, 1 + sum(1 for q in before.values() if q > p), int(rows[t].get("pos") or 0)))
    return out


def round_movers(matches, fixtures, standings, today=None, comps=MOVERS_COMPS):
    """The evening after a league round ended: who climbed and who dropped.
    Only when the table we hold IS the table after that round - no match of
    a later round started, no other match of the league played since the
    round began."""
    SE = _se()
    now = SE._now(today)
    if not _after(now, today, MOVERS_FROM_H):
        return []
    yesterday = (_cairo_day(now) - datetime.timedelta(days=1)).isoformat()
    fresh = {str(m.get("match_id")): m for m in matches or []}
    tables = {s.get("competition"): s for s in standings or []}
    found = []
    for fx in fixtures or []:
        comp = fx.get("competition")
        st = tables.get(comp) or {}
        if comp not in comps or st.get("zeroed") or not st.get("table"):
            continue
        rounds = [(r.get("round"), [fresh.get(str(m.get("match_id")), m) for m in r.get("matches") or []])
                  for r in fx.get("rounds") or [] if r.get("matches")]
        for rn, ms in rounds:
            if not all(SE._finished(m) for m in ms):
                continue
            days = sorted(str(m.get("kickoff") or "")[:10] for m in ms)
            if days[-1] != yesterday:
                continue
            others = [m for r2, ms2 in rounds if r2 != rn for m in ms2]
            if any(SE._started(m) and str(m.get("kickoff") or "")[:10] >= days[0] for m in others):
                continue                    # the table has moved on: it is not this round's table
            # the table must already hold this round (the feed's table can
            # lag its results by a refresh): else «before» would be rebuilt
            # from a table that is itself the one before
            if max(int(r.get("played") or 0) for r in st["table"]) < int(rn or 0):
                continue
            moves = [(t, b, a, b - a) for t, b, a in round_moves(st["table"], ms)]
            up = sorted((x for x in moves if x[3] >= MOVERS_MIN), key=lambda x: (-x[3], x[2]))[:MOVERS_EACH]
            down = sorted((x for x in moves if x[3] <= -MOVERS_MIN), key=lambda x: (x[3], x[2]))[:MOVERS_EACH]
            if not up and not down:
                continue
            lines = [f"📈 حركة الجدول بعد الجولة {rn} من {SE.comp_label(comp)}."]
            lines += [f"{t} تقدم {_places(mv)}: من المركز {b} إلى {a}." for t, b, a, mv in up]
            lines += [f"{t} تراجع {_places(-mv)}: من المركز {b} إلى {a}." for t, b, a, mv in down]
            season = SE.season_of(days[0])
            found.append((max(abs(x[3]) for x in up + down), SE.event(
                KIND_MOVERS, f"{comp}:R{rn}:{season}", f"حركة الجدول بعد الجولة {rn} من {SE.comp_label(comp)}", lines,
                SE.comp_url(comp, "standings"), "الجدول كاملًا",
                [SE.comp_tag(comp)] + [SE._club_tag(x[0]) for x in (up + down)[:2]],
                competition=comp, round=rn, season=season,
                moves=[{"team": t, "before": b, "after": a,
                        "crest": next((r.get("crest") for r in st["table"] if SE.ar_team(r.get("team") or "") == t), None)}
                       for t, b, a, _ in up + down])))
    found.sort(key=lambda x: -x[0])
    return [ev for _, ev in found[:MOVERS_MAX]]


# ---------------------------------------------------------------- «محترفونا هذا الأسبوع»
ABROAD_FILE = "abroad_players.json"      # repo root: the user's list (player as the feed writes him + his club)
ABROAD_WEEKDAY, ABROAD_FROM_H = 0, 13    # Monday 13:00 Cairo


def load_abroad(path=None):
    """[{name, team, nation}] - the hand-kept list. A name is matched EXACTLY
    and only in his own club's matches: names repeat across leagues, and a
    goal credited to the other side is an own goal."""
    import io
    import json
    import os
    p = path or os.path.join(os.path.dirname(os.path.abspath(__file__)), ABROAD_FILE)
    try:
        with io.open(p, encoding="utf-8") as f:
            rows = json.load(f).get("players") or []
    except (OSError, ValueError):
        return []
    return [r for r in rows if isinstance(r, dict) and (r.get("name") or "").strip() and (r.get("team") or "").strip()]


def abroad_week(matches, archive, today=None, players=None):
    """Monday: the goals of the listed players in the seven days before."""
    SE = _se()
    now = SE._now(today)
    if now.weekday() != ABROAD_WEEKDAY or not _after(now, today, ABROAD_FROM_H):
        return []
    players = load_abroad() if players is None else players
    if not players:
        return []
    day = _cairo_day(now)
    lo, hi = (day - datetime.timedelta(days=7)).isoformat(), (day - datetime.timedelta(days=1)).isoformat()
    pool = sorted((m for m in SE.results_pool(matches, archive) if lo <= str(m.get("kickoff") or "")[:10] <= hi and m.get("goals")),
                  key=lambda m: (str(m.get("kickoff") or ""), m.get("koff_time") or ""))
    lines, who = [], []
    for p in players:
        name, team = p["name"].strip(), p["team"].strip()
        for m in pool:
            h, a = SE._side_names(m)
            side = "h" if h == team else "a" if a == team else None
            if not side:
                continue
            n = sum(1 for g in m["goals"] if g.get("side") == side and (g.get("player") or "").strip() == name)
            if not n:
                continue
            hs, as_ = int(m["home_score"]), int(m["away_score"])
            gf, ga = (hs, as_) if side == "h" else (as_, hs)
            opp = a if side == "h" else h
            how = (f"في الفوز {gf}-{ga} على {opp}" if gf > ga else f"في التعادل {gf}-{ga} مع {opp}" if gf == ga
                   else f"في الخسارة {gf}-{ga} أمام {opp}")
            goals = "هدفًا" if n == 1 else "هدفين" if n == 2 else f"{n} أهداف"
            lines.append(f"{name} سجل {goals} لـ{team} {how}.")
            if name not in who:
                who.append(name)
    if not lines:
        return []
    iso = day.isocalendar()
    return [SE.event(KIND_ABROAD, f"{iso[0]}-W{iso[1]:02d}", "محترفونا هذا الأسبوع", ["🌍 محترفونا هذا الأسبوع"] + lines,
                     SE.SITE + "/", "كل النتائج", [SE._club_tag(w) for w in who[:3]],
                     players=who, week=[lo, hi])]


# ---------------------------------------------------------------- «ساعة الأهداف»
# The night's ONE match on the goal dial (goal_clock.py; user 2026-11-20:
# «شكل ساعة الأهداف جميلة اعملها»). Not a SOCIAL kind: he saw the card and
# asked for it, so it goes out with the other news-from-the-data posts.
KIND_CLOCK = "goal-clock"
CLOCK_MIN_GOALS = 3          # a dial with one mark on it is not a picture
CLOCK_FROM_H = 23            # Cairo, with the night's results


NIGHT_OPEN_H = 3.0           # a match is given this long after its kick-off to end and be recorded


def night_open(matches, day, clock, ours=lambda m: True):
    """True while a match of `day` that counts (`ours`) is not finished: in
    play, or kicked off less than NIGHT_OPEN_H hours ago (or still to kick
    off). A fixture the feed never closes stops holding the night after that."""
    SE = _se()
    for m in matches or []:
        if str(m.get("kickoff") or "")[:10] != day or not ours(m) or SE._finished(m):
            continue
        if (m.get("status") or "").upper() == "LIVE":
            return True
        k = SE._kick_dt(m)
        if k and (clock - k).total_seconds() < NIGHT_OPEN_H * 3600:
            return True
    return False


def goal_clock_night(matches, archive, details, today=None):
    """At most one event a night: the night's match (the same pick as the
    results card and reel - day_card.day_hero) when it had CLOCK_MIN_GOALS
    goals, else the match of the leagues of the bar / our clubs / the Arab
    national teams with the most goals. Only a match whose goal list adds
    up to its score (goal_clock.goals_of)."""
    import day_card as DC
    import goal_clock as GC
    from site_lib.competitions import LEAGUE_BAR, is_arab_nation_match
    from site_lib.matchdata import match_details_index
    from site_lib.names import _is_ticker_team
    SE = _se()
    now = clock = SE._now(today)
    if not _after(now, today, CLOCK_FROM_H):
        if not (_is_clock(today) and now.hour < 3):
            return []
        now = now - datetime.timedelta(days=1)
    day = _cairo_day(now).isoformat()
    if not details:
        return []
    ours = lambda m: m.get("competition") in LEAGUE_BAR or _is_ticker_team(m) or is_arab_nation_match(m)   # noqa: E731
    # the night is not over while one of its matches is in play: on
    # 2026-11-24 the dial went out at 23:00 with an under-17 match while
    # Real Madrid 5-1 PSV (22:00) was still being played, and the day's one
    # post was spent. The next run asks again, until 03:00.
    if _is_clock(today) and night_open(matches, day, clock, ours):
        return []
    idx = match_details_index(details)
    rows = []
    for m in SE.results_pool(matches, archive):
        if str(m.get("kickoff") or "")[:10] != day:
            continue
        if not ours(m):
            continue
        m = dict(m, status="FINISHED")
        goals = GC.goals_of(m, idx)
        if goals and len(goals) >= CLOCK_MIN_GOALS:
            rows.append((m, goals))
    if not rows:
        return []
    hero = DC.day_hero([m for m, _ in rows])
    pick = next(((m, g) for m, g in rows if hero is not None and m.get("match_id") == hero.get("match_id")), None)
    if pick is None or not (DC.day_hero([pick[0]]) and (_is_ticker_team(pick[0]) or is_arab_nation_match(pick[0]))):
        # none of ours tonight: the dial with the most on it
        pick = max(rows, key=lambda r: (len(r[1]), -rows.index(r)))
    m, goals = pick
    h, a = SE._side_names(m)
    hs, as_ = int(m["home_score"]), int(m["away_score"])
    lines = [f"🎯 ساعة الأهداف: {h} {hs}-{as_} {a}."]
    for g in goals:
        who = (g["player"] or "هدف") + (" (عكسي)" if g["own"] else "")
        lines.append(f"الدقيقة {g['minute']}: {who} — {h if g['side'] == 'h' else a}.")
    return [SE.event(KIND_CLOCK, day, f"ساعة الأهداف: {h} {hs}-{as_} {a}", lines,
                     f"{SE.SITE}/m/{m.get('match_id')}", "أحداث المباراة",
                     [SE.comp_tag(m.get("competition")), SE._club_tag(h), SE._club_tag(a)],
                     competition=m.get("competition"),
                     match={k: m.get(k) for k in ("match_id", "home", "away", "home_score", "away_score", "home_badge",
                                                  "away_badge", "competition", "kickoff")},
                     goals=goals)]


# ---------------------------------------------------------------- «ساعة أهداف الشهر»
# A club's whole month on one goal dial (club_clock.py; user 2026-11-20:
# «اعمل 11»). One club a day in the first days of a month, for the month
# before - the Egyptian three and الهلال السوداني, in this order.
KIND_MONTH = "club-month-clock"
MONTH_CLUBS = ("al-ahly", "zamalek", "pyramids", "al-hilal-sudan")
MONTH_FROM_H = 18


def club_month(matches, archive, details, today=None, clubs=MONTH_CLUBS):
    """The club whose day it is (day 1 = the first of `clubs`, day 2 the
    second ...), when its month before is whole in our data
    (club_clock.month_info) - else nothing that day."""
    import club_clock as CC
    from site_lib.matchdata import match_details_index
    SE = _se()
    now = SE._now(today)
    day = _cairo_day(now)
    if day.day > len(clubs) or not _after(now, today, MONTH_FROM_H) or not details:
        return []
    slug = clubs[day.day - 1]
    prev = (day.replace(day=1) - datetime.timedelta(days=1)).strftime("%Y-%m")
    pool = {str(m.get("match_id")): dict(m, status=(m.get("status") or "FINISHED"))
            for m in SE.results_pool(matches, archive) if m.get("match_id")}
    info = CC.month_info(slug, prev, pool, match_details_index(details))
    if not info:
        return []
    club, nf, na = info["club"], len(info["goals_for"]), len(info["goals_against"])
    lines = [f"🎯 ساعة أهداف {club} في {CC.month_ar(prev)}.",
             f"سجل {nf} واستقبل {na} في {CC._matches(info['matches'])}."]
    top = max(info["bands_for"])
    if top and info["bands_for"].count(top) == 1:
        lo, hi = CC.BANDS[info["bands_for"].index(top)]
        lines.append(f"أكثر ربع ساعة سجل فيه: من الدقيقة {lo} إلى {hi} (" + ("هدف واحد" if top == 1 else "هدفان" if top == 2 else f"{top} أهداف" if top <= 10 else f"{top} هدفًا") + ").")
    return [SE.event(KIND_MONTH, f"{slug}:{prev}", f"ساعة أهداف {club} في {CC.month_ar(prev)}", lines,
                     f"{SE.SITE}/team/{slug}", f"صفحة {club}", [SE._club_tag(club), "#ساعة_الأهداف"],
                     info=info)]
