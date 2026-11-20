# -*- coding: utf-8 -*-
r"""/standings/<slug> for the competitions played in GROUPS (2026-11-20).

    python tests/test_group_standings.py      (from the repo root, after a build)

The SEO review found the group tables only inside /fixtures/<slug>, one at a
time behind ‹ ›, and an article linking /standings/afcon-qualifiers - a page
that did not exist. site_pages.leagues.group_standings_pages writes one page
per group competition. Every check is a RELATION between the data and the
built page (a competition with no groups in the data checks nothing), so the
test cannot go red because a tournament ended.
"""
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())

from site_lib.competitions import COMP_SLUG      # noqa: E402
from site_lib.names import ar_team               # noqa: E402

fails = 0


def ck(msg, cond, extra=""):
    global fails
    print(("  ok   " if cond else "  FAIL ") + msg + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails += 1


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


raw = json.load(open("data/standings.json", encoding="utf-8"))
items = raw.get("results") if isinstance(raw, dict) else raw
if items and isinstance(items[0], dict) and "items" in items[0]:
    items = items[0]["items"]
group_comps = [s for s in items or []
               if s.get("competition") in COMP_SLUG and not s.get("table")
               and any(g.get("table") for g in s.get("groups") or [])]
print(f"group competitions in the data: {len(group_comps)}")

print("1. one page per group competition, every group on show")
for s in group_comps:
    comp, slug = s["competition"], COMP_SLUG[s["competition"]]
    path = os.path.join("dist", "standings", slug + ".html")
    ck(f"{slug}: the page exists", os.path.exists(path))
    if not os.path.exists(path):
        continue
    html = read(path)
    groups = [g for g in s["groups"] if g.get("table")]
    title = re.search(r"<title>(.*?)</title>", html).group(1)
    ck(f"{slug}: the title says «ترتيب مجموعات»", title.startswith("ترتيب مجموعات"), title)
    ck(f"{slug}: the title is not cut", len(title.split(" | ")[0]) <= 62, title)
    desc = re.search(r'name="description" content="(.*?)"', html).group(1)
    ck(f"{slug}: the description ends on a whole sentence", desc.endswith(".") and "…" not in desc, desc)
    heads = re.findall(r'<section class="minfo gst" id="g(\d+)">\s*<h2>(.*?)</h2>', html)
    ck(f"{slug}: a heading per group ({len(groups)})", len(heads) == len(groups), str(len(heads)))
    ck(f"{slug}: no group is hidden behind a navigator",
       'class="rnav"' not in html and not re.search(r'<div class="round"[^>]*hidden', html))
    for g in groups:
        names = [ar_team(r.get("team")) for r in g["table"]]
        h2 = next((h for num, h in heads if num == str(g["num"])), "")
        if not all(n in h2 for n in names):
            ck(f"{slug}: {g['name']} heading names its teams", False, h2)
            break
    else:
        ck(f"{slug}: every heading names its group's teams", True)
    ck(f"{slug}: as many tables as groups", html.count('<div class="ltable"') == len(groups),
       str(html.count('<div class="ltable"')))
    started = any((r.get("played") or 0) for g in groups for r in g["table"])
    ck(f"{slug}: a stage not yet played says so, a played one does not",
       ("لم يبدأ بعد" in html) == (not started))
    ck(f"{slug}: breadcrumbs + FAQ data", "BreadcrumbList" in html and "FAQPage" in html)
    ck(f"{slug}: not noindexed", 'content="noindex' not in html)
    fx = os.path.join("dist", "fixtures", slug + ".html")
    if os.path.exists(fx):
        ck(f"{slug}: the fixtures page links it",
           re.search(rf'href="/standings/{slug}(\.html)?"', read(fx)) is not None)
        ck(f"{slug}: it links the fixtures page",
           re.search(rf'href="/fixtures/{slug}(\.html)?"', html) is not None)

print("2. /leagues opens the groups page, not the fixtures page")
lg = read(os.path.join("dist", "leagues.html"))
for s in group_comps:
    slug = COMP_SLUG[s["competition"]]
    ck(f"{slug}: the «البطولات» row", re.search(rf'class="lgx-row" href="/standings/{slug}(\.html)?"', lg) is not None)

print("3. no /standings link anywhere on the hub pages points at a missing page")
have = {f[:-5] for f in os.listdir(os.path.join("dist", "standings")) if f.endswith(".html")}
dead = set()
for folder in ("", "fixtures", "standings", "team", "scorers"):
    base = os.path.join("dist", folder)
    for f in os.listdir(base):
        if f.endswith(".html"):
            for slug in re.findall(r'href="/standings/([a-z0-9-]+)(?:\.html)?"', read(os.path.join(base, f))):
                if slug not in have:
                    dead.add((folder + "/" + f, slug))
ck("hub pages: every /standings link resolves", not dead, str(sorted(dead)[:5]))

print("4. a club page shows the group its club plays in")
from site_lib.clubs import TEAM_PAGES            # noqa: E402
from site_lib.names import _team_match           # noqa: E402
n_club = 0
for s in group_comps:
    comp, slug = s["competition"], COMP_SLUG[s["competition"]]
    for g in s["groups"]:
        for tp in TEAM_PAGES:
            hit = [r for r in g.get("table") or []
                   if _team_match(tp, {"home": r.get("team") or "", "away": "", "competition": comp})]
            if len(hit) != 1:
                continue
            page = os.path.join("dist", "team", tp["slug"] + ".html")
            if not os.path.exists(page):
                continue
            n_club += 1
            html = read(page)
            ok = (re.search(rf'href="/standings/{slug}(\.html)?"', html) is not None
                  and g["name"] in html and 'class="lt-me"' in html)
            if not ok:
                ck(f"/team/{tp['slug']}: its {g['name']} table ({slug})", False)
ck(f"club pages checked: {n_club}", True)

print("\nALL OK" if not fails else f"\n{fails} FAILED")
sys.exit(1 if fails else 0)
