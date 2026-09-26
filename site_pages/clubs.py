"""The curated clubs' pages (/team/<slug>) - slugs are indexed URLs, never
rename them.

Moved verbatim out of build_site.py (2026-09-26, tools/move_names.py):
source and comments exactly as they were there. Edit here; build_site
imports these back under the same names."""
import os
from site_lib.clubs import TEAM_PAGES
from site_lib.competitions import COMP_SLUG
from site_lib.config import DIST, REF_TODAY, SITE_BASE, SITE_NAME
from site_lib.crests import local_crest
from site_lib.dates import art_reltime
from site_lib.names import _team_match, _team_news, comp_label
from site_lib.predictions import pred_pop
from site_lib.render import Markup, render
from site_lib.shell import foot, head, write
from site_lib.tables import match_row, standings_table
from site_lib.text import esc, jsonld
from site_lib.urls import article_href, breadcrumb_ld, match_url


def club_pages(_plog, _preds, articles, forms, m_all, season, st_by_comp, urls):
    """/team/<slug> - evergreen SEO hubs for the highest-volume Arabic query
    family: «أخبار الأهلي اليوم»، «مباريات الزمالك القادمة»، «نتيجة ريال مدريد».
    One page per curated club: latest news + next matches + recent results +
    league standing, refreshed every publish cycle; cross-linked from article
    pages, match pages (club-chips) and the footer. Markup: club.html
    (templated 2026-09-26); the pieces are built here in the same order as
    before. Returns the loop's last _img / a / img / r under the same names."""
    os.makedirs(os.path.join(DIST, "team"), exist_ok=True)
    club_matches_src = sorted(m_all.values(),
                              key=lambda m: m.get("kickoff") or "")
    for tp in TEAM_PAGES:
        name, slug = tp["name"], tp["slug"]
        league_ar = comp_label(tp["league"])
        cm = [m for m in club_matches_src
              if _team_match(tp, m) and m.get("home") and m.get("kickoff")]
        up_next = [m for m in cm
                   if (m.get("status") or "").upper() in ("UPCOMING", "LIVE")
                   and m["kickoff"] >= REF_TODAY][:3]
        last_res = [m for m in reversed(cm)
                    if (m.get("status") or "").upper() == "FINISHED"
                    and m.get("home_score") is not None][:5]
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
        title = (f"أخبار {name} اليوم — مباريات ونتائج وترتيب {name} "
                 f"{season} | {SITE_NAME}")
        desc = (f"آخر أخبار {name} اليوم، موعد مباراة {name} القادمة، نتائج "
                f"آخر المباريات وترتيب {name} في {league_ar} {season} — "
                "تتحدّث الصفحة تلقائيًا على مدار اليوم.")
        img = (crest if crest.startswith("http")
               else SITE_BASE + crest) if crest else None
        page_head = head(title, desc, SITE_BASE + t_url, image=img)
        crumbs_ld = breadcrumb_ld([("أخبار", SITE_BASE + "/"),
                                   ("المباريات", SITE_BASE + "/matches.html"),
                                   (name, SITE_BASE + t_url)])
        _img = (f'<img class="club-crest" src="{esc(crest)}" alt="{esc(name)}" '
                'width="64" height="64" loading="eager">' if crest else "")
        _pos = ""
        if srow:
            _pos = (f'<p class="club-pos">المركز <b>{srow.get("pos")}</b> في '
                    f'{esc(league_ar)} برصيد <b>{srow.get("pts")}</b> نقطة '
                    f'من {srow.get("played")} مباراة</p>')
        up_rows = []
        for m in up_next:
            up_rows.append(match_row(m, show_time=True, show_comp=True,
                                     link=match_url(m),
                                     pred=_preds.get(str(m.get("match_id")))))
        last_rows = []
        for m in last_res:
            last_rows.append(match_row(m, show_time=False, show_comp=True,
                                       link=match_url(m),
                                       done=_plog.get(str(m.get("match_id")))))
        news_items = []
        for a in news:
            _t = art_reltime(a)
            news_items.append({"href": Markup(article_href(a)), "title": a["title"],
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
        others = [o for o in TEAM_PAGES if o["slug"] != slug]
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
            name=name, crest_img=Markup(_img), position=Markup(_pos),
            up_rows=[Markup(x) for x in up_rows], last_rows=[Markup(x) for x in last_rows],
            news=news_items, has_table=bool(st and st.get("table")),
            table_heading=Markup(table_heading), table=Markup(table),
            others=[{"slug": Markup(o["slug"]), "name": o["name"]} for o in others],
            club_ld=Markup(club_ld), popup=Markup(popup), page_foot=Markup(foot())))
        urls.append(t_url)
    print(f"  + club pages: {len(TEAM_PAGES)}")
