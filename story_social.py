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
SOCIAL_KINDS = (KIND_NUMBER, KIND_SCENARIO, KIND_SUDAN, KIND_QUESTION)

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
                     match={"match_id": m.get("match_id"), "home": h, "away": a, "home_score": hs, "away_score": as_},
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
