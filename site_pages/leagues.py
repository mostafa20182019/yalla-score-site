"""Per-league pages: standings + scorers, the season's fixtures, and the
(hidden) stats dashboard.

Moved verbatim out of build_site.py (2026-09-26, tools/move_names.py):
source and comments exactly as they were there. Edit here; build_site
imports these back under the same names."""
import datetime
import os
from site_lib.competitions import COMP_SLUG, COMP_TV, comp_season
from site_lib.config import DIST, PREDICTIONS_ON, REF_TODAY, SHOW_STATS_PAGE, SITE_BASE, SITE_NAME
from site_lib.matchdata import match_goals
from site_lib.names import ar_team, comp_label
from site_lib.predictions import pred_pop
from site_lib.render import Markup, render
from site_lib.shell import _LASTMOD, foot, head, noindex, page_head_ad, write
from site_lib.snippets import LT_GAMES_JS, ROUNDS_JS, ST_TABS_JS
from site_lib.stats import _cnt, scorers_read, standings_analysis
from site_lib.tables import (clubs_panel, league_rounds_panel, match_row, round_on_show,
                             scorers_list, standings_table)
from site_lib.text import esc, jsonld
from site_lib.urls import breadcrumb_ld, match_url
from site_lib.league_desc import fixtures_desc, scorers_desc, standings_desc


