r"""Saudi Al-Ahli must never land on the Egyptian Al Ahly club page (2026-10-07).

    python tests/test_saudi_ahly.py      (from the repo root)

The trap: Saudi Al-Ahli's Arabic name is ALSO bare «الأهلي», and the club
matcher (names._team_news, behind article_clubs, the club pages and the D1
article_clubs rows) searches by substring. `article_put.py --check
--match-brief` on the preview of الفتح × الأهلي (match 4789470, Saudi Pro
League) printed clubs=['al-ahly']. The fix: a match piece obeys the club's
match scope (the ticker's rule), «الأهلي السعودي» and friends are cut out
before matching, and a Saudi-league context without an Egyptian anchor means
the bare name is the Saudi club. Egyptian Al Ahly - the site's main club - must
keep every story it had: these checks fail the day either side regresses.
Pure: no network, no data files (set_match_comps replaces the lazy load).
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())
from site_lib import names as N                                    # noqa: E402
from site_lib.articles import _ART_CLUBS, article_clubs            # noqa: E402

fails = []


def ck(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  [{extra}]" if extra else ""))
    if not cond:
        fails.append(name)


SPL, EPL, CAF = "Saudi Pro League", "Egyptian Premier League", "CAF Champions League"
N.set_match_comps({"4789470": SPL, "900": EPL, "901": CAF})
_n = [0]


def clubs(title, summary="", **kw):
    _n[0] += 1
    a = dict(article_id=f"t{_n[0]}", title=title, summary=summary, **kw)
    return [tp["slug"] for tp in article_clubs(a)]


# --- match pieces: the competition decides
ck("1 the reported preview: الفتح × الأهلي, Saudi Pro League -> no club",
   clubs("قبل المباراة: الفتح × الأهلي", "الفتح يستضيف الأهلي في الجولة السادسة",
         match_id="4789470", kind="preview") == [])
ck("2 a Saudi report found through the match registry -> no club",
   "al-ahly" not in clubs("تقرير: الأهلي يفوز على الفتح 2-1", match_id=4789470, kind="report"))
ck("3 a competition passed on the record wins (article_put's brief path)",
   "al-ahly" not in clubs("قبل المباراة: الأهلي × النصر", match_id="77", kind="preview",
                          competition=SPL))
ck("4 an Egyptian league piece still links Al Ahly",
   clubs("قبل المباراة: الأهلي يواجه الزمالك في القمة", match_id="900", kind="preview")
   == ["al-ahly", "zamalek"])
ck("5 a CAF Champions League piece still links Al Ahly (EGY_SCOPE, tested scope by scope)",
   "al-ahly" in clubs("تقرير: الأهلي يتأهل في أبطال أفريقيا", match_id="901", kind="report"))
ck("6 an unknown match falls back to the text (never drops a story silently)",
   "al-ahly" in clubs("قبل المباراة: الأهلي × إنبي", match_id="12345", kind="preview"))
ck("7 a European club is untouched by the scope rule",
   "liverpool" in clubs("تقرير: ليفربول يفوز", match_id="4789470", kind="report"))

# --- news: context, not a blanket veto
ck("8 «الأهلي السعودي» alone -> not the Egyptian club",
   "al-ahly" not in clubs("الأهلي السعودي يتعاقد مع مهاجم برازيلي"))
ck("9 an Egyptian story naming the Saudi club as a suitor keeps Al Ahly",
   "al-ahly" in clubs("الأهلي يرفض عرض الأهلي السعودي لضم إمام عاشور"))
ck("10 «دوري روشن» with no Egyptian anchor -> the bare name is the Saudi club",
   "al-ahly" not in clubs("الأهلي يفوز على الفتح ويتصدر دوري روشن"))
ck("11 a Saudi context WITH an Egyptian anchor keeps Al Ahly",
   "al-ahly" in clubs("الأهلي يغلق باب الرحيل", "اهتمام من الدوري السعودي بنجم الأهلي متصدر الدوري المصري"))
ck("12 a plain Egyptian story keeps Al Ahly",
   clubs("الأهلي يتعادل مع الزمالك في القمة") == ["al-ahly", "zamalek"])
ck("13 «شباب الأهلي» (Dubai) is cut out, not a veto",
   "al-ahly" not in clubs("شباب الأهلي يتوج بالدوري الإماراتي")
   and "al-ahly" in clubs("الأهلي يواجه شباب الأهلي وديًا"))

# --- the match-row link (same scope rule)
ck("14 _team_link: Al Ahly on a CAF Champions League row is linked",
   "/team/al-ahly" in N._team_link(CAF, "الأهلي"))
ck("15 _team_link: «الأهلي» on a Saudi Pro League row is NOT linked",
   "/team/" not in N._team_link(SPL, "الأهلي"))

# --- article_put: the brief's competition + no cache bleed between drafts
import article_put as AP                                           # noqa: E402
brief = {"kind": "preview", "match": {"match_id": "555", "competition_raw": SPL}}
saudi = {"title": "قبل المباراة: الفتح × الأهلي", "summary": "", "match_id": "555", "kind": "preview"}
ck("16 clubs_of takes the competition from a match brief",
   AP.clubs_of(saudi, brief=brief) == [])
ck("17 two drafts in one run never share the cached 'new' entry",
   AP.clubs_of({"title": "الزمالك يفوز"}) == ["zamalek"]
   and AP.clubs_of({"title": "بيراميدز يفوز"}) == ["pyramids"]
   and "new" not in _ART_CLUBS)

print(f"\n{'FAILED: ' + ', '.join(fails) if fails else 'all passed'}")
sys.exit(1 if fails else 0)
