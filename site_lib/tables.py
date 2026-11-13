"""League tables, fixtures and rounds panels, scorers lists, the clubs
panel, match rows and the match-details block.

Moved verbatim out of build_site.py (2026-09-26, tools/move_names.py):
source and comments exactly as they were there. Edit here; build_site
imports these back under the same names."""
from site_lib.clubs import TEAM_SPELLINGS, TICKER_TEAMS
from site_lib.crests import comp_icon, local_crest
from site_lib.dates import fmt_day
from site_lib.matchdata import _athlete_img, _min_key, _pitch_rows, _pshort, _rt_class, score_pill
from site_lib.names import ar_team, comp_label
from site_lib.stats import form_dots
from site_lib.text import _pval, esc
from site_lib.ticker import _tk_date


def team_key(name):
    """A team as counted by team_results: one key for a club's spellings."""
    return TEAM_SPELLINGS.get(name, name)


def team_results(games):
    """team_key -> [(match, 'w'|'d'|'l')] in kick-off order, from finished matches."""
    out = {}
    for m in sorted(games or [], key=lambda m: (m.get("kickoff") or "", m.get("koff_time") or "")):
        hs, as_ = m.get("home_score"), m.get("away_score")
        if hs is None or as_ is None:
            continue
        for team, mine, theirs in ((m.get("home"), hs, as_), (m.get("away"), as_, hs)):
            r = "w" if mine > theirs else "d" if mine == theirs else "l"
            out.setdefault(team_key(team), []).append((m, r))
    return out


def standings_table(comp, rows, past=False, season_label="", zeroed=False, form_map=None,
                    embedded=False, games=None, pages=None, store_src=None, title=None):
    """League standings table (FotMob-style). Hidden until its league is picked.
    `zeroed` = the new season hasn't kicked off yet, so this is the new season's
    team list with everything at 0; it gets a "new season" badge.
    `past` = legacy flag (last season's final table) kept for old data files.

    `games` = the competition's finished matches (the season pool): then
    «لعب / ف / ت / خ» become buttons opening those matches (user, 2026-11-01:
    «عايز ارقام الخاصة ب لعب و فاز وتعادل وخسر تكون لينكات ولما نضغط عليها يجيب
    المباريات دى»; LT_GAMES_JS draws the list). Only for a team whose four
    numbers ALL equal what we hold - a «لعب 10» opening four matches would be
    worse than a plain number. `pages(m)` = the id of m's /m page or None
    (no link); the season pool and the pages can carry different ids for the
    same 365scores match, so the caller also matches by clubs + day.

    `store_src` (2026-11-07, the match pages: «عايز لما اضغط على الرقم فاز
    لفريق يجيب المباريات اللى فاز فيها»): the buttons and each row's ids as
    above, but the store of match rows is NOT inlined - an empty .lt-games
    with data-src points at the standings page that holds it, and
    LT_GAMES_JS fetches it on the first tap. Inlining it would copy the
    league's whole season into each of the ~1,450 match pages."""
    def cell(v):
        return "0" if v is None else esc(str(v))
    res = team_results(games) if games is not None else {}
    used = {}
    body = []
    for r in rows:
        crest = (f'<img src="{esc(local_crest(r.get("crest")))}" alt="" loading="lazy">'
                 if r.get("crest") else "")
        fm = form_dots((form_map or {}).get(r.get("team"), [])) if form_map is not None else ""
        fmtd = f'<td class="lt-form">{fm}</td>' if form_map is not None else ""
        mine = res.get(team_key(r.get("team"))) or []
        n = {k: sum(1 for _, x in mine if x == k) for k in "wdl"}
        live = bool(mine) and (len(mine), n["w"], n["d"], n["l"]) == tuple(
            r.get(k) or 0 for k in ("played", "won", "draw", "lost"))

        def num(key, k):
            v = cell(r.get(key))
            if not live or not (r.get(key) or 0):
                return f'<td>{v}</td>'
            return f'<td><button type="button" class="lt-n" data-k="{k}">{v}</button></td>'
        tr_attr = ""
        if live:
            for m, _ in mine:
                used[str(m["match_id"])] = m
            tr_attr = (f' data-tn="{esc(ar_team(r.get("team")))}" data-gm="'
                       + ",".join(f'{m["match_id"]}:{x}' for m, x in mine) + '"')
        body.append(
            f'<tr{tr_attr}><td class="lt-pos">{cell(r.get("pos"))}</td>'
            f'<td class="lt-team">{crest}<bdi>{esc(ar_team(r.get("team")))}</bdi></td>'
            f'{fmtd}'
            f'{num("played", "p")}{num("won", "w")}'
            f'{num("draw", "d")}{num("lost", "l")}'
            f'<td class="lt-gf">{cell(r.get("gf"))}</td><td class="lt-ga">{cell(r.get("ga"))}</td>'
            f'<td>{cell(r.get("gd"))}</td><td class="lt-pts">{cell(r.get("pts"))}</td></tr>')
    # every match once; the buttons' rows list ids and the script clones these
    store = ""
    if used and store_src:
        store = f'<div class="lt-games" data-src="{esc(store_src)}" hidden></div>'
    elif used:
        items = []
        for mid, m in used.items():
            inner = f'<span class="lgm-d">{esc(fmt_day(m.get("kickoff")))}</span>{fixture_mini(m)}'
            page = m["match_id"] if pages is None else pages(m)
            if page:
                items.append(f'<a class="lgm" data-id="{mid}" href="/m/{page}">{inner}</a>')
            else:
                items.append(f'<div class="lgm" data-id="{mid}">{inner}</div>')
        store = f'<div class="lt-games" hidden>{"".join(items)}</div>'
    if zeroed:
        badge = (f'<span class="lt-past">الموسم الجديد'
                 f'{(" " + esc(season_label)) if season_label else ""} — لم ينطلق بعد</span>')
    elif past:
        badge = (f'<span class="lt-past">الموسم الماضي'
                 f'{(" " + esc(season_label)) if season_label else ""}</span>')
    else:
        badge = ""
    return (f'<div class="ltable" data-comp="{esc(comp)}"{"" if embedded else " hidden"}>'
            f'<div class="lt-head">{comp_icon(comp)} {esc(title) if title else "جدول ترتيب " + esc(comp_label(comp))}{badge}</div>'
            f'<div class="lt-scroll"><table class="lt"><thead><tr>'
            f'<th class="lt-pos">#</th><th class="lt-team">الفريق</th>'
            + (f'<th class="lt-form" title="آخر 5 مباريات">آخر 5</th>' if form_map is not None else "") +
            f'<th title="لعب">لعب</th><th title="فاز">ف</th><th title="تعادل">ت</th>'
            f'<th title="خسر">خ</th><th class="lt-gf" title="له">له</th><th class="lt-ga" title="عليه">عليه</th>'
            f'<th title="الفارق">+/-</th><th class="lt-pts">نقاط</th></tr></thead>'
            f'<tbody>{"".join(body)}</tbody></table></div>{store}</div>')