def league_pages(_bycomp, _preds, as_by_comp, as_ok, forms, matches, sc_by_comp, sc_ok,
                 st_by_comp, urls, fx_by_comp=None, m_all=None, ge_idx=None, md_idx=None):
    """Evergreen SEO landing pages with their own URLs: «ترتيب الدوري المصري» and
    «هدافو الدوري المصري» are huge monthly queries that a tab inside /matches can
    never rank for. One /standings/<slug> per league with a table, and one
    /scorers/<slug> when the charts are current (the stale-last-season guard
    sc_ok/as_ok gates them, same as /matches). Markup: templates standings.html
    + scorers.html (2026-09-26); the pieces are built here in the same order as
    before. Returns (the competitions that got a /standings page, the season
    label) - read by the analysis section, fixtures and club pages."""
    os.makedirs(os.path.join(DIST, "standings"), exist_ok=True)
    os.makedirs(os.path.join(DIST, "scorers"), exist_ok=True)
    _n = datetime.date.today()
    season = (f"{_n.year}-{_n.year + 1}" if _n.month >= 7
              else f"{_n.year - 1}-{_n.year}")
    n_lp = 0
    _comps_with_table = set()
    # a season-pool match -> its /m page id: by id, else by clubs + day (the
    # 365scores leagues' pool and pages can hold the same match under two ids)
    _by_fx = {(ar_team(m.get("home")), ar_team(m.get("away")), m.get("kickoff")): mid
              for mid, m in (m_all or {}).items()}

    def page_of(m):
        if m_all is None:
            return m.get("match_id")
        if m.get("match_id") in m_all:
            return m["match_id"]
        return _by_fx.get((ar_team(m.get("home")), ar_team(m.get("away")), m.get("kickoff")))
    league_season = season
    for comp, slug in COMP_SLUG.items():
        season = comp_season(comp, league_season)   # «2026» for a one-year tournament
        label = comp_label(comp)
        st = st_by_comp.get(comp)
        if st and st.get("table"):
            _comps_with_table.add(comp)
        sc = sc_by_comp.get(comp) if sc_ok.get(comp) else None
        asst = as_by_comp.get(comp) if as_ok.get(comp) else None
        st_url, sc_url = f"/standings/{slug}.html", f"/scorers/{slug}.html"
        up_next = [m for m in matches
                   if m.get("competition") == comp
                   and (m.get("status") or "").upper() in ("UPCOMING", "LIVE")][:6]
        if st and st.get("table"):
            # the link preview: the top of the table on our own card (og_card.py,
            # 2026-11-13). Not for a zeroed pre-season table: five clubs on 0
            # points in alphabetical order would read as a ranking.
            import og_card
            from site_lib.dates import fmt_day
            _og = None
            if not st.get("zeroed") and not st.get("past"):
                _og = og_card.league(
                    label, "جدول الترتيب",
                    [(r.get("pos"), r.get("crest"), ar_team(r.get("team")), r.get("pts"))
                     for r in st["table"][:5]],
                    "نقطة", season, "تحديث " + " ".join(fmt_day(REF_TODAY).split()[1:]),
                    os.path.join(DIST, "og", "standings", f"{slug}.jpg"))
            page_head = Markup(head(f"ترتيب {label} اليوم — جدول الترتيب الكامل {season} | {SITE_NAME}",
                                    standings_desc(label, season, st["table"], st.get("zeroed")),
                                    SITE_BASE + st_url, active="leagues",
                                    image=f"{SITE_BASE}/og/standings/{slug}.jpg" if _og else None))
            crumbs_ld = Markup(breadcrumb_ld([("الرئيسية", SITE_BASE + "/"),
                                              ("البطولات", SITE_BASE + "/leagues.html"),
                                              (f"ترتيب {label}", SITE_BASE + st_url)]))
            table = standings_table(comp, st["table"], past=st.get("past"),
                                    season_label=st.get("season_label"),
                                    zeroed=st.get("zeroed"),
                                    form_map=forms.get(comp, {}), embedded=True,
                                    # «لعب / ف / ت / خ» open the matches (2026-11-01)
                                    games=(_bycomp or {}).get(comp) or [],
                                    pages=page_of)
            # the written «قراءة في ترتيب» block left the page (user, 2026-10-31):
            # the scorers + assists charts take its place, as tabs beside the
            # table (same day). Its FAQ stays - same numbers in question form.
            _an, _faq = standings_analysis(comp, label, season, st["table"],
                                           forms.get(comp, {}), sc or [], up_next,
                                           zeroed=st.get("zeroed"))
            _an = ""
            scorers = scorers_list(sc, "أهداف", comp) if sc else ""
            assists = scorers_list(asst, "صناعة", comp) if asst else ""
            # the whole round on show, played + live + to come (user, 2026-10-31:
            # «عايز فى دى يجيب مباريات الجولة كلها»); the freshest copy of each
            # match comes from m_all, and only a match with a page gets a link.
            # A league without round data keeps the next six matches.
            rn, rd_ms = round_on_show((fx_by_comp or {}).get(comp))
            if rd_ms:
                m_all = m_all or {}
                shown = sorted((m_all.get(m.get("match_id"), m) for m in rd_ms),
                               key=lambda m: (m.get("kickoff") or "", m.get("koff_time") or ""))
                next_title = f"الجولة {rn} من {label}"
            else:
                shown, next_title = up_next, f"مباريات {label} القادمة"
            next_rows = []
            for m in shown:
                has_page = m_all is None or m.get("match_id") in m_all
                next_rows.append(match_row(m, show_time=True, show_comp=False, show_date=True,
                                           goals=match_goals(ge_idx, m) if ge_idx else None,
                                           link=match_url(m) if has_page else None))
            # the popup is added only when a row carries a prediction button
            popup = pred_pop([table, scorers, assists] + next_rows + [_faq])
            # the hub triangle (SEO review 2026-11-13): the table links its
            # fixtures and scorers pages - 13 fixtures pages and 12 scorers
            # pages had no link from any page body. A bottom row, not a pane
            # heading (those stay plain text, user 2026-10-31).
            from site_lib import h2h as _H2H
            _more = []
            if ((fx_by_comp or {}).get(comp) or {}).get("rounds"):
                _more.append(f'<a href="/fixtures/{slug}.html">جدول مباريات {esc(label)} ومواعيد المباريات القادمة ←</a>')
            _more.append(f'<a href="{sc_url}">ترتيب هدافي {esc(label)} ←</a>')
            # «حاسبة الترتيب» (2026-11-19) - the same test the page builder uses
            from site_lib.calc import calc_data as _calc_data
            from site_lib.league_numbers import READY as _NB_READY
            if comp in _NB_READY:
                _more.append(f'<a href="/numbers/{slug}.html">إحصائيات {esc(label)}: الإنذارات والطرد ←</a>')
            _has_calc = bool(_calc_data(st, (fx_by_comp or {}).get(comp)))
            if _has_calc:
                _more.append(f'<a href="/calc/{slug}.html">حاسبة ترتيب {esc(label)}: توقّع النتائج وشاهد الجدول ←</a>')
            _more += [f'<a href="/h2h/{p["slug"]}.html">{esc(_H2H.link_label(p))} ←</a>'
                      for p in _H2H.pairs_for_league(comp)]
            write(f"standings/{slug}.html", render(
                "standings.html", page_head=page_head, crumbs_ld=crumbs_ld, label=label,
                # a button above the table, not only the last line of the page
                calc_href=Markup(f"/calc/{slug}.html") if _has_calc else "",
                season=season, table=Markup(table), has_sc=bool(sc),
                sc_url=Markup(sc_url), scorers=Markup(scorers),
                has_asst=bool(asst), assists=Markup(assists), tabs_js=Markup(ST_TABS_JS), games_js=Markup(LT_GAMES_JS),
                next_rows=[Markup(r) for r in next_rows], next_title=next_title,
                faq=Markup(_faq), more=[Markup(x) for x in _more],
                popup=Markup(popup), page_foot=Markup(foot())))
            urls.append(st_url)
            n_lp += 1
        if sc or (st and st.get("table")):
            # the page must exist whenever the league is active (the footer
            # links to /scorers/egypt.html sitewide) - a stale-gated chart
            # gets a placeholder, never last season's names
            import og_card
            from site_lib.dates import fmt_day
            _og = None
            if sc:
                _og = og_card.league(
                    label, "الهدافون",
                    [(k, r.get("crest"), r.get("name"), r.get("goals")) for k, r in zip(
                        og_card.shared_ranks([r.get("goals") for r in sc[:5]]), sc[:5])],
                    "هدف", season, "تحديث " + " ".join(fmt_day(REF_TODAY).split()[1:]),
                    os.path.join(DIST, "og", "scorers", f"{slug}.jpg"), head="الترتيب · اللاعب")
            page_head = Markup(head(f"هداف {label} {season} — ترتيب الهدافين وصناع الأهداف | {SITE_NAME}",
                                    scorers_desc(label, season, sc),
                                    SITE_BASE + sc_url, active="leagues",
                                    image=f"{SITE_BASE}/og/scorers/{slug}.jpg" if _og else None))
            scorers = scorers_list(sc, "أهداف", comp) if sc else ""
            assists = scorers_list(asst, "صناعة", comp) if asst else ""
            # a list of ten names is not a page; the reading is what makes it
            # one (2026-09-16, after an outside audit found /scorers/egypt
            # empty - see scorers_read)
            _sr, _sfaq, _sw = scorers_read(label, season, sc, asst,
                                           (st or {}).get("table"), _bycomp.get(comp))
            # the scorers beyond the feed's ten + each club's top scorer,
            # counted from the archive and shown only when the count agrees
            # with the chart (SEO review 2026-11-19; site_lib/full_scorers.py)
            from site_lib.full_scorers import full_scorers as _full_scorers
            from site_lib.stats import _cnt as _fcnt
            _fs = _full_scorers(_bycomp.get(comp), md_idx, sc) if sc else None
            _goals_txt = lambda n: _fcnt(n, "هدف واحد", "هدفان", "أهداف", "هدفًا")      # noqa: E731
            _rest_rows = [{"name": p, "team": t, "goals": n} for p, t, n in (_fs or {}).get("rest") or []]
            _club_rows = [{"team": t, "names": "، ".join(ps[:3]) + (f" و{len(ps) - 3} آخرون" if len(ps) > 3 else ""),
                           "goals": n} for t, ps, n in (_fs or {}).get("clubs") or []]
            if _club_rows:
                _cf = "؛ ".join(f"{c['team']}: {c['names']} ({_goals_txt(c['goals'])})" for c in _club_rows[:8])
                _q, _a = f"من هداف كل نادٍ في {label} {season}؟", _cf + "."
                _fq = (f'<details><summary>{esc(_q)}</summary><p>{esc(_a)}</p></details>')
                if _sfaq and "</section>" in _sfaq:
                    _sfaq = _sfaq.replace("</section>", _fq + "</section>", 1)
            _also = []
            if st and st.get("table"):
                _also.append(f'<a href="{st_url}">جدول ترتيب {esc(label)} كاملًا</a>')
            if ((fx_by_comp or {}).get(comp) or {}).get("rounds"):
                _also.append(f'<a href="/fixtures/{slug}.html">جدول مباريات {esc(label)}</a>')
            _html = render(
                "scorers.html", page_head=page_head, label=label, season=season,
                # the one hub page that had no BreadcrumbList (SEO review 2026-11-19)
                crumbs_ld=Markup(breadcrumb_ld([("الرئيسية", SITE_BASE + "/"),
                                                ("البطولات", SITE_BASE + "/leagues.html"),
                                                (f"هدافو {label}", SITE_BASE + sc_url)])),
                also=[Markup(x) for x in _also],
                rest=_rest_rows, rest_ones=(_fs or {}).get("ones") or 0, club_tops=_club_rows,
                has_sc=bool(sc), scorers=Markup(scorers), has_asst=bool(asst),
                assists=Markup(assists), reading=Markup(_sr or ""),
                has_table=bool(st and st.get("table")), st_url=Markup(st_url),
                reading_faq=Markup(_sfaq or ""), page_foot=Markup(foot()))
            # Indexable only once the page says something: the chart plus a
            # reading of at least three facts. Under that it stays what it was
            # before - a page for visitors and old links, out of the index and
            # out of the sitemap - because ~80 words of names is exactly the
            # thin content the AdSense rejection named.
            _rich_sc = bool(sc) and _sw >= 3
            if not _rich_sc:
                _html = noindex(_html)
            write(f"scorers/{slug}.html", _html)
            if _rich_sc:
                urls.append(sc_url)
            n_lp += 1
    print(f"  + league pages: {n_lp}")
    return _comps_with_table, league_season


