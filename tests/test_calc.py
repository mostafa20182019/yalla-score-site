# -*- coding: utf-8 -*-
r"""«حاسبة الترتيب» (/calc/<slug>, 2026-11-19).

    python tests/test_calc.py      (from the repo root)

What it guards: which league gets the page (a real table, enough matches
still to play between teams OF that table); what the reader may decide
(never a finished or a live match); the page saying something true without
its script; the arithmetic itself - run in node on the page's own script -
and the rule that nothing from the feed is written as HTML.
"""
import io
import json
import os
import subprocess
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())

from site_lib import calc as K          # noqa: E402

fails = 0


def ck(msg, cond, extra=""):
    global fails
    print(("  ok   " if cond else "  FAIL ") + msg + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails += 1


def row(team, pts, p=5, gf=5, ga=5):
    return {"team": team, "crest": "", "played": p, "won": 0, "draw": 0, "lost": 0, "gf": gf, "ga": ga, "pts": pts}


def match(i, h, a, st="UPCOMING", rd=6, **kw):
    m = {"match_id": i, "home": h, "away": a, "status": st, "kickoff": "2026-11-23", "koff_time": "20:00",
         "home_score": None, "away_score": None, "round": rd}
    m.update(kw)
    return m


TEAMS = ["أ", "ب", "ج", "د", "هـ", "و"]
ST = {"table": [row(t, 12 - 2 * i) for i, t in enumerate(TEAMS)]}
FX = {"rounds": [{"round": 6, "matches": [match(1, "أ", "ب"), match(2, "ج", "د"), match(3, "هـ", "و")]},
                 {"round": 7, "matches": [match(4, "ب", "ج", rd=7), match(5, "د", "هـ", rd=7), match(6, "و", "أ", rd=7)]}]}
d = K.calc_data(ST, FX)
ck("1 a league with a table and matches to play gets the page: teams in table order, rounds in order",
   d and [t["n"] for t in d["teams"]] == TEAMS and [r["r"] for r in d["rounds"]] == [6, 7]
   and d["rounds"][0]["m"][0][:3] == ["1", 0, 1], str(d)[:200])
ck("2 the counts the page states", K.calc_counts(d) == (2, 6))

fx2 = {"rounds": [{"round": 6, "matches": [
    match(1, "أ", "ب", "FINISHED", home_score=1, away_score=0), match(2, "ج", "د", "LIVE"),
    match(3, "هـ", "و"), match(7, "أ", "نادٍ من خارج الجدول"), match(8, "أ", "أ")]},
    {"round": 7, "matches": [match(4, "ب", "ج", rd=7), match(5, "د", "هـ", rd=7), match(6, "و", "أ", rd=7),
                             match(9, "ب", "د", "POSTPONED", rd=7)]}]}
d2 = K.calc_data(ST, fx2)
keys = [m[0] for r in d2["rounds"] for m in r["m"]]
ck("3 a finished match, a live one, a side outside the table and a team against itself are never offered",
   keys == ["3", "4", "5", "6", "9"], str(keys))
ck("4 a postponed match stays, and says so", [m[3] for r in d2["rounds"] for m in r["m"] if m[0] == "9"] == ["مؤجلة"])
ck("5 no table, a tiny table, no fixtures: no page",
   K.calc_data({"table": []}, FX) is None and K.calc_data({"table": ST["table"][:3]}, FX) is None
   and K.calc_data(ST, {"rounds": []}) is None and K.calc_data(None, None) is None)
ck(f"6 fewer than {K.MIN_MATCHES} matches to play is a stub, not a page",
   K.calc_data(ST, {"rounds": [{"round": 6, "matches": [match(1, "أ", "ب"), match(2, "ج", "د")]}]}) is None)
ck("7 a named stage (a cup round) is not a league round",
   K.calc_data(ST, {"rounds": [{"round": 1, "label": "دور الـ16", "matches": FX["rounds"][0]["matches"] + FX["rounds"][1]["matches"]}]}) is None)

# ------------------------------------------------- the arithmetic, in node
js = io.open("site_src/snippets/calc_js.html", encoding="utf-8").read()
body = js.split("<script>", 1)[1].rsplit("</script>", 1)[0]
harness = r"""
const store = {};
function node(tag){ const n={tag,children:[],attrs:{},className:'',textContent:'',hidden:false,disabled:false,listeners:{},
  classList:{add(c){n.className+=' '+c;},contains(c){return n.className.split(' ').includes(c);}},
  appendChild(c){ if(n._text!==undefined) n._text=undefined; n.children.push(c); return c; },
  setAttribute(k,v){n.attrs[k]=v;}, getAttribute(k){return n.attrs[k];},
  addEventListener(e,f){n.listeners[e]=f;}, click(){ n.listeners.click && n.listeners.click(); },
  querySelector(){ return null; } };
  Object.defineProperty(n,'textContent',{get(){return n._t||'';},set(v){n._t=v; if(v==='') n.children=[];}});
  return n; }
const els = { calc: node('div'), calcData: node('script'), calcRound: node('h2'), calcMatches: node('div'),
              calcBody: node('tbody'), calcCount: node('span'), calcReset: node('button') };
els.calc.attrs['data-slug']='t'; const prev=node('button'), next=node('button');
els.calc.querySelector = (s) => s==='.calc-prev' ? prev : s==='.calc-next' ? next : null;
els.calcData.textContent = JSON.stringify(DATA);
global.document = { getElementById: (i) => els[i] || null, createElement: node };
global.localStorage = { getItem: (k) => (k in store ? store[k] : null), setItem: (k,v) => { store[k]=v; } };
BODY
const table = () => els.calcBody.children.map(tr => [tr.children[2].children[0].children[1].textContent, +tr.children[3].textContent,
                                                  tr.children[4].textContent, +tr.children[5].textContent, tr.children[1].textContent]);
const pick = (i, v) => els.calcMatches.children[i].children[1].children[v].click();
const out = { start: table(), round: els.calcRound.textContent, n: els.calcMatches.children.length };
pick(0, 2);                       // match 1: the AWAY side (ب) wins
out.afterAway = table(); out.stored = store['elgoonCalc:t']; out.count = els.calcCount.textContent;
pick(0, 2);                       // the same button again: the pick is taken back
out.undone = table();
pick(0, 1); pick(1, 0);           // a draw, and a home win in match 2
out.mixed = table();
next.click(); out.round2 = els.calcRound.textContent; out.nextDisabled = next.disabled;
els.calcReset.click(); out.reset = table(); out.storedAfter = store['elgoonCalc:t'];
console.log(JSON.stringify(out));
"""
tmp = os.path.join(tempfile.mkdtemp(), "calc_run.js")
io.open(tmp, "w", encoding="utf-8").write(
    harness.replace("DATA", json.dumps(d, ensure_ascii=False)).replace("BODY", body))
r = subprocess.run(["node", tmp], capture_output=True, text=True, encoding="utf-8")
o = json.loads(r.stdout) if r.returncode == 0 and r.stdout.strip() else {}
ck("8 the script runs and opens on the nearest round with the table as saved",
   o.get("round") == "الجولة 6" and o.get("n") == 3 and [x[0] for x in o.get("start", [])] == TEAMS, r.stderr[:300])
aw = {x[0]: x for x in o.get("afterAway", [])}
ck("9 an away win: +3 points, one more match, +1 / -1 goal difference - and the table re-sorts",
   aw and aw["ب"][3] == 13 and aw["ب"][1] == 6 and aw["ب"][2] == "+1" and aw["أ"][3] == 12 and aw["أ"][2] == "-1"
   and [x[0] for x in o["afterAway"]][:2] == ["ب", "أ"], str(o.get("afterAway")))
ck("10 the arrows say who moved", aw and aw["ب"][4] == "▲1" and aw["أ"][4] == "▼1")
ck("11 the pick is kept in the browser, per league", o.get("stored") == '{"1":"a"}' and "1" in (o.get("count") or ""))
ck("12 the same button again takes the pick back", o.get("undone") == o.get("start"))
mx = {x[0]: x for x in o.get("mixed", [])}
ck("13 a draw gives a point each and leaves the goal difference; a home win gives three",
   mx and mx["أ"][3] == 13 and mx["ب"][3] == 11 and mx["أ"][2] == "0" and mx["ج"][3] == 11 and mx["د"][3] == 6)
ck("14 the next round opens, and the last one has no «next»", o.get("round2") == "الجولة 7" and o.get("nextDisabled") is True)
ck("15 «مسح التوقعات» puts the table back", o.get("reset") == o.get("start") and o.get("storedAfter") == "{}")
ck("16 nothing from the feed is parsed as HTML", "innerHTML" not in body and "insertAdjacentHTML" not in body
   and "document.write" not in body)
ck("17 no request leaves the page", "fetch(" not in body and "XMLHttpRequest" not in body and "sendBeacon" not in body)
# site review 2026-11-19
ck("17b the picked side is told apart: the button is ticked and the winner's name goes bold",
   "(v===o[0]?'✓ ':'')+o[1]" in body and "v==='h'?' calc-win':''" in body and "v==='a'?' calc-win':''" in body)
ck("17c the cells holding one signed number are LTR («+15», «▲1»), and the name sits in a span, not a flex table cell",
   body.count("setAttribute('dir','ltr')") >= 3 and "el('span','calc-tmw')" in body
   and "td.calc-tm{display:flex" not in io.open("site_src/style.css", encoding="utf-8").read())
_tplc = io.open("site_src/templates/calc.html", encoding="utf-8").read()
_cssc = io.open("site_src/style.css", encoding="utf-8").read()
ck("17d the effect of the last pick stays in sight: a sticky bar, hidden until a pick, with a way down to the table",
   'id="calcFx" class="calc-fx" role="status" hidden' in _tplc and 'id="calcFxGo"' in _tplc
   and ".calc-fx{position:sticky" in _cssc and "effect(m,drawTable())" in body and "effect(null)" in body)
ck("17e the choice buttons are finger-sized", ".calc-b{" in _cssc and "min-height:44px;min-width:48px" in _cssc)

# ------------------------------------------------- the page and its wiring
tpl = io.open("site_src/templates/calc.html", encoding="utf-8").read()
ck("18 without the script the page still shows the table and the next round; the buttons are the script's",
   "{% for r in rows %}" in tpl and "{% for m in first %}" in tpl and 'class="calc-prev"' in tpl
   and tpl.count(" hidden>") >= 3)
ck("19 the page says how a win and a draw are counted, and that the official rules may differ",
   "الفوز يُحسب 1-0 والتعادل 1-1" in tpl and "لائحة البطولة الرسمية" in tpl)
pg = io.open("site_pages/calc.py", encoding="utf-8").read()
ck("20 the JSON cannot close its own script element", '.replace("</", "<\\\\/")' in pg)
lg = io.open("site_pages/leagues.py", encoding="utf-8").read()
ck("21 the standings page links here only when the same test passes",
   "_calc_data(st, (fx_by_comp or {}).get(comp))" in lg and "/calc/{slug}.html" in lg)
bs = io.open("build_site.py", encoding="utf-8").read()
ck("22 the build writes the pages before the sitemap", bs.index("calc_pages(fx_by_comp") < bs.index("robots_sitemap_ads(articles, urls)"))

dist = os.path.join(os.getcwd(), "dist")
if os.path.isdir(os.path.join(dist, "calc")):
    import re
    files = sorted(os.listdir(os.path.join(dist, "calc")))
    sm = io.open(os.path.join(dist, "sitemap.xml"), encoding="utf-8").read()
    bad = []
    for f in files:
        h = io.open(os.path.join(dist, "calc", f), encoding="utf-8").read()
        dd = json.loads(re.search(r'id="calcData">(.*?)</script>', h, re.S).group(1))
        slug = f[:-5]
        if not (len(dd["teams"]) >= K.MIN_TEAMS and K.calc_counts(dd)[1] >= K.MIN_MATCHES
                and h.count("<h1") == 1 and f"/calc/{slug}<" in sm
                and f'href="/calc/{slug}"' in io.open(os.path.join(dist, "standings", f), encoding="utf-8").read()
                and all(0 <= m[1] < len(dd["teams"]) and 0 <= m[2] < len(dd["teams"]) for r in dd["rounds"] for m in r["m"])):
            bad.append(slug)
    ck(f"23 every built page ({len(files)}): valid data, one H1, in the sitemap, linked from its standings page", files and not bad, str(bad))

print("ALL OK" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