def group_tables_panel(comp, groups, focus_tps=()):
    """A group stage, one group at a time behind the rounds navigator
    (‹ المجموعة › - ROUNDS_JS drives it like the rounds; user 2026-11-13).
    Opens on the first group holding a club/team we follow (focus_tps: the
    TEAM_PAGES entries - منتخب مصر for the AFCON qualifiers), else group 1."""
    from site_lib.names import _team_match
    groups = [g for g in groups or [] if g.get("table")]
    if not groups:
        return ""
    cur = groups[0]["num"]
    for g in groups:
        if any(_team_match(tp, {"home": r.get("team") or "", "away": "", "competition": comp})
               for tp in focus_tps for r in g["table"]):
            cur = g["num"]
            break
    parts = [f'<div class="lg-fix rounds-panel groups-panel" data-comp="{esc(comp)}" data-current="{cur}">',
             f'<div class="fx-head">{comp_icon(comp)} مجموعات {esc(comp_label(comp))}</div>',
             '<div class="rnav">'
             '<button type="button" class="rn-prev" aria-label="المجموعة السابقة">‹</button>'
             '<span class="rn-label"></span>'
             '<button type="button" class="rn-next" aria-label="المجموعة التالية">›</button></div>',
             '<div class="rounds">']
    for g in groups:
        parts.append(f'<div class="round" data-round="{g["num"]}" data-label="{esc(g["name"])}" hidden>'
                     + standings_table(comp, g["table"], embedded=True, title=g["name"]) + '</div>')
    parts.append('</div></div>')
    return "".join(parts)


def fixture_mini(m, link=None):
    """Compact fixture row for the league side panel (FotMob-style).
    link (2026-11-13, SEO + site review): the row IS the link to the match
    page - used on /fixtures/<slug> only, where 0 of 2,951 rows linked
    anywhere and 284 indexable match pages had no inbound link at all."""
    st = (m.get("status") or "").upper()
    def cr(u):
        return f'<img src="{esc(local_crest(u))}" alt="" loading="lazy">' if u else '<span class="fx-ph">⚽</span>'
    if st in ("FINISHED", "LIVE"):
        # the score is its own grid column here, so it needs the pill too -
        # a bare "2-1" between the two columns puts the home goals on the
        # away side (same bug as the record, 2026-09-16)
        mid = score_pill(m.get("home_score"), m.get("away_score"), "fx-sc sc-in")
    else:
        mid = f'<span class="fx-time">{esc(m.get("koff_time") or "")}</span>'
    _open, _close = ((f'<a class="fx" href="{esc(link)}">', '</a>') if link
                     else ('<div class="fx">', '</div>'))
    return (f'{_open}'
            f'<span class="fx-home"><bdi>{esc(ar_team(m.get("home")))}</bdi>{cr(m.get("home_badge"))}</span>'
            f'{mid}'
            f'<span class="fx-away">{cr(m.get("away_badge"))}<bdi>{esc(ar_team(m.get("away")))}</bdi></span>{_close}')


def league_rounds_panel(comp, fx, embedded=False, only_current=False, more_url=None, pages=None):
    """FotMob-style rounds panel: a ‹ round › navigator + every round of the
    season, each round's matches grouped by day. JS shows one round at a time."""
    from collections import OrderedDict
    rounds = fx.get("rounds") or []
    current = fx.get("current") or (rounds[0]["round"] if rounds else 1)
    parts = [f'<div class="lg-fix rounds-panel" data-comp="{esc(comp)}" '
             f'data-current="{current}"{"" if embedded else " hidden"}>',
             f'<div class="fx-head">{comp_icon(comp)} {esc(comp_label(comp))}</div>',
             ('' if only_current else
              '<div class="rnav">'
              '<button type="button" class="rn-prev" aria-label="الجولة السابقة">‹</button>'
              '<span class="rn-label"></span>'
              '<button type="button" class="rn-next" aria-label="الجولة التالية">›</button></div>'),
             '<div class="rounds">']
    if only_current:
        # /matches ships ONE round, not the season: the hidden rest was 2,206
        # fixture rows and 4,955 crest tags on the site's second-busiest page
        rounds = [r for r in rounds if r.get("round") == current] or rounds[:1]
    for r in rounds:
        _hid = "" if only_current else " hidden"
        parts.append(f'<div class="round" data-round="{r["round"]}" '
                     f'data-label="{esc(r.get("label") or "الجولة " + str(r["round"]))}"{_hid}>')
        days = OrderedDict()
        for m in r.get("matches", []):
            days.setdefault(m.get("kickoff") or "", []).append(m)
        for d in sorted(days.keys()):
            parts.append(f'<div class="fx-day">{esc(fmt_day(d))}</div>')
            for m in days[d]:
                # `pages` = the match ids that have a page (fixtures pages only)
                parts.append(fixture_mini(
                    m, link=(f'/m/{m["match_id"]}.html'
                             if pages is not None and m.get("match_id") in pages else None)))
        parts.append('</div>')
    parts.append('</div>')
    if more_url:
        parts.append(f'<p class="more-link"><a href="{esc(more_url)}">كل جولات '
                     f'{esc(comp_label(comp))} ←</a></p>')
    parts.append('</div>')
    return "".join(parts)


