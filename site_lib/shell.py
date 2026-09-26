"""The page shell every page shares: <head> (SEO, Open Graph, ads, the
ticker), the footer (+ the live/related scripts), card thumbnails, and
writing pages into dist/ with the lastmod registry the sitemap reads.

TICKER_HTML, KO_SCRIPT and CSS_VER are set by build() on THIS module
(`_shell.TICKER_HTML = ...`) - build_site does not re-export them, so a
stale copy cannot be read by mistake.

Moved verbatim out of build_site.py (2026-09-26, tools/move_names.py):
source and comments exactly as they were there. Edit here; build_site
imports these back under the same names."""
import io
import os
import re
from site_lib.config import ADSENSE_CLIENT, ADSENSE_SLOT, ADSENSE_SLOT_TOP, CF_ANALYTICS_TOKEN, DIST, FB_PAGE_URL, HERE, LOCALE, SHOW_HEADLINES, SHOW_REELS, SHOW_STATS_PAGE, SHOW_VIDEOS, SITE_BASE, SITE_NAME, SITE_TAGLINE, TG_CHANNEL_URL, _src
from site_lib.text import esc, seo_desc, strip_tags


def thumb_url(url):
    """The 640px card copy of one of OUR photos, when it exists on disk.

    Lighthouse (2026-09-22) measured ~3 MB of the 3.9 MB home page as the
    full 1600px article photos rendered inside card slots. shrink_media.py
    writes media/thumbs/<same name> at 640px; every CARD slot goes through
    here, while the article hero, og:image and RSS keep the original.
    Anything not ours passes through untouched: external hotlinks (headline
    cards), the SVG placeholders, and a photo whose thumb is not in this
    checkout yet (same race as resolve_missing_media - the next run heals it;
    in publish.yml shrink_media runs BEFORE the build, so it never happens
    there)."""
    u = str(url or "")
    path = u[len(SITE_BASE):] if u.startswith(SITE_BASE) else u
    if not path.startswith("/media/") or path.lower().endswith(".svg") \
            or path.startswith("/media/thumbs/"):
        return url
    name = path.split("/media/", 1)[1].split("?")[0]
    if not os.path.exists(os.path.join(HERE, "media", "thumbs", name)):
        return url
    return (SITE_BASE if u.startswith(SITE_BASE) else "") + "/media/thumbs/" + name


def adsense_slot():
    """Left-column ad slot: the real AdSense unit when configured, else a placeholder."""
    if ADSENSE_CLIENT and ADSENSE_SLOT:
        return ('<ins class="adsbygoogle ad-unit" style="display:block"'
                f' data-ad-client="{ADSENSE_CLIENT}" data-ad-slot="{ADSENSE_SLOT}"'
                ' data-ad-format="auto" data-full-width-responsive="true"></ins>'
                '<script>(adsbygoogle=window.adsbygoogle||[]).push({});</script>')
    # no placeholder before approval: empty dashed "ad space" frames read as an
    # unfinished site to a reviewer (AdSense low-value rejection, 2026-09-04)
    return ""


def page_head_ad(title_html, hint=""):
    """Page title on the start side, a leaderboard ad on the end side (the free
    left half in RTL). Desktop only - phones already get .ad-top above the page."""
    hint_html = f'<p class="hintline">{hint}</p>' if hint else ""
    return (f'<div class="page-head"><div class="page-head-t">{title_html}{hint_html}</div>'
            f'<div class="head-ad">{adsense_slot()}</div></div>')


def adsense_top_banner():
    """Slim full-width banner shown on MOBILE only, right at the top of every
    page (the classic 320x50-style slot). Real unit when configured, else a
    placeholder so the layout can be judged before AdSense approval."""
    if ADSENSE_CLIENT and ADSENSE_SLOT_TOP:
        inner = ('<ins class="adsbygoogle" style="display:block;height:60px"'
                 f' data-ad-client="{ADSENSE_CLIENT}" data-ad-slot="{ADSENSE_SLOT_TOP}"'
                 ' data-ad-format="horizontal" data-full-width-responsive="true"></ins>'
                 '<script>(adsbygoogle=window.adsbygoogle||[]).push({});</script>')
    else:
        return ""      # nothing (not even the frame) until the real unit exists
    return f'<div class="ad-top">{inner}</div>'


