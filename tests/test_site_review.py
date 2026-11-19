# -*- coding: utf-8 -*-
r"""The site review of 2026-11-19 (the site-check agent's list, done the same
evening): what a reader meets right after a story, the doors to the table
calculator, a shareable prediction, and a match page that says something
about its two sides before kick-off.

    python tests/test_site_review.py      (from the repo root)
"""
import io
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())

fails = 0


def ck(msg, cond, extra=""):
    global fails
    print(("  ok   " if cond else "  FAIL ") + msg + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails += 1


def rd(p):
    return io.open(p, encoding="utf-8").read()


art, fjs, cjs = rd("site_src/templates/article.html"), rd("site_src/snippets/follow_js.html"), rd("site_src/snippets/calc_js.html")
apy, css = rd("site_pages/articles.py"), rd("site_src/style.css")

# ------------------------------------------------------------- the article
ck("1 the follow button and the share link come right after the story, before anything else",
   art.index('class="a-body"') < art.index('class="a-act"') < art.index('class="a-rel"') < art.index("{{ today_strip }}"))
ck("2 the follow button is the club the TITLE names, hidden until the script can use storage",
   '{% if lead %}' in art and 'data-slug="{{ lead.slug }}"' in art
   and art.split('class="follow-btn"')[1].split(">")[0].rstrip().endswith("hidden")
   and "lead=({" in apy and "_lead_tp" in apy.split("lead=({")[1][:120])
ck("3 the script serves every follow button on a page, and checks the slug it is handed",
   "querySelectorAll('.follow-btn')" in fjs and "if(!ok(slug||'')) return;" in fjs)
ck("4 the share link works with NO script (a plain WhatsApp link); the phone's own sheet where there is one",
   'class="share-btn" href="{{ share_href }}"' in art and '"https://wa.me/?text=" + _q(' in apy
   and "if(!navigator.share) return;" in fjs and "navigator.share({" in fjs)
ck("5 no third-party script comes with it", "<script" not in art and "sharethis" not in art.lower() and "addthis" not in art.lower())
ck("6 «اقرأ أيضًا»: three stories with their pictures, inside the article - the bare list under it is gone",
   "related_articles(a, articles)[:3]" in apy and '"th": Markup(' in apy.split("related_articles(a, articles)[:3]")[1][:600]
   and 'class="al-row"' in art and "مقالات ذات صلة" not in art and "mp-newslist" not in art)
ck("7 the Telegram line shows only while the channel posts",
   "{% if tg_on %}" in art and 'CHANNEL_PAUSED' in apy and "tg_on=_TG_ON" in apy)
import tg_post                                           # noqa: E402
ck("7b ...and today it is paused, so the promise «لحظة بلحظة» is not printed",
   tg_post.CHANNEL_PAUSED is True)

# ------------------------------------------------------------- the calculator's doors
lpy, cpy, stt = rd("site_pages/leagues.py"), rd("site_pages/clubs.py"), rd("site_src/templates/standings.html")
ck("8 a button above the table on the standings page, only where the calculator exists",
   "{% if calc_href %}" in stt and stt.index("calc-cta") < stt.index('{% include "_st_tabs.html" %}')
   and 'calc_href=Markup(f"/calc/{slug}.html") if _has_calc else ""' in lpy)
ck("9 the club page and the fixtures page link it by the same test the page builder uses",
   "_calc_data(st, (fx_by_comp or {}).get(tp[\"league\"]))" in cpy and "_calc_data_fx(st_by_comp.get(comp), fx)" in lpy)

# ------------------------------------------------------------- a shareable prediction
ck("10 the picks ride in the link's FRAGMENT, and only known matches with h/d/a are read back",
   "'#p='" in cjs and r"/^([A-Za-z0-9-]{1,24})\.([hda])$/" in cjs and "if(m&&live[m[1]])" in cjs)
ck("11 the share link appears with the first pick and carries the reader's own table",
   'id="calcShare" class="share-btn"' in rd("site_src/templates/calc.html") and "elShare.hidden=!n;" in cjs
   and "setAttribute('data-share-url',u)" in cjs)
ck("12 the day and hour once above the matches that share them, not under every match",
   "el('div','calc-d',m[3])" in cjs and "el('span','calc-w',m[3])" not in cjs)
ck("13 the count agrees in number", "n===1?'مباراة واحدة':n===2?'مباراتان':n<=10?n+' مباريات':n+' مباراة'" in cjs)

# ------------------------------------------------------------- the match page
mpy, mt = rd("site_pages/matches.py"), rd("site_src/templates/match.html")
ck("14 the two sides' own stories first; the general list only when there is none",
   "any(_team_news(tp, a) for tp in _tps)" in mpy and 'news_title = "أخبار " + " و".join(' in mpy
   and "if articles and not news:" in mpy and "{{ news_title }}" in mt)
ck("15 «الفريقان قبل المباراة»: from the table's own rows, never on a finished match, never with a side missing",
   'if st != "FINISHED" and all(r for r, _ in _two):' in mpy and "form_dots(_fm.get(nm, []))" in mpy
   and "{{ form_card }}" in mt and mt.index("{{ motm }}") < mt.index("{{ form_card }}") < mt.index("{{ article_block }}"))
from site_lib.stats import form_dots                     # noqa: E402
_d = form_dots(["L", "D", "W"])
ck("16 its caption says the truth about the dots' order (the list runs oldest to newest; RTL puts the newest on the left)",
   _d.index("fm-l") < _d.index("fm-w") and "الأحدث على اليسار" in mpy and "الأحدث أولًا" not in mpy)
ck("17 the two sides are marked in the table under the match",
   '<bdi class="lt-me">' in mpy and "tr:has(.lt-me) td{" in css)
ck("18 the home filter's hint fits a phone", 'placeholder="فريق أو بطولة"' in rd("site_lib/snippets.py"))

# ------------------------------------------------------------- the built pages
dist = os.path.join(os.getcwd(), "dist")
if os.path.isdir(os.path.join(dist, "a")):
    pages = [f for f in os.listdir(os.path.join(dist, "a")) if f.endswith(".html")]
    with_btn = 0
    bad = []
    for f in pages[-200:]:
        h = rd(os.path.join(dist, "a", f))
        if 'class="a-act"' not in h:
            continue                                      # a moved stub / a legacy page
        if 'class="follow-btn"' in h:
            with_btn += 1
        if h.count('class="share-btn"') != 1 or "a-tg" in h or h.count('<h1') != 1:
            bad.append(f)
    ck("19 built articles: one share link each, no Telegram promise, one H1; some carry a follow button",
       not bad and with_btn > 0, f"{bad[:5]} with_btn={with_btn}")
    ms = [f for f in os.listdir(os.path.join(dist, "m")) if f.endswith(".html")]
    fc = [f for f in ms if 'class="minfo form-card"' in rd(os.path.join(dist, "m", f))]
    wrong = [f for f in fc if "انتهت" in re.sub(r"<[^>]+>", " ", rd(os.path.join(dist, "m", f)).split('class="mlist mp-hero"')[1][:1500])]
    ck(f"20 built match pages: the two-sides card on upcoming matches ({len(fc)}), on no finished one", fc and not wrong, str(wrong[:5]))
    st = [f for f in os.listdir(os.path.join(dist, "calc"))]
    miss = [f for f in st if "calc-cta" not in rd(os.path.join(dist, "standings", f))]
    ck(f"21 every league with a calculator ({len(st)}) shows its button on the standings page", st and not miss, str(miss))

print("ALL OK" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
