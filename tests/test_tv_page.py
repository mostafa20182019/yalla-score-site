# -*- coding: utf-8 -*-
"""/tv - «القنوات الناقلة لمباريات اليوم» (2026-11-27).

    python tests/test_tv_page.py     (from the repo root)

The rule the page stands on: a channel is the match's own (the feed) or the
competition's verified broadcaster - never a guess; a match with neither says
«لم تُعلن بعد».
"""
import io, os, sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())
from site_lib import tvguide as TV

fails = 0
def ck(msg, cond, extra=""):
    global fails
    print(("  ok   " if cond else "  FAIL ") + msg + (f"  [{extra}]" if extra and not cond else ""))
    fails += not cond

D = "2026-11-28"
def m(i, h, a, comp, t="18:00", st="UPCOMING", ch=None, day=D):
    return {"match_id": i, "kickoff": day, "koff_time": t, "home": h, "away": a, "competition": comp, "status": st, "channel": ch}

MS = [m(1, "الزمالك", "النادي الأفريقي", "CAF Champions League", ch="beIN SPORTS HD 4"),
      m(2, "Liverpool FC", "Everton FC", "Premier League", t="14:30", st="FINISHED"),
      m(3, "الأهلي", "النصر", "Saudi Pro League", t="21:00"),
      m(4, "أ", "ب", "Some Cup Nobody Shows", t=""),
      m(5, "ج", "د", "Premier League", st="POSTPONED"),
      m(6, "هـ", "و", "Premier League", day="2026-11-29")]
rows = TV.day_rows(MS, D)
by = {r["id"]: r for r in rows}
ck("1 the day's matches only, a postponed one left out, by the clock", [r["id"] for r in rows] == ["2", "1", "3", "4"], str([r["id"] for r in rows]))
ck("2 the feed's channel is printed as it came", by["1"]["channel"] == "beIN SPORTS HD 4")
ck("3 no channel from the feed: the competition's verified broadcaster", by["2"]["channel"] == "beIN Sports" and by["3"]["channel"])
ck("4 neither: empty - the page writes «لم تُعلن بعد», never a guess", by["4"]["channel"] == "" and TV.NOT_YET == "لم تُعلن بعد")
ck("5 Cairo and Mecca time (an hour apart in winter)", (by["1"]["cairo"], by["1"]["mecca"]) == ("18:00", "19:00"))
ck("6 a match without a time has no time, not midnight", (by["4"]["cairo"], by["4"]["mecca"]) == ("", ""))
ck("7 the Saudi «الأهلي» is written «الأهلي السعودي»", by["3"]["home"] == "الأهلي السعودي")
ck("8 a finished match says so", by["2"]["state"] == "انتهت" and by["1"]["state"] == "")
ck("9 the site's own order of competitions", [lb for lb, _ in TV.by_competition(rows)][:1] == ["الدوري الإنجليزي"] or
   [lb for lb, _ in TV.by_competition(rows)].index("الدوري الإنجليزي") < [lb for lb, _ in TV.by_competition(rows)].index("Some Cup Nobody Shows"))
fq = TV.faq(rows)
ck("10 the questions: matches still to play with a named channel, ours first", [q for q, _ in fq][0] == "ما القناة الناقلة لمباراة الزمالك والنادي الأفريقي اليوم؟"
   and len(fq) == 2 and all("ليفربول" not in q for q, _ in fq), str(fq))
ck("11 the answer says the hour in both cities and the channel", "18:00 بتوقيت القاهرة (19:00 بتوقيت مكة المكرمة) على beIN SPORTS HD 4." in fq[0][1])
ck("12 at most FAQ_MAX questions", len(TV.faq([dict(by["1"], id=str(i)) for i in range(9)])) == TV.FAQ_MAX)
src = io.open("site_pages/tv.py", encoding="utf-8").read()
ck("13 a day with fewer than INDEX_MIN named channels is built but not indexed and not in the sitemap",
   "if n_named >= TV.INDEX_MIN:" in src and "html = noindex(html)" in src and src.index("urls.append(url)") < src.index("html = noindex(html)"))
tpl = io.open("site_src/templates/tv.html", encoding="utf-8").read()
ck("14 the template prints the channel or «لم تُعلن بعد», each name in its own <bdi>, each match linked to its page",
   "{% if r.channel %}<bdi>{{ r.channel }}</bdi>{% else %}" in tpl and "{{ not_yet }}" in tpl and '<a href="/m/{{ r.id }}.html">' in tpl
   and "<bdi>{{ r.home }}</bdi>" in tpl)
b = io.open("build_site.py", encoding="utf-8").read()
ck("15 built once, after the match pages; one link in the footer", b.count("tv_page(m_all, urls)") == 1
   and b.index("m_all = match_pages(") < b.index("tv_page(m_all, urls)")
   and io.open("site_lib/shell.py", encoding="utf-8").read().count('<a href="/tv.html">القنوات الناقلة</a>') == 1)
print("ALL OK" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