_OG_DIMS = {}
def _og_dims(url):
    """(width, height) of one of OUR images (media/ or assets/ under SITE_BASE),
    (None, None) for anything remote or unreadable. Cached per build."""
    if not url or not url.startswith(SITE_BASE + "/"):
        return (None, None)
    if url in _OG_DIMS:
        return _OG_DIMS[url]
    rel = url[len(SITE_BASE) + 1:].split("?")[0]
    cand = [os.path.join(HERE, rel)]
    if rel.startswith("assets/"):
        cand.append(os.path.join(HERE, "assets-src", rel[len("assets/"):]))
    dims = (None, None)
    for p in cand:
        try:
            from PIL import Image as _PILImage
            with _PILImage.open(p) as im:
                dims = im.size
            break
        except Exception:
            continue
    _OG_DIMS[url] = dims
    return dims


def seo_title(title, limit=62):
    """<title>: drop the « — يلا سكور» brand suffix when the whole thing would
    exceed ~60 chars — Google truncates longer titles and the article headline
    (the part that carries the query words) matters more than the brand,
    which is already in og:site_name and the publisher schema."""
    t = " ".join((title or "").split())
    if len(t) <= limit:
        return t
    for suf in (f" — {SITE_NAME}", f" | {SITE_NAME}", f" - {SITE_NAME}"):
        if t.endswith(suf):
            return t[:-len(suf)]
    return t