def group_standings_pages(groups_by_comp, fx_by_comp, season, urls, m_all=None, bycomp=None):
    """/standings/<slug> for a competition played in GROUPS (SEO review
    2026-11-20). The group tables existed only inside /fixtures/<slug>, one at
    a time behind ‹ ›, under a «جدول مباريات» title - nothing answered «ترتيب
    مجموعات دوري أبطال أفريقيا» or «ترتيب مجموعة بيراميدز», and articles
    already linked /standings/afcon-qualifiers, a page that did not exist.
    Here every group is on show with its own heading naming its teams, then
    «حسابات التأهل», the round on show and the «في أي مجموعة» questions. All
    of it computed from the same tables the fixtures page shows."""
    from site_lib.clubs import TEAM_PAGES
    from site_lib.competitions import GROUP_PAGES
    from site_lib.names import _team_match
    from site_lib.qualify import QUALIFY, outlook_html
    from site_lib.tables import _group_games
    os.makedirs(os.path.join(DIST, "standings"), exist_ok=True)
    league_season = season
    _by_fx = {(ar_team(m.get("home")), ar_team(m.get("away")), m.get("kickoff")): mid
              for mid, m in (m_all or {}).items()}
    pages = ((lambda m: m.get("match_id") if m.get("match_id") in m_all else
              _by_fx.get((ar_team(m.get("home")), ar_team(m.get("away")), m.get("kickoff"))))
             if m_all is not None else None)
    n = 0
    for comp, slug in COMP_SLUG.items():
        if comp not in GROUP_PAGES:
            continue
        groups = [g for g in (groups_by_comp or {}).get(comp) or [] if g.get("table")]
        if not groups:
            continue
        label = comp_label(comp)
        fx = (fx_by_comp or {}).get(comp)
        season = comp_season(comp, league_season, (fx or {}).get("rounds") or None)
        games = (bycomp or {}).get(comp) if bycomp is not None else None
        url = f"/standings/{slug}.html"
        started = any((r.get("played") or 0) for g in groups for r in g["table"])

        def mine(g):
            """the club pages' teams in this group, by their page name"""
            return [tp for tp in TEAM_PAGES
                    if sum(1 for r in g["table"]
                           if _team_match(tp, {"home": r.get("team") or "", "away": "",
                                               "competition": comp})) == 1]
        blocks = []
        for g in groups:
            blocks.append({"num": g["num"], "name": g["name"],
                           "teams": "، ".join(ar_team(r.get("team")) for r in g["table"]),
                           "table": Markup(standings_table(
                               comp, g["table"], embedded=True, title=g["name"],
                               zeroed=False, games=_group_games(g["table"], games), pages=pages))})
        # the description names where OUR clubs and teams are (the query is
        # «ترتيب مجموعة بيراميدز»), then what the page holds - whole sentences
        # inside the ~150 characters a result shows
        where = [" و".join(tp["name"] for tp in mine(g)) + f" في {g['name']}"
                 for g in groups if mine(g)]
        n_txt = _cnt(len(groups), "مجموعة واحدة", "مجموعتين", "مجموعات", "مجموعة")
        desc = f"ترتيب مجموعات {label} {season}: "
        for k in (3, 2, 1, 0):
            d = desc + ("، ".join(where[:k]) + ". " if where[:k] else "") + f"جدول كل مجموعة من {n_txt} في صفحة واحدة."
            if len(d) <= 150 or k == 0:
                desc = d
                break
        title = next((t for t in (f"ترتيب مجموعات {label} {season}: جدول كل مجموعة",
                                  f"ترتيب مجموعات {label} {season}",
                                  f"ترتيب مجموعات {label}") if len(t) <= 62),
                     f"ترتيب مجموعات {label}")
        hint = (f"جدول كل مجموعة في {label}، يتحدّث تلقائيًا بعد كل مباراة." if started else
                "دور المجموعات لم يبدأ بعد: كل الأرقام صفر، والترتيب الظاهر داخل كل مجموعة ليس ترتيبًا فعليًا.")
        # the round on show, as on a league's standings page
        rn, rd_ms = round_on_show(fx)
        _pool = m_all or {}
        shown = sorted((_pool.get(m.get("match_id"), m) for m in rd_ms),
                       key=lambda m: (m.get("kickoff") or "", m.get("koff_time") or ""))
        _rd_label = next((r.get("label") for r in (fx or {}).get("rounds") or []
                          if r.get("round") == rn and r.get("label")),
                         f"الجولة {rn}" if rn is not None else "")
        next_title = f"{label}: {_rd_label}" if shown else ""
        next_rows = [match_row(m, show_time=True, show_comp=False, show_date=True, card_link=False,
                               link=match_url(m) if m.get("match_id") in _pool else None)
                     for m in shown]
        faq = []
        for g in groups:
            names = [r.get("team") for r in g["table"] if r.get("team")]
            for tp in mine(g):
                me = [x for x in names if _team_match(tp, {"home": x, "away": "", "competition": comp})]
                if len(names) >= 3:
                    others = [ar_team(x) for x in names if x != me[0]]
                    faq.append((f"في أي مجموعة {tp['name']} في {label}؟",
                                f"{tp['name']} في {g['name']} مع " + " و".join(others) + "."))
        rule = QUALIFY.get(comp)
        if rule:
            two = "أول فريقين" if rule["slots"] == 2 else f"أول {rule['slots']} فرق"
            faq.append((f"كم فريقًا يتأهل من كل مجموعة في {label}؟",
                        f"يتأهل {two} من كل مجموعة إلى {rule['to']}."
                        + (f" المجموعة التي فيها بلد مستضيف ({'، '.join(rule['hosts'])}) يتأهل منها فريق واحد فقط غير المستضيف."
                           if rule.get("hosts") else "")))
        faq.append((f"كم مجموعة في {label}؟",
                    _cnt(len(groups), "مجموعة واحدة", "مجموعتان", "مجموعات", "مجموعة") + "."))
        faq_html = (f'<section class="minfo faq"><h2>أسئلة شائعة عن مجموعات {esc(label)}</h2>'
                    + "".join(f'<details><summary>{esc(q)}</summary><p>{esc(a)}</p></details>'
                              for q, a in faq) + '</section>'
                    + jsonld({"@context": "https://schema.org", "@type": "FAQPage",
                              "mainEntity": [{"@type": "Question", "name": q,
                                              "acceptedAnswer": {"@type": "Answer", "text": a}}
                                             for q, a in faq]}))
        more = []
        if (fx or {}).get("rounds"):
            more.append(f'<a href="/fixtures/{slug}.html">جدول مباريات {esc(label)} ومواعيد المباريات القادمة ←</a>')
        from site_lib.league_numbers import READY as _NB_READY_G
        if comp in _NB_READY_G:
            more.append(f'<a href="/numbers/{slug}.html">إحصائيات {esc(label)} ←</a>')
        seen = set()
        for g in groups:
            for tp in mine(g):
                if tp["slug"] not in seen:
                    seen.add(tp["slug"])
                    more.append(f'<a href="/team/{tp["slug"]}.html">{esc(tp["name"])} ←</a>')
        tables_html = "".join(str(b["table"]) for b in blocks)
        write(f"standings/{slug}.html", render(
            "standings_groups.html",
            page_head=Markup(head(f"{title} | {SITE_NAME}", desc, SITE_BASE + url, active="leagues")),
            crumbs_ld=Markup(breadcrumb_ld([("الرئيسية", SITE_BASE + "/"),
                                            ("البطولات", SITE_BASE + "/leagues.html"),
                                            (f"ترتيب مجموعات {label}", SITE_BASE + url)])),
            label=label, season=season, hint=hint, groups=blocks, chips=len(blocks) > 4,
            outlook=Markup(outlook_html(comp, label, groups, games)),
            next_title=next_title, next_rows=[Markup(x) for x in next_rows],
            faq=Markup(faq_html), more=[Markup(x) for x in more],
            games_js=Markup(LT_GAMES_JS if 'class="lt-n"' in tables_html else ""),
            page_foot=Markup(foot())))
        urls.append(url)
        _LASTMOD[url] = REF_TODAY
        n += 1
    print(f"  + group standings pages: {n}")


