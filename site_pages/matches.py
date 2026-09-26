"""/matches and the per-match pages (/m/<id>).

Moved verbatim out of build_site.py (2026-09-26, tools/move_names.py):
source and comments exactly as they were there. Edit here; build_site
imports these back under the same names."""
import datetime
import os
from site_lib.articles import match_article_block
from site_lib.clubs import TEAM_PAGES
from site_lib.competitions import COMP_ORDER, COMP_SLUG, COMP_TV
from site_lib.config import DIST, REF_TODAY, SITE_BASE, SITE_NAME, load
from site_lib.crests import comp_icon, local_crest
from site_lib.dates import fmt_day
from site_lib.matchdata import absence_block, match_details_for, match_goals, prematch_for
from site_lib.names import _team_match, ar_team, comp_label
from site_lib.predictions import pred_block, pred_pop
from site_lib.reads import post_match_read, pre_match_read
from site_lib.render import Markup, render
from site_lib.shell import _LASTMOD, adsense_slot, foot, head, thumb_url, write
from site_lib.snippets import FILTERS_HTML, MATCHES_JS, ROUNDS_JS
from site_lib.stats import _finished_by_comp
from site_lib.tables import fixture_mini, league_rounds_panel, match_details_html, match_row, standings_table
from site_lib.text import esc
from site_lib.urls import article_href, breadcrumb_ld, match_url, pick_match_article


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
    page_head = head(f"مواعيد ونتائج المباريات — {SITE_NAME}",
                     "مواعيد ونتائج مباريات كرة القدم بتوقيت القاهرة على يلا سكور.",
                     SITE_BASE + "/matches.html", active="matches")
    leagues = []
    for c in comp_order:
        leagues.append({"comp": c, "icon": Markup(comp_icon(c)), "label": comp_label(c)})
    ad = adsense_slot()
    LEAGUE_TABS = [("table", "الترتيب"), ("scorers", "الهدافون"),
                   ("numbers", "الأرقام"), ("trend", "التطور"),
                   ("rounds", "الجولات")]
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
        views.append({"comp": c, "tabs": tabs, "panes": view_panes})
    days = []
    for d in sorted_days:
        day = {"day": d, "heading": fmt_day(d), "comps": []}
        comps = OrderedDict()
        for m in daymap[d]:
            comps.setdefault(m.get("competition") or "", []).append(m)
        # same fixed league order as the sidebar
        for comp, ms in sorted(comps.items(),
                               key=lambda kv: (COMP_ORDER.index(kv[0])
                                               if kv[0] in COMP_ORDER
                                               else len(COMP_ORDER), kv[0])):
            block = {"comp": comp, "label": comp_label(comp), "rows": []}
            if comp:
                block["icon"] = Markup(comp_icon(comp))
                comp_label(comp)                 # (the old code asked twice; kept for order)
            for m in ms:
                _mid, _mst = str(m.get("match_id")), (m.get("status") or "").upper()
                row = match_row(m, show_time=True, show_comp=False,
                                goals=match_goals(ge_idx, m),
                                link=match_url(m),
                                pred=_preds.get(_mid) if _mst == "UPCOMING" else None,
                                done=_plog.get(_mid) if _mst == "FINISHED" else None)
                # filter hooks: "على التلفزيون" = a known broadcaster (per-match
                # channel or the verified COMP_TV map); "حسب الوقت" sorts by data-ko
                tv = "1" if (m.get("channel") or COMP_TV.get(comp)) else "0"
                row = row.replace('<div class="mrow ',
                                  f'<div data-tv="{tv}" data-ko="{esc(m.get("koff_time") or "")}" class="mrow ', 1)
                block["rows"].append(Markup(row))
                pieces.append(row)
            day["comps"].append(block)
        days.append(day)
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
                "title": fa.get("title")}
        for a in articles[1:4]:
            img = thumb_url(a.get("image_url"))
            th = (f'<span class="mn-th" style="background-image:url(\'{esc(img)}\')"></span>'
                  if img else '<span class="mn-th noimg">⚽</span>')
            news.append({"href": Markup(article_href(a)), "th": Markup(th),
                         "title": a.get("title"), "date": a.get("pub_date") or ""})
    popup = pred_pop(pieces)
    write("matches.html", render(
        "matches.html", page_head=Markup(page_head), leagues=leagues, ad=Markup(ad),
        views=views, filters=Markup(FILTERS_HTML), today=REF_TODAY, days=days, rail=rail,
        feat=feat, news=news, matches_js=Markup(MATCHES_JS), rounds_js=Markup(ROUNDS_JS),
        popup=Markup(popup), page_foot=Markup(foot())))
    return comp_order