def round_on_show(fx):
    """(round number, its matches) for the «الجولة» block of /standings: the
    round with a live match, else the round of the nearest upcoming one, else
    the feed's `current`. Not `current` alone: on 2026-10-31 it still said
    Spain 8 (all played but one match postponed to December) while round 11
    was on, and Saudi 10 while 12 was on. POSTPONED rows never pick a round."""
    rounds = (fx or {}).get("rounds") or []
    pool = [m for r in rounds for m in r.get("matches", [])]
    live = [m for m in pool if (m.get("status") or "").upper() == "LIVE"]
    up = sorted((m for m in pool if (m.get("status") or "").upper() == "UPCOMING"),
                key=lambda m: (m.get("kickoff") or "", m.get("koff_time") or ""))
    rn = (live or up or [{}])[0].get("round", (fx or {}).get("current"))
    rd = next((r for r in rounds if r.get("round") == rn), None)
    return (rn, rd.get("matches") or []) if rd else (None, [])


def _scorer_face(sc):
    """Player photo when the feed has one, else the club crest, else a ball."""
    u = sc.get("photo") or sc.get("crest") or ""
    if not u:
        return '<span class="ph">⚽</span>'
    cls = "sc-face" if sc.get("photo") else ""
    return f'<img class="{cls}" src="{esc(local_crest(u))}" alt="" loading="lazy">'


def clubs_panel(st_by_comp, sc_ok, sc_by_comp, forms, matches, fixtures):
    """The curated clubs (TICKER_TEAMS) at a glance: position, points, last 5,
    and the club's own top scorer — or its next match while the season hasn't
    given it any of those yet. Skips a club we can't find in any table.
    The next-match pool is matches ∪ the fixtures rounds: matches.json is
    capped at 90 rows, and a club whose opener falls past the cap (Chelsea's
    24/08 game did) would otherwise show no fixture at all."""
    pool = list(matches)
    for fx in fixtures:
        for rd in fx.get("rounds", []):
            pool.extend(rd.get("matches", []))
    upcoming = sorted((m for m in pool
                       if (m.get("status") or "").upper() == "UPCOMING"),
                      key=lambda m: (m.get("kickoff") or "", m.get("koff_time") or ""))
    cards = []
    from site_lib.names import _in_scope, _tok_hit
    for token, only_comp in TICKER_TEAMS:
        found = None
        for comp, st in st_by_comp.items():
            # scope may be a tuple since 2026-09-02 (_in_scope knows); an Arabic
            # token must equal the row's name - «الأهلي طرابلس» shares a table
            # with «الأهلي» in the Confederation Cup (2026-10-17)
            if not _in_scope(only_comp, comp):
                continue
            for r in st["table"]:
                if _tok_hit(token, {"home": r.get("team") or "", "away": ""}):
                    found = (comp, r)
                    break
            if found:
                break
        if not found:
            continue
        comp, row = found
        name = ar_team(row.get("team"))
        max_played = max((x.get("played") or 0) for x in st_by_comp[comp]["table"])
        crest = (f'<img src="{esc(local_crest(row.get("crest")))}" alt="" loading="lazy">'
                 if row.get("crest") else '<span class="ph">⚽</span>')
        res = (forms.get(comp) or {}).get(row.get("team")) or []
        if row.get("played"):
            rank = (f'<span class="cl-pos">#{esc(str(row.get("pos")))}</span>'
                    f'<span class="cl-pts">{row.get("pts")} نقطة</span>')
        elif max_played:
            rank = '<span class="cl-soon">لم يلعب بعد</span>'
        else:
            rank = '<span class="cl-soon">الموسم لم ينطلق</span>'
        form = f'<span class="cl-form">{form_dots(res)}</span>' if res else ""
        top = ""
        if sc_ok.get(comp):
            best = next((x for x in sc_by_comp.get(comp, []) if x.get("team") == name), None)
            if best:
                top = (f'<span class="cl-sc">هدافه: <b>{esc(best.get("name"))}</b>'
                       f' · {_pval(best)}</span>')
        if not top and not row.get("played"):
            # nothing played yet -> the next fixture is the useful line
            nxt = next((m for m in upcoming
                        if (not only_comp or (m.get("competition") or "") == only_comp)
                        and (token in (m.get("home") or "")
                             or token in (m.get("away") or ""))), None)
            if nxt:
                rival = (nxt.get("away") if token in (nxt.get("home") or "")
                         else nxt.get("home"))
                when = _tk_date(nxt.get("kickoff"))
                top = (f'<span class="cl-sc">القادمة: <b><bdi>{esc(ar_team(rival))}</bdi></b>'
                       f' · {esc(when)}'
                       + (f' {esc(nxt.get("koff_time"))}' if nxt.get("koff_time") else "")
                       + '</span>')
        cards.append(f'<a class="cl-card" href="/matches.html">'
                     f'<span class="cl-top">{crest}<span class="cl-n"><bdi>{esc(name)}</bdi></span></span>'
                     f'<span class="cl-lg">{esc(comp_label(comp))}</span>'
                     f'<span class="cl-row">{rank}{form}</span>{top}</a>')
    if not cards:
        return ""
    return ('<section class="stats-sec"><h2 class="lt-head">⭐ أبرز الأندية</h2>'
            f'<div class="cl-grid">{"".join(cards)}</div></section>')