def head(title, desc, url, image=None, og_type="website", active="",
         preload_img=None):
    # preload_img: the page's LCP image (the home hero is a CSS background,
    # so the browser only discovers it after the stylesheet - Lighthouse
    # 2026-09-22 measured the discovery delay inside an 8.2s local LCP).
    # Only the LCP image belongs here; preloading more steals its bandwidth.
    og_desc = strip_tags(desc)[:300]
    desc = seo_desc(desc)
    title = seo_title(title)
    # og:image must be a raster — Facebook/Twitter ignore SVG entirely (the
    # homepage once inherited a placeholder SVG from the hero article and FB
    # rendered no preview at all) — and at least 200px. The branded 1200x630
    # banner is both the default and the SVG-placeholder replacement.
    if not image or image.lower().endswith(".svg"):
        image = SITE_BASE + "/assets/og-banner.png"
    img = image
    # og:image:width/height: without them Facebook renders the FIRST share of
    # a URL with NO image (it fetches the picture asynchronously and only later
    # shares get it) — article 371's post came out with an empty image box on
    # 2026-09-04. Known only for our own files (media/, assets/), read once.
    ogw, ogh = _og_dims(img)
    # Tiny images (club crests ~95px on match/team pages) are below Facebook's
    # 200px minimum and look broken in Discover/Twitter cards → use the banner.
    if ogw and ogw < 400:
        img = SITE_BASE + "/assets/og-banner.png"
        ogw, ogh = _og_dims(img)
    og_type_img = "png" if img.lower().endswith(".png") else "jpeg"
    og_dims = (
        f'\n<meta property="og:image:width" content="{ogw}">'
        f'\n<meta property="og:image:height" content="{ogh}">'
        f'\n<meta property="og:image:type" content="image/{og_type_img}">'
    ) if ogw else ""
    preload = (f'\n<link rel="preload" as="image" href="{esc(preload_img)}">'
               if preload_img else "")
    ha = " is-active" if active == "home" else ""
    ma = " is-active" if active == "matches" else ""
    aa = " is-active" if active == "analysis" else ""
    sa = " is-active" if active == "stats" else ""
    stats_tab = ('    <a href="/stats.html" class="navtab' + sa + '">'
                 '<span class="ico">📊</span> إحصائيات<span class="nav-en"> | Stats</span></a>'
                 if SHOW_STATS_PAGE else "")
    va = " is-active" if active == "videos" else ""
    ra = " is-active" if active == "reels" else ""
    vids_tab = (f'\n    <a href="/videos.html" class="navtab{va}"><span class="ico">🎬</span> فيديوهات<span class="nav-en"> | Videos</span></a>'
                if SHOW_VIDEOS else "")
    reels_tab = (f'\n    <a href="/reels.html" class="navtab{ra}"><span class="ico">⚡</span> ريلز<span class="nav-en"> | Reels</span></a>'
                 if SHOW_REELS else "")
    ads_head = (f'<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client={ADSENSE_CLIENT}" crossorigin="anonymous"></script>'
                if ADSENSE_CLIENT else "")
    t = f"""<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<script>try{{window.__livePromise=fetch('/live.json?b='+Math.floor(Date.now()/1e4),{{cache:'no-store'}})}}catch(e){{}}</script>
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{esc(url)}">{preload}
<meta name="robots" content="index, follow, max-image-preview:large, max-snippet:-1, max-video-preview:-1">
<meta name="google-site-verification" content="mMvVRBkeRXu37K-dU3QCrngUUJs9a2FfwpJNX3CHcpk">
<meta property="og:type" content="{og_type}">
<meta property="og:site_name" content="{esc(SITE_NAME)}">
<meta property="og:locale" content="{LOCALE}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(og_desc)}">
<meta property="og:url" content="{esc(url)}">
<meta property="og:image" content="{esc(img)}">{og_dims}
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{esc(title)}">
<meta name="twitter:description" content="{esc(og_desc)}">
<meta name="twitter:image" content="{esc(img)}">
<link rel="alternate" type="application/rss+xml" title="{esc(SITE_NAME)}" href="/feed.xml">
<link rel="icon" type="image/png" sizes="192x192" href="/assets/favicon.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Almarai:wght@300;400;700;800&display=swap">
<link rel="stylesheet" href="/assets/style.css?v={CSS_VER}">
{ads_head}
</head>
<body>
<header class="site-head">
  <div class="head-crowd" aria-hidden="true"></div>
  <div class="wrap head-in">
    <a class="brand" href="/"><img class="ball" src="/assets/favicon.png" alt="" width="30" height="30"> {esc(SITE_NAME)}</a>
  </div>
  {TICKER_HTML}
  <nav class="site-nav"><div class="wrap nav-in">
    <a href="/" class="navtab{ha}"><span class="ico">📰</span> أخبار<span class="nav-en"> | News</span></a>
    <a href="/matches.html" class="navtab{ma}"><span class="ico">⚽</span> المباريات<span class="nav-en"> | Matches</span></a>
    <a href="/analysis.html" class="navtab{aa}"><span class="ico">📈</span> تحليلات<span class="nav-en"> | Analysis</span></a>
{stats_tab}{vids_tab}{reels_tab}
  </div></nav>
</header>
<main class="wrap">
{adsense_top_banner()}
"""
    return t


def cf_beacon():
    """Cloudflare Web Analytics beacon — one deferred script, no cookies, no
    consent banner needed; inert while CF_ANALYTICS_TOKEN is empty."""
    if not CF_ANALYTICS_TOKEN:
        return ""
    return ('<script defer src="https://static.cloudflareinsights.com/beacon.min.js" '
            f"data-cf-beacon='{{\"token\": \"{CF_ANALYTICS_TOKEN}\"}}'></script>")


