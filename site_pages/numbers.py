# -*- coding: utf-8 -*-
"""/numbers/<slug> - «أرقام الدوري» (SEO review 2026-11-19). What counts and
what is refused lives in site_lib/league_numbers.py; this writes the pages."""
import os

from site_lib.competitions import COMP_SLUG, comp_season
from site_lib.config import DIST, REF_TODAY, SITE_BASE, SITE_NAME
from site_lib.league_numbers import league_numbers
from site_lib.names import comp_label
from site_lib.render import Markup, render
from site_lib.shell import _LASTMOD, foot, head, write
from site_lib.stats import _cnt
from site_lib.text import esc, jsonld
from site_lib.urls import breadcrumb_ld


def numbers_pages(bycomp, md_idx, season, fx_by_comp, st_by_comp, urls):
    os.makedirs(os.path.join(DIST, "numbers"), exist_ok=True)
    n_pages = 0
    for comp, slug in COMP_SLUG.items():
        nb = league_numbers((bycomp or {}).get(comp), md_idx)
        if not nb:
            continue
        label = comp_label(comp)
        _season = comp_season(comp, season, ((fx_by_comp or {}).get(comp) or {}).get("rounds"))
        url = f"/numbers/{slug}.html"
        m_txt = lambda n: _cnt(n, "مباراة واحدة", "مباراتين", "مباريات", "مباراة")
        y_txt = _cnt(nb["yellow"], "إنذار واحد", "إنذاران", "إنذارات", "إنذارًا")
        r_txt = _cnt(nb["red"], "بطاقة حمراء واحدة", "بطاقتان حمراوان", "بطاقات حمراء", "بطاقة حمراء")
        g_txt = _cnt(nb["goals"], "هدف واحد", "هدفان", "أهداف", "هدفًا")
        top = nb["booked"][0] if nb["booked"] else None
        title = f"إحصائيات {label} {_season}: الإنذارات والطرد وأهداف آخر ربع ساعة | {SITE_NAME}"
        desc = (f"إحصائيات {label} {_season} من {m_txt(nb['n'])}: {y_txt} و{r_txt}."
                + (f" الأكثر إنذارات: {top[0]} ({top[1]}) بـ{top[2]}." if top else "")
                + f" وأهداف آخر ربع ساعة: {nb['late']} من {nb['goals']}.")
        late_txt = (f"سُجّل {_cnt(nb['late'], 'هدف واحد', 'هدفان', 'أهداف', 'هدفًا')} بعد الدقيقة 75 "
                    f"من أصل {g_txt} في المباريات المحسوبة.")
        faq = []
        if top:
            tied = [b for b in nb["booked"] if b[2] == top[2]]
            if len(tied) == 1:
                ans = f"{top[0]} لاعب {top[1]}: " + _cnt(top[2], "إنذار واحد", "إنذاران", "إنذارات", "إنذارًا") + "."
            else:
                ans = (" و".join(f"{b[0]} ({b[1]})" for b in tied[:4])
                       + (" وآخرون" if len(tied) > 4 else "") + ": "
                       + _cnt(top[2], "إنذار واحد", "إنذاران", "إنذارات", "إنذارًا") + " لكل لاعب.")
            faq.append((f"من أكثر لاعب حصل على إنذارات في {label}؟", ans + f" من {m_txt(nb['n'])} محسوبة."))
        faq.append((f"كم بطاقة حمراء في {label} هذا الموسم؟",
                    (r_txt if nb["red"] else "لا بطاقات حمراء") + f" في {m_txt(nb['n'])} محسوبة."))
        if nb["late_teams"]:
            lt = nb["late_teams"][0]
            faq.append((f"أي فريق يسجل أكثر في آخر ربع ساعة في {label}؟",
                        f"{lt[0]}: " + _cnt(lt[1], "هدف واحد", "هدفان", "أهداف", "هدفًا") + " بعد الدقيقة 75."))
        faq_html = ('<section class="minfo faq"><h2>أسئلة شائعة عن إحصائيات ' + esc(label) + '</h2>'
                    + "".join(f'<details><summary>{esc(q)}</summary><p>{esc(a)}</p></details>' for q, a in faq)
                    + '</section>'
                    + jsonld({"@context": "https://schema.org", "@type": "FAQPage",
                              "mainEntity": [{"@type": "Question", "name": q,
                                              "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]}))
        links = []
        if ((st_by_comp or {}).get(comp) or {}).get("table"):
            links.append(f'<a href="/standings/{slug}.html">ترتيب {esc(label)} ←</a>')
        if os.path.exists(os.path.join(DIST, "scorers", f"{slug}.html")):
            links.append(f'<a href="/scorers/{slug}.html">هدافو {esc(label)} ←</a>')
        if ((fx_by_comp or {}).get(comp) or {}).get("rounds"):
            links.append(f'<a href="/fixtures/{slug}.html">جدول مباريات {esc(label)} ←</a>')
        write(f"numbers/{slug}.html", render(
            "numbers.html", page_head=Markup(head(title, desc, SITE_BASE + url, active="leagues")),
            crumbs_ld=Markup(breadcrumb_ld([("الرئيسية", SITE_BASE + "/"), ("البطولات", SITE_BASE + "/leagues.html"),
                                            (f"أرقام {label}", SITE_BASE + url)])),
            label=label, season=_season, n_txt=m_txt(nb["n"]), of_txt=m_txt(nb["of"]),
            goals_txt=g_txt, yellow_txt=y_txt, red_txt=r_txt, late_txt=late_txt,
            booked=[{"player": p, "team": t, "n": n} for p, t, n in nb["booked"]],
            sent_off=[{"player": p, "team": t, "minute": mn, "opp": o} for p, t, mn, o in nb["sent_off"]],
            teams=[{"team": t, "yellow": y, "red": r} for t, y, r in nb["teams"]],
            late_teams=[{"team": t, "n": n} for t, n in nb["late_teams"]],
            faq=Markup(faq_html), links=[Markup(x) for x in links], page_foot=Markup(foot())))
        urls.append(url)
        _LASTMOD[url] = REF_TODAY
        n_pages += 1
    print(f"  + league numbers pages: {n_pages}")
    return n_pages
