# -*- coding: utf-8 -*-
"""/tv - «القنوات الناقلة لمباريات اليوم» (user 2026-11-27).

One function, called once by build(); what a row holds and which channel is
printed live in site_lib/tvguide.py. Today's matches and tomorrow's, each
with its kick-off (Cairo and Mecca) and its channel. Never a guessed channel:
a match with none says «لم تُعلن بعد»."""
import datetime

from site_lib import tvguide as TV
from site_lib.config import SITE_BASE, SITE_NAME
from site_lib.dates import day_month
from site_lib.render import Markup, render
from site_lib.shell import _LASTMOD, foot, head, noindex, write
from site_lib.stats import _cnt
from site_lib.text import esc, jsonld
from site_lib.urls import breadcrumb_ld


def tv_page(m_all, urls, today=None):
    """Write /tv.html; returns how many of today's matches carry a named
    channel. In the sitemap only on a day with TV.INDEX_MIN named channels."""
    today = today or TV.cairo_today()
    days = []
    for off, word in ((0, "اليوم"), (1, "غدًا")):
        d = (today + datetime.timedelta(days=off)).isoformat()
        rows = TV.day_rows((m_all or {}).values(), d)
        days.append({"word": word, "date_txt": day_month(d, weekday=True), "rows": rows,
                     "groups": [{"label": lb, "rows": rs} for lb, rs in TV.by_competition(rows)]})
    t_rows = days[0]["rows"]
    n_named = len(TV.named(t_rows))
    date_txt = days[0]["date_txt"]
    _t = next((t for t in (f"القنوات الناقلة لمباريات اليوم {date_txt}: الموعد والقناة لكل مباراة",
                           f"القنوات الناقلة لمباريات اليوم {date_txt}: الموعد والقناة",
                           f"القنوات الناقلة لمباريات اليوم {date_txt}") if len(t) <= 62),
              "القنوات الناقلة لمباريات اليوم")
    m_txt = _cnt(len(t_rows), "مباراة واحدة", "مباراتان", "مباريات", "مباراة")
    if t_rows:
        first = next((r for r in t_rows if r["channel"] and r["cairo"]), None)
        desc = (f"القنوات الناقلة لمباريات اليوم {date_txt}: {m_txt} بمواعيدها بتوقيت القاهرة ومكة المكرمة"
                + (f"، منها {first['home']} و{first['away']} الساعة {first['cairo']} على {first['channel']}." if first else "."))
        intro = (f"{m_txt} اليوم {date_txt}. "
                 + (f"القناة معلنة لـ{_cnt(n_named, 'مباراة واحدة', 'مباراتين', 'مباريات', 'مباراة')} منها."
                    if n_named else "لم تُعلن قناة أي مباراة منها بعد."))
    else:
        desc = f"القنوات الناقلة لمباريات اليوم {date_txt} ومباريات الغد بمواعيدها بتوقيت القاهرة ومكة المكرمة."
        intro = f"لا مباريات اليوم {date_txt} في البطولات التي يتابعها الموقع."
    faq = TV.faq(t_rows)
    faq_html = ""
    if faq:
        faq_html = ('<section class="minfo faq"><h2>أسئلة شائعة عن القنوات الناقلة اليوم</h2>'
                    + "".join(f'<details><summary>{esc(q)}</summary><p>{esc(a)}</p></details>' for q, a in faq)
                    + '</section>'
                    + jsonld({"@context": "https://schema.org", "@type": "FAQPage",
                              "mainEntity": [{"@type": "Question", "name": q,
                                              "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]}))
    url = "/tv.html"
    html = render("tv.html",
                  page_head=Markup(head(f"{_t} | {SITE_NAME}", desc, SITE_BASE + url, active="matches")),
                  crumbs_ld=Markup(breadcrumb_ld([("الرئيسية", SITE_BASE + "/"),
                                                  ("القنوات الناقلة", SITE_BASE + url)])),
                  date_txt=date_txt, intro=intro, days=days, not_yet=TV.NOT_YET,
                  faq=Markup(faq_html), page_foot=Markup(foot()))
    if n_named >= TV.INDEX_MIN:
        urls.append(url)
        _LASTMOD[url] = today.isoformat()
    else:
        html = noindex(html)          # a day without channels is not a guide
    write("tv.html", html)
    print(f"  + /tv: {len(t_rows)} match(es) today, {n_named} with a named channel"
          + ("" if n_named >= TV.INDEX_MIN else " (not indexed today)"))
    return n_named
