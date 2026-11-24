"""/matches and the per-match pages (/m/<id>).

Moved verbatim out of build_site.py (2026-09-26, tools/move_names.py):
source and comments exactly as they were there. Edit here; build_site
imports these back under the same names."""
import datetime
import os
from site_lib.articles import ensure_match_image, match_article_block
from site_lib.tables import jump_chips
from site_lib.clubs import TEAM_PAGES
from site_lib.competitions import COMP_ORDER, COMP_SLUG, match_tv
from site_lib import h2h as _H2H
from site_lib.config import DIST, REF_TODAY, SITE_BASE, SITE_NAME, load
from site_lib.crests import comp_icon, local_crest
from site_lib.dates import fmt_day
from site_lib.daylist import comp_hrefs, day_sections, inline_days, write_day_fragments
from site_lib.league_desc import matches_desc
from site_lib.matchdata import absence_block, match_details_for, match_goals, prematch_for
from site_lib.media import highlight_links, highlight_video
from site_lib.names import _team_match, ar_team, ar_team_in, comp_label
from site_lib.predictions import pred_block, pred_pop
from site_lib.reads import post_match_read, pre_match_read
from site_lib.render import Markup, render
from site_lib.shell import _LASTMOD, adsense_slot, foot, head, noindex, thumb_url, write
from site_lib.snippets import FILTERS_HTML, LT_GAMES_JS, MATCHES_JS, ROUNDS_JS, SHOT_JS, ST_TABS_JS, VIDEO_JS
from site_lib.stats import _finished_by_comp
from site_lib.tables import fixture_mini, league_rounds_panel, match_details_html, match_row, match_stats_html, motm_html, scorers_list, standings_table
from site_lib.text import esc, jsonld
from site_lib.urls import article_href, breadcrumb_ld, pick_match_article