def leagues_page(_comps_with_table, fx_by_comp, urls):
    """/leagues - «البطولات», FotMob's Leagues tab (user, 2026-10-26: «عايز
    يكون فيه تاب اسمها البطولات»): every competition we cover, one row each,
    opening its own page - the table (/standings) when it has one, otherwise
    its season's fixtures (/fixtures). A competition with neither (the CAF
    cups have no feed of their own yet) is left out, never a dead row.
    Domestic leagues first, then the continental and international ones."""
    from site_lib.competitions import COMP_ORDER, GROUP_PAGES as _GROUP_PAGES
    from site_lib.crests import comp_icon
    domestic, arab, rest = [], [], []
    for comp in sorted(COMP_SLUG, key=lambda c: (COMP_ORDER.index(c) if c in COMP_ORDER else len(COMP_ORDER), c)):
        slug = COMP_SLUG[comp]
        if comp in _comps_with_table:
            href, what = f"/standings/{slug}.html", "الترتيب والهدافون والمباريات"
        elif comp in _GROUP_PAGES and os.path.exists(os.path.join(DIST, "standings", f"{slug}.html")):
            href, what = f"/standings/{slug}.html", "ترتيب المجموعات والمباريات"
        elif (fx_by_comp.get(comp) or {}).get("rounds"):
            href, what = f"/fixtures/{slug}.html", "جدول المباريات"
        else:
            continue
        row = {"href": href, "icon": Markup(comp_icon(comp)), "label": comp_label(comp), "what": what}
        (domestic if slug in DOMESTIC_SLUGS else arab if slug in ARAB_SLUGS else rest).append(row)
    groups = [(t, rows) for t, rows in (("الدوريات الأوروبية", domestic), ("الدوريات العربية", arab),
                                        ("البطولات القارية والدولية", rest)) if rows]
    page_head = Markup(head(f"البطولات: الترتيب والهدافون ومواعيد المباريات | {SITE_NAME}",
                            # the Arab leagues and the African cups by name (SEO review 2026-11-20)
                            "الدوري المصري والسعودي والمغربي والجزائري والتونسي والعراقي، الدوريات "
                            "الأوروبية، وأبطال أفريقيا وأوروبا: الترتيب والهدافون ومواعيد المباريات.",
                            SITE_BASE + "/leagues.html", active="leagues"))
    write("leagues.html", render("leagues.html", page_head=page_head, groups=groups,
                                 page_foot=Markup(foot())))
    urls.append("/leagues.html")
    print(f"  + leagues page: {sum(len(r) for _, r in groups)} competitions")