def match_pages(_bycomp, _cal, _lparams, _match_arts, _plog, _preds, _squad, _tstats, articles,
                fixtures, forms, ge_idx, matches, md_idx, st_by_comp, urls):
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
    n_mp = 0
    n_mp_idx = 0
    n_mp_sm = 0
    for mid, m in sorted(m_all.items(), key=lambda kv: kv[1].get("kickoff") or ""):
        if not (m.get("home") and m.get("away") and m.get("kickoff")):
            continue
        h_ar, a_ar = ar_team(m.get("home")), ar_team(m.get("away"))
        comp = comp_label(m.get("competition") or "")
        st = (m.get("status") or "").upper()
        day_txt = fmt_day(m["kickoff"])
        hs, as_ = m.get("home_score"), m.get("away_score")
        when = day_txt + (f" الساعة {m['koff_time']} بتوقيت القاهرة"
                          if m.get("koff_time") else "")
        if st == "FINISHED" and hs is not None:
            title = f"نتيجة مباراة {h_ar} و{a_ar} {hs}-{as_} — {comp} | {SITE_NAME}"
            desc = (f"انتهت مباراة {h_ar} و{a_ar} في {comp} يوم {day_txt} "
                    f"بنتيجة {hs}-{as_}. مسجلو الأهداف وترتيب البطولة هنا.")
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
            desc = (f"موعد مباراة {h_ar} و{a_ar} في {comp}: {when}، "
                    "والقنوات الناقلة للمباراة. النتيجة المباشرة ومسجلو "
                    "الأهداف هنا فور انطلاق اللقاء.")
        img = None
        if m.get("home_badge"):
            _lc = local_crest(m["home_badge"])
            img = _lc if _lc.startswith("http") else SITE_BASE + _lc
        murl = f"/m/{mid}.html"
        _goals = match_goals(ge_idx, m)
        page_head = head(title, desc, SITE_BASE + murl, image=img, active="matches")
        hero_row = match_row(m, show_time=True, show_comp=True, goals=_goals)
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
            _rd = f"الجولة {m['round']} من " if m.get("round") else ""
        # the match's own article (layer 3, 2026-09-16): the story sits above
        # the computed reading, which is what backs it with numbers
        _art = pick_match_article(_match_arts.get(str(mid)) or [], st)
        article_block = match_article_block(_art, m.get("competition") or "") if _art else ""
        # «قراءة قبل المباراة» (layer 1): how the two clubs arrive
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
        absence = absence_block(_squad, m.get("competition"), m, h_ar, a_ar)
        # «توقع يلا سكور»: model probabilities for an upcoming match; for a
        # finished one, what the model said before kick-off vs the result
        _pb = pred_block(m, _preds.get(str(mid)) if st == "UPCOMING" else None,
                         _plog.get(str(mid)), _tstats.get(m.get("competition"), {}),
                         params=_lparams.get(m.get("competition")), cal=_cal)
        info = [("البطولة", comp)]
        if m.get("round"):
            info.append(("الجولة", str(m["round"])))
        info.append(("التاريخ", day_txt))
        if m.get("koff_time"):
            info.append(("موعد الانطلاق", f"{m['koff_time']} بتوقيت القاهرة"))
        if m.get("channel"):
            info.append(("القناة الناقلة", str(m["channel"])))
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
            _h = (f'<a href="/standings/{_slug}.html">ترتيب {esc(comp)} ←</a>'
                  if _slug else f'ترتيب {esc(comp)}')
            table_heading = _h
            table = standings_table(m.get("competition"), stc["table"],
                                    past=stc.get("past"),
                                    season_label=stc.get("season_label"),
                                    zeroed=stc.get("zeroed"),
                                    form_map=forms.get(m.get("competition"), {}),
                                    embedded=True)
        news = []
        if articles:
            for a in articles[:4]:
                news.append({"href": Markup(article_href(a)), "title": a["title"]})
        crumbs_ld = breadcrumb_ld([("أخبار", SITE_BASE + "/"),
                                   ("المباريات", SITE_BASE + "/matches.html"),
                                   (comp, SITE_BASE + murl)])
        _html = render(
            "match.html", page_head=Markup(page_head), comp=comp, h_ar=h_ar, a_ar=a_ar,
            hero_row=Markup(hero_row), kickoff_info=kickoff_info, round_txt=Markup(_rd),
            when_txt=Markup(_tw), channel=str(m["channel"]) if m.get("channel") else "",
            comp_tv=COMP_TV.get(m.get("competition")) or "",
            article_block=Markup(article_block), pre_read=Markup(pre_read),
            post_read=Markup(post_read), details=Markup(details), absence=Markup(absence),
            prediction=Markup(_pb or ""), info=info_rows,
            clubs=[{"slug": Markup(tp["slug"]), "name": tp["name"]} for tp in _clubs],
            has_table=bool(stc and stc.get("table")), table_heading=Markup(table_heading),
            table=Markup(table), faq=Markup(_faq_html or ""), news=news,
            crumbs_ld=Markup(crumbs_ld), page_foot=Markup(foot()))
        # lastmod: a page whose match is recent/upcoming changes every run;
        # an old finished match settled around its kickoff day.
        _LASTMOD[murl] = (REF_TODAY if m["kickoff"] >= (datetime.date.today()
                                                        - datetime.timedelta(days=2)).isoformat()
                          else m["kickoff"])
        # AdSense "low value content" rejection (2026-09-04): a match page with
        # no real content yet (no scorers, no lineups/details) stays reachable
        # but is NOINDEXed and out of the sitemap; it becomes indexable once the
        # data arrives. Since 2026-09-14 a fixture whose pre-match reading found
        # at least four substantive facts counts as content (a guide, not a stub).
        _rich = bool(_art) or bool(_goals) or bool(_det) or _pre_weight >= 4
        if not _rich:
            _html = _html.replace("<head>", '<head><meta name="robots" content="noindex">', 1)
        write(f"m/{mid}.html", _html)
        n_mp += 1
        if _rich:
            n_mp_idx += 1
            # WHAT WE ADVERTISE vs what we publish (2026-09-20): every rich match
            # page stays indexable and linked; the sitemap carries only the last
            # 7 days + everything to come, any curated-club match, and any page
            # carrying an original article (that URL replaced an article URL).
            if m["kickoff"] >= sm_cut or _art or _clubs:
                urls.append(murl)
                n_mp_sm += 1
    print(f"  + match pages: {n_mp} ({n_mp_idx} indexable, {n_mp_sm} in the sitemap)")
    return m_all
