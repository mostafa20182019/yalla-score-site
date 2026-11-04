# -*- coding: utf-8 -*-
"""The SEO pass of 2026-11-04 (user: «ابدأ الإصلاحات»), four code fixes:

  1. a Saudi Pro League «الأهلي» is «الأهلي السعودي» in a match page's text
     (names.ar_team_in) - the bare word is the Egyptian club's to every reader;
  2. the season's details from the D1 archive fill what the 45-day store lost
     (matchdata.merge_details), so an old result keeps its reading and its index;
  3. the news archives are paginated (40 rows a page, /news/p2 ...), each page
     a canonical URL in the sitemap with «الأحدث» / «الأقدم» links;
  4. the home page has an H1 and a match page's H1 is the query its title answers.

Run from the site root:  python tests/test_seo_pass.py
"""
import io
import os
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())

fails = []


def ok(n, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + n + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails.append(n)


# ---- 1. the Saudi Al-Ahli ----------------------------------------------------
from site_lib.names import ar_team, ar_team_in                   # noqa: E402

ok("1a Saudi Pro League: «الأهلي» becomes «الأهلي السعودي»",
   ar_team_in("الأهلي", "Saudi Pro League") == "الأهلي السعودي")
ok("1b Egyptian Premier League / cups / CAF: the bare name stays",
   all(ar_team_in("الأهلي", c) == "الأهلي"
       for c in ("Egyptian Premier League", "Egypt Cup", "CAF Confederation Cup", "", None)))
ok("1c the Libyan sides arrive distinct and are left alone",
   ar_team_in("الأهلي طرابلس", "Libyan Premier League") == "الأهلي طرابلس"
   and ar_team_in("الأهلي بنغازي", "Libyan Premier League") == "الأهلي بنغازي")
ok("1d any other club = ar_team()",
   ar_team_in("الهلال", "Saudi Pro League") == ar_team("الهلال")
   and ar_team_in("Arsenal FC", "Premier League") == ar_team("Arsenal FC"))
mp = io.open("site_pages/matches.py", encoding="utf-8").read()
ok("1e the match pages use the qualified name for their text",
   'h_ar = ar_team_in(m.get("home"), m.get("competition"))' in mp
   and 'a_ar = ar_team_in(m.get("away"), m.get("competition"))' in mp)

# ---- 2. the archived details under the store -------------------------------
from site_lib.matchdata import merge_details                     # noqa: E402

store = [{"match_id": "1", "home": "الأهلي", "away": "الزمالك", "date": "2026-10-01", "src": "store"}]
arch = [{"match_id": "1", "home": "الأهلي", "away": "الزمالك", "date": "2026-10-01", "src": "arch"},
        {"match_id": "x", "home": "الزمالك", "away": "الأهلي", "date": "2026-10-01", "src": "arch-flipped"},
        {"match_id": "2", "home": "سموحة", "away": "بيراميدز", "date": "2026-08-21", "src": "arch"},
        {"match_id": "3", "home": "", "away": "زد", "date": "2026-08-21", "src": "bad"}]
m = merge_details(store, arch)
ok("2a the store's entry wins over the archive's copy of the same match",
   [e["src"] for e in m if e["match_id"] == "1"] == ["store"])
ok("2b the reversed pair of a held match is the same match, not a second entry",
   not any(e["src"] == "arch-flipped" for e in m))
ok("2c an older match the store no longer holds is added from the archive",
   any(e["match_id"] == "2" for e in m))
ok("2d an entry without both clubs and a date is skipped", not any(e["src"] == "bad" for e in m))
ok("2e no archive = the store untouched", merge_details(store, []) is store)
b = io.open("build_site.py", encoding="utf-8").read()
ok("2f build() merges details_archive.json under match_details.json before indexing",
   'merge_details(_details_raw, load("details_archive.json"))' in b
   and b.index('load("details_archive.json")') < b.index("md_idx = match_details_index(_details_raw)"))
ds = io.open("data_store.py", encoding="utf-8").read()
ok("2g the export is a store file, accumulating by (date, home, away)",
   '"details_archive.json",' in ds and '"details_archive.json": lambda e: f\'{e.get("date")}|{e.get("home")}|{e.get("away")}\'' in ds)
wf = io.open(".github/workflows/archive-db.yml", encoding="utf-8").read()
ok("2h the nightly archive job exports it and pushes ONLY that file",
   "python archive_db.py --export data/details_archive.json" in wf
   and "python data_store.py push --only details_archive.json" in wf)
_exp = wf.split("Export the season's details for the build", 1)[1]
ok("2h2 the push step carries the KV token (CLOUDFLARE_API_TOKEN, as publish.yml) and pipefail - "
   "the first run's 401 hid behind `| tee` (2026-11-04)",
   "CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}" in _exp and "set -o pipefail" in _exp)

# push --only: the other files come from the store as it is NOW, never from
# this job's hour-old pull
import json                                                      # noqa: E402
import data_store as DS                                          # noqa: E402

tmp = tempfile.mkdtemp(prefix="seo-")
DS.DATA = os.path.join(tmp, "data")
DS.STATE = os.path.join(DS.DATA, ".store_state.json")
os.makedirs(DS.DATA)
KV = {}
DS.remote_get = lambda: DS.unpack(KV["blob"]) if "blob" in KV else (None, {})
DS.remote_put = lambda blob: KV.__setitem__("blob", blob)


def _w(name, doc):
    with open(os.path.join(DS.DATA, name), "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False)


_w("matches.json", {"results": [{"items": [{"match_id": "fresh"}]}]})
_w("fixtures.json", {"results": [{"items": []}]})
_w("results_archive.json", {"meta": {}, "results": []})
DS.push(seed=True)                                   # the store as the publish runs left it
DS.pull()
_w("matches.json", {"results": [{"items": [{"match_id": "STALE"}]}]})   # this job's old copy
_w("details_archive.json", {"results": [{"items": [{"date": "2026-08-21", "home": "a", "away": "b"}]}]})
rc = DS.push(only=["details_archive.json"])
_, after = DS.remote_get()
ok("2i push --only writes the named file and keeps the store's copy of the rest",
   rc == 0 and b"STALE" not in after["matches.json"] and b"fresh" in after["matches.json"]
   and after.get("details_archive.json") and b"2026-08-21" in after["details_archive.json"])

# a plain push from a job whose data/ lacks a store file keeps the store's
# copy - the archive export was lost exactly this way on its first day
os.remove(os.path.join(DS.DATA, "details_archive.json"))
_w("matches.json", {"results": [{"items": [{"match_id": "fresher"}]}]})
with open(DS.STATE, encoding="utf-8") as f:
    _st = json.load(f)
_st["remote_ver"] = "stale"                    # pulled before someone else pushed
with open(DS.STATE, "w", encoding="utf-8") as f:
    json.dump(_st, f)
rc = DS.push()
_, after = DS.remote_get()
ok("2j a plain push never drops a store file the job did not have (the union rule)",
   rc == 0 and after.get("details_archive.json") and b"2026-08-21" in after["details_archive.json"]
   and b"fresher" in after["matches.json"])

# ---- 3. the paginated news archives ----------------------------------------
import site_lib.shell as SH                                      # noqa: E402
import site_pages.articles as AP                                 # noqa: E402

dist = os.path.join(tmp, "dist")
os.makedirs(dist)
_d1, _d2 = SH.DIST, AP.DIST
SH.DIST, AP.DIST = dist, dist
try:
    arts = [{"article_id": str(i), "title": f"خبر {i}", "summary": "ملخص", "pub_date": "2026-11-01",
             "pub_ts": "2026-11-01T10:00:00", "author": "فريق التحرير"} for i in range(1, 86)]
    urls = []
    AP.news_archive_pages(arts, urls)
    p1 = io.open(os.path.join(dist, "news.html"), encoding="utf-8").read()
    p2 = io.open(os.path.join(dist, "news", "p2.html"), encoding="utf-8").read()
    p3 = io.open(os.path.join(dist, "news", "p3.html"), encoding="utf-8").read()
    ok("3a 85 articles = pages of 40: /news, /news/p2, /news/p3 (and no p4)",
       p1.count('class="al-row"') == 40 and p2.count('class="al-row"') == 40 and p3.count('class="al-row"') == 5
       and not os.path.exists(os.path.join(dist, "news", "p4.html")))
    ok("3b the first page keeps its title; later pages say which page they are",
       "<title>كل الأخبار — الجون</title>" in p1 and "صفحة 2" in p2 and 'rel="canonical" href="https://elgoon.com/news/p2"' in p2)
    ok("3c «الأحدث» / «الأقدم» walk the archive: p1 has only الأقدم, p3 only الأحدث",
       'href="/news/p2">الأقدم' in p1 and "الأحدث" not in p1.split('class="pager"')[1]
       and 'href="/news/p2">الأحدث' in p3 and "الأقدم" not in p3.split('class="pager"')[1]
       and 'href="/news">الأحدث' in p2 and 'href="/news/p3">الأقدم' in p2)
    ok("3d the newest article opens the first page, the oldest closes the last",
       p1.index('خبر 1<') < p1.index('خبر 40<') and 'خبر 85<' in p3 and 'خبر 41<' not in p1)
    ok("3e every page is in the sitemap list; the section archives paginate as /news/<section>-p2",
       "/news.html" in urls and "/news/p2.html" in urls and "/news/p3.html" in urls
       and "/news/egypt.html" in urls and not any(u.startswith("/news/egypt-p") for u in urls))
    ok("3f a continuation page shows no breadcrumb to itself", 'class="crumbs"' not in p2)
finally:
    SH.DIST, AP.DIST = _d1, _d2

# ---- 4. the headings ----------------------------------------------------------
home = io.open("site_src/templates/home.html", encoding="utf-8").read()
ok("4a the home page has one H1 (screen-reader only - the match centre keeps its look)",
   home.count("<h1") == 1 and '<h1 class="sr-only">' in home and "مباريات اليوم" in home)
mt = io.open("site_src/templates/match.html", encoding="utf-8").read()
ok("4b a match page's H1 is the query its title answers, not a bare «مباراة X وY»",
   '<h1 class="page-h">{{ h1 }}</h1>' in mt and 'h1=title.split(" — ")[0]' in mp)

print(f"\n{len(fails)} FAILED: {fails}" if fails else "\nALL SEO-PASS TESTS PASSED")
sys.exit(1 if fails else 0)
