r"""الترتيب · الهدافون · صناعة الأهداف as tabs on the match page (2026-11-06).

    python tests/test_match_tabs.py

«عايزك تحط جنب الترتيب تاب للهدافين وتاب لأعلى اسيستات». The block is the
standings page's own (site_src/templates/_st_tabs.html), included by both
pages, so the two cannot drift apart.
"""
import os, re, sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())
from site_lib.render import Markup, render                 # noqa: E402
from site_lib.snippets import ST_TABS_JS                   # noqa: E402

fails = []
def ck(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  [{extra}]" if extra else ""))
    if not cond:
        fails.append(name)

rd = lambda p: open(p, encoding="utf-8").read()
ck("1 both pages include the one shared block",
   '{% include "_st_tabs.html" %}' in rd("site_src/templates/standings.html")
   and '{% include "_st_tabs.html" %}' in rd("site_src/templates/match.html"))

both = render("_st_tabs.html", table=Markup('<div class="ltable">T</div>'), has_sc=True,
              scorers=Markup("<p>S</p>"), has_asst=True, assists=Markup("<p>A</p>"),
              label="الدوري", tabs_js=Markup(ST_TABS_JS))
tabs = re.findall(r'data-pane="(\w+)">([^<]+)</button>', both)
ck("2 three tabs, the table first", tabs == [("table", "الترتيب"), ("scorers", "الهدافون"),
                                             ("assists", "صناعة الأهداف")], tabs)
ck("3 every pane is in the HTML (indexable without JS) and the script follows the block",
   all(f'data-pane="{k}"' in both for k in ("table", "scorers", "assists"))
   and both.index("</div>" , both.rindex('data-pane="assists"')) < both.index("<script>"))
only = render("_st_tabs.html", table=Markup('<div class="ltable">T</div>'), has_sc=False, scorers="",
              has_asst=False, assists="", label="x", tabs_js=Markup(ST_TABS_JS))
ck("4 no charts for the league: just the table, no tab bar, no script", "ltabs" not in only and "<script>" not in only
   and 'class="ltable"' in only)

mp = rd("site_pages/matches.py")
ck("5 the match pages render each league's lists once (comp_charts cache)", "def comp_charts(comp):" in mp
   and "_chart_html[comp]" in mp)
ck("6 build() hands the charts to match_pages", "charts=(sc_by_comp, sc_ok, as_by_comp, as_ok)" in rd("build_site.py"))
css = rd("site_src/style.css")
ck("7 on a phone the block bleeds to the card edges so «نقاط» stays on screen",
   ".minfo>.st-tabs,.minfo>.ltable{margin-inline:-14px}" in css)

print(f"\n{len(fails)} FAILED" if fails else "\nALL OK")
sys.exit(1 if fails else 0)
