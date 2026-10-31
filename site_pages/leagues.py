"""Per-league pages: standings + scorers, the season's fixtures, and the
(hidden) stats dashboard.

Moved verbatim out of build_site.py (2026-09-26, tools/move_names.py):
source and comments exactly as they were there. Edit here; build_site
imports these back under the same names."""
import datetime
import os
from site_lib.competitions import COMP_SLUG
from site_lib.config import DIST, PREDICTIONS_ON, REF_TODAY, SHOW_STATS_PAGE, SITE_BASE, SITE_NAME
from site_lib.names import comp_label
from site_lib.predictions import pred_pop
from site_lib.render import Markup, render
from site_lib.shell import _LASTMOD, foot, head, page_head_ad, write
from site_lib.snippets import ROUNDS_JS
from site_lib.stats import scorers_read, standings_analysis
from site_lib.tables import clubs_panel, league_rounds_panel, match_row, scorers_list, standings_table
from site_lib.text import esc
from site_lib.urls import breadcrumb_ld, match_url
from site_lib.league_desc import fixtures_desc, scorers_desc, standings_desc


def league_pages(_bycomp, _preds, as_by_comp, as_ok, forms, matches, sc_by_comp, sc_ok,
                 st_by_comp, urls):
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
    for comp, slug in COMP_SLUG.items():
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
            page_head = Markup(head(f"ترتيب {label} اليوم — جدول الترتيب الكامل {season} | {SITE_NAME}",
                                    standings_desc(label, season, st["table"], st.get("zeroed")),
                                    SITE_BASE + st_url, active="leagues"))
            crumbs_ld = Markup(breadcrumb_ld([("أخبار", SITE_BASE + "/"),
                                              ("البطولات", SITE_BASE + "/leagues.html"),
                                              (f"ترتيب {label}", SITE_BASE + st_url)]))
            table = standings_table(comp, st["table"], past=st.get("past"),
                                    season_label=st.get("season_label"),
                                    zeroed=st.get("zeroed"),
                                    form_map=forms.get(comp, {}), embedded=True)
            # the written «قراءة في ترتيب» block left the page (user, 2026-10-31):
            # the scorers + assists charts take its place under the table. Its
            # FAQ stays - same numbers in question form.
            _an, _faq = standings_analysis(comp, label, season, st["table"],
                                           forms.get(comp, {}), sc or [], up_next,
                                           zeroed=st.get("zeroed"))
            _an = ""
            scorers = scorers_list(sc, "أهداف") if sc else ""
            assists = scorers_list(asst, "صناعة") if asst else ""
            next_rows = []
            for m in up_next:
                next_rows.append(match_row(m, show_time=True, show_comp=False, show_date=True,
                                           link=match_url(m)))
            # the popup is added only when a row carries a prediction button
            popup = pred_pop([table, scorers, assists] + next_rows + [_faq])
            write(f"standings/{slug}.html", render(
                "standings.html", page_head=page_head, crumbs_ld=crumbs_ld, label=label,
                season=season, table=Markup(table), has_sc=bool(sc),
                sc_url=Markup(sc_url), scorers=Markup(scorers),
                has_asst=bool(asst), assists=Markup(assists),
                next_rows=[Markup(r) for r in next_rows], faq=Markup(_faq),
                popup=Markup(popup), page_foot=Markup(foot())))
            urls.append(st_url)
            n_lp += 1
        if sc or (st and st.get("table")):
            # the page must exist whenever the league is active (the footer
            # links to /scorers/egypt.html sitewide) - a stale-gated chart
            # gets a placeholder, never last season's names
            page_head = Markup(head(f"هداف {label} {season} — ترتيب الهدافين وصناع الأهداف | {SITE_NAME}",
                                    scorers_desc(label, season, sc),
                                    SITE_BASE + sc_url, active="leagues"))
            scorers = scorers_list(sc, "أهداف") if sc else ""
            assists = scorers_list(asst, "صناعة") if asst else ""
            # a list of ten names is not a page; the reading is what makes it
            # one (2026-09-16, after an outside audit found /scorers/egypt
            # empty - see scorers_read)
            _sr, _sfaq, _sw = scorers_read(label, season, sc, asst,
                                           (st or {}).get("table"), _bycomp.get(comp))
            _html = render(
                "scorers.html", page_head=page_head, label=label, season=season,
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
                _html = _html.replace("<head>", '<head><meta name="robots" content="noindex">', 1)
            write(f"scorers/{slug}.html", _html)
            if _rich_sc:
                urls.append(sc_url)
            n_lp += 1
    print(f"  + league pages: {n_lp}")
    return _comps_with_table, season


def leagues_page(_comps_with_table, fx_by_comp, urls):
    """/leagues - «البطولات», FotMob's Leagues tab (user, 2026-10-26: «عايز
    يكون فيه تاب اسمها البطولات»): every competition we cover, one row each,
    opening its own page - the table (/standings) when it has one, otherwise
    its season's fixtures (/fixtures). A competition with neither (the CAF
    cups have no feed of their own yet) is left out, never a dead row.
    Domestic leagues first, then the continental and international ones."""
    from site_lib.competitions import COMP_ORDER
    from site_lib.crests import comp_icon
    domestic, rest = [], []
    for comp in sorted(COMP_SLUG, key=lambda c: (COMP_ORDER.index(c) if c in COMP_ORDER else len(COMP_ORDER), c)):
        slug = COMP_SLUG[comp]
        if comp in _comps_with_table:
            href, what = f"/standings/{slug}.html", "الترتيب والهدافون والمباريات"
        elif (fx_by_comp.get(comp) or {}).get("rounds"):
            href, what = f"/fixtures/{slug}.html", "جدول المباريات"
        else:
            continue
        row = {"href": href, "icon": Markup(comp_icon(comp)), "label": comp_label(comp), "what": what}
        (domestic if slug in DOMESTIC_SLUGS else rest).append(row)
    groups = [(t, rows) for t, rows in (("الدوريات", domestic), ("البطولات القارية والدولية", rest)) if rows]
    page_head = Markup(head(f"البطولات: الترتيب والهدافون ومواعيد المباريات | {SITE_NAME}",
                            "كل البطولات على يلا سكور: الدوري المصري والإنجليزي والإسباني والإيطالي "
                            "والألماني والفرنسي والتركي والسعودي ودوري أبطال أوروبا - الترتيب "
                            "والهدافون ومواعيد المباريات لكل بطولة.",
                            SITE_BASE + "/leagues.html", active="leagues"))
    write("leagues.html", render("leagues.html", page_head=page_head, groups=groups,
                                 page_foot=Markup(foot())))
    urls.append("/leagues.html")
    print(f"  + leagues page: {sum(len(r) for _, r in groups)} competitions")


# the national leagues - the first card of /leagues
DOMESTIC_SLUGS = ("egypt", "england", "spain", "italy", "germany", "france", "turkey", "saudi")


def fixtures_pages(fx_by_comp, season, st_by_comp, urls):
    """/fixtures/<slug> - a league's whole season. These used to be INSIDE
    /matches, hidden behind the league filter: 2,206 fixture rows and 4,955
    crest tags that every visitor downloaded to look at the 82 rows of one day.
    As their own pages they cost nothing to the people who do not want them and
    answer a real query - «جدول مباريات الدوري المصري». Markup: fixtures.html
    (templated 2026-09-26). Returns the loop's last comp/label/slug, as before."""
    os.makedirs(os.path.join(DIST, "fixtures"), exist_ok=True)
    n_fx = 0
    for comp, slug in COMP_SLUG.items():
        fx = fx_by_comp.get(comp)
        rounds = (fx or {}).get("rounds") or []
        if not rounds:
            continue
        label = comp_label(comp)
        n_m = sum(len(r.get("matches") or []) for r in rounds)
        page_head = Markup(head(f"جدول مباريات {label} اليوم والجولة القادمة {season} | {SITE_NAME}",
                                fixtures_desc(label, season, rounds, n_m),
                                SITE_BASE + f"/fixtures/{slug}.html", active="leagues"))
        rounds_panel = league_rounds_panel(comp, fx, embedded=True)
        _links = [f'<a href="/matches.html">مباريات اليوم ←</a>']
        if comp in st_by_comp and (st_by_comp[comp] or {}).get("table"):
            _links.append(f'<a href="/standings/{slug}.html">ترتيب {esc(label)} ←</a>')
        if PREDICTIONS_ON and comp in COMP_SLUG and os.path.exists(os.path.join(DIST, "analysis", f"{slug}.html")):
            _links.append(f'<a href="/analysis/{slug}.html">توقعات {esc(label)} ←</a>')
        crumbs_ld = breadcrumb_ld([("أخبار", SITE_BASE + "/"),
                                   ("البطولات", SITE_BASE + "/leagues.html"),
                                   (f"جدول {label}", SITE_BASE + f"/fixtures/{slug}.html")])
        write(f"fixtures/{slug}.html", render(
            "fixtures.html", page_head=page_head, label=label, season=season,
            n_rounds=len(rounds), n_matches=n_m, rounds_panel=Markup(rounds_panel),
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
        html_out = html_out.replace("<head>", '<head><meta name="robots" content="noindex">', 1)
    write("stats.html", html_out)
    if SHOW_STATS_PAGE:
        urls.append("/stats.html")