def scorers_list(sc, unit="أهداف"):
    """Chart table: rank, player (+club), value — plus a matches column only
    when the feed actually carries appearances (365scores does not)."""
    has_m = any((x.get("played") or 0) for x in sc)
    m_hd = "<span>مباريات</span>" if has_m else ""
    rows = [f'<div class="sc-list{"" if has_m else " sc-nom"}">'
            f'<div class="sc-hd"><span></span><span>اللاعب</span>'
            f'{m_hd}<span>{esc(unit)}</span></div>']
    for i, x in enumerate(sc, 1):
        club = (f'<span class="sc-club"><bdi>{esc(x.get("team"))}</bdi></span>'
                if x.get("team") else "")
        m_cell = f'<span class="sc-m">{x.get("played")}</span>' if has_m else ""
        rows.append(f'<div class="sc-row"><span class="sc-n">{i}</span>'
                    f'<span class="sc-p">{_scorer_face(x)}'
                    f'<span class="sc-nm"><bdi>{esc(x.get("name"))}</bdi>{club}</span></span>'
                    f'{m_cell}<b class="sc-g">{_pval(x)}</b></div>')
    rows.append('</div>')
    return "".join(rows)


MSTAT_ROWS = (("الأهداف المتوقعة (xG)", "xg", "{:.2f}"), ("xG على المرمى", "xgot", "{:.2f}"),
              ("التسديدات", "shots", "{}"), ("تسديدات على المرمى", "sot", "{}"),
              ("فرص خطيرة", "big", "{}"), ("الاستحواذ", "poss", "{}%"))


def match_stats_html(row, h_ar, a_ar):
    """«أرقام المباراة» on a finished match page (2026-10-07): xG, shots and
    possession from data/match_stats.json, home on the right like the score.
    Nothing when the match has no stats row with xG.

    Bars since 2026-11-06 (user: «اليوزر مبيحبش القراءة بيحب يشوف المعلومات
    من الصور»): each stat is the two values with a label between them and,
    under it, two half-tracks that fill from the centre outward by each
    side's share - the side ahead in our dark blue, the other in grey, like
    FotMob's match stats."""
    if not row or row.get("status") != "ok":
        return ""
    h, a = row.get("h") or {}, row.get("a") or {}
    bars = []
    for label, key, fmt in MSTAT_ROWS:
        if h.get(key) is None or a.get(key) is None:
            continue
        hv, av = h[key], a[key]
        tot = (hv or 0) + (av or 0)
        hp = round(100 * hv / tot) if tot else 0
        ap = (100 - hp) if tot else 0
        lead = "h" if hv > av else ("a" if av > hv else "")
        on = lambda s: " on" if lead == s else ""
        bars.append(
            f'<div class="sb"><div class="sb-l"><b class="sb-v{on("h")}">{fmt.format(hv)}</b>'
            f'<span>{esc(label)}</span><b class="sb-v{on("a")}">{fmt.format(av)}</b></div>'
            f'<div class="sb-t" aria-hidden="true"><span class="sb-h"><i class="{on("h").strip()}" style="width:{hp}%"></i></span>'
            f'<span class="sb-a"><i class="{on("a").strip()}" style="width:{ap}%"></i></span></div></div>')
    if not bars:
        return ""
    return (f'<section class="minfo mstats"><h2>أرقام مباراة {esc(h_ar)} و{esc(a_ar)}</h2>'
            f'<div class="sbars"><div class="sb-teams"><bdi>{esc(h_ar)}</bdi><bdi>{esc(a_ar)}</bdi></div>'
            + "".join(bars) + '</div>'
            '<p class="hintline">الأهداف المتوقعة (xG) تقيس جودة الفرص: كم هدفًا كان يُنتظر من التسديدات نفسها. '
            'المصدر: 365scores.</p></section>')


BOOT_SVG = ('<svg viewBox="0 0 16 16" aria-hidden="true"><path fill="#0f172a" d="M2.2 3.2h3.6l1 3.1'
            ' 4.8 1.9c1.4.5 2.2 1.4 2.2 2.6v.7H2.2z"/><path fill="#0f172a" d="M3 12.3h1.6v1.6H3zm4.2'
            ' 0h1.6v1.6H7.2zm4.2 0H13v1.6h-1.6z"/></svg>')
# the same boot on the scorer lines, in the line's own (light) colour
BOOT_MG = BOOT_SVG.replace('fill="#0f172a"', 'fill="currentColor"')


def _lead_int(v):
    """'19/21 (90%)' -> 19, '4' -> 4, "86'" -> 86; None when not a number."""
    import re as _re
    m = _re.match(r"\s*(\d+)", str(v or ""))
    return int(m.group(1)) if m else None


