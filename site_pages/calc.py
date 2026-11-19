# -*- coding: utf-8 -*-
"""/calc/<slug> - «حاسبة الترتيب» (2026-11-19). The rule for which league
gets a page, and what the script receives, lives in site_lib/calc.py; this
only writes the pages."""
import json
import os

from site_lib.calc import calc_counts, calc_data
from site_lib.competitions import COMP_SLUG, comp_season
from site_lib.config import DIST, REF_TODAY, SITE_BASE, SITE_NAME
from site_lib.names import comp_label
from site_lib.render import Markup, render
from site_lib.shell import _LASTMOD, _src, foot, head, write
from site_lib.stats import _cnt
from site_lib.text import esc, jsonld
from site_lib.urls import breadcrumb_ld

CALC_JS = _src("snippets/calc_js.html")


def calc_pages(fx_by_comp, season, st_by_comp, urls):
    os.makedirs(os.path.join(DIST, "calc"), exist_ok=True)
    n = 0
    for comp, slug in COMP_SLUG.items():
        st, fx = (st_by_comp or {}).get(comp), (fx_by_comp or {}).get(comp)
        data = calc_data(st, fx)
        if not data:
            continue
        label = comp_label(comp)
        _season = comp_season(comp, season, (fx or {}).get("rounds"))
        n_rounds, n_matches = calc_counts(data)
        url = f"/calc/{slug}.html"
        first = data["rounds"][0]
        title = f"حاسبة ترتيب {label} {_season}: توقّع النتائج وشاهد الجدول | {SITE_NAME}"
        top = data["teams"][0]
        desc = (f"حاسبة ترتيب {label} {_season}: اختر نتائج المباريات القادمة وشاهد الترتيب يتغيّر فورًا. "
                f"المتصدر الآن {top['n']} برصيد {top['pts']} نقطة، والمتبقي "
                + _cnt(n_matches, "مباراة واحدة", "مباراتان", "مباريات", "مباراة") + ".")
        page_head = head(title, desc, SITE_BASE + url)
        crumbs_ld = breadcrumb_ld([("الرئيسية", SITE_BASE + "/"),
                                   ("البطولات", SITE_BASE + "/leagues.html"),
                                   (f"حاسبة ترتيب {label}", SITE_BASE + url)])
        # computed, never generated: three questions the page itself answers
        second = data["teams"][1]
        gap = top["pts"] - second["pts"]
        faq = [(f"كيف تعمل حاسبة ترتيب {label}؟",
                f"تختار فوز صاحب الأرض أو التعادل أو فوز الضيف لكل مباراة لم تُلعب، فتُضاف النقاط إلى ترتيب {label} "
                "الحالي ويُعاد ترتيب الجدول. الفوز يُحسب 1-0 والتعادل 1-1."),
               (f"من يتصدر {label} الآن؟",
                f"{top['n']} في الصدارة برصيد {top['pts']} نقطة من "
                + _cnt(top["p"], "مباراة واحدة", "مباراتين", "مباريات", "مباراة")
                + (f"، بفارق {_cnt(gap, 'نقطة واحدة', 'نقطتين', 'نقاط', 'نقطة')} عن {second['n']}." if gap > 0
                   else f"، ويتساوى معه {second['n']} في النقاط.")),
               (f"كم مباراة متبقية في {label}؟",
                "المتاح في الحاسبة الآن " + _cnt(n_matches, "مباراة واحدة", "مباراتان", "مباريات", "مباراة")
                + " في " + _cnt(n_rounds, "جولة واحدة", "جولتين", "جولات", "جولة") + f"، أقربها الجولة {first['r']}.")]
        faq_html = ('<section class="minfo faq"><h2>أسئلة شائعة عن حاسبة ترتيب ' + esc(label) + '</h2>'
                    + "".join(f'<details><summary>{esc(q)}</summary><p>{esc(a)}</p></details>' for q, a in faq)
                    + '</section>'
                    + jsonld({"@context": "https://schema.org", "@type": "FAQPage",
                              "mainEntity": [{"@type": "Question", "name": q,
                                              "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]}))
        links = [f'<a href="/standings/{slug}.html">ترتيب {esc(label)} ←</a>',
                 f'<a href="/fixtures/{slug}.html">جدول مباريات {esc(label)} ←</a>']
        if os.path.exists(os.path.join(DIST, "scorers", f"{slug}.html")):
            links.append(f'<a href="/scorers/{slug}.html">هدافو {esc(label)} ←</a>')
        write(f"calc/{slug}.html", render(
            "calc.html", page_head=Markup(page_head), label=label, season=_season, slug=Markup(slug),
            rounds_txt=_cnt(n_rounds, "جولة واحدة", "جولتان", "جولات", "جولة"),
            matches_txt=_cnt(n_matches, "مباراة واحدة", "مباراتان", "مباريات", "مباراة"),
            first_round=first["r"],
            first=[{"h": data["teams"][m[1]]["n"], "a": data["teams"][m[2]]["n"], "when": m[3]} for m in first["m"]],
            rows=[{"pos": i + 1, "name": t["n"], "p": t["p"], "pts": t["pts"],
                   "gd": ("+" if t["gf"] - t["ga"] > 0 else "") + str(t["gf"] - t["ga"])}
                  for i, t in enumerate(data["teams"])],
            faq=Markup(faq_html), links=[Markup(x) for x in links], crumbs_ld=Markup(crumbs_ld),
            # «</» cannot close the script element from inside a team's name
            data=Markup(json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")),
            calc_js=Markup(CALC_JS), page_foot=Markup(foot())))
        urls.append(url)
        _LASTMOD[url] = REF_TODAY
        n += 1
    print(f"  + table calculator pages: {n}")
    return n