def matches_page(_plog, _preds, articles, fixtures, forms, fx_by_comp, ge_idx, league_stats_parts,
                 matches, st_by_comp, standings):
    """/matches - the per-day navigator. Markup: site_src/templates/matches.html
    (templated 2026-09-26). The loops below are the ones that used to append
    HTML, in the same order and under the same names - they now fill the
    structures the template renders - so every helper runs in the same
    sequence and the loop variables build() reads afterwards (a, comp, i, img,
    k, m, st) end exactly where they used to. comp_order is the real output."""
    from collections import OrderedDict
    daymap = OrderedDict()
    for m in matches:
        daymap.setdefault(m.get("kickoff") or "", []).append(m)
    sorted_days = sorted(k for k in daymap.keys() if k)
    # distinct competitions across the feed (for the leagues sidebar):
    # every league seen in the day view, plus any league that has a standings
    # table or a rounds panel even if it has no match in the current window
    # (e.g. a league added before its season starts).
    comp_order = []
    for m in matches:
        c = m.get("competition") or ""
        if c and c not in comp_order:
            comp_order.append(c)
    for s in standings:
        c = s.get("competition") or ""
        if c and s.get("table") and c not in comp_order:
            comp_order.append(c)
    for f in fixtures:
        c = f.get("competition") or ""
        if c and c not in comp_order:
            comp_order.append(c)
    comp_order.sort(key=lambda c: (COMP_ORDER.index(c) if c in COMP_ORDER
                                   else len(COMP_ORDER), c))
    pieces = []          # every dynamic piece, for pred_pop's "any prediction button?"
    # 2026-10-12 (user: «اعمل نفس الحاجة لصفحة المباريات»): the title is the
    # query («مواعيد ونتائج مباريات اليوم») and the description opens with
    # today's count, the headline fixture and the latest score.
    _mdesc = matches_desc(matches, REF_TODAY, TEAM_PAGES, comp_order)
    page_head = head(f"مواعيد ونتائج مباريات اليوم بتوقيت القاهرة | {SITE_NAME}",
                     _mdesc, SITE_BASE + "/", active="matches")
    # CollectionPage (SEO review 2026-11-12: /matches carried no schema)
    page_head += jsonld({"@context": "https://schema.org", "@type": "CollectionPage",
                         "name": "مواعيد ونتائج مباريات اليوم بتوقيت القاهرة",
                         "description": _mdesc, "url": SITE_BASE + "/",
                         "inLanguage": "ar",
                         "isPartOf": {"@type": "WebSite", "@id": SITE_BASE + "/#website",
                                      "name": SITE_NAME, "url": SITE_BASE + "/"}})
    leagues = []
    for c in comp_order:
        leagues.append({"comp": c, "icon": Markup(comp_icon(c)), "label": comp_label(c)})
    ad = adsense_slot()
    LEAGUE_TABS = [("table", "الترتيب"), ("scorers", "الهدافون"),
                   ("numbers", "الأرقام"), ("trend", "التطور"),
                   ("rounds", "الجولات")]
    # 2026-11-05: a league's view is a FRAGMENT at /matches/l/<slug> that the
    # page fetches on the first click (the 21 views inline were 472 KB of the
    # page); the template gets only the shell. The slug is COMP_SLUG's, like
    # the standings page; a competition without one is named by its index.
    os.makedirs(os.path.join(DIST, "matches", "l"), exist_ok=True)
    views = []
    for c in comp_order:
        st = st_by_comp.get(c)
        panes = league_stats_parts(c)
        if st and st.get("table"):
            panes["table"] = standings_table(
                c, st.get("table"), past=st.get("past"),
                season_label=st.get("season_label"), zeroed=st.get("zeroed"),
                form_map=forms.get(c, {}), embedded=True)
        if c in fx_by_comp:
            _fxs = COMP_SLUG.get(c)
            panes["rounds"] = league_rounds_panel(
                c, fx_by_comp[c], embedded=True, only_current=True,
                more_url=f"/fixtures/{_fxs}.html" if _fxs else None)
        live = [(k, lbl) for k, lbl in LEAGUE_TABS if panes.get(k)]
        if not live:
            continue
        tabs = []
        for i, (k, lbl) in enumerate(live):
            tabs.append((k, lbl))
        view_panes = []
        for i, (k, lbl) in enumerate(live):
            view_panes.append((k, Markup(panes[k])))
            pieces.append(panes[k])
        _vslug = COMP_SLUG.get(c) or f"c{len(views)}"
        write(f"matches/l/{_vslug}.html",
              render("_lview.html", v={"tabs": tabs, "panes": view_panes}))
        views.append({"comp": c, "src": f"/matches/l/{_vslug}"})
    # the days (shared with the home page since 2026-10-26: site_lib/daylist)
    days, _rows = day_sections(matches, ge_idx, comp_hrefs(
        {c for c, st in st_by_comp.items() if (st or {}).get("table")}, set(fx_by_comp)))
    pieces.extend(_rows)
    # every day as a fragment, today +-INLINE_SPAN also inline (2026-11-05)
    write_day_fragments(days)
    near_days, all_days = inline_days(days, REF_TODAY)
    # left rail: per-league fixtures BY DAY for leagues without round data
    comp_fix = {}
    for d in sorted_days:
        for m in daymap[d]:
            comp_fix.setdefault(m.get("competition") or "", {}).setdefault(d, []).append(m)
    rail = []
    for c in comp_order:
        if c not in fx_by_comp and comp_fix.get(c):
            entry = {"comp": c, "icon": Markup(comp_icon(c)), "label": comp_label(c), "days": []}
            for d in sorted(comp_fix[c].keys()):
                fday = {"heading": fmt_day(d), "minis": []}
                for m in comp_fix[c][d]:
                    mini = fixture_mini(m)
                    fday["minis"].append(Markup(mini))
                    pieces.append(mini)
                entry["days"].append(fday)
            rail.append(entry)
    feat, news = None, []
    if articles:
        fa = articles[0]
        feat = {"href": Markup(article_href(fa)), "has_img": bool(fa.get("image_url")),
                "img": thumb_url(fa["image_url"]) if fa.get("image_url") else "",
                "img_full": fa.get("image_url") or "",      # the big slot: srcset thumb + original (2026-10-18)
                "title": fa.get("title")}
        for a in articles[1:4]:
            img = thumb_url(a.get("image_url"))
            th = (f'<span class="mn-th"><img src="{esc(img)}" alt="" loading="lazy" decoding="async"></span>'
                  if img else '<span class="mn-th noimg">⚽</span>')
            news.append({"href": Markup(article_href(a)), "th": Markup(th),
                         "title": a.get("title"), "date": a.get("pub_date") or ""})
    popup = pred_pop(pieces)
    write("matches.html", render(
        "matches.html", page_head=Markup(page_head), leagues=leagues, ad=Markup(ad),
        views=views, filters=Markup(FILTERS_HTML), today=REF_TODAY, days=near_days,
        all_days=all_days, rail=rail,
        feat=feat, news=news, matches_js=Markup(MATCHES_JS + SHOT_JS), rounds_js=Markup(ROUNDS_JS),
        popup=Markup(popup), page_foot=Markup(foot())))
    return comp_order


