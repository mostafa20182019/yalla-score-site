"""The curated clubs' pages (/team/<slug>) - slugs are indexed URLs, never
rename them.

Moved verbatim out of build_site.py (2026-09-26, tools/move_names.py):
source and comments exactly as they were there. Edit here; build_site
imports these back under the same names."""
import os
from site_lib.clubs import TEAM_PAGES
from site_lib.competitions import COMP_SLUG
from site_lib.config import DIST, HERE, REF_TODAY, SITE_BASE, SITE_NAME, VAPID_PUBLIC_KEY
from site_lib.crests import local_crest
from site_lib.dates import art_reltime
from site_lib.names import _team_match, _team_news, comp_label
from site_lib.predictions import pred_pop
from site_lib.render import Markup, render
from site_lib.follow import my_block_html, my_json
from site_lib.shell import _clean_urls, foot, head, thumb_url, write, write_text
from site_lib.stats import more_matches_txt
from site_lib.tables import match_row, standings_table
from site_lib.text import esc, jsonld
from site_lib.urls import article_href, breadcrumb_ld, match_url


def club_pages(_plog, _preds, articles, forms, m_all, season, st_by_comp, urls,
               fx_by_comp=None, sc_by_comp=None, sc_ok=None, md_idx=None, groups_by_comp=None):
    """/team/<slug> - evergreen SEO hubs for the highest-volume Arabic query
    family: «أخبار الأهلي اليوم»، «مباريات الزمالك القادمة»، «نتيجة ريال مدريد».
    One page per curated club: latest news + next matches + recent results +
    league standing, refreshed every publish cycle; cross-linked from article
    pages, match pages (club-chips) and the footer. Markup: club.html
    (templated 2026-09-26); the pieces are built here in the same order as
    before. Returns the loop's last _img / a / img / r under the same names."""
    os.makedirs(os.path.join(DIST, "team"), exist_ok=True)
    os.makedirs(os.path.join(DIST, "my"), exist_ok=True)     # «تابع فريقك» fragments
    club_matches_src = sorted(m_all.values(),
                              key=lambda m: m.get("kickoff") or "")
    for tp in TEAM_PAGES:
        name, slug = tp["name"], tp["slug"]
        league_ar = comp_label(tp["league"])
        cm = [m for m in club_matches_src
              if _team_match(tp, m) and m.get("home") and m.get("kickoff")]
        # the next matches come from the SEASON, not only the day window of
        # m_all (SEO review 2026-11-13: Trabzonspor's page showed 1 of its 11
        # scheduled matches). A match without a page yet is a row with no link.
        _seen = {m.get("match_id") for m in cm}
        # a postponed match (2026-11-25, the Egypt Cup round of 16): the day
        # window keeps its OLD date - unplayed, in the past - while the season
        # file has the new one. The season's copy is the one that is still to
        # come, so it is not dropped as «already seen».
        _old = {m.get("match_id") for m in cm
                if (m.get("status") or "").upper() not in ("FINISHED", "LIVE", "IN_PLAY", "PAUSED")
                and m.get("home_score") is None and (m.get("kickoff") or "") < REF_TODAY}
        _later = [m for fx in (fx_by_comp or {}).values() for r in (fx or {}).get("rounds") or []
                  for m in r.get("matches") or []
                  if (m.get("match_id") not in _seen
                      or (m.get("match_id") in _old and (m.get("kickoff") or "") >= REF_TODAY))
                  and _team_match(tp, m)
                  and m.get("home") and m.get("kickoff")]
        # THE WHOLE SEASON is on the page (SEO review 2026-11-20: الأهلي's page
        # listed 5 of the 18 matches the data holds, and «جدول مباريات الأهلي
        # 2026-2027» had nothing to land on). The first five stay as they
        # were - the FAQ, the follow block and the card read them - and the
        # rest sit under them in a <details>: in the HTML, closed on screen.
        _up_all = sorted((m for m in cm + _later
                          if (m.get("status") or "").upper() in ("UPCOMING", "LIVE")
                          and m["kickoff"] >= REF_TODAY),
                         key=lambda m: (m.get("kickoff") or "", m.get("koff_time") or ""))
        up_next = _up_all[:5]
        _season_from = f"{str(season)[:4]}-07-01" if str(season)[:4].isdigit() else ""
        _res_all = [m for m in reversed(cm)
                    if (m.get("status") or "").upper() == "FINISHED"
                    and m.get("home_score") is not None]
        last_res = _res_all[:5]
        up_more = [match_row(m, show_time=True, show_comp=True, show_date=True, card_link=False,
                             link=match_url(m) if m.get("match_id") in m_all else None)
                   for m in _up_all[5:]]
        last_more = [match_row(m, show_time=False, show_comp=True, show_date=True, card_link=False,
                               link=match_url(m))
                     for m in _res_all[5:] if not _season_from or m["kickoff"] >= _season_from]
        news = [a for a in articles if _team_news(tp, a)][:8]
        st = st_by_comp.get(tp["league"])
        srow = None
        if st and st.get("table") and not st.get("zeroed"):
            for r in st["table"]:
                if any(t in (r.get("team") or "") for t, _ in tp["match_tokens"]):
                    srow = r
                    break
        crest = ""
        if srow and srow.get("crest"):
            crest = local_crest(srow["crest"])
        else:
            for m in reversed(cm):
                for side in ("home", "away"):
                    if (any(t in (m.get(side) or "")
                            for t, _ in tp["match_tokens"])
                            and m.get(side + "_badge")):
                        crest = local_crest(m[side + "_badge"])
                        break
                if crest:
                    break
        t_url = f"/team/{slug}.html"
        # 2026-10-12 (user «نفذه الآن»): GSC's first non-branded impressions were
        # «نتيجة ريال مدريد اليوم / الآن» and «آخر أخبار نادي بيراميدز» - the title
        # now answers the result intent first, and the description opens with
        # the last score and the next fixture instead of a generic sentence.
        from site_lib.dates import day_month
        from site_lib.names import ar_team
        # ≤ 62 chars with the brand for the short names (seo_title drops the
        # brand, never the query words, when a long name pushes it over)
        # 2026-11-12 (GSC export): the biggest non-brand query of the club
        # pages is the bare name - «طرابزون سبور» 209 impressions at position
        # 11, against 17 for «نتيجة طرابزون سبور اليوم». The title now STARTS
        # with the name and keeps «نتيجة اليوم» and «المباريات القادمة».
        title = f"{name}: نتيجة اليوم والمباريات القادمة والأخبار | {SITE_NAME}"
        _parts = []
        if last_res:
            _l = last_res[0]
            # the score with SPACES: a glued «1-0» is one LTR run and reverses in RTL
            _parts.append(f"آخر نتيجة: {ar_team(_l.get('home'))} {_l.get('home_score')} - "
                          f"{_l.get('away_score')} {ar_team(_l.get('away'))} ({day_month(_l.get('kickoff'))}).")
        if up_next:
            _n = up_next[0]
            _parts.append(f"القادمة: {ar_team(_n.get('home'))} × {ar_team(_n.get('away'))} "
                          f"{day_month(_n.get('kickoff'), weekday=True)}"
                          + (f" {_n.get('koff_time')} بتوقيت القاهرة." if _n.get("koff_time") else "."))
        # «وترتيبه» only where the page shows a table (the national team's
        # qualifier group is not in our standings data)
        _parts.append(f"أخبار {name} وترتيبه في {league_ar}." if (st and st.get("table"))
                      else f"آخر أخبار {name} ومواعيد مبارياته في {league_ar}.")
        desc = " ".join(_parts)
        img = (crest if crest.startswith("http")
               else SITE_BASE + crest) if crest else None
        # the link preview: the club's identity card (1600x680, our own art)
        # when media/ holds one - the 136px crest fell back to the site banner
        # on every club page (designer review 2026-11-13). `img` stays the
        # crest for the SportsTeam logo below.
        _card = f"{slug}-identity-card.jpg"
        og_img = (f"{SITE_BASE}/media/{_card}"
                  if os.path.exists(os.path.join(HERE, "media", _card)) else img)
        page_head = head(title, desc, SITE_BASE + t_url, image=og_img)
        crumbs_ld = breadcrumb_ld([("الرئيسية", SITE_BASE + "/"),
                                   (name, SITE_BASE + t_url)])
        _img = (f'<img class="club-crest" src="{esc(crest)}" alt="{esc(name)}" '
                'width="64" height="64" loading="eager">' if crest else "")
        _pos = ""
        if srow:
            # number agreement: «8 نقاط من 10 مباريات», «25 نقطة من 11 مباراة»
            _p, _g = int(srow.get("pts") or 0), int(srow.get("played") or 0)
            _pos = (f'<p class="club-pos">المركز <b>{srow.get("pos")}</b> في '
                    f'{esc(league_ar)} برصيد <b>{_p}</b> {"نقاط" if 3 <= _p <= 10 else "نقطة"} '
                    f'من {_g} {"مباريات" if 3 <= _g <= 10 else "مباراة"}</p>')
        up_rows = []
        for m in up_next:
            up_rows.append(match_row(m, show_time=True, show_comp=True, show_date=True,
                                     link=match_url(m) if m.get("match_id") in m_all else None))
        last_rows = []
        for m in last_res:
            last_rows.append(match_row(m, show_time=False, show_comp=True, show_date=True,
                                       link=match_url(m)))
        news_items = []
        for a in news:
            _t = art_reltime(a)
            _nimg = thumb_url(a.get("image_url"))
            news_items.append({"href": Markup(article_href(a)), "title": a["title"],
                               # the /news row (site-check 2026-11-12): picture + title
                               "th": Markup(f'<span class="al-th"><img src="{esc(_nimg)}" alt="" loading="lazy" decoding="async"></span>'
                                            if _nimg else '<span class="al-th noimg">⚽</span>'),
                               "when": Markup(_t) if _t else ""})
        table = table_heading = ""
        if st and st.get("table"):
            _slug = COMP_SLUG.get(tp["league"])
            table_heading = (f'<a href="/standings/{_slug}.html">ترتيب {esc(league_ar)} ←</a>'
                             if _slug else f'ترتيب {esc(league_ar)}')
            table = standings_table(tp["league"], st["table"],
                                    past=st.get("past"),
                                    season_label=st.get("season_label"),
                                    zeroed=st.get("zeroed"),
                                    form_map=forms.get(tp["league"], {}),
                                    embedded=True)
        # the club's own GROUP in a group competition (SEO review 2026-11-20:
        # /team/pyramids and /team/al-hilal-sudan never said «المجموعة» while
        # the two share a Champions League group). Its table, linking the
        # page that holds every group.
        group_tables = []
        _my_groups = []                  # (competition, group, the club's row) - the FAQ below says it in words
        from site_lib.competitions import GROUP_PAGES
        from site_lib.names import ar_team as _ar
        for _gc in COMP_SLUG:
            if _gc not in GROUP_PAGES:
                continue
            for _g in (groups_by_comp or {}).get(_gc) or []:
                _in = [r for r in _g.get("table") or []
                       if _team_match(tp, {"home": r.get("team") or "", "away": "", "competition": _gc})]
                if len(_in) != 1:
                    continue
                _gt = standings_table(_gc, _g["table"], embedded=True, title=_g["name"])
                _b = f'<bdi>{esc(_ar(_in[0].get("team")))}</bdi>'
                _gt = _gt.replace(_b, f'<bdi class="lt-me">{esc(_ar(_in[0].get("team")))}</bdi>', 1)
                _my_groups.append((_gc, _g, _in[0]))
                group_tables.append({
                    "heading": Markup(f'<a href="/standings/{COMP_SLUG[_gc]}.html">ترتيب {esc(_g["name"])} في '
                                      f'{esc(comp_label(_gc))} ←</a>'),
                    "table": Markup(_gt)})
                break
        # computed FAQ (2026-11-12): the club queries GSC shows are questions
        # the page already answers in rows - «نتيجة طرابزون سبور اليوم»،
        # «آخر مباراة لطرابزون»، «مباريات طرابزون سبور القادمة». Said once in
        # words, from the same data, with its FAQPage schema. Never generated.
        faq = []
        if last_res:
            _l = last_res[0]
            faq.append((f"ما نتيجة آخر مباراة لعبها {name}؟",
                        f"{ar_team(_l.get('home'))} {_l.get('home_score')} - {_l.get('away_score')} "
                        f"{ar_team(_l.get('away'))} في {comp_label(_l.get('competition'))} "
                        f"يوم {day_month(_l.get('kickoff'), weekday=True)}."))
        if up_next:
            _n = up_next[0]
            faq.append((f"متى مباراة {name} القادمة؟",
                        f"{ar_team(_n.get('home'))} ضد {ar_team(_n.get('away'))} "
                        f"يوم {day_month(_n.get('kickoff'), weekday=True)}"
                        + (f" الساعة {_n.get('koff_time')} بتوقيت القاهرة" if _n.get("koff_time") else "")
                        + f" في {comp_label(_n.get('competition'))}."))
        if srow and not (st or {}).get("zeroed"):
            from site_lib.stats import _cnt
            _pts = int(srow.get("pts") or 0)
            faq.append((f"ما ترتيب {name} في {league_ar}؟",
                        f"{name} في المركز {srow.get('pos')} برصيد "
                        + (f"{_pts} نقطة" if _pts in (0, 1, 2) else _cnt(_pts, "نقطة واحدة", "نقطتين", "نقاط", "نقطة"))
                        + " من " + _cnt(srow.get("played"), "مباراة واحدة", "مباراتين", "مباريات", "مباراة") + "."))
        # the club's top scorer in its league, when the saved chart names one
        _chart = (sc_by_comp or {}).get(tp["league"]) if (sc_ok or {}).get(tp["league"]) else None
        _top = next((r for r in _chart or []
                     if any(t in (r.get("team") or "") for t, _ in tp["match_tokens"])
                     and int(r.get("goals") or 0) > 0), None)
        if _top:
            from site_lib.stats import _cnt as _cn
            faq.append((f"من هداف {name} في {league_ar} هذا الموسم؟",
                        f"{_top['name']} برصيد "
                        + _cn(_top["goals"], "هدف واحد", "هدفين", "أهداف", "هدفًا")
                        + f" في {league_ar}."))
        # «أرقام لاعبي الفريق» (SEO review 2026-11-19) - site_lib/squad_stats.py
        # the group, said in words (SEO review 2026-11-26: the Sudan pages
        # answered two questions where Al Ahly's answers six; «مجموعة الهلال
        # السوداني في دوري أبطال أفريقيا» is asked as a question). From the
        # same table the page shows - who is in it, nothing judged.
        for _gc, _g, _row in _my_groups:
            _others = [_ar(r.get("team")) for r in _g.get("table") or [] if r is not _row and r.get("team")]
            if not _others:
                continue
            _with = "، ".join(_others[:-1]) + (" و" + _others[-1] if len(_others) > 1 else _others[0])
            faq.append((f"في أي مجموعة {name} في {comp_label(_gc)}؟",
                        f"{name} في {_g['name']} من {comp_label(_gc)}، مع {_with}."))
        from site_lib.squad_stats import squad_stats
        _sq = squad_stats(tp, cm, md_idx)
        squad = None
        if _sq:
            from site_lib.stats import _cnt as _cq
            squad = {"n_txt": _cq(_sq["n"], "مباراة واحدة", "مباراتين", "مباريات", "مباراة"),
                     "rows": _sq["rows"], "rated": any(r["rating"] for r in _sq["rows"])}
            _t0 = _sq["rows"][0]
            faq.append((f"من أكثر لاعبي {name} مشاركة هذا الموسم؟",
                        f"{_t0['name']}: شارك في " + _cq(_t0["apps"], "مباراة واحدة", "مباراتين", "مباريات", "مباراة")
                        + " من " + _cq(_sq["n"], "مباراة واحدة", "مباراتين", "مباريات", "مباراة")
                        + f" لدينا تشكيلها لـ{name} هذا الموسم."))
        # the league's hub pages, only the ones the build writes
        _ls = COMP_SLUG.get(tp["league"])
        hub_links = []
        if _ls and ((fx_by_comp or {}).get(tp["league"]) or {}).get("rounds"):
            hub_links.append({"href": Markup(f"/fixtures/{_ls}.html"), "label": f"جدول مباريات {league_ar}"})
        if _ls and st and st.get("table"):
            hub_links.append({"href": Markup(f"/scorers/{_ls}.html"), "label": f"هدافو {league_ar}"})
        from site_lib.league_numbers import READY as _NB_READY
        if _ls and tp["league"] in _NB_READY:
            hub_links.append({"href": Markup(f"/numbers/{_ls}.html"), "label": f"إحصائيات {league_ar}"})
        # the table calculator (site review 2026-11-19: one text link led to it)
        from site_lib.calc import calc_data as _calc_data, calc_focus as _calc_focus
        _cd = _calc_data(st, (fx_by_comp or {}).get(tp["league"])) if _ls else None
        # «ماذا لو فاز فريقك؟» (2026-11-25): the door opens on THIS club's
        # nearest league match, as a question about it
        whatif = None
        if _cd:
            hub_links.append({"href": Markup(f"/calc/{_ls}.html"), "label": f"حاسبة ترتيب {league_ar}"})
            _fo = _calc_focus(_cd, st["table"].index(srow)) if srow else None
            if _fo:
                whatif = {"href": f"/calc/{_ls}.html#m={_fo[0]}.{_fo[1]}",
                          "label": f"ماذا لو فاز {name} على {_fo[2]}؟"}
        faq_html = ""
        if faq:
            faq_html = ('<section class="minfo faq"><h2>أسئلة شائعة عن ' + esc(name) + '</h2>'
                        + "".join(f'<details><summary>{esc(q)}</summary><p>{esc(a)}</p></details>'
                                  for q, a in faq) + '</section>'
                        + jsonld({"@context": "https://schema.org", "@type": "FAQPage",
                                  "mainEntity": [{"@type": "Question", "name": q,
                                                  "acceptedAnswer": {"@type": "Answer", "text": a}}
                                                 for q, a in faq]}))
        # the pair's head-to-head page (/h2h/<slug>, 2026-11-13), from both clubs
        from site_lib.h2h import link_label, pairs_for_club
        h2h_link = [{"href": Markup(f"/h2h/{_p['slug']}.html"), "label": link_label(_p)}
                    for _p in pairs_for_club(slug)]
        # a league page (2026-11-20) is listed beside its own league only:
        # thirty-five more chips on every club page would bury the rest
        others = [o for o in TEAM_PAGES if o["slug"] != slug
                  and (not o.get("league_page") or o["league"] == tp["league"])]
        club_ld = jsonld({
            "@context": "https://schema.org", "@type": "SportsTeam",
            "name": name, "sport": "Football", "url": SITE_BASE + t_url,
            **({"logo": img} if img else {}),
            "memberOf": {"@type": "SportsOrganization", "name": league_ar},
        })
        # the popup is added only when a row carries a prediction button
        popup = pred_pop([page_head, crumbs_ld, _img, _pos] + up_rows + last_rows
                         + [table_heading, table, club_ld])
        write(f"team/{slug}.html", render(
            "club.html", page_head=Markup(page_head), crumbs_ld=Markup(crumbs_ld),
            name=name, slug=Markup(slug), push_on=bool(VAPID_PUBLIC_KEY), squad=squad, crest_img=Markup(_img), position=Markup(_pos),
            up_rows=[Markup(x) for x in up_rows], last_rows=[Markup(x) for x in last_rows],
            news=news_items, has_table=bool(st and st.get("table")),
            table_heading=Markup(table_heading), table=Markup(table),
            group_tables=group_tables, season=season,
            up_more_txt=more_matches_txt(len(up_more)), last_more_txt=more_matches_txt(len(last_more)),
            up_more=[Markup(x) for x in up_more], last_more=[Markup(x) for x in last_more],
            others=[{"slug": Markup(o["slug"]), "name": o["name"]} for o in others],
            club_ld=Markup(club_ld), faq=Markup(faq_html), popup=Markup(popup),
            h2h=h2h_link, hub_links=hub_links,
            whatif=({"href": Markup(whatif["href"]), "label": whatif["label"]} if whatif else None),
            page_foot=Markup(foot())))
        urls.append(t_url)
        # «تابع فريقك» (2026-11-19): the home page's block for a visitor who
        # follows this club - ONE row (its next match, else its last result),
        # where it stands in a few words, one news line.
        # A fragment, not a page: out of the sitemap, noindex in _headers.
        _chip = ""
        if srow:
            _cp = int(srow.get("pts") or 0)
            _chip = f'المركز {srow.get("pos")} · {_cp} {"نقاط" if 3 <= _cp <= 10 else "نقطة"}'
        write_text(f"my/{slug}.json", my_json(_clean_urls(my_block_html(
            name, slug, crest, _chip, up_rows[0] if up_rows else (last_rows[0] if last_rows else ""),
            [{"href": str(n["href"]), "title": n["title"]} for n in news_items],
            calc=whatif or next(({"href": str(h["href"]), "label": h["label"]} for h in hub_links
                                 if str(h["href"]).startswith("/calc/")), None))),
            ko=(f'{up_next[0].get("kickoff") or ""} {up_next[0].get("koff_time") or ""}'.strip() if up_next else "")))
    print(f"  + club pages: {len(TEAM_PAGES)}")