def motm_html(e, flipped, h_ar, a_ar, home_badge=None, away_badge=None):
    """The top-rated starter, as a card right under the score (2026-11-06,
    the visual replacement of the reading's «الأفضل في اللقاء» line). It says
    «الأعلى تقييمًا في المباراة», not «رجل المباراة»: the rating is
    365scores', and an official man-of-the-match award can go to someone
    else - never a possibly-wrong label. Up to three facts: his goals, his
    assists, then his first non-zero stats. Nothing when fewer than 18
    starters carry a rating (a partial feed must not crown anybody). A tap
    opens his pitch card when he has one (snippets/pitch_js.html, data-pn)."""
    lus = e.get("lineups") or {}
    eh, ea = ("a", "h") if flipped else ("h", "a")
    best, rated = None, 0
    for feed_side, team, badge in ((eh, h_ar, home_badge), (ea, a_ar, away_badge)):
        for p in ((lus.get(feed_side) or {}).get("xi") or []):
            try:
                r = float(p.get("rt"))
            except (TypeError, ValueError):
                continue
            rated += 1
            if best is None or r > best[0]:
                best = (r, p, team, badge)
    if best is None or rated < 18:
        return ""
    r, p, team, badge = best
    name = p.get("name") or ""
    goals = sum(1 for g in e.get("goals") or [] if g.get("player") == name and g.get("tag") != "عكسية")
    asts = sum(1 for g in e.get("goals") or [] if g.get("assist") == name)
    facts = []
    if goals:
        facts.append(("⚽", "هدف" if goals == 1 else ("هدفان" if goals == 2 else f"{goals} أهداف")))
    if asts:
        facts.append((BOOT_SVG, "صناعة هدف" if asts == 1 else ("صناعة هدفين" if asts == 2 else f"صناعة {asts} أهداف")))
    st = p.get("st") or {}
    for key, label in (("23", "تصديات"), ("46", "صناعة فرص"), ("3", "تسديدات"), ("19", "دقة التمرير"),
                       ("39", "تدخلات ناجحة"), ("86", "استعادة الكرة"), ("41", "اعتراضات")):
        if len(facts) >= 3:
            break
        v = st.get(key)
        if v is None or not _lead_int(v):
            continue
        if key == "19":
            import re as _re
            pc = _re.search(r"\((\d+)%\)", v)
            if not pc:
                continue
            facts.append(("", f"{label}: {pc.group(1)}%"))
        else:
            facts.append(("", f"{label}: {_lead_int(v)}"))
    rc = _rt_class(r) or ""
    img = _athlete_img(p)
    src = local_crest(img) if img else None
    ph = (f'<img src="{esc(src)}" alt="" loading="lazy" onerror="this.remove()">' if src else "")
    crest = local_crest(badge) if badge else None
    cr = f'<img src="{esc(crest)}" alt="" loading="lazy">' if crest else ""
    chips = "".join(f'<span>{ic}{" " if ic else ""}{esc(t)}</span>' for ic, t in facts[:3])
    tap = (f' role="button" tabindex="0" aria-label="الأعلى تقييمًا في المباراة: {esc(name)} - تفاصيل اللاعب"'
           if st else "")
    return (f'<section class="motm" data-pn="{esc(name)}"{tap}>'
            f'<span class="motm-ph">{ph}<span class="pp-rt {rc}">{r:.1f}</span></span>'
            f'<span class="motm-b"><span class="motm-k">الأعلى تقييمًا في المباراة</span>'
            f'<b class="motm-n"><bdi>{esc(name)}</bdi></b>'
            f'<span class="motm-t">{cr}<bdi>{esc(team)}</bdi></span>'
            + (f'<span class="motm-f">{chips}</span>' if chips else "")
            + '</span></section>')