# the first card of /leagues, «الدوريات الأوروبية» (user, 2026-11-03: «سمى
# المجموعة الاولى بالدوريات الاوروبية») - Turkey stays here (a UEFA league)
DOMESTIC_SLUGS = ("england", "spain", "italy", "germany", "france", "turkey")
# «الدوريات العربية» - the North African leagues (2026-11-02), joined by the
# Egyptian league and cups and the Saudi league (user, 2026-11-03: «انقل الدورى
# المصرى وكأس مصر والدورى السعودى للدوريات العربية»)
ARAB_SLUGS = ("egypt", "egypt-cup", "egypt-capital-cup", "egypt-second-division", "saudi",
              "morocco", "algeria", "tunisia", "libya", "iraq", "syria")


def fixtures_pages(fx_by_comp, season, st_by_comp, urls, groups_by_comp=None, m_all=None,
                   bycomp=None):
    """/fixtures/<slug> - a league's whole season. These used to be INSIDE
    /matches, hidden behind the league filter: 2,206 fixture rows and 4,955
    crest tags that every visitor downloaded to look at the 82 rows of one day.
    As their own pages they cost nothing to the people who do not want them and
    answer a real query - «جدول مباريات الدوري المصري». Markup: fixtures.html
    (templated 2026-09-26). Returns the loop's last comp/label/slug, as before."""
    os.makedirs(os.path.join(DIST, "fixtures"), exist_ok=True)
    league_season = season
    n_fx = 0
    for comp, slug in COMP_SLUG.items():
        fx = fx_by_comp.get(comp)
        rounds = (fx or {}).get("rounds") or []
        if not rounds:
            continue
        label = comp_label(comp)
        season = comp_season(comp, league_season, rounds)   # «2026» for a one-year tournament
        n_m = sum(len(r.get("matches") or []) for r in rounds)
        # 2026-11-12 (GSC export): «مباريات الدوري التركي القادمه» 34,
        # «جدول مباريات الدوري التركي» 28, «مواعيد مباريات الدوري التركي» -
        # all at ~10. The title carries «مواعيد» and «المباريات القادمة».
        _next = "الدور القادم" if any(r.get("label") for r in rounds) else "المباريات القادمة"   # a cup's stages
        # ... and stays whole in the results (SEO review 2026-11-19: the Africa
        # qualifiers' title was 80 characters, Turkey's and Libya's 71 - cut
        # mid-phrase). What goes first is the SEASON, then «والنتائج» - never
        # «مواعيد» or «المباريات القادمة», the words the queries are made of.
        _ft = next((t for t in (f"جدول مباريات {label}: مواعيد {_next} والنتائج {season}",
                                f"جدول مباريات {label}: مواعيد {_next} والنتائج",
                                f"جدول مباريات {label}: مواعيد {_next}",
                                f"مواعيد مباريات {label}")      # كأس الكونفدرالية الأفريقية: the longest name we carry
                    if len(t) <= 62), f"مواعيد مباريات {label}")   # 62 = seo_title's own limit
        page_head = Markup(head(f"{_ft} | {SITE_NAME}",
                                fixtures_desc(label, season, rounds, n_m),
                                SITE_BASE + f"/fixtures/{slug}.html", active="leagues"))
        rounds_panel = league_rounds_panel(comp, fx, embedded=True,
                                           pages=m_all if m_all is not None else None)
        # «مباريات X القادمة» in words (SEO review 2026-11-13: the page ranked
        # ~10 for that query with no heading, no sentence and no visible list
        # saying it - every round but one is `hidden`). The round on show as
        # real rows, and the same facts as questions. Computed, never written.
        from site_lib.dates import fmt_day
        rn, rd_ms = round_on_show(fx)
        _pool = m_all or {}
        shown = sorted((_pool.get(m.get("match_id"), m) for m in rd_ms),
                       key=lambda m: (m.get("kickoff") or "", m.get("koff_time") or ""))
        _rd_label = next((r.get("label") for r in rounds if r.get("round") == rn and r.get("label")),
                         f"الجولة {rn}" if rn is not None else "")
        _coming = [m for m in shown if (m.get("status") or "").upper() in ("UPCOMING", "LIVE")
                   and m.get("kickoff")]
        next_title = (f"مباريات {label} القادمة: {_rd_label}" if _coming
                      else f"{label}: {_rd_label}" if shown else "")
        next_rows = [match_row(m, show_time=True, show_comp=False, show_date=True, card_link=False,
                               link=match_url(m) if m.get("match_id") in _pool else None)
                     for m in shown]
        faq = []
        if _coming:
            _d1, _d2 = _coming[0]["kickoff"], _coming[-1]["kickoff"]
            faq.append((f"متى مباريات {_rd_label} من {label}؟",
                        (f"تقام يوم {fmt_day(_d1)}." if _d1 == _d2
                         else f"تبدأ يوم {fmt_day(_d1)}. تنتهي يوم {fmt_day(_d2)}.")))
        _done = sorted((m for r in rounds for m in r.get("matches") or []
                        if (m.get("status") or "").upper() == "FINISHED"
                        and m.get("home_score") is not None and m.get("kickoff")),
                       key=lambda m: (m.get("kickoff"), m.get("koff_time") or ""), reverse=True)
        if _done:
            _last = [m for m in _done if m["kickoff"] == _done[0]["kickoff"]][:3]
            faq.append((f"ما آخر نتائج {label}؟",
                        f"نتائج يوم {fmt_day(_done[0]['kickoff'])}: "
                        + " ".join(f"{ar_team(m.get('home'))} {m.get('home_score')} - "
                                   f"{m.get('away_score')} {ar_team(m.get('away'))}." for m in _last)))
        if COMP_TV.get(comp):
            faq.append((f"ما القناة الناقلة لمباريات {label}؟",
                        f"{COMP_TV[comp]} في المنطقة العربية."))
        # «في أي مجموعة X؟» (SEO review 2026-11-19): one question per club page
        # that plays in this group stage, answered from the group tables the
        # page shows - the group's name and the other sides of it. Computed.
        from site_lib.clubs import TEAM_PAGES as _TPS
        from site_lib.names import _team_match as _tmatch
        for _g in (groups_by_comp or {}).get(comp) or []:
            _names = [r.get("team") for r in _g.get("table") or [] if r.get("team")]
            for _tp in _TPS:
                _mine = [n for n in _names if _tmatch(_tp, {"home": n, "away": "", "competition": comp})]
                if len(_mine) == 1 and len(_names) >= 3:
                    _others = [ar_team(n) for n in _names if n != _mine[0]]
                    faq.append((f"في أي مجموعة {_tp['name']} في {label}؟",
                                f"{_tp['name']} في {_g.get('name')} مع " + " و".join(_others) + "."))
        faq_html = ""
        if faq:
            faq_html = (f'<section class="minfo faq"><h2>أسئلة شائعة عن مباريات {esc(label)}</h2>'
                        + "".join(f'<details><summary>{esc(q)}</summary><p>{esc(ans)}</p></details>'
                                  for q, ans in faq) + '</section>'
                        + jsonld({"@context": "https://schema.org", "@type": "FAQPage",
                                  "mainEntity": [{"@type": "Question", "name": q,
                                                  "acceptedAnswer": {"@type": "Answer", "text": ans}}
                                                 for q, ans in faq]}))
        # a group stage's tables, group by group (user 2026-11-13)
        from site_lib.clubs import TEAM_PAGES
        from site_lib.tables import group_tables_panel
        # «لعب / ف / ت / خ» open the group's matches, as in a league table
        # (user 2026-11-15). The matches are the SEASON POOL (bycomp: this
        # season's fixtures + the results archive) - the page's own rounds
        # hold only the last weeks, and a «لعب 6» opening two matches is
        # refused by standings_table anyway.
        _by_fx = {(ar_team(m.get("home")), ar_team(m.get("away")), m.get("kickoff")): mid
                  for mid, m in (m_all or {}).items()}
        groups_panel = group_tables_panel(
            comp, (groups_by_comp or {}).get(comp), TEAM_PAGES,
            games=(bycomp or {}).get(comp) if bycomp is not None else None,
            pages=(lambda m: m.get("match_id") if m.get("match_id") in m_all else
                   _by_fx.get((ar_team(m.get("home")), ar_team(m.get("away")), m.get("kickoff"))))
            if m_all is not None else None)
        # «حسابات التأهل» (site review 2026-11-19): who is through, who is out,
        # what total guarantees it - counted over every remaining result
        from site_lib.qualify import outlook_html as _outlook_html
        groups_panel += _outlook_html(comp, label, (groups_by_comp or {}).get(comp),
                                      (bycomp or {}).get(comp) if bycomp is not None else None)
        _links = [f'<a href="/">مباريات اليوم ←</a>']
        # a round as its own page (site_lib/rounds.py, 2026-11-27): the round
        # on show, the one before and the one after
        from site_lib import rounds as _RD
        if comp in _RD.ROUND_COMPS:
            _links += [f'<a href="{_RD.round_url(comp, _n)}">الجولة {_n} من {esc(label)} ←</a>' for _n in _RD.window(fx)]
        if comp in st_by_comp and (st_by_comp[comp] or {}).get("table"):
            _links.append(f'<a href="/standings/{slug}.html">ترتيب {esc(label)} ←</a>')
        elif os.path.exists(os.path.join(DIST, "standings", f"{slug}.html")):
            # the groups page (group_standings_pages runs before this function)
            _links.append(f'<a href="/standings/{slug}.html">ترتيب مجموعات {esc(label)} كلها في صفحة واحدة ←</a>')
        from site_lib.league_numbers import READY as _NB_READY_FX
        if comp in _NB_READY_FX:
            _links.append(f'<a href="/numbers/{slug}.html">إحصائيات {esc(label)} ←</a>')
        from site_lib.calc import calc_data as _calc_data_fx
        if _calc_data_fx(st_by_comp.get(comp), fx):
            _links.append(f'<a href="/calc/{slug}.html">حاسبة ترتيب {esc(label)} ←</a>')
        # the scorers page is written by league_pages, before this function
        if os.path.exists(os.path.join(DIST, "scorers", f"{slug}.html")):
            _links.append(f'<a href="/scorers/{slug}.html">هدافو {esc(label)} ←</a>')
        from site_lib import h2h as _H2H
        _links += [f'<a href="/h2h/{p["slug"]}.html">{esc(_H2H.link_label(p))} ←</a>'
                   for p in _H2H.pairs_for_league(comp)]
        if PREDICTIONS_ON and comp in COMP_SLUG and os.path.exists(os.path.join(DIST, "analysis", f"{slug}.html")):
            _links.append(f'<a href="/analysis/{slug}.html">توقعات {esc(label)} ←</a>')
        crumbs_ld = breadcrumb_ld([("الرئيسية", SITE_BASE + "/"),
                                   ("البطولات", SITE_BASE + "/leagues.html"),
                                   (f"جدول {label}", SITE_BASE + f"/fixtures/{slug}.html")])
        write(f"fixtures/{slug}.html", render(
            "fixtures.html", page_head=page_head, label=label, season=season,
            # the group tables' «لعب / ف / ت / خ» popup - only where a button exists
            games_js=Markup(LT_GAMES_JS if 'class="lt-n"' in groups_panel else ""),
            # what the page HOLDS, with number agreement - it used to say «كل
            # جولات… 11 جولة» while the Turkish feed carries rounds 10-20 only
            # (SEO review 2026-11-13: a wrong claim, and «2 جولة» / «3 دور»)
            rounds_txt=(_cnt(len(rounds), "دور واحد", "دوران", "أدوار", "دورًا")
                        if any(r.get("label") for r in rounds)
                        else _cnt(len(rounds), "جولة واحدة", "جولتان", "جولات", "جولة")),
            matches_txt=_cnt(n_m, "مباراة واحدة", "مباراتان", "مباريات", "مباراة"),
            rounds_panel=Markup(rounds_panel),
            next_title=next_title, next_rows=[Markup(x) for x in next_rows],
            faq=Markup(faq_html), popup=Markup(pred_pop(next_rows)),
            groups_panel=Markup(groups_panel),
            staged=any(r.get("label") for r in rounds),
            links=[Markup(x) for x in _links], crumbs_ld=Markup(crumbs_ld),
            page_foot=Markup(foot()), rounds_js=Markup(ROUNDS_JS)))
        urls.append(f"/fixtures/{slug}.html")
        _LASTMOD[f"/fixtures/{slug}.html"] = REF_TODAY
        n_fx += 1
    print(f"  + season fixture pages: {n_fx}")


