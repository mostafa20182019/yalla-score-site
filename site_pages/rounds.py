# -*- coding: utf-8 -*-
"""/fixtures/<slug>/round-N - a league round as its own page (2026-11-27).

One function, called once by build(); what a round's page says lives in
site_lib/rounds.py. The rows are the site's own match rows, freshened from
the day's pool, each linked to its match page."""
import os

from site_lib import rounds as RD
from site_lib.competitions import COMP_SLUG, COMP_TV
from site_lib.config import DIST, REF_TODAY, SITE_BASE, SITE_NAME
from site_lib.names import comp_label
from site_lib.render import Markup, render
from site_lib.shell import _LASTMOD, foot, head, noindex, write
from site_lib.tables import match_row, standings_table
from site_lib.text import esc, jsonld
from site_lib.urls import breadcrumb_ld, match_url


def round_pages(fx_by_comp, st_by_comp, forms, m_all, urls):
    """One page per numbered round of every league in RD.ROUND_COMPS. In the
    sitemap: the round on show, the one before and the one after. Returns how
    many pages were written."""
    n_pages = 0
    pool = m_all or {}
    for comp in RD.ROUND_COMPS:
        fx = (fx_by_comp or {}).get(comp)
        slug = COMP_SLUG.get(comp)
        rounds = RD.numbered(fx)
        if not slug or not rounds:
            continue
        os.makedirs(os.path.join(DIST, "fixtures", slug), exist_ok=True)
        label = comp_label(comp)
        win = RD.window(fx)
        nums = [n for n, _ in rounds]
        table = (st_by_comp.get(comp) or {}).get("table") if st_by_comp else None
        for n, raw in rounds:
            ms = sorted((pool.get(m.get("match_id"), m) for m in raw),
                        key=lambda m: (m.get("kickoff") or "", m.get("koff_time") or ""))
            latest = RD.is_latest(fx, n)
            st = RD.state(ms)
            ttl = RD.title(comp, n, ms, latest and bool(table))
            url = RD.round_url(comp, n)
            rows = [match_row(m, show_time=True, show_comp=False, show_date=True, card_link=False,
                              link=match_url(m) if m.get("match_id") in pool else None) for m in ms]
            qa = RD.faq(comp, n, ms)
            faq_html = ""
            if qa:
                faq_html = (f'<section class="minfo faq"><h2>أسئلة شائعة عن الجولة {n} من {esc(label)}</h2>'
                            + "".join(f'<details><summary>{esc(q)}</summary><p>{esc(a)}</p></details>' for q, a in qa)
                            + '</section>'
                            + jsonld({"@context": "https://schema.org", "@type": "FAQPage",
                                      "mainEntity": [{"@type": "Question", "name": q,
                                                      "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in qa]}))
            # the table is «after this round» only while no later round has begun
            table_html, table_h = "", ""
            if table and latest and st != "coming":
                table_h = f"ترتيب {label} بعد الجولة {n}" if st == "done" else f"ترتيب {label} الآن"
                table_html = standings_table(comp, table, form_map=(forms or {}).get(comp, {}), embedded=True)
            links = []
            if n - 1 in nums:
                links.append(f'<a href="{RD.round_url(comp, n - 1)}">→ الجولة {n - 1}</a>')
            if n + 1 in nums:
                links.append(f'<a href="{RD.round_url(comp, n + 1)}">الجولة {n + 1} ←</a>')
            links.append(f'<a href="/fixtures/{slug}.html">جدول مباريات {esc(label)} كاملًا ←</a>')
            if table:
                links.append(f'<a href="/standings/{slug}.html">ترتيب {esc(label)} ←</a>')
            if st != "done":
                links.append('<a href="/tv.html">القنوات الناقلة لمباريات اليوم ←</a>')
            html = render(
                "round.html",
                page_head=Markup(head(f"{ttl} | {SITE_NAME}", RD.description(comp, n, ms), SITE_BASE + url, active="leagues")),
                crumbs_ld=Markup(breadcrumb_ld([("الرئيسية", SITE_BASE + "/"), ("البطولات", SITE_BASE + "/leagues.html"),
                                                (f"جدول {label}", SITE_BASE + f"/fixtures/{slug}.html"),
                                                (f"الجولة {n}", SITE_BASE + url)])),
                label=label, slug=slug, n=n, title=ttl, intro=RD.intro(comp, n, ms),
                rows_h=(f"مباريات الجولة {n} من {label}" if st == "coming" else f"نتائج ومباريات الجولة {n} من {label}"),
                rows=[Markup(r) for r in rows],
                tv=(COMP_TV.get(comp) or "") if st != "done" else "",
                table_h=table_h, table=Markup(table_html), faq=Markup(faq_html),
                links=[Markup(x) for x in links], page_foot=Markup(foot()))
            if not RD.indexable(fx, n, ms):
                html = noindex(html)        # a round weeks away: built and linked, not advertised
            write(f"fixtures/{slug}/round-{n}.html", html)
            if n in win:
                urls.append(url)
                _LASTMOD[url] = REF_TODAY
            n_pages += 1
        print(f"  + round pages, {label}: {len(rounds)} ({len(win)} in the sitemap: {win})")
    return n_pages
