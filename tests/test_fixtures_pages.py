r"""The season fixtures moved out of /matches (2026-09-20).

    python build_site.py && python tests/test_fixtures_pages.py

/matches was 958 KB of HTML because the whole season of every league sat inside
it, hidden behind the league filter: 2,206 fixture rows and 4,955 crest <img>
tags for a visitor who sees 82 rows. The season now lives at /fixtures/<league>
- ten pages that answer «جدول مباريات <الدوري>» - and /matches keeps the
current round plus a link.

This checks the built site, so it needs a build first. The weight assertion is
the point: it is a regression guard, not a style preference.
"""
import glob, os, re, sys
sys.stdout.reconfigure(encoding="utf-8")
DIST = "dist"

fails = []
def ck(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  [{extra}]" if extra else ""))
    if not cond:
        fails.append(name)

def rd(p):
    return open(p, encoding="utf-8").read()

m = rd(os.path.join(DIST, "matches.html"))
# the scripts at the foot of the page contain the navigator's own source, so
# strip them before asking what the MARKUP contains
m_html = re.sub(r"<script.*?</script>", "", m, flags=re.S)
kb = os.path.getsize(os.path.join(DIST, "matches.html")) / 1024

# ------------------------------------------------------------------ /matches
# BUDGET, not a target. 336 KB right after the season moved out (2026-09-06),
# 452 KB on 2026-09-24 - the growth is data (AFCON qualifiers + Nations League
# joined on 09-21, more rounds played), not a regression in the markup, so the
# line moved to 520 once, on purpose. If it trips again, find what grew
# before moving it: the megabyte came back once through exactly this drift.
ck("1 /matches is no longer a megabyte of HTML", kb < 520, f"{kb:.0f} KB (was 958; budget 520)")
ck("2 the hidden season is gone: a handful of fixture rows, not thousands",
   len(re.findall(r'class="fx"', m)) < 200, len(re.findall(r'class="fx"', m)))
ck("3 and the crest tags went with it",
   m.count("<img") < 1200, f'{m.count("<img")} img tags (was 4,959)')
panels = re.findall(r'<div class="lg-fix rounds-panel.*?(?=<div class="lg-fix rounds-panel|\Z)',
                    m_html, re.S)
ck("4 every league ships ONE round inline",
   panels and all(len(re.findall(r'class="round"', p)) <= 1 for p in panels),
   f"{len(panels)} panels, rounds: {[len(re.findall(chr(34)+'round'+chr(34), p)) for p in panels][:4]}")
ck("5 that round is visible without JS (no navigator to reveal it)",
   panels and all('data-label="الجولة' in p and ' hidden>' not in p.split("</div>")[0]
                  for p in panels[:1]))
ck("6 each panel links to the full season",
   all("/fixtures/" in p for p in panels), sum("/fixtures/" in p for p in panels))
ck("7 the navigator arrows are not shipped where there is one round",
   all("rn-next" not in p for p in panels))

# ------------------------------------------------------------- the new pages
pages = sorted(glob.glob(f"{DIST}/fixtures/*.html"))
ck("8 a page per league with a season", len(pages) >= 8, len(pages))
sm = rd(os.path.join(DIST, "sitemap.xml"))
# «all rounds» means all the rounds THE DATA HOLDS, not a fixed floor: the
# hardcoded >= 5 broke the day the national-team competitions arrived
# (AFCON qualifiers legitimately had 2 windows, the Nations League 4 —
# 2026-09-22). A domestic league still shows its full season because the
# data holds the full season.
import json as _json                                     # noqa: E402
import sys as _sys                                       # noqa: E402
_sys.path.insert(0, os.getcwd())
import build_site as _B                                  # noqa: E402
_slug2comp = {v: k for k, v in _B.COMP_SLUG.items()}
_fxdoc = _json.load(open(os.path.join(os.getcwd(), "data", "fixtures.json"),
                         encoding="utf-8"))
_fxrounds = {f["competition"]: len(f.get("rounds") or [])
             for f in _fxdoc["results"][0]["items"]}
for f in pages:
    slug = os.path.basename(f)[:-5]
    t = rd(f)
    name = f"/fixtures/{slug}"
    want = _fxrounds.get(_slug2comp.get(slug), 0)
    got = len(re.findall(r'class="round"', t))
    ok = ("rounds-panel" in t and "rn-next" in t
          and got == want and want >= 2
          and f'<link rel="canonical" href="https://yallascore.site/fixtures/{slug}"' in t
          and "BreadcrumbList" in t and "<h1" in t)
    ck(f"9 {name}: all rounds + navigator + canonical + breadcrumbs", ok,
       f"{got} rounds on the page, {want} in the data")
    ck(f"10 {name} is in the sitemap and indexable",
       f"<loc>https://yallascore.site/fixtures/{slug}</loc>" in sm
       and 'content="noindex"' not in t)

# the title has to answer the query, not describe the site
t0 = rd(pages[0])
ck("11 the title is the query a reader types",
   re.search(r"<title>جدول مباريات .+ — كل الجولات", t0) is not None,
   re.search(r"<title>(.*?)</title>", t0).group(1)[:60])
ck("12 the page says how many rounds and matches it holds, in words",
   re.search(r"<b>\d+</b> جولة و<b>\d+</b> مباراة", t0) is not None)

# ------------------------------------------------------------ no dead links
have = set()
for p in glob.glob(f"{DIST}/**/*.html", recursive=True):
    u = "/" + os.path.relpath(p, DIST).replace("\\", "/")
    have.add(u); have.add(u[:-5])
dead = [h for h in set(re.findall(r'href="(/fixtures/[^"#?]*)"', m))
        if h not in have and h + ".html" not in have]
ck("13 every /fixtures link on /matches resolves", not dead, dead)

print()
print(f"{len(fails)} FAILED: {', '.join(fails)}" if fails else "ALL FIXTURES-PAGE TESTS PASSED")
sys.exit(1 if fails else 0)