def match_details_html(e, flipped, h_ar, a_ar):
    """'أحداث المباراة' timeline (goals+cards+subs) + 'التشكيلة' section."""
    def side(s):
        return ("a" if s == "h" else "h") if flipped else s
    parts = []
    evs = []
    for g in (e.get("goals") or []):
        txt = f'<bdi>{esc(g["player"])}</bdi>' + (
            f' <span class="ev-tag">({esc(g["tag"])})</span>' if g.get("tag") else "")
        evs.append((_min_key(g.get("minute")), side(g.get("side")),
                    g.get("minute"), "⚽", txt))
    for c in (e.get("cards") or []):
        ic = f'<span class="cardic {"r" if c.get("color") == "r" else "y"}"></span>'
        evs.append((_min_key(c.get("minute")), side(c.get("side")),
                    c.get("minute"), ic, f'<bdi>{esc(c["player"])}</bdi>'))
    for s in (e.get("subs") or []):
        txt = (f'<span class="sub-in">▲ <bdi>{esc(s["in"])}</bdi></span> '
               f'<span class="sub-out">▼ <bdi>{esc(s["out"])}</bdi></span>')
        evs.append((_min_key(s.get("minute")), side(s.get("side")),
                    s.get("minute"), "🔁", txt))
    # newest first (user, 2026-11-06: «الدقايق تبدأ من تحت» - the last minute at
    # the top, kick-off at the bottom, like a live feed). reverse=True keeps
    # same-minute events in their insertion order (goal, then card, then sub).
    evs.sort(key=lambda x: x[0], reverse=True)
    if evs:
        parts.append('<section class="minfo"><h2>أحداث المباراة</h2><div class="mtl">')
        for _, sd, mn, ic, txt in evs:
            cell = f'{ic} {txt}'
            mn_t = f'<span dir="ltr">{esc(mn)}′</span>' if mn else ""
            parts.append(f'<div class="tl-r"><div class="tl-h">{cell if sd == "h" else ""}</div>'
                         f'<div class="tl-m">{mn_t}</div>'
                         f'<div class="tl-a">{cell if sd != "h" else ""}</div></div>')
        parts.append('</div></section>')
    lus = e.get("lineups") or {}
    eh, ea = ("a", "h") if flipped else ("h", "a")
    lh, la = lus.get(eh), lus.get(ea)
    ph, pa = _pitch_rows(lh, True), _pitch_rows(la, False)
    if ph and pa:
        # sofascore-style pitch: home XI in the top half, away mirrored below
        def badges(side_key):
            cards = {}
            for c in e.get("cards") or []:
                if side(c.get("side")) == side_key:
                    cur = cards.get(c.get("player"))
                    cards[c.get("player")] = ("r" if c.get("color") == "r"
                                              or cur == "r" else "y")
            off = {s.get("out") for s in e.get("subs") or []
                   if side(s.get("side")) == side_key}
            return cards, off
        # «تشكيلات/ترتيبات فنربخشة – ليفربول» ranked 4 with no click (GSC
        # 2026-11-12): the heading names the match, like the stats one does
        parts.append(f'<section class="minfo"><h2>تشكيل {esc(h_ar)} و{esc(a_ar)}</h2>')
        fh = f' <span class="lu-f" dir="ltr">{esc(lh["formation"])}</span>' if lh.get("formation") else ""
        fa = f' <span class="lu-f" dir="ltr">{esc(la["formation"])}</span>' if la.get("formation") else ""
        # labels live INSIDE the pitch corners so the same markup reads
        # correctly in both orientations (vertical mobile / horizontal desktop)
        parts.append('<div class="pitch" dir="ltr">'
                     '<div class="pt-half"></div><div class="pt-circle"></div>'
                     '<div class="pt-box pt-box-t"></div><div class="pt-box pt-box-b"></div>'
                     f'<span class="pt-lab pt-lab-h"><bdi>{esc(h_ar)}</bdi>{fh}</span>'
                     f'<span class="pt-lab pt-lab-a"><bdi>{esc(a_ar)}</bdi>{fa}</span>')
        # who scored / who assisted, by name (user, 2026-11-06: «جنب اللعيب
        # اللى سجل هدف كورة وجنب اللاعب اللى عمل اسيست حذاء»). Names come from
        # the same 365scores members as the XI, so they match exactly. An own
        # goal is marked on the player who put it in, in red.
        scored, owngoals, assisted = {}, {}, {}
        for g in e.get("goals") or []:
            who = g.get("player")
            if who:
                bucket = owngoals if g.get("tag") == "عكسية" else scored
                bucket[who] = bucket.get(who, 0) + 1
            if g.get("assist"):
                assisted[g["assist"]] = assisted.get(g["assist"], 0) + 1

        # our own boot (the 👟 emoji was a pale grey sneaker on the white disc on
        # Windows and a different shoe on every phone): a dark football boot
        # with three studs, the same on every screen
        boot = ('<svg viewBox="0 0 16 16" aria-hidden="true"><path fill="#0f172a" d="M2.2 3.2h3.6l1 3.1'
                ' 4.8 1.9c1.4.5 2.2 1.4 2.2 2.6v.7H2.2z"/><path fill="#0f172a" d="M3 12.3h1.6v1.6H3zm4.2'
                ' 0h1.6v1.6H7.2zm4.2 0H13v1.6h-1.6z"/></svg>')

        # the player card (2026-11-06, «لما اضغط على لاعب ... زى 365
        # scores»): every starter the feed gave stats for is a button; the
        # card data rides one JSON block and snippets/pitch_js.html opens it
        CARD_ROWS = (("30", "الدقائق"), ("27", "الأهداف"), ("26", "صناعة الأهداف"),
                     ("76", "الأهداف المتوقعة (xG)"), ("shots", "التسديدات (على المرمى)"),
                     ("46", "صناعة الفرص"), ("19", "التمريرات الصحيحة"), ("45", "لمس الكرة"),
                     ("54", "المراوغات الناجحة"), ("39", "التدخلات الناجحة"), ("41", "الاعتراضات"),
                     ("86", "استعادة الكرة"), ("55", "الالتحامات الأرضية"),
                     ("56", "الالتحامات الهوائية"), ("23", "التصديات"), ("35", "أهداف استقبلها"))
        cards_data = []

        def player_events(name):
            out = []
            for g in e.get("goals") or []:
                if g.get("player") == name:
                    out.append(("og" if g.get("tag") == "عكسية" else "g", g.get("minute") or ""))
                if g.get("assist") == name:
                    out.append(("a", g.get("minute") or ""))
            for c in e.get("cards") or []:
                if c.get("player") == name:
                    out.append(("r" if c.get("color") == "r" else "y", c.get("minute") or ""))
            for s in e.get("subs") or []:
                if s.get("out") == name:
                    out.append(("off", s.get("minute") or ""))
            return sorted(out, key=lambda x: _min_key(x[1]))

        def card_rows(st):
            rows = []
            for key, label in CARD_ROWS:
                if key == "shots":
                    if "3" in st:
                        rows.append((label, st["3"] + (f' ({st["4"]})' if "4" in st else "")))
                elif key in st:
                    rows.append((label, st[key].replace("'", "′")))
            return rows

        def ev_badges(name):
            out = ""
            for n, cls, ic, lbl in ((scored.get(name), "", "⚽", "هدف"),
                                    (owngoals.get(name), " og", "⚽", "هدف عكسي"),
                                    (assisted.get(name), " as", boot, "صناعة هدف")):
                if n:
                    cnt = f'<b>{n}</b>' if n > 1 else ""
                    out += (f'<span class="pp-ev{cls}" title="{lbl}" aria-label="{lbl}">'
                            f'{ic}{cnt}</span>')
            return f'<span class="pp-evs">{out}</span>' if out else ""

        for chips, side_key in ((ph, "h"), (pa, "a")):
            cards, off = badges(side_key)
            for x, y, p in chips:
                img = _athlete_img(p)
                src = local_crest(img) if img else None
                num = esc(str(p.get("num"))) if p.get("num") is not None else ""
                ava = (f'<img src="{esc(src)}" alt="" loading="lazy" '
                       'onerror="this.style.display=\'none\';'
                       "this.nextElementSibling.style.display='flex'\">"
                       f'<span class="pp-fb">{num}</span>'
                       if src else f'<span class="pp-fb" style="display:flex">{num}</span>')
                bd = ""
                c = cards.get(p.get("name"))
                if c:
                    bd += f'<span class="pp-card {c}"></span>'
                if p.get("name") in off:
                    bd += '<span class="pp-sub">⇄</span>'
                bd += ev_badges(p.get("name"))
                # a rating badge on this pitch means "how he played in THIS
                # match" — on a pre-match XI the feed's number is a carried-over
                # average, and printing it next to an unplayed match reads as a
                # match rating for a match nobody has played (no possibly-wrong
                # numbers, user rule 2026-08-31)
                rc = None if e.get("pre") else _rt_class(p.get("rt"))
                rt = (f'<span class="pp-rt {rc}">{float(p["rt"]):.1f}</span>'
                      if rc else "")
                cap = '<span class="pp-cap">C</span>' if p.get("cap") else ""
                nm = f'{num + " " if num else ""}{esc(_pshort(p.get("name")))}'
                tap = ""
                if p.get("st") and not e.get("pre"):
                    tap = (f' data-i="{len(cards_data)}" role="button" tabindex="0" '
                           f'aria-label="تفاصيل {esc(p.get("name"))}"')
                    cards_data.append({
                        "n": p.get("name"), "num": p.get("num"), "pos": p.get("pos"),
                        "team": h_ar if side_key == "h" else a_ar, "img": src or "",
                        "rt": f'{float(p["rt"]):.1f}' if rc else "", "rc": rc or "",
                        "ev": player_events(p.get("name")), "st": card_rows(p["st"])})
                parts.append(
                    f'<div class="pp" style="--xv:{x:.1f}%;--yv:{y:.1f}%"{tap}>'
                    f'<span class="pp-ava">{ava}{rt}{bd}{cap}</span>'
                    f'<span class="pp-nm"><bdi>{nm}</bdi></span></div>')
        parts.append('</div>')
        if cards_data:
            import json as _json
            from site_lib.snippets import PITCH_JS
            blob = _json.dumps(cards_data, ensure_ascii=False).replace("</", "<\\/")
            parts.append('<p class="pc-hint">اضغط على أي لاعب لعرض أرقامه في المباراة.</p>'
                         f'<script type="application/json" id="ppData">{blob}</script>{PITCH_JS}')
        parts.append('</section>')
        return "".join(parts)
    if lh or la:
        parts.append(f'<section class="minfo"><h2>تشكيل {esc(h_ar)} و{esc(a_ar)}</h2><div class="lu">')
        for team_name, lu in ((h_ar, lh), (a_ar, la)):
            parts.append('<div class="lu-t">')
            if lu:
                fm = (f' <span class="lu-f" dir="ltr">{esc(lu["formation"])}</span>'
                      if lu.get("formation") else "")
                parts.append(f'<h3><bdi>{esc(team_name)}</bdi>{fm}</h3><ol class="lu-l">')
                for p in lu.get("xi") or []:
                    num = (f'<span class="lu-n">{p["num"]}</span>'
                           if p.get("num") is not None else '<span class="lu-n">·</span>')
                    pos = (f'<span class="lu-p">{esc(p["pos"])}</span>'
                           if p.get("pos") else "")
                    parts.append(f'<li>{num} <bdi>{esc(p["name"])}</bdi>{pos}</li>')
                parts.append('</ol>')
            else:
                parts.append(f'<h3><bdi>{esc(team_name)}</bdi></h3>'
                             '<div class="lu-none">التشكيلة غير متاحة</div>')
            parts.append('</div>')
        parts.append('</div></section>')
    return "".join(parts)


