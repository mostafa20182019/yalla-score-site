# -*- coding: utf-8 -*-
r"""The site review's second list (2026-11-19): «حسابات التأهل» under the group
tables, jump chips on a finished match page, the calculator's door in «فريقك».

    python tests/test_site_review2.py      (from the repo root)

The heart of it is site_lib/qualify.py: a sentence about who is through must
be TRUE whatever the tie-breakers are, so it is counted on points alone with
every tie read against the side - and a group our rows cannot rebuild gets no
sentence at all.
"""
import io
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())

import site_lib.qualify as Q        # noqa: E402

fails = 0


def ck(msg, cond, extra=""):
    global fails
    print(("  ok   " if cond else "  FAIL ") + msg + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails += 1


T = ["أ", "ب", "ج", "د"]


def g(i, h, a, hs=None, as_=None):
    return {"match_id": i, "home": h, "away": a, "home_score": hs, "away_score": as_,
            "status": "FINISHED" if hs is not None else "UPCOMING", "kickoff": f"2026-12-{i:02d}"}


def table(games):
    rows = {t: {"team": t, "played": 0, "pts": 0} for t in T}
    for m in games:
        if m["home_score"] is None:
            continue
        h, a = rows[m["home"]], rows[m["away"]]
        h["played"] += 1; a["played"] += 1
        if m["home_score"] > m["away_score"]:
            h["pts"] += 3
        elif m["home_score"] < m["away_score"]:
            a["pts"] += 3
        else:
            h["pts"] += 1; a["pts"] += 1
    return sorted(rows.values(), key=lambda r: -r["pts"])


# four rounds played: أ 12, ب 7, ج 4, د 0 ; two rounds left
GAMES = [g(1, "أ", "ب", 1, 0), g(2, "ج", "د", 2, 0), g(3, "أ", "ج", 2, 0), g(4, "ب", "د", 1, 0),
         g(5, "أ", "د", 3, 0), g(6, "ب", "ج", 1, 1), g(7, "ب", "أ", 0, 1), g(8, "د", "ج", 0, 0)]
GAMES[7] = g(8, "د", "ج", 0, 1)        # ج 7... keep it simple: ج beats د again
LEFT = [g(9, "ج", "أ"), g(10, "د", "ب"), g(11, "د", "أ"), g(12, "ج", "ب")]
tb = table(GAMES)
pts = {r["team"]: r["pts"] for r in tb}
out = {o["team"]: o for o in Q.group_outlook(tb, GAMES + LEFT, 2)}
ck("1 the table our rows rebuild: أ 12, ب 4, ج 7, د 0", pts == {"أ": 12, "ب": 4, "ج": 7, "د": 0}, str(pts))
ck("2 أ is through: nobody but one side can reach 12", out.get("أ", {}).get("state") == "in", str(out.get("أ")))
ck("3 د is out: two sides are already beyond the 6 it can reach", out.get("د", {}).get("state") == "out", str(out.get("د")))
# ج (7, two left): ب can reach 10. ج on 10 could be level with ب on 10 -> not sure; ج on 11+ ... reachable totals 7,8,9,10,11,13
ck("4 ج: the total that guarantees it is the lowest one above every tie (ب can reach 10 -> 11)",
   out.get("ج", {}).get("state") == "need" and out["ج"]["need"] == 11, str(out.get("ج")))
ck("5 ب (4, two left, max 10): 10 can be matched by ج, so nothing is guaranteed - and it is not out: NO sentence",
   "ب" not in out, str(out.get("ب")))

# brute force cross-check of the definitions on this group
import itertools        # noqa: E402
idx = {t: i for i, t in enumerate(T)}
base = [pts[t] for t in T]
ok = True
for case in itertools.product((0, 1, 2), repeat=len(LEFT)):
    p = base[:]
    for m, r in zip(LEFT, case):
        h, a = idx[m["home"]], idx[m["away"]]
        if r == 0:
            p[h] += 3
        elif r == 2:
            p[a] += 3
        else:
            p[h] += 1; p[a] += 1
    rank = lambda i: sum(1 for j in range(4) if j != i and p[j] >= p[i])       # noqa: E731
    above = lambda i: sum(1 for j in range(4) if j != i and p[j] > p[i])       # noqa: E731
    ok &= rank(idx["أ"]) < 2 and above(idx["د"]) >= 2
    if p[idx["ج"]] >= 11:
        ok &= rank(idx["ج"]) < 2
ck("6 every one of the 81 cases agrees with the three sentences", ok)

ck("7 the sentences: plain, with the totals and the matches left",
   Q.line(out["أ"], "ربع النهائي") == "أ ضمن التأهل إلى ربع النهائي."
   and Q.line(out["د"], "ربع النهائي") == "د خرج من المنافسة على التأهل."
   and Q.line(out["ج"], "ربع النهائي") == "ج يضمن التأهل إذا وصل إلى 11 نقطة. رصيده 7 نقاط، وأمامه مباراتان.")
early = [dict(m, home_score=None, away_score=None, status="UPCOMING") if i >= 4 else m for i, m in enumerate(GAMES)]
ck("8b two rounds played: no sentence yet", Q.group_outlook(table(early), early + LEFT, 2) == [])
bad = [dict(r) for r in tb]
bad[0]["pts"] += 1
ck("9 a table our rows do not add up to: the whole group is skipped", Q.group_outlook(bad, GAMES + LEFT, 2) == [])
ck("10 a remaining match missing from the feed: skipped", Q.group_outlook(tb, GAMES + LEFT[:3], 2) == [])
ck("11 the group is over: the table is the answer, no sentence",
   Q.group_outlook(table(GAMES + [dict(m, home_score=1, away_score=0, status="FINISHED") for m in LEFT]),
                   GAMES + [dict(m, home_score=1, away_score=0, status="FINISHED") for m in LEFT], 2) == [])
ck("12 the same match listed twice is one match", {o["team"]: o["state"] for o in Q.group_outlook(tb, GAMES + GAMES + LEFT + LEFT, 2)}
   == {t: o["state"] for t, o in out.items()})
grp = [{"name": "المجموعة أ", "table": tb}]
ck("13 only competitions whose rule is fixed: the two CAF club cups, never the Africa Cup qualifiers (a host changes the rule)",
   set(Q.QUALIFY) == {"CAF Champions League", "CAF Confederation Cup"}
   and Q.outlook_html("Africa Cup of Nations Qualification", "التصفيات", grp, GAMES + LEFT) == "")
html = Q.outlook_html("CAF Champions League", "دوري أبطال أفريقيا", grp, GAMES + LEFT)
ck("14 the section: the rule, the honest note about ties, one line per side we are sure of",
   'id="qual"' in html and "أول فريقين" in html and "بالنقاط فقط" in html and html.count("<li>") == 3
   and "المجموعة أ" in html, html)
ck("15 nothing sure to say -> no section", Q.outlook_html("CAF Champions League", "x", [{"name": "g", "table": table(early)}], early + LEFT) == "")

# ---------------------------------------------------------------- jump chips
from site_lib.tables import jump_chips        # noqa: E402

art = '<section class="minfo marticle"><h2>t</h2></section>'
det = ('<section class="minfo mstats"><h2>أرقام</h2></section><section class="minfo"><h2>أحداث المباراة</h2></section>'
       '<section class="minfo"><h2>تشكيل أ وب</h2></section>')
a2, d2, nav = jump_chips(art, det)
ck("16 a finished page with its report: four chips in page order, each section given its id once",
   [x.split('"')[0] for x in nav.split('href="#')[1:]] == ["mp-report", "mp-stats", "mp-events", "mp-xi"]
   and 'id="mp-report"' in a2 and d2.count(' id="') == 3)
ck("17 no report -> no chips, and nothing is changed for a page with one section",
   jump_chips("", det)[2] == "" and jump_chips(art, "")[2] == "")
tpl = io.open("site_src/templates/match.html", encoding="utf-8").read()
ck("18 the chips sit right under the score, before everything else", tpl.index("{{ hero_row }}") < tpl.index("{{ jump }}") < tpl.index("{{ motm }}"))

# ---------------------------------------------------------------- the calculator's door in «فريقك»
from site_lib.follow import my_block_html        # noqa: E402

b1 = my_block_html("الأهلي", "al-ahly", "", "المركز 2", "", [], calc={"href": "/calc/egypt.html", "label": "حاسبة ترتيب الدوري المصري"})
ck("19 a club whose league has a calculator page gets the door; another gets nothing",
   'class="my-calc" href="/calc/egypt.html"' in b1 and "my-calc" not in my_block_html("السودان", "sudan", "", "", "", []))
css = io.open("site_src/style.css", encoding="utf-8").read()
ck("20 tap targets of 44px for the chips and the door; the sticky header does not cover a jump",
   ".mp-jump a{" in css and "min-height:44px" in css.split(".mp-jump a{")[1].split("}")[0]
   and "min-height:44px" in css.split(".my-calc{")[1].split("}")[0] and "scroll-margin-top" in css)

dist = os.path.join(os.getcwd(), "dist")
if os.path.isdir(os.path.join(dist, "my")):
    import glob
    with_art = [p for p in glob.glob(os.path.join(dist, "m", "*.html"))[:400] if 'id="mp-report"' in io.open(p, encoding="utf-8").read()]
    ck("21 the built site: finished pages with a report carry the chips; الأهلي's block has the door",
       with_art and all('class="mp-jump"' in io.open(p, encoding="utf-8").read() for p in with_art[:20])
       and "my-calc" in io.open(os.path.join(dist, "my", "al-ahly.json"), encoding="utf-8").read())

print("ALL OK" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
