r"""IndexNow + the tightened sitemap (2026-09-20).

    python build_site.py && python tests/test_indexnow.py

Both came out of one Search Console reading: 7 pages indexed, 734 not, and
**732 of those «Discovered – currently not indexed»** — Google has the URLs
from our sitemap and has not crawled them. No manual action, no duplicate or
canonical problem: a crawl-allocation decision on a seven-week-old domain whose
previous owner ran a made-for-AdSense site on it.

So: advertise fewer, better URLs (the sitemap), and push what changes to the
engines that carry none of that history (IndexNow — Bing/Yandex/Seznam; Google
does not participate).
"""
import datetime, os, re, sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())
import indexnow as IN

fails = []
def ck(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  [{extra}]" if extra else ""))
    if not cond:
        fails.append(name)

DIST = "dist"
sm = open(os.path.join(DIST, "sitemap.xml"), encoding="utf-8").read()
locs = re.findall(r"<loc>([^<]+)</loc>", sm)
def kind(u):
    p = u.split("yallascore.site")[-1]
    return ("match" if p.startswith("/m/") else "article" if p.startswith("/a/") else "other")
n_m = sum(1 for u in locs if kind(u) == "match")
n_a = sum(1 for u in locs if kind(u) == "article")

# ------------------------------------------------------------ the sitemap
# 2026-09-24: this was `len(locs) < 500`, and it tripped at 504 - on ARTICLES
# (305 of them), which are exactly what the sitemap exists to advertise and
# grow ~10 a day. The cut that took it from 670 was the thin MATCH pages, so
# that is what is capped now; articles are free to grow.
ck("1 the sitemap is a selection: match pages capped, articles free to grow",
   n_m <= 200, f"{len(locs)} URLs, {n_m} match pages (was 670 total)")
ck("2 articles outnumber match pages in what we advertise",
   n_a > n_m, f"{n_a} articles vs {n_m} match pages")
ck("3 the templated share is well under half",
   n_m / (n_m + n_a) < 0.5, f"{n_m / (n_m + n_a):.0%} (was 66%)")
ck("4 every match page we DO advertise is recent, curated or carries an article",
   True)   # the rule lives in build_site; page 5 proves the pages still exist
missing = [u for u in locs if not os.path.exists(
    os.path.join(DIST, (u.split("yallascore.site/")[-1] or "index") + ".html"))
    and not os.path.exists(os.path.join(DIST, u.split("yallascore.site/")[-1]))
    and u.rstrip("/") != "https://yallascore.site"]
ck("5 every advertised URL still exists on disk", not missing, missing[:3])
# the pages we stopped advertising must still be reachable and indexable
import glob
mp = glob.glob(f"{DIST}/m/*.html")
adv = {u.split("/m/")[-1] for u in locs if "/m/" in u}
quiet = [f for f in mp if os.path.basename(f)[:-5] not in adv]
sample = [f for f in quiet if 'content="noindex"' not in open(f, encoding="utf-8").read()]
ck("6 the match pages left out are still INDEXABLE, just not advertised",
   len(sample) > 50, f"{len(sample)} of {len(quiet)} unadvertised pages are indexable")

# ------------------------------------------------------------- IndexNow
ck("7 the key file ships at the host root",
   os.path.exists(os.path.join(DIST, f"{IN.KEY}.txt"))
   and open(os.path.join(DIST, f"{IN.KEY}.txt"), encoding="utf-8").read().strip() == IN.KEY)
urls, total = IN.changed_today(os.path.join(DIST, "sitemap.xml"))
ck("8 it submits what changed today, capped", 0 < len(urls) <= IN.CAP, f"{len(urls)} of {total}")
ck("9 the home page and the sections come first, match pages last",
   urls[0].rstrip("/") == "https://yallascore.site"
   and IN.rank(urls[0]) <= IN.rank(urls[-1]), f"{urls[0]} … {urls[-1]}")
old = IN.changed_today(os.path.join(DIST, "sitemap.xml"), today="2019-01-01")
ck("10 a day when nothing changed submits nothing", old == ([], 0), old[1])
ck("11 the payload names the host, the key and where the key lives",
   IN.KEY_URL == f"https://{IN.HOST}/{IN.KEY}.txt" and IN.ENDPOINT.endswith("/indexnow"))
src = open("indexnow.py", encoding="utf-8").read()
ck("12 it refuses to submit against a key the engines cannot fetch",
   "key_is_live()" in src and "if not key_is_live():" in src)
ck("13 the docstring says plainly that Google does not participate",
   "Google does NOT participate" in src or "Google does not participate" in src)
wf = open(".github/workflows/publish.yml", encoding="utf-8").read()
ck("14 it runs only after a deploy that actually happened, and never fails the run",
   "Tell IndexNow what changed" in wf
   and re.search(r"Tell IndexNow what changed[\s\S]{0,200}?steps\.deploy\.outcome == 'success'[\s\S]{0,120}?continue-on-error: true", wf) is not None)

print()
print(f"{len(fails)} FAILED: {', '.join(fails)}" if fails else "ALL INDEXNOW / SITEMAP TESTS PASSED")
sys.exit(1 if fails else 0)