def stats_page(comp_order, fixtures, forms, league_stats_sec, matches, sc_by_comp, sc_ok,
               st_by_comp, urls):
    """/stats - the visual stats board. Markup: site_src/templates/stats.html
    (templated 2026-09-26). Noindexed unless SHOW_STATS_PAGE."""
    page_head = head(f"إحصائيات وتحليلات — {SITE_NAME}",
                     "لوحة إحصائيات مرئية: سباق النقاط، الأهداف في كل جولة، وأرقام الموسم لكل بطولة.",
                     SITE_BASE + "/stats.html", active="stats")
    page_title = page_head_ad(
        '<h1 class="page-h">📊 إحصائيات وتحليلات</h1>',
        'أرقام محسوبة من نتائج الموسم الحالي — تتحدّث تلقائيًا بعد كل جولة.')
    clubs = clubs_panel(st_by_comp, sc_ok, sc_by_comp, forms, matches, fixtures)
    sections = []
    for comp in comp_order:
        sec = league_stats_sec(comp)
        if sec:
            sections.append(Markup(sec))
    html_out = render("stats.html", page_head=Markup(page_head), page_title=Markup(page_title),
                      clubs=Markup(clubs), sections=sections, page_foot=Markup(foot()))
    if not SHOW_STATS_PAGE:
        html_out = noindex(html_out)
    write("stats.html", html_out)
    if SHOW_STATS_PAGE:
        urls.append("/stats.html")