def match_row(m, show_time=False, show_comp=True, goals=None, link=None,
              show_date=False, highlight=None, card_link=True, show_assist=False):
    """show_date (2026-10-08, user: «حط هنا برضه تواريخ المباريات» on the club
    page): the match's day on the competition line - for lists that are NOT
    grouped under a day heading (club pages, the standings page's next matches).
    highlight = (youtube url, channel) of the match's goals video
    (media.highlight_links): a «الأهداف» button in the row's spare column,
    opening the video on YouTube (user, 2026-11-02).
    card_link=False (2026-11-05): no «بطاقة المباراة» link - the day lists
    (.mlist) hid it with CSS and the stretched link already covers the row,
    so it was one hidden duplicate link per match on every page."""
    st = (m.get("status") or "").upper()
    badge = {"LIVE": ("مباشر", "live"), "FINISHED": ("انتهت", "fin"),
             "UPCOMING": ("قادمة", "up"), "POSTPONED": ("", "pp")}.get(st, ("", "up"))
    if st == "POSTPONED":
        mid = '<span class="ko ko-pp">مؤجلة</span>'
    elif st == "LIVE":
        # static live scores are up to 15 min stale = wrong data (user rule
        # 2026-08-31): dashes until LIVE_JS paints the real score
        mid = '<b class="score">- - -</b>'
    elif st == "FINISHED":
        mid = f'<b class="score">{m.get("home_score") if m.get("home_score") is not None else ""} - {m.get("away_score") if m.get("away_score") is not None else ""}</b>'
        # a shoot-out under the score, same «home - away» order (2026-11-10:
        # «عايز ضربات الجزاء تظهر وتظهر لها نتيجة»)
        if m.get("home_pens") is not None and m.get("away_pens") is not None:
            mid += (f'<span class="mpen" title="ركلات الترجيح">ترجيح '
                    f'<b>{m["home_pens"]} - {m["away_pens"]}</b></span>')
    else:
        when = (m.get("koff_time") if show_time and m.get("koff_time") else m.get("kickoff"))
        mid = f'<span class="ko">{esc(when)}</span>'
    def crest(u):
        return f'<img src="{esc(local_crest(u))}" alt="" width="34" height="34" loading="lazy">' if u else '<span class="ph">⚽</span>'
    comp = ""
    meta = []
    if show_comp:
        meta.append(esc(comp_label(m.get("competition"))))
        if m.get("channel"):
            meta.append(esc(m.get("channel")))
    if show_date and m.get("kickoff"):
        meta.append(esc(fmt_day(m.get("kickoff"))))
    if meta:
        comp = f'<div class="mcomp">{" · ".join(meta)}</div>'
    # only LIVE / FINISHED get a status pill (upcoming shows its time instead)
    pill = (f'<span class="pill pill-{badge[1]}">{esc(badge[0])}</span>'
            if st in ("LIVE", "FINISHED") else "")
    gblock = ""
    if goals:
        def side_list(sd):
            its = []
            for g in goals:
                if g.get("side") != sd:
                    continue
                mn = (f' <i class="mg-m">{esc(g["minute"])}′</i>'
                      if g.get("minute") else "")
                tg = f' <small>({esc(g["tag"])})</small>' if g.get("tag") else ""
                # the assister on his own line under the scorer (user, 2026-11-06:
                # «تحت اللاعب اللى مسجل الهدف اللاعب صاحب الاسيست»); LIVE_JS
                # paintGoals writes the same markup from /live.json's `a`
                # the boot instead of «صناعة:» (user, 2026-11-07); the word
                # stays for screen readers
                # ... and only on the match's own page (show_assist, user,
                # 2026-11-07: «يظهر بس لما اضغط على المباراة ... ميظهرش فى
                # صفحة المباريات») - the lists keep one line per goal
                ast = (f'<span class="mg-as">{BOOT_MG}<span class="sr-only">صناعة: </span>'
                       f'<bdi>{esc(g["assist"])}</bdi></span>'
                       if show_assist and g.get("assist") else "")
                its.append(f'<span class="mg">⚽ <bdi>{esc(g.get("player"))}</bdi>{mn}{tg}{ast}</span>')
            return "".join(its)
        gblock = (f'<div class="mgoals"><div class="mg-side">{side_list("h")}</div>'
                  f'<div class="mg-gap"></div>'
                  f'<div class="mg-side">{side_list("a")}</div></div>')
    # «بطاقة المباراة ←» rides its own full-width row under the teams (user,
    # 2026-10-24: «بدل ما فيه لينك اسمه توقع يلا سكور يكون لينك بطاقة
    # المباراة») - the same label the day cards and the article strip wear,
    # pointing at the one page that holds everything about the match,
    # the prediction included. It replaced the «توقع الجون» popup
    # button (pred_btn / done_btn, kept in widgets.py), so a row no longer
    # carries any prediction data.
    pbtn = (f'<div class="mgo-row"><a class="mgo" href="{esc(link)}">بطاقة المباراة ←</a></div>'
            if link and card_link else "")
    stretch = (f'<a class="mstretch" href="{esc(link)}" '
               f'aria-label="تفاصيل مباراة {esc(ar_team(m.get("home")))} و{esc(ar_team(m.get("away")))}"></a>'
               if link else "")
    hl = ""
    if highlight and st == "FINISHED":
        hl = (f'<a class="mhl" href="{esc(highlight[0])}" target="_blank" rel="noopener" '
              f'title="أهداف المباراة على {esc(highlight[1])}" aria-label="أهداف المباراة على يوتيوب">'
              f'<span class="mhl-i" aria-hidden="true">▶</span><span class="mhl-t">الأهداف</span></a>')
    # data-d = the kick-off day (Cairo): LIVE_JS paints a row only from the feed
    # game of the SAME day (2026-11-06: the Capital Cup's Abu Qir 0-2 Ceramica of
    # 11-03 was painted «انتهت 2-0» over their Egypt Cup tie of 11-07)
    return f"""<div class="mrow mrow-{badge[1]}" data-lv data-h="{esc(ar_team(m.get('home')))}" data-a="{esc(ar_team(m.get('away')))}" data-d="{esc(m.get('kickoff') or '')}">
  {stretch}{pill}{hl}
  <div class="team th">{crest(m.get('home_badge'))}<span><bdi>{esc(ar_team(m.get('home')))}</bdi></span></div>
  <div class="mid">{mid}</div>
  <div class="team ta">{crest(m.get('away_badge'))}<span><bdi>{esc(ar_team(m.get('away')))}</bdi></span></div>
  {comp}
  {pbtn}
  {gblock}
</div>"""