def match_pages(_bycomp, _cal, _lparams, _match_arts, _plog, _preds, _squad, _tstats, articles,
                fixtures, forms, ge_idx, matches, md_idx, st_by_comp, urls, mstats=None,
                charts=None):
    """/m/<id> - one landing page per match (archive + current window): the
    long-tail queries a single /matches can never rank for («نتيجة مباراة X»،
    «موعد مباراة Y والقناة الناقلة»). Old pages persist through
    matches_archive.json so an indexed URL does not 404 once the match leaves
    the day window; pages get the live layer for free (match_row emits data-lv,
    LIVE_JS ships in foot()).

    Markup: site_src/templates/match.html (templated 2026-09-26). Everything
    else - the titles, the kick-off sentence, the readings, the noindex rule,
    the sitemap choice - is computed here in the same order and under the same
    names as before, so the helpers run in the same sequence and the values
    build() reads afterwards (m_all, and the loop's last _h, _html, _slug, a,
    comp, desc, img, m, st, title, v, when) end exactly where they used to."""
    os.makedirs(os.path.join(DIST, "m"), exist_ok=True)
    # الهدافون · صناعة الأهداف beside the table (2026-11-06): the same lists the
    # standings page shows, rendered once per competition. charts =
    # (sc_by_comp, sc_ok, as_by_comp, as_ok) from build(); absent = table only.
    sc_by_comp, sc_ok, as_by_comp, as_ok = charts or ({}, {}, {}, {})
    _chart_html = {}
    _table_html = {}

    def comp_charts(comp):
        if comp not in _chart_html:
            sc = sc_by_comp.get(comp) if sc_ok.get(comp) else None
            asst = as_by_comp.get(comp) if as_ok.get(comp) else None
            _chart_html[comp] = (scorers_list(sc, "أهداف", comp) if sc else "",
                                 scorers_list(asst, "صناعة", comp) if asst else "")
        return _chart_html[comp]
    # finished matches per competition (season pool + fixtures) - table_after()
    # uses it to prove the official table is describing THIS match and not a
    # later round
    _fin_by_comp = _finished_by_comp(fixtures, _bycomp)
    # h2h and rest days cross competitions (a club plays the league on Saturday
    # and the CAF Champions League on Tuesday), so keep a flat chronological list
    _fin_all = sorted((x for ms in _fin_by_comp.values() for x in ms),
                      key=lambda x: (x.get("kickoff") or "", x.get("koff_time") or ""))
    m_all = {m["match_id"]: m
             for m in load("matches_archive.json") if m.get("match_id")}
    for m in matches:
        if m.get("match_id"):
            m_all[m["match_id"]] = m      # day-window copy is always fresher
    # ±7 days, not ±30: see the sitemap note at the match-page append below
    sm_cut = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
    # ... and 7 days AHEAD too (SEO review 2026-11-18): every fixture of the
    # season was advertised, and two fixtures of one league months away share
    # 74-78% of their text (table, scorers, news) - Google answered with
    # «Crawled - not indexed». A far fixture stays built, linked and indexable;
    # it enters the sitemap when its week comes.
    sm_end = (datetime.date.today() + datetime.timedelta(days=7)).isoformat()
    # the days on which a match page really changes: line-ups, the score, the
    # reading after it
    lm_from = (datetime.date.today() - datetime.timedelta(days=2)).isoformat()
    lm_to = (datetime.date.today() + datetime.timedelta(days=2)).isoformat()
    n_mp = 0
    n_mp_idx = 0
    n_mp_sm = 0
    from urllib.parse import quote as _quote
    from site_lib.today_strip import today_strip as _ts
    _today_strip = _ts(matches)          # the same strip on every match page: built once
    for mid, m in sorted(m_all.items(), key=lambda kv: kv[1].get("kickoff") or ""):
        if not (m.get("home") and m.get("away") and m.get("kickoff")):
            continue
        # qualified names for the page text: Saudi «الأهلي» -> «الأهلي السعودي»
        h_ar = ar_team_in(m.get("home"), m.get("competition"))
        a_ar = ar_team_in(m.get("away"), m.get("competition"))
        comp = comp_label(m.get("competition") or "")
        st = (m.get("status") or "").upper()
        day_txt = fmt_day(m["kickoff"])
        hs, as_ = m.get("home_score"), m.get("away_score")
        when = day_txt + (f" الساعة {m['koff_time']} بتوقيت القاهرة"
                          if m.get("koff_time") else "")
        # a cup tie decided on penalties (2026-11-10): the title and the
        # description name the shoot-out - «0-0» alone reads as a draw
        _hp, _ap = m.get("home_pens"), m.get("away_pens")
        _pens = (f" ({_hp}-{_ap} بركلات الترجيح)" if st == "FINISHED" and _hp is not None and _ap is not None else "")
        _pen_win = (f" وتأهل {h_ar if _hp > _ap else a_ar} بركلات الترجيح {max(_hp, _ap)}-{min(_hp, _ap)}"
                    if _pens else "")
        # a highlight video from the rights holder (highlights.py) - the title
        # then answers «أهداف مباراة X وY» / «ملخص مباراة X وY», what readers
        # type the day after (user, 2026-11-04: «Yes, change it»)
        _hl = highlight_links().get(str(m.get("match_id")))
        if st == "FINISHED" and hs is not None and _hl:
            title = f"أهداف وملخص مباراة {h_ar} و{a_ar} {hs}-{as_}{_pens} — {comp} | {SITE_NAME}"
            _chn = f" من {_hl[1]}" if _hl[1] else ""
            desc = (f"شاهد أهداف وملخص مباراة {h_ar} و{a_ar} بالفيديو{_chn}. "
                    f"انتهت المباراة بنتيجة {hs}-{as_} في {comp} يوم {day_txt}. "
                    "مسجلو الأهداف وترتيب البطولة هنا.")
        elif st == "FINISHED" and hs is not None:
            title = f"نتيجة مباراة {h_ar} و{a_ar} {hs}-{as_}{_pens} — {comp} | {SITE_NAME}"
            desc = (f"انتهت مباراة {h_ar} و{a_ar} في {comp} يوم {day_txt} "
                    f"بنتيجة {hs}-{as_}{_pen_win}. مسجلو الأهداف وترتيب البطولة هنا.")
        elif st == "LIVE":
            title = f"مباراة {h_ar} و{a_ar} مباشر الآن — {comp} | {SITE_NAME}"
            desc = (f"تابع الآن مباشرة مباراة {h_ar} و{a_ar} في {comp} — "
                    "النتيجة لحظة بلحظة ومسجلو الأهداف.")
        elif st == "POSTPONED":
            title = f"تأجيل مباراة {h_ar} و{a_ar} — {comp} | {SITE_NAME}"
            desc = f"تأجلت مباراة {h_ar} و{a_ar} في {comp} التي كانت مقررة يوم {day_txt}."
        else:
            title = (f"موعد مباراة {h_ar} و{a_ar} والقنوات الناقلة — "
                     f"{comp} | {SITE_NAME}")
            # the channel in the snippet (SEO review 2026-11-13: 0 of 220
            # upcoming pages named it there, though the page shows it)
            _ch = m.get("channel") or match_tv(m)
            desc = (f"موعد مباراة {h_ar} و{a_ar} في {comp}: {when}."
                    + (f" القناة الناقلة: {_ch}." if _ch else "")
                    + " النتيجة المباشرة ومسجلو الأهداف هنا.")
        # the match's own article (layer 3, 2026-09-16) is picked here, before
        # the head: its picture (the matchup card, drawn now if the writer's
        # run left none) is the page's og:image. Without it the 95px crest
        # fell through to the site banner on every Facebook link preview
        # (2026-10-18, the Brentford x Liverpool report).
        _art = pick_match_article(_match_arts.get(str(mid)) or [], st)
        img = ensure_match_image(m, _art, st) if _art else None
        if not img and m.get("home_badge"):
            _lc = local_crest(m["home_badge"])
            img = _lc if _lc.startswith("http") else SITE_BASE + _lc
        murl = f"/m/{mid}.html"
        _goals = match_goals(ge_idx, m)
        # og:type=article when the page carries its story (SEO audit 2026-11-06)
        page_head = head(title, desc, SITE_BASE + murl, image=img, active="matches",
                         og_type="article" if _art else "website")
        # the day too (site review 2026-11-20): an upcoming match showed
        # «22:00» with no day - the date sat two cards lower
        hero_row = match_row(m, show_time=True, show_comp=True, goals=_goals,
                             highlight=_hl, show_assist=True, show_date=True)
        # THE VIDEO PLAYS HERE (SEO review 2026-11-20: 122 «أهداف وملخص» pages
        # sent the reader to YouTube - the intent is "watch"). A thumbnail
        # until it is tapped (no player weight before that), and only for a
        # video its rights holder lets other sites play (media.highlight_video);
        # the rest keep the «الأهداف» link in the row above. VideoObject data
        # only with the video's REAL upload date - never the day we found it.
        _video = ""
        _hv = highlight_video(m.get("match_id")) if (st == "FINISHED" and hs is not None) else None
        if _hv:
            from site_lib.widgets import video_facade
            _vt = f"أهداف وملخص مباراة {h_ar} و{a_ar} {hs}-{as_}"
            _video = (f'<section class="minfo mp-video" id="mp-video"><h2>{esc(_vt)} بالفيديو</h2>'
                      + video_facade({"video_id": _hv["vid"], "title": _vt})
                      + f'<p class="hintline">الفيديو من قناة {esc(_hv.get("channel") or "")} الرسمية على يوتيوب.</p></section>')
            if _hv.get("published"):
                _video += jsonld({"@context": "https://schema.org", "@type": "VideoObject", "name": _vt,
                                  "description": f"{_vt} في {comp} - من قناة {_hv.get('channel') or ''} الرسمية.",
                                  "thumbnailUrl": [f"https://i.ytimg.com/vi/{_hv['vid']}/hqdefault.jpg"],
                                  "uploadDate": _hv["published"],
                                  "embedUrl": f"https://www.youtube.com/embed/{_hv['vid']}",
                                  "contentUrl": f"https://www.youtube.com/watch?v={_hv['vid']}"})
        kickoff_info = st not in ("FINISHED", "POSTPONED")
        _tw = _rd = ""
        if kickoff_info:
            _tw = f"يوم {day_txt}"
            if m.get("koff_time"):
                _sa = ""
                try:
                    from zoneinfo import ZoneInfo
                    _dt = datetime.datetime.fromisoformat(
                        f"{m['kickoff']}T{m['koff_time']}:00"
                    ).replace(tzinfo=ZoneInfo("Africa/Cairo"))
                    _sa = _dt.astimezone(ZoneInfo("Asia/Riyadh")).strftime("%H:%M")
                except Exception:
                    pass
                if _sa == m["koff_time"]:
                    _tw += (f" في تمام الساعة {m['koff_time']} بتوقيت القاهرة "
                            "ومكة المكرمة")
                elif _sa:
                    _tw += (f" في تمام الساعة {m['koff_time']} بتوقيت القاهرة "
                            f"({_sa} بتوقيت مكة المكرمة)")
                else:
                    _tw += f" في تمام الساعة {m['koff_time']} بتوقيت القاهرة"
            _rd = (f"الجولة {m['round']} من " if m.get("round")
                   else f"{m['stage']} من " if m.get("stage") else "")   # a cup's stage (2026-11-03)
        # the story sits above the computed reading, which is what backs it
        # with numbers (_art picked above, with its image settled)
        article_block = (match_article_block(_art, m.get("competition") or "",
                                             page_title=title.split(" — ")[0], status=st)
                         if _art else "")
        # «قراءة قبل المباراة» (layer 1): how the two clubs arrive. No longer
        # SHOWN (user, 2026-10-31 - match.html); still computed because its
        # weight keeps the upcoming page indexed (user: keep them indexed, new
        # pre-match information is coming) and its FAQ still renders.
        _pre_weight = 0
        pre_read = ""
        if st == "UPCOMING":
            _pre, _pre_faq, _pre_weight = pre_match_read(
                m, h_ar, a_ar, comp,
                st_by_comp.get(m.get("competition")),
                forms.get(m.get("competition")) or {},
                _fin_by_comp.get(m.get("competition")) or [], _fin_all,
                _preds.get(str(mid)))
            if _pre:
                pre_read = _pre
        _det = match_details_for(md_idx, m)
        # «قراءة المباراة» - the summary goes ABOVE the evidence
        _faq_html = _pre_faq if st == "UPCOMING" and _pre_weight else ""
        post_read = ""
        if st == "FINISHED" and _det and hs is not None and as_ is not None:
            _read, _faq_html = post_match_read(
                m, _det[0], _det[1], h_ar, a_ar, hs, as_, comp,
                st_by_comp.get(m.get("competition")),
                forms.get(m.get("competition")) or {},
                _fin_by_comp.get(m.get("competition")) or [])
            if _read:
                post_read = _read
        details = ""
        if _det:
            details = match_details_html(_det[0], _det[1], h_ar, a_ar)
        else:
            # announced XI before kick-off: the pitch, then who is missing
            _pre = prematch_for(md_idx, m)
            if _pre:
                details = match_details_html(_pre[0], _pre[1], h_ar, a_ar)
        if st == "FINISHED":
            # «أرقام المباراة»: xG + shots (match_stats.py), above the lineups
            details = match_stats_html((mstats or {}).get(str(mid)), h_ar, a_ar) + details
        absence = absence_block(_squad, m.get("competition"), m, h_ar, a_ar)
        # jump chips (site review 2026-11-19): on a finished page the report
        # is ~4700px tall and stands before the timeline and the line-ups.
        # The order stays as approved; one row of #anchor links under the score.
        jump = ""
        if st == "FINISHED":
            article_block, details, jump = jump_chips(article_block, details)
        # «توقع الجون»: model probabilities for an upcoming match; for a
        # finished one, what the model said before kick-off vs the result
        _pb = pred_block(m, _preds.get(str(mid)) if st == "UPCOMING" else None,
                         _plog.get(str(mid)), _tstats.get(m.get("competition"), {}),
                         params=_lparams.get(m.get("competition")), cal=_cal)
        info = [("البطولة", comp)]
        if m.get("round"):
            info.append(("الجولة", str(m["round"])))
        elif m.get("stage"):
            info.append(("الدور", m["stage"]))     # كأس مصر (2026-11-03)
        info.append(("التاريخ", day_txt))
        if m.get("koff_time"):
            info.append(("موعد الانطلاق", f"{m['koff_time']} بتوقيت القاهرة"))
        if m.get("channel"):
            info.append(("القناة الناقلة", str(m["channel"])))
        elif st != "FINISHED" and match_tv(m):
            # growth plan 2026-10-08: «موعد المباراة والقنوات الناقلة» is the
            # title's promise; the verified per-competition map keeps it when
            # the feed names no channel (every European league, in practice)
            info.append(("القنوات الناقلة", match_tv(m)))
        state_txt = {"FINISHED": "انتهت", "LIVE": "جارية الآن",
                     "UPCOMING": "لم تبدأ بعد", "POSTPONED": "مؤجلة"}.get(st)
        if state_txt:
            info.append(("الحالة", state_txt))
        info_rows = []
        for k, v in info:
            # the live layer overwrites the state text while the match can still
            # move (UPCOMING -> LIVE -> FINISHED); a finished page stays static
            info_rows.append((k, str(v), k == "الحالة" and st in ("UPCOMING", "LIVE")))
        _clubs = [tp for tp in TEAM_PAGES if _team_match(tp, m)]
        stc = st_by_comp.get(m.get("competition"))
        table = table_heading = ""
        if stc and stc.get("table"):
            _slug = COMP_SLUG.get(m.get("competition"))
            # the league's name alone (user, 2026-11-07: «خليها الدورى الانجليزى»):
            # the section holds الترتيب · الهدافون · صناعة الأهداف since the tabs
            _h = (f'<a href="/standings/{_slug}.html">{esc(comp)} ←</a>'
                  if _slug else esc(comp))
            table_heading = _h
            # the same table for every match of a competition: built once.
            # «لعب / ف / ت / خ» open the team's matches here too (2026-11-07);
            # the match rows come from /standings/<slug> on the first tap
            _ck = m.get("competition")
            if _ck not in _table_html:
                _table_html[_ck] = standings_table(
                    _ck, stc["table"], past=stc.get("past"),
                    season_label=stc.get("season_label"), zeroed=stc.get("zeroed"),
                    form_map=forms.get(_ck, {}), embedded=True,
                    games=((_bycomp or {}).get(_ck) or []) if _slug else None,
                    store_src=f"/standings/{_slug}" if _slug else None)
            table = _table_html[_ck]
        _sc_h, _as_h = comp_charts(m.get("competition")) if table else ("", "")
        # the two sides' own stories first (site review 2026-11-19: الأهلي ×
        # بيراميدز opened its news with a story about Barcelona); the general
        # list only when neither side has a club page or a story
        news, news_title = [], "آخر الأخبار"

        def _news_row(a):
            # the /news row, picture + title (site review 2026-11-20: the
            # match page listed its stories as bare bullets)
            from site_lib.shell import thumb_url as _thumb
            _ni = _thumb(a.get("image_url"))
            return {"href": Markup(article_href(a)), "title": a["title"],
                    "th": Markup(f'<span class="al-th"><img src="{esc(_ni)}" alt="" loading="lazy" decoding="async"></span>'
                                 if _ni else '<span class="al-th noimg">⚽</span>')}
        _tps = [tp for tp in TEAM_PAGES if _team_match(tp, m)]
        if articles and _tps:
            from site_lib.names import _team_news
            for a in articles:
                if any(_team_news(tp, a) for tp in _tps):
                    news.append(_news_row(a))
                    if len(news) == 4:
                        break
            if news:
                news_title = "أخبار " + " و".join(tp["name"] for tp in _tps[:2])
        if articles and not news:
            for a in articles[:4]:
                news.append(_news_row(a))
        # the two sides in the table: their rows marked, and - before the match
        # is over - a two-line card with where each stands and its last five
        form_card = ""
        if table and stc and stc.get("table") and not stc.get("zeroed"):
            from site_lib.tables import form_dots
            _fm = forms.get(m.get("competition"), {}) or {}
            _rows = {r.get("team"): r for r in stc["table"]}
            _two = [(_rows.get(m.get(k)), m.get(k)) for k in ("home", "away")]
            for _r, _nm in _two:
                if _r:
                    _b = f'<bdi>{esc(ar_team(_nm))}</bdi>'
                    table = table.replace(_b, f'<bdi class="lt-me">{esc(ar_team(_nm))}</bdi>', 1)
            if st != "FINISHED" and all(r for r, _ in _two):
                def _fline(r, nm):
                    _c = (f'<img src="{esc(local_crest(r["crest"]))}" alt="" width="26" height="26" loading="lazy">'
                          if r.get("crest") else "")
                    _p = int(r.get("pts") or 0)
                    return ('<div class="fc-r">' + _c + f'<b><bdi>{esc(ar_team(nm))}</bdi></b>'
                            f'<span class="fc-p">المركز {esc(str(r.get("pos")))} · {_p} {"نقاط" if 3 <= _p <= 10 else "نقطة"}</span>'
                            f'<span class="fc-f">{form_dots(_fm.get(nm, []))}</span></div>')
                form_card = ('<section class="minfo form-card"><h2>الفريقان قبل المباراة</h2>'
                             + "".join(_fline(r, nm) for r, nm in _two)
                             + '<p class="fc-k">آخر 5 مباريات لكل فريق: أخضر فوز، رمادي تعادل، أحمر خسارة. الأحدث على اليسار.</p></section>')
        # the competition crumb links its hub (SEO audit 2026-11-06: it pointed
        # at the page itself on ~1,190 indexed match pages - the standings and
        # fixtures pages had no link from them); the last crumb is the page
        _cslug = COMP_SLUG.get(m.get("competition"))
        comp_href = ""
        if _cslug:
            from site_lib.competitions import GROUP_PAGES as _GP
            comp_href = (f"/standings/{_cslug}.html"
                         if ((stc and stc.get("table")) or m.get("competition") in _GP)
                         else f"/fixtures/{_cslug}.html")
        crumbs_ld = breadcrumb_ld([("الرئيسية", SITE_BASE + "/")]
                                  + ([(comp, SITE_BASE + comp_href)] if comp_href else [])
                                  + [(title.split(" — ")[0], SITE_BASE + murl)])
        _html = render(
            "match.html", page_head=Markup(page_head), comp=comp, comp_href=Markup(comp_href),
            h_ar=h_ar, a_ar=a_ar,
            h1=title.split(" — ")[0],
            hero_row=Markup(hero_row), kickoff_info=kickoff_info, round_txt=Markup(_rd),
            when_txt=Markup(_tw), channel=str(m["channel"]) if m.get("channel") else "",
            comp_tv=match_tv(m),
            jump=Markup(jump),
            article_block=Markup(article_block), pre_read=Markup(pre_read),
            post_read=Markup(post_read), details=Markup(details), absence=Markup(absence),
            prediction=Markup(_pb or ""), info=info_rows, show_info=st != "FINISHED",
            # the top-rated starter under the score (2026-11-06), finished only
            motm=Markup(motm_html(_det[0], _det[1], h_ar, a_ar, m.get("home_badge"), m.get("away_badge"))
                        if st == "FINISHED" and _det else ""),
            clubs=[{"slug": Markup(tp["slug"]), "name": tp["name"]} for tp in _clubs],
            # the pair's head-to-head page, from every match between the two
            h2h=(lambda _p: {"href": Markup(f'/h2h/{_p["slug"]}.html'), "label": _H2H.link_label(_p)}
                 if _p else None)(_H2H.pair_of_match(m.get("home"), m.get("away"))),
            has_table=bool(stc and stc.get("table")), table_heading=Markup(table_heading),
            table=Markup(table), faq=Markup(_faq_html or ""), news=news, news_title=news_title,
            # follow + share + today's matches (site review 2026-11-20: the page
            # behind every match post was a dead end)
            video=Markup(_video), video_js=Markup(VIDEO_JS if _video else ""),
            lead=({"slug": Markup(_clubs[0]["slug"]), "name": _clubs[0]["name"]} if _clubs else None),
            share_href=Markup("https://wa.me/?text=" + _quote(f"{title.split(' — ')[0]} {SITE_BASE}/m/{mid}")),
            share_url=Markup(f"{SITE_BASE}/m/{mid}"), today_strip=Markup(_today_strip),
            form_card=Markup(form_card),
            label=comp, has_sc=bool(_sc_h), scorers=Markup(_sc_h),
            has_asst=bool(_as_h), assists=Markup(_as_h), tabs_js=Markup(ST_TABS_JS),
            games_js=Markup(LT_GAMES_JS if 'class="lt-n"' in table else ""),
            crumbs_ld=Markup(crumbs_ld), page_foot=Markup(foot()))
        # lastmod must be TRUE or absent (SEO review 2026-11-18: 317 match
        # pages said «today» every day, and Google drops a lastmod it catches
        # lying - the articles' real dates lose their weight with it).
        # Within two days of kick-off the page really changes -> today. An old
        # finished match settled on its kick-off day. A fixture further away
        # changes only in its shared blocks: the date of its article if it
        # carries one, otherwise no lastmod at all.
        if lm_from <= m["kickoff"] <= lm_to:
            _LASTMOD[murl] = REF_TODAY
        elif m["kickoff"] < lm_from:
            _LASTMOD[murl] = m["kickoff"]
        else:
            _am = (_art or {}).get("updated_ts") or (_art or {}).get("pub_ts") or (_art or {}).get("pub_date")
            if _am:
                _LASTMOD[murl] = _am
            else:
                _LASTMOD.pop(murl, None)
        # AdSense "low value content" rejection (2026-09-04): a match page with
        # no real content yet stays reachable but is NOINDEXed and out of the
        # sitemap; it becomes indexable once the content arrives. Since
        # 2026-09-14 a fixture whose pre-match reading found at least four
        # substantive facts counts as content (a guide, not a stub). Since
        # 2026-10-22 (the 4th rejection named "thin content" and the sitemap
        # carried 386 match pages) a score or a lineup sheet alone no longer
        # counts: a finished match is content only with its reading (story,
        # ratings or the table after), i.e. what no scoreboard site repeats.
        _rich = bool(_art) or (st == "FINISHED" and bool(post_read)) or _pre_weight >= 4
        if not _rich:
            _html = noindex(_html)
        write(f"m/{mid}.html", _html)
        n_mp += 1
        if _rich:
            n_mp_idx += 1
            # WHAT WE ADVERTISE vs what we publish (2026-09-20): every rich match
            # page stays indexable and linked; the sitemap carries only the last
            # 7 days + everything to come, any curated-club match, and any page
            # carrying an original article (that URL replaced an article URL).
            # a LEAGUE page's club (2026-11-20) does not keep its matches in
            # the sitemap for the season: that would put every Egyptian and
            # Saudi league match there - the thin pages the cap is for
            if sm_cut <= m["kickoff"] <= sm_end or _art or any(not tp.get("league_page") for tp in _clubs):
                urls.append(murl)
                n_mp_sm += 1
    print(f"  + match pages: {n_mp} ({n_mp_idx} indexable, {n_mp_sm} in the sitemap)")
    return m_all