def foot():
    year = "2026"
    stats_link = ' · <a href="/stats.html">إحصائيات</a>' if SHOW_STATS_PAGE else ""
    heads_link = ' · <a href="/headlines.html">عناوين الصحف</a>' if SHOW_HEADLINES else ""
    vids_link = ' · <a href="/videos.html">فيديوهات</a>' if SHOW_VIDEOS else ""
    reels_link = ' · <a href="/reels.html">ريلز</a>' if SHOW_REELS else ""
    return f"""</main>
<footer class="site-foot"><div class="wrap">
  <p>{esc(SITE_NAME)} — {esc(SITE_TAGLINE)}</p>
  <p class="foot-links"><a href="/">أخبار</a> · <a href="/news.html">كل الأخبار</a>{heads_link} · <a href="/matches.html">المباريات</a> · <a href="/analysis.html">تحليلات وتوقعات</a> · <a href="/predictions.html">سجل التوقعات</a> · <a href="/standings/egypt.html">ترتيب الدوري المصري</a> · <a href="/scorers/egypt.html">هدافو الدوري المصري</a> · <a href="/team/al-ahly.html">أخبار الأهلي</a> · <a href="/team/zamalek.html">أخبار الزمالك</a>{stats_link}{vids_link}{reels_link} · <a href="/about.html">من نحن</a> · <a href="/contact.html">اتصل بنا</a> · <a href="/editorial.html">السياسة التحريرية</a> · <a href="/terms.html">شروط الاستخدام</a> · <a href="/privacy.html">سياسة الخصوصية</a> · <a href="/editors.html">فريق التحرير</a> · <a href="{FB_PAGE_URL}" target="_blank" rel="noopener">فيسبوك</a> · <a href="{TG_CHANNEL_URL}" target="_blank" rel="noopener">تيليجرام</a></p>
  <p class="credit">صور عبر Wikimedia Commons / Unsplash — رخص حرة / المجال العام · صورة جماهير الهيدر: Кирилл Венедиктов، CC BY-SA 3.0 (مُجمّعة ومقصوصة) · صور لاعبي منتخب مصر 2026: Bryan Berlin، CC BY-SA 4.0</p>
  <p class="credit">© {year} {esc(SITE_NAME)}</p>
</div></footer>
{cf_beacon()}</body></html>{KO_SCRIPT}{REL_JS}{LIVE_JS}"""


# Live-scores ticker in the header. Built once per build from matches.json
# (site rebuilds every 30 min, so it stays fresh). Set by build().
TICKER_HTML = ""
CSS_VER = "1"   # cache-buster for /assets/style.css, set from CSS content hash in build()
# window.__koTs = epoch-ms of nearby kickoffs (set by build(), injected in
# foot()) — LIVE_JS uses it to wake its polling right before a match starts
# instead of sleeping through kickoff on the idle 5-minute cadence.
KO_SCRIPT = ""
# Client-side live layer: polls /live.json (edge-cached 15s) and patches
# scores/minute into the ticker + match rows IN PLACE. Matching is by
# normalized Arabic team-name pair; anything unmatched just stays on the
# 15-minute static refresh - the site never depends on this script.
LIVE_JS = _src("snippets/live_js.html")
# sitemap <lastmod> per URL path (set where the page's real change date is
# known: articles = publish time, match pages = kickoff/today). Pages that
# are rebuilt with fresh data every run default to today in the writer;
# static legal pages get none.
_LASTMOD = {}
# The official URL form is EXTENSIONLESS (/news, /a/307, /m/551993): Cloudflare
# Workers assets 307-redirect /x.html -> /x, so .html canonicals/sitemap URLs
# made Google see every URL as a temporary redirect whose target pointed back
# at the redirect (1/500 pages indexed). Files on disk keep their .html names —
# only emitted URLs are normalized here, at the single output choke point.
# Matches internal URLs only: absolute ones starting with SITE_BASE, or
# root-relative ones right after a delimiter ("'>=( or whitespace) so external
# publisher links like https://example.com/foo.html are never touched.
_HTML_URL = re.compile(
    r'(?P<pre>' + re.escape(SITE_BASE) + r'|["\'>=(\s])'
    r'(?P<path>/[A-Za-z0-9_\-/]+)\.html')
def _clean_urls(text):
    return _HTML_URL.sub(lambda m: m.group("pre") + m.group("path"), text)


def write_text(rel, content):
    """A raw file in dist/: no URL normalisation, no .html handling."""
    with io.open(os.path.join(DIST, rel), "w", encoding="utf-8", newline="") as f:
        f.write(content)


def write(rel, content):
    path = os.path.join(DIST, rel)
    if rel.endswith((".html", ".xml")):
        content = _clean_urls(content)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


# client-side relative time ("منذ X") - always accurate to the visitor's clock.
REL_JS = _src("snippets/rel_js.html")
