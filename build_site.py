#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Yalla Score - static-site generator.
Reads data/*.json (exported from the APEX DB via SQLcl `set sqlformat json`)
and writes a fully SEO-optimized static site into dist/.

Deploy dist/ to any free static host (Netlify Drop, Cloudflare Pages, GitHub
Pages) - no credit card needed. Google indexes static HTML very well.

IMPORTANT: set SITE_BASE to your final public URL before the last build,
so canonical/Open-Graph/sitemap URLs are correct. You can rebuild anytime.
"""
import base64, json, os, re, html, shutil, datetime, hashlib, io
import analysis as AN     # تحليلات: strength model, predictions, accuracy, player insights
import store              # prediction log (D1 when configured, else the json file)
import results_archive as RA   # every finished match of the season, frozen once complete

# ---------------------------------------------------------------- config
SITE_BASE = "https://yallascore.site"  # custom domain on the Cloudflare Worker (since 2026-08-03)
SITE_NAME = "يلا سكور"
SITE_TAGLINE = "أخبار ونتائج كرة القدم"
SITE_DESC = "يلا سكور — أخبار كرة القدم ونتائج المباريات ومواعيد البطولات بالعربية."
LOCALE = "ar_AR"
BUILD_DATE = os.environ.get("BUILD_DATE", "")  # pass a date; else today isn't used in content

# --- Google AdSense (fill these AFTER AdSense approves your site, then rebuild) ---
# 1) ADSENSE_CLIENT: your publisher id, e.g. "ca-pub-1234567890123456"
# 2) ADSENSE_SLOT:   the ad-unit slot id from AdSense, e.g. "1234567890"
# While either is empty, a tidy "مساحة إعلانية" placeholder is shown instead.
# NOTE: AdSense usually requires your OWN domain (a *.workers.dev subdomain is
# typically not approved) + a Privacy Policy page.
ADSENSE_CLIENT = "ca-pub-3080285229612776"
ADSENSE_SLOT = ""
ADSENSE_SLOT_TOP = ""   # mobile top-banner unit id (leave empty for placeholder)

# Optional contact email shown on the Privacy Policy page (leave "" to omit).
CONTACT_EMAIL = "yallascore.eg@gmail.com"
# Facebook page «يلا سكور» — numeric id URL always resolves; swap for the
# vanity URL (facebook.com/<username>) once the page has one.
FB_PAGE_URL = "https://www.facebook.com/104238901487012"
# the owned Telegram channel (created by the user 2026-09-22; tg_post.py
# posts every new article to it after deploy, same machinery as Facebook)
TG_CHANNEL_URL = "https://t.me/yallascore"
# Editorial identity shown on /editors.html and in every article byline.
EDITOR_NAME = "مصطفى عبدالسلام"
EDITOR_ROLE = "مدير التحرير"
EDITOR_EMAIL = CONTACT_EMAIL
# The bylines Google reads as a faceless publisher. An article carrying one of
# these is signed by the named editor instead (2026-09-15): a person who can be
# looked up, mailed and held responsible is the E-E-A-T signal a generic «فريق
# التحرير» never gives, and it was one of the two decisions left open after the
# content rejection. Rendering-level on purpose — the 466 stored rows are not
# rewritten, so this is one constant away from being undone.
GENERIC_BYLINES = (SITE_NAME, "فريق التحرير", "فريق يلا سكور", "")

def byline(a):
    """The name to print (and to put in schema) for one article."""
    return EDITOR_NAME if (a.get("author") or "") in GENERIC_BYLINES else a["author"]

# The competitions whose match data comes from 365scores; everything else
# we cover gets its table and season numbers from football-data.org (match
# details and goals come from 365scores for all of them). This mirrors
# fetch_data.S365_LEAGUES, which cannot be imported here - fetch_data imports
# THIS module.
S365_COMPETITIONS = ("Egyptian Premier League", "Turkish Super Lig",
                     "Saudi Pro League", "CAF Champions League",
                     "Africa Cup of Nations Qualification",
                     "UEFA Nations League")

def match_data_sources(a, comp):
    """The data credit a match preview/report carries when its writer left the
    `sources` field empty.

    The match-article prompt asks for it, yet 23 of the pieces published since
    2026-09-05 shipped with no sources at all - and an article with no source
    line, under an editorial policy that promises one, is exactly the
    contradiction a reviewer reads as a broken promise (ChatGPT's site audit,
    2026-09-16, found it on /a/397). So the RENDERER guarantees the line, the
    way byline() guarantees the signature: nothing stored is rewritten, and a
    writer that does supply real sources still wins - this only fills a void.

    Honest by competition: 365scores is always named because every match page
    is built from its game data; football-data.org is added only for the
    competitions we actually read from it.
    """
    url = f"{SITE_BASE}/m/{a['match_id']}.html" if a.get("match_id") else None
    def entry(name, note):
        return {"name": name, "url": url, "note": note} if url else {"name": name, "note": note}
    out = [entry("بيانات المباريات — 365scores",
                 "النتائج والتشكيلات وأهداف المباريات والمواجهات المباشرة")]
    if comp and comp not in S365_COMPETITIONS:
        out.append(entry("football-data.org", "ترتيب الدوري وأرقام الفريقين هذا الموسم"))
    return out
# Cloudflare Web Analytics (cookie-less page views / referrers / top pages).
# Paste the 32-char token from Cloudflare -> Analytics & Logs -> Web Analytics
# -> Add a site (manual install). Empty = no beacon in the pages.
CF_ANALYTICS_TOKEN = ""

# Feature switches. Flip to True to bring a section back (nav tab, footer link,
# home teaser, its page, and sitemap entry all follow this flag automatically).
SHOW_VIDEOS = False
SHOW_REELS = False
# aggregated press headlines OFF for the AdSense review (2026-08-30, user
# decision): copied titles + outbound links are the site's weakest
# originality signal. The home slot shows a deeper grid of OUR articles
# instead. fetch_data.py still refreshes headlines.json (editorial tasks
# read the RSS separately) — this flag only gates the DISPLAY.
SHOW_HEADLINES = False
# stats live inside the /matches league view now (2026-08-19, user request);
# the standalone page still builds (old links don't 404) but is unlinked,
# out of the sitemap, and noindexed. Flip to True to bring it back.
SHOW_STATS_PAGE = False

# Generic fallback thumbnails (our own SVGs in media/, no licensing worries)
# for headline cards whose source page offers no og:image.
PLACEHOLDER_IMGS = ["/media/ph-pitch.svg", "/media/ph-ball.svg"]

def resolve_missing_media(articles, media_dir=None, base=None):
    """An article whose image_url points at OUR /media/ but whose file is not in
    this checkout gets a placeholder FOR THIS BUILD (and no credit line, since
    the placeholder needs none). Returns the list of missing file names.

    Why (2026-09-13, article 497 «طرابزون سبور يستبعد جوارديولا»): D1 is written
    by article_put.py BEFORE the image file reaches git, so a 15-minute refresh
    run that starts inside that window builds the article from D1 with an image
    its checkout does not have -> a blank card on the live site until the
    article's own run deploys ~10 min later. Resolving it here, once, covers
    every render site (home blocks, article page, club pages, RSS, OG image);
    the next build has the file and heals itself without anyone touching it."""
    import hashlib
    media_dir = media_dir or os.path.join(HERE, "media")
    base = SITE_BASE if base is None else base
    missing = []
    for a in articles or []:
        u = a.get("image_url") or ""
        if "/media/" not in u:
            continue
        name = u.split("/media/", 1)[1].split("?")[0]
        if not name or os.path.exists(os.path.join(media_dir, name)):
            continue
        missing.append(name)
        pick = int(hashlib.md5(str(a.get("article_id", "")).encode()).hexdigest(), 16) % len(PLACEHOLDER_IMGS)
        a["_image_missing"] = u
        a["image_url"] = base + PLACEHOLDER_IMGS[pick]
        a["image_credit"] = ""
    return missing


HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
DIST = os.path.join(HERE, "dist")

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

def load(name):
    """Load a SQLcl `set sqlformat json` export -> list of row dicts (tolerant)."""
    p = os.path.join(DATA, name)
    if not os.path.exists(p):
        return []
    try:
        with open(p, encoding="utf-8") as f:
            doc = json.load(f)
        return doc["results"][0]["items"]
    except Exception as e:
        print("  ! could not parse %s (%s) - skipping" % (name, e))
        return []

def articles_current():
    """(articles, source label) - the committed export when it is provably
    current, the store otherwise.

    A full store.article_all() scans the articles table plus three child
    tables on EVERY build (~48-96 runs/day), and D1's free tier bills rows
    scanned - the read quota ran out on 2026-09-16, 09-19 and 09-20. So the
    build first reads the ONE-ROW change marker every article write replaces
    (store.articles_sig) and, when it equals the sig recorded inside the
    committed export, uses the export as-is. An admin-page edit bumps the
    marker without rewriting the export, so those builds pull the full set
    until the next article_put/d1-admin export re-syncs the file - correct,
    just briefly more expensive. ARTICLES_FULL=1 is the escape hatch if a
    writer is ever suspected of forgetting the bump."""
    if store.backend() != "json" and not os.environ.get("ARTICLES_FULL"):
        sig = store.articles_sig()          # one row read
        if sig:
            try:
                with open(os.path.join(DATA, "articles.json"), encoding="utf-8") as f:
                    doc = json.load(f)
                if doc.get("sig") == sig:
                    return (doc["results"][0]["items"],
                            "the committed export (sig match, 1 row read)")
            except Exception:                               # noqa: BLE001
                pass                # unreadable export -> pull everything
    return store.article_all(), f"the {store.backend()} store"

def esc(s):
    return html.escape(s or "", quote=True)

def strip_tags(s):
    import re
    return re.sub(r"<[^>]+>", "", s or "").strip()

def strip_src(title, source):
    """Drop a trailing ' - <source>' suffix from aggregated headlines (like the app)."""
    t = (title or "").strip()
    if source and t.endswith(" - " + source):
        t = t[: -(len(source) + 3)].strip()
    return t

REF_TODAY = datetime.date.today().isoformat()  # machine clock (the sandbox is set to Jul 2026)
_AR_DAYS = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]  # weekday() 0..6
_AR_MONTHS = ["", "يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو",
              "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]
def fmt_day(d):
    try:
        dt = datetime.date.fromisoformat(d)
        return f"{_AR_DAYS[dt.weekday()]} {dt.day} {_AR_MONTHS[dt.month]} {dt.year}"
    except Exception:
        return d

def _ar_ago(n, one, two, few):
    """Arabic 'منذ N <unit>' with the correct plural form (1 / 2 / 3-10 / 11+)."""
    if n == 1:
        return f"منذ {one}"
    if n == 2:
        return f"منذ {two}"
    if 3 <= n <= 10:
        return f"منذ {n} {few}"
    return f"منذ {n} {one}"

def rel_ar(iso):
    """Build-time Arabic 'منذ X' (JS refines it in the visitor's browser)."""
    try:
        dt = datetime.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except Exception:
        return ""
    now = datetime.datetime.now(dt.tzinfo) if dt.tzinfo else datetime.datetime.now()
    s = int((now - dt).total_seconds())
    if s < 0:
        s = 0
    if s < 60:
        return "منذ لحظات"
    m = s // 60
    if m < 60:
        return _ar_ago(m, "دقيقة", "دقيقتين", "دقائق")
    h = m // 60
    if h < 24:
        return _ar_ago(h, "ساعة", "ساعتين", "ساعات")
    return _ar_ago(h // 24, "يوم", "يومين", "أيام")

def art_reltime(a):
    """<time> element showing 'منذ X' for an article carrying pub_ts (full ISO
    timestamp, present on articles published since 2026-08-31). Older articles
    have only pub_date -> returns '' and the caller shows what it always did."""
    ts = a.get("pub_ts") or ""
    txt = rel_ar(ts) if ts else ""
    if not txt:
        return ""
    return f'<time class="reltime" datetime="{esc(ts)}">{esc(txt)}</time>'

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

def seo_desc(desc, limit=155):
    """Meta description: Google shows ~155-160 chars; cut at a word boundary
    so the snippet never ends mid-word. (og:description keeps the long form.)"""
    d = " ".join(strip_tags(desc).split())
    if len(d) <= limit:
        return d
    cut = d[:limit].rsplit(" ", 1)[0].rstrip(" ،,.:;-—")
    return cut + "…"

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

def jsonld(obj):
    return '<script type="application/ld+json">' + json.dumps(obj, ensure_ascii=False) + '</script>'

# Live-scores ticker in the header. Built once per build from matches.json
# (site rebuilds every 30 min, so it stays fresh). Set by build().
TICKER_HTML = ""
CSS_VER = "1"   # cache-buster for /assets/style.css, set from CSS content hash in build()
# Articles shorter than this are UNLISTED: the page stays online at the same
# URL, but it is noindexed, left out of the sitemap / news sitemap / RSS, and
# dropped from every listing on the site (home blocks, /news archives, club
# pages, match pages, related-article blocks).
#
# Raised 200 -> 300 on 2026-09-06 (user decision). He asked whether to DELETE
# the old archive instead; the numbers said no: 60 of these articles have a
# live Facebook post pointing at them and 35 are linked from another article,
# so deleting breaks our main traffic channel — while buying nothing back,
# since Search Console had 499/500 of them as "discovered, not indexed" anyway.
# Unlisting shows Google and a browsing reviewer exactly what deletion would,
# keeps the URL working for anyone arriving from an old post, and is reversible.
# 294 of 355 articles are under the new bar; upgrade-articles.yml rewrites 5/day
# to the 500-700-word standard and each one crosses back on its own.
ARTICLE_MIN_WORDS = 300

def article_words(a):
    return len(strip_tags(a.get("body") or "").split())

def is_thin(a):
    return article_words(a) < ARTICLE_MIN_WORDS
# window.__koTs = epoch-ms of nearby kickoffs (set by build(), injected in
# foot()) — LIVE_JS uses it to wake its polling right before a match starts
# instead of sleeping through kickoff on the idle 5-minute cadence.
KO_SCRIPT = ""

# ---- crest mirroring ---------------------------------------------------
# football-data's crest host has had TLS/outage problems (2026-07-27: broken
# certificate chain -> every badge vanished). Mirror each crest into
# assets/crests/ once and serve it from our own domain; keep a cache next to
# the sources so rebuilds don't re-download, and fall back to the remote URL
# if a download ever fails.
CRESTS_CACHE = os.path.join(HERE, "assets-src", "crests")
_CREST_MAP = {}          # remote url -> "/assets/crests/<file>"

def _crest_name(url):
    ext = ".png"
    for e in (".png", ".svg", ".jpg", ".jpeg", ".gif", ".webp"):
        if url.lower().split("?")[0].endswith(e):
            ext = e
            break
    return hashlib.md5(url.encode("utf-8")).hexdigest()[:16] + ext

_CREST_FAILS = [0]       # give up quickly when the crest host is unreachable
_CREST_FAIL_LIMIT = 3

def local_crest(url):
    """Return a site-local path for a remote crest (downloading it if needed).
    Falls back to the original URL when the download isn't possible."""
    if not url or not url.startswith("http"):
        return url
    if url in _CREST_MAP:
        return _CREST_MAP[url]
    name = _crest_name(url)
    cached = os.path.join(CRESTS_CACHE, name)
    if not os.path.exists(cached):
        if _CREST_FAILS[0] >= _CREST_FAIL_LIMIT:
            _CREST_MAP[url] = url            # host looks down; stop hammering it
            return url
        try:
            import urllib.request, ssl
            os.makedirs(CRESTS_CACHE, exist_ok=True)
            req = urllib.request.Request(url, headers={"User-Agent": "yalla-score/1.0"})
            try:
                with urllib.request.urlopen(req, timeout=8) as r:
                    data = r.read()
            except Exception:
                # some crest hosts ship a broken cert chain; we're only fetching
                # public logo images, so retry without verification rather than
                # leaving the site with no badges at all
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                with urllib.request.urlopen(req, timeout=8, context=ctx) as r:
                    data = r.read()
            if not data:
                raise ValueError("empty")
            with open(cached, "wb") as f:
                f.write(data)
        except Exception as e:
            _CREST_FAILS[0] += 1
            if _CREST_FAILS[0] <= _CREST_FAIL_LIMIT:
                print(f"  ! crest download failed ({url}): {e}")
                if _CREST_FAILS[0] == _CREST_FAIL_LIMIT:
                    print("  ! crest host unreachable - using remote URLs for the rest")
            _CREST_MAP[url] = url            # keep remote url as fallback
            return url
    _CREST_MAP[url] = "/assets/crests/" + name
    return _CREST_MAP[url]

# The header ticker shows ONLY these clubs' matches (user pick 2026-08-08).
# Tokens are substring-matched against football-data team names, so keep them
# unambiguous — "FC Barcelona", NOT "Barcelona" (that would also match
# "RCD Espanyol de Barcelona").
# (token, competition-or-None): 365scores leagues use native Arabic names,
# and "الأهلي" alone is AMBIGUOUS since the Saudi league joined (Saudi
# Al-Ahli is also "الأهلي") - so Arabic tokens are scoped to their league.
# URL slugs for the per-league standings/scorers landing pages
# (/standings/<slug>.html, /scorers/<slug>.html). Keys must match the
# competition names as they appear in standings.json / scorers.json.
COMP_SLUG = {
    "Egyptian Premier League": "egypt",
    "Premier League": "england",
    "Primera Division": "spain",
    "Serie A": "italy",
    "Bundesliga": "germany",
    "Ligue 1": "france",
    "Turkish Super Lig": "turkey",
    "Saudi Pro League": "saudi",
    "UEFA Champions League": "champions-league",
    "CAF Champions League": "caf-champions-league",
    "Africa Cup of Nations Qualification": "afcon-qualifiers",
    "UEFA Nations League": "nations-league",
}

# MENA broadcast rights per competition — feeds the «القنوات الناقلة» block
# on /m/ pages. ONLY entries verified for the current season belong here
# (firm site rule: never show possibly-wrong data). A missing league gets an
# honest "لم تتوفر معلومات القناة" line instead. Per-match m["channel"]
# (if a data source ever provides it) overrides this map.
COMP_TV = {
    "Egyptian Premier League": "أون سبورت (OnTime Sports)",
    "Premier League": "beIN Sports",
    "Primera Division": "beIN Sports",
    "Ligue 1": "beIN Sports",
    "UEFA Champions League": "beIN Sports",
    "CAF Champions League": "beIN Sports",     # confirmed by the user 2026-09-02
    # Serie A / Bundesliga / Turkish / Saudi: rights unverified — add when confirmed.
}

# a scope is None (any competition), one competition name, or a tuple of
# names — the Egyptian clubs must count in Africa too (CAF CL, 2026-09-02),
# while bare "الأهلي" must still never match Saudi Al-Ahli
EGY_SCOPE = ("Egyptian Premier League", "CAF Champions League")

def _in_scope(scope, comp):
    if scope is None:
        return True
    return comp in scope if isinstance(scope, tuple) else comp == scope

TICKER_TEAMS = [
    ("Real Madrid", None), ("FC Barcelona", None), ("Manchester United", None),
    ("Manchester City", None), ("Arsenal FC", None), ("Liverpool FC", None),
    ("Chelsea FC", None),
    ("الأهلي", EGY_SCOPE),
    ("الزمالك", EGY_SCOPE),
    ("بيراميدز", EGY_SCOPE),
    ("طرابزون سبور", "Turkish Super Lig"),
]

def _is_ticker_team(m):
    ha = (m.get("home") or "") + "|" + (m.get("away") or "")
    comp = m.get("competition") or ""
    return any(t in ha and _in_scope(c, comp) for t, c in TICKER_TEAMS)

# Evergreen club pages (/team/<slug>) — one per curated club, targeting
# "أخبار الأهلي اليوم" / "مباريات الزمالك القادمة" query families.
# match_tokens follow the TICKER_TEAMS convention: (substring token,
# competition-scope-or-None) — FD English tokens for European clubs
# ("FC Barcelona" not "Barcelona": Espanyol collision), Arabic clubs scoped
# to their league (bare "الأهلي" also matches Saudi Al-Ahli). news_tokens
# are searched in article title+summary; news_excl vetoes false positives.
TEAM_PAGES = [
    {"slug": "al-ahly", "name": "الأهلي", "league": "Egyptian Premier League",
     "match_tokens": [("الأهلي", EGY_SCOPE)],
     "news_tokens": ["الأهلي"],
     "news_excl": ["الأهلي السعودي", "أهلي جدة", "شباب الأهلي دبي", "شباب أهلي دبي"]},
    {"slug": "zamalek", "name": "الزمالك", "league": "Egyptian Premier League",
     "match_tokens": [("الزمالك", EGY_SCOPE)],
     "news_tokens": ["الزمالك"]},
    {"slug": "pyramids", "name": "بيراميدز", "league": "Egyptian Premier League",
     "match_tokens": [("بيراميدز", EGY_SCOPE)],
     "news_tokens": ["بيراميدز"]},
    {"slug": "real-madrid", "name": "ريال مدريد", "league": "Primera Division",
     "match_tokens": [("Real Madrid", None)], "news_tokens": ["ريال مدريد"]},
    {"slug": "barcelona", "name": "برشلونة", "league": "Primera Division",
     "match_tokens": [("FC Barcelona", None)], "news_tokens": ["برشلونة"]},
    {"slug": "man-united", "name": "مانشستر يونايتد", "league": "Premier League",
     "match_tokens": [("Manchester United", None)],
     "news_tokens": ["مانشستر يونايتد"]},
    {"slug": "man-city", "name": "مانشستر سيتي", "league": "Premier League",
     "match_tokens": [("Manchester City", None)],
     "news_tokens": ["مانشستر سيتي"]},
    {"slug": "arsenal", "name": "أرسنال", "league": "Premier League",
     "match_tokens": [("Arsenal FC", None)], "news_tokens": ["أرسنال", "آرسنال"]},
    {"slug": "liverpool", "name": "ليفربول", "league": "Premier League",
     "match_tokens": [("Liverpool FC", None)], "news_tokens": ["ليفربول"]},
    {"slug": "chelsea", "name": "تشيلسي", "league": "Premier League",
     "match_tokens": [("Chelsea FC", None)], "news_tokens": ["تشيلسي"]},
    {"slug": "trabzonspor", "name": "طرابزون سبور", "league": "Turkish Super Lig",
     "match_tokens": [("طرابزون سبور", "Turkish Super Lig")],
     "news_tokens": ["طرابزون", "محمد صلاح"]},
]

def _team_match(tp, m):
    """Does match m involve club tp? Same token+scope rule as the ticker."""
    ha = (m.get("home") or "") + "|" + (m.get("away") or "")
    comp = m.get("competition") or ""
    return any(t in ha and _in_scope(c, comp)
               for t, c in tp["match_tokens"])

def _team_news(tp, a):
    """Does article a mention club tp? title+summary, with exclusions."""
    txt = (a.get("title") or "") + " " + (a.get("summary") or "")
    if any(x in txt for x in tp.get("news_excl", [])):
        return False
    return any(t in txt for t in tp["news_tokens"])

def _tk_date(kick):
    """Short Arabic date chip: اليوم / أمس / غدًا / dd/mm."""
    try:
        d = datetime.date.fromisoformat(kick)
        t = datetime.date.fromisoformat(REF_TODAY)
    except Exception:
        return kick or ""
    delta = (d - t).days
    if delta == 0:
        return "اليوم"
    if delta == -1:
        return "أمس"
    if delta == 1:
        return "غدًا"
    return f"{d.day:02d}/{d.month:02d}"

# Arabic display names for football-data's Latin team names (365scores
# leagues arrive Arabic-native). Unmapped names fall through unchanged.
AR_TEAM = {
    "1. FC Köln": "كولن", "1. FC Union Berlin": "يونيون برلين",
    "1. FSV Mainz 05": "ماينز 05", "AC Milan": "ميلان", "AC Monza": "مونزا",
    "ACF Fiorentina": "فيورنتينا", "AFC Ajax": "أياكس",
    "AFC Bournemouth": "بورنموث", "AJ Auxerre": "أوكسير",
    "AS Monaco FC": "موناكو", "AS Roma": "روما", "Angers SCO": "أنجيه",
    "Arsenal FC": "أرسنال", "Aston Villa FC": "أستون فيلا",
    "Atalanta BC": "أتالانتا", "Athletic Club": "أتلتيك بلباو",
    "Bayer 04 Leverkusen": "باير ليفركوزن", "Bologna FC 1909": "بولونيا",
    "Borussia Dortmund": "بوروسيا دورتموند",
    "Borussia Mönchengladbach": "بوروسيا مونشنجلادباخ",
    "Brentford FC": "برينتفورد", "Brighton & Hove Albion FC": "برايتون",
    "CA Osasuna": "أوساسونا", "Cagliari Calcio": "كالياري",
    "Chelsea FC": "تشيلسي", "Club Atlético de Madrid": "أتلتيكو مدريد",
    "Club Brugge KV": "كلوب بروج", "Como 1907": "كومو",
    "Coventry City FC": "كوفنتري سيتي", "Crystal Palace FC": "كريستال بالاس",
    "Deportivo Alavés": "ألافيس", "ES Troyes AC": "تروا",
    "Eintracht Frankfurt": "آينتراخت فرانكفورت", "Elche CF": "إلتشي",
    "Everton FC": "إيفرتون", "FC Augsburg": "أوغسبورغ",
    "FC Barcelona": "برشلونة", "FC Bayern München": "بايرن ميونخ",
    "FC Internazionale Milano": "إنتر ميلان", "FC København": "كوبنهاجن",
    "FC Lorient": "لوريان", "FC Schalke 04": "شالكه",
    "FK Bodø/Glimt": "بودو جليمت", "FK Kairat": "كايرات",
    "Frosinone Calcio": "فروزينوني", "Fulham FC": "فولهام",
    "Galatasaray SK": "جالطة سراي", "Genoa CFC": "جنوى",
    "Getafe CF": "خيتافي", "Hamburger SV": "هامبورج",
    "Hull City AFC": "هال سيتي", "Ipswich Town FC": "إبسويتش تاون",
    "Juventus FC": "يوفنتوس", "Le Havre AC": "لو آفر",
    "Le Mans FC": "لومان", "Leeds United FC": "ليدز يونايتد",
    "Levante UD": "ليفانتي", "Lille OSC": "ليل", "Liverpool FC": "ليفربول",
    "Manchester City FC": "مانشستر سيتي",
    "Manchester United FC": "مانشستر يونايتد", "Málaga CF": "مالقا",
    "Newcastle United FC": "نيوكاسل يونايتد",
    "Nottingham Forest FC": "نوتنجهام فورست", "OGC Nice": "نيس",
    "Olympique Lyonnais": "أولمبيك ليون", "Olympique de Marseille": "أولمبيك مارسيليا",
    "PAE Olympiakos SFP": "أولمبياكوس", "PSV": "آيندهوفن",
    "Paphos FC": "بافوس", "Paris FC": "باريس أف.سي.",
    "Paris Saint-Germain FC": "باريس سان جيرمان",
    "Parma Calcio 1913": "بارما", "Qarabağ Ağdam FK": "قره باغ",
    "RB Leipzig": "لايبزيج", "RC Celta de Vigo": "سيلتا فيجو",
    "RC Deportivo La Coruña": "ديبورتيفو لاكورونيا",
    "RC Strasbourg Alsace": "ستراسبورج",
    "RCD Espanyol de Barcelona": "إسبانيول",
    "Racing Club de Lens": "لانس",
    "Rayo Vallecano de Madrid": "رايو فاييكانو",
    "Real Betis Balompié": "ريال بيتيس", "Real Madrid CF": "ريال مدريد",
    "Real Racing Club de Santander": "راسينج سانتاندير",
    "Real Sociedad de Fútbol": "ريال سوسيداد",
    "Royale Union Saint-Gilloise": "يونيون سان جيلواز",
    "SC Freiburg": "فرايبورج", "SC Paderborn 07": "بادربورن",
    "SK Slavia Praha": "سلافيا براج", "SS Lazio": "لاتسيو",
    "SSC Napoli": "نابولي", "SV 07 Elversberg": "إلفيرسبيرغ",
    "SV Werder Bremen": "فيردر بريمن", "Sevilla FC": "إشبيلية",
    "Sport Lisboa e Benfica": "بنفيكا",
    "Sporting Clube de Portugal": "سبورتينج لشبونة",
    "Stade Brestois 29": "بريست", "Stade Rennais FC 1901": "ستاد رين",
    "Sunderland AFC": "سندرلاند", "TSG 1899 Hoffenheim": "هوفنهايم",
    "Torino FC": "تورينو", "Tottenham Hotspur FC": "توتنهام هوتسبر",
    "Toulouse FC": "تولوز", "US Lecce": "ليتشي",
    "US Sassuolo Calcio": "ساسولو", "Udinese Calcio": "أودينيزي",
    "Valencia CF": "فالنسيا", "Venezia FC": "فينيزيا",
    "VfB Stuttgart": "شتوتجارت", "Villarreal CF": "فياريال",
}

def ar_team(name):
    return AR_TEAM.get(name or "", name or "")

def make_ticker(matches):
    """Header ticker: ONLY the hand-picked TICKER_TEAMS clubs — LIVE first,
    then today's, then next upcoming + latest finished, each non-today item
    carrying a short date chip. Returns "" when there's nothing to show."""
    if not matches:
        return ""
    picked = [m for m in matches
              if _is_ticker_team(m) and (m.get("status") or "") != "POSTPONED"]
    live = [m for m in picked if (m.get("status") or "") == "LIVE"]
    todays = [m for m in picked
              if m.get("kickoff") == REF_TODAY and (m.get("status") or "") != "LIVE"]
    rest = [m for m in picked if m not in live and m not in todays]

    def stale(m):
        """FINISHED match that kicked off >24h ago — user rule (2026-08-23):
        a day-old result has no place in the ticker. Missing koff_time counts
        from midnight (conservative: drops earlier rather than lingering)."""
        try:
            from zoneinfo import ZoneInfo
            cairo = ZoneInfo("Africa/Cairo")
            ko = datetime.datetime.fromisoformat(
                f"{m.get('kickoff')}T{m.get('koff_time') or '00:00'}:00"
            ).replace(tzinfo=cairo)
            return (datetime.datetime.now(cairo) - ko).total_seconds() > 86400
        except Exception:
            return False

    fin = sorted((m for m in rest if m.get("status") == "FINISHED"
                  and not stale(m)),
                 key=lambda m: (m.get("kickoff") or "", m.get("koff_time") or ""),
                 reverse=True)
    up = sorted((m for m in rest if m.get("status") == "UPCOMING"),
                key=lambda m: (m.get("kickoff") or "", m.get("koff_time") or ""))

    def one_per_team(ms):
        """Keep only the first match per picked club (nearest upcoming /
        latest finished) - a club must not appear once per future fixture."""
        seen, kept = set(), []
        for m in ms:
            ha = (m.get("home") or "") + "|" + (m.get("away") or "")
            comp = m.get("competition") or ""
            # _in_scope, NOT c == comp: Egyptian clubs carry a TUPLE scope
            # (EGY_SCOPE) so == never matched and Zamalek showed once per
            # fixture (2026-09-03 screenshot: CAF 04/09 + EPL 08/09 both)
            teams = [t for t, c in TICKER_TEAMS
                     if t in ha and _in_scope(c, comp)]
            if teams and all(t in seen for t in teams):
                continue
            seen.update(teams)
            kept.append(m)
        return kept

    # ONE match per curated club across the WHOLE pool, priority live > today
    # > next upcoming > latest finished (user rule 2026-09-03: a club must
    # never appear twice — deduping only `up` left Ahly today + Ahly next)
    pool = one_per_team(live + todays + up + fin)[:14]
    if not pool:
        return ""
    sc = lambda v: "-" if v is None else v
    its = []
    for m in pool:
        st = m.get("status")
        hb = (f'<img class="tk-b" src="{esc(local_crest(m.get("home_badge")))}" alt="" loading="lazy">'
              if m.get("home_badge") else "")
        ab = (f'<img class="tk-b" src="{esc(local_crest(m.get("away_badge")))}" alt="" loading="lazy">'
              if m.get("away_badge") else "")
        if st == "LIVE":
            # NEVER bake a live score into static HTML - it is up to 15 min
            # stale and reads as WRONG data (user rule 2026-08-31). Dashes
            # until LIVE_JS paints the real score seconds after load.
            mid = score_pill(None, None, "tk-s tk-live") + '<span class="tk-dot"></span>'
        elif st == "FINISHED":
            mid = score_pill(m.get("home_score"), m.get("away_score"), "tk-s")
        else:
            mid = f'<span class="tk-t">{esc(m.get("koff_time") or "")}</span>'
        # date chip on every non-live item, today's included (user request
        # 2026-09-03: «اليوم» next to today's matches); live rows keep the dot
        day = ("" if st == "LIVE"
               else f'<span class="tk-d">{esc(_tk_date(m.get("kickoff")))}</span>')
        its.append(f'<span class="tk-item" data-lv data-h="{esc(ar_team(m.get("home")))}" data-a="{esc(ar_team(m.get("away")))}">{day}{hb}<bdi>{esc(ar_team(m.get("home")))}</bdi> <span class="tk-mid">{mid}</span> <bdi>{esc(ar_team(m.get("away")))}</bdi>{ab}</span>')
    seq = "".join(its)
    return ('<a class="ticker" href="/matches.html" aria-label="نتائج المباريات — اضغط للتفاصيل">'
            f'<div class="tk-track">{seq}{seq}</div></a>')

# (the top-transfers widget was removed 2026-09-01 by user decision — the
# FotMob-style news blocks took its home slots; fetch_data no longer pulls
# transfers.json. Restore from git history if it ever comes back.)

# Client-side live layer: polls /live.json (edge-cached 15s) and patches
# scores/minute into the ticker + match rows IN PLACE. Matching is by
# normalized Arabic team-name pair; anything unmatched just stays on the
# 15-minute static refresh - the site never depends on this script.
LIVE_JS = r"""<script>
(function(){
  var els=[].slice.call(document.querySelectorAll('[data-lv]'));
  if((!els.length&&!document.getElementById('favLive'))||!window.fetch)return;
  function norm(s){return(s||'').replace(/[أإآ]/g,'ا')
    .replace(/ة/g,'ه').replace(/ى/g,'ي').replace(/[.'’]/g,'').replace(/\s+/g,'');}
  /* rows register under BOTH name orders: the sources can disagree on who
     is at home (FD: PSG x Rennes vs 365scores: Rennes x PSG) — a reversed
     hit paints with home/away swapped so the numbers stay correct. */
  var map={};
  els.forEach(function(e){
    var h=norm(e.getAttribute('data-h')),a=norm(e.getAttribute('data-a'));
    (map[h+'|'+a]=map[h+'|'+a]||[]).push({e:e,sw:false});
    (map[a+'|'+h]=map[a+'|'+h]||[]).push({e:e,sw:true});
  });
  function swap(g){
    var gl=(g.goals||[]).map(function(x){
      return {s:x.s==='h'?'a':'h',p:x.p,m:x.m,t:x.t};});
    return {h:g.a,a:g.h,hs:g.as,as:g.hs,live:g.live,min:g.min,c:g.c,
            goals:g.goals?gl:undefined};
  }
  /* home score on the home side - see score_pill() in build_site.py.
     Named sPill: paint() declares `var pill` for the status badge, and var
     hoisting would shadow a helper called pill across the WHOLE function. */
  function sPill(cls,hs,as_){
    return '<b class="'+cls+'"><span>'+hs+'</span><i>-</i><span>'+as_+'</span></b>';
  }
  function escH(s){return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
  /* live scorer lines - same markup as match_row()'s gblock so the static
     block and the live-painted one are indistinguishable. Only ever painted
     when the reply carries goals; an absent goals field must NOT clear an
     existing (static) list. */
  function paintGoals(e,g){
    if(!g.goals||!g.goals.length)return;
    var gh='',ga='';
    g.goals.forEach(function(x){
      var it='<span class="mg">⚽ <bdi>'+escH(x.p)+'</bdi>'
        +(x.m?' <i class="mg-m">'+escH(x.m)+'′</i>':'')
        +(x.t?' <small>('+escH(x.t)+')</small>':'')+'</span>';
      if(x.s==='h')gh+=it;else ga+=it;
    });
    var inner='<div class="mg-side">'+gh+'</div><div class="mg-gap"></div>'
      +'<div class="mg-side">'+ga+'</div>';
    var gb=e.querySelector('.mgoals');
    if(gb)gb.innerHTML=inner;
    else e.insertAdjacentHTML('beforeend','<div class="mgoals">'+inner+'</div>');
  }
  /* replay the CSS animation on an element that may already carry the class:
     removing it is not enough, the browser needs a reflow in between. */
  function flash(el){
    if(!el)return;
    el.classList.remove('sc-pop');
    void el.offsetWidth;
    el.classList.add('sc-pop');
    setTimeout(function(){el.classList.remove('sc-pop');},1500);
  }
  function paint(e,g){
    var sc=g.hs+' - '+g.as;
    /* a goal = the number differs from the LAST PAINTED one. data-sc is absent
       on the first paint, so a visitor arriving mid-match never sees a flash
       for a goal that was already on the screen when the page was built. */
    var prev=e.getAttribute('data-sc'), popped=(prev!==null&&prev!==sc);
    e.setAttribute('data-sc',sc);
    if(e.classList.contains('tk-item')){
      var mid=e.querySelector('.tk-mid'); if(!mid)return;
      mid.innerHTML=sPill('tk-s'+(g.live?' tk-live':''),g.hs,g.as)
        +(g.live?'<span class="tk-dot"></span>':'');
      if(popped)flash(mid.querySelector('.tk-s'));
    }else{
      var mid=e.querySelector('.mid'); if(!mid)return;
      mid.innerHTML='<b class="score">'+sc+'</b>'+(g.live&&g.min?'<span class="lv-min">'+g.min+'</span>':'');
      e.classList.remove('mrow-up','mrow-live','mrow-fin');
      e.classList.add(g.live?'mrow-live':'mrow-fin');
      var pill=e.querySelector('.pill');
      var txt=g.live?'مباشر':'انتهت';
      var cls=g.live?'live':'fin';
      if(pill){pill.className='pill pill-'+cls;pill.textContent=txt;}
      else e.insertAdjacentHTML('afterbegin','<span class="pill pill-'+cls+'">'+txt+'</span>');
      paintGoals(e,g);
      if(popped)flash(mid.querySelector('.score'));
      /* the match page's info card: «الحالة» follows the row (2026-09-13) */
      if(e.closest&&e.closest('.mp-hero')){
        var sd=document.querySelector('[data-lv-state]');
        if(sd){sd.textContent=g.live?('جارية الآن'+(g.min?' · '+g.min:'')):'انتهت';}
      }
    }
  }
  /* favourite-club live card next to "آخر الأخبار" (home page only).
     Entries are {n:name, c:competitionId|null}; a scoped entry (c set) only
     matches a game from that league — "الأهلي" is both Al Ahly Egypt AND
     Al-Ahli Saudi in the 365scores feed, and name-only matching once put
     the Saudi club's match in the card. */
  var favBox=document.getElementById('favLive');
  var FAV=(window.__favClubs||[]).map(function(e){
    return {n:norm(e&&e.n!==undefined?e.n:e), c:(e&&e.c)||null};
  });
  /* build-time extras for the card: crests + the match's own page URL,
     keyed by the normalized Arabic name pair (emitted as __favMeta) */
  var FMETA={};
  (function(){var raw=window.__favMeta||{};
    for(var k in raw){var p=k.split('|');
      if(p.length===2){
        FMETA[norm(p[0])+'|'+norm(p[1])]=raw[k];
        /* reversed too — same home/away source-disagreement as `map` */
        FMETA[norm(p[1])+'|'+norm(p[0])]={hb:raw[k].ab,ab:raw[k].hb,u:raw[k].u};
      }}})();
  /* ALL live curated-club matches, one card each (user rule 2026-08-23 —
     showing only the first hit hid Al Ahly while Trabzonspor was live) */
  function favRender(gs){
    if(!favBox)return;
    var hits=[];
    for(var i=0;i<gs.length;i++){
      var g=gs[i];
      if(!g.live)continue;
      var nh=norm(g.h),na=norm(g.a);
      for(var j=0;j<FAV.length;j++){
        var f=FAV[j];
        if((f.n===nh||f.n===na)&&(!f.c||f.c===g.c)){hits.push(g);break;}
      }
    }
    if(!hits.length){favBox.hidden=true;favBox.innerHTML='';return;}
    var html='';
    hits.forEach(function(hit){
      var mt=FMETA[norm(hit.h)+'|'+norm(hit.a)]||{};
      var hc=mt.hb?'<img class="fv-c" src="'+mt.hb+'" alt="" loading="lazy">':'';
      var ac=mt.ab?'<img class="fv-c" src="'+mt.ab+'" alt="" loading="lazy">':'';
      html+='<a class="fav-live" href="'+(mt.u||'/matches.html')+'">'
        +'<span class="fv-live"><span class="fv-dot"></span><span class="fv-lt">مباشر الآن</span></span>'
        +'<span class="fv-m">'+hc+'<bdi>'+hit.h+'</bdi>'
        +sPill('fv-s',hit.hs,hit.as)
        +'<bdi>'+hit.a+'</bdi>'+ac+'</span>'
        +(hit.min?'<span class="fv-min">'+hit.min+'</span>':'');
      html+='</a>';
    });
    favBox.innerHTML=html;
    favBox.hidden=false;
  }
  /* grace = how many more polls stay on the fast-ish 60s cadence after the
     last LIVE sighting. Without it ONE transient "nothing live" reply (an
     edge-cache entry built a second earlier, a match the source hasn't
     registered yet) dropped the page straight to 5-minute polling mid-match,
     and two in a row left a score ~10 minutes stale. */
  var timer=null,hadLive=!!document.querySelector('.mrow-live,.tk-dot'),
      grace=hadLive?3:0;
  /* the <head> starts the first /live.json request in parallel with the
     page load (window.__livePromise) — consume it once, then fetch fresh.
     ?b= = 10s-bucket cache-buster: Cloudflare's zone Browser-Cache-TTL
     rewrites our max-age to 4 HOURS, and mobile browsers/WebViews that
     ignore fetch's no-store hint then serve an hours-old cached copy on
     page open (user saw stale scores on open, 2026-08-30). A unique URL
     per 10s makes the local cache unusable; the worker keys its edge cache
     on the bare pathname, so edge caching is unaffected. */
  function liveReq(){
    var p=window.__livePromise;window.__livePromise=null;
    return p||fetch('/live.json?b='+Math.floor(Date.now()/1e4),{cache:'no-store'});
  }
  /* local minute clock: the worker sends each live game's numeric minute
     (gt) + half (hf) and the reply's build time (ts). The browser advances
     the minute itself between polls, so the shown minute never stalls on
     the poll/cache cadence. Past 45/90 it shows 45+ / 90+ (convention). */
  var last=null;
  function calcMin(g,at){
    if(!g.live||g.min==='استراحة'||!(g.gt>0))return;
    var est=Math.floor(g.gt+(Date.now()-at)/60000);
    if(g.hf===2)g.min=est>90?'90+':est+"'";
    else g.min=est>45?'45+':est+"'";
  }
  function render(){
    if(!last)return false;
    var any=false;
    last.gs.forEach(function(g){calcMin(g,last.at);});
    favRender(last.gs);
    last.gs.forEach(function(g){
      var arr=map[norm(g.h)+'|'+norm(g.a)];
      if(arr){arr.forEach(function(x){paint(x.e,x.sw?swap(g):g);});}
      if(g.live)any=true;
    });
    return any;
  }
  /* kickoff-aware cadence: __koTs (build-time epochs of nearby kickoffs)
     wakes an idle page right before a match starts instead of letting it
     sleep through kickoff on the 5-minute cadence. */
  var KO=window.__koTs||[];
  function nextDelay(any){
    if(any)return 30000;
    if(grace>0)return 60000;
    var now=Date.now(),wait=Infinity;
    for(var i=0;i<KO.length;i++){
      var dt=KO[i]-now;
      if(dt<=120000&&dt>=-300000)return 25000; /* KO-2min .. KO+5min */
      if(dt>120000)wait=Math.min(wait,dt-120000);
    }
    return wait===Infinity?300000:Math.min(300000,Math.max(25000,wait));
  }
  function tick(){
    liveReq().then(function(r){return r.json();}).then(function(d){
      /* age = how stale the (edge-cached) reply already is, so the minute
         baseline includes cache staleness; clamped so a wrong client clock
         cannot warp the minute by more than 3 minutes */
      var age=Math.max(0,Math.min(180000,Date.now()-(d.ts||Date.now())));
      last={gs:d.games||[],at:Date.now()-age};
      var any=render();
      if(d.ok===false){schedule(hadLive?60000:120000);return;}
      if(any)grace=3;else if(grace>0)grace--;
      hadLive=any;
      schedule(nextDelay(any));
    }).catch(function(){schedule(hadLive?60000:120000);});
  }
  /* re-render the local minute between polls. paint() only flashes when the
     SCORE string changes, so this repaint can never trigger a goal flash. */
  setInterval(function(){
    if(hadLive&&document.visibilityState==='visible')render();
  },20000);
  function schedule(ms){clearTimeout(timer);timer=setTimeout(tick,ms);}
  document.addEventListener('visibilitychange',function(){
    if(document.visibilityState==='visible'){clearTimeout(timer);tick();}
    else clearTimeout(timer);
  });
  /* bfcache/tab-restore on mobile can bring a page back without firing
     visibilitychange — refresh immediately on that path too */
  window.addEventListener('pageshow',function(e){
    if(e.persisted){clearTimeout(timer);tick();}
  });
  tick();
})();
</script>"""

def article_href(a):
    """Site-relative URL of an article.

    A match preview/report lives INSIDE its match page (2026-09-16): one URL per
    match carrying the story, the numbers, the XI and the result, instead of a
    prose page at /a/ and a data page at /m/ competing for the same query with
    half an answer each. Everything that links an article goes through here, so
    the move is one function wide. The old /a/<id> URLs keep working as 301s
    (see the _redirects file the build writes) - 43 of the 44 have a published
    Facebook post pointing at them.
    """
    if a.get("kind") in ("preview", "report") and a.get("match_id"):
        return f"/m/{a['match_id']}.html"
    return f"/a/{a['article_id']}.html"

def article_url(a):
    return SITE_BASE + article_href(a)

def is_match_piece(a):
    return bool(a.get("kind") in ("preview", "report") and a.get("match_id"))

# article_id -> match page, for the pieces that moved (filled by build()).
# An article body written before the move can link a piece as /a/<id>;
# that still works through the 301, but an internal link should name the
# destination, not a redirect to it.
_MOVED_LINKS = {}
_A_HREF = re.compile(r'href="/a/(\d+)(?:\.html)?"')

def fix_moved_links(body):
    if not _MOVED_LINKS or not body:
        return body
    return _A_HREF.sub(
        lambda m: 'href="%s"' % _MOVED_LINKS.get(m.group(1), "/a/" + m.group(1)),
        body)

def match_article_block(a, comp):
    """The AI preview/report, rendered inside its match page (layer 3).

    Two pages about one match - prose with no numbers at /a/, numbers with no
    prose at /m/ - is the thin, templated pattern that got the site rejected
    twice. This puts the story, the photo, the named byline, the sources and
    the computed readings on ONE url.

    The FAQ is rendered WITHOUT its FAQPage schema on purpose: the match page
    emits its own from the reading below, and two FAQPage blocks on one page
    is a structured-data conflict. The visible questions still help a reader.
    """
    src = [x for x in (a.get("sources") or []) if isinstance(x, dict) and x.get("name")]
    if not src:
        src = match_data_sources(a, comp)
    img = a.get("image_url")
    out = ['<section class="minfo marticle">']
    out.append(f'<h2>{esc(a["title"])}</h2>')
    # «بمعلومات وقت النشر»: a report written the night Al Ahly topped the
    # table sits on the same page as a reading computed from TODAY's table
    # (3rd, level with Zamalek) - both are right, and without the label they
    # read as a contradiction (outside audit, 2026-09-22). The article is a
    # dated snapshot BY POLICY (published pieces are never rewritten); the
    # computed reading is the current state.
    out.append(f'<p class="a-meta"><a class="a-by" href="/editors.html">{esc(byline(a))}</a>'
               f' · <time datetime="{esc(a.get("pub_date"))}">{esc(a.get("pub_date"))}</time>'
               f' · <span class="a-tnote">بمعلومات وقت النشر</span></p>')
    if img:
        out.append(f'<figure class="a-fig"><img class="a-img" src="{esc(img)}" '
                   f'alt="{esc(a["title"])}" loading="lazy">')
        if a.get("image_credit"):
            out.append(f'<figcaption class="a-credit">{esc(a["image_credit"])}</figcaption>')
        out.append('</figure>')
    if a.get("summary"):
        out.append(f'<p class="lead">{esc(a["summary"])}</p>')
    out.append(f'<div class="a-body">{fix_moved_links(a.get("body")) or ""}</div>')
    faq = [f for f in (a.get("faq") or []) if isinstance(f, dict) and f.get("q") and f.get("a")]
    if faq:
        out.append('<div class="a-faq"><h3>أسئلة شائعة</h3>'
                   + "".join(f'<details><summary>{esc(f["q"])}</summary><p>{esc(f["a"])}</p></details>'
                             for f in faq) + '</div>')
    out.append('<div class="a-sources"><h3>المصادر</h3><ul>'
               + "".join((f'<li><a href="{esc(x["url"])}" target="_blank" rel="noopener nofollow">{esc(x["name"])}</a>'
                          if x.get("url") else f'<li>{esc(x["name"])}')
                         + (f' — {esc(x["note"])}' if x.get("note") else "") + '</li>' for x in src)
               + '</ul></div>')
    out.append(embeds_block(a.get("embeds")))
    out.append('</section>')
    out.append(jsonld({"@context": "https://schema.org", "@type": "NewsArticle",
                       "headline": a["title"], "description": strip_tags(a.get("summary")),
                       "datePublished": a.get("pub_ts") or a.get("pub_date"),
                       "dateModified": a.get("updated_ts") or a.get("pub_ts") or a.get("pub_date"),
                       "mainEntityOfPage": SITE_BASE + article_href(a),
                       "author": {"@type": "Person", "name": byline(a),
                                  "url": SITE_BASE + "/editors.html"},
                       "publisher": {"@type": "Organization", "name": SITE_NAME,
                                     "url": SITE_BASE}}))
    return "".join(out)

def pick_match_article(pieces, status):
    """One piece per match page: the report once the match is over, otherwise
    the preview. Both on one page would tell the same story twice."""
    if not pieces:
        return None
    want = "report" if status == "FINISHED" else "preview"
    return (next((a for a in pieces if a.get("kind") == want), None)
            or sorted(pieces, key=lambda a: a.get("pub_ts") or "")[-1])

def article_moved_stub(a):
    """What stays at the old /a/ URL of a piece that moved into its match page.

    The _redirects file should answer 301 long before this file is ever served.
    It exists because 43 of the 44 moved pieces have a published Facebook post
    pointing at /a/<id>, and a redirect rule that silently fails to apply would
    turn all of them into 404s. Belt to that pair of braces: noindex so the URL
    leaves the index, canonical so whatever signal it still holds is credited
    to the match page, and a refresh plus a real link so a human always lands
    in the right place.
    """
    to = article_href(a)
    return (f'<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8">'
            f'<meta name="robots" content="noindex,follow">'
            f'<link rel="canonical" href="{esc(SITE_BASE + to)}">'
            f'<meta http-equiv="refresh" content="0;url={esc(to)}">'
            f'<title>{esc(a.get("title") or "")}</title></head>'
            f'<body><p>انتقلت هذه الصفحة إلى '
            f'<a href="{esc(to)}">صفحة المباراة</a>.</p></body></html>')

# sitemap <lastmod> per URL path (set where the page's real change date is
# known: articles = publish time, match pages = kickoff/today). Pages that
# are rebuilt with fresh data every run default to today in the writer;
# static legal pages get none.
_LASTMOD = {}

def breadcrumb_ld(items):
    """BreadcrumbList JSON-LD from [(name, absolute_url), ...]."""
    return jsonld({
        "@context": "https://schema.org", "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "name": n, "item": u}
            for i, (n, u) in enumerate(items)]})

_ART_CLUBS = {}
def article_clubs(a):
    """TEAM_PAGES entries an article talks about (cached per article id)."""
    k = a.get("article_id")
    if k not in _ART_CLUBS:
        _ART_CLUBS[k] = [tp for tp in TEAM_PAGES if _team_news(tp, a)]
    return _ART_CLUBS[k]

_KW_STOP = {"مباراة", "الدوري", "أمام", "بعد", "قبل", "خلال", "اليوم", "المصري",
            "الفريق", "نادي", "لاعب", "الجولة", "موعد", "نتيجة", "تقرير", "المباراة",
            "بطولة", "دوري", "أبطال", "الموسم", "الجديد", "يعلن", "رسميًا", "رسميا"}
def _art_kw(a):
    return {w.strip("،:.,؟!\"'()«»") for w in (a.get("title") or "").split()
            if len(w.strip("،:.,؟!\"'()«»")) >= 4} - _KW_STOP

def related_articles(a, articles, n=4):
    """Articles worth linking from `a`: same match (preview <-> report),
    shared curated club(s), shared title words; newest first on ties, then
    padded with the newest articles so every page links to n others."""
    my_clubs = {tp["slug"] for tp in article_clubs(a)}
    my_kw = _art_kw(a)
    scored = []
    for i, b in enumerate(articles):
        if b.get("article_id") == a.get("article_id"):
            continue
        s = 0
        if a.get("match_id") and b.get("match_id") == a.get("match_id"):
            s += 10
        s += 3 * len(my_clubs & {tp["slug"] for tp in article_clubs(b)})
        s += min(3, len(my_kw & _art_kw(b)))
        if s:
            scored.append((s, -i, b))
    scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
    out = [b for _, _, b in scored[:n]]
    for b in articles:
        if len(out) >= n:
            break
        if b.get("article_id") != a.get("article_id") and b not in out:
            out.append(b)
    return out

def _team_link(comp, raw_name):
    """Arabic team name, linked to its /team/ page when it is a curated club."""
    nm = ar_team(raw_name)
    for tp in TEAM_PAGES:
        scope = tuple(c for _, c in tp["match_tokens"] if c) or None
        in_league = (tp["league"] == comp) or (scope is not None and _in_scope(scope, comp))
        if in_league and any(t in (raw_name or "") or t == nm for t, _ in tp["match_tokens"]):
            return f'<a href="/team/{tp["slug"]}.html">{esc(nm)}</a>'
    return esc(nm)

def _cnt(n, one, two, few, many):
    """Arabic count with proper agreement: 1 -> one ("نقطة واحدة"),
    2 -> two ("نقطتان"), 3-10 -> "n few" ("5 نقاط"), 0/11+ -> "n many" ("12 نقطة")."""
    n = int(n or 0)
    if n == 0:
        return f"دون {few}"          # "دون أهداف" / "دون خسائر"
    if n == 1:
        return one
    if n == 2:
        return two
    if 3 <= n <= 10:
        return f"{n} {few}"
    return f"{n} {many}"

def _pts(n):   return _cnt(n, "نقطة واحدة", "نقطتين", "نقاط", "نقطة")
def _games(n): return _cnt(n, "مباراة واحدة", "مباراتين", "مباريات", "مباراة")
def _goals(n): return _cnt(n, "هدف واحد", "هدفين", "أهداف", "هدفًا")
def _wins(n):  return _cnt(n, "فوز واحد", "فوزين", "انتصارات", "فوزًا")
def _draws(n): return _cnt(n, "تعادل واحد", "تعادلين", "تعادلات", "تعادلًا")
def _losses(n): return _cnt(n, "خسارة واحدة", "خسارتين", "خسائر", "خسارة")
def _assists(n): return _cnt(n, "تمريرة حاسمة واحدة", "تمريرتين حاسمتين",
                             "تمريرات حاسمة", "تمريرة حاسمة")
def _players(n): return _cnt(n, "لاعبًا واحدًا", "لاعبين", "لاعبين", "لاعبًا")

def _lil(name):
    """«لـ» before a club name, with the ل+ال elision Arabic requires:
    القناة -> للقناة, not «لـالقناة»."""
    name = (name or "").strip()
    return ("لل" + name[2:]) if name.startswith("ال") else ("لـ" + name)

def scorers_read(label, season, sc, asst, table, pool):
    """Editorial reading of a top-scorer chart, computed from the numbers we
    already publish — the same answer /standings got on 2026-09-06 when a bare
    table was judged thin content.

    Ten names is a list, not a page. What makes it a page is what the list
    MEANS: who leads and by how much, how much of his club's season he is
    carrying, whether one club owns the chart, who creates rather than
    finishes, and where all of it sits against the league's own goal rate.

    Every sentence restates data on this site (the chart, the official table,
    the season pool). Nothing is estimated, and each fact is skipped when its
    input is missing — which is also what decides whether the page is worth
    indexing: returns (html, faq_html, weight).
    """
    sc = [x for x in (sc or []) if x.get("name")]
    if not sc:
        return "", "", 0
    facts, faq = [], []
    top_v = _pval(sc[0])
    leaders = [x for x in sc if _pval(x) == top_v]
    gf_by = {}
    for r in (table or []):
        if r.get("team"):
            gf_by[_gnorm(r["team"])] = r

    # 1. the lead, and what it is worth
    if len(leaders) == 1:
        nxt = next((_pval(x) for x in sc if _pval(x) < top_v), None)
        gap = (f" بفارق {_goals(top_v - nxt)} عن أقرب منافسيه"
               if nxt is not None and top_v > nxt else " بالتساوي مع أقرب منافسيه")
        facts.append(f'يتصدر <b>{esc(sc[0]["name"])}</b> ({esc(sc[0].get("team") or "")}) '
                     f'قائمة هدافي {esc(label)} بـ{_goals(top_v)}{gap}.')
        faq.append((f"من هداف {label} الآن؟",
                    f"{sc[0]['name']} ({sc[0].get('team') or ''}) برصيد {_goals(top_v)} "
                    f"في موسم {season}."))
    else:
        # name EVERY leader while they fit in a sentence: capping at three
        # under a count of four read «بين 4 لاعبين (a، b، c)» and dropped
        # Zizo from his own shared lead (ChatGPT site audit, 2026-09-21).
        # Past five names, say «منهم» so the sentence stops claiming to be
        # the full list instead of silently contradicting the count.
        if len(leaders) <= 5:
            names, pre = "، ".join(esc(x["name"]) for x in leaders), ""
        else:
            names, pre = "، ".join(esc(x["name"]) for x in leaders[:3]), "منهم "
        facts.append(f'تُقسَم صدارة هدافي {esc(label)} بين {_players(len(leaders))} '
                     f'({pre}{names}) برصيد {_goals(top_v)} لكل منهم.')
        faq_names = ("، ".join(x["name"] for x in leaders) if len(leaders) <= 5
                     else "، ".join(x["name"] for x in leaders[:3]) + " وآخرون")
        faq.append((f"من هداف {label} الآن؟",
                    f"الصدارة مشتركة بين {_players(len(leaders))} برصيد {_goals(top_v)} لكل منهم: "
                    + faq_names + "."))

    # 2. how much of his club's season the leader is carrying
    row = gf_by.get(_gnorm(sc[0].get("team")))
    if row and (row.get("gf") or 0) > 0 and top_v <= row["gf"]:
        share = round(top_v * 100 / row["gf"])
        # named, never «وسجّل وحده»: the lead above may be shared, and an
        # unnamed pronoun would then point at whichever name came first
        facts.append(f'وسجّل <b>{esc(sc[0]["name"])}</b> {_goals(top_v)} من أصل '
                     f'{_goals(row["gf"])} {esc(_lil(row["team"]))} هذا الموسم، '
                     f'أي {share}% من أهداف ناديه.')

    # 3. one club owning the chart
    clubs = {}
    for x in sc:
        if x.get("team"):
            clubs.setdefault(_gnorm(x["team"]), [x["team"], 0])[1] += 1
    top_club = max(clubs.values(), key=lambda v: v[1]) if clubs else None
    if top_club and top_club[1] >= 2:
        facts.append(f'ويضع {esc(top_club[0])} {_players(top_club[1])} من صفوفه '
                     f'داخل أعلى {len(sc)} هدافين.')

    # 4. the creators, and anyone doing both
    if asst:
        a0 = asst[0]
        facts.append(f'وفي صناعة الأهداف يتقدم <b>{esc(a0["name"])}</b> '
                     f'({esc(a0.get("team") or "")}) بـ{_assists(_pval(a0))}.')
        faq.append((f"من أكثر صانعي الأهداف في {label}؟",
                    f"{a0['name']} ({a0.get('team') or ''}) برصيد {_assists(_pval(a0))}."))
        both = [x["name"] for x in sc
                if any(_gnorm(y.get("name")) == _gnorm(x.get("name")) for y in asst)]
        if both:
            facts.append('واللافت أن ' + "، ".join(esc(n) for n in both)
                         + (' حاضر في القائمتين: بين الهدافين وصنّاع الأهداف معًا.'
                            if len(both) == 1 else
                            ' حاضرون في القائمتين معًا.'))

    # 5. the league's own scale
    if pool:
        g = sum(int(m["home_score"]) + int(m["away_score"]) for m in pool)
        n = len(pool)
        if n and g:
            top_sum = sum(_pval(x) for x in sc)
            facts.append(f'وللمقارنة، سجّل {esc(label)} {g} هدفًا في {_games(n)} '
                         f'هذا الموسم (بمعدل {g / n:.2f} للمباراة)، فأعلى {len(sc)} هدافين '
                         f'يمثلون {round(top_sum * 100 / g)}% منها.')
            faq.append((f"كم هدفًا سُجّل في {label} هذا الموسم؟",
                        f"{g} هدفًا في {_games(n)} منتهية، بمعدل {g / n:.2f} هدف في المباراة "
                        f"حتى تاريخ التحديث."))

    faq.append(("متى تُحدَّث قائمة الهدافين؟",
                "تُحدَّث تلقائيًا من مصدر بيانات المباريات كل ربع ساعة تقريبًا، "
                "فتظهر أهداف كل جولة بعد نهايتها مباشرة."))

    html = (f'<section class="minfo st-analysis"><h2>قراءة في صدارة هدافي {esc(label)}</h2>'
            + "".join(f"<p>{t}</p>" for t in facts) + '</section>')
    fhtml = ('<section class="minfo faq"><h2>أسئلة شائعة عن هدافي ' + esc(label) + '</h2>'
             + "".join(f'<details><summary>{esc(q)}</summary><p>{esc(a)}</p></details>'
                       for q, a in faq) + '</section>')
    fld = jsonld({"@context": "https://schema.org", "@type": "FAQPage",
                  "mainEntity": [{"@type": "Question", "name": q,
                                  "acceptedAnswer": {"@type": "Answer", "text": a}}
                                 for q, a in faq]})
    return html, fhtml + fld, len(facts)

def standings_analysis(comp, label, season, rows, form_map, scorers, up_next, zeroed=False):
    """Editorial reading of a league table, generated ONLY from the numbers we
    already publish (AdSense 'low value content' remediation: a bare table is
    thin; the same page with an explanation, a title-race reading, form notes
    and an FAQ is a real guide). Returns (html, faq_jsonld_or_empty).
    Every sentence is a restatement of table/form/scorer data — no guesses."""
    rows = [r for r in rows if r.get("team")]
    if not rows:
        return "", ""
    if zeroed or all(int(r.get("played") or 0) == 0 for r in rows):
        html = (f'<section class="minfo st-analysis"><h2>عن ترتيب {esc(label)} {esc(season)}</h2>'
                f'<p>الموسم الجديد من {esc(label)} لم ينطلق بعد، لذلك يظهر الجدول بقائمة الأندية '
                f'المشاركة ({len(rows)} فريقًا) وكل الأرقام عند الصفر. بمجرد انتهاء أول مباراة يتحدّث '
                'الجدول تلقائيًا بالنقاط والأهداف وفارق الأهداف ونتائج آخر خمس مباريات لكل فريق.</p>'
                '<p><b>كيف تُقرأ الأعمدة؟</b> لعب = عدد المباريات، ف/ت/خ = الفوز والتعادل والخسارة، '
                'له/عليه = الأهداف المسجلة والمستقبلة، الفارق = له ناقص عليه، النقاط = 3 لكل فوز '
                'ونقطة لكل تعادل.</p></section>')
        return html, ""
    T = lambda r: _team_link(comp, r.get("team"))
    N = lambda r: ar_team(r.get("team"))
    lead, second = rows[0], (rows[1] if len(rows) > 1 else None)
    gap = int(lead.get("pts") or 0) - int((second or {}).get("pts") or 0)
    ps = []
    ps.append(f'<p>يتصدر {T(lead)} ترتيب {esc(label)} برصيد <b>{_pts(lead.get("pts"))}</b> من '
              f'{_games(lead.get("played"))} '
              f'({_wins(lead.get("won"))}، {_draws(lead.get("draw"))}، {_losses(lead.get("lost"))})'
              + (f'، بفارق {_pts(gap)} عن {T(second)} صاحب المركز الثاني.'
                 if second and gap > 0 else
                 (f'، متساويًا في النقاط مع {T(second)} الثاني الذي يفصله عنه فارق الأهداف '
                  f'({lead.get("gd")} مقابل {second.get("gd")}).' if second else '.'))
              + '</p>')
    top3 = rows[:3]
    if len(rows) >= 4:
        ps.append('<p>المربع الأمامي حتى الآن: ' + '، '.join(
            f'{T(r)} ({_pts(r.get("pts"))})' for r in rows[:4]) + '.</p>')
    played = [r for r in rows if int(r.get("played") or 0) > 0]
    if played:
        best_att = max(played, key=lambda r: (int(r.get("gf") or 0), -int(r.get("ga") or 0)))
        best_def = min(played, key=lambda r: (int(r.get("ga") or 0), -int(r.get("gf") or 0)))
        best_gd = max(played, key=lambda r: int(r.get("gd") or 0))
        worst_gd = min(played, key=lambda r: int(r.get("gd") or 0))
        ps.append(f'<p><b>الهجوم والدفاع:</b> أقوى خط هجوم هو {T(best_att)} بـ{_goals(best_att.get("gf"))}، '
                  f'وأقل شباك استقبالًا للأهداف {T(best_def)} '
                  + (f'بـ{_goals(best_def.get("ga"))} فقط. ' if int(best_def.get("ga") or 0) else 'بشباك لم تستقبل أي هدف حتى الآن. ')
                  + f'أفضل فارق أهداف يملكه {T(best_gd)} ({"+" if int(best_gd.get("gd") or 0) > 0 else ""}{best_gd.get("gd")})، '
                  f'وأسوأ فارق عند {T(worst_gd)} ({worst_gd.get("gd")}).</p>')
    fm = form_map or {}
    def _last5(r):
        return (fm.get(r.get("team")) or [])[-5:]
    hot = sorted([r for r in rows if len(_last5(r)) >= 3],
                 key=lambda r: (-_last5(r).count("W"), _last5(r).count("L")))[:3]
    cold = [r for r in rows if len(_last5(r)) >= 3 and _last5(r).count("W") == 0]
    if hot:
        ps.append('<p><b>الفرق في أفضل حالاتها:</b> ' + '، '.join(
            f'{T(r)} ({_wins(_last5(r).count("W"))} في آخر {_games(len(_last5(r)))})' for r in hot)
            + (f'. أما الفرق التي لم تحقق أي فوز في آخر مبارياتها فهي: '
               + '، '.join(T(r) for r in cold[:4]) + '.' if cold else '.') + '</p>')
    bottom = rows[-3:] if len(rows) >= 6 else []
    if bottom:
        ps.append('<p><b>قاع الجدول:</b> ' + '، '.join(
            f'{T(r)} ({_pts(r.get("pts"))})' for r in bottom)
            + ' — هذه الفرق تحتاج إلى تحسين سريع في النتائج قبل أن تتسع الفجوة مع منطقة الأمان.</p>')
    top_sc = (scorers or [None])[0]
    if top_sc and top_sc.get("name"):
        ps.append(f'<p><b>هداف البطولة:</b> {esc(top_sc["name"])} ({esc(ar_team(top_sc.get("team")))}) '
                  f'برصيد {_goals(top_sc.get("goals") or top_sc.get("value"))}'
                  + (f'، يليه {esc(scorers[1]["name"])} بـ{_goals(scorers[1].get("goals") or scorers[1].get("value"))}.'
                     if len(scorers) > 1 else '.') + '</p>')
    nxt = up_next[0] if up_next else None
    if nxt:
        ps.append(f'<p><b>الجولة القادمة:</b> تُستكمل مباريات {esc(label)} يوم {esc(nxt.get("kickoff"))} '
                  f'بلقاء {esc(ar_team(nxt.get("home")))} و{esc(ar_team(nxt.get("away")))}'
                  + (f' و{_games(len(up_next) - 1)} أخرى' if len(up_next) > 1 else '')
                  + ' — القائمة الكاملة أسفل الصفحة، وكل مباراة لها صفحتها بالتشكيل والأهداف.</p>')
    ps.append('<p><b>كيف تُقرأ الأعمدة؟</b> «لعب» عدد المباريات، «ف/ت/خ» الفوز والتعادل والخسارة، '
              '«له» الأهداف المسجلة و«عليه» المستقبلة، «الفارق» = له ناقص عليه، و«النقاط» = 3 نقاط '
              'لكل فوز ونقطة لكل تعادل. عند التساوي في النقاط تُطبَّق معايير الفصل الواردة في لائحة '
              'البطولة (فارق الأهداف والأهداف المسجلة، وفي بعض البطولات المواجهات المباشرة أولًا). '
              'النقاط الملوّنة بجوار كل فريق هي نتائج آخر خمس مباريات من الأقدم إلى الأحدث.</p>')
    html = (f'<section class="minfo st-analysis"><h2>قراءة في ترتيب {esc(label)} {esc(season)}</h2>'
            + "".join(ps) + '</section>')
    # FAQ — answers are the same data in question form
    faq = [(f"من يتصدر {label} حاليًا؟",
            f"{N(lead)} يتصدر برصيد {_pts(lead.get('pts'))} من {_games(lead.get('played'))}"
            + (f"، بفارق {_pts(gap)} عن {N(second)}." if second and gap > 0 else "."))]
    if second:
        faq.append((f"كم الفارق بين الأول والثاني في {label}؟",
                    f"{_pts(gap)} بين {N(lead)} ({lead.get('pts')}) و{N(second)} ({second.get('pts')})."
                    if gap else f"لا فارق في النقاط: {N(lead)} و{N(second)} متساويان برصيد {_pts(lead.get('pts'))}، ويفصل بينهما فارق الأهداف."))
    if top_sc and top_sc.get("name"):
        faq.append((f"من هو هداف {label} هذا الموسم؟",
                    f"{top_sc['name']} لاعب {ar_team(top_sc.get('team'))} برصيد {_goals(top_sc.get('goals') or top_sc.get('value'))} حتى الآن."))
    faq.append(("كيف يُحسب فارق الأهداف؟",
                "فارق الأهداف = الأهداف المسجلة (له) ناقص الأهداف المستقبلة (عليه). يُستخدم كأحد معايير الفصل بين الفرق المتساوية في النقاط."))
    if nxt:
        faq.append((f"متى الجولة القادمة في {label}؟",
                    f"أقرب مباراة يوم {nxt.get('kickoff')}: {ar_team(nxt.get('home'))} ضد {ar_team(nxt.get('away'))} (التوقيت بتوقيت القاهرة في صفحة المباريات)."))
    faq.append(("كم مرة يتحدّث جدول الترتيب؟",
                "يتحدّث الجدول تلقائيًا كل ربع ساعة تقريبًا من مصدر بيانات المباريات، فتظهر النتائج بعد صافرة النهاية مباشرة."))
    fhtml = ('<section class="minfo faq"><h2>أسئلة شائعة عن ' + esc(label) + '</h2>'
             + "".join(f'<details><summary>{esc(q)}</summary><p>{esc(a)}</p></details>' for q, a in faq)
             + '</section>')
    fld = jsonld({"@context": "https://schema.org", "@type": "FAQPage",
                  "mainEntity": [{"@type": "Question", "name": q,
                                  "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]})
    return html, fhtml + fld

def _rfc822(a):
    """RSS pubDate from pub_ts (full ISO) or pub_date (noon Cairo)."""
    ts = a.get("pub_ts") or ""
    try:
        dt = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        try:
            from zoneinfo import ZoneInfo
            dt = datetime.datetime.fromisoformat(f"{a.get('pub_date')}T12:00:00").replace(
                tzinfo=ZoneInfo("Africa/Cairo"))
        except Exception:
            return ""
    return dt.strftime("%a, %d %b %Y %H:%M:%S %z")

def headline_card(h):
    """One external-headline card (home teaser + /headlines.html page)."""
    t = strip_src(h.get("title"), h.get("source"))
    iso = h.get("pub_iso") or ""
    when = rel_ar(iso) if iso else (h.get("pub_date") or "")
    timeel = (f'<time class="reltime" datetime="{esc(iso)}">{esc(when)}</time>'
              if iso else esc(when))
    src = esc(h.get('source') or '')
    img = h.get("image") or ""
    # Publisher thumbnail, hotlinked from the source's own CDN (aggregator
    # style — we never copy the file). No image (or a broken one) falls back
    # to one of our own generic pitch/ball SVGs, picked deterministically so
    # neighbouring cards alternate.
    ph = PLACEHOLDER_IMGS[int(hashlib.md5((h.get("link") or t).encode("utf-8")).hexdigest(), 16) % len(PLACEHOLDER_IMGS)]
    thumb = (f'<span class="himg"><img src="{esc(img)}" alt="" loading="lazy" '
             f'referrerpolicy="no-referrer" '
             f'onerror="this.onerror=null;this.src=\'{ph}\';"></span>' if img else
             f'<span class="himg"><img src="{ph}" alt="" loading="lazy"></span>')
    return (f'<a class="hcard" href="{esc(h.get("source_url") or h.get("link"))}" target="_blank" rel="noopener nofollow">'
            f'<span class="go" aria-hidden="true">↗</span>{thumb}'
            f'<h3>{esc(t)}</h3>'
            f'<p class="meta"><span class="hsrc">{src}</span><span class="reltime-wrap">{timeel}</span></p></a>')

def news_card(a):
    """One article card (used by the home shelf and the /news.html archive)."""
    img = thumb_url(a.get("image_url"))
    thumb = (f'<div class="card-img" style="background-image:url(\'{esc(img)}\')"></div>'
             if img else '<div class="card-img noimg">⚽</div>')
    t = art_reltime(a)
    return (f'<a class="card" href="{article_href(a)}">{thumb}'
            f'<div class="card-b"><h3>{esc(a["title"])}</h3>'
            f'<p class="meta">{esc(byline(a))}{" · " + t if t else ""}</p></div></a>')

def _art_meta(a):
    """author · منذ X — the byline under FotMob-block titles."""
    t = art_reltime(a)
    return esc(byline(a)) + (f" · {t}" if t else "")

def club_crest(tp, standings, matches, fixtures):
    """Self-hosted crest URL for a TEAM_PAGES club: its standings row first,
    else any match badge (matches ∪ fixtures rounds); "" when unknown."""
    toks = tp["match_tokens"]
    for st in standings:
        if not _in_scope(tuple(c for _, c in toks if c) or None, st.get("competition")) \
                and st.get("competition") != tp["league"]:
            continue
        for r in st.get("table") or []:
            if any(t in (r.get("team") or "") for t, _ in toks) and r.get("crest"):
                return local_crest(r["crest"])
    pool = list(matches)
    for fx in fixtures:
        for rd in fx.get("rounds", []):
            pool.extend(rd.get("matches", []))
    for m in reversed(pool):
        if not _team_match(tp, m):
            continue
        for side in ("home", "away"):
            if any(t in (m.get(side) or "") for t, _ in toks) and m.get(side + "_badge"):
                return local_crest(m[side + "_badge"])
    return ""

def clubs_strip(standings, matches, fixtures):
    """Horizontal crest strip of the curated clubs (user ask 2026-09-02) —
    each item links to the club's /team/ page. Arrows glide on desktop and
    hide when everything already fits (CLUBS_JS)."""
    items = []
    for tp in TEAM_PAGES:
        crest = club_crest(tp, standings, matches, fixtures)
        ico = (f'<img src="{esc(crest)}" alt="" width="46" height="46" loading="lazy">'
               if crest else '<span class="cs-ph">⚽</span>')
        items.append(f'<a class="cs-item" href="/team/{tp["slug"]}.html">'
                     f'{ico}<span>{esc(tp["name"])}</span></a>')
    if not items:
        return ""
    return ('<section class="clubs" aria-label="أندية يلا سكور">'
            '<button class="cs-btn cs-l" type="button" aria-label="السابق">‹</button>'
            f'<div class="cs-track" id="clubsStrip">{"".join(items)}</div>'
            '<button class="cs-btn cs-r" type="button" aria-label="التالي">›</button>'
            '</section>' + CLUBS_JS)

CLUBS_JS = """<script>
(function(){
  var sh=document.getElementById('clubsStrip'); if(!sh) return;
  var l=document.querySelector('.cs-l'), r=document.querySelector('.cs-r');
  function fits(){ return sh.scrollWidth <= sh.clientWidth + 2; }
  function sync(){ var h=fits(); if(l) l.hidden=h; if(r) r.hidden=h; }
  function step(){ var c=sh.querySelector('.cs-item'); return (c ? c.offsetWidth + 22 : 110) * 3; }
  /* rAF glide, same reason as SHELF_JS: Chromium mis-clamps RTL smooth scrollBy */
  function glide(delta){
    var start=sh.scrollLeft, min=-(sh.scrollWidth-sh.clientWidth), max=0;
    var target=Math.min(max, Math.max(min, start+delta)), t0=performance.now();
    function f(t){ var k=Math.min(1,(t-t0)/300); k=1-Math.pow(1-k,3);
      sh.scrollLeft=start+(target-start)*k; if(k<1) requestAnimationFrame(f); }
    requestAnimationFrame(f);
  }
  if(l) l.addEventListener('click',function(){ glide(-step()); });
  if(r) r.addEventListener('click',function(){ glide( step()); });
  sync(); window.addEventListener('resize', sync);
})();
</script>"""

# Filter chips beside the «آخر الأخبار» title (FotMob news-page style, user
# ask 2026-09-02): round icons — الأكثر تداولًا (pulse), مصر (flag), أوروبا
# (UCL emblem). Chips whose block is missing on this build hide themselves.
_NF_ICON_TREND = ('<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">'
                  '<polyline points="2,13 6,13 9,6 13,18 16,11 18,13 22,13" fill="none" '
                  'stroke="#1f94d3" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg>')
_NF_ICON_EUR = ('<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"><clipPath id="nfsb"><circle cx="12" cy="12" r="11"/></clipPath><circle cx="12" cy="12" r="11" fill="#ffffff"/><g clip-path="url(#nfsb)" fill="#2b2b2b"><polygon points="12.00,7.40 13.12,10.46 16.37,10.58 13.81,12.59 14.70,15.72 12.00,13.90 9.30,15.72 10.19,12.59 7.63,10.58 10.88,10.46"/><polygon points="12.00,22.20 11.12,19.81 8.58,19.71 10.57,18.14 9.88,15.69 12.00,17.10 14.12,15.69 13.43,18.14 15.42,19.71 12.88,19.81"/><polygon points="3.17,17.10 4.79,15.14 3.61,12.89 5.97,13.83 7.75,12.01 7.58,14.55 9.86,15.68 7.40,16.30 7.03,18.82 5.67,16.67"/><polygon points="3.17,6.90 5.67,7.33 7.03,5.18 7.40,7.70 9.86,8.32 7.58,9.45 7.75,11.99 5.97,10.17 3.61,11.11 4.79,8.86"/><polygon points="12.00,1.80 12.88,4.19 15.42,4.29 13.43,5.86 14.12,8.31 12.00,6.90 9.88,8.31 10.57,5.86 8.58,4.29 11.12,4.19"/><polygon points="20.83,6.90 19.21,8.86 20.39,11.11 18.03,10.17 16.25,11.99 16.42,9.45 14.14,8.32 16.60,7.70 16.97,5.18 18.33,7.33"/><polygon points="20.83,17.10 18.33,16.67 16.97,18.82 16.60,16.30 14.14,15.68 16.42,14.55 16.25,12.01 18.03,13.83 20.39,12.89 19.21,15.14"/><polygon points="4.70,24.64 5.12,22.27 3.07,20.99 5.46,20.66 6.04,18.32 7.10,20.49 9.51,20.32 7.77,21.99 8.68,24.23 6.55,23.09"/><polygon points="-2.60,12.00 -0.33,11.18 -0.25,8.77 1.23,10.67 3.55,10.00 2.20,12.00 3.55,14.00 1.23,13.33 -0.25,15.23 -0.33,12.82"/><polygon points="4.70,-0.64 6.55,0.91 8.68,-0.23 7.77,2.01 9.51,3.68 7.10,3.51 6.04,5.68 5.46,3.34 3.07,3.01 5.12,1.73"/><polygon points="19.30,-0.64 18.88,1.73 20.93,3.01 18.54,3.34 17.96,5.68 16.90,3.51 14.49,3.68 16.23,2.01 15.32,-0.23 17.45,0.91"/><polygon points="26.60,12.00 24.33,12.82 24.25,15.23 22.77,13.33 20.45,14.00 21.80,12.00 20.45,10.00 22.77,10.67 24.25,8.77 24.33,11.18"/><polygon points="19.30,24.64 17.45,23.09 15.32,24.23 16.23,21.99 14.49,20.32 16.90,20.49 17.96,18.32 18.54,20.66 20.93,20.99 18.88,22.27"/></g><circle cx="12" cy="12" r="11" fill="none" stroke="#d9dee5" stroke-width="0.8"/></svg>')   # UCL-style starball, no text (user 2026-09-02)
_NF_ICON_EGY = ('<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">'
                '<clipPath id="nfeg"><circle cx="12" cy="12" r="11"/></clipPath>'
                '<g clip-path="url(#nfeg)"><rect x="0" y="0" width="24" height="8" fill="#ce1126"/>'
                '<rect x="0" y="8" width="24" height="8" fill="#ffffff"/>'
                '<rect x="0" y="16" width="24" height="8" fill="#000000"/>'
                '<circle cx="12" cy="12" r="2.3" fill="#c09300"/></g>'
                '<circle cx="12" cy="12" r="11" fill="none" stroke="#e2e8f0"/></svg>')

def _nf_icon_eur():
    """FotMob-style UCL starball (solid black, no text): the ball cut out of the
    football-data CL crest, inlined as a data URI. Falls back to the drawn SVG."""
    f = os.path.join(HERE, "assets-src", "ucl-starball.png")
    try:
        with open(f, "rb") as fh:
            b64 = base64.b64encode(fh.read()).decode("ascii")
        return (f'<img src="data:image/png;base64,{b64}" alt="" width="24" height="24" '
                'style="width:24px;height:24px">')
    except OSError:
        return _NF_ICON_EUR

def news_filter_bar():
    chips = [
        ("trend", "الأكثر تداولًا", _NF_ICON_TREND),
        ("egy", "أخبار الكرة المصرية", _NF_ICON_EGY),
        ("eur", "أخبار الكرة الأوروبية", _nf_icon_eur()),   # UCL starball, no text (user wants FotMob's)
    ]
    btns = "".join(
        f'<button type="button" class="nf-chip" data-nf="{k}" title="{esc(t)}" '
        f'aria-label="{esc(t)}" aria-pressed="false">{ico}</button>' for k, t, ico in chips)
    # Facebook follow button on the far end of the title row (user ask
    # 2026-09-04): the site's Google visitors don't know the page exists.
    # icon-only, both of them (user ask 2026-09-23: «شيل كلمة تابعنا») — the
    # title/aria keep the words for hover and screen readers
    fb = (f'<a class="nf-fb" href="{esc(FB_PAGE_URL)}" target="_blank" rel="noopener" '
          'title="تابعنا على فيسبوك" aria-label="تابعنا على فيسبوك">'
          '<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"><path fill="#fff" '
          'd="M13.5 22v-8.2h2.8l.4-3.3h-3.2V8.4c0-.9.3-1.6 1.6-1.6h1.7V3.9c-.3 0-1.3-.1-2.5-.1'
          '-2.5 0-4.2 1.5-4.2 4.3v2.4H7.3v3.3h2.8V22h3.4z"/></svg></a>')
    tg = (f'<a class="nf-tg" href="{esc(TG_CHANNEL_URL)}" target="_blank" rel="noopener" '
          'title="قناتنا على تيليجرام" aria-label="قناتنا على تيليجرام">'
          '<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"><path fill="#fff" '
          'd="M21.9 4.3 18.9 19c-.2 1-.8 1.2-1.7.8l-4.6-3.4-2.2 2.1c-.3.3-.5.5-.9.5l.3-4.6L18.2 7'
          'c.4-.3-.1-.5-.6-.2L7.4 13.2 3 11.8c-1-.3-1-1 .2-1.4l17.3-6.7c.8-.3 1.6.2 1.4 1.6z"/>'
          '</svg></a>')
    return ('<div class="nf-bar"><h1 class="page-h">آخر الأخبار</h1>'
            f'<div class="nf-chips" role="group" aria-label="فلتر الأخبار">{btns}</div>{fb}{tg}</div>'
            + NEWS_FILTER_JS)

NEWS_FILTER_JS = """<script>
(function(){
  /* FotMob behaviour (user, 2026-09-02): a chip JUMPS to its block — nothing
     is hidden. The highlighted chip follows the block in view (scroll-spy).
     Runs after DOMContentLoaded: the bar renders before the blocks. */
  if(document.readyState==='loading'){ document.addEventListener('DOMContentLoaded',init); } else { init(); }
  function init(){
    var bar=document.querySelector('.nf-bar'); if(!bar) return;
    var chips=[].slice.call(bar.querySelectorAll('.nf-chip'));
    var blocks=[].slice.call(document.querySelectorAll('.fmb[data-nf]'));
    if(!blocks.length) return;
    var byKey={}; blocks.forEach(function(b){ byKey[b.getAttribute('data-nf')]=b; });
    chips.forEach(function(c){ if(!byKey[c.getAttribute('data-nf')]) c.hidden=true; });
    var head=document.querySelector('.site-head');
    function offset(){ return (head?head.offsetHeight:0)+12; }
    function mark(key){
      chips.forEach(function(c){ var on=c.getAttribute('data-nf')===key;
        c.classList.toggle('is-on',on); c.setAttribute('aria-pressed',on?'true':'false'); });
    }
    var lock=0;
    chips.forEach(function(c){ c.addEventListener('click',function(){
      var b=byKey[c.getAttribute('data-nf')]; if(!b) return;
      mark(c.getAttribute('data-nf')); lock=Date.now()+900;
      var y=b.getBoundingClientRect().top+window.pageYOffset-offset();
      /* smooth where supported; older Safari ignores the options object entirely */
      if('scrollBehavior' in document.documentElement.style){ window.scrollTo({top:y,behavior:'smooth'}); }
      else { window.scrollTo(0,y); }
    }); });
    /* scroll-spy: the block whose top is nearest below the sticky header wins */
    function spy(){
      if(Date.now()<lock) return;
      var off=offset(), best=null, bestD=Infinity;
      blocks.forEach(function(b){ var r=b.getBoundingClientRect();
        if(r.bottom<=off) return;                       /* already scrolled past */
        var d=Math.abs(r.top-off); if(d<bestD){ bestD=d; best=b; } });
      mark(best?best.getAttribute('data-nf'):'');
    }
    var t=null;
    window.addEventListener('scroll',function(){ if(t) return; t=setTimeout(function(){ t=null; spy(); },80); },{passive:true});
    spy();
  }
})();
</script>"""

def fmb_block(feat_a, list_items, list_head, more_url, banner="", flip=False, nf=""):
    """FotMob-style home block: one featured card (image + title) beside a
    numbered trending-list column with thumbnails and 'منذ X' bylines.
    flip=True mirrors the columns (featured LEFT, list RIGHT) for visual
    alternation between consecutive blocks."""
    img = thumb_url(feat_a.get("image_url"))
    imgdiv = (f'<div class="fmb-img" style="background-image:url(\'{esc(img)}\')"></div>'
              if img else '<div class="fmb-img fmb-noimg"></div>')
    _nf = f' data-nf="{nf}"' if nf else ""     # news-filter key (NEWS_FILTER_JS)
    out = [f'<section class="fmb fmb-flip"{_nf}>' if flip else f'<section class="fmb"{_nf}>']
    out.append(f'<a class="fmb-feat" href="{article_href(feat_a)}">'
               + (f'<div class="fmb-banner">{banner}</div>' if banner else "")
               + imgdiv
               + f'<div class="fmb-fb"><h2>{esc(feat_a["title"])}</h2>'
               + f'<p class="fmb-meta">{_art_meta(feat_a)}</p></div></a>')
    out.append(f'<div class="fmb-list"><div class="fmb-lh">{esc(list_head)}</div>')
    for i, a in enumerate(list_items, 1):
        th = (f'<img class="fmb-th" src="{esc(thumb_url(a.get("image_url")))}" alt="" loading="lazy">'
              if a.get("image_url") else "")
        out.append(f'<a class="fmb-row" href="{article_href(a)}">'
                   f'<span class="fmb-num">{i}</span>'
                   f'<span class="fmb-rt"><b>{esc(a["title"])}</b>'
                   f'<small>{_art_meta(a)}</small></span>{th}</a>')
    out.append(f'<a class="fmb-more" href="{more_url}">المزيد ←</a></div></section>')
    return "".join(out)


def pred_home_block(upcoming, preds, today, n=4, acc=None, cal=None):
    """«توقعات يلا سكور» on the home page (user ask 2026-09-12): the next few
    predicted fixtures, in the same card language as the FotMob blocks, with
    المزيد opening /analysis.html. Picks matches within 7 days that HAVE a
    prediction, curated clubs first, then the Egyptian league, then kickoff.
    Rows are pred_row() - the same markup the analysis pages use - so a
    number here is never a second rendering of the same prediction."""
    wk = (today + datetime.timedelta(days=7)).isoformat()
    cand = []
    for m in upcoming:
        p = preds.get(str(m.get("match_id")))
        if not p or (m.get("kickoff") or "") > wk:
            continue
        cand.append((0 if _is_ticker_team(m) else 1,
                     0 if m.get("competition") == "Egyptian Premier League" else 1,
                     m.get("kickoff") or "", m.get("koff_time") or "", m, p))
    cand.sort(key=lambda t: t[:4])
    rows = [(m, p) for *_, m, p in cand[:n]]
    if not rows:
        return ""
    # The record line (2026-09-16). Every scores site shows predictions; what
    # separates this one is that it publishes how those predictions turned out,
    # and that was two clicks away. Calibration leads because it is the measure
    # that judges a probabilistic model - the same order /predictions uses - and
    # the naive baseline sits next to the hit rate so the rate cannot flatter
    # us. Silent until something has actually been scored.
    a = (acc or {}).get("all")
    rec = ""
    if a and cal and cal.get("matches"):
        rec = (f'<a class="pred-rec" href="/predictions.html">'
               f'سجلنا مفتوح: <b>{cal["statements"]}</b> احتمالًا معلنًا على '
               f'<b>{cal["matches"]}</b> مباراة — انحراف المعايرة '
               f'<b>{cal["ece"] * 100:.1f}</b> نقطة، وإصابة الاتجاه '
               f'<b>{_pct(a["hit_rate"])}</b> مقابل {_pct(a["home_baseline"])} '
               f'لمعيار ساذج. إصاباتنا وأخطاؤنا كاملة ←</a>')
    return ('<section class="fmb fmb-pred" data-nf="pred">'
            '<div class="fmb-lh fmb-predh"><span>توقعات يلا سكور</span>'
            '<small>احتمالات إحصائية من نتائج الموسم · ليست نصيحة للمراهنة</small></div>'
            + rec +
            '<div class="plist">' + "".join(pred_row(m, p) for m, p in rows) + '</div>'
            '<a class="fmb-more" href="/analysis.html">كل التوقعات والتحليلات ←</a></section>')

# home block 2 filter: Egyptian-football stories (clubs, league, NT)
_EGY_TOKENS = ["الأهلي", "الزمالك", "بيراميدز", "الدوري المصري",
               "منتخب مصر", "كأس مصر"]

def _egy_article(a):
    txt = (a.get("title") or "") + " " + (a.get("summary") or "")
    if "الأهلي السعودي" in txt or "أهلي جدة" in txt:
        return False
    return any(t in txt for t in _EGY_TOKENS)

# home block 3 filter: European-football stories (big clubs + leagues).
# Runs AFTER the Egyptian block, so a story naming both (بيراميدز يفاوض
# لاعب برشلونة) lands in the Egyptian block and never duplicates here.
_EUR_TOKENS = ["ريال مدريد", "برشلونة", "مانشستر يونايتد", "مانشستر سيتي",
               "أرسنال", "آرسنال", "ليفربول", "تشيلسي", "توتنهام",
               "نيوكاسل", "بايرن ميونخ", "بوروسيا دورتموند",
               "باريس سان جيرمان", "يوفنتوس", "إنتر ميلان", "ميلان",
               "نابولي", "أتلتيكو مدريد", "الدوري الإنجليزي",
               "الدوري الإسباني", "الدوري الإيطالي", "الدوري الألماني",
               "الدوري الفرنسي", "دوري أبطال أوروبا", "الدوري الأوروبي",
               "طرابزون سبور"]

def _eur_article(a):
    txt = (a.get("title") or "") + " " + (a.get("summary") or "")
    return any(t in txt for t in _EUR_TOKENS)

def reel_slide(r, first=False):
    """One full-height slide of the TikTok-style vertical feed: tap to play
    (VIDEO_JS facade), swipe up for the next (CSS scroll-snap)."""
    vid = esc(r.get("video_id") or "")
    title = esc(r.get("title") or "")
    thumb = f"https://i.ytimg.com/vi/{vid}/oar2.jpg"          # vertical thumb
    fallback = f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"  # crop if missing
    hint = '<div class="swipe-hint">اسحب لفوق للريل التالي ⬆</div>' if first else ""
    return (f'<section class="rslide">'
            f'<div class="vcard reel rstage" data-vid="{vid}" data-src="youtube">'
            f'<button type="button" class="vthumb" aria-label="تشغيل: {title}">'
            f'<img src="{thumb}" alt="{title}" loading="lazy" '
            f'onerror="this.onerror=null;this.src=\'{fallback}\'">'
            f'<span class="vplay" aria-hidden="true">▶</span></button>'
            f'<div class="rtitle">{title}</div>{hint}'
            f'</div></section>')

# fixed section order on /videos.html; a section with no videos is not rendered
VIDEO_CATS = [
    ("wc",     "🏆 فيديوهات كأس العالم 2026"),
    ("epl",    "🦁 فيديوهات الدوري الإنجليزي 2026-2027"),
    ("laliga", "🇪🇸 فيديوهات الدوري الإسباني 2026-2027"),
    ("misc",   "⚽ متنوعات كروية"),
]

def video_facade(v):
    """A lightweight video 'facade': thumbnail + play button; the real iframe
    is injected by VIDEO_JS only when the visitor clicks (keeps the page fast).
    Supports source = "youtube" (default) | "dailymotion"."""
    vid = esc(v.get("video_id") or "")
    src = (v.get("source") or "youtube").lower()
    title = esc(v.get("title") or "")
    date = esc(v.get("pub_date") or "")
    if src == "dailymotion":
        thumb = f"https://www.dailymotion.com/thumbnail/video/{vid}"
    else:
        src = "youtube"
        thumb = f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"
    meta = f'<p class="meta">{date}</p>' if date else ""
    return (f'<div class="vcard" data-vid="{vid}" data-src="{src}">'
            f'<button type="button" class="vthumb" aria-label="تشغيل الفيديو: {title}">'
            f'<img src="{thumb}" alt="{title}" loading="lazy" '
            f'onerror="this.style.display=\'none\';this.parentNode.classList.add(\'noimg\')">'
            f'<span class="vplay" aria-hidden="true">▶</span></button>'
            f'<div class="vb"><h3>{title}</h3>{meta}</div></div>')

# ---------------------------------------------------------------- build
# ---------------------------------------------------------------- تحليلات (rendering)
# Official-post embeds under an article (user ask 2026-09-13: «النقطة 1» -
# the club's own X / Instagram / Facebook post, the one legal way to show a
# professional photo of the event without a licence: the platform serves it).
# Rendered as a CARD that loads the platform's script only when the reader
# clicks - nothing third-party on page load (speed, AdSense, privacy). Without
# JS the card is a plain link to the post.
EMBED_LABEL = {"x": "X (تويتر)", "instagram": "إنستغرام", "facebook": "فيسبوك"}


def embed_platform(url):
    return store.embed_platform(url)


def embeds_block(urls):
    items = [(u, embed_platform(u)) for u in (urls or []) if isinstance(u, str)]
    items = [(u, p) for u, p in items if p]
    if not items:
        return ""
    cards = []
    for u, p in items:
        short = re.sub(r"^https://(www\.)?", "", u)
        short = short if len(short) <= 60 else short[:57] + "…"
        cards.append(f'<div class="emb" data-p="{p}" data-u="{esc(u)}">'
                     f'<div class="emb-h"><span class="emb-ico emb-{p}"></span><b>منشور رسمي على {EMBED_LABEL[p]}</b></div>'
                     f'<a class="emb-l" href="{esc(u)}" target="_blank" rel="noopener nofollow">{esc(short)}</a>'
                     f'<button type="button" class="emb-b">عرض المنشور</button></div>')
    return ('<section class="a-embeds"><h2>من الحسابات الرسمية</h2>'
            '<p class="hintline">يُحمَّل المنشور من منصته عند الضغط فقط، وتنطبق عليه سياسة خصوصية تلك المنصة.</p>'
            + "".join(cards) + '</section>' + EMBED_JS)


EMBED_JS = r"""<script>(function(){if(window.__ye)return;window.__ye=1;
var L={};function need(src,id,done){if(L[src]){done();return}var s=document.createElement('script');s.src=src;s.async=true;s.onload=function(){L[src]=1;done()};document.head.appendChild(s)}
document.addEventListener('click',function(e){var b=e.target.closest('.emb-b');if(!b)return;var c=b.closest('.emb'),p=c.getAttribute('data-p'),u=c.getAttribute('data-u');
b.disabled=true;b.textContent='جارٍ التحميل…';var box=document.createElement('div');box.className='emb-box';c.appendChild(box);
if(p==='x'){box.innerHTML='<blockquote class="twitter-tweet" dir="rtl"><a href="'+u+'"></a></blockquote>';need('https://platform.twitter.com/widgets.js','x',function(){if(window.twttr&&twttr.widgets)twttr.widgets.load(box)})}
else if(p==='instagram'){box.innerHTML='<blockquote class="instagram-media" data-instgrm-permalink="'+u+'" data-instgrm-version="14" style="margin:0 auto;max-width:540px;width:100%"></blockquote>';need('https://www.instagram.com/embed.js','ig',function(){if(window.instgrm)instgrm.Embeds.process()})}
else if(p==='facebook'){if(!document.getElementById('fb-root')){var r=document.createElement('div');r.id='fb-root';document.body.appendChild(r)}box.innerHTML='<div class="fb-post" data-href="'+u+'" data-width="500" data-show-text="true"></div>';need('https://connect.facebook.net/ar_AR/sdk.js#xfbml=1&version=v20.0','fb',function(){if(window.FB&&FB.XFBML)FB.XFBML.parse(box)})}
b.remove();});})();</script>"""


AN_DISCLAIMER = ('التوقعات احتمالات إحصائية من نموذج يلا سكور مبنية على نتائج الموسم الحالي فقط، '
                 'وليست نصيحة للمراهنة. كلما زاد عدد المباريات زادت دقة النموذج.')

def _pct(x):
    return f"{round(x * 100)}%"

def pred_btn(p):
    """«توقع يلا سكور» — the whole prediction on a match row, in ~110 bytes.

    The site's one differentiator was reachable only from /m/<id> or
    /analysis, and the numbers said nobody went: over 24 hours the home page
    and /matches were ~85% of all traffic and exactly one match page showed
    up at all, twice (2026-09-18). So the prediction now offers itself where
    the reader already is.

    What crosses the wire per row is five small numbers, not a rendered
    block: three probabilities, the modal scoreline and the confidence key.
    /matches is already a 1 MB page with 13% of its LCP samples in the
    "poor" band, so ~110 bytes x ~90 rows (about 10 KB, below the fold and
    behind a click) is the whole budget this feature gets. Everything else -
    the team names, the bar, the link to the full reading - is read at click
    time from markup the row already carries.
    """
    if not p:
        return ""
    top = p["top"][0]
    return ('<button type="button" class="pbtn" data-pp="'
            f'{round(p["ph"] * 100)},{round(p["pd"] * 100)},{round(p["pa"] * 100)}"'
            f' data-ps="{top[0]}-{top[1]}" data-pc="{esc(p["conf"])}">'
            'توقع يلا سكور</button>')


def done_btn(e):
    """«توقعنا قبل المباراة» — the same button on a match that is over.

    Stronger than the pre-match one, and for one reason: a probability
    before kickoff is a claim, a probability beside the final score is a
    claim the reader can CHECK. That is the whole point of /predictions,
    and /predictions is a page nobody visits — /matches is where they are.

    Everything here comes from the FROZEN log row, written the day the
    prediction was made and never touched again (analysis.update_log:
    `if old.get("hs") is not None: continue`). Recomputing it today from
    today's Elo would be marking our own homework with the answers in
    front of us, and it would quietly turn the site's one honest number
    into a lie. `hit` is carried rather than derived for the same reason:
    the log decides what counted, not this renderer.

    And it appears on the misses exactly as it does on the hits — 21 of
    the 54 finished rows in today's window were wrong. A button that only
    showed up when we were right would destroy the credibility it exists
    to build.
    """
    if not e or e.get("hs") is None or e.get("as") is None:
        return ""     # in the log but not played yet, or never scored
    return ('<button type="button" class="pbtn" data-pp="'
            f'{round(e["ph"] * 100)},{round(e["pd"] * 100)},{round(e["pa"] * 100)}"'
            f' data-ps="{esc(e.get("score") or "")}"'
            f' data-pr="{e["hs"]}-{e["as"]}"'
            f' data-hit="{1 if e.get("hit") else 0}">'
            'توقعنا قبل المباراة</button>')


# Everything here is namespaced ppop-*, NOT pp-*: «.pp» and its family
# (.pp-ava, .pp-fb) are the player markers on the pitch graphic, and the last
# two class collisions in this stylesheet (.tl, .pp) both shipped broken to
# the user's phone. A JS hook that shares a prefix with a positioned element
# is the same bug waiting.
#
# The dialog is ONE element per page, filled at click time from the button's
# data- attributes and the row around it. It ends with a link to the match
# page rather than restating what is there: the popup answers the question,
# the page explains the answer, and the click that follows is earned instead
# of being the only way in.
PRED_POP = """<dialog id="ppop" class="ppop" aria-labelledby="ppop-ttl">
<div class="ppop-in">
  <div class="ppop-hd"><h3 id="ppop-ttl">توقع يلا سكور</h3>
    <form method="dialog"><button class="ppop-x" aria-label="إغلاق">×</button></form></div>
  <p class="ppop-t"><bdi class="ppop-nh"></bdi> <span>×</span> <bdi class="ppop-na"></bdi></p>
  <p class="ppop-m"><span class="ppop-fav"></span><span class="ppop-cf"></span></p>
  <div class="pbar"><span class="pb-seg pb-h"></span><span class="pb-seg pb-d"></span><span class="pb-seg pb-a"></span></div>
  <p class="ppop-probs pr-probs"></p>
  <p class="ppop-res" hidden>النتيجة <b class="ppop-rv sc-in"></b></p>
  <p class="ppop-s"><span class="ppop-slab">النتيجة الأكثر احتمالًا</span> <b class="ppop-val sc-in"></b></p>
  <p class="ppop-d">احتمالات إحصائية من نموذج يلا سكور مبنية على نتائج الموسم الحالي، وليست نصيحة للمراهنة.</p>
  <a class="ppop-go" href="#">لماذا رجّح النموذج هذا التوقع؟ ←</a>
  <a class="ppop-rec" href="/predictions.html" hidden>السجل الكامل، إصابةً وخطأ ←</a>
</div>
</dialog>
<script>(function(){
var d=document.getElementById("ppop");if(!d)return;
var CF=__CONF_AR__;
var q=function(s){return d.querySelector(s)};
var seg=[q(".pb-h"),q(".pb-d"),q(".pb-a")];
// "2-1" as one text run reverses in RTL and the reader meets the AWAY
// number first (the standing score_pill() rule) - so build the same
// span/i/span pill the rest of the site uses. Seen on a phone render:
// the model's 2-1 for the home side displayed as 1-2.
function pill(el,s){var x=(s||"").split("-");
  el.innerHTML=x.length>1?"<span>"+x[0]+"</span><i>-</i><span>"+x[1]+"</span>":"";}
function shut(){if(d.close){d.close()}else{d.removeAttribute("open");d.classList.remove("ppop-open")}}
document.addEventListener("click",function(e){
  var b=e.target.closest?e.target.closest(".pbtn"):null;if(!b)return;
  e.preventDefault();e.stopPropagation();
  var r=b.closest(".mrow"),p=(b.getAttribute("data-pp")||"").split(",");
  if(p.length<3)return;
  var h=(r&&r.getAttribute("data-h"))||"الأرض",a=(r&&r.getAttribute("data-a"))||"الضيف";
  q(".ppop-nh").textContent=h;q(".ppop-na").textContent=a;
  for(var i=0;i<3;i++){seg[i].style.width=p[i]+"%"}
  q(".ppop-probs").innerHTML=
    '<span class="prb"><i class="prb-h"></i>'+h+' <b>'+p[0]+'%</b></span>'+
    '<span class="prb"><i class="prb-d"></i>تعادل <b>'+p[1]+'%</b></span>'+
    '<span class="prb"><i class="prb-a"></i>'+a+' <b>'+p[2]+'%</b></span>';
  var ph=+p[0],pd=+p[1],pa=+p[2],top=Math.max(ph,pd,pa);
  var fav=ph>=pd&&ph>=pa?h:(pa>=pd?a:null);      // null = the draw
  // A finished row carries the real result; that attribute IS the switch
  // between "here is what we think" and "here is what we said, check us".
  var res=b.getAttribute("data-pr"),fin=!!res,cf=q(".ppop-cf");
  q("#ppop-ttl").textContent=fin?"توقعنا قبل المباراة":"توقع يلا سكور";
  // The verdict is on the OUTCOME, never on the scoreline. 42% on the home
  // win that then happened is a hit even though the 1-1 we called closest
  // ended 3-2 - and a green tick beside "توقعنا 1-1 · 3-2" reads like a
  // joke at the reader's expense. So the claim line states the outcome and
  // its probability, and the scoreline is demoted and relabelled below.
  q(".ppop-fav").textContent=fin
    ?("قلنا: "+(fav===null?"التعادل":"فوز "+fav)+" "+top+"%")
    :("الأرجح: "+(fav===null?"التعادل":fav));
  // keep the hook class: assigning className wholesale used to drop
  // "ppop-cf", so the very next lookup returned null, the handler threw
  // before showModal() and NOTHING opened. Caught on a phone-width render.
  if(fin){var w=b.getAttribute("data-hit")==="1";
    cf.className="ppop-cf hit "+(w?"ok":"no");cf.textContent=w?"✔ أصاب":"✘ لم يُصب"}
  else{var c=b.getAttribute("data-pc")||"";
    cf.className="ppop-cf conf conf-"+c;cf.textContent=CF[c]||""}
  pill(q(".ppop-rv"),res);q(".ppop-res").hidden=!fin;
  q(".ppop-slab").textContent=fin?"أقرب نتيجة رجّحها النموذج":"النتيجة الأكثر احتمالًا";
  pill(q(".ppop-val"),b.getAttribute("data-ps"));
  var s=r&&r.querySelector(".mstretch"),g=q(".ppop-go");
  g.textContent=fin?"قراءة المباراة ←":"لماذا رجّح النموذج هذا التوقع؟ ←";
  if(s){g.href=s.getAttribute("href");g.hidden=false}else{g.hidden=true}
  // one week of 33 right out of 54 is not the record (the season is
  // 45-54%). The way out to the full log is what stops a lucky window
  // being read as the performance.
  q(".ppop-rec").hidden=!fin;
  if(d.showModal){d.showModal()}else{d.setAttribute("open","");d.classList.add("ppop-open")}
});
d.addEventListener("click",function(e){if(e.target===d)shut()});
// Escape: a modal <dialog> is supposed to close itself, and in the preview
// pane it does not - the keydown arrives at the document and the dialog
// stays open. Sixty bytes is cheaper than trusting that.
document.addEventListener("keydown",function(e){if(e.key==="Escape"&&d.open)shut()});
})();</script>"""
PRED_POP = PRED_POP.replace("__CONF_AR__",
                            json.dumps(AN.CONF_AR, ensure_ascii=False))


def pred_pop(parts):
    """The dialog — but only on a page that actually rendered a button.

    A club page whose next fixture has no prediction, or a standings page in a
    gap between rounds, would otherwise carry 2.6 KB of markup nothing can
    open."""
    return PRED_POP if any('class="pbtn"' in x for x in parts) else ""


def prob_bar(p):
    """Three-segment 1X2 bar (home = brand blue, draw = grey, away = slate).

    PURELY VISUAL since 2026-09-16: the numbers used to be printed inside the
    segments, but a number does not fit in a narrow one, so a lopsided
    prediction rendered as "20% 72%" or "87%" — two outside reviewers read that
    as a missing third probability, twice. A bar that states two of three
    numbers and a line underneath that states all three is two partial
    readings of one thing; if a reviewer is confused by it, a reader is too.
    So the bar shows the shape and prob_legend() says the numbers, once.
    """
    ph, pd, pa = p["ph"], p["pd"], p["pa"]
    def seg(cls, v):
        return f'<span class="pb-seg pb-{cls}" style="width:{v * 100:.1f}%"></span>' 
    return ('<div class="pbar" role="img" aria-label="'
            f'فوز الأرض {_pct(ph)}، تعادل {_pct(pd)}، فوز الضيف {_pct(pa)}">'
            + seg("h", ph) + seg("d", pd) + seg("a", pa) + '</div>')

def prob_legend(p, cls="pr-probs", home=None, away=None):
    """The three probabilities in words — and the bar's key.

    Each one carries a swatch in its segment's colour, so the reader can see
    which slice is which without a number being crammed into a 12-pixel
    segment. This is the ONLY place the percentages are printed (see
    prob_bar), which is the point: one statement, never a partial one."""
    def one(k, label, cls_):
        # .prb, not .pp: «.pp» is already the player marker on the pitch
        # graphic (position:absolute) and these three collapsed onto the bar
        return (f'<span class="prb"><i class="prb-{cls_}"></i>{esc(label)} '
                f'<b>{_pct(p[k])}</b></span>')
    # The clubs by NAME whenever the caller knows them (user, 2026-09-18:
    # «خلى هنا اسماء الفرق»). الأرض/الضيف is the fallback for a caller that
    # has only the numbers — it makes the reader map a generic word onto a
    # club that is written two lines up, which is work the page can do.
    return (f'<span class="{cls}">' + one("ph", home or "الأرض", "h")
            + one("pd", "تعادل", "d") + one("pa", away or "الضيف", "a") + '</span>')

def conf_chip(conf):
    return f'<span class="conf conf-{esc(conf)}">{esc(AN.CONF_AR.get(conf, ""))}</span>'

def pred_row(m, p):
    """Compact prediction row for the analysis pages (links to the match page)."""
    h, a = ar_team(m.get("home")), ar_team(m.get("away"))
    def crest(u):
        return f'<img src="{esc(local_crest(u))}" alt="" loading="lazy">' if u else '<span class="ph">⚽</span>'
    top = p["top"][0]
    link = match_url(m) or "#"
    when = f'{_tk_date(m.get("kickoff"))}{(" · " + m["koff_time"]) if m.get("koff_time") else ""}'
    fav = h if p["ph"] >= max(p["pd"], p["pa"]) else a if p["pa"] >= p["pd"] else "التعادل"
    return (f'<a class="prow" href="{esc(link)}">'
            f'<span class="pr-when">{esc(when)}</span>'
            f'<span class="pr-teams"><span class="pr-t">{crest(m.get("home_badge"))}<bdi>{esc(h)}</bdi></span>'
            f'<span class="pr-vs">×</span>'
            f'<span class="pr-t">{crest(m.get("away_badge"))}<bdi>{esc(a)}</bdi></span></span>'
            + f'<span class="pr-bw">{prob_bar(p)}{prob_legend(p, home=h, away=a)}</span>' +
            f'<span class="pr-meta">'
            f'<span class="pr-fav">الأرجح: <b>{esc(fav)}</b></span>'
            # score_pill, not a bare "2-1": as one LTR run the HOME number
            # lands on the away side and an RTL reader gets the prediction
            # backwards. Same bug the record page was fixed for on
            # 2026-09-16; measured still live here on 2026-09-18, the home
            # 2 sitting under the away club.
            f'<span class="pr-score">النتيجة الأكثر احتمالًا '
            + score_pill(top[0], top[1], "sc-in") + '</span>'
            + conf_chip(p["conf"]) + '</span></a>')

def _signed_pct(x):
    """+24% / -18%, for a factor's distance from the league average."""
    return ("+" if x >= 0 else "−") + f"{abs(x) * 100:.0f}%"

def why_block(m, p, ex, cal):
    """«لماذا رجّح النموذج هذا التوقع؟» — the prediction taken apart.

    Every site in this market shows a score and a table. What none of them
    shows is the arithmetic behind its own number, and that is the one page
    element here that cannot be copied from a feed: each line below is a term
    that appears literally in analysis.lambdas(), printed with this match's
    values (AN.explain returns them, it does not re-derive anything).

    It also ends with the model's own track record AT THIS confidence — from
    the frozen log, so a confident-looking prediction carries the rate at
    which past confident predictions actually came true. A number that
    explains itself and then admits how often it has been wrong is the
    opposite of the scaled, templated page Google penalises.

    Silent when the league has no finished matches to average (a pre-season
    table tells us nothing) - the same rule the readings follow.
    """
    if not ex or not p or (ex["n_h"] == 0 and ex["n_a"] == 0):
        return ""
    # The published prediction may come from the ORACLE model (the nightly
    # PL/SQL file, when it is fresh) while explain() re-derives python's
    # lambdas. The two are meant to be identical - that is the standing rule,
    # and 10/10 leagues matched when it was set. If they ever drift, the
    # decomposition would be describing a DIFFERENT prediction than the one on
    # the page, so say nothing rather than something that does not add up.
    if abs(ex["lh"] - p.get("lh", ex["lh"])) > 0.05 or \
       abs(ex["la"] - p.get("la", ex["la"])) > 0.05:
        return ""
    h, a = ar_team(m.get("home")), ar_team(m.get("away"))
    li = []
    li.append(f'<li><b>نقطة البداية — متوسط هذا الدوري:</b> صاحب الأرض يسجّل '
              f'{ex["mu_home"]:.2f} هدف في المباراة والضيف {ex["mu_away"]:.2f}.</li>')
    # the two clubs' own numbers, each against the league average
    def side(club, d_att, d_def_other, other):
        bits = []
        if abs(d_att) >= 0.05:
            bits.append(f'هجوم {esc(club)} {_signed_pct(d_att)} عن متوسط الدوري')
        else:
            bits.append(f'هجوم {esc(club)} عند متوسط الدوري تقريبًا')
        if abs(d_def_other) >= 0.05:
            # the word carries the direction, so the number must not carry it
            # too ("يستقبل −14% أقل" is a double negative)
            bits.append(f'ودفاع {esc(other)} يستقبل {abs(d_def_other) * 100:.0f}% '
                        f'{"أكثر" if d_def_other > 0 else "أقل"} من المتوسط')
        return " ".join(bits)
    li.append(f'<li><b>{esc(h)}:</b> {side(h, ex["d_att_h"], ex["d_def_a"], a)}.</li>')
    li.append(f'<li><b>{esc(a)}:</b> {side(a, ex["d_att_a"], ex["d_def_h"], h)}.</li>')
    if abs(ex["elo_edge"]) >= 0.01:
        li.append(f'<li><b>فارق القوة:</b> تقييم {esc(h)} {round(ex["elo_h"])} مقابل '
                  f'{round(ex["elo_a"])} لـ{esc(a)}، ويضيف النموذج {round(ex["elo_hfa"])} '
                  f'نقطة لعامل الأرض — الأثر {_signed_pct(ex["elo_edge"])} على أرقام '
                  f'{esc(h)} ومثلها في الاتجاه المعاكس على أرقام {esc(a)}.</li>')
    li.append(f'<li><b>الناتج:</b> {ex["lh"]:.1f} هدف متوقع لـ{esc(h)} و{ex["la"]:.1f} '
              f'لـ{esc(a)}، ومن توزيع بواسون على هذين الرقمين تخرج النسب '
              f'{_pct(p["ph"])} و{_pct(p["pd"])} و{_pct(p["pa"])}.</li>')
    top = max(p["ph"], p["pd"], p["pa"])
    b = AN.stated_bucket(cal, top)
    rec = ""
    if b:
        rec = (f'<p class="pd-note">وللأمانة: في المرات السابقة التي قال فيها النموذج '
               f'احتمالًا بين {b["lo"]}% و{b["hi"]}%، تحقّق ما قاله في '
               f'<b>{b["hits"]}</b> من <b>{b["n"]}</b> مرة. '
               f'<a href="/predictions.html">السجل كاملًا</a>.</p>')
    small = ""
    if min(ex["n_h"], ex["n_a"]) < 4:
        small = ('<p class="pd-note">عدد المباريات المنتهية لأحد الفريقين هذا الموسم قليل، '
                 'فالأرقام أعلاه تميل إلى متوسط الدوري أكثر من الطبيعي.</p>')
    return (f'<section class="minfo predict why"><h2>لماذا رجّح النموذج هذا التوقع؟</h2>'
            f'<p class="pd-line">النموذج لا يقرأ الأخبار — يحسب. وهذه هي الأرقام نفسها '
            f'التي دخلت المعادلة:</p><ul class="why-list">' + "".join(li) + '</ul>'
            + small + rec + '</section>')

def pred_block(m, p, logged, comp_stats, params=None, cal=None):
    """«توقع يلا سكور» section on a match page. Upcoming: live model output.
    Finished (with a frozen prediction): what we said vs what happened."""
    h, a = ar_team(m.get("home")), ar_team(m.get("away"))
    st = (m.get("status") or "").upper()
    if st == "UPCOMING" and p:
        top = " · ".join(f'<b>{i}-{j}</b> ({_pct(q)})' for i, j, q in p["top"])
        hs, as_ = comp_stats.get(m.get("home")), comp_stats.get(m.get("away"))
        facts = []
        if hs and hs["played"]:
            facts.append(f'{esc(h)}: {_goals(hs["gf"])} له و{_goals(hs["ga"])} عليه في {AN_games(hs["played"])} '
                         f'(تقييم القوة {round(hs["elo"])})')
        if as_ and as_["played"]:
            facts.append(f'{esc(a)}: {_goals(as_["gf"])} له و{_goals(as_["ga"])} عليه في {AN_games(as_["played"])} '
                         f'(تقييم القوة {round(as_["elo"])})')
        return (f'<section class="minfo predict"><h2>توقع يلا سكور لمباراة {esc(h)} و{esc(a)}</h2>'
                f'<div class="pd-heads"><span>{esc(h)} <b>{_pct(p["ph"])}</b></span>'
                f'<span>تعادل <b>{_pct(p["pd"])}</b></span><span>{esc(a)} <b>{_pct(p["pa"])}</b></span></div>'
                + prob_bar(p) +
                f'<p class="pd-line">الأهداف المتوقعة: <b>{p["lh"]:.1f}</b> لـ{esc(h)} و<b>{p["la"]:.1f}</b> لـ{esc(a)} · '
                f'أكثر من 2.5 هدف: <b>{_pct(p["over25"])}</b> · يسجل الفريقان: <b>{_pct(p["btts"])}</b></p>'
                f'<p class="pd-line">النتائج الأكثر احتمالًا: {top}</p>'
                + (f'<p class="pd-facts">{" — ".join(facts)}</p>' if facts else "")
                + f'<p class="pd-note">{conf_chip(p["conf"])} {AN_DISCLAIMER} '
                  '<a href="/analysis.html">كيف يعمل النموذج؟</a></p></section>'
                + (why_block(m, p, AN.explain(comp_stats, params, m.get("home"), m.get("away")),
                             cal) if params else ""))
    if st == "FINISHED" and logged and logged.get("hs") is not None:
        pick_ar = {"H": f"فوز {h}", "D": "التعادل", "A": f"فوز {a}"}[logged["pick"]]
        verdict = ('<span class="hit ok">✔ أصاب التوقع</span>' if logged.get("hit")
                   else '<span class="hit no">✘ لم يُصب التوقع</span>')
        fake = {"ph": logged["ph"], "pd": logged["pd"], "pa": logged["pa"]}
        return (f'<section class="minfo predict"><h2>ماذا توقع نموذج يلا سكور قبل المباراة؟</h2>'
                + prob_bar(fake) +
                f'<p class="pd-line">{prob_legend(fake, "pd-probs", h, a)}</p>'
                f'<p class="pd-line">رجّح النموذج <b>{esc(pick_ar)}</b> باحتمال {_pct(max(fake.values()))} '
                f'ونتيجة <b>{esc(logged.get("score", ""))}</b>، وانتهت المباراة <b>{logged["hs"]}-{logged["as"]}</b>. {verdict}</p>'
                f'<p class="pd-note">{AN_DISCLAIMER} <a href="/predictions.html">سجل التوقعات كاملًا (إصابةً وخطأ)</a></p></section>')
    return ""

def AN_games(n):
    return _games(n)

def power_table(comp, stats, params, form_map):
    """Club strength table for one competition, ranked by Elo."""
    rows = sorted(stats.values(), key=lambda r: -r["elo"])
    if not rows:
        return ""
    mu = params["mu"]
    out = ['<div class="tbl-wrap"><table class="ptable"><thead><tr>'
           '<th>#</th><th class="tl">النادي</th><th title="تقييم القوة (Elo)">القوة</th><th>لعب</th>'
           '<th title="أهداف له لكل مباراة">له/م</th><th title="أهداف عليه لكل مباراة">عليه/م</th>'
           '<th title="مؤشر الهجوم مقارنة بمتوسط الدوري">هجوم</th><th title="مؤشر الدفاع مقارنة بمتوسط الدوري (الأقل أفضل)">دفاع</th>'
           '<th>ن/م</th><th>آخر 5</th></tr></thead><tbody>']
    for i, r in enumerate(rows, 1):
        att, dfc = AN.strength(r, mu)
        pg = r["played"] or 1
        crest = f'<img src="{esc(local_crest(r["badge"]))}" alt="" loading="lazy">' if r.get("badge") else ""
        out.append(f'<tr><td>{i}</td><td class="tl">{crest}<bdi>{esc(ar_team(r["team"]))}</bdi></td>'
                   f'<td><b>{round(r["elo"])}</b></td><td>{r["played"]}</td>'
                   f'<td>{r["gf"] / pg:.2f}</td><td>{r["ga"] / pg:.2f}</td>'
                   f'<td class="{"good" if att > 1.1 else "bad" if att < 0.9 else ""}">{att:.2f}</td>'
                   f'<td class="{"good" if dfc < 0.9 else "bad" if dfc > 1.1 else ""}">{dfc:.2f}</td>'
                   f'<td>{r["pts"] / pg:.2f}</td><td>{form_dots((form_map or {}).get(r["team"]) or r["form"])}</td></tr>')
    out.append('</tbody></table></div>')
    return "".join(out)

def timing_bars(timing, title):
    tot = sum(timing.values()) or 1
    mx = max(timing.values()) or 1
    bars = "".join(
        f'<div class="tb"><span class="tb-l">{esc(lbl)}</span>'
        f'<span class="tb-bar"><i style="width:{timing[lbl] / mx * 100:.0f}%"></i></span>'
        f'<span class="tb-v">{timing[lbl]} <small>({timing[lbl] / tot * 100:.0f}%)</small></span></div>'
        for lbl, _, _ in AN.MINUTE_BUCKETS)
    return f'<div class="timing"><h3>{esc(title)}</h3>{bars}</div>'

def ratings_table(rows, title):
    if not rows:
        return ""
    out = [f'<div class="tbl-wrap"><h3>{esc(title)}</h3><table class="ptable"><thead><tr><th>#</th>'
           '<th class="tl">اللاعب</th><th class="tl">النادي</th><th>المركز</th><th>مباريات</th><th>متوسط التقييم</th><th>أفضل</th></tr></thead><tbody>']
    for i, r in enumerate(rows, 1):
        out.append(f'<tr><td>{i}</td><td class="tl"><bdi>{esc(r["name"])}</bdi></td><td class="tl"><bdi>{esc(r["club"])}</bdi></td>'
                   f'<td>{esc(r.get("pos") or "")}</td><td>{r["n"]}</td><td><b>{r["avg"]:.2f}</b></td><td>{r["best"]:.1f}</td></tr>')
    out.append('</tbody></table></div>')
    return "".join(out)

def ga_table(rows, share, title):
    if not rows:
        return ""
    sh = {(s["name"], s["team"]): s for s in share}
    out = [f'<div class="tbl-wrap"><h3>{esc(title)}</h3><table class="ptable"><thead><tr><th>#</th>'
           '<th class="tl">اللاعب</th><th class="tl">النادي</th><th>أهداف</th><th>صناعة</th><th>أ+ص</th>'
           '<th title="نسبة أهدافه من أهداف ناديه">من أهداف ناديه</th></tr></thead><tbody>']
    for i, r in enumerate(rows, 1):
        s = sh.get((r["name"], r["team"]))
        out.append(f'<tr><td>{i}</td><td class="tl"><bdi>{esc(r["name"])}</bdi></td><td class="tl"><bdi>{esc(ar_team(r["team"]))}</bdi></td>'
                   f'<td>{r["g"]}</td><td>{r["a"]}</td><td><b>{r["g"] + r["a"]}</b></td>'
                   f'<td>{(_pct(s["share"]) + " (" + str(s["g"]) + "/" + str(s["club_goals"]) + ")") if s else "—"}</td></tr>')
    out.append('</tbody></table></div>')
    return "".join(out)

def accuracy_html(acc, anchor=True):
    a = acc.get("all")
    hid = ' id="accuracy"' if anchor else ""
    if not a:
        return (f'<section class="minfo"{hid}><h2>دقة التوقعات</h2><p>يُثبَّت كل توقع قبل انطلاق المباراة ثم يُقارَن '
                'بالنتيجة الفعلية بعد صافرة النهاية. يبدأ هذا السجل بالظهور بعد أول مباريات تُلعب منذ إطلاق القسم.</p></section>')
    out = [f'<section class="minfo"{hid}><h2>دقة التوقعات</h2>'
           f'<div class="acc-tiles"><div class="tile"><b>{a["n"]}</b><span>مباراة مقيَّمة</span></div>'
           f'<div class="tile"><b>{_pct(a["hit_rate"])}</b><span>إصابة الاتجاه (فوز/تعادل/خسارة)</span></div>'
           f'<div class="tile"><b>{_pct(a["home_baseline"])}</b><span>لو توقعنا فوز الأرض دائمًا</span></div>'
           f'<div class="tile"><b>{a["brier"]:.3f}</b><span>مؤشر Brier (الأقل أفضل، 0.667 = عشوائي)</span></div>'
           f'<div class="tile"><b>{a["score_hits"]}</b><span>نتيجة مضبوطة</span></div></div>']
    if acc.get("comps"):
        out.append('<div class="tbl-wrap"><table class="ptable"><thead><tr><th class="tl">البطولة</th><th>مباريات</th><th>إصابة الاتجاه</th><th>Brier</th></tr></thead><tbody>')
        for comp in COMP_ORDER + [c for c in acc["comps"] if c not in COMP_ORDER]:
            c = acc["comps"].get(comp)
            if c:
                out.append(f'<tr><td class="tl">{esc(comp_label(comp))}</td><td>{c["n"]}</td><td>{_pct(c["hit_rate"])}</td><td>{c["brier"]:.3f}</td></tr>')
        out.append('</tbody></table></div>')
    if acc.get("recent"):
        out.append('<h3>آخر المباريات المقيَّمة</h3><ul class="acc-list">')
        for e in acc["recent"]:
            pick_ar = {"H": ar_team(e["home"]), "D": "تعادل", "A": ar_team(e["away"])}[e["pick"]]
            out.append(f'<li><bdi>{esc(ar_team(e["home"]))} '
                       f'{score_pill(e["hs"], e["as"], "sc-in")} {esc(ar_team(e["away"]))}</bdi> — '
                       f'توقعنا <b>{esc(pick_ar)}</b> ({_pct(max(e["ph"], e["pd"], e["pa"]))}) '
                       + ('<span class="hit ok">✔</span>' if e.get("hit") else '<span class="hit no">✘</span>') + '</li>')
        out.append('</ul>')
    out.append('<p class="hintline"><a href="/predictions.html">السجل الكامل: كل توقع بإصابته '
               'وخطئه، ومعايرة الاحتمالات ←</a></p>')
    out.append('</section>')
    return "".join(out)

# ===========================================================================
# «سجل التوقعات» — /predictions.html (2026-09-14)
#
# The user's ask: a full prediction history that shows the model FAILING as
# loudly as it succeeds. The site already froze every prediction before
# kick-off and scored it after; what it published was one number - 47%
# direction accuracy - which is the weakest thing we measure and the least
# informative. The record now leads with calibration (when we say 30%, does it
# happen 30% of the time?), keeps the naive baseline next to the hit rate, and
# prints the most confident MISSES beside the most confident hits.
#
# Everything is computed from the frozen log; nothing here can be edited after
# a match, which is the only reason a record like this is worth anything.
# ===========================================================================
# Every row stays in the HTML - the record is meant to be complete, and a
# crawler must see all of it - but the reader gets PAGE_STEP at a time; 151
# rows already make a 30,000-pixel page and the record only grows.
PRED_FILTER_JS = """<script>
(function(){
  var STEP=40;
  var rows=[].slice.call(document.querySelectorAll('#predlist .rec-i'));
  var days=[].slice.call(document.querySelectorAll('#predlist .rec-day'));
  var chips=[].slice.call(document.querySelectorAll('.pf-chip'));
  var sel=document.getElementById('pf-comp'), cnt=document.getElementById('pf-count');
  var none=document.getElementById('pf-none');
  var more=document.getElementById('pf-more'), state='all', limit=STEP;
  function apply(){
    var comp=sel?sel.value:'', matched=0, shown=0, live={};
    rows.forEach(function(r){
      var okHit = state==='all' || (state==='hit') === (r.dataset.hit==='1');
      var okComp = !comp || r.dataset.comp===comp;
      if(okHit && okComp){ matched++; var on = shown<limit; if(on){ shown++;
          live[r.dataset.day]=1; } r.hidden=!on; }
      else r.hidden=true;
    });
    /* a day header only belongs there while that day still has a visible match */
    days.forEach(function(d){ d.hidden = !live[d.dataset.day]; });
    if(cnt) cnt.textContent=matched;
    if(none) none.hidden = matched>0;
    if(more){
      more.hidden = matched<=shown;
      more.textContent='عرض المزيد ('+(matched-shown)+' متبقية)';
    }
  }
  chips.forEach(function(c){ c.addEventListener('click', function(){
    chips.forEach(function(x){ x.classList.remove('on'); });
    c.classList.add('on'); state=c.dataset.f; limit=STEP; apply(); }); });
  if(sel) sel.addEventListener('change', function(){ limit=STEP; apply(); });
  if(more) more.addEventListener('click', function(){ limit+=STEP; apply(); });
  apply();
})();
</script>"""


def calibration_html(cal):
    """The reliability table: what we said vs what happened, per band."""
    bs = [b for b in cal["buckets"] if b["n"] >= 10]
    if not bs:
        return ""
    out = ['<section class="minfo" id="calibration"><h2>هل احتمالاتنا صادقة؟ (معايرة النموذج)</h2>',
           '<p>كل توقع يقول ثلاثة أرقام: احتمال فوز الأرض، والتعادل، وفوز الضيف — '
           f'أي <b>{cal["statements"]}</b> احتمالًا معلنًا في <b>{cal["matches"]}</b> مباراة. '
           'هنا نجمع كل احتمال في نطاقه ونقارنه بما حدث فعلًا: لو قلنا «30%» في مئة حالة، '
           'المفروض تقع نحو ثلاثين منها. هذا هو المقياس الحقيقي لنموذج احتمالي، '
           'وليس عدد المرات التي أصاب فيها أعلى احتمال.</p>',
           '<div class="tbl-wrap"><table class="ptable"><thead><tr><th class="tl">النطاق</th>'
           '<th>عدد الحالات</th><th>قلنا (متوسط)</th><th>حدث فعلًا</th><th>الفارق</th>'
           '</tr></thead><tbody>']
    for b in bs:
        diff = b["actual"] - b["stated"]
        cls = "good" if abs(diff) <= 0.05 else "bad" if abs(diff) > 0.12 else ""
        sign = "+" if diff > 0 else ""
        out.append(f'<tr><td class="tl" dir="ltr">{b["lo"]}–{b["hi"]}%</td><td>{b["n"]}</td>'
                   f'<td>{_pct(b["stated"])}</td><td><b>{_pct(b["actual"])}</b></td>'
                   f'<td class="{cls}" dir="ltr">{sign}{diff * 100:.1f}</td></tr>')
    out.append('</tbody></table></div>')
    out.append(f'<p class="hintline">متوسط انحراف المعايرة (ECE): <b>{cal["ece"] * 100:.1f}</b> نقطة مئوية — '
               'كلما اقترب من الصفر كانت الاحتمالات أصدق. النطاقات التي تقل حالاتها عن عشرة لا تُعرض '
               'لأن عيّنتها أصغر من أن تقول شيئًا.</p>')
    out.append('</section>')
    return "".join(out)


def _rec_day_label(d):
    """«اليوم · 15 سبتمبر» for the record's day headers. The date belongs on
    the group, not repeated on all 166 rows (user, 2026-09-16)."""
    try:
        dt = datetime.date.fromisoformat(d)
    except Exception:
        return esc(d or "")
    today = datetime.date.fromisoformat(REF_TODAY)
    lead = ("اليوم" if dt == today
            else "أمس" if dt == today - datetime.timedelta(days=1)
            else _AR_DAYS[dt.weekday()])
    year = f" {dt.year}" if dt.year != today.year else ""
    return f"{lead} · {dt.day} {_AR_MONTHS[dt.month]}{year}"


def _pred_item_html(e):
    """One prediction in the record: the verdict first (an RTL reader meets it
    immediately), the match and its real score, then one muted line with what
    we said. A six-column table put the verdict at the far end of the row and
    repeated the date on every line - this reads instead of being decoded."""
    mid = e.get("match_id")
    h, a = ar_team(e.get("home")), ar_team(e.get("away"))
    pick_ar = {"H": f"فوز {h}", "D": "تعادل", "A": f"فوز {a}"}.get(e.get("pick"), "—")
    conf = max(e.get("ph") or 0, e.get("pd") or 0, e.get("pa") or 0)
    hit = 1 if e.get("hit") else 0
    verdict = "أصاب" if hit else "أخطأ"
    # score_pill, NOT "2-0" text: between two names in an RTL row a glued score
    # is one LTR bidi run and lands home-score-left = next to the AWAY club
    # (measured 2026-09-16).
    score = score_pill(e.get("hs"), e.get("as"), "sc-in")
    exact = ' <span class="pf-exact" title="أصبنا النتيجة بالضبط">🎯</span>' if e.get("score_hit") else ""
    tag, href = ("a", f' href="/m/{esc(mid)}.html"') if mid else ("div", "")
    return (f'<{tag} class="rec-i {"ok" if hit else "no"}"{href} data-hit="{hit}" '
            f'data-comp="{esc(e.get("comp") or "")}" data-day="{esc(e.get("kickoff") or "")}">'
            f'<span class="rec-v" title="{verdict}" aria-label="{verdict}">{"✔" if hit else "✘"}</span>'
            f'<span class="rec-m"><span class="rec-t"><bdi>{esc(h)}</bdi> {score} '
            f'<bdi>{esc(a)}</bdi>{exact}</span>'
            f'<span class="rec-s">قلنا <b>{esc(pick_ar)}</b> بنسبة {_pct(conf)} '
            f'<i class="rec-d">· أقرب نتيجة {score_txt(e.get("score"), "sc-in sc-s")}</i>'
            f'<i class="rec-lg">· {esc(comp_label(e.get("comp") or ""))}</i></span></span>'
            f'<span class="rec-c">{esc(comp_label(e.get("comp") or ""))}</span>'
            f'</{tag}>')


def _calls_html(ex):
    """The most confident hits and the most confident misses, side by side and
    the same size. A record that shows only the hits is an advert."""
    if not (ex["best"] or ex["worst"]):
        return ""
    def col(title, rows, cls):
        if not rows:
            return f'<div class="calls-c"><h3>{esc(title)}</h3><p class="hintline">لا شيء بعد.</p></div>'
        items = []
        for e in rows:
            h, a = ar_team(e.get("home")), ar_team(e.get("away"))
            pick_ar = {"H": h, "D": "تعادل", "A": a}.get(e.get("pick"), "—")
            conf = max(e.get("ph") or 0, e.get("pd") or 0, e.get("pa") or 0)
            items.append(f'<li><bdi>{esc(h)} {score_pill(e.get("hs"), e.get("as"), "sc-in")} {esc(a)}</bdi>'
                         f'<span>قلنا <b><bdi>{esc(pick_ar)}</bdi></b> بنسبة {_pct(conf)}</span></li>')
        return f'<div class="calls-c {cls}"><h3>{esc(title)}</h3><ul>{"".join(items)}</ul></div>'
    return ('<section class="minfo"><h2>أوضح إصاباتنا وأوضح إخفاقاتنا</h2>'
            '<div class="calls">'
            + col("أصاب النموذج وهو واثق", ex["best"], "ok")
            + col("أخطأ النموذج وهو واثق", ex["worst"], "no")
            + '</div><p class="hintline">أعلى التوقعات ثقةً في الاتجاهين — تُعرض معًا بالحجم نفسه.</p></section>')


def prediction_history_page(plog, acc):
    """/predictions.html — every frozen prediction, scored, with the model's
    calibration and its misses. Returns the url (or None when nothing scored)."""
    a = (acc or {}).get("all")
    rows = AN.history(plog)
    if not a or not rows:
        return None
    cal = AN.calibration(plog)
    ex = AN.extremes(plog)
    first = min(r.get("kickoff") or "" for r in rows)
    last = max(r.get("kickoff") or "" for r in rows)
    title = f"سجل توقعات يلا سكور: الإصابات والإخفاقات كاملة — {SITE_NAME}"
    desc = (f"كل توقع أصدره نموذج يلا سكور مُثبَّتًا قبل المباراة ومقارنًا بالنتيجة: "
            f"{a['n']} مباراة مقيَّمة، نسبة إصابة الاتجاه {_pct(a['hit_rate'])} مقابل "
            f"{_pct(a['home_baseline'])} لمعيار ساذج، ومعايرة الاحتمالات كاملة.")
    url = "/predictions.html"
    P = [head(title, desc, SITE_BASE + url, active="analysis")]
    P.append('<nav class="crumbs"><a href="/">أخبار</a> › '
             '<a href="/analysis.html">تحليلات وتوقعات</a> › سجل التوقعات</nav>')
    P.append('<h1 class="page-h">سجل توقعات يلا سكور — بالإصابات والإخفاقات</h1>')
    P.append('<section class="minfo"><p>يُثبَّت كل توقع في قاعدة البيانات <b>قبل انطلاق المباراة</b>، '
             'ولا يُعدَّل ولا يُحذف بعد صافرة النهاية، ثم يُقارَن بالنتيجة تلقائيًا. '
             f'هذه الصفحة تعرض السجل كاملًا منذ <b>{esc(first)}</b> وحتى <b>{esc(last)}</b> — '
             'ما أصاب فيه النموذج وما أخطأ فيه، بالأرقام نفسها ودون انتقاء. '
             'التوقعات احتمالات إحصائية من نتائج الموسم، وليست نصيحة للمراهنة.</p>')
    P.append(f'<div class="acc-tiles"><div class="tile"><b>{a["n"]}</b><span>مباراة مقيَّمة</span></div>'
             f'<div class="tile"><b>{_pct(a["hit_rate"])}</b><span>إصابة الاتجاه</span></div>'
             f'<div class="tile"><b>{_pct(a["home_baseline"])}</b><span>معيار ساذج: فوز الأرض دائمًا</span></div>'
             f'<div class="tile"><b>{a["brier"]:.3f}</b><span>Brier (الأقل أفضل · 0.667 عشوائي)</span></div>'
             f'<div class="tile"><b>{a["score_hits"]}</b><span>نتيجة مضبوطة</span></div>'
             f'<div class="tile"><b>{cal["ece"] * 100:.1f}</b><span>انحراف المعايرة (نقطة مئوية)</span></div>'
             '</div></section>')
    P.append(calibration_html(cal))
    P.append(_calls_html(ex))

    # per competition, with the sample size in front of every rate
    comps = (acc or {}).get("comps") or {}
    if comps:
        P.append('<section class="minfo"><h2>حسب البطولة</h2>'
                 '<div class="tbl-wrap"><table class="ptable"><thead><tr><th class="tl">البطولة</th>'
                 '<th>مباريات</th><th>إصابة الاتجاه</th><th>Brier</th></tr></thead><tbody>')
        for comp in COMP_ORDER + [c for c in comps if c not in COMP_ORDER]:
            c = comps.get(comp)
            if not c:
                continue
            small = ' <span class="pf-small">عيّنة صغيرة</span>' if c["n"] < 20 else ""
            P.append(f'<tr><td class="tl">{esc(comp_label(comp))}{small}</td><td>{c["n"]}</td>'
                     f'<td>{_pct(c["hit_rate"])}</td><td>{c["brier"]:.3f}</td></tr>')
        P.append('</tbody></table></div><p class="hintline">مع عشر مباريات أو عشرين، فرق النسب بين '
                 'بطولة وأخرى يقع كله داخل نطاق الصدفة — الأرقام هنا للعرض لا للترتيب.</p></section>')

    # the two models, apart and NOT as a race
    srcs = (acc or {}).get("by_src") or {}
    if len(srcs) > 1:
        # since 2026-09-24 every new prediction is python's (one model, the
        # user's decision); the Oracle rows are its record before that date,
        # kept exactly as scored - history is not rewritten
        P.append('<section class="minfo"><h2>مصدر التوقعات: بايثون وOracle</h2>'
                 '<div class="tbl-wrap"><table class="ptable"><thead><tr><th class="tl">المصدر</th>'
                 '<th>مباريات</th><th>إصابة الاتجاه</th><th>Brier</th></tr></thead><tbody>')
        for k in sorted(srcs):
            v = srcs[k]
            if not v:
                continue
            nm = {"oracle": "نموذج Oracle (PL/SQL)", "python": "نموذج بايثون"}.get(k, k)
            P.append(f'<tr><td class="tl">{esc(nm)}</td><td>{v["n"]}</td>'
                     f'<td>{_pct(v["hit_rate"])}</td><td>{v["brier"]:.3f}</td></tr>')
        P.append('</tbody></table></div><p class="hintline">منذ 24 سبتمبر 2026 تصدر كل التوقعات '
                 'من نموذج بايثون وحده، وصف Oracle هو سجل توقعاته قبل ذلك التاريخ، باقٍ كما حُسب. '
                 '<b>ليست مباراة بين النموذجين:</b> '
                 'كل توقع يصدر من المصدر المتاح وقتها، فالمجموعتان ليستا نفس المباريات، '
                 'والفارق بينهما عند هذا العدد يقع داخل نطاق الضوضاء. نعرضهما منفصلين حتى '
                 'يظهر اليوم الذي يصبح فيه أحدهما أفضل فعلًا.</p></section>')

    # the full record
    comp_opts = "".join(f'<option value="{esc(c)}">{esc(comp_label(c))}</option>'
                        for c in (COMP_ORDER + [c for c in comps if c not in COMP_ORDER])
                        if c in comps)
    P.append('<section class="minfo" id="record"><h2>السجل الكامل</h2>'
             '<div class="pf-bar"><span class="pf-chip on" data-f="all">الكل</span>'
             '<span class="pf-chip" data-f="hit">أصاب</span>'
             '<span class="pf-chip" data-f="miss">أخطأ</span>'
             f'<select id="pf-comp"><option value="">كل البطولات</option>{comp_opts}</select>'
             '<span class="pf-n"><b id="pf-count">' + str(len(rows)) + '</b> مباراة</span></div>'
             '<div class="rec" id="predlist">')
    # grouped by day: the date is a header, not a column repeated on every line
    last_day = None
    for e in rows:
        day = e.get("kickoff") or ""
        if day != last_day:
            P.append(f'<div class="rec-day" data-day="{esc(day)}">{_rec_day_label(day)}</div>')
            last_day = day
        P.append(_pred_item_html(e))
    P.append('</div><p class="rec-none" id="pf-none" hidden>لا توجد مباريات بهذا الاختيار.</p>'
             '<button type="button" id="pf-more" class="pf-more" hidden></button>'
             '<p class="hintline">🎯 = أصبنا النتيجة بالضبط. «أقرب نتيجة» هي أعلى نتيجة '
             'احتمالًا وقت التوقع، والعلامة ✔/✘ تقارن الاتجاه (فوز/تعادل/خسارة) بما حدث.</p></section>')

    P.append('<section class="minfo"><h2>حدود هذا السجل</h2><ul class="lim">'
             f'<li>يبدأ من <b>{esc(first)}</b> — أول يوم ثبّتنا فيه التوقعات آليًا، وليس من إطلاق الموقع.</li>'
             '<li>يُحتفظ بالتوقعات 150 يومًا، فالسجل نافذة متحركة وليس أرشيفًا أبديًا.</li>'
             '<li>العيّنة صغيرة: النسب لكل بطولة على عشرات المباريات، وتتحرك كثيرًا مع كل جولة.</li>'
             '<li>النموذج لا يعرف الإصابات ولا الإيقافات ولا تغيّر المدرب، ويعتمد على الموسم الحالي فقط.</li>'
             '<li>وسم الثقة الحالي لا يفصل بعد بين التوقعات الجيدة والضعيفة — نعرضه ونعمل على تحسينه.</li>'
             '<li>هذه أرقام تحليلية للقارئ، وليست نصيحة للمراهنة بأي شكل.</li>'
             '</ul><p><a href="/analysis.html#model">كيف يعمل النموذج؟ ←</a></p></section>')

    faq = [
        ("هل توقعات يلا سكور دقيقة؟",
         f"على {a['n']} مباراة مقيَّمة أصاب النموذج اتجاه النتيجة في {_pct(a['hit_rate'])} من الحالات، "
         f"مقابل {_pct(a['home_baseline'])} لو توقعنا فوز صاحب الأرض دائمًا. الأهم أن الاحتمالات "
         f"نفسها مُعايَرة: متوسط انحرافها {cal['ece'] * 100:.1f} نقطة مئوية عمّا يحدث فعلًا."),
        ("هل تُعدَّل التوقعات بعد المباراة؟",
         "لا. يُثبَّت التوقع في قاعدة البيانات قبل انطلاق المباراة ولا يُعدَّل ولا يُحذف بعدها، "
         "والسجل يعرض الإخفاقات كما يعرض الإصابات."),
        ("ماذا يعني مؤشر Brier؟",
         "قياس لجودة الاحتمالات: صفر يعني توقعًا مثاليًا، و0.667 يعني تخمينًا عشوائيًا بين ثلاث نتائج. "
         f"النموذج عند {a['brier']:.3f} حاليًا."),
        ("هل هذه نصيحة للمراهنة؟",
         "لا. الأرقام تحليلية مبنية على نتائج الموسم الحالي فقط، ولا تصلح أساسًا لأي رهان."),
    ]
    P.append('<section class="minfo faq"><h2>أسئلة شائعة عن سجل التوقعات</h2>'
             + "".join(f'<details><summary>{esc(q)}</summary><p>{esc(v)}</p></details>'
                       for q, v in faq) + '</section>')
    P.append(jsonld({"@context": "https://schema.org", "@type": "FAQPage",
                     "mainEntity": [{"@type": "Question", "name": q,
                                     "acceptedAnswer": {"@type": "Answer", "text": v}}
                                    for q, v in faq]}))
    P.append(breadcrumb_ld([("أخبار", SITE_BASE + "/"),
                            ("تحليلات وتوقعات", SITE_BASE + "/analysis.html"),
                            ("سجل التوقعات", SITE_BASE + url)]))
    P.append(foot())
    P.append(PRED_FILTER_JS)
    write("predictions.html", "".join(P))
    _LASTMOD[url] = REF_TODAY
    return url


def model_explainer():
    return ('<section class="minfo explain" id="model"><h2>كيف يعمل نموذج يلا سكور؟</h2>'
            '<p>القسم لا يعتمد على آراء أو توقعات شخصية، بل على أرقام المباريات الفعلية التي يجمعها الموقع '
            'كل ربع ساعة. لكل بطولة يبني النموذج ثلاث طبقات:</p><ol>'
            '<li><b>تقييم القوة (Elo):</b> يبدأ كل نادٍ برصيد 1500 نقطة، ويربح أو يخسر نقاطًا بعد كل مباراة '
            'بحسب النتيجة وقوة الخصم، مع ميزة صغيرة لصاحب الأرض. الفوز على فريق قوي يرفع التقييم أكثر من الفوز على فريق ضعيف.</li>'
            '<li><b>مؤشرا الهجوم والدفاع:</b> متوسط أهداف كل نادٍ له وعليه مقارنة بمتوسط الدوري، مع تخفيف أثر العيّنات '
            'الصغيرة في بداية الموسم حتى لا يبدو فريق «لا يُقهر» بعد مباراتين.</li>'
            '<li><b>الأهداف المتوقعة والاحتمالات:</b> من المؤشرين ومتوسط أهداف الأرض والضيف في الدوري يُحسب عدد الأهداف '
            'المتوقع لكل فريق، ثم توزيع بواسون على كل النتائج الممكنة يعطي احتمالات الفوز والتعادل والخسارة، '
            'والنتائج الأكثر ترجيحًا، واحتمال تجاوز 2.5 هدف وتسجيل الفريقين.</li></ol>'
            '<p><b>الشفافية:</b> يُثبَّت كل توقع قبل انطلاق المباراة ولا يُعدَّل بعدها، ثم يُقارَن بالنتيجة الفعلية في '
            '<a href="#accuracy">سجل الدقة</a> أعلاه، إلى جانب مقياس ساذج (توقع فوز الأرض دائمًا) حتى يعرف القارئ إن كان '
            'النموذج يضيف شيئًا فعلًا.</p>'
            '<p><b>حدود النموذج:</b> لا يعرف الإصابات ولا الإيقافات ولا تغيّر المدرب، ويعتمد على الموسم الحالي فقط '
            'فتكون عيّنته صغيرة في الجولات الأولى (نُشير إلى ذلك بوسم «عيّنة صغيرة»). لذلك تُقرأ التوقعات كاحتمالات '
            'وليست حقائق، وهي ليست نصيحة للمراهنة.</p></section>')

def comp_has_table(comp, has_table):
    """Was a /standings page written for this competition this build?"""
    return comp in (has_table or set())


def analysis_pages(matches, upcoming, preds, plog, acc, tstats, lparams, pins, sins,
                   forms, has_table=None):
    """Write /analysis.html (hub) + /analysis/<slug>.html per league. Returns urls."""
    urls = []
    today = datetime.date.fromisoformat(REF_TODAY)
    wk = (today + datetime.timedelta(days=7)).isoformat()
    by_comp = {}
    for m in upcoming:
        p = preds.get(str(m.get("match_id")))
        if p and (m.get("kickoff") or "") <= wk:
            by_comp.setdefault(m.get("competition"), []).append((m, p))
    for ms in by_comp.values():
        ms.sort(key=lambda t: (t[0].get("kickoff") or "", t[0].get("koff_time") or ""))
    comps = [c for c in COMP_ORDER if c in tstats] + [c for c in tstats if c not in COMP_ORDER]
    n_pred = sum(len(v) for v in by_comp.values())
    # ---- hub ----
    hp = [head("تحليلات وتوقعات المباريات بالأرقام — يلا سكور",
               "توقعات مباريات الأسبوع باحتمالات مبنية على بيانات الموسم، تقييم قوة الأندية، تحليل اللاعبين، "
               "وسجل شفاف لدقة التوقعات في الدوري المصري وأبرز الدوريات.",
               SITE_BASE + "/analysis.html", active="analysis")]
    hp.append(breadcrumb_ld([("أخبار", SITE_BASE + "/"), ("تحليلات", SITE_BASE + "/analysis.html")]))
    hp.append('<nav class="crumbs"><a href="/">أخبار</a> › تحليلات</nav>')
    hp.append('<h1 class="page-h">تحليلات وتوقعات بالأرقام</h1>')
    hp.append(f'<p class="hintline">نموذج يلا سكور يقرأ نتائج الموسم الحالي في {len(comps)} بطولات ويحوّلها إلى '
              f'تقييم قوة لكل نادٍ واحتمالات لكل مباراة قادمة — {n_pred} مباراة متوقعة خلال الأيام السبعة القادمة. '
              '<a href="#model">كيف يعمل النموذج؟</a></p>')
    hp.append('<div class="an-nav">' + "".join(
        f'<a href="/analysis/{COMP_SLUG[c]}.html">{comp_icon(c)} {esc(comp_label(c))}</a>'
        for c in comps if c in COMP_SLUG) + '</div>')
    hp.append('<section class="minfo"><h2>توقعات مباريات الأسبوع</h2>')
    if not by_comp:
        hp.append('<p class="hintline">لا مباريات قادمة خلال سبعة أيام في البطولات المغطاة.</p>')
    for c in comps:
        rows = by_comp.get(c)
        if not rows:
            continue
        hp.append(f'<h3 class="an-comp">{comp_icon(c)} <a href="/analysis/{COMP_SLUG.get(c, "")}.html">{esc(comp_label(c))}</a></h3>')
        hp.append('<div class="plist">' + "".join(pred_row(m, p) for m, p in rows[:8]) + '</div>')
        if len(rows) > 8 and c in COMP_SLUG:
            hp.append(f'<p class="more-link"><a href="/analysis/{COMP_SLUG[c]}.html">كل توقعات {esc(comp_label(c))} ({len(rows)}) ←</a></p>')
    hp.append(f'<p class="pd-note">{AN_DISCLAIMER}</p></section>')
    # power snapshot: top 5 per league
    hp.append('<section class="minfo"><h2>أقوى الأندية الآن (تقييم Elo)</h2><div class="pw-grid">')
    for c in comps:
        rows = sorted(tstats[c].values(), key=lambda r: -r["elo"])[:5]
        if not rows or all(r["played"] == 0 for r in rows):
            continue
        hp.append(f'<div class="pw-card"><h3>{comp_icon(c)} {esc(comp_label(c))}</h3><ol>' + "".join(
            f'<li><bdi>{esc(ar_team(r["team"]))}</bdi> <b>{round(r["elo"])}</b></li>' for r in rows)
            + (f'</ol><a href="/analysis/{COMP_SLUG[c]}.html">الجدول الكامل ←</a></div>' if c in COMP_SLUG else '</ol></div>'))
    hp.append('</div></section>')
    # players snapshot: best-rated across leagues (n>=2)
    best = []
    for c, d in pins.items():
        for r in d.get("ratings", [])[:5]:
            best.append(dict(r, comp=c))
    best.sort(key=lambda r: (-r["avg"], -r["n"]))
    if best:
        hp.append('<section class="minfo"><h2>أعلى اللاعبين تقييمًا هذا الموسم</h2>'
                  '<p class="hintline">متوسط تقييم اللاعب في المباريات التي بدأها أساسيًا (مرتان على الأقل)، من تقييمات مزوّد البيانات.</p>'
                  '<div class="tbl-wrap"><table class="ptable"><thead><tr><th>#</th><th class="tl">اللاعب</th><th class="tl">النادي</th><th class="tl">البطولة</th><th>مباريات</th><th>التقييم</th></tr></thead><tbody>')
        for i, r in enumerate(best[:12], 1):
            hp.append(f'<tr><td>{i}</td><td class="tl"><bdi>{esc(r["name"])}</bdi></td><td class="tl"><bdi>{esc(r["club"])}</bdi></td>'
                      f'<td class="tl">{esc(comp_label(r["comp"]))}</td><td>{r["n"]}</td><td><b>{r["avg"]:.2f}</b></td></tr>')
        hp.append('</tbody></table></div></section>')
    hp.append(accuracy_html(acc))
    hp.append(model_explainer())
    hp.append(foot())
    write("analysis.html", "".join(hp))
    urls.append("/analysis.html")
    # ---- per-league pages ----
    for c in comps:
        slug = COMP_SLUG.get(c)
        if not slug:
            continue
        label = comp_label(c)
        stats, params = tstats[c], lparams[c]
        if not stats:
            continue
        lp = [head(f"تحليلات {label}: توقعات المباريات وقوة الأندية واللاعبون — يلا سكور",
                   f"توقعات مباريات {label} القادمة باحتمالات مبنية على نتائج الموسم، ترتيب قوة الأندية (Elo) "
                   f"ومؤشرات الهجوم والدفاع، توقيت الأهداف، وأعلى اللاعبين تقييمًا.",
                   SITE_BASE + f"/analysis/{slug}.html", active="analysis")]
        lp.append(breadcrumb_ld([("أخبار", SITE_BASE + "/"), ("تحليلات", SITE_BASE + "/analysis.html"),
                                 (label, SITE_BASE + f"/analysis/{slug}.html")]))
        lp.append(f'<nav class="crumbs"><a href="/">أخبار</a> › <a href="/analysis.html">تحليلات</a> › {esc(label)}</nav>')
        lp.append(f'<h1 class="page-h">تحليلات {esc(label)}</h1>')
        n_m = params["n"]
        lp.append(f'<p class="hintline">مبنية على {_games(n_m)} منتهية هذا الموسم · متوسط الأهداف في المباراة '
                  f'{(params["gpm"] or 0):.2f}'
                  + (f' · فوز الأرض في {_pct(params["home_win"])} من المباريات والتعادل في {_pct(params["draw"])}' if params["home_win"] is not None else '')
                  + '.</p>')
        rows = by_comp.get(c, [])
        # all upcoming of this comp within 14 days
        wk2 = (today + datetime.timedelta(days=14)).isoformat()
        rows = sorted([(m, preds[str(m["match_id"])]) for m in upcoming
                       if m.get("competition") == c and str(m.get("match_id")) in preds and (m.get("kickoff") or "") <= wk2],
                      key=lambda t: (t[0].get("kickoff") or "", t[0].get("koff_time") or ""))
        lp.append(f'<section class="minfo"><h2>توقعات مباريات {esc(label)} القادمة</h2>')
        lp.append('<div class="plist">' + "".join(pred_row(m, p) for m, p in rows) + '</div>' if rows
                  else '<p class="hintline">لا مباريات قادمة خلال 14 يومًا.</p>')
        lp.append(f'<p class="pd-note">{AN_DISCLAIMER}</p></section>')
        lp.append(f'<section class="minfo"><h2>قوة أندية {esc(label)}</h2>'
                  '<p class="hintline">الترتيب بتقييم القوة (Elo) لا بالنقاط: يكافئ الفوز على الأقوياء ويأخذ فارق الأهداف '
                  'في الحساب. مؤشر الهجوم/الدفاع = أهداف النادي مقارنة بمتوسط الدوري (1.00 = المتوسط).</p>'
                  + power_table(c, stats, params, forms.get(c, {})) + '</section>')
        pi = pins.get(c)
        si = sins.get(c)
        if pi or si:
            lp.append(f'<section class="minfo"><h2>تحليل اللاعبين في {esc(label)}</h2>')
            if si and si.get("ga"):
                lp.append(ga_table(si["ga"], si.get("share", []), "الأكثر مساهمة في الأهداف (أهداف + صناعة)"))
            if pi and pi.get("ratings"):
                lp.append(ratings_table(pi["ratings"][:10], "أعلى اللاعبين تقييمًا (مرتان أساسيًا على الأقل)"))
            lp.append('</section>')
        if pi and sum(pi["timing"].values()) >= 10:
            late = sorted(pi["club_late"].items(), key=lambda kv: -kv[1]["late_share"])[:3]
            early = sorted(pi["club_late"].items(), key=lambda kv: -(kv[1]["early"] / kv[1]["total"]))[:3]
            lp.append(f'<section class="minfo"><h2>متى تُسجَّل الأهداف في {esc(label)}؟</h2>'
                      f'<p class="hintline">توزيع {sum(pi["timing"].values())} هدفًا في {_games(pi["n_matches"])} مرصودة بالتفاصيل هذا الموسم.</p>'
                      + timing_bars(pi["timing"], "الأهداف حسب فترة المباراة (بالدقائق)"))
            if late:
                lp.append('<p class="pd-line"><b>أندية الأهداف المتأخرة (بعد الدقيقة 75):</b> ' + '، '.join(
                    f'<bdi>{esc(k)}</bdi> ({v["late"]} من {v["total"]})' for k, v in late if v["late"]) + '</p>')
            if early:
                lp.append('<p class="pd-line"><b>أندية البداية السريعة (أول 15 دقيقة):</b> ' + '، '.join(
                    f'<bdi>{esc(k)}</bdi> ({v["early"]} من {v["total"]})' for k, v in early if v["early"]) + '</p>')
            lp.append('</section>')
        ca = {"all": acc["comps"].get(c), "comps": {}, "recent": [e for e in acc.get("recent", []) if e.get("comp") == c]}
        lp.append(accuracy_html(ca, anchor=False))
        # the standings page exists only for a competition with ONE table; a
        # cup (CAF CL) has group tables and no /standings page, so linking it
        # unconditionally left a dead link on that league's analysis page
        _st_link = (f'<a href="/standings/{slug}.html">ترتيب {esc(label)} ←</a> · '
                    if (has_table or set()) and comp_has_table(c, has_table) else "")
        lp.append(f'<p class="more-link">{_st_link}'
                  f'<a href="/analysis.html#model">كيف يعمل النموذج؟</a></p>')
        lp.append(foot())
        write(f"analysis/{slug}.html", "".join(lp))
        urls.append(f"/analysis/{slug}.html")
    return urls

def build():
    # Clear dist CONTENTS rather than the folder itself, so an open handle on
    # dist (e.g. a running preview server) doesn't block the rebuild.
    if os.path.exists(DIST):
        for name in os.listdir(DIST):
            p = os.path.join(DIST, name)
            if os.path.isdir(p):
                shutil.rmtree(p, ignore_errors=True)
            else:
                try:
                    os.remove(p)
                except OSError:
                    pass
    else:
        os.makedirs(DIST)
    os.makedirs(os.path.join(DIST, "a"), exist_ok=True)
    os.makedirs(os.path.join(DIST, "assets"), exist_ok=True)

    # Articles come from D1 (the writer since 2026-09-10). The committed
    # export is the fallback, and it is a real one: a build must render every
    # page when the store is unreachable. It can only ever be BEHIND, never
    # wrong - article_put.py rewrites it in the same commit as the article.
    try:
        articles_all, _asrc = articles_current()
        print(f"  articles: {len(articles_all)} from {_asrc}")
    except Exception as e:                                  # noqa: BLE001
        articles_all = load("articles.json")
        print(f"  ! article store unreachable ({e}) - using the committed "
              f"export ({len(articles_all)} articles)")
    # `articles_all` -> every piece still gets its own page at its own URL.
    # `articles`     -> what the SITE SHOWS anywhere: home blocks, archives,
    # club pages, match pages, related blocks, RSS, both sitemaps. Thin pieces
    # drop out of all of them at once (see ARTICLE_MIN_WORDS above).
    _miss = resolve_missing_media(articles_all)
    if _miss:
        print(f'  ! {len(_miss)} article image(s) not in this checkout yet - placeholder for this build: '
              + ', '.join(_miss[:5]))
    articles = [a for a in articles_all if not is_thin(a)]
    matches = load("matches.json")
    headlines = load("headlines.json")
    videos = load("videos.json")
    standings = load("standings.json")   # [{competition, table:[...]}]
    scorers = load("scorers.json")       # [{competition, scorers:[{name,team,goals,...}]}]
    assists = load("assists.json")       # same shape, key "assists"
    fixtures = load("fixtures.json")      # [{competition, current, rounds:[{round, matches}]}]
    goal_events = load("goal_events.json")  # [{home, away, date, goals:[{side,player,minute,tag}]}]
    # per-match lineups/cards/subs, accumulated by fetch_data (45 days)
    _details_raw = load("match_details.json")
    md_idx = match_details_index(_details_raw)
    # ONE rule for a finished match: the frozen archive first (results_archive.py,
    # 2026-09-24 - python's heir to Oracle's MATCH_RESULTS), the feed files below
    # it. These are dict.update() layers and the LAST one wins, so the archive is
    # applied last. Reading bottom-up:
    #   match_details.json  - the 45-day store, the deepest feed source
    #   goal_events.json    - a ROLLING window, fresher while it lasts; a
    #                         finished match drops out within hours
    #   results_archive     - frozen once the scorers account for the score,
    #                         never overwritten after that
    # Letting frozen beat fresh is safe BECAUSE of that gate. The cost, stated
    # plainly: a complete-but-wrong list, once frozen, is not corrected by a
    # later feed - that is what "frozen" means.
    _res_arch = RA.load()
    _frozen = RA.frozen_entries(_res_arch)
    # the SCORE of a finished match comes from the archive too, not only its
    # scorers - both halves of "النتيجة ومسجلي الأهداف"
    _sc_fill, _sc_chg = apply_frozen_scores(matches, frozen_scores_index(_frozen))
    ge_idx = goals_index(goal_events, _details_raw, _frozen)
    print("  + results archive: %d finished match(es), %d frozen; scores taken for %d%s"
          % (len(_res_arch), len(_frozen), _sc_fill,
             (" - %d DISAGREED with the feed" % _sc_chg) if _sc_chg else ""))

    # ---- تحليلات: strength model + predictions + accuracy + player insights ----
    _archive = load("matches_archive.json")
    # The season pool: the results archive AHEAD of the feed's rolling files, so
    # the opening rounds the feed has forgotten still count (the Saudi 51-vs-60
    # drift of 2026-09-13) and a frozen score wins a conflict. season_matches()
    # de-duplicates by fixture, so a match on both sides is counted once.
    _bycomp = AN.season_matches(fixtures, RA.season_rows(_res_arch) + _archive)
    # season carry-over (roadmap factor 1): the five European leagues start from
    # last season's carried Elo (data/elo_seeds.json, season_carry.py); absent
    # file = flat 1500 as before. The Oracle copy reads the same seeds.
    _seeds = AN.load_elo_seeds()
    if _seeds:
        print(f'  + elo seeds: {sum(len(v) for v in _seeds.values())} clubs in {len(_seeds)} leagues')
    _tstats = AN.team_stats(_bycomp, _seeds)
    _lparams = {c: AN.league_params(ms) for c, ms in _bycomp.items()}
    def _pred(m):
        comp = m.get("competition")
        if comp not in _tstats or not m.get("home") or not m.get("away"):
            return None
        return AN.predict(_tstats[comp], _lparams[comp], m["home"], m["away"])
    _upcoming = [m for m in matches if (m.get("status") or "").upper() == "UPCOMING" and m.get("match_id")]
    _preds = {}
    for m in _upcoming:
        p = _pred(m)
        if p:
            p["src"] = "python"
            _preds[str(m["match_id"])] = p
    print(f'  + predictions: {len(_preds)} upcoming fixtures, python model')
    # The prediction log lives in the store (D1 when configured). A frozen
    # prediction that gets re-frozen with newer data would silently inflate the
    # published accuracy, which is the one thing the accuracy page exists to
    # prevent - so the freeze has to be atomic, and store.pred_freeze refuses
    # to touch a row that is already scored.
    #
    # THE BUILD MUST NOT DEPEND ON A LIVE SERVICE: if the store is unreachable,
    # fall back to the last committed export, skip persisting, and still render
    # every page. A dead database may cost us one cycle of the log; it must
    # never cost us the site.
    _plog, _pstore_ok = {}, True
    try:
        _plog = store.pred_all()
    except Exception as e:                                  # noqa: BLE001
        _pstore_ok = False
        print(f"  ! prediction store unreachable ({e}) - using the committed export")
        _plog = AN.load_log()
    # the model's own track record per stated-probability band, computed once:
    # every upcoming match page prints the band its top number falls in
    _cal = AN.calibration(_plog)
    _pch = AN.update_log(_plog, _upcoming, _preds, matches + _archive, datetime.date.today())
    if _pstore_ok:
        try:
            for _mid in _pch["frozen"]:
                store.pred_freeze(_mid, _plog[_mid])
            for _mid in _pch["scored"]:
                _e = _plog[_mid]
                store.pred_score(_mid, _e["hs"], _e["as"], _e["outcome"], _e["pick"],
                                 _e["hit"], _e["brier"], _e["score_hit"])
            if _pch["pruned"]:
                store.pred_prune(AN.PRUNE_DAYS)
            if any(_pch.values()):
                print(f'  + predictions: {len(_pch["frozen"])} frozen, '
                      f'{len(_pch["scored"])} scored, {len(_pch["pruned"])} pruned '
                      f'({len(_plog)} in the log, backend {store.backend()})')
        except Exception as e:                              # noqa: BLE001
            print(f"  ! could not persist predictions ({e}) - pages still build")
    _acc = AN.accuracy(_plog)
    for _k, _v in sorted((_acc.get("by_src") or {}).items()):
        if _v:
            print(f'  + accuracy [{_k}]: n={_v["n"]} hit={_v["hit_rate"]:.1%} brier={_v["brier"]:.4f}')
    _comp_idx = {}
    for m in matches + _archive + [mm for f in fixtures for rd in f.get("rounds", []) for mm in rd.get("matches", [])]:
        if m.get("home") and m.get("away"):
            _comp_idx[(ar_team(m["home"]), ar_team(m["away"]), m.get("kickoff"))] = m.get("competition")
    _pins = AN.player_insights(_details_raw, lambda h, a, d: _comp_idx.get((h, a, d)), ar_team)
    # who each club normally starts -> «من غاب ومن عاد» on the match pages
    _squad = AN.SquadIndex(_details_raw, lambda h, a, d: _comp_idx.get((h, a, d)))
    _sins = AN.scorer_insights(scorers, assists, {s.get("competition"): s["table"] for s in standings if s.get("table")})
    # reels: hand-picked first, then auto-pulled channel uploads (deduped)
    reels = load("reels.json")
    seen_r = {r.get("video_id") for r in reels}
    for r in load("reels_auto.json"):
        if r.get("video_id") not in seen_r:
            reels.append(r)
            seen_r.add(r.get("video_id"))

    global TICKER_HTML
    TICKER_HTML = make_ticker(matches)

    # kickoff epochs for LIVE_JS's kickoff-aware polling (see KO_SCRIPT)
    global KO_SCRIPT
    try:
        from zoneinfo import ZoneInfo
        _cairo = ZoneInfo("Africa/Cairo")
        _now = datetime.datetime.now(_cairo)
        _kos = set()
        for _m in matches:
            if not (_m.get("kickoff") and _m.get("koff_time")):
                continue
            try:
                _dt = datetime.datetime.fromisoformat(
                    f"{_m['kickoff']}T{_m['koff_time']}:00").replace(tzinfo=_cairo)
            except ValueError:
                continue
            _delta = (_dt - _now).total_seconds()
            # recent past too: a match may already be live at build time
            if -4 * 3600 <= _delta <= 36 * 3600:
                _kos.add(int(_dt.timestamp() * 1000))
        KO_SCRIPT = (f"<script>window.__koTs={json.dumps(sorted(_kos))}</script>"
                     if _kos else "")
    except Exception:
        KO_SCRIPT = ""

    # ---- assets: css + logo ----
    global CSS_VER
    _css = CSS + "\n" + LEGENDS_CSS
    CSS_VER = hashlib.md5(_css.encode("utf-8")).hexdigest()[:8]   # changes only when CSS changes
    with open(os.path.join(DIST, "assets", "style.css"), "w", encoding="utf-8") as f:
        f.write(_css)
    # /favicon.ico at the site root — the legacy fallback path some crawlers
    # (and Google's favicon fetcher) request directly; was a 404 before
    _ico = os.path.join(HERE, "assets-src", "favicon.ico")
    if os.path.exists(_ico):
        shutil.copy(_ico, os.path.join(DIST, "favicon.ico"))
    _fav = os.path.join(HERE, "assets-src", "favicon.png")
    if os.path.exists(_fav):
        shutil.copy(_fav, os.path.join(DIST, "assets", "favicon.png"))
    _ogb = os.path.join(HERE, "assets-src", "og-banner.png")
    if os.path.exists(_ogb):
        shutil.copy(_ogb, os.path.join(DIST, "assets", "og-banner.png"))
    for _logo in (os.path.join(HERE, "assets-src", "logo.png"),
                  os.path.join(HERE, "..", "shared-components", "static-files", "icons", "app-icon-192.png")):
        if os.path.exists(_logo):
            shutil.copy(_logo, os.path.join(DIST, "assets", "logo.png"))
            break

    urls = ["/", "/matches.html"]

    # ---- home ----
    feat = articles[0] if articles else None    # og:image source
    parts = [head(f"{SITE_NAME} — {SITE_TAGLINE}", SITE_DESC, SITE_BASE + "/",
                  image=(feat and feat.get("image_url")) or None, active="home",
                  # the hero block renders the THUMB now - preloading the
                  # full 1600 would fetch a file the page never uses
                  preload_img=thumb_url(feat and feat.get("image_url")) or None)]
    # Organization (publisher identity: logo + Facebook page + contact) and
    # WebSite in one graph — the entity Google ties every NewsArticle's
    # `publisher` and the brand-name query to.
    parts.append(jsonld({
        "@context": "https://schema.org",
        "@graph": [
            {"@type": "Organization", "@id": SITE_BASE + "/#org",
             "name": SITE_NAME, "url": SITE_BASE + "/",
             "logo": {"@type": "ImageObject", "url": SITE_BASE + "/assets/logo.png"},
             "sameAs": [FB_PAGE_URL, TG_CHANNEL_URL],
             "email": "yallascore.eg@gmail.com"},
            {"@type": "WebSite", "@id": SITE_BASE + "/#website",
             "name": SITE_NAME, "url": SITE_BASE + "/",
             "inLanguage": "ar", "description": strip_tags(SITE_DESC),
             "publisher": {"@id": SITE_BASE + "/#org"}}]}))
    # single-column home since 2026-09-01 (the transfers rail — the only
    # left-column tenant — was removed by user decision, replaced by the
    # FotMob-style blocks). The ad strip keeps its place ABOVE آخر الأخبار
    # (firm user rule: never move the ad slot).
    parts.append(f'<div class="home-topad">{adsense_slot()}</div>')
    # heading row: title on the start side, a LIVE card for one of the curated
    # clubs on the end side. The card is filled by LIVE_JS in the visitor's
    # browser — a 15-minute-old build can't know what is live right now.
    # between the ad slot and the heading — user's chosen order; the ad keeps
    # its place inside the column, so the bar takes the column's width
    # NO static seed (removed 2026-08-31, user rule: never show data that may
    # be wrong — a build-time "live" snapshot showed a finished match as
    # مباشر الآن with a stale score). The card renders EXCLUSIVELY from the
    # first fresh /live.json reply, ~1s after load.
    parts.append('<div id="favLive" class="fav-wrap" hidden></div>')
    # «آخر الأخبار» + FotMob-style chips (user ask 2026-09-02): a chip scrolls
    # to its block (trend / egy / eur) and the highlight follows the block in
    # view — nothing is hidden (user corrected the first hide-others version)
    parts.append(news_filter_bar())
    # FotMob-style blocks (2026-09-01, replaced the hero + horizontal shelf):
    # block 1 = newest article featured + the next 4 as a numbered trending
    # list; block 2 = the same shape scoped to Egyptian football (green
    # banner), skipping anything block 1 already showed.
    used = set()
    if articles:
        b1 = articles[:5]
        used = {a["article_id"] for a in b1}
        parts.append(fmb_block(b1[0], b1[1:], "الأكثر تداولًا", "/news.html", nf="trend"))
        egy = [a for a in articles
               if a["article_id"] not in used and _egy_article(a)]
        if len(egy) >= 2:
            parts.append(fmb_block(egy[0], egy[1:5], "أخبار الكرة المصرية",
                                   "/news/egypt.html", nf="egy"))
            used |= {a["article_id"] for a in egy[:5]}
        eur = [a for a in articles
               if a["article_id"] not in used and _eur_article(a)]
        if len(eur) >= 2:
            parts.append(fmb_block(eur[0], eur[1:5], "أخبار الكرة الأوروبية",
                                   "/news/europe.html", flip=True, nf="eur"))
            used |= {a["article_id"] for a in eur[:5]}
    # «توقعات يلا سكور» under the news blocks (user ask 2026-09-12): four
    # predicted fixtures, المزيد -> /analysis.html
    parts.append(pred_home_block(_upcoming, _preds, datetime.date.fromisoformat(REF_TODAY),
                                 acc=_acc, cal=_cal))
    # latest videos teaser (full library lives on /videos.html)
    if videos and SHOW_VIDEOS:
        parts.append('<div class="sec-h"><h2 class="page-h">أحدث الفيديوهات</h2>'
                     '<a class="see-all" href="/videos.html">كل الفيديوهات ←</a></div>')
        parts.append('<div class="vstrip">')
        for v in videos[:3]:
            parts.append(video_facade(v))
        parts.append('</div>')
        parts.append(VIDEO_JS)
    # reels teaser: ONE banner -> the swipe feed on /reels.html
    if reels and SHOW_REELS:
        r0 = reels[0]
        rthumb = f"https://i.ytimg.com/vi/{esc(r0.get('video_id'))}/oar2.jpg"
        rfb = f"https://i.ytimg.com/vi/{esc(r0.get('video_id'))}/hqdefault.jpg"
        parts.append(f"""<a class="reels-banner" href="/reels.html">
  <img src="{rthumb}" alt="" loading="lazy" onerror="this.onerror=null;this.src='{rfb}'">
  <div class="rb-body">
    <h2>⚡ ريلز يلا سكور</h2>
    <p>مقاطع قصيرة ممتعة — اضغط للمشاهدة، واسحب لفوق تجيب اللي بعده</p>
    <span class="rb-cta">شاهد الآن ▶</span>
  </div></a>""")
    # external headlines teaser (24 = 8 rows, matches IMG_ENRICH_TOP so every
    # card gets a thumbnail; the full list lives on /headlines.html)
    if headlines and SHOW_HEADLINES:
        parts.append('<div class="sec-h"><h2 class="page-h">عناوين</h2>'
                     '<a class="see-all" href="/headlines.html">كل العناوين ←</a></div>')
        parts.append('<div class="hgrid">')
        for h in headlines[:24]:
            parts.append(headline_card(h))
        parts.append('</div>')
    # NOTE (2026-09-01, user): no leftover "من أخبارنا أيضًا" section — home
    # shows ONLY the three FotMob blocks (featured + 4 each, keep the lists
    # at 4); everything older lives on /news.html via each block's المزيد.
    # (matches are NOT shown on the home page - they live on /matches.html)
    # curated-clubs crest strip closes the news page (user ask 2026-09-02):
    # each crest opens the club's /team/ page
    parts.append(clubs_strip(standings, matches, fixtures))
    # crests + per-match page URL for the live card, curated clubs only
    # (keyed by the Arabic name pair — LIVE_JS normalizes both sides)
    fav_meta = {}
    for m in matches:
        if _is_ticker_team(m) and m.get("match_id"):
            fav_meta[f'{ar_team(m.get("home"))}|{ar_team(m.get("away"))}'] = {
                "hb": local_crest(m["home_badge"]) if m.get("home_badge") else "",
                "ab": local_crest(m["away_badge"]) if m.get("away_badge") else "",
                "u": match_url(m)}
    parts.append('<script>window.__favClubs='
                 + json.dumps(fav_club_names(standings, fixtures), ensure_ascii=False)
                 + ';window.__favMeta='
                 + json.dumps(fav_meta, ensure_ascii=False)
                 + ';</script>')
    parts.append(foot())
    write("index.html", "".join(parts))

    # ---- article pages ---- (every article, listed or not, keeps its page)
    # match_id -> competition, so a match piece whose writer skipped `sources`
    # still credits the right data provider (see match_data_sources)
    _mcomp = {str(m["match_id"]): (m.get("competition") or "")
              for m in (load("matches_archive.json") + matches) if m.get("match_id")}
    # match previews/reports do not get a page of their own any more: they are
    # rendered inside /m/<match_id> further down, and their old URL 301s there
    _match_arts = {}
    _moved = []
    _MOVED_LINKS.clear()
    _MOVED_LINKS.update({str(x["article_id"]): f"/m/{x['match_id']}"
                         for x in articles_all if is_match_piece(x)})
    n_thin = 0
    for a in articles_all:
        if is_match_piece(a):
            _match_arts.setdefault(str(a["match_id"]), []).append(a)
            _moved.append((f"/a/{a['article_id']}", article_href(a)))
            write(f"a/{a['article_id']}.html", article_moved_stub(a))
            continue
        url = article_url(a)
        img = a.get("image_url")
        _clubs = article_clubs(a)
        _pub_iso = a.get("pub_ts") or a.get("pub_date")
        # updated_ts is set by the upgrade-articles workflow (rewrite to the
        # 500-700-word standard) — dateModified, «آخر تحديث» and sitemap lastmod
        _mod_iso = a.get("updated_ts") or _pub_iso
        _words = len(strip_tags(a.get("body") or "").split())
        ld = {"@context": "https://schema.org", "@type": "NewsArticle",
              "headline": a["title"], "description": strip_tags(a.get("summary")),
              "datePublished": _pub_iso, "dateModified": _mod_iso,
              "inLanguage": "ar", "mainEntityOfPage": url, "url": url,
              "isAccessibleForFree": True, "articleSection": "كرة القدم",
              "wordCount": _words,
              # byline() resolves the generic team name to the named editor, so
              # every article carries a Person entity that resolves to a page
              # with a role, an email and a photo-less but real identity
              "author": {"@type": "Person", "name": byline(a),
                         "url": SITE_BASE + "/editors.html"},
              "publisher": {"@type": "Organization", "@id": SITE_BASE + "/#org",
                            "name": SITE_NAME, "url": SITE_BASE + "/",
                            "sameAs": [FB_PAGE_URL, TG_CHANNEL_URL],
                            "logo": {"@type": "ImageObject", "url": SITE_BASE + "/assets/logo.png"}}}
        if _clubs:
            ld["keywords"] = ", ".join(tp["name"] for tp in _clubs)
            ld["about"] = [{"@type": "SportsTeam", "name": tp["name"],
                            "url": f'{SITE_BASE}/team/{tp["slug"]}.html'} for tp in _clubs]
        if img:
            _iw, _ih = _og_dims(img)
            ld["image"] = ([{"@type": "ImageObject", "url": img, "width": _iw, "height": _ih}]
                           if _iw else [img])
        # 56 older match articles shipped without a summary and their pages
        # went out with an EMPTY meta description (audit 2026-09-22) - the
        # search snippet then falls to whatever Google scrapes. The body's
        # opening is the article's own lead; seo_desc trims it to size.
        _desc = a.get("summary") or strip_tags(a.get("body") or "")[:220]
        p = [head(f"{a['title']} — {SITE_NAME}", _desc, url, image=img, og_type="article")]
        p.append(jsonld(ld))
        _crumbs = [("أخبار", SITE_BASE + "/"), ("كل الأخبار", SITE_BASE + "/news.html")]
        if _clubs:
            _crumbs.append((_clubs[0]["name"], f'{SITE_BASE}/team/{_clubs[0]["slug"]}.html'))
        p.append(breadcrumb_ld(_crumbs + [(a["title"], url)]))
        p.append('<nav class="crumbs">'
                 + " › ".join(f'<a href="{esc(u.replace(SITE_BASE, "") or "/")}">{esc(n)}</a>'
                              for n, u in _crumbs)
                 + '</nav>')
        p.append('<article class="article">')
        p.append(f'<h1>{esc(a["title"])}</h1>')
        _t = art_reltime(a)
        _upd = ""
        if a.get("updated_ts"):
            _upd = (f' · <span class="a-upd">آخر تحديث <time datetime="{esc(a["updated_ts"])}">'
                    f'{esc(str(a["updated_ts"])[:10])}</time></span>')
        p.append(f'<p class="a-meta"><a class="a-by" href="/editors.html">{esc(byline(a))}</a> · <time datetime="{esc(a.get("pub_date"))}">{esc(a.get("pub_date"))}</time>'
                 f'{" · " + _t if _t else ""}{_upd}</p>')
        if img:
            p.append(f'<figure class="a-fig"><img class="a-img" src="{esc(img)}" alt="{esc(a["title"])}" loading="eager" fetchpriority="high">')
            cr = a.get("image_credit")
            if cr:
                p.append(f'<figcaption class="a-credit">{esc(cr)}</figcaption>')
            p.append('</figure>')
        if a.get("summary"):
            p.append(f'<p class="lead">{esc(a["summary"])}</p>')
        p.append(f'<div class="a-body">{fix_moved_links(a.get("body")) or ""}</div>')
        # optional editorial blocks written by the article tasks since
        # 2026-09-06: named sources (transparency — "المصادر") and a short FAQ
        # answered from the body. Older articles simply have neither field.
        _src = [s for s in (a.get("sources") or []) if isinstance(s, dict) and s.get("name")]
        if not _src and a.get("kind") in ("preview", "report"):
            _src = match_data_sources(a, _mcomp.get(str(a.get("match_id")), ""))
        if _src:
            p.append('<section class="a-sources"><h2>المصادر</h2><ul>'
                     + "".join((f'<li><a href="{esc(s["url"])}" target="_blank" rel="noopener nofollow">{esc(s["name"])}</a>'
                                if s.get("url") else f'<li>{esc(s["name"])}')
                               + (f' — {esc(s["note"])}' if s.get("note") else "") + '</li>' for s in _src)
                     + '</ul></section>')
        _faq = [f for f in (a.get("faq") or []) if isinstance(f, dict) and f.get("q") and f.get("a")]
        if _faq:
            p.append('<section class="a-faq"><h2>أسئلة شائعة</h2>'
                     + "".join(f'<details><summary>{esc(f["q"])}</summary><p>{esc(f["a"])}</p></details>' for f in _faq)
                     + '</section>')
            p.append(jsonld({"@context": "https://schema.org", "@type": "FAQPage",
                             "mainEntity": [{"@type": "Question", "name": f["q"],
                                             "acceptedAnswer": {"@type": "Answer", "text": f["a"]}} for f in _faq]}))
        # official posts about the story, click-to-load (2026-09-13)
        p.append(embeds_block(a.get("embeds")))
        if _clubs:
            p.append('<nav class="club-chips"><span>المزيد عن:</span>'
                     + "".join(f'<a href="/team/{tp["slug"]}.html">'
                               f'{esc(tp["name"])}</a>' for tp in _clubs)
                     + '</nav>')
        p.append('</article>')
        # related articles: internal links between pieces about the same
        # match/club/topic — articles used to get ~2 inbound links each (only
        # from listing pages), so deep crawl + PageRank flow was weak.
        _rel = related_articles(a, articles)
        if _rel:
            p.append('<section class="minfo related"><h2>مقالات ذات صلة</h2><ul class="mp-newslist">')
            for b in _rel:
                _bt = art_reltime(b)
                p.append(f'<li><a href="{article_href(b)}">{esc(b["title"])}</a>'
                         + (f' <span class="club-when">({_bt})</span>' if _bt else "")
                         + '</li>')
            p.append('</ul></section>')
        p.append(foot())
        _ahtml = "".join(p)
        if _words < ARTICLE_MIN_WORDS:
            # legacy short pieces: keep the URL alive (still linked from lists
            # and related blocks) but out of the index AND out of the sitemap —
            # a noindexed URL in the sitemap is a contradictory signal.
            _ahtml = _ahtml.replace("<head>", '<head><meta name="robots" content="noindex">', 1)
            n_thin += 1
        write(f"a/{a['article_id']}.html", _ahtml)
        if _words >= ARTICLE_MIN_WORDS:
            urls.append(f"/a/{a['article_id']}.html")
            _LASTMOD[f"/a/{a['article_id']}.html"] = _mod_iso
    print(f"  + match pieces moved into their match page: {len(_moved)}")
    print(f"  + articles: {len(articles_all)} pages, {len(articles)} listed "
          f"({n_thin} unlisted: under {ARTICLE_MIN_WORDS} words, noindexed + out of every listing)")

    # ---- shared per-league data + stats machinery (matches page + /stats) ----
    st_by_comp = {s.get("competition"): s for s in standings if s.get("table")}
    sc_by_comp = {s.get("competition"): (s.get("scorers") or [])
                  for s in scorers if s.get("scorers")}
    as_by_comp = {s.get("competition"): (s.get("assists") or [])
                  for s in assists if s.get("assists")}
    # both read the season pool (_bycomp) so a truncated fixtures.json cannot
    # empty the «آخر 5» column or the tile fallback (2026-09-13)
    forms = team_form(fixtures, standings, _bycomp)
    elos = compute_elo(fixtures, _bycomp)
    fx_by_comp = {f.get("competition"): f for f in fixtures if f.get("rounds")}
    STAT_PAL = ["#1f94d3", "#e11d48", "#f59e0b", "#7c3aed", "#334155"]

    def _fin_ms(fx):
        """(round, match) pairs for finished matches with scores, chronological."""
        ms = []
        for rd in fx.get("rounds", []):
            for m in rd.get("matches", []):
                if (m.get("status") == "FINISHED"
                        and m.get("home_score") is not None
                        and m.get("away_score") is not None):
                    ms.append((rd.get("round"), m))
        ms.sort(key=lambda t: (t[1].get("kickoff") or "", t[1].get("koff_time") or ""))
        return ms

    def _pts_race_svg(fin, top_teams):
        """Cumulative points per round for the leading teams, inline SVG line chart."""
        rounds = sorted({r for r, _ in fin if r is not None})
        top_teams = [t for t in top_teams if t]
        if len(rounds) < 2 or not top_teams:
            return ""
        per = {}
        for r, m in fin:
            if r is None:
                continue
            hs, aw = m["home_score"], m["away_score"]
            d = per.setdefault(r, {})
            d[m.get("home")] = d.get(m.get("home"), 0) + (3 if hs > aw else 1 if hs == aw else 0)
            d[m.get("away")] = d.get(m.get("away"), 0) + (3 if aw > hs else 1 if hs == aw else 0)
        series = {}
        for t in top_teams:
            c, vals = 0, []
            for r in rounds:
                c += per.get(r, {}).get(t, 0)
                vals.append(c)
            series[t] = vals
        w, h, ml, mr, mt, mb = 680, 240, 30, 12, 12, 26
        ymax = max(max(v) for v in series.values()) or 1
        def x(i): return ml + (w - ml - mr) * (i / max(1, len(rounds) - 1))
        def y(v): return mt + (h - mt - mb) * (1 - v / ymax)
        parts = [f'<svg class="chart" viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="سباق النقاط">']
        step = max(1, ymax // 4)
        for g in range(0, ymax + 1, step):
            parts.append(f'<line x1="{ml}" y1="{y(g):.1f}" x2="{w - mr}" y2="{y(g):.1f}" stroke="#eef2f6"/>')
            parts.append(f'<text x="{ml - 5}" y="{y(g) + 4:.1f}" font-size="10" fill="#94a3b8" text-anchor="end">{g}</text>')
        for i, r in enumerate(rounds):
            parts.append(f'<text x="{x(i):.1f}" y="{h - 8}" font-size="10" fill="#94a3b8" text-anchor="middle">{r}</text>')
        for k, (t, vals) in enumerate(series.items()):
            col = STAT_PAL[k % len(STAT_PAL)]
            pl = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(vals))
            parts.append(f'<polyline points="{pl}" fill="none" stroke="{col}" stroke-width="2.5" stroke-linejoin="round"/>')
            parts.append(f'<circle cx="{x(len(vals) - 1):.1f}" cy="{y(vals[-1]):.1f}" r="3.5" fill="{col}"/>')
        parts.append('</svg>')
        legend = "".join(
            f'<span class="lgd"><i style="background:{STAT_PAL[k % len(STAT_PAL)]}"></i><bdi>{esc(ar_team(t))}</bdi></span>'
            for k, t in enumerate(series))
        return f'<div class="chart-wrap">{"".join(parts)}</div><div class="legend">{legend}</div>'

    def _goals_svg(fin):
        """Total goals per round, inline SVG bar chart (needs 2+ rounds —
        a single bar just repeats the season-total tile)."""
        rounds = sorted({r for r, _ in fin if r is not None})
        if len(rounds) < 2:
            return ""
        goals = {r: 0 for r in rounds}
        for r, m in fin:
            if r is not None:
                goals[r] += m["home_score"] + m["away_score"]
        w, h, ml, mr, mt, mb = 680, 200, 30, 12, 14, 26
        ymax = max(goals.values()) or 1
        bw = min((w - ml - mr) / len(rounds) * 0.6, 64)
        parts = [f'<svg class="chart" viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="الأهداف في كل جولة">']
        for i, r in enumerate(rounds):
            cx = ml + (w - ml - mr) * ((i + .5) / len(rounds))
            bh = (h - mt - mb) * goals[r] / ymax
            parts.append(f'<rect x="{cx - bw / 2:.1f}" y="{h - mb - bh:.1f}" width="{bw:.1f}" height="{max(bh, 1):.1f}" rx="3" fill="#1f94d3" opacity="0.85"/>')
            parts.append(f'<text x="{cx:.1f}" y="{h - mb - bh - 4:.1f}" font-size="10" fill="#475569" text-anchor="middle">{goals[r]}</text>')
            parts.append(f'<text x="{cx:.1f}" y="{h - 8}" font-size="10" fill="#94a3b8" text-anchor="middle">{r}</text>')
        parts.append('</svg>')
        return f'<div class="chart-wrap">{"".join(parts)}</div>'

    # season totals per competition, so the player charts can be checked
    # against the season they claim to describe (see chart_is_current)
    comp_goals, comp_maxp = {}, {}
    for _c, _fx in fx_by_comp.items():
        _f = _fin_ms(_fx)
        # The denominator has to be the SEASON POOL, not this one file. For the
        # 365scores leagues fixtures.json carries scores for only a few rounds
        # (Egypt on 2026-09-16: 11 goals in the file against the 93 the season
        # actually holds), and an understated denominator makes
        # chart_is_current reject a perfectly current top-scorer list as "last
        # season's": 13 goals across the top five > 11 for the whole league.
        # That is what emptied /scorers/egypt - the guard was right about the
        # arithmetic and wrong about the world. Found by an outside HTML audit
        # of the live site, 2026-09-16.
        comp_goals[_c] = max(
            sum(int(m["home_score"]) + int(m["away_score"]) for m in (_bycomp.get(_c) or [])),
            sum(m["home_score"] + m["away_score"] for _, m in _f))
        _tbl = (st_by_comp.get(_c) or {}).get("table") or []
        comp_maxp[_c] = (max((r.get("played") or 0) for r in _tbl) if _tbl
                         else max((r or 0 for r, _ in _f), default=0))
    sc_ok = {c: chart_is_current(rows, comp_goals.get(c), comp_maxp.get(c))
             for c, rows in sc_by_comp.items()}
    as_ok = {c: chart_is_current(rows, comp_goals.get(c), comp_maxp.get(c))
             for c, rows in as_by_comp.items()}
    stats_cutoff = (datetime.date.today() - datetime.timedelta(days=30)).isoformat()

    def league_stats_parts(comp):
        """One league's stats, split into the tab panes the matches page uses:
        {"numbers": tiles + percentages, "scorers": scorers + assists charts,
         "trend": points race + goals per round}. Missing pieces are absent.
        /stats.html stitches them back into one section."""
        parts = []
        fx = fx_by_comp.get(comp)
        if not fx:
            return {}
        fin = _fin_ms(fx)
        if not fin:
            return {}
        fx = fx_by_comp.get(comp)
        if not fx:
            return ""
        fin = _fin_ms(fx)
        if not fin:
            return ""
        # a season that ended long ago (e.g. last season's Champions League
        # rounds still in the feed) must not pose as current-season numbers:
        # skip when nothing is left to play AND the last match is >30 days old
        all_ms = [m for rd in fx.get("rounds", []) for m in rd.get("matches", [])]
        pending = any((m.get("status") or "").upper() != "FINISHED" for m in all_ms)
        last_day = max((m.get("kickoff") or "" for m in all_ms), default="")
        if not pending and last_day and last_day < stats_cutoff:
            return {}
        played = len(fin)
        goals = sum(m["home_score"] + m["away_score"] for _, m in fin)
        big = max((m for _, m in fin),
                  key=lambda m: (m["home_score"] + m["away_score"],
                                 max(m["home_score"], m["away_score"])))
        big_t = (f'{ar_team(big.get("home"))} {big["home_score"]}-{big["away_score"]} '
                 f'{ar_team(big.get("away"))}')
        # who played it: same home-first order as every match row on the site
        def _tile_side(name, badge):
            img = (f'<img src="{esc(local_crest(badge))}" alt="" loading="lazy">'
                   if badge else '<span class="ph">⚽</span>')
            return f'<span class="tm">{img}<bdi>{esc(ar_team(name))}</bdi></span>'
        big_ms = (f'<div class="tile-ms">{_tile_side(big.get("home"), big.get("home_badge"))}'
                  f'<i>×</i>{_tile_side(big.get("away"), big.get("away_badge"))}</div>')
        big_bits = []
        if big.get("round") is not None:
            big_bits.append(f'الجولة {esc(str(big["round"]))}')
        if big.get("kickoff"):
            try:
                _d = datetime.date.fromisoformat(big["kickoff"])
                big_bits.append(f'{_d.day:02d}/{_d.month:02d}/{_d.year}')
            except Exception:
                pass
        big_when = (f'<div class="tile-when">{" · ".join(big_bits)}</div>'
                    if big_bits else "")
        top_rows = (st_by_comp.get(comp) or {}).get("table") or []
        top_teams = [r.get("team") for r in top_rows[:5]]
        if not top_teams:
            er = elos.get(comp, {})
            top_teams = [t for t, _ in sorted(er.items(), key=lambda kv: -kv[1][0])[:5]]
        panes = {}
        # player charts, only when they describe THIS season (chart_is_current)
        sc = sc_by_comp.get(comp) or [] if sc_ok.get(comp) else []
        asst = as_by_comp.get(comp) or [] if as_ok.get(comp) else []
        sc_tile = ""
        if sc:
            lead = sc[0]
            sc_tile = (f'<div class="tile tile-sc" title="{esc(lead.get("name"))}'
                       f' - {esc(lead.get("team"))}"><b>{lead.get("goals")}</b>'
                       f'<span>هداف الدوري</span>'
                       f'<div class="tile-ms">{_scorer_face(lead)}'
                       f'<span class="tm"><bdi>{esc(lead.get("name"))}</bdi></span></div>'
                       f'<div class="tile-when">{esc(lead.get("team"))}</div></div>')
        num = ['<div class="stat-tiles">'
               f'<div class="tile"><b>{played}</b><span>مباراة لُعبت</span></div>'
               f'<div class="tile"><b>{goals}</b><span>هدفًا</span></div>'
               f'<div class="tile"><b>{goals / played:.2f}</b><span>متوسط الأهداف/مباراة</span></div>'
               f'<div class="tile tile-res" title="{esc(big_t)}">'
               f'{score_pill(big["home_score"], big["away_score"], "sc-in")}'
               f'<span>أكبر نتيجة</span>{big_ms}{big_when}</div>'
               f'{sc_tile}'
               '</div>']
        pcts = league_pcts(fin)
        if pcts:
            num.append('<h3 class="stats-h3">📐 نِسَب البطولة</h3>')
            num.append(pcts)
        panes["numbers"] = "".join(num)
        if sc or asst:
            chart = ['<div class="chart-cols">']
            if sc:
                chart.append('<div><h3 class="stats-h3">⚽ ترتيب الهدافين</h3>'
                             + scorers_list(sc, "أهداف") + '</div>')
            if asst:
                chart.append('<div><h3 class="stats-h3">🎯 صانعو الأهداف</h3>'
                             + scorers_list(asst, "صناعة") + '</div>')
            chart.append('</div>')
            panes["scorers"] = "".join(chart)
        trend = []
        race = _pts_race_svg(fin, top_teams)
        if race:
            trend.append('<h3 class="stats-h3">سباق النقاط — المقدمة</h3>')
            trend.append(race)
        gsvg = _goals_svg(fin)
        if gsvg:
            trend.append('<h3 class="stats-h3">الأهداف في كل جولة</h3>')
            trend.append(gsvg)
        if trend:
            panes["trend"] = "".join(trend)
        return panes

    def league_stats_sec(comp, heading=True):
        """All of a league's stats as one section — used by /stats.html."""
        panes = league_stats_parts(comp)
        if not panes:
            return ""
        head_html = (f'<h2 class="lt-head">{comp_icon(comp)} {esc(comp_label(comp))}</h2>'
                     if heading else "")
        body = "".join(panes.get(k, "") for k in ("numbers", "scorers", "trend"))
        return f'<section class="stats-sec">{head_html}{body}</section>' 

    # ---- matches page (per-day navigator, like the live app) ----
    from collections import OrderedDict
    daymap = OrderedDict()
    for m in matches:
        daymap.setdefault(m.get("kickoff") or "", []).append(m)
    sorted_days = sorted(k for k in daymap.keys() if k)
    # distinct competitions across the feed (for the leagues sidebar):
    # every league seen in the day view, plus any league that has a standings
    # table or a rounds panel even if it has no match in the current window
    # (e.g. a league added before its season starts).
    comp_order = []
    for m in matches:
        c = m.get("competition") or ""
        if c and c not in comp_order:
            comp_order.append(c)
    for s in standings:
        c = s.get("competition") or ""
        if c and s.get("table") and c not in comp_order:
            comp_order.append(c)
    for f in fixtures:
        c = f.get("competition") or ""
        if c and c not in comp_order:
            comp_order.append(c)
    comp_order.sort(key=lambda c: (COMP_ORDER.index(c) if c in COMP_ORDER
                                   else len(COMP_ORDER), c))

    p = [head(f"مواعيد ونتائج المباريات — {SITE_NAME}",
              "مواعيد ونتائج مباريات كرة القدم بتوقيت القاهرة على يلا سكور.",
              SITE_BASE + "/matches.html", active="matches")]
    # the page had no <h1> at all (its visible heading structure starts at the
    # league sidebar's h2); a screen-reader-only h1 names the page for crawlers
    # without touching the FotMob-style layout
    p.append('<h1 class="sr-only">مواعيد ونتائج مباريات اليوم بتوقيت القاهرة</h1>')
    p.append('<div class="mpage">')

    # --- right rail (RTL start): leagues filter ---
    p.append('<aside class="mp-side mp-leagues"><h2 class="mp-h">البطولات</h2><div class="lg-list">')
    for c in comp_order:
        p.append(f'<button type="button" class="lg-item" data-comp="{esc(c)}">'
                 f'{comp_icon(c)} <span class="lg-name">{esc(comp_label(c))}</span></button>')
    p.append('</div></aside>')

    # --- center: league tables (hidden) + day navigator + days ---
    p.append('<div class="mp-main">')
    # ad strip at the top of the CENTER column - matches-list width only
    p.append(f'<div class="home-topad">{adsense_slot()}</div>')
    # one tabbed view per league: الترتيب · الهدافون · الأرقام · التطور · الجولات.
    # Everything is in the DOM (so it stays indexable); JS just switches panes.
    LEAGUE_TABS = [("table", "الترتيب"), ("scorers", "الهدافون"),
                   ("numbers", "الأرقام"), ("trend", "التطور"),
                   ("rounds", "الجولات")]
    for c in comp_order:
        st = st_by_comp.get(c)
        panes = league_stats_parts(c)
        if st and st.get("table"):
            panes["table"] = standings_table(
                c, st.get("table"), past=st.get("past"),
                season_label=st.get("season_label"), zeroed=st.get("zeroed"),
                form_map=forms.get(c, {}), embedded=True)
        if c in fx_by_comp:
            _fxs = COMP_SLUG.get(c)
            panes["rounds"] = league_rounds_panel(
                c, fx_by_comp[c], embedded=True, only_current=True,
                more_url=f"/fixtures/{_fxs}.html" if _fxs else None)
        live = [(k, lbl) for k, lbl in LEAGUE_TABS if panes.get(k)]
        if not live:
            continue
        p.append(f'<div class="lview" data-comp="{esc(c)}" hidden>')
        p.append('<div class="ltabs" role="tablist">')
        for i, (k, lbl) in enumerate(live):
            on = " is-on" if i == 0 else ""
            p.append(f'<button type="button" class="ltab{on}" role="tab" '
                     f'data-pane="{k}">{lbl}</button>')
        p.append('</div>')
        for i, (k, lbl) in enumerate(live):
            hid = "" if i == 0 else " hidden"
            p.append(f'<div class="lpane" data-pane="{k}"{hid}>{panes[k]}</div>')
        p.append('</div>')
    p.append('<div id="noTable" class="no-table" hidden></div>')  # empty state (league with no data)
    p.append('<div id="daynav" class="daynav" hidden>'
             '<button type="button" id="prevDay" class="dn-arrow" aria-label="اليوم السابق">‹</button>'
             '<span id="dayLabel" class="dn-label"></span>'
             '<button type="button" id="nextDay" class="dn-arrow" aria-label="اليوم التالي">›</button></div>')
    p.append(FILTERS_HTML)   # FotMob-style match filters (user ask 2026-09-02)
    p.append(f'<div id="days" data-today="{REF_TODAY}">')
    for d in sorted_days:
        p.append(f'<section class="day" data-day="{d}"><h2 class="day-h">{esc(fmt_day(d))}</h2>')
        comps = OrderedDict()
        for m in daymap[d]:
            comps.setdefault(m.get("competition") or "", []).append(m)
        # same fixed league order as the sidebar
        for comp, ms in sorted(comps.items(),
                               key=lambda kv: (COMP_ORDER.index(kv[0])
                                               if kv[0] in COMP_ORDER
                                               else len(COMP_ORDER), kv[0])):
            p.append(f'<div class="comp" data-comp="{esc(comp)}" data-label="{esc(comp_label(comp))}">')
            if comp:
                p.append(f'<div class="comp-h">{comp_icon(comp)} {esc(comp_label(comp))}</div>')
            p.append('<div class="mlist">')
            for m in ms:
                _mid, _mst = str(m.get("match_id")), (m.get("status") or "").upper()
                row = match_row(m, show_time=True, show_comp=False,
                                goals=match_goals(ge_idx, m),
                                link=match_url(m),
                                pred=_preds.get(_mid) if _mst == "UPCOMING" else None,
                                done=_plog.get(_mid) if _mst == "FINISHED" else None)
                # filter hooks: "على التلفزيون" = a known broadcaster (per-match
                # channel or the verified COMP_TV map); "حسب الوقت" sorts by data-ko
                tv = "1" if (m.get("channel") or COMP_TV.get(comp)) else "0"
                row = row.replace('<div class="mrow ',
                                  f'<div data-tv="{tv}" data-ko="{esc(m.get("koff_time") or "")}" class="mrow ', 1)
                p.append(row)
            p.append('</div></div>')
        p.append('<p class="no-comp" hidden>لا مباريات لهذه البطولة في هذا اليوم — جرّب يومًا آخر.</p>')
        p.append('</section>')
    p.append('</div></div>')  # /days /mp-main

    # --- left rail (RTL end): per-league fixtures BY ROUND (shown on select) ---
    # fallback (leagues with no round data): day-grouped from the day view
    comp_fix = {}
    for d in sorted_days:
        for m in daymap[d]:
            comp_fix.setdefault(m.get("competition") or "", {}).setdefault(d, []).append(m)
    p.append('<aside class="mp-side mp-extra">')
    # leagues WITHOUT rounds data still get a rail panel (day-grouped fallback);
    # leagues with rounds show them in the "الجولات" tab instead.
    for c in comp_order:
        if c not in fx_by_comp and comp_fix.get(c):
            p.append(f'<div class="lg-fix" data-comp="{esc(c)}" hidden>'
                     f'<div class="fx-head">{comp_icon(c)} مباريات {esc(comp_label(c))}</div>')
            for d in sorted(comp_fix[c].keys()):
                p.append(f'<div class="fx-day">{esc(fmt_day(d))}</div>')
                for m in comp_fix[c][d]:
                    p.append(fixture_mini(m))
            p.append('</div>')
    # default rail content: featured-article card + latest headlines -
    # swapped for the league rounds panel when a competition is selected
    p.append('<div id="mpDefault">')
    if articles:
        fa = articles[0]
        p.append(f'<a class="mp-feat" href="{article_href(fa)}">')
        if fa.get("image_url"):
            p.append(f'<img class="mp-feat-img" src="{esc(thumb_url(fa["image_url"]))}" alt="" loading="lazy">')
        p.append(f'<b class="mp-feat-t">{esc(fa.get("title"))}</b>'
                 '<span class="mp-feat-cta">اقرأ الخبر ←</span></a>')
        p.append('<div class="mp-news">')
        for a in articles[1:4]:
            img = thumb_url(a.get("image_url"))
            th = (f'<span class="mn-th" style="background-image:url(\'{esc(img)}\')"></span>'
                  if img else '<span class="mn-th noimg">⚽</span>')
            p.append(f'<a class="mn-item" href="{article_href(a)}">{th}'
                     f'<span class="mn-b"><span class="mn-t">{esc(a.get("title"))}</span>'
                     f'<span class="mn-d">{esc(a.get("pub_date") or "")}</span></span></a>')
        p.append('</div>')
    p.append('</div>')
    p.append('</aside>')

    p.append('</div>')  # /mpage
    p.append(MATCHES_JS)
    p.append(ROUNDS_JS)
    p.append(pred_pop(p))
    p.append(foot())
    write("matches.html", "".join(p))

    # ---- per-match pages (/m/<id>.html) ----
    # One landing page per match (archive ∪ current window): these target the
    # long-tail queries a single /matches.html can never rank for ("نتيجة
    # مباراة X"، "موعد مباراة Y والقناة الناقلة"). Old pages persist through
    # data/matches_archive.json (updated by fetch_data, committed back) so an
    # indexed URL doesn't 404 once the match leaves the day window. Pages get
    # the live layer for free: match_row emits data-lv, LIVE_JS ships in foot().
    os.makedirs(os.path.join(DIST, "m"), exist_ok=True)
    # finished matches per competition (season pool ∪ fixtures) - table_after()
    # uses it to prove the official table is describing THIS match and not a
    # later round
    _fin_by_comp = _finished_by_comp(fixtures, _bycomp)
    # h2h and rest days cross competitions (a club plays the league on Saturday
    # and the CAF Champions League on Tuesday), so keep a flat chronological list
    _fin_all = sorted((x for ms in _fin_by_comp.values() for x in ms),
                      key=lambda x: (x.get("kickoff") or "", x.get("koff_time") or ""))
    m_all = {m["match_id"]: m
             for m in load("matches_archive.json") if m.get("match_id")}
    for m in matches:
        if m.get("match_id"):
            m_all[m["match_id"]] = m      # day-window copy is always fresher
    # ±7 days, not ±30: see the sitemap note at the match-page append below
    sm_cut = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
    n_mp = 0
    n_mp_idx = 0
    n_mp_sm = 0
    for mid, m in sorted(m_all.items(), key=lambda kv: kv[1].get("kickoff") or ""):
        if not (m.get("home") and m.get("away") and m.get("kickoff")):
            continue
        h_ar, a_ar = ar_team(m.get("home")), ar_team(m.get("away"))
        comp = comp_label(m.get("competition") or "")
        st = (m.get("status") or "").upper()
        day_txt = fmt_day(m["kickoff"])
        hs, as_ = m.get("home_score"), m.get("away_score")
        when = day_txt + (f" الساعة {m['koff_time']} بتوقيت القاهرة"
                          if m.get("koff_time") else "")
        if st == "FINISHED" and hs is not None:
            title = f"نتيجة مباراة {h_ar} و{a_ar} {hs}-{as_} — {comp} | {SITE_NAME}"
            desc = (f"انتهت مباراة {h_ar} و{a_ar} في {comp} يوم {day_txt} "
                    f"بنتيجة {hs}-{as_}. مسجلو الأهداف وترتيب البطولة هنا.")
        elif st == "LIVE":
            title = f"مباراة {h_ar} و{a_ar} مباشر الآن — {comp} | {SITE_NAME}"
            desc = (f"تابع الآن مباشرة مباراة {h_ar} و{a_ar} في {comp} — "
                    "النتيجة لحظة بلحظة ومسجلو الأهداف.")
        elif st == "POSTPONED":
            title = f"تأجيل مباراة {h_ar} و{a_ar} — {comp} | {SITE_NAME}"
            desc = f"تأجلت مباراة {h_ar} و{a_ar} في {comp} التي كانت مقررة يوم {day_txt}."
        else:
            title = (f"موعد مباراة {h_ar} و{a_ar} والقنوات الناقلة — "
                     f"{comp} | {SITE_NAME}")
            desc = (f"موعد مباراة {h_ar} و{a_ar} في {comp}: {when}، "
                    "والقنوات الناقلة للمباراة. النتيجة المباشرة ومسجلو "
                    "الأهداف هنا فور انطلاق اللقاء.")
        img = None
        if m.get("home_badge"):
            _lc = local_crest(m["home_badge"])
            img = _lc if _lc.startswith("http") else SITE_BASE + _lc
        murl = f"/m/{mid}.html"
        _goals = match_goals(ge_idx, m)
        mp = [head(title, desc, SITE_BASE + murl, image=img, active="matches")]
        mp.append(f'<nav class="crumbs"><a href="/">أخبار</a> › '
                  f'<a href="/matches.html">المباريات</a> › {esc(comp)}</nav>')
        mp.append(f'<h1 class="page-h">مباراة {esc(h_ar)} و{esc(a_ar)}</h1>')
        # .mp-hero: LIVE_JS repaints THIS row's pill/score like any match row, and
        # since 2026-09-13 also the «الحالة» line of the info card below (the
        # user saw «لم تبدأ بعد» 18 min into a live match: the card was static
        # build-time text while the row above it already said مباشر)
        mp.append('<div class="mlist mp-hero">')
        mp.append(match_row(m, show_time=True, show_comp=True,
                            goals=_goals))
        mp.append('</div>')
        # «موعد المباراة والقنوات الناقلة» — a direct-answer paragraph for the
        # highest-volume pre-match queries ("موعد مباراة X"، "القنوات الناقلة
        # لمباراة Y"). Pre-match only: after kickoff the page's job is the
        # result. Channel comes from m["channel"] (per-match, when a source
        # provides it) else the verified per-league COMP_TV map, else an
        # honest "not announced" line — never a guess.
        if st not in ("FINISHED", "POSTPONED"):
            _tw = f"يوم {day_txt}"
            if m.get("koff_time"):
                _sa = ""
                try:
                    from zoneinfo import ZoneInfo
                    _dt = datetime.datetime.fromisoformat(
                        f"{m['kickoff']}T{m['koff_time']}:00"
                    ).replace(tzinfo=ZoneInfo("Africa/Cairo"))
                    _sa = _dt.astimezone(ZoneInfo("Asia/Riyadh")).strftime("%H:%M")
                except Exception:
                    pass
                if _sa == m["koff_time"]:
                    _tw += (f" في تمام الساعة {m['koff_time']} بتوقيت القاهرة "
                            "ومكة المكرمة")
                elif _sa:
                    _tw += (f" في تمام الساعة {m['koff_time']} بتوقيت القاهرة "
                            f"({_sa} بتوقيت مكة المكرمة)")
                else:
                    _tw += f" في تمام الساعة {m['koff_time']} بتوقيت القاهرة"
            _rd = f"الجولة {m['round']} من " if m.get("round") else ""
            mp.append(f'<section class="minfo"><h2>موعد مباراة {esc(h_ar)} '
                      f'و{esc(a_ar)} والقنوات الناقلة</h2>'
                      f'<p>تُقام مباراة <b>{esc(h_ar)}</b> و<b>{esc(a_ar)}</b> '
                      f'ضمن {_rd}{esc(comp)} {_tw}.</p>')
            if m.get("channel"):
                mp.append(f'<p>وتُنقل المباراة مباشرة عبر قناة '
                          f'<b>{esc(str(m["channel"]))}</b>.</p>')
            elif COMP_TV.get(m.get("competition")):
                mp.append(f'<p>وتُنقل مباريات {esc(comp)} في المنطقة العربية '
                          f'عبر قنوات <b>{esc(COMP_TV[m["competition"]])}</b>.</p>')
            else:
                mp.append('<p>لم تتوفر بعد معلومات القناة الناقلة لهذه '
                          'المباراة — تُحدَّث هذه الصفحة تلقائيًا فور توفرها.</p>')
            mp.append('</section>')
        # the match's own article (layer 3, 2026-09-16): the story sits above
        # the computed reading, which is what backs it with numbers
        _art = pick_match_article(_match_arts.get(str(mid)) or [], st)
        if _art:
            mp.append(match_article_block(_art, m.get("competition") or ""))
        # «قراءة قبل المباراة» (layer 1): how the two clubs arrive - table,
        # form, goals per game, the last meeting, a short turnaround, and what
        # a win is worth. Sits under the time/TV answer and above the XI.
        _pre_weight = 0
        if st == "UPCOMING":
            _pre, _pre_faq, _pre_weight = pre_match_read(
                m, h_ar, a_ar, comp,
                st_by_comp.get(m.get("competition")),
                forms.get(m.get("competition")) or {},
                _fin_by_comp.get(m.get("competition")) or [], _fin_all,
                _preds.get(str(mid)))
            if _pre:
                mp.append(_pre)
        _det = match_details_for(md_idx, m)
        # «قراءة المباراة» — the summary goes ABOVE the evidence: what happened
        # and what it changed, then the timeline and the XI that prove it.
        _faq_html = _pre_faq if st == "UPCOMING" and _pre_weight else ""
        if st == "FINISHED" and _det and hs is not None and as_ is not None:
            _read, _faq_html = post_match_read(
                m, _det[0], _det[1], h_ar, a_ar, hs, as_, comp,
                st_by_comp.get(m.get("competition")),
                forms.get(m.get("competition")) or {},
                _fin_by_comp.get(m.get("competition")) or [])
            if _read:
                mp.append(_read)
        if _det:
            mp.append(match_details_html(_det[0], _det[1], h_ar, a_ar))
        else:
            # announced XI before kick-off: the pitch, then who is missing
            _pre = prematch_for(md_idx, m)
            if _pre:
                mp.append(match_details_html(_pre[0], _pre[1], h_ar, a_ar))
        mp.append(absence_block(_squad, m.get("competition"), m, h_ar, a_ar))
        # «توقع يلا سكور»: model probabilities for an upcoming match; for a
        # finished one, what the model said before kick-off vs the result
        _pb = pred_block(m, _preds.get(str(mid)) if st == "UPCOMING" else None,
                         _plog.get(str(mid)), _tstats.get(m.get("competition"), {}),
                         params=_lparams.get(m.get("competition")), cal=_cal)
        if _pb:
            mp.append(_pb)
        info = [("البطولة", comp)]
        if m.get("round"):
            info.append(("الجولة", str(m["round"])))
        info.append(("التاريخ", day_txt))
        if m.get("koff_time"):
            info.append(("موعد الانطلاق", f"{m['koff_time']} بتوقيت القاهرة"))
        if m.get("channel"):
            info.append(("القناة الناقلة", str(m["channel"])))
        state_txt = {"FINISHED": "انتهت", "LIVE": "جارية الآن",
                     "UPCOMING": "لم تبدأ بعد", "POSTPONED": "مؤجلة"}.get(st)
        if state_txt:
            info.append(("الحالة", state_txt))
        mp.append('<section class="minfo"><h2>معلومات المباراة</h2><dl class="minfo-l">')
        for k, v in info:
            # the live layer overwrites the state text while the match can still
            # move (UPCOMING -> LIVE -> FINISHED); a finished page stays static
            hook = ' data-lv-state' if k == "الحالة" and st in ("UPCOMING", "LIVE") else ''
            mp.append(f'<div><dt>{esc(k)}</dt><dd{hook}>{esc(str(v))}</dd></div>')
        mp.append('</dl></section>')
        _clubs = [tp for tp in TEAM_PAGES if _team_match(tp, m)]
        if _clubs:
            mp.append('<nav class="club-chips"><span>صفحات الأندية:</span>'
                      + "".join(f'<a href="/team/{tp["slug"]}.html">أخبار '
                                f'{esc(tp["name"])}</a>' for tp in _clubs)
                      + '</nav>')
        stc = st_by_comp.get(m.get("competition"))
        if stc and stc.get("table"):
            _slug = COMP_SLUG.get(m.get("competition"))
            _h = (f'<a href="/standings/{_slug}.html">ترتيب {esc(comp)} ←</a>'
                  if _slug else f'ترتيب {esc(comp)}')
            mp.append(f'<section class="minfo"><h2>{_h}</h2>')
            mp.append(standings_table(m.get("competition"), stc["table"],
                                      past=stc.get("past"),
                                      season_label=stc.get("season_label"),
                                      zeroed=stc.get("zeroed"),
                                      form_map=forms.get(m.get("competition"), {}),
                                      embedded=True))
            mp.append('</section>')
        if _faq_html:
            mp.append(_faq_html)
        if articles:
            mp.append('<section class="minfo"><h2>آخر الأخبار</h2><ul class="mp-newslist">')
            for a in articles[:4]:
                mp.append(f'<li><a href="{article_href(a)}">{esc(a["title"])}</a></li>')
            mp.append('</ul></section>')
        # NO SportsEvent markup (removed 2026-09-23). Google's Event rich
        # result REQUIRES location (a Place with an address) and Search
        # Console flagged every match page critical for it: «Missing field
        # location» plus five recommended fields (offers, endDate, performer,
        # organizer.url, image). We hold NO venue data at all (0 mentions in
        # 402 detail entries) and inventing a stadium breaks the firm
        # never-show-possibly-wrong-data rule - so the markup could only ever
        # be invalid: all the GSC nagging, none of the rich result. The pages
        # keep BreadcrumbList and the embedded article's NewsArticle. If a
        # venue field is ever fetched from 365scores, revisit.
        mp.append(breadcrumb_ld([("أخبار", SITE_BASE + "/"),
                                 ("المباريات", SITE_BASE + "/matches.html"),
                                 (comp, SITE_BASE + murl)]))
        mp.append(foot())
        # lastmod: a page whose match is recent/upcoming changes every run;
        # an old finished match settled around its kickoff day.
        _LASTMOD[murl] = (REF_TODAY if m["kickoff"] >= (datetime.date.today()
                                                        - datetime.timedelta(days=2)).isoformat()
                          else m["kickoff"])
        # AdSense "low value content" rejection (2026-09-04): 457 templated
        # match pages vs 325 articles in the sitemap. A match page with no
        # real content yet (no scorers, no lineups/details) stays reachable
        # for visitors and links but is NOINDEXed and kept out of the
        # sitemap; it becomes indexable automatically once the data arrives.
        #
        # 2026-09-14: a fixture page is no longer automatically thin. When the
        # pre-match reading found at least four substantive facts (the table
        # standing, both form lines, the goal averages, the stakes...) the page
        # carries the kick-off answer, that reading, the model's numbers, the
        # league table and an FAQ - which is a guide, not a stub. A fixture we
        # know nothing about still scores below the bar and stays out.
        _rich = bool(_art) or bool(_goals) or bool(_det) or _pre_weight >= 4
        _html = "".join(mp)
        if not _rich:
            _html = _html.replace("<head>", '<head><meta name="robots" content="noindex">', 1)
        write(f"m/{mid}.html", _html)
        n_mp += 1
        if _rich:
            n_mp_idx += 1
            # WHAT WE ADVERTISE vs what we publish (2026-09-20). Every rich
            # match page stays indexable and linked; the sitemap carries only
            # the ones worth a crawl while the budget is what it is:
            #   - the last 7 days and everything still to come, which is what
            #     people actually search for;
            #   - any match of the eleven curated clubs, our own audience;
            #   - any page carrying an original article, because that URL
            #     replaced an article URL (2026-09-16).
            # The rest keep working for visitors and for links; they are just
            # not the pages we ask Google to spend its crawl on.
            if m["kickoff"] >= sm_cut or _art or _clubs:
                urls.append(murl)
                n_mp_sm += 1
    print(f"  + match pages: {n_mp} ({n_mp_idx} indexable, {n_mp_sm} in the sitemap)")

    # ---- per-league standings + top-scorers pages ----
    # Evergreen SEO landing pages with their own URLs: "ترتيب الدوري المصري"
    # and "هدافو الدوري المصري" are huge monthly queries that a tab inside
    # /matches.html can never rank for. One /standings/<slug>.html per league
    # with a table, and one /scorers/<slug>.html when the charts are current
    # (the stale-last-season guard sc_ok/as_ok gates them, same as /matches).
    os.makedirs(os.path.join(DIST, "standings"), exist_ok=True)
    os.makedirs(os.path.join(DIST, "scorers"), exist_ok=True)
    _n = datetime.date.today()
    season = (f"{_n.year}-{_n.year + 1}" if _n.month >= 7
              else f"{_n.year - 1}-{_n.year}")
    n_lp = 0
    _comps_with_table = set()
    for comp, slug in COMP_SLUG.items():
        label = comp_label(comp)
        st = st_by_comp.get(comp)
        if st and st.get("table"):
            _comps_with_table.add(comp)
        sc = sc_by_comp.get(comp) if sc_ok.get(comp) else None
        asst = as_by_comp.get(comp) if as_ok.get(comp) else None
        st_url, sc_url = f"/standings/{slug}.html", f"/scorers/{slug}.html"
        up_next = [m for m in matches
                   if m.get("competition") == comp
                   and (m.get("status") or "").upper() in ("UPCOMING", "LIVE")][:6]
        if st and st.get("table"):
            sp2 = [head(f"ترتيب {label} {season} — جدول الترتيب الكامل | {SITE_NAME}",
                        f"جدول ترتيب {label} لموسم {season} محدثًا تلقائيًا: "
                        "النقاط والمباريات والأهداف وفارق الأهداف "
                        "ونتائج آخر 5 مباريات لكل فريق.",
                        SITE_BASE + st_url, active="matches")]
            sp2.append(breadcrumb_ld([("أخبار", SITE_BASE + "/"),
                                      ("المباريات", SITE_BASE + "/matches.html"),
                                      (f"ترتيب {label}", SITE_BASE + st_url)]))
            sp2.append(f'<nav class="crumbs"><a href="/">أخبار</a> › '
                       f'<a href="/matches.html">المباريات</a> › ترتيب {esc(label)}</nav>')
            sp2.append(f'<h1 class="page-h">ترتيب {esc(label)} {esc(season)}</h1>')
            sp2.append(f'<p class="hintline">جدول {esc(label)} الكامل — يتحدّث '
                       'تلقائيًا بعد كل مباراة، مع نتائج آخر 5 مباريات لكل فريق.</p>')
            sp2.append(standings_table(comp, st["table"], past=st.get("past"),
                                       season_label=st.get("season_label"),
                                       zeroed=st.get("zeroed"),
                                       form_map=forms.get(comp, {}), embedded=True))
            _an, _faq = standings_analysis(comp, label, season, st["table"],
                                           forms.get(comp, {}), sc or [], up_next,
                                           zeroed=st.get("zeroed"))
            sp2.append(_an)
            if sc:
                sp2.append(f'<section class="minfo"><h2>'
                           f'<a href="{sc_url}">هدافو {esc(label)} ←</a></h2>'
                           + scorers_list(sc, "أهداف") + '</section>')
            if up_next:
                sp2.append(f'<section class="minfo"><h2>مباريات {esc(label)} القادمة</h2>'
                           '<div class="mlist">')
                for m in up_next:
                    sp2.append(match_row(m, show_time=True, show_comp=False,
                                         link=match_url(m),
                                         pred=_preds.get(str(m.get("match_id")))))
                sp2.append('</div></section>')
            sp2.append(_faq)
            sp2.append(pred_pop(sp2))
            sp2.append(foot())
            write(f"standings/{slug}.html", "".join(sp2))
            urls.append(st_url)
            n_lp += 1
        if sc or (st and st.get("table")):
            # the page must exist whenever the league is active (the footer
            # links to /scorers/egypt.html sitewide) — a stale-gated chart
            # gets a placeholder, never last season's names
            cp = [head(f"هدافو {label} {season} — ترتيب الهدافين وصناع الأهداف | {SITE_NAME}",
                       f"قائمة هدافي {label} لموسم {season} محدثة تلقائيًا بعد كل "
                       "جولة، مع ترتيب صناع الأهداف (التمريرات الحاسمة).",
                       SITE_BASE + sc_url, active="matches")]
            cp.append(f'<nav class="crumbs"><a href="/">أخبار</a> › '
                      f'<a href="/matches.html">المباريات</a> › هدافو {esc(label)}</nav>')
            cp.append(f'<h1 class="page-h">هدافو {esc(label)} {esc(season)}</h1>')
            cp.append('<section class="minfo"><h2>ترتيب الهدافين</h2>'
                      + (scorers_list(sc, "أهداف") if sc else
                         '<p class="hintline">تُحدَّث قائمة الهدافين تلقائيًا '
                         'مع انطلاق جولات الموسم الجديد.</p>')
                      + '</section>')
            if asst:
                cp.append('<section class="minfo"><h2>صناع الأهداف</h2>'
                          + scorers_list(asst, "صناعة") + '</section>')
            # a list of ten names is not a page; the reading is what makes it
            # one (2026-09-16, after an outside audit found /scorers/egypt
            # empty — see scorers_read)
            _sr, _sfaq, _sw = scorers_read(label, season, sc, asst,
                                           (st or {}).get("table"), _bycomp.get(comp))
            if _sr:
                cp.append(_sr)
            if st and st.get("table"):
                cp.append(f'<p class="hintline">شاهد أيضًا: '
                          f'<a href="{st_url}">جدول ترتيب {esc(label)} كاملًا</a></p>')
            if _sfaq:
                cp.append(_sfaq)
            cp.append(foot())
            # Indexable only once the page says something: the chart plus a
            # reading of at least three facts. Under that it stays what it was
            # before — a page for visitors and old links, out of the index and
            # out of the sitemap — because ~80 words of names is exactly the
            # thin content the AdSense rejection named.
            _rich_sc = bool(sc) and _sw >= 3
            _html = "".join(cp)
            if not _rich_sc:
                _html = _html.replace("<head>", '<head><meta name="robots" content="noindex">', 1)
            write(f"scorers/{slug}.html", _html)
            if _rich_sc:
                urls.append(sc_url)
            n_lp += 1
    print(f"  + league pages: {n_lp}")

    # ---- per-league season fixtures (/fixtures/<slug>.html) ----
    # These used to be INSIDE /matches, hidden behind the league filter: 2,206
    # fixture rows and 4,955 crest tags that every visitor downloaded to look
    # at the 82 rows of one day. As their own pages they cost nothing to the
    # people who do not want them and answer a real query - «جدول مباريات
    # الدوري المصري» - which a megabyte of hidden markup never could.
    os.makedirs(os.path.join(DIST, "fixtures"), exist_ok=True)
    n_fx = 0
    for comp, slug in COMP_SLUG.items():
        fx = fx_by_comp.get(comp)
        rounds = (fx or {}).get("rounds") or []
        if not rounds:
            continue
        label = comp_label(comp)
        n_m = sum(len(r.get("matches") or []) for r in rounds)
        fp = [head(f"جدول مباريات {label} {season} — كل الجولات | {SITE_NAME}",
                   f"جدول مباريات {label} لموسم {season} كاملًا: {len(rounds)} جولة "
                   f"و{n_m} مباراة بمواعيدها ونتائجها، محدّثًا تلقائيًا بعد كل جولة.",
                   SITE_BASE + f"/fixtures/{slug}.html", active="matches")]
        fp.append(f'<nav class="crumbs"><a href="/">أخبار</a> › '
                  f'<a href="/matches.html">المباريات</a> › جدول {esc(label)}</nav>')
        fp.append(f'<h1 class="page-h">جدول مباريات {esc(label)} {esc(season)}</h1>')
        fp.append(f'<section class="minfo"><p>كل جولات {esc(label)} لموسم {esc(season)} — '
                  f'<b>{len(rounds)}</b> جولة و<b>{n_m}</b> مباراة. المباريات المنتهية '
                  'تظهر بنتيجتها والقادمة بموعدها بتوقيت القاهرة، ويتحدّث الجدول تلقائيًا '
                  'بعد كل مباراة. استخدم ‹ و› للتنقل بين الجولات.</p></section>')
        fp.append(league_rounds_panel(comp, fx, embedded=True))
        _links = [f'<a href="/matches.html">مباريات اليوم ←</a>']
        if comp in st_by_comp and (st_by_comp[comp] or {}).get("table"):
            _links.append(f'<a href="/standings/{slug}.html">ترتيب {esc(label)} ←</a>')
        if comp in COMP_SLUG and os.path.exists(os.path.join(DIST, "analysis", f"{slug}.html")):
            _links.append(f'<a href="/analysis/{slug}.html">تحليلات وتوقعات {esc(label)} ←</a>')
        fp.append('<p class="more-link">' + ' · '.join(_links) + '</p>')
        fp.append(breadcrumb_ld([("أخبار", SITE_BASE + "/"),
                                 ("المباريات", SITE_BASE + "/matches.html"),
                                 (f"جدول {label}", SITE_BASE + f"/fixtures/{slug}.html")]))
        fp.append(foot())
        fp.append(ROUNDS_JS)
        write(f"fixtures/{slug}.html", "".join(fp))
        urls.append(f"/fixtures/{slug}.html")
        _LASTMOD[f"/fixtures/{slug}.html"] = REF_TODAY
        n_fx += 1
    print(f"  + season fixture pages: {n_fx}")

    # ---- تحليلات: /analysis hub + /analysis/<league> ----
    os.makedirs(os.path.join(DIST, "analysis"), exist_ok=True)
    _hist_url = prediction_history_page(_plog, _acc)
    if _hist_url:
        urls.append(_hist_url)
        print(f"  + prediction history: {_acc['all']['n']} scored predictions")
    _an_urls = analysis_pages(matches, _upcoming, _preds, _plog, _acc, _tstats, _lparams,
                              _pins, _sins, forms, _comps_with_table)
    urls.extend(_an_urls)
    print(f"  + analysis pages: {len(_an_urls)}")

    # ---- per-club pages (/team/<slug>) ----
    # Evergreen SEO hubs for the highest-volume Arabic query family we don't
    # cover: "أخبار الأهلي اليوم"، "مباريات الزمالك القادمة"، "نتيجة ريال
    # مدريد". One page per curated club: latest club news + next matches +
    # recent results + league standing, refreshed every publish cycle.
    # Cross-linked from article pages + match pages (club-chips) + footer.
    os.makedirs(os.path.join(DIST, "team"), exist_ok=True)
    club_matches_src = sorted(m_all.values(),
                              key=lambda m: m.get("kickoff") or "")
    for tp in TEAM_PAGES:
        name, slug = tp["name"], tp["slug"]
        league_ar = comp_label(tp["league"])
        cm = [m for m in club_matches_src
              if _team_match(tp, m) and m.get("home") and m.get("kickoff")]
        up_next = [m for m in cm
                   if (m.get("status") or "").upper() in ("UPCOMING", "LIVE")
                   and m["kickoff"] >= REF_TODAY][:3]
        last_res = [m for m in reversed(cm)
                    if (m.get("status") or "").upper() == "FINISHED"
                    and m.get("home_score") is not None][:5]
        news = [a for a in articles if _team_news(tp, a)][:8]
        st = st_by_comp.get(tp["league"])
        srow = None
        if st and st.get("table") and not st.get("zeroed"):
            for r in st["table"]:
                if any(t in (r.get("team") or "") for t, _ in tp["match_tokens"]):
                    srow = r
                    break
        crest = ""
        if srow and srow.get("crest"):
            crest = local_crest(srow["crest"])
        else:
            for m in reversed(cm):
                for side in ("home", "away"):
                    if (any(t in (m.get(side) or "")
                            for t, _ in tp["match_tokens"])
                            and m.get(side + "_badge")):
                        crest = local_crest(m[side + "_badge"])
                        break
                if crest:
                    break
        t_url = f"/team/{slug}.html"
        title = (f"أخبار {name} اليوم — مباريات ونتائج وترتيب {name} "
                 f"{season} | {SITE_NAME}")
        desc = (f"آخر أخبار {name} اليوم، موعد مباراة {name} القادمة، نتائج "
                f"آخر المباريات وترتيب {name} في {league_ar} {season} — "
                "تتحدّث الصفحة تلقائيًا على مدار اليوم.")
        img = (crest if crest.startswith("http")
               else SITE_BASE + crest) if crest else None
        pt = [head(title, desc, SITE_BASE + t_url, image=img)]
        pt.append(breadcrumb_ld([("أخبار", SITE_BASE + "/"),
                                 ("المباريات", SITE_BASE + "/matches.html"),
                                 (name, SITE_BASE + t_url)]))
        pt.append(f'<nav class="crumbs"><a href="/">أخبار</a> › '
                  f'<a href="/matches.html">المباريات</a> › {esc(name)}</nav>')
        _img = (f'<img class="club-crest" src="{esc(crest)}" alt="{esc(name)}" '
                'width="64" height="64" loading="eager">' if crest else "")
        _pos = ""
        if srow:
            _pos = (f'<p class="club-pos">المركز <b>{srow.get("pos")}</b> في '
                    f'{esc(league_ar)} برصيد <b>{srow.get("pts")}</b> نقطة '
                    f'من {srow.get("played")} مباراة</p>')
        pt.append(f'<header class="club-hero">{_img}<div>'
                  f'<h1 class="page-h">أخبار {esc(name)}</h1>'
                  f'<p class="hintline">كل جديد {esc(name)}: الأخبار والمباريات '
                  f'والنتائج والترتيب في مكان واحد — تتحدّث تلقائيًا.</p>'
                  f'{_pos}</div></header>')
        if up_next:
            pt.append(f'<section class="minfo"><h2>مباريات {esc(name)} القادمة</h2>'
                      '<div class="mlist">')
            for m in up_next:
                pt.append(match_row(m, show_time=True, show_comp=True,
                                    link=match_url(m),
                                    pred=_preds.get(str(m.get("match_id")))))
            pt.append('</div></section>')
        if last_res:
            pt.append(f'<section class="minfo"><h2>آخر نتائج {esc(name)}</h2>'
                      '<div class="mlist">')
            for m in last_res:
                pt.append(match_row(m, show_time=False, show_comp=True,
                                    link=match_url(m),
                                    done=_plog.get(str(m.get("match_id")))))
            pt.append('</div></section>')
        pt.append(f'<section class="minfo"><h2>آخر أخبار {esc(name)}</h2>')
        if news:
            pt.append('<ul class="mp-newslist">')
            for a in news:
                _t = art_reltime(a)
                pt.append(f'<li><a href="{article_href(a)}">'
                          f'{esc(a["title"])}</a>'
                          + (f' <span class="club-when">({_t})</span>' if _t else "")
                          + '</li>')
            pt.append('</ul>')
        else:
            pt.append('<p class="hintline">تُنشر أخبار '
                      f'{esc(name)} هنا فور ورودها.</p>')
        pt.append('</section>')
        if st and st.get("table"):
            _slug = COMP_SLUG.get(tp["league"])
            _h = (f'<a href="/standings/{_slug}.html">ترتيب {esc(league_ar)} ←</a>'
                  if _slug else f'ترتيب {esc(league_ar)}')
            pt.append(f'<section class="minfo"><h2>{_h}</h2>')
            pt.append(standings_table(tp["league"], st["table"],
                                      past=st.get("past"),
                                      season_label=st.get("season_label"),
                                      zeroed=st.get("zeroed"),
                                      form_map=forms.get(tp["league"], {}),
                                      embedded=True))
            pt.append('</section>')
        others = [o for o in TEAM_PAGES if o["slug"] != slug]
        pt.append('<nav class="club-chips"><span>أندية أخرى:</span>'
                  + "".join(f'<a href="/team/{o["slug"]}.html">{esc(o["name"])}</a>'
                            for o in others)
                  + '</nav>')
        pt.append(jsonld({
            "@context": "https://schema.org", "@type": "SportsTeam",
            "name": name, "sport": "Football", "url": SITE_BASE + t_url,
            **({"logo": img} if img else {}),
            "memberOf": {"@type": "SportsOrganization", "name": league_ar},
        }))
        pt.append(pred_pop(pt))
        pt.append(foot())
        write(f"team/{slug}.html", "".join(pt))
        urls.append(t_url)
    print(f"  + club pages: {len(TEAM_PAGES)}")

    # ---- stats dashboard (/stats.html) ----
    sp = [head(f"إحصائيات وتحليلات — {SITE_NAME}",
               "لوحة إحصائيات مرئية: سباق النقاط، الأهداف في كل جولة، وأرقام الموسم لكل بطولة.",
               SITE_BASE + "/stats.html", active="stats")]
    sp.append(page_head_ad(
        '<h1 class="page-h">📊 إحصائيات وتحليلات</h1>',
        'أرقام محسوبة من نتائج الموسم الحالي — تتحدّث تلقائيًا بعد كل جولة.'))
    sp.append(clubs_panel(st_by_comp, sc_ok, sc_by_comp, forms, matches, fixtures))
    any_stats = False
    for comp in comp_order:
        sec = league_stats_sec(comp)
        if sec:
            any_stats = True
            sp.append(sec)
    if not any_stats:
        sp.append('<p class="hintline">لا توجد بيانات كافية بعد — تعود اللوحة للعمل مع انطلاق الجولات.</p>')
    sp.append(foot())
    html_out = "".join(sp)
    if not SHOW_STATS_PAGE:
        html_out = html_out.replace("<head>", '<head><meta name="robots" content="noindex">', 1)
    write("stats.html", html_out)
    if SHOW_STATS_PAGE:
        urls.append("/stats.html")

    # ---- 404 page (served by Cloudflare for any missing asset) ----
    # Not in the sitemap on purpose. The auto-retry exists for one real case:
    # an article page can 404 for a minute or two right around a deploy while
    # the reader already holds a newer home page — the page re-checks itself
    # and reloads the moment the URL starts resolving, so that reader never
    # has to do anything. Bounded retries: a genuinely dead link stops
    # polling after ~2 minutes and stays a normal 404.
    nf = [head(f"الصفحة غير موجودة — {SITE_NAME}",
               "الصفحة التي تبحث عنها غير موجودة.",
               SITE_BASE + "/404.html")]
    nf.append('<div class="nf"><div class="nf-emoji">⚽</div>')
    nf.append('<h1 class="page-h">الصفحة غير موجودة</h1>')
    nf.append('<p class="nf-p">يبدو أن الرابط غير صحيح أو أن الصفحة لم تعد متاحة.</p>')
    nf.append('<p class="nf-p nf-wait" id="nfWait" hidden>لو ده خبر نُشر حالًا فهو '
              'يتجهّز الآن — الصفحة ستفتح تلقائيًا خلال لحظات <span class="nf-spin"></span></p>')
    nf.append('<p class="nf-links"><a class="nf-btn" href="/">الصفحة الرئيسية</a>'
              '<a class="nf-btn nf-btn2" href="/matches.html">المباريات</a>'
              '<a class="nf-btn nf-btn2" href="/news.html">كل الأخبار</a></p>')
    nf.append('</div>')
    nf.append(r"""<script>
(function(){
  /* auto-retry only where it can help: article pages right after a deploy */
  if(!/^\/a\//.test(location.pathname)||!window.fetch)return;
  var w=document.getElementById('nfWait'); if(w)w.hidden=false;
  var tries=0;
  function again(){
    if(++tries>6){if(w)w.hidden=true;return;}   /* ~2 min then give up */
    fetch(location.href,{cache:'no-store'}).then(function(r){
      if(r.ok){location.reload();}else{setTimeout(again,20000);}
    }).catch(function(){setTimeout(again,20000);});
  }
  setTimeout(again,15000);
})();
</script>""")
    nf.append(foot())
    write("404.html", "".join(nf))

    # ---- privacy policy (required for AdSense) ----
    contact = (f'راسِلنا على <a href="mailto:{esc(CONTACT_EMAIL)}">{esc(CONTACT_EMAIL)}</a>.'
               if CONTACT_EMAIL else 'يمكنك التواصل معنا عبر قنواتنا الرسمية.')
    pv = [head("سياسة الخصوصية — " + SITE_NAME,
               "سياسة الخصوصية وملفات تعريف الارتباط والإعلانات في موقع يلا سكور.",
               SITE_BASE + "/privacy.html")]
    pv.append('<article class="article legal"><h1>سياسة الخصوصية</h1>')
    pv.append(f'<p class="a-meta">آخر تحديث: {REF_TODAY}</p><div class="a-body">')
    pv.append('<p>خصوصيتك تهمّنا. توضّح هذه الصفحة كيف يتعامل موقع <b>يلا سكور</b> مع المعلومات عند زيارتك له.</p>')
    pv.append('<h2>المعلومات التي نجمعها</h2><p>الموقع لا يطلب منك التسجيل أو إدخال بيانات شخصية. وقد تُجمَع بيانات تقنية بشكل تلقائي (مثل نوع المتصفح ونظام التشغيل والصفحات التي تزورها) عبر ملفات تعريف الارتباط وخدمات الطرف الثالث بهدف تشغيل الموقع وتحسينه.</p>')
    pv.append('<h2>ملفات تعريف الارتباط (Cookies)</h2><p>قد نستخدم ملفات تعريف الارتباط لحفظ تفضيلاتك وتحسين تجربتك ولعرض الإعلانات. يمكنك ضبط متصفحك لرفض ملفات تعريف الارتباط كليًا أو جزئيًا، مع العلم أن ذلك قد يؤثّر على بعض وظائف الموقع.</p>')
    # 2026-09-16: the paragraph used to name the «DART cookie» — wording Google
    # retired years ago and that survives only in copied templates. Replaced
    # with how AdSense actually describes it today (first- and third-party
    # cookies, doubleclick.net / googlesyndication.com), per
    # support.google.com/adsense/answer/7549925.
    pv.append('<h2>إعلانات الطرف الثالث — Google AdSense</h2><p>قد نعرض إعلانات عبر خدمة <b>Google AdSense</b>. تستخدم Google والشركات الشريكة لها ملفات تعريف ارتباط — بعضها من نطاق الموقع نفسه وبعضها من نطاقات خارجية مثل <span dir="ltr">doubleclick.net</span> و<span dir="ltr">googlesyndication.com</span> — لقياس أداء الإعلانات ومنع تكرارها واكتشاف الاحتيال، ولعرض إعلانات مبنية على زياراتك السابقة لهذا الموقع أو لمواقع أخرى.</p>')
    pv.append('<p>يمكنك تعطيل الإعلانات المخصّصة من خلال <a href="https://www.google.com/settings/ads" target="_blank" rel="noopener">إعدادات إعلانات Google</a>، ومعرفة المزيد عبر <a href="https://policies.google.com/technologies/ads" target="_blank" rel="noopener">سياسة Google بشأن الإعلانات</a>.</p>')
    pv.append('<h2>الروابط الخارجية</h2><p>يحتوي الموقع على روابط لمصادر إخبارية ومواقع خارجية. عند الضغط عليها تنتقل إلى مواقع لا نتحكّم فيها، ولا نتحمّل مسؤولية سياسات الخصوصية أو المحتوى الخاص بها.</p>')
    pv.append('<h2>خصوصية الأطفال</h2><p>الموقع غير موجَّه للأطفال دون 13 عامًا، ولا نجمع عمدًا أي بيانات منهم.</p>')
    pv.append('<h2>التعديلات على هذه السياسة</h2><p>قد نُحدّث هذه السياسة من وقت لآخر، ويُشير تاريخ «آخر تحديث» أعلاه إلى أحدث نسخة.</p>')
    pv.append(f'<h2>التواصل</h2><p>لأي استفسار بخصوص سياسة الخصوصية، {contact}</p>')
    pv.append('</div></article>')
    pv.append(foot())
    write("privacy.html", "".join(pv))
    urls.append("/privacy.html")

    # ---- about page (من نحن) — helps AdSense/E-E-A-T review ----
    ab = [head("من نحن — " + SITE_NAME,
               "تعرّف على يلا سكور: موقع عربي لأخبار كرة القدم ونتائج المباريات وجداول الترتيب.",
               SITE_BASE + "/about.html")]
    ab.append('<article class="article legal"><h1>من نحن</h1><div class="a-body">')
    ab.append(f'<p><b>{esc(SITE_NAME)}</b> موقع عربي متخصص في كرة القدم، يقدّم أخبار الكرة المصرية '
              'والعالمية، ومواعيد ونتائج المباريات، وجداول ترتيب أبرز البطولات — في مكان واحد وبواجهة سريعة وبسيطة.</p>')
    ab.append('<h2>ماذا نقدّم؟</h2><ul>'
              '<li><b>أخبار بصياغتنا:</b> يُعِدّ <a href="/editors.html">مصطفى عبدالسلام</a>، مدير تحرير الموقع، المقالات '
              '(بمساعدة أدوات ذكاء اصطناعي في الصياغة وتحت مراجعته — '
              '<a href="/editorial.html">إفصاح كامل هنا</a>) '
              'من الحقائق التي أكّدها مصدران مستقلان على الأقل، مع تسمية المصدر داخل الخبر وإضافة الخلفية '
              'والأرقام وما يعنيه الخبر — دون نسخ نصوص المواقع الأخرى. '
              '<a href="/editorial.html">تفاصيل طريقة العمل في السياسة التحريرية</a>.</li>'
              '<li><b>عناوين من المصادر:</b> نجمع أحدث عناوين الصحف والمواقع الرياضية مع رابط مباشر إلى المصدر الأصلي '
              'لقراءة التفاصيل كاملة على موقعه.</li>'
              '<li><b>مباريات وترتيب:</b> مواعيد ونتائج المباريات وجداول الترتيب لأبرز الدوريات والبطولات، '
              'تُحدَّث تلقائيًا على مدار اليوم من مصادر بيانات موثوقة.</li></ul>')
    ab.append('<h2>معاييرنا التحريرية</h2><ul>'
              '<li>لا ننشر خبرًا إلا بعد تأكيده من أكثر من مصدر، ونتجنّب الشائعات المتضاربة.</li>'
              '<li>ننسب المعلومات إلى مصادرها ("بحسب تقارير صحفية") ولا نختلق تصريحات أو أرقامًا.</li>'
              '<li>نستخدم صورًا مرخّصة للاستخدام الحر فقط (Creative Commons / الملكية العامة) مع ذكر صاحب الصورة والرخصة.</li></ul>')
    ab.append(f'<h2>تواصل معنا</h2><p>لأي ملاحظة أو تصحيح أو استفسار، تفضّل بزيارة صفحة '
              f'<a href="/contact.html">اتصل بنا</a>.</p>')
    ab.append('</div></article>')
    ab.append(foot())
    write("about.html", "".join(ab))
    urls.append("/about.html")


    # ---- editorial team page (فريق التحرير) — publisher identity for the
    # AdSense / E-E-A-T review (2nd rejection 2026-09-04 cited low value
    # content); linked from every article byline, the footer and /about ----
    ed = [head("فريق التحرير — " + SITE_NAME,
               f"من يقف خلف {SITE_NAME}: مدير التحرير، طريقة عملنا في التحقق من الأخبار، وكيف تتواصل معنا للتصحيح.",
               SITE_BASE + "/editors.html")]
    ed.append('<article class="article legal"><h1>فريق التحرير</h1><div class="a-body">')
    ed.append(f'<p>{esc(SITE_NAME)} موقع مصري مستقل لأخبار كرة القدم ونتائج المباريات. '
              'يشرف على المحتوى مدير تحرير واحد مسؤول عن كل ما يُنشر، ويتلقى التصحيحات والملاحظات مباشرة.</p>')
    ed.append('<h2>مدير التحرير</h2>'
              f'<div class="ed-card"><div class="ed-name">{esc(EDITOR_NAME)}</div>'
              f'<div class="ed-role">{esc(EDITOR_ROLE)} ومؤسس {esc(SITE_NAME)}</div>'
              f'<p>مطوّر برمجيات مصري ومتابع للكرة المصرية والأوروبية. يضع السياسة التحريرية للموقع، '
              'ويراجع ما يُنشر، ويردّ على طلبات التصحيح. <b>كل مقال على الموقع يحمل توقيعه</b> '
              'باعتباره المسؤول عن محتواه.</p>'
              f'<p class="ed-contact">البريد: <a href="mailto:{esc(EDITOR_EMAIL)}">{esc(EDITOR_EMAIL)}</a> · '
              f'<a href="{esc(FB_PAGE_URL)}" target="_blank" rel="noopener">صفحة الموقع على فيسبوك</a> · '
              f'<a href="{esc(TG_CHANNEL_URL)}" target="_blank" rel="noopener">قناة الموقع على تيليجرام</a></p></div>')
    ed.append('<h2>كيف نعمل</h2><ul>'
              '<li><b>التحقق أولًا:</b> لا يُنشر خبر إلا بعد تأكيده من مصدرين مستقلين على الأقل، '
              'ونتجاهل الشائعات المتضاربة حتى تُحسم.</li>'
              '<li><b>صياغة أصلية:</b> كل مقال مكتوب بصياغتنا، مع نسبة المعلومات إلى مصادرها ودون اختلاق تصريحات أو أرقام.</li>'
              '<li><b>إفصاح:</b> تُصاغ المقالات بمساعدة أدوات ذكاء اصطناعي من حقائق تحقّقنا منها، '
              'تحت إشرافي ومراجعتي، وأنا المسؤول عن كل ما يُنشر — '
              '<a href="/editorial.html">التفاصيل في السياسة التحريرية</a>.</li>'
              '<li><b>بيانات المباريات:</b> النتائج وجداول الترتيب والهدافون تُحدَّث آليًا من مزوّدي بيانات متخصصين، '
              'وتُراجع قواعد سلامتها باستمرار حتى لا يظهر رقم غير مؤكد.</li>'
              '<li><b>الصور:</b> نستخدم صورًا مرخّصة للاستخدام الحر فقط، مع ذكر المصوّر والرخصة تحت كل صورة.</li>'
              '<li><b>التصحيح:</b> عند اكتشاف خطأ نصحّحه في المقال نفسه في أسرع وقت. '
              f'أبلغنا عبر <a href="mailto:{esc(EDITOR_EMAIL)}">{esc(EDITOR_EMAIL)}</a> أو صفحة '
              '<a href="/contact.html">اتصل بنا</a>.</li></ul>')
    ed.append('<p>التفاصيل الكاملة في <a href="/editorial.html">السياسة التحريرية</a>.</p>')
    ed.append('</div></article>')
    ed.append(jsonld({
        "@context": "https://schema.org", "@type": "ProfilePage",
        "name": f"فريق التحرير — {SITE_NAME}", "url": SITE_BASE + "/editors.html",
        "mainEntity": {"@type": "Person", "name": EDITOR_NAME, "jobTitle": EDITOR_ROLE,
                       "email": f"mailto:{EDITOR_EMAIL}", "url": SITE_BASE + "/editors.html",
                       "worksFor": {"@type": "Organization", "name": SITE_NAME, "url": SITE_BASE}},
    }))
    ed.append(foot())
    write("editors.html", "".join(ed))
    urls.append("/editors.html")

    # ---- contact page (اتصل بنا) ----
    ct = [head("اتصل بنا — " + SITE_NAME,
               "تواصل مع فريق يلا سكور للاستفسارات والتصحيحات والإعلانات.",
               SITE_BASE + "/contact.html")]
    ct.append('<article class="article legal"><h1>اتصل بنا</h1><div class="a-body">')
    ct.append('<p>يسعدنا تواصلك معنا في أي من الحالات التالية:</p><ul>'
              '<li>تصحيح معلومة وردت في خبر منشور.</li>'
              '<li>ملاحظات على حقوق صورة أو محتوى.</li>'
              '<li>استفسارات الإعلانات والشراكات.</li>'
              '<li>اقتراحات لتطوير الموقع.</li></ul>')
    if CONTACT_EMAIL:
        ct.append(f'<p>راسلنا على البريد الإلكتروني: '
                  f'<a href="mailto:{esc(CONTACT_EMAIL)}"><b>{esc(CONTACT_EMAIL)}</b></a> '
                  'وسنرد في أقرب وقت ممكن.</p>')
    else:
        ct.append('<p>سيتم إضافة بريد التواصل الرسمي قريبًا.</p>')
    ct.append('</div></article>')
    ct.append(foot())
    write("contact.html", "".join(ct))
    urls.append("/contact.html")

    # ---- terms of use (شروط الاستخدام) ----
    tm = [head("شروط الاستخدام — " + SITE_NAME,
               "شروط استخدام موقع يلا سكور: حدود المسؤولية وقواعد استخدام المحتوى.",
               SITE_BASE + "/terms.html")]
    tm.append('<article class="article legal"><h1>شروط الاستخدام</h1><div class="a-body">')
    tm.append(f'<p>باستخدامك موقع <b>{esc(SITE_NAME)}</b> فأنت توافق على الشروط التالية:</p>')
    tm.append('<h2>طبيعة المحتوى</h2><ul>'
              '<li>الموقع يقدّم أخبارًا ونتائج ومواعيد مباريات لأغراض إعلامية عامة.</li>'
              '<li>نبذل جهدًا دائمًا لضمان دقة النتائج والمواعيد المعروضة، إلا أنها تصل من مصادر '
              'بيانات خارجية وقد يطرأ عليها تأخير أو تعديل، لذا لا نضمن خلوّها من الخطأ، '
              'ولا يتحمّل الموقع مسؤولية أي قرار يُتّخذ بناءً عليها.</li>'
              '<li>روابط عناوين الصحف تقود إلى مواقع خارجية لا نتحكم في محتواها ولا نتحمل مسؤوليته.</li></ul>')
    tm.append('<h2>حقوق المحتوى</h2><ul>'
              '<li>المقالات المنشورة على الموقع باسم محرره ملك للموقع؛ يُسمح بالاقتباس المختصر مع ذكر '
              'المصدر ورابط المقال، ولا يجوز إعادة النشر الكامل دون إذن.</li>'
              '<li>الصور المستخدمة مرخّصة للاستخدام الحر (Creative Commons / الملكية العامة) '
              'وتُنسب لأصحابها؛ شعارات الأندية والبطولات ملك لأصحابها وتُعرض لغرض التعريف فقط.</li></ul>')
    tm.append('<h2>الإعلانات</h2>'
              '<p>قد يعرض الموقع إعلانات عبر Google AdSense؛ راجع <a href="/privacy.html">سياسة الخصوصية</a> '
              'لتفاصيل ملفات تعريف الارتباط.</p>')
    tm.append('<h2>تعديل الشروط</h2>'
              '<p>قد نُحدّث هذه الشروط من وقت لآخر، ويُعد استمرارك في استخدام الموقع موافقةً على النسخة الأحدث.</p>')
    tm.append('</div></article>')
    tm.append(foot())
    write("terms.html", "".join(tm))
    urls.append("/terms.html")

    # ---- editorial policy (السياسة التحريرية) — E-E-A-T signal ----
    ed = [head("السياسة التحريرية — " + SITE_NAME,
               "منهج يلا سكور التحريري: التحقق من مصادر متعددة، صياغة أصلية، صور مرخصة، وتصحيح علني للأخطاء.",
               SITE_BASE + "/editorial.html")]
    ed.append('<article class="article legal"><h1>السياسة التحريرية</h1><div class="a-body">')
    ed.append('<p>نلتزم في تغطيتنا الإخبارية بمعايير ثابتة نطبّقها على كل مقال ننشره:</p>')
    ed.append('<h2>التحقق قبل النشر</h2><ul>'
              '<li>لا ننشر خبرًا إلا بعد تطابقه لدى <b>مصدرين مستقلين على الأقل</b>.</li>'
              '<li>نتجنّب نشر الشائعات والتقارير المتضاربة حتى تتضح، ونميّز دائمًا بين الخبر '
              'المؤكد والمنسوب ("بحسب تقارير صحفية").</li>'
              '<li>لا نختلق تصريحات أو أرقامًا أو تفاصيل تعاقدية غير معلنة.</li></ul>')
    ed.append('<h2>كيف نُعِدّ الخبر؟</h2><ul>'
              '<li><b>مصادر الخبر:</b> نبدأ من المصدر الرسمي حين يتوفر (النادي، الاتحاد، اللاعب عبر '
              'حساباته الرسمية) ثم نقارنه بما نشرته وسائل إعلام رياضية موثوقة، ولا نكتب إلا ما اتفق عليه '
              'مصدران مستقلان على الأقل. نسمّي المصدر داخل الخبر، ونذكر المصادر التي اعتمدنا عليها في '
              'نهاية المقال في المقالات المنشورة منذ سبتمبر 2026.</li>'
              '<li><b>الكتابة:</b> نكتب المقال بصياغتنا الخاصة من الحقائق المؤكدة، ولا ننسخ نصوص المواقع '
              'الأخرى. نحرص على أن يضيف كل مقال ما يفيد القارئ فعلًا: خلفية القصة، الأرقام ذات الصلة '
              '(المباريات، الأهداف، الترتيب، التواريخ)، ماذا يعني الخبر للنادي أو اللاعب، وما الخطوة '
              'التالية المتوقعة، مع الربط بمقالاتنا السابقة عن الموضوع نفسه.</li>'
              '<li><b>البيانات:</b> النتائج والمواعيد وجداول الترتيب والهدافون تأتي من مزوّدي بيانات '
              'المباريات وتتحدّث تلقائيًا، ولا نعرض نتيجة مباشرة إلا بعد تأكدها من المصدر.</li>'
              f'<li><b>إعداد ومراجعة:</b> <a href="/editors.html">{esc(EDITOR_NAME)}</a>، '
              'ويظهر وقت النشر على كل مقال. عن دور أدوات الذكاء الاصطناعي في الصياغة، '
              'انظر القسم أدناه.</li>'
              '<li>قسم "عناوين الصحف" تجميعي بطبيعته: يعرض العنوان ويحيل مباشرةً إلى المصدر الأصلي.</li></ul>')
    ed.append('<h2>استخدام الذكاء الاصطناعي</h2>'
              '<p>نفصح عن ذلك صراحةً: <b>تُصاغ مقالات الموقع بمساعدة أدوات ذكاء اصطناعي</b>، '
              'انطلاقًا من حقائق تحقّقنا منها ومن أرقام مباريات حقيقية، وتحت إشراف ومراجعة '
              f'<a href="/editors.html">{esc(EDITOR_NAME)}</a> الذي يوقّع المقالات ويتحمّل '
              'المسؤولية الكاملة عن كل ما يُنشر. الأداة تساعد في الصياغة والترتيب، ولا تقرّر '
              'ما يُنشر ولا تُسنِد خبرًا إلى مصدر لم نراجعه.</p>'
              '<p>وللتفريق بين ثلاثة أشياء مختلفة على الموقع:</p><ul>'
              '<li><b>المقالات:</b> صياغة بمساعدة الذكاء الاصطناعي من حقائق مؤكدة، بمراجعة بشرية '
              'قبل النشر، ومع تسمية المصادر داخل المقال وفي نهايته.</li>'
              '<li><b>قراءات المباريات وتحليل الترتيب:</b> ليست مكتوبة بالذكاء الاصطناعي إطلاقًا — '
              'جُمَل تُبنى حسابيًا من الأرقام المعروضة على الصفحة نفسها (الترتيب، الشكل الأخير، '
              'أحداث المباراة، تقييمات اللاعبين)، فإن غابت البيانات لا تُكتب الجملة.</li>'
              '<li><b>النتائج والجداول والتوقعات:</b> بيانات تصل آليًا من مزوّدي بيانات المباريات، '
              'والتوقعات مخرجات نموذج إحصائي مفتوح الشرح في '
              '<a href="/analysis.html#model">صفحة التحليلات</a>، وسجلّه كاملًا بإصاباته وإخفاقاته '
              'في <a href="/predictions.html">سجل التوقعات</a>.</li></ul>'
              '<p>إن وجدت في أي مقال معلومة تبدو غير دقيقة، '
              f'<a href="/contact.html">أبلغنا</a> وسنراجعها ونصحّحها علنًا.</p>')
    ed.append('<h2>الصور</h2><ul>'
              '<li>نستخدم صورًا مرخّصة للاستخدام الحر فقط، وثيقة الصلة بموضوع الخبر، '
              'مع ذكر المصوِّر والرخصة أسفل كل صورة.</li></ul>')
    ed.append('<h2>التصحيح</h2>'
              '<p>إذا اكتشفنا خطأً في مقال منشور نصحّحه فور التثبت منه، ونرحّب بأي تصحيح عبر صفحة '
              '<a href="/contact.html">اتصل بنا</a>.</p>')
    ed.append('</div></article>')
    ed.append(foot())
    write("editorial.html", "".join(ed))
    urls.append("/editorial.html")

    # ---- news archive pages ----
    # /news.html = everything; /news/egypt.html + /news/europe.html = the
    # section archives each home block's «المزيد» opens (user 2026-09-01:
    # the blocks stay at 4 rows — the rest lives behind المزيد). Same calm
    # list rows everywhere - the old card grid read as scattered ("شتات").
    def news_archive(fname, h1, title, desc, arts):
        np_ = [head(f"{title} — {SITE_NAME}", desc,
                    SITE_BASE + "/" + fname, active="home")]
        np_.append(f'<h1 class="page-h">{esc(h1)}</h1>')
        if fname != "news.html":
            np_.append('<nav class="crumbs"><a href="/">أخبار</a> › '
                       f'<a href="/news.html">كل الأخبار</a> › {esc(h1)}</nav>')
        if arts:
            np_.append('<div class="alist">')
            for a in arts:
                img = thumb_url(a.get("image_url"))
                th = (f'<span class="al-th" style="background-image:url(\'{esc(img)}\')"></span>'
                      if img else '<span class="al-th noimg">⚽</span>')
                np_.append(
                    f'<a class="al-row" href="{article_href(a)}">{th}'
                    f'<span class="al-b"><b class="al-t">{esc(a.get("title"))}</b>'
                    f'<span class="al-s">{esc(strip_tags(a.get("summary") or ""))}</span>'
                    f'<span class="al-m">{esc(byline(a))} · '
                    f'{art_reltime(a) or esc(a.get("pub_date") or "")}</span>'
                    f'</span></a>')
            np_.append('</div>')
        else:
            np_.append('<p class="empty-note">لا توجد أخبار بعد.</p>')
        np_.append(foot())
        write(fname, "".join(np_))
        urls.append("/" + fname)

    news_archive("news.html", "كل الأخبار", "كل الأخبار",
                 "أرشيف أخبار كرة القدم على يلا سكور — كل المقالات والتقارير.",
                 articles)
    os.makedirs(os.path.join(DIST, "news"), exist_ok=True)
    news_archive("news/egypt.html", "أخبار الكرة المصرية",
                 "أخبار الكرة المصرية اليوم",
                 "كل أخبار الكرة المصرية على يلا سكور: الأهلي والزمالك "
                 "وبيراميدز والدوري المصري ومنتخب مصر — تتحدّث على مدار اليوم.",
                 [a for a in articles if _egy_article(a)])
    news_archive("news/europe.html", "أخبار الكرة الأوروبية",
                 "أخبار الكرة الأوروبية اليوم",
                 "كل أخبار الدوريات الأوروبية على يلا سكور: الدوري الإنجليزي "
                 "والإسباني ودوري الأبطال وكبار الأندية — تتحدّث على مدار اليوم.",
                 [a for a in articles if _eur_article(a)])

    # ---- fb.html — INTERNAL helper: ready-to-paste Facebook posts ----
    # Unlinked, out of the sitemap, noindexed. The user opens it directly
    # (bookmark) and copies each new article's post until FB auto-posting
    # (fb_post.py + FB_PAGE_TOKEN) goes live. Post text comes from the
    # article's fb_post field (written by the AI tasks); older articles get
    # a plain generated fallback.
    def _fb_text(a):
        t = (a.get("fb_post") or "").strip()
        if t:
            return t
        # teaser fallback (user rule 2026-08-31): no summary in the post —
        # the information lives on the site, the post only pulls the click
        return (f"⚽ {(a.get('title') or '').strip()}\n\n"
                f"التفاصيل الكاملة على الموقع 👇\n{article_url(a)}\n\n#يلا_سكور")
    fbp = [head(f"بوستات فيسبوك — {SITE_NAME}", "صفحة داخلية.",
                SITE_BASE + "/fb.html")]
    fbp.append('<h1 class="page-h">بوستات فيسبوك جاهزة 📋</h1>'
               '<p class="fbp-note">صفحة داخلية غير معلنة — اضغط «نسخ» والصق البوست على صفحة يلا سكور.</p>')
    for a in articles[:15]:
        _w = art_reltime(a)
        fbp.append('<div class="fbp">'
                   f'<div class="fbp-h"><b>مقال {a["article_id"]}</b> · {esc(a.get("pub_date") or "")}'
                   f'{" · " + _w if _w else ""}</div>'
                   f'<textarea class="fbp-t" readonly rows="8">{esc(_fb_text(a))}</textarea>'
                   '<button type="button" class="fbp-c">📋 نسخ</button></div>')
    fbp.append(FBCOPY_JS)
    fbp.append(foot())
    write("fb.html", "".join(fbp).replace(
        "<head>", '<head><meta name="robots" content="noindex">', 1))
    # deliberately NOT appended to urls (sitemap) and linked from nowhere

    # ---- headlines page (full aggregated list; gated by SHOW_HEADLINES) ----
    if SHOW_HEADLINES:
        hp = [head(f"عناوين الصحف — {SITE_NAME}",
                   "آخر عناوين كرة القدم من الصحف والمواقع الإخبارية — تتحدث تلقائيًا على مدار الساعة.",
                   SITE_BASE + "/headlines.html", active="home")]
        hp.append('<h1 class="page-h">عناوين الصحف</h1>')
        if headlines:
            # same calm list rows as /news.html (the card grid read as scattered)
            hp.append('<div class="alist">')
            for h in headlines:
                t = strip_src(h.get("title"), h.get("source"))
                iso = h.get("pub_iso") or ""
                when = rel_ar(iso) if iso else (h.get("pub_date") or "")
                timeel = (f'<time class="reltime" datetime="{esc(iso)}">{esc(when)}</time>'
                          if iso else esc(when))
                ph = PLACEHOLDER_IMGS[int(hashlib.md5((h.get("link") or t).encode("utf-8")).hexdigest(), 16) % len(PLACEHOLDER_IMGS)]
                img = h.get("image") or ph
                hp.append(
                    f'<a class="al-row" href="{esc(h.get("source_url") or h.get("link"))}" target="_blank" rel="noopener nofollow">'
                    f'<span class="al-th"><img src="{esc(img)}" alt="" loading="lazy" referrerpolicy="no-referrer"'
                    f' onerror="this.onerror=null;this.src=\'{ph}\'"></span>'
                    f'<span class="al-b"><b class="al-t">{esc(t)}</b>'
                    f'<span class="al-m"><span class="hsrc">{esc(h.get("source") or "")}</span> · {timeel}</span>'
                    f'</span></a>')
            hp.append('</div>')
        else:
            hp.append('<p class="empty-note">لا توجد عناوين حاليًا.</p>')
        hp.append(foot())
        write("headlines.html", "".join(hp))
        urls.append("/headlines.html")

    # ---- reels page (vertical shorts; data/reels.json + reels_auto.json) ----
    rp = [head(f"ريلز كرة القدم — {SITE_NAME}",
               "ريلز كرة القدم — مقاطع قصيرة: مهارات وأهداف ولقطات ممتعة بالفيديو.",
               SITE_BASE + "/reels.html", active="reels")]
    rp.append('<h1 class="page-h">⚡ ريلز</h1>')
    if reels:
        rp.append('<div class="rwrap"><div class="rfeed" id="rfeed">')
        for i, r in enumerate(reels):
            rp.append(reel_slide(r, first=(i == 0)))
        rp.append('</div>')
        rp.append('<div class="rarrows">'
                  '<button type="button" id="rUp" aria-label="الريل السابق">⬆</button>'
                  '<button type="button" id="rDn" aria-label="الريل التالي">⬇</button></div>')
        rp.append('</div>')
        rp.append(VIDEO_JS)
        rp.append(REELS_FEED_JS)
    else:
        rp.append('<p class="empty-note">الريلز قريبًا — تابعونا.</p>')
    rp.append(foot())
    if SHOW_REELS:
        write("reels.html", "".join(rp))
        urls.append("/reels.html")

    # ---- videos page: grouped by competition (empty sections auto-hide) ----
    # item.cat: "wc" | "epl" | "laliga" | absent -> "misc"
    vp = [head(f"فيديوهات كرة القدم — {SITE_NAME}",
               "فيديوهات كأس العالم 2026 والدوري الإنجليزي والدوري الإسباني على يلا سكور.",
               SITE_BASE + "/videos.html", active="videos")]
    vp.append('<h1 class="page-h">فيديوهات</h1>')
    if videos:
        by_cat = {}
        for v in videos:
            by_cat.setdefault((v.get("cat") or "misc"), []).append(v)
        for key, label in VIDEO_CATS:
            vs = by_cat.get(key)
            if not vs:
                continue
            vp.append(f'<h2 class="page-h vcat-h">{label}</h2><div class="vgrid">')
            for v in vs:
                vp.append(video_facade(v))
            vp.append('</div>')
        vp.append(VIDEO_JS)
    else:
        vp.append('<p class="empty-note">الفيديوهات قريبًا — تابعونا.</p>')
    vp.append(foot())
    if SHOW_VIDEOS:
        write("videos.html", "".join(vp))
        urls.append("/videos.html")

    # ---- robots + sitemap + ads.txt ----
    write("robots.txt", f"User-agent: *\nAllow: /\nSitemap: {SITE_BASE}/sitemap.xml\n"
                        f"Sitemap: {SITE_BASE}/sitemap-news.xml\n")
    # Google-News sitemap: only articles from the last 48h belong here (News
    # ignores older entries). An empty urlset is valid on quiet days.
    news_cut = (datetime.date.today() - datetime.timedelta(days=2)).isoformat()
    ns = ['<?xml version="1.0" encoding="UTF-8"?>',
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
          'xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">']
    for a in articles:
        if (a.get("pub_date") or "") >= news_cut:
            ns.append(f"  <url><loc>{esc(article_url(a))}</loc><news:news>"
                      f"<news:publication><news:name>{esc(SITE_NAME)}</news:name>"
                      "<news:language>ar</news:language></news:publication>"
                      f"<news:publication_date>{esc(a.get('pub_ts') or a['pub_date'])}</news:publication_date>"
                      f"<news:title>{esc(a['title'])}</news:title></news:news></url>")
    ns.append("</urlset>")
    write("sitemap-news.xml", "\n".join(ns))
    # RSS 2.0 feed: newest 30 articles (aggregators, Google News/Discover
    # discovery, and anyone following the site outside Facebook).
    rss = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom" '
           'xmlns:media="http://search.yahoo.com/mrss/">', '<channel>',
           f'<title>{esc(SITE_NAME)} — {esc(SITE_TAGLINE)}</title>',
           f'<link>{SITE_BASE}/</link>',
           f'<description>{esc(strip_tags(SITE_DESC))}</description>',
           '<language>ar</language>',
           f'<atom:link href="{SITE_BASE}/feed.xml" rel="self" type="application/rss+xml"/>',
           f'<image><url>{SITE_BASE}/assets/logo.png</url><title>{esc(SITE_NAME)}</title>'
           f'<link>{SITE_BASE}/</link></image>']
    _lb = _rfc822(articles[0]) if articles else ""
    if _lb:
        rss.append(f'<lastBuildDate>{_lb}</lastBuildDate>')
    for a in articles[:30]:
        _u = article_url(a)
        _d = _rfc822(a)
        _img = a.get("image_url") or ""
        rss.append('<item>'
                   f'<title>{esc(a["title"])}</title>'
                   f'<link>{esc(_u)}</link>'
                   f'<guid isPermaLink="true">{esc(_u)}</guid>'
                   + (f'<pubDate>{_d}</pubDate>' if _d else "")
                   + f'<description>{esc(strip_tags(a.get("summary")))}</description>'
                   + (f'<media:content url="{esc(_img)}" medium="image"/>' if _img else "")
                   + '</item>')
    rss.append('</channel></rss>')
    write("feed.xml", "\n".join(rss))
    if ADSENSE_CLIENT:   # AdSense seller declaration (clears the ads.txt warning)
        write("ads.txt", f"google.com, {ADSENSE_CLIENT.replace('ca-', '')}, DIRECT, f08c47fec0942fa0\n")
    # <lastmod> tells Google which of the ~600 URLs actually changed since its
    # last crawl (it ignores changefreq/priority but uses lastmod). Listing,
    # team, standings and scorers pages are rebuilt with fresh data every
    # run -> today; legal/static pages carry none.
    _dyn = ("/", "/matches.html", "/news.html", "/stats.html", "/analysis.html")
    sm = ['<?xml version="1.0" encoding="UTF-8"?>',
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u in urls:
        lm = _LASTMOD.get(u)
        if not lm and (u in _dyn or u.startswith(("/news/", "/team/", "/standings/", "/scorers/", "/analysis/"))):
            lm = REF_TODAY
        sm.append(f"  <url><loc>{esc(SITE_BASE + u)}</loc>"
                  + (f"<lastmod>{esc(lm)}</lastmod>" if lm else "") + "</url>")
    sm.append("</urlset>")
    write("sitemap.xml", "\n".join(sm))

    # ---- passthrough root files (Google Search Console verification, etc.) ----
    extras = os.path.join(HERE, "root-extras")
    if os.path.isdir(extras):
        for fn in os.listdir(extras):
            src = os.path.join(extras, fn)
            if os.path.isfile(src):
                shutil.copy(src, os.path.join(DIST, fn))
                print("  + root file:", fn)

    # ---- _redirects: the match pieces that moved into their match page ----
    # Cloudflare Workers static-asset routing reads this file. Both spellings
    # are listed because the extensionless form is the official URL (write()
    # normalizes every internal link) while published Facebook posts and old
    # Google results can still carry either.
    if _moved:
        lines = []
        for old_path, new_path in _moved:
            # the extensionless form is the canonical one; targeting the .html
            # name would make every redirect a 301 into a 307 (Workers assets
            # redirect /x.html -> /x), the chain that cost us indexing once
            new_path = new_path[:-5] if new_path.endswith(".html") else new_path
            lines.append(f"{old_path} {new_path} 301")
            lines.append(f"{old_path}.html {new_path} 301")
        write_text("_redirects", NEWLINE.join(lines) + NEWLINE)
        print(f"  + _redirects: {len(_moved)} match piece(s) 301 to their match page")

    # ---- mirrored crests (downloaded by local_crest during rendering) ----
    if _CREST_MAP:
        dest = os.path.join(DIST, "assets", "crests")
        os.makedirs(dest, exist_ok=True)
        n = 0
        for local in set(_CREST_MAP.values()):
            if not local.startswith("/assets/crests/"):
                continue                      # remote fallback, nothing to copy
            fn = local.rsplit("/", 1)[-1]
            src = os.path.join(CRESTS_CACHE, fn)
            if os.path.exists(src):
                shutil.copy(src, os.path.join(dest, fn))
                n += 1
        print(f"  + crests mirrored: {n}")

    # ---- uploaded media (article images added via the admin page) ----
    media = os.path.join(HERE, "media")
    if os.path.isdir(media):
        os.makedirs(os.path.join(DIST, "media"), exist_ok=True)
        n = 0
        for fn in os.listdir(media):
            src = os.path.join(media, fn)
            if os.path.isfile(src):
                shutil.copy(src, os.path.join(DIST, "media", fn))
                n += 1
        thumbs = os.path.join(media, "thumbs")
        if os.path.isdir(thumbs):                 # the 640px card copies
            os.makedirs(os.path.join(DIST, "media", "thumbs"), exist_ok=True)
            for fn in os.listdir(thumbs):
                src = os.path.join(thumbs, fn)
                if os.path.isfile(src):
                    shutil.copy(src, os.path.join(DIST, "media", "thumbs", fn))
                    n += 1
        if n:
            print(f"  + media files: {n}")

    write_text("build-info.json", json.dumps(build_info(articles, _preds),
                                             ensure_ascii=False))

    try:
        _rw, _st = store.writes()
        _rr, _ = store.reads()
        if _st:
            print(f"  · D1: {_rw} rows written, {_rr} rows read in {_st} statements "
                  f"this run (free tier per DAY, shared with every workflow and "
                  f"the Worker: 100,000 written / 5,000,000 read)")
    except Exception:                                        # noqa: BLE001
        pass
    print(f"Built {len(articles)} articles, {len(matches)} matches -> {DIST}")
    print(f"SITE_BASE = {SITE_BASE}  (edit build_site.py to change, then rebuild)")

def _scored(m):
    return m.get("home_score") is not None and m.get("away_score") is not None


def _finished_by_comp(fixtures, pool=None):
    """competition -> chronological FINISHED matches with scores.

    From the season pool when the build has one (fixtures ∪ matches_archive ∪
    results_archive, de-duplicated by analysis.season_matches - the
    very matches the Elo model replays), from the rounds data alone otherwise.

    2026-09-13: fixtures.json arrived with La Liga cut to rounds [4, 5] after a
    degraded feed answer (fetch_data.merge_fixture_rounds now stops that at the
    source) and the «آخر 5» column collapsed to one or two dots. The pool still
    held the season, so the standings columns read from it: a truncated
    fixtures file can no longer empty them."""
    out = {}
    for comp, ms in (pool or {}).items():
        out[comp] = [m for m in ms if m.get("status") == "FINISHED" and _scored(m)]
    for f in fixtures:
        comp = f.get("competition")
        if comp in out:
            continue
        ms = []
        for rd in f.get("rounds", []):
            ms.extend(rd.get("matches", []))
        out[comp] = [m for m in ms if m.get("status") == "FINISHED" and _scored(m)]
    for ms in out.values():
        ms.sort(key=lambda m: (m.get("kickoff") or "", m.get("koff_time") or ""))
    return out


def compute_elo(fixtures, pool=None):
    """competition -> {team: (rating, played)} from the finished matches
    (_finished_by_comp), chronological. Plain Elo: start 1500, K=28, home adv +70.
    Only a fallback for the league tiles when a league has no official table."""
    out = {}
    for comp, ms in _finished_by_comp(fixtures, pool).items():
        r, n = {}, {}
        for m in ms:
            h, a = m.get("home"), m.get("away")
            rh, ra = r.get(h, 1500.0), r.get(a, 1500.0)
            e = 1.0 / (1 + 10 ** ((ra - (rh + 70)) / 400))
            hs, aw = m["home_score"], m["away_score"]
            sc = 1.0 if hs > aw else 0.5 if hs == aw else 0.0
            r[h], r[a] = rh + 28 * (sc - e), ra + 28 * ((1 - sc) - (1 - e))
            n[h], n[a] = n.get(h, 0) + 1, n.get(a, 0) + 1
        out[comp] = {t: (r[t], n[t]) for t in r}
    return out

def team_form(fixtures, standings=None, pool=None):
    """competition -> team -> chronological 'W'/'D'/'L' list: finished matches
    from the season pool (see _finished_by_comp; the rounds data when there is
    no pool), LIVE matches with a score from the rounds data.

    Reconciled with the official table (2026-09-13, user: Barcelona «لعب 5»
    but four dots): within ONE fetch, football-data's standings already
    counted Levante x Barcelona while its fixtures still said LIVE 1-3 - the
    feed flips a match to FINISHED minutes after it updates the table. So when
    the table says a club has played MORE matches than we have finished for
    it, the club's LIVE match with a score (there is at most one) counts as
    decided too. When the fixture flips to FINISHED it is counted the normal
    way, never twice."""
    form = {}
    pending = {}                     # comp -> team -> results of LIVE matches with a score

    def _res(m):
        hs, aw = m["home_score"], m["away_score"]
        return ("W" if hs > aw else "D" if hs == aw else "L",
                "W" if aw > hs else "D" if hs == aw else "L")

    for comp, ms in _finished_by_comp(fixtures, pool).items():
        d = form.setdefault(comp, {})
        for m in ms:
            rh, ra = _res(m)
            d.setdefault(m.get("home"), []).append(rh)
            d.setdefault(m.get("away"), []).append(ra)
    for f in fixtures:
        comp = f.get("competition")
        ms = []
        for rd in f.get("rounds", []):
            ms.extend(rd.get("matches", []))
        ms = [m for m in ms if _scored(m) and m.get("status") == "LIVE"]
        ms.sort(key=lambda m: (m.get("kickoff") or "", m.get("koff_time") or ""))
        form.setdefault(comp, {})
        pd_ = pending.setdefault(comp, {})
        for m in ms:
            rh, ra = _res(m)
            pd_.setdefault(m.get("home"), []).append(rh)
            pd_.setdefault(m.get("away"), []).append(ra)
    for st in standings or []:
        comp = st.get("competition")
        if comp not in form:
            continue
        for row in st.get("table") or []:
            team, played = row.get("team"), row.get("played")
            if team is None or played is None:
                continue
            have = len(form[comp].get(team, []))
            extra = pending.get(comp, {}).get(team, [])
            if played > have and extra:
                form[comp].setdefault(team, []).extend(extra[-(played - have):])
    return form

def form_dots(results):
    """Last-5 form as colored dots (oldest -> newest)."""
    if not results:
        return '<span class="fm-none">—</span>'
    return "".join(f'<span class="fm fm-{r.lower()}" title="{ {"W":"فوز","D":"تعادل","L":"خسارة"}[r] }"></span>'
                   for r in results[-5:])

def standings_table(comp, rows, past=False, season_label="", zeroed=False, form_map=None,
                    embedded=False):
    """League standings table (FotMob-style). Hidden until its league is picked.
    `zeroed` = the new season hasn't kicked off yet, so this is the new season's
    team list with everything at 0; it gets a "new season" badge.
    `past` = legacy flag (last season's final table) kept for old data files."""
    def cell(v):
        return "0" if v is None else esc(str(v))
    body = []
    for r in rows:
        crest = (f'<img src="{esc(local_crest(r.get("crest")))}" alt="" loading="lazy">'
                 if r.get("crest") else "")
        fm = form_dots((form_map or {}).get(r.get("team"), [])) if form_map is not None else ""
        fmtd = f'<td class="lt-form">{fm}</td>' if form_map is not None else ""
        body.append(
            f'<tr><td class="lt-pos">{cell(r.get("pos"))}</td>'
            f'<td class="lt-team">{crest}<bdi>{esc(ar_team(r.get("team")))}</bdi></td>'
            f'{fmtd}'
            f'<td>{cell(r.get("played"))}</td><td>{cell(r.get("won"))}</td>'
            f'<td>{cell(r.get("draw"))}</td><td>{cell(r.get("lost"))}</td>'
            f'<td>{cell(r.get("gf"))}</td><td>{cell(r.get("ga"))}</td>'
            f'<td>{cell(r.get("gd"))}</td><td class="lt-pts">{cell(r.get("pts"))}</td></tr>')
    if zeroed:
        badge = (f'<span class="lt-past">الموسم الجديد'
                 f'{(" " + esc(season_label)) if season_label else ""} — لم ينطلق بعد</span>')
    elif past:
        badge = (f'<span class="lt-past">الموسم الماضي'
                 f'{(" " + esc(season_label)) if season_label else ""}</span>')
    else:
        badge = ""
    return (f'<div class="ltable" data-comp="{esc(comp)}"{"" if embedded else " hidden"}>'
            f'<div class="lt-head">{comp_icon(comp)} جدول ترتيب {esc(comp_label(comp))}{badge}</div>'
            f'<div class="lt-scroll"><table class="lt"><thead><tr>'
            f'<th class="lt-pos">#</th><th class="lt-team">الفريق</th>'
            + (f'<th class="lt-form" title="آخر 5 مباريات">آخر 5</th>' if form_map is not None else "") +
            f'<th title="لعب">لعب</th><th title="فاز">ف</th><th title="تعادل">ت</th>'
            f'<th title="خسر">خ</th><th title="له">له</th><th title="عليه">عليه</th>'
            f'<th title="الفارق">+/-</th><th class="lt-pts">نقاط</th></tr></thead>'
            f'<tbody>{"".join(body)}</tbody></table></div></div>')

# official competition emblems (same host as the team crests already used)
COMP_LOGO = {
    "Premier League":   "https://crests.football-data.org/PL.png",
    "Primera Division": "https://crests.football-data.org/PD.png",
    "Serie A":          "https://crests.football-data.org/SA.png",
    "Bundesliga":       "https://crests.football-data.org/BL1.png",
    "Ligue 1":          "https://crests.football-data.org/FL1.png",
    "UEFA Champions League": "https://crests.football-data.org/CL.png",
    # 365scores competition emblems (self-hosted through local_crest at build)
    "CAF Champions League": "https://imagecache.365scores.com/image/upload/"
                            "f_png,w_68,h_68,c_limit,q_auto:eco,dpr_2,"
                            "d_Competitions:default1.png/v4/Competitions/624",
    "Africa Cup of Nations Qualification":
        "https://imagecache.365scores.com/image/upload/"
        "f_png,w_68,h_68,c_limit,q_auto:eco,dpr_2,"
        "d_Competitions:default1.png/v4/Competitions/588",
    "UEFA Nations League":
        "https://imagecache.365scores.com/image/upload/"
        "f_png,w_68,h_68,c_limit,q_auto:eco,dpr_2,"
        "d_Competitions:default1.png/v4/Competitions/7016",
}
# friendlier display names (data-comp keeps the raw API name for filtering)
COMP_LABEL = {
    "Egyptian Premier League": "الدوري المصري",
    "CAF Champions League": "دوري أبطال أفريقيا",
    "Premier League": "الدوري الإنجليزي",
    "Primera Division": "الدوري الإسباني",
    "Turkish Super Lig": "الدوري التركي",
    "Saudi Pro League": "الدوري السعودي",
    "Ligue 1": "الدوري الفرنسي",
    "Bundesliga": "الدوري الألماني",
    "Serie A": "الدوري الإيطالي",
    "UEFA Champions League": "دوري أبطال أوروبا",
    "Africa Cup of Nations Qualification": "تصفيات كأس أمم إفريقيا",
    "UEFA Nations League": "دوري الأمم الأوروبية",
}
# fixed sidebar order (user's pick 2026-08-13); anything unlisted goes last
COMP_ORDER = ["Egyptian Premier League", "Premier League", "Primera Division",
              "Turkish Super Lig", "Saudi Pro League", "Ligue 1",
              "Bundesliga", "Serie A", "UEFA Champions League",
              "CAF Champions League",   # after UCL (user pick 2026-09-02)
              "Africa Cup of Nations Qualification",  # user ask 2026-09-20
              "UEFA Nations League"]                  # user ask 2026-09-21

def comp_label(name):
    return COMP_LABEL.get(name, name or "")

def comp_icon(name):
    url = COMP_LOGO.get(name)
    if url:
        return f'<img class="lg-logo" src="{esc(local_crest(url))}" alt="" loading="lazy">'
    return f'<span class="lg-ico">{comp_emoji(name)}</span>'

def comp_emoji(name):
    n = (name or "").lower()
    if "world cup" in n or "مونديال" in n or "كأس العالم" in n: return "🏆"
    if "egypt" in n or "المصري" in n: return "🇪🇬"   # before "premier" (Egyptian Premier League)
    if "turk" in n or "التركي" in n: return "🇹🇷"
    if "saudi" in n or "السعودي" in n: return "🇸🇦"
    if "premier" in n: return "🦁"
    if "primera" in n or "laliga" in n or "la liga" in n: return "🇪🇸"
    if "serie a" in n: return "🇮🇹"
    if "bundesliga" in n: return "🇩🇪"
    if "ligue 1" in n: return "🇫🇷"
    if "caf" in n or "أفريقيا" in n: return "🌍"   # before the generic "champions"
    if "champions" in n: return "⭐"
    return "⚽"

def fixture_mini(m):
    """Compact fixture row for the league side panel (FotMob-style)."""
    st = (m.get("status") or "").upper()
    def cr(u):
        return f'<img src="{esc(local_crest(u))}" alt="" loading="lazy">' if u else '<span class="fx-ph">⚽</span>'
    if st in ("FINISHED", "LIVE"):
        # the score is its own grid column here, so it needs the pill too -
        # a bare "2-1" between the two columns puts the home goals on the
        # away side (same bug as the record, 2026-09-16)
        mid = score_pill(m.get("home_score"), m.get("away_score"), "fx-sc sc-in")
    else:
        mid = f'<span class="fx-time">{esc(m.get("koff_time") or "")}</span>'
    return (f'<div class="fx">'
            f'<span class="fx-home"><bdi>{esc(ar_team(m.get("home")))}</bdi>{cr(m.get("home_badge"))}</span>'
            f'{mid}'
            f'<span class="fx-away">{cr(m.get("away_badge"))}<bdi>{esc(ar_team(m.get("away")))}</bdi></span></div>')

def league_rounds_panel(comp, fx, embedded=False, only_current=False, more_url=None):
    """FotMob-style rounds panel: a ‹ round › navigator + every round of the
    season, each round's matches grouped by day. JS shows one round at a time."""
    from collections import OrderedDict
    rounds = fx.get("rounds") or []
    current = fx.get("current") or (rounds[0]["round"] if rounds else 1)
    parts = [f'<div class="lg-fix rounds-panel" data-comp="{esc(comp)}" '
             f'data-current="{current}"{"" if embedded else " hidden"}>',
             f'<div class="fx-head">{comp_icon(comp)} {esc(comp_label(comp))}</div>',
             ('' if only_current else
              '<div class="rnav">'
              '<button type="button" class="rn-prev" aria-label="الجولة السابقة">‹</button>'
              '<span class="rn-label"></span>'
              '<button type="button" class="rn-next" aria-label="الجولة التالية">›</button></div>'),
             '<div class="rounds">']
    if only_current:
        # /matches ships ONE round, not the season: the hidden rest was 2,206
        # fixture rows and 4,955 crest tags on the site's second-busiest page
        rounds = [r for r in rounds if r.get("round") == current] or rounds[:1]
    for r in rounds:
        _hid = "" if only_current else " hidden"
        parts.append(f'<div class="round" data-round="{r["round"]}" '
                     f'data-label="الجولة {r["round"]}"{_hid}>')
        days = OrderedDict()
        for m in r.get("matches", []):
            days.setdefault(m.get("kickoff") or "", []).append(m)
        for d in sorted(days.keys()):
            parts.append(f'<div class="fx-day">{esc(fmt_day(d))}</div>')
            for m in days[d]:
                parts.append(fixture_mini(m))
        parts.append('</div>')
    parts.append('</div>')
    if more_url:
        parts.append(f'<p class="more-link"><a href="{esc(more_url)}">كل جولات '
                     f'{esc(comp_label(comp))} ←</a></p>')
    parts.append('</div>')
    return "".join(parts)

def _scorer_face(sc):
    """Player photo when the feed has one, else the club crest, else a ball."""
    u = sc.get("photo") or sc.get("crest") or ""
    if not u:
        return '<span class="ph">⚽</span>'
    cls = "sc-face" if sc.get("photo") else ""
    return f'<img class="{cls}" src="{esc(local_crest(u))}" alt="" loading="lazy">'

def chart_is_current(rows, season_goals, max_played):
    """The 365scores charts keep serving LAST season's list until a new season
    produces numbers. Such a list always overshoots the season it claims to
    describe: more goals than the whole competition scored, or more
    appearances than the busiest team has played."""
    if not rows:
        return False
    if sum(_pval(x) for x in rows) > (season_goals or 0):
        return False
    if max_played and max((x.get("played") or 0) for x in rows) > max_played:
        return False
    return True

def league_pcts(fin):
    """Share-of-matches figures for one competition (from finished matches)."""
    n = len(fin)
    if not n:
        return ""
    over = sum(1 for _, m in fin if m["home_score"] + m["away_score"] >= 3)
    draws = sum(1 for _, m in fin if m["home_score"] == m["away_score"])
    homes = sum(1 for _, m in fin if m["home_score"] > m["away_score"])
    clean = sum(1 for _, m in fin if min(m["home_score"], m["away_score"]) == 0)
    cells = [("3 أهداف أو أكثر", over), ("تعادلات", draws),
             ("فوز أصحاب الأرض", homes), ("شباك نظيفة", clean)]
    out = ['<div class="pct-grid">']
    for label, cnt in cells:
        pc = round(cnt * 100 / n)
        out.append(f'<div class="pct" title="{cnt} من {n} مباراة">'
                   f'<span class="pct-l">{label}</span><b>{pc}%</b>'
                   f'<span class="pct-bar"><i style="width:{pc}%"></i></span>'
                   f'<span class="pct-s">{cnt} من {n}</span></div>')
    out.append('</div>')
    return "".join(out)

def fav_club_names(standings, fixtures):
    """The curated clubs as the ARABIC names the live feed uses — TICKER_TEAMS
    holds football-data tokens for the European clubs, and /live.json speaks
    365scores Arabic, so resolve each token through the real data + ar_team()
    instead of hand-maintaining a second list."""
    names = []
    for token, only_comp in TICKER_TEAMS:
        hit = None
        for st in standings:
            comp = st.get("competition")
            if not _in_scope(only_comp, comp):
                continue
            for r in st.get("table") or []:
                if token in (r.get("team") or ""):
                    hit = r.get("team")
                    break
            if hit:
                break
        if not hit:                      # no table yet: try the fixtures feed
            for fx in fixtures:
                if not _in_scope(only_comp, fx.get("competition")):
                    continue
                for rd in fx.get("rounds", []):
                    for m in rd.get("matches", []):
                        for side in ("home", "away"):
                            if token in (m.get(side) or ""):
                                hit = m[side]
                                break
                        if hit: break
                    if hit: break
                if hit: break
        nm = ar_team(hit) if hit else token
        # league scope must survive into the browser: /live.json games carry
        # the 365scores competition id (g.c), and a scoped entry only matches
        # inside its own league — otherwise Saudi Al-Ahli ("الأهلي" too)
        # hijacks the favourite-club card meant for Al Ahly Egypt.
        # a tuple scope emits one entry per league id (الأهلي in 552 AND 624)
        scopes = only_comp if isinstance(only_comp, tuple) else (only_comp,)
        for sc in scopes:
            cid = S365_COMP_IDS.get(sc) if sc else None
            if not any(e["n"] == nm and e["c"] == cid for e in names):
                names.append({"n": nm, "c": cid})
    return names

# 365scores competition ids for the leagues TICKER_TEAMS scopes by name —
# must agree with LIVE_COMPS in worker.js
# (552,78,649,7,11,17,25,35,572,624,588,7016).
S365_COMP_IDS = {
    "Egyptian Premier League": 552,
    "Turkish Super Lig": 78,
    "Saudi Pro League": 649,
    "CAF Champions League": 624,
    "Africa Cup of Nations Qualification": 588,
    "UEFA Nations League": 7016,
}

def clubs_panel(st_by_comp, sc_ok, sc_by_comp, forms, matches, fixtures):
    """The curated clubs (TICKER_TEAMS) at a glance: position, points, last 5,
    and the club's own top scorer — or its next match while the season hasn't
    given it any of those yet. Skips a club we can't find in any table.
    The next-match pool is matches ∪ the fixtures rounds: matches.json is
    capped at 90 rows, and a club whose opener falls past the cap (Chelsea's
    24/08 game did) would otherwise show no fixture at all."""
    pool = list(matches)
    for fx in fixtures:
        for rd in fx.get("rounds", []):
            pool.extend(rd.get("matches", []))
    upcoming = sorted((m for m in pool
                       if (m.get("status") or "").upper() == "UPCOMING"),
                      key=lambda m: (m.get("kickoff") or "", m.get("koff_time") or ""))
    cards = []
    for token, only_comp in TICKER_TEAMS:
        found = None
        for comp, st in st_by_comp.items():
            if only_comp and comp != only_comp:
                continue
            for r in st["table"]:
                if token in (r.get("team") or ""):
                    found = (comp, r)
                    break
            if found:
                break
        if not found:
            continue
        comp, row = found
        name = ar_team(row.get("team"))
        max_played = max((x.get("played") or 0) for x in st_by_comp[comp]["table"])
        crest = (f'<img src="{esc(local_crest(row.get("crest")))}" alt="" loading="lazy">'
                 if row.get("crest") else '<span class="ph">⚽</span>')
        res = (forms.get(comp) or {}).get(row.get("team")) or []
        if row.get("played"):
            rank = (f'<span class="cl-pos">#{esc(str(row.get("pos")))}</span>'
                    f'<span class="cl-pts">{row.get("pts")} نقطة</span>')
        elif max_played:
            rank = '<span class="cl-soon">لم يلعب بعد</span>'
        else:
            rank = '<span class="cl-soon">الموسم لم ينطلق</span>'
        form = f'<span class="cl-form">{form_dots(res)}</span>' if res else ""
        top = ""
        if sc_ok.get(comp):
            best = next((x for x in sc_by_comp.get(comp, []) if x.get("team") == name), None)
            if best:
                top = (f'<span class="cl-sc">هدافه: <b>{esc(best.get("name"))}</b>'
                       f' · {_pval(best)}</span>')
        if not top and not row.get("played"):
            # nothing played yet -> the next fixture is the useful line
            nxt = next((m for m in upcoming
                        if (not only_comp or (m.get("competition") or "") == only_comp)
                        and (token in (m.get("home") or "")
                             or token in (m.get("away") or ""))), None)
            if nxt:
                rival = (nxt.get("away") if token in (nxt.get("home") or "")
                         else nxt.get("home"))
                when = _tk_date(nxt.get("kickoff"))
                top = (f'<span class="cl-sc">القادمة: <b><bdi>{esc(ar_team(rival))}</bdi></b>'
                       f' · {esc(when)}'
                       + (f' {esc(nxt.get("koff_time"))}' if nxt.get("koff_time") else "")
                       + '</span>')
        cards.append(f'<a class="cl-card" href="/matches.html">'
                     f'<span class="cl-top">{crest}<span class="cl-n"><bdi>{esc(name)}</bdi></span></span>'
                     f'<span class="cl-lg">{esc(comp_label(comp))}</span>'
                     f'<span class="cl-row">{rank}{form}</span>{top}</a>')
    if not cards:
        return ""
    return ('<section class="stats-sec"><h2 class="lt-head">⭐ أبرز الأندية</h2>'
            f'<div class="cl-grid">{"".join(cards)}</div></section>')

def score_pill(hs, aws, cls):
    """A score sitting BETWEEN two team names must put the home number on the
    home side. "1-0" as plain text is one LTR bidi run, so in an RTL row it
    lands home-score-left = next to the AWAY team (reversed). Ordering two
    separate elements inside an RTL flex container fixes it and stays correct
    for two-digit scores, which a bidi-override would scramble.
    (The .score in match rows is fine as-is: its spaces around the hyphen
    already split it into separate runs — measured, don't "tidy" them away.)"""
    h = "-" if hs is None else hs
    a = "-" if aws is None else aws
    return (f'<b class="{cls}"><span>{h}</span><i>-</i><span>{a}</span></b>')


def score_txt(s, cls="sc-in"):
    """Same, for a score already stored as the string "H-A" (a frozen
    prediction, a saved result). A bare "1-2" in a cell of its own is an
    LTR run with no Arabic letter in front of it to turn the digits into
    Arabic numerals, so an RTL reader meets the AWAY number first and reads
    the prediction backwards (user, 2026-09-16)."""
    s = "" if s is None else str(s).strip()
    if "-" not in s:
        return esc(s or "—")
    h, a = s.split("-", 1)
    return score_pill(esc(h.strip()), esc(a.strip()), cls)

def _pval(x):
    """Chart value — "value" is the current key, "goals" the original one."""
    v = x.get("value")
    return (x.get("goals") or 0) if v is None else v

def scorers_list(sc, unit="أهداف"):
    """Chart table: rank, player (+club), value — plus a matches column only
    when the feed actually carries appearances (365scores does not)."""
    has_m = any((x.get("played") or 0) for x in sc)
    m_hd = "<span>مباريات</span>" if has_m else ""
    rows = [f'<div class="sc-list{"" if has_m else " sc-nom"}">'
            f'<div class="sc-hd"><span></span><span>اللاعب</span>'
            f'{m_hd}<span>{esc(unit)}</span></div>']
    for i, x in enumerate(sc, 1):
        club = (f'<span class="sc-club"><bdi>{esc(x.get("team"))}</bdi></span>'
                if x.get("team") else "")
        m_cell = f'<span class="sc-m">{x.get("played")}</span>' if has_m else ""
        rows.append(f'<div class="sc-row"><span class="sc-n">{i}</span>'
                    f'<span class="sc-p">{_scorer_face(x)}'
                    f'<span class="sc-nm"><bdi>{esc(x.get("name"))}</bdi>{club}</span></span>'
                    f'{m_cell}<b class="sc-g">{_pval(x)}</b></div>')
    rows.append('</div>')
    return "".join(rows)

def _gnorm(s):
    """Same normalization LIVE_JS uses to pair rows with 365scores names."""
    s = (s or "")
    for a, b in (("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ة", "ه"), ("ى", "ي")):
        s = s.replace(a, b)
    return "".join(ch for ch in s if ch not in ".'’  	")

def goal_events_index(goal_events):
    """(normalized home|away, date) -> goals. Names in the feed are 365scores
    Arabic — the same spellings AR_TEAM maps the football-data names to."""
    idx = {}
    for e in goal_events:
        if e.get("goals"):
            idx[(f'{_gnorm(e.get("home"))}|{_gnorm(e.get("away"))}', e.get("date"))] = e["goals"]
    return idx

def goals_index(goal_events=None, details=None, frozen=None):
    """THE scorers index - every consumer must use this one (2026-09-24).

    Three sources, later ones winning: match_details.json (ACCUMULATING - every
    finished match we ever fetched), goal_events.json (a ROLLING window, the
    freshest word on the last few hours) and the frozen archive (complete by
    construction). The page switched to this merge on 2026-09-13 after the
    rolling file alone made scorers vanish hours after the whistle; fb_reel,
    fb_cards and match_brief kept reading goal_events.json alone, so the reel
    found ZERO candidates (every curated match with goals looked scorer-less
    once it left the window) - caught by test_fb_reel 8 when the tests moved
    into CI. Arguments default to loading the files."""
    if details is None:
        details = load("match_details.json")
    if goal_events is None:
        goal_events = load("goal_events.json")
    if frozen is None:
        frozen = RA.frozen_entries(RA.load())
    idx = goal_events_index(details)
    idx.update(goal_events_index(goal_events))
    idx.update(goal_events_index(frozen))      # frozen wins
    return idx

def match_goals(idx, m):
    """Scorer lines for a match row — FINISHED only.

    A live match used to get them too, and that quietly broke the rule the
    dashes exist for. The user saw «مالقا - - - فياريال» with one goal listed
    at 12': the score was hidden as possibly-stale while the goal list, which
    is exactly as stale, implied 1-0. It was 1-1 — the second goal had arrived
    after the last build. Publishing half the picture is worse than publishing
    none of it, so a live match now shows nothing until LIVE_JS paints the
    score AND the goals together from /live.json, which carries both.
    """
    if (m.get("status") or "").upper() != "FINISHED":
        return None
    h, a = _gnorm(ar_team(m.get("home"))), _gnorm(ar_team(m.get("away")))
    g = idx.get((f"{h}|{a}", m.get("kickoff")))
    if g is None:
        # the two sources can disagree on who is at home (2026-08-23:
        # football-data said PSG x Rennes, 365scores said Rennes x PSG and
        # the scorers silently vanished) — try the reversed pair and flip
        # each goal's side so scorers stay under the right club
        rg = idx.get((f"{a}|{h}", m.get("kickoff")))
        if rg is not None:
            g = [{**x, "side": "a" if x.get("side") == "h" else "h"}
                 for x in rg]
    return g

def _epoch_ms(iso):
    """ISO timestamp (any offset, or a bare date) -> epoch ms, None if unreadable."""
    if not iso:
        return None
    try:
        d = datetime.datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return None
    if d.tzinfo is None:                     # a bare pub_date: noon Cairo, as the RSS does
        d = d.replace(hour=12, tzinfo=datetime.timezone(datetime.timedelta(hours=3)))
    return int(d.timestamp() * 1000)


def build_info(articles, preds):
    """build-info.json - what THIS deploy contains, read by the Worker's /health
    and its 15-minute watchdog (2026-09-24).

    It answers from the DEPLOYED copy on purpose: a green publish run can skip
    its deploy (main moved) and a fetch step can fail under continue-on-error,
    and in both cases every signal inside GitHub still said «success». The file
    the reader is actually being served cannot lie about its own age.
    Epoch ms everywhere, so the Worker never parses a time zone."""
    try:
        with io.open(os.path.join(DATA, "fetch_debug.json"), encoding="utf-8") as f:
            fd = json.load(f)
    except (OSError, ValueError):
        fd = {}
    # fetch_data.py writes "FAIL: <repr>" for a source that raised, and keeps
    # the previous file for it - the site still builds, just not newer data
    bad = sorted(k for k, v in fd.items() if isinstance(v, str) and v.startswith("FAIL"))
    newest = max((t for t in (_epoch_ms(a.get("pub_ts") or a.get("pub_date"))
                              for a in articles) if t), default=None)
    return {
        "built_at": int(datetime.datetime.now(datetime.timezone.utc).timestamp() * 1000),
        "fetch_at": _epoch_ms(fd.get("utc")),
        "fetch_failed": bad,
        "articles": len(articles),
        "newest_article_at": newest,
        "predictions": len(preds),
    }


def frozen_scores_index(entries):
    """(normalized home|away, date) -> (home_score, away_score), from the frozen
    archive. Keyed by NAMES and date like the scorer index above, not by
    match_id: the site's matches come from football-data for the European
    leagues and its ids are not 365scores ids, which is the same reason
    goal_events_index exists in this shape."""
    idx = {}
    for e in entries:
        if e.get("hs") is not None and e.get("as") is not None:
            idx[(f'{_gnorm(e.get("home"))}|{_gnorm(e.get("away"))}',
                 e.get("date"))] = (e["hs"], e["as"])
    return idx


def apply_frozen_scores(matches, idx):
    """Overlay the frozen score onto every FINISHED match the archive owns.

    The archive wins here, which is the point of freezing. It should never actually differ - both numbers
    come from the same feed and a finished match does not get corrected - so
    any disagreement is worth seeing rather than hiding, and the count is
    printed in the build log. Matches the archive does not hold keep the site's
    own number, so nothing can go blank.

    Returns (filled, changed): rows taken from the archive, and how many of
    those carried a different score than the site had."""
    filled = changed = 0
    for m in matches:
        if (m.get("status") or "").upper() != "FINISHED":
            continue
        h, a = _gnorm(ar_team(m.get("home"))), _gnorm(ar_team(m.get("away")))
        hit, flip = idx.get((f"{h}|{a}", m.get("kickoff"))), False
        if hit is None:
            # same reversed-pair fallback the scorers use: the two sources can
            # disagree on who was at home
            hit, flip = idx.get((f"{a}|{h}", m.get("kickoff"))), True
        if hit is None:
            continue
        hs, asc = (hit[1], hit[0]) if flip else hit
        if m.get("home_score") != hs or m.get("away_score") != asc:
            changed += 1
        m["home_score"], m["away_score"] = hs, asc
        filled += 1
    return filled, changed


def match_details_index(entries):
    """Same keying as goal_events_index, but keeps the whole entry
    (goals + cards + subs + lineups) for the /m/ match pages."""
    idx = {}
    for e in entries:
        idx[(f'{_gnorm(e.get("home"))}|{_gnorm(e.get("away"))}',
             e.get("date"))] = e
    return idx

def prematch_for(idx, m):
    """(entry, flipped) for an UPCOMING match whose XI is already announced
    (fetch_data stores those with pre=True from ~1h before kick-off), else
    None. Same reversed-pair fallback as match_details_for."""
    if (m.get("status") or "").upper() != "UPCOMING":
        return None
    h, a = _gnorm(ar_team(m.get("home"))), _gnorm(ar_team(m.get("away")))
    for key, flip in ((f"{h}|{a}", False), (f"{a}|{h}", True)):
        e = idx.get((key, m.get("kickoff")))
        if e is not None and ((e.get("lineups") or {}).get("h", {}).get("xi")
                              or (e.get("lineups") or {}).get("a", {}).get("xi")):
            return e, flip
    return None

def absence_block(squad, comp, m, h_ar, a_ar):
    """«الغائبون عن التشكيل المعتاد» — presented as FACTS, not as a probability
    adjustment. The prediction model deliberately ignores this for now: on the
    25 matches it moves, the absence factor improved brier by 0.013 while the
    noise band at that sample is ±0.18 (backtest.py, 2026-09-06), so moving the
    numbers would be dressing up noise. Naming who is missing needs no such
    proof — it is simply what the announced XI says."""
    if squad is None or not comp:
        return ""
    out = []
    for club_raw, label in ((m.get("home"), h_ar), (m.get("away"), a_ar)):
        club = ar_team(club_raw)
        r = squad.report(comp, club, m.get("kickoff"))
        if not r or not (r["missing"] or r["back"]):
            continue
        bits = []
        if r["missing"]:
            bits.append('<p><b>غائبون عن التشكيل المعتاد:</b> ' + '، '.join(
                f'<bdi>{esc(x["name"])}</bdi>'
                + (f' <small>(أساسي في {x["starts"]} من {_games(x["of"])}'
                   + (f'، متوسط تقييمه {x["avg"]:.1f}' if x.get("avg") else '') + ')</small>')
                for x in r["missing"][:5]) + '</p>')
        if r["back"]:
            bits.append('<p><b>عائدون للتشكيل:</b> ' + '، '.join(
                f'<bdi>{esc(x["name"])}</bdi>' for x in r["back"][:5]) + '</p>')
        out.append(f'<div class="abs-club"><h3>{esc(label)}</h3>' + "".join(bits) + '</div>')
    if not out:
        return ""
    _up = (m.get("status") or "").upper() == "UPCOMING"
    _h2 = "التشكيل المعلن — من غاب ومن عاد" if _up else "من غاب عن التشكيل المعتاد"
    return (f'<section class="minfo absences"><h2>{_h2}</h2>'
            + "".join(out)
            + '<p class="pd-note">«التشكيل المعتاد» يُحسب من التشكيلات السابقة لكل فريق هذا '
              'الموسم: من بدأ 60% منها فأكثر. الغياب هنا واقعة من التشكيل المعلن، وقد يكون '
              'سببه إصابة أو إيقافًا أو قرارًا فنيًا — لا نخمّن السبب، ولا تدخل هذه المعلومة '
              'في حساب <a href="/analysis.html#model">التوقع</a> حتى تثبت فائدتها بالأرقام.</p>'
            '</section>')

def match_details_for(idx, m):
    """(entry, flipped) for a FINISHED/LIVE match, else None — with the
    same reversed-pair fallback as match_goals (sources can disagree on
    who is at home)."""
    if (m.get("status") or "").upper() not in ("FINISHED", "LIVE"):
        return None
    h, a = _gnorm(ar_team(m.get("home"))), _gnorm(ar_team(m.get("away")))
    e = idx.get((f"{h}|{a}", m.get("kickoff")))
    if e is not None:
        return e, False
    e = idx.get((f"{a}|{h}", m.get("kickoff")))
    if e is not None:
        return e, True
    return None

def _min_key(mn):
    """'45+2' -> 45.02 for chronological event sorting."""
    try:
        base, _, add = (mn or "").partition("+")
        return int(base) + int(add or 0) / 100.0
    except ValueError:
        return 0.0

def _pshort(name):
    """Pitch-chip name: surname only when the full name is long."""
    w = (name or "").split()
    return name if len(name or "") <= 9 or len(w) == 1 else w[-1]

def _athlete_img(p):
    """365scores athlete headshot URL (mirrored locally via local_crest)."""
    aid = p.get("aid")
    if not aid:
        return None
    try:
        v = f"v{int(p['iv'])}/" if p.get("iv") else ""
    except (TypeError, ValueError):
        v = ""
    return ("https://imagecache.365scores.com/image/upload/"
            "f_png,w_68,h_68,c_limit,q_auto:eco,dpr_2,d_Athletes:default.png/"
            f"{v}Athletes/{aid}")

def _pitch_rows(lu, top):
    """[(x%, y%, player)] for one team's XI, or None when the feed has no
    formation lines. Home (top=True) attacks downward: GK on line 1 sits
    nearest its own goal (top edge); away is mirrored from the bottom."""
    xi = (lu or {}).get("xi") or []
    if sum(1 for p in xi if p.get("ln")) < 8:
        return None
    lines = {}
    for p in xi:
        lines.setdefault(p.get("ln") or 99, []).append(p)
    rows = [lines[k] for k in sorted(lines)]
    n = len(rows)
    out = []
    for i, row in enumerate(rows):
        frac = i / (n - 1) if n > 1 else 0.0
        y = 6 + 38 * frac if top else 94 - 38 * frac
        row.sort(key=lambda p: (p.get("sd") if p.get("sd") is not None else 50))
        if not top:
            row.reverse()               # mirror left/right for the away half
        for j, p in enumerate(row):
            out.append(((j + 0.5) / len(row) * 100, y, p))
    return out

def _rt_class(rt):
    try:
        r = float(rt)
    except (TypeError, ValueError):
        return None
    return "r8" if r >= 8 else "r7" if r >= 7 else "r65" if r >= 6.5 else "r6"

# ===========================================================================
# «قراءة المباراة» — layer 2 of the match-page rework (2026-09-14).
#
# The page had every number and said nothing. These functions read the data
# that is already on it: the events timeline becomes a story, the rating
# badges already printed on the pitch chips become "who decided this match",
# and the official table becomes "what the result changed".
#
# Same discipline as standings_analysis(): every clause is a restatement of
# data we publish, plus arithmetic on minutes, the running score and the
# table. Nothing is inferred, nothing is generated - so this can run on all
# 483 match pages without becoming scaled auto-written content, and a page
# whose data is incomplete simply says less.
# ===========================================================================
_ORD_AR = {1: "الأول", 2: "الثاني", 3: "الثالث", 4: "الرابع", 5: "الخامس",
           6: "السادس", 7: "السابع", 8: "الثامن", 9: "التاسع", 10: "العاشر",
           11: "الحادي عشر", 12: "الثاني عشر", 13: "الثالث عشر", 14: "الرابع عشر",
           15: "الخامس عشر", 16: "السادس عشر", 17: "السابع عشر", 18: "الثامن عشر",
           19: "التاسع عشر", 20: "العشرين"}
# «الخسارة» is feminine in Arabic: الخسارة الثانية, not الخسارة الثاني
_ORD_AR_F = {n: (w + "ة") for n, w in _ORD_AR.items() if n <= 10}

def _ord_ar(n, fem=False):
    """Arabic ordinal, or the bare number for a place past the twentieth (the
    36-club Champions League league phase) - never «المركز رقم 24»."""
    n = int(n or 0)
    return (_ORD_AR_F if fem else _ORD_AR).get(n, str(n))

def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f > 0 else None

def _lam(name):
    """Arabic lam of possession before a club name: «الأهلي» -> «للأهلي»,
    «نيوم» -> «لنيوم». Writing «لـالأهلي» is what a template does, not a writer."""
    name = name or ""
    return ("ل" + name[1:]) if name.startswith("ال") else ("ل" + name)


def _played_names(e, flipped, side_key):
    """Names that were ON THE PITCH for one side: the XI plus everyone involved
    in a substitution. Used to tell a sent-off player from a sent-off manager."""
    sd = _side_of(flipped)
    lus = e.get("lineups") or {}
    feed_key = ("a" if side_key == "h" else "h") if flipped else side_key
    names = {(p.get("name") or "").strip()
             for p in ((lus.get(feed_key) or {}).get("xi") or []) if p.get("name")}
    for sub in (e.get("subs") or []):
        if sd(sub.get("side")) == side_key:
            names.update(x.strip() for x in (sub.get("in"), sub.get("out")) if x)
    return names


def _side_of(flipped):
    """The details entry stores sides as the FEED saw them; `flipped` means the
    feed's home is our away (the two sources disagree on who is at home)."""
    return (lambda s: ("a" if s == "h" else "h")) if flipped else (lambda s: s)


def match_story(e, flipped, h_ar, a_ar, hs, as_):
    """The sentences a reader wants under the score: who opened, who turned it
    around, which goal settled it, what the sending-off did. Returns a list of
    plain-text sentences (the caller escapes them)."""
    sd = _side_of(flipped)
    nm = {"h": h_ar, "a": a_ar}
    goals = [{"k": _min_key(g.get("minute")), "s": sd(g.get("side")),
              "m": (g.get("minute") or "").strip(), "p": (g.get("player") or "").strip(),
              "t": g.get("tag") or ""}
             for g in (e.get("goals") or [])]
    timed = sorted([g for g in goals if g["k"] > 0 and g["s"] in ("h", "a")],
                   key=lambda g: g["k"])
    reds = sorted([{"k": _min_key(c.get("minute")), "s": sd(c.get("side")),
                    "m": (c.get("minute") or "").strip(),
                    "p": (c.get("player") or "").strip()}
                   for c in (e.get("cards") or []) if c.get("color") == "r"],
                  key=lambda c: c["k"])
    winner = "h" if (hs or 0) > (as_ or 0) else "a" if (as_ or 0) > (hs or 0) else None
    other = {"h": "a", "a": "h"}
    out = []

    if not (hs or 0) and not (as_ or 0):
        out.append(f"انتهت المباراة بالتعادل السلبي دون أهداف بين {h_ar} و{a_ar}.")
    elif timed:
        g0 = timed[0]
        if "عكس" in g0["t"]:
            out.append(f"تقدّم {nm[g0['s']]} بهدف عكسي سجله {g0['p']} في الدقيقة {g0['m']}.")
        else:
            pen = " من ركلة جزاء" if "ج" in g0["t"] else ""
            out.append(f"افتتح {g0['p']} التسجيل {_lam(nm[g0['s']])}{pen} في الدقيقة {g0['m']}.")

    # the running score: who led, who came back, which goal settled it
    run = {"h": 0, "a": 0}
    hist = []
    for g in timed:
        run[g["s"]] += 1
        lead = "h" if run["h"] > run["a"] else "a" if run["a"] > run["h"] else None
        hist.append((g, lead))
    first_lead = next((l for _, l in hist if l), None)
    if winner and first_lead and first_lead != winner:
        out.append(f"قلب {nm[winner]} تأخره أمام {nm[other[winner]]} وحسم اللقاء "
                   f"{max(hs, as_)}-{min(hs, as_)}.")
    elif not winner and first_lead and timed:
        out.append(f"أدرك {nm[other[first_lead]]} التعادل بعد تأخره أمام {nm[first_lead]}.")

    if winner and len(timed) > 1:
        dec, prev = None, None
        for g, lead in hist:
            if lead == winner and prev != winner:
                dec = g
            prev = lead
        if dec is timed[0]:
            dec = None          # already told: the opener was never caught
        if dec:
            if dec["k"] >= 80:
                out.append(f"وجاء هدف الحسم متأخرًا عبر {dec['p']} في الدقيقة {dec['m']}.")
            else:
                out.append(f"وجاء هدف الحسم عبر {dec['p']} في الدقيقة {dec['m']}.")

    # a player with more than one goal
    tally = {}
    for g in goals:
        if g["p"] and "عكس" not in g["t"] and g["s"] in ("h", "a"):
            tally[(g["p"], g["s"])] = tally.get((g["p"], g["s"]), 0) + 1
    for (pl, sside), n in sorted(tally.items(), key=lambda kv: -kv[1]):
        if n >= 3:
            out.append(f"سجّل {pl} ثلاثية كاملة مع {nm[sside]}.")
            break
        if n == 2:
            out.append(f"سجّل {pl} هدفين {_lam(nm[sside])}.")
            break

    if reds:
        r = reds[0]
        if r["s"] in ("h", "a"):
            # a red card is shown to managers and bench staff too (Neom x
            # Al-Fateh 2026: Christophe Galtier). Their name is not in the XI
            # or the substitutions, and their dismissal does NOT leave the team
            # a man short - so the ten-men sentence needs proof, not a guess.
            played = _played_names(e, flipped, r["s"])
            n_off = sum(1 for x in reds
                        if x["s"] == r["s"] and x["p"] in played)
            if r["p"] in played:
                short = {1: "بعشرة لاعبين", 2: "بتسعة لاعبين"}.get(n_off, "منقوص العدد")
                line = (f"أكمل {nm[r['s']]} المباراة {short} بعد طرد {r['p']} "
                        f"في الدقيقة {r['m']}")
                if winner == r["s"]:
                    line += "، وخرج فائزًا رغم النقص العددي."
                elif winner is None:
                    line += "، ونجح في الخروج بالتعادل رغم النقص العددي."
                else:
                    line += "."
            else:
                line = f"وتلقى {r['p']} بطاقة حمراء في الدقيقة {r['m']}."
            out.append(line)

    if winner and not (as_ if winner == "h" else hs):
        out.append(f"وحافظ {nm[winner]} على نظافة شباكه.")

    if len(timed) >= 3:
        if all(g["k"] >= 60 for g in timed):
            out.append("كل أهداف اللقاء جاءت في الثلث الأخير من زمن المباراة.")
        elif all(g["k"] <= 45 for g in timed):
            out.append("كل أهداف اللقاء جاءت في الشوط الأول.")
    return out[:6]


def match_ratings(e, flipped, h_ar, a_ar):
    """{best, best_other, low, sides} from the XI ratings the feed already
    gives us, or None when either XI is not fully rated (an incomplete set
    would name a 'best player' out of half a team)."""
    lus = e.get("lineups") or {}
    eh, ea = ("a", "h") if flipped else ("h", "a")
    sides = []
    for key, name in ((eh, h_ar), (ea, a_ar)):
        xi = ((lus.get(key) or {}).get("xi")) or []
        rated = [{"name": (p.get("name") or "").strip(), "rt": _num(p.get("rt")),
                  "club": name}
                 for p in xi if _num(p.get("rt")) and p.get("name")]
        if len(rated) < 8:
            return None
        sides.append({"club": name, "players": rated,
                      "avg": round(sum(p["rt"] for p in rated) / len(rated), 1)})
    everyone = sides[0]["players"] + sides[1]["players"]
    best = max(everyone, key=lambda p: p["rt"])
    other = [p for p in everyone if p["club"] != best["club"]]
    return {"best": best,
            "best_other": max(other, key=lambda p: p["rt"]) if other else None,
            "low": min(everyone, key=lambda p: p["rt"]),
            "sides": sides}


def _streak_ar(res):
    """Trailing run in a chronological W/D/L list, as Arabic - or ''."""
    if not res:
        return ""
    last, n = res[-1], 0
    for r in reversed(res):
        if r != last:
            break
        n += 1
    if n > 10:            # past the ordinals: plain and plural
        return f"{n} " + {"W": "انتصارات", "D": "تعادلات", "L": "خسائر"}[last] + " متتالية"
    if n >= 2:
        word = {"W": "الفوز", "D": "التعادل", "L": "الخسارة"}[last]
        return f"{word} {_ord_ar(n, fem=last == 'L')} على التوالي"
    unb = 0
    for r in reversed(res):
        if r == "L":
            break
        unb += 1
    return f"{unb} مباريات دون خسارة" if unb >= 4 else ""


def table_after(m, st, form_map, fin_comp, h_ar, a_ar):
    """«ماذا تغيّر في الجدول»: the club's place and points AFTER this match,
    read straight off the official table - never re-sorted by us (tie-break
    rules differ per league and a home-made order could be wrong).

    Only when the table describes THIS moment: the match must be the last
    finished match of both clubs in the competition, and the official `played`
    for each club must equal the finished matches we hold. Otherwise the
    numbers belong to a later round and the sentence would be false."""
    rows = (st or {}).get("table") or []
    if not rows or (st or {}).get("zeroed") or (st or {}).get("past"):
        return []
    fin = fin_comp or []
    pairs = []
    for raw, ar in ((m.get("home"), h_ar), (m.get("away"), a_ar)):
        played_by_club = [x for x in fin
                          if raw in (x.get("home"), x.get("away"))]
        if not played_by_club:
            return []
        last = played_by_club[-1]
        if (last.get("kickoff"), last.get("home"), last.get("away")) != \
           (m.get("kickoff"), m.get("home"), m.get("away")):
            return []                      # a later match has been played since
        row = next((r for r in rows if r.get("team") == raw), None)
        if row is None or row.get("pos") is None:
            return []
        if int(row.get("played") or 0) != len(played_by_club):
            return []                      # the table has not caught up (or is ahead)
        pairs.append((row, ar, (form_map or {}).get(raw) or []))
    out = []
    for row, ar, form in pairs:
        pos = int(row["pos"])
        line = f"{ar} في المركز {_ord_ar(pos)} برصيد {_pts(row.get('pts'))}"
        nb = next((r for r in rows if int(r.get("pos") or 0) == (pos - 1 if pos > 1 else 2)), None)
        if nb and nb.get("pts") is not None and row.get("pts") is not None:
            gap = abs(int(nb["pts"]) - int(row["pts"]))
            who = f"{ar_team(nb.get('team'))} ({_ord_ar(int(nb['pos']))})"
            if gap:
                line += f"، بفارق {_pts(gap)} {'خلف' if pos > 1 else 'أمام'} {who}"
            else:
                line += f"، متساويًا في النقاط مع {who}"
        streak = _streak_ar(form)
        line += f" — {streak}." if streak else "."
        out.append(line)
    return out


def _form_counts(res, n=5):
    l = (res or [])[-n:]
    return l, l.count("W"), l.count("D"), l.count("L")


def _form_phrase(res, club):
    """«الأهلي في آخر 5 مباريات: 3 انتصارات وتعادلان» (+ the current run)."""
    l, w, d, ls = _form_counts(res)
    if len(l) < 3:
        return ""
    bits = [x for x in (_wins(w) if w else "", _draws(d) if d else "",
                        _losses(ls) if ls else "") if x]
    out = f"{club} في آخر {_games(len(l))}: " + " و".join(bits)
    st = _streak_ar(l)
    return out + (f" ({st})" if st else "")


def _pts_phrase(n):
    """«برصيد 10 نقاط» / «دون أي نقاط» — _pts(0) alone gives «دون نقاط», which
    reads wrong after «برصيد»."""
    n = int(n or 0)
    return f"برصيد {_pts(n)}" if n else "دون أي نقاط"


def _per_game(row):
    g = int(row.get("played") or 0)
    if not g:
        return None
    return (int(row.get("gf") or 0) / g, int(row.get("ga") or 0) / g)


def _club_pool(fin_all, raw):
    return [x for x in (fin_all or []) if raw in (x.get("home"), x.get("away"))]


def _days_between(d1, d2):
    try:
        a = datetime.date.fromisoformat(d1)
        b_ = datetime.date.fromisoformat(d2)
        return (a - b_).days
    except Exception:
        return None


def pre_match_read(m, h_ar, a_ar, comp_label_txt, st=None, form_map=None,
                   fin_comp=None, fin_all=None, pred=None):
    """«قراءة قبل المباراة» — (html, faq_html, weight) for an UPCOMING match.

    Layer 1 of the match-page rework (2026-09-14). The page could already tell
    you WHEN the match is and what the model thinks; it could not tell you how
    the two clubs arrive at it. Everything here is a restatement of the
    official table, the form list and the finished matches in the season pool -
    the same discipline as post_match_read(), so it can run on every fixture
    without turning into generated content.

    `weight` counts the substantive facts: the caller uses it to decide whether
    the page is worth indexing (an empty fixture page was the thin content
    AdSense rejected on 2026-09-04)."""
    rows = (st or {}).get("table") or []
    if (st or {}).get("zeroed") or (st or {}).get("past"):
        rows = []
    def row_of(raw):
        r = next((x for x in rows if x.get("team") == raw), None)
        return r if r and int(r.get("played") or 0) > 0 else None
    rh, ra = row_of(m.get("home")), row_of(m.get("away"))
    fm = form_map or {}
    fh, fa = fm.get(m.get("home")) or [], fm.get(m.get("away")) or []
    ps, weight = [], 0

    # 1. where the two clubs stand right now
    if rh and ra:
        ps.append(f"يدخل {h_ar} المباراة في المركز {_ord_ar(int(rh['pos']))} "
                  f"{_pts_phrase(rh.get('pts'))} من {_games(rh.get('played'))}، "
                  f"بينما يحتل {a_ar} المركز {_ord_ar(int(ra['pos']))} "
                  f"{_pts_phrase(ra.get('pts'))}.")
        weight += 1

    # 2. how they arrive: the last five, with the current run
    forms = [x for x in (_form_phrase(fh, h_ar), _form_phrase(fa, a_ar)) if x]
    if forms:
        ps.append("، و".join(forms) + ".")
        weight += len(forms)

    # 3. the goals: scored and conceded per game this season
    if rh and ra:
        ph_, pa_ = _per_game(rh), _per_game(ra)
        if ph_ and pa_:
            ps.append(f"هجوميًا، سجّل {h_ar} بمعدل {ph_[0]:.1f} هدف في المباراة "
                      f"واستقبل {ph_[1]:.1f}، مقابل {pa_[0]:.1f} و{pa_[1]:.1f} "
                      f"{_lam(a_ar)}.")
            weight += 1

    # 4. clean sheets, counted off the season pool
    for raw, club in ((m.get("home"), h_ar), (m.get("away"), a_ar)):
        ms = _club_pool(fin_comp, raw)
        if len(ms) >= 3:
            cs = sum(1 for x in ms
                     if (x["away_score"] if x.get("home") == raw else x["home_score"]) == 0)
            if cs >= 2:
                ps.append(f"حافظ {club} على نظافة شباكه في "
                          f"{_cnt(cs, 'مباراة واحدة', 'مباراتين', 'مباريات', 'مباراة')} "
                          f"من أصل {len(ms)} هذا الموسم.")
                weight += 1
                break

    # 5. the last time they met (any competition in the season pool)
    prev = sorted([x for x in (fin_all or [])
                   if {x.get("home"), x.get("away")} == {m.get("home"), m.get("away")}],
                  key=lambda x: x.get("kickoff") or "")
    if prev:
        lastm = prev[-1]
        hs_, as_ = lastm.get("home_score"), lastm.get("away_score")
        who = (ar_team(lastm.get("home")) if hs_ > as_
               else ar_team(lastm.get("away")) if as_ > hs_ else None)
        res = (f"بفوز {who} {max(hs_, as_)}-{min(hs_, as_)}" if who
               else f"بالتعادل {hs_}-{as_}")
        ps.append(f"آخر مواجهة بينهما كانت يوم {fmt_day(lastm['kickoff'])} "
                  f"وانتهت {res}.")
        weight += 1

    # 6. a short turnaround is a fact worth knowing before kick-off
    rest = []
    for raw, club in ((m.get("home"), h_ar), (m.get("away"), a_ar)):
        ms = _club_pool(fin_all, raw)
        if not ms:
            continue
        gap = _days_between(m.get("kickoff"), ms[-1].get("kickoff"))
        if gap is not None and 0 <= gap <= 3:
            opp = ar_team(ms[-1]["away"] if ms[-1].get("home") == raw else ms[-1]["home"])
            rest.append(f"{club} يلعب بعد {_cnt(gap, 'يوم واحد', 'يومين', 'أيام', 'يومًا')} "
                        f"فقط من مباراته أمام {opp}")
    if rest:
        ps.append("، و".join(rest) + ".")
        weight += 1

    # 7. what a win is worth - arithmetic on the CURRENT points, never a
    #    predicted position (other clubs play too, and tie-break rules differ)
    if rh and ra:
        stake = f"الفوز يرفع {h_ar} إلى {_pts(int(rh.get('pts') or 0) + 3)}"
        pos = int(rh["pos"])
        nb = next((r for r in rows if int(r.get("pos") or 0) == (pos - 1 if pos > 1 else 2)), None)
        if nb and nb.get("pts") is not None:
            diff = (int(rh.get("pts") or 0) + 3) - int(nb["pts"])
            # the neighbour in the table is often the opponent itself - naming
            # it twice in one sentence reads like two different clubs
            who = (f"{a_ar} نفسه" if nb.get("team") == m.get("away")
                   else f"{ar_team(nb.get('team'))} ({_ord_ar(int(nb['pos']))})")
            if diff > 0:
                stake += f"، أي {_pts(diff)} فوق {who} حاليًا"
            elif diff < 0:
                stake += f"، أي {_pts(-diff)} خلف {who} حاليًا"
            else:
                stake += f"، ليتساوى مع {who} حاليًا"
        stake += (f"، بينما يرفع الفوز {a_ar} إلى "
                  f"{_pts(int(ra.get('pts') or 0) + 3)}.")
        ps.append(stake)
        weight += 1

    if not ps:
        return "", "", 0
    html = (f'<section class="minfo st-analysis mread"><h2>قراءة قبل مباراة '
            f'{esc(h_ar)} و{esc(a_ar)}</h2><p>' + " ".join(esc(x) for x in ps)
            + '</p><p class="pd-note">الأرقام من جدول البطولة الرسمي ونتائج '
              'الموسم حتى تاريخ النشر، وتُحدَّث تلقائيًا حتى صافرة البداية.</p></section>')

    faq = []
    when = fmt_day(m["kickoff"]) + (f" في تمام {m['koff_time']} بتوقيت القاهرة"
                                    if m.get("koff_time") else "")
    faq.append((f"متى مباراة {h_ar} و{a_ar}؟",
                f"تُقام يوم {when} ضمن {comp_label_txt}."))
    ch = m.get("channel") or COMP_TV.get(m.get("competition"))
    faq.append((f"ما القناة الناقلة لمباراة {h_ar} و{a_ar}؟",
                f"تُنقل عبر {ch}." if ch else
                "لم تتوفر بعد معلومات القناة الناقلة لهذه المباراة، وتُحدَّث الصفحة فور توفرها."))
    if forms:
        faq.append((f"كيف يدخل {h_ar} و{a_ar} المباراة؟", "، و".join(forms) + "."))
    if pred:
        pick = max((("H", pred["ph"]), ("D", pred["pd"]), ("A", pred["pa"])),
                   key=lambda x: x[1])
        pick_ar = {"H": f"فوز {h_ar}", "D": "التعادل", "A": f"فوز {a_ar}"}[pick[0]]
        faq.append((f"ما توقع يلا سكور لمباراة {h_ar} و{a_ar}؟",
                    f"يرجّح النموذج {pick_ar} باحتمال {_pct(pick[1])}، والأهداف "
                    f"المتوقعة {pred['lh']:.1f} مقابل {pred['la']:.1f}. "
                    "هذه احتمالات إحصائية وليست نصيحة للمراهنة."))
    fhtml = ('<section class="minfo faq"><h2>أسئلة شائعة عن المباراة</h2>'
             + "".join(f'<details><summary>{esc(q)}</summary><p>{esc(a)}</p></details>'
                       for q, a in faq) + '</section>')
    fld = jsonld({"@context": "https://schema.org", "@type": "FAQPage",
                  "mainEntity": [{"@type": "Question", "name": q,
                                  "acceptedAnswer": {"@type": "Answer", "text": a}}
                                 for q, a in faq]})
    return html, fhtml + fld, weight


def post_match_read(m, e, flipped, h_ar, a_ar, hs, as_, comp_label_txt,
                    st=None, form_map=None, fin_comp=None):
    """(section_html, faq_html_plus_jsonld) for a finished match page."""
    story = match_story(e, flipped, h_ar, a_ar, hs, as_)
    rat = match_ratings(e, flipped, h_ar, a_ar)
    tbl = table_after(m, st, form_map, fin_comp, h_ar, a_ar)
    if not story and not rat and not tbl:
        return "", ""
    ps = []
    if story:
        ps.append("<p>" + " ".join(esc(x) for x in story) + "</p>")
    if rat:
        def chip(lbl, p):
            cls = _rt_class(p["rt"]) or "r6"
            return (f'<div class="mr-c"><span class="mr-l">{esc(lbl)}</span>'
                    f'<b><bdi>{esc(p["name"])}</bdi></b>'
                    f'<small><bdi>{esc(p["club"])}</bdi></small>'
                    f'<span class="rt-b {cls}">{p["rt"]:.1f}</span></div>')
        tie = rat["best_other"] and rat["best_other"]["rt"] >= rat["best"]["rt"]
        cards = [chip(f'الأفضل في {rat["best"]["club"]}' if tie else "الأفضل في اللقاء",
                      rat["best"])]
        if rat["best_other"]:
            cards.append(chip(f'الأفضل في {rat["best_other"]["club"]}', rat["best_other"]))
        if rat["low"]["rt"] < rat["best"]["rt"]:
            cards.append(chip("أقل تقييم", rat["low"]))
        s1, s2 = rat["sides"]
        ps.append('<div class="mr-grid">' + "".join(cards) + '</div>')
        ps.append(f'<p class="mr-avg">متوسط تقييم التشكيلة الأساسية: '
                  f'<bdi>{esc(s1["club"])}</bdi> <b>{s1["avg"]:.1f}</b> مقابل '
                  f'<bdi>{esc(s2["club"])}</bdi> <b>{s2["avg"]:.1f}</b> '
                  '<small>(تقييمات المصدر لكل لاعب، وهي نفسها الظاهرة على الملعب أدناه)</small></p>')
    if tbl:
        ps.append('<p><b>بعد هذه النتيجة:</b> ' + " ".join(esc(x) for x in tbl) + '</p>')
    html = (f'<section class="minfo st-analysis mread"><h2>قراءة مباراة '
            f'{esc(h_ar)} و{esc(a_ar)}</h2>' + "".join(ps) + '</section>')

    # FAQ: the same facts as questions (the shape /standings pages already use)
    sd = _side_of(flipped)
    scorers = [g for g in (e.get("goals") or []) if g.get("player")]
    faq = [(f"كم انتهت مباراة {h_ar} و{a_ar}؟",
            f"انتهت {h_ar} {hs}-{as_} {a_ar} في {comp_label_txt}.")]
    if scorers:
        names = [f'{g["player"]} ({g["minute"]}\u2032)' if g.get("minute") else g["player"]
                 for g in scorers]
        faq.append((f"من سجل أهداف مباراة {h_ar} و{a_ar}؟", "، ".join(names) + "."))
    if rat:
        _bo = rat["best_other"]
        if _bo and _bo["rt"] >= rat["best"]["rt"]:
            ans = (f'تساوى {rat["best"]["name"]} ({rat["best"]["club"]}) و{_bo["name"]} '
                   f'({_bo["club"]}) في أعلى تقييم بالمباراة بـ{rat["best"]["rt"]:.1f}.')
        else:
            ans = (f'{rat["best"]["name"]} لاعب {rat["best"]["club"]} بتقييم '
                   f'{rat["best"]["rt"]:.1f}، وهو الأعلى بين لاعبي التشكيلتين الأساسيتين.')
        faq.append((f"من أفضل لاعب في مباراة {h_ar} و{a_ar}؟", ans))
    if tbl:
        faq.append((f"ماذا تغيّر في الترتيب بعد مباراة {h_ar} و{a_ar}؟",
                    " ".join(tbl)))
    fhtml = ('<section class="minfo faq"><h2>أسئلة شائعة عن المباراة</h2>'
             + "".join(f'<details><summary>{esc(q)}</summary><p>{esc(a)}</p></details>'
                       for q, a in faq) + '</section>')
    fld = jsonld({"@context": "https://schema.org", "@type": "FAQPage",
                  "mainEntity": [{"@type": "Question", "name": q,
                                  "acceptedAnswer": {"@type": "Answer", "text": a}}
                                 for q, a in faq]})
    return html, fhtml + fld


def match_details_html(e, flipped, h_ar, a_ar):
    """'أحداث المباراة' timeline (goals+cards+subs) + 'التشكيلة' section."""
    def side(s):
        return ("a" if s == "h" else "h") if flipped else s
    parts = []
    evs = []
    for g in (e.get("goals") or []):
        txt = f'<bdi>{esc(g["player"])}</bdi>' + (
            f' <span class="ev-tag">({esc(g["tag"])})</span>' if g.get("tag") else "")
        evs.append((_min_key(g.get("minute")), side(g.get("side")),
                    g.get("minute"), "⚽", txt))
    for c in (e.get("cards") or []):
        ic = f'<span class="cardic {"r" if c.get("color") == "r" else "y"}"></span>'
        evs.append((_min_key(c.get("minute")), side(c.get("side")),
                    c.get("minute"), ic, f'<bdi>{esc(c["player"])}</bdi>'))
    for s in (e.get("subs") or []):
        txt = (f'<span class="sub-in">▲ <bdi>{esc(s["in"])}</bdi></span> '
               f'<span class="sub-out">▼ <bdi>{esc(s["out"])}</bdi></span>')
        evs.append((_min_key(s.get("minute")), side(s.get("side")),
                    s.get("minute"), "🔁", txt))
    evs.sort(key=lambda x: x[0])
    if evs:
        parts.append('<section class="minfo"><h2>أحداث المباراة</h2><div class="mtl">')
        for _, sd, mn, ic, txt in evs:
            cell = f'{ic} {txt}'
            mn_t = f'<span dir="ltr">{esc(mn)}′</span>' if mn else ""
            parts.append(f'<div class="tl-r"><div class="tl-h">{cell if sd == "h" else ""}</div>'
                         f'<div class="tl-m">{mn_t}</div>'
                         f'<div class="tl-a">{cell if sd != "h" else ""}</div></div>')
        parts.append('</div></section>')
    lus = e.get("lineups") or {}
    eh, ea = ("a", "h") if flipped else ("h", "a")
    lh, la = lus.get(eh), lus.get(ea)
    ph, pa = _pitch_rows(lh, True), _pitch_rows(la, False)
    if ph and pa:
        # sofascore-style pitch: home XI in the top half, away mirrored below
        def badges(side_key):
            cards = {}
            for c in e.get("cards") or []:
                if side(c.get("side")) == side_key:
                    cur = cards.get(c.get("player"))
                    cards[c.get("player")] = ("r" if c.get("color") == "r"
                                              or cur == "r" else "y")
            off = {s.get("out") for s in e.get("subs") or []
                   if side(s.get("side")) == side_key}
            return cards, off
        parts.append('<section class="minfo"><h2>التشكيلة الأساسية</h2>')
        fh = f' <span class="lu-f" dir="ltr">{esc(lh["formation"])}</span>' if lh.get("formation") else ""
        fa = f' <span class="lu-f" dir="ltr">{esc(la["formation"])}</span>' if la.get("formation") else ""
        # labels live INSIDE the pitch corners so the same markup reads
        # correctly in both orientations (vertical mobile / horizontal desktop)
        parts.append('<div class="pitch" dir="ltr">'
                     '<div class="pt-half"></div><div class="pt-circle"></div>'
                     '<div class="pt-box pt-box-t"></div><div class="pt-box pt-box-b"></div>'
                     f'<span class="pt-lab pt-lab-h"><bdi>{esc(h_ar)}</bdi>{fh}</span>'
                     f'<span class="pt-lab pt-lab-a"><bdi>{esc(a_ar)}</bdi>{fa}</span>')
        for chips, side_key in ((ph, "h"), (pa, "a")):
            cards, off = badges(side_key)
            for x, y, p in chips:
                img = _athlete_img(p)
                src = local_crest(img) if img else None
                num = esc(str(p.get("num"))) if p.get("num") is not None else ""
                ava = (f'<img src="{esc(src)}" alt="" loading="lazy" '
                       'onerror="this.style.display=\'none\';'
                       "this.nextElementSibling.style.display='flex'\">"
                       f'<span class="pp-fb">{num}</span>'
                       if src else f'<span class="pp-fb" style="display:flex">{num}</span>')
                bd = ""
                c = cards.get(p.get("name"))
                if c:
                    bd += f'<span class="pp-card {c}"></span>'
                if p.get("name") in off:
                    bd += '<span class="pp-sub">⇄</span>'
                # a rating badge on this pitch means "how he played in THIS
                # match" — on a pre-match XI the feed's number is a carried-over
                # average, and printing it next to an unplayed match reads as a
                # match rating for a match nobody has played (no possibly-wrong
                # numbers, user rule 2026-08-31)
                rc = None if e.get("pre") else _rt_class(p.get("rt"))
                rt = (f'<span class="pp-rt {rc}">{float(p["rt"]):.1f}</span>'
                      if rc else "")
                cap = '<span class="pp-cap">C</span>' if p.get("cap") else ""
                nm = f'{num + " " if num else ""}{esc(_pshort(p.get("name")))}'
                parts.append(
                    f'<div class="pp" style="--xv:{x:.1f}%;--yv:{y:.1f}%">'
                    f'<span class="pp-ava">{ava}{rt}{bd}{cap}</span>'
                    f'<span class="pp-nm"><bdi>{nm}</bdi></span></div>')
        parts.append('</div></section>')
        return "".join(parts)
    if lh or la:
        parts.append('<section class="minfo"><h2>التشكيلة الأساسية</h2><div class="lu">')
        for team_name, lu in ((h_ar, lh), (a_ar, la)):
            parts.append('<div class="lu-t">')
            if lu:
                fm = (f' <span class="lu-f" dir="ltr">{esc(lu["formation"])}</span>'
                      if lu.get("formation") else "")
                parts.append(f'<h3><bdi>{esc(team_name)}</bdi>{fm}</h3><ol class="lu-l">')
                for p in lu.get("xi") or []:
                    num = (f'<span class="lu-n">{p["num"]}</span>'
                           if p.get("num") is not None else '<span class="lu-n">·</span>')
                    pos = (f'<span class="lu-p">{esc(p["pos"])}</span>'
                           if p.get("pos") else "")
                    parts.append(f'<li>{num} <bdi>{esc(p["name"])}</bdi>{pos}</li>')
                parts.append('</ol>')
            else:
                parts.append(f'<h3><bdi>{esc(team_name)}</bdi></h3>'
                             '<div class="lu-none">التشكيلة غير متاحة</div>')
            parts.append('</div>')
        parts.append('</div></section>')
    return "".join(parts)

def match_url(m):
    """Canonical per-match page path, or None when the id is missing."""
    return f"/m/{m['match_id']}.html" if m.get("match_id") else None

def match_row(m, show_time=False, show_comp=True, goals=None, link=None,
              pred=None, done=None):
    st = (m.get("status") or "").upper()
    badge = {"LIVE": ("مباشر", "live"), "FINISHED": ("انتهت", "fin"),
             "UPCOMING": ("قادمة", "up"), "POSTPONED": ("", "pp")}.get(st, ("", "up"))
    if st == "POSTPONED":
        mid = '<span class="ko ko-pp">مؤجلة</span>'
    elif st == "LIVE":
        # static live scores are up to 15 min stale = wrong data (user rule
        # 2026-08-31): dashes until LIVE_JS paints the real score
        mid = '<b class="score">- - -</b>'
    elif st == "FINISHED":
        mid = f'<b class="score">{m.get("home_score") if m.get("home_score") is not None else ""} - {m.get("away_score") if m.get("away_score") is not None else ""}</b>'
    else:
        when = (m.get("koff_time") if show_time and m.get("koff_time") else m.get("kickoff"))
        mid = f'<span class="ko">{esc(when)}</span>'
    def crest(u):
        return f'<img src="{esc(local_crest(u))}" alt="" loading="lazy">' if u else '<span class="ph">⚽</span>'
    comp = ""
    if show_comp:
        comp = f'<div class="mcomp">{esc(comp_label(m.get("competition")))}{(" · " + esc(m.get("channel"))) if m.get("channel") else ""}</div>'
    # only LIVE / FINISHED get a status pill (upcoming shows its time instead)
    pill = (f'<span class="pill pill-{badge[1]}">{esc(badge[0])}</span>'
            if st in ("LIVE", "FINISHED") else "")
    gblock = ""
    if goals:
        def side_list(sd):
            its = []
            for g in goals:
                if g.get("side") != sd:
                    continue
                mn = (f' <i class="mg-m">{esc(g["minute"])}′</i>'
                      if g.get("minute") else "")
                tg = f' <small>({esc(g["tag"])})</small>' if g.get("tag") else ""
                its.append(f'<span class="mg">⚽ <bdi>{esc(g.get("player"))}</bdi>{mn}{tg}</span>')
            return "".join(its)
        gblock = (f'<div class="mgoals"><div class="mg-side">{side_list("h")}</div>'
                  f'<div class="mg-gap"></div>'
                  f'<div class="mg-side">{side_list("a")}</div></div>')
    # the prediction button rides its own full-width row under the teams.
    # It sits ABOVE .mstretch (which covers the row) or the stretched link
    # swallows the click and opens the match page instead of the popup.
    # `pred` = a prediction for a match still to come; `done` = the frozen
    # log row of one that is over. Never both.
    _pb = pred_btn(pred) if pred else done_btn(done)
    pbtn = f'<div class="pbtn-row">{_pb}</div>' if _pb else ""
    stretch = (f'<a class="mstretch" href="{esc(link)}" '
               f'aria-label="تفاصيل مباراة {esc(ar_team(m.get("home")))} و{esc(ar_team(m.get("away")))}"></a>'
               if link else "")
    return f"""<div class="mrow mrow-{badge[1]}" data-lv data-h="{esc(ar_team(m.get('home')))}" data-a="{esc(ar_team(m.get('away')))}">
  {stretch}{pill}
  <div class="team th">{crest(m.get('home_badge'))}<span><bdi>{esc(ar_team(m.get('home')))}</bdi></span></div>
  <div class="mid">{mid}</div>
  <div class="team ta">{crest(m.get('away_badge'))}<span><bdi>{esc(ar_team(m.get('away')))}</bdi></span></div>
  {comp}
  {pbtn}
  {gblock}
</div>"""

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

NEWLINE = chr(10)

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

# ---------------------------------------------------------------- styles
CSS = r""":root{
  --green:#1f94d3; --green-d:#15658f; --live:#e11d48; --fin:#64748b; --up:#2563eb;
  --ink:#0f172a; --muted:#64748b; --card:#fff; --bg:#eef2f6;
}
*{box-sizing:border-box}
/* a class-level `display` beats the UA's [hidden]{display:none}, so an element
   hidden via the attribute keeps rendering (the fav-live card showed as an
   empty pill, and the daynav needed an inline-style workaround for the same
   reason). One rule closes the whole class of bug. */
[hidden]{display:none!important}
html,body{overflow-x:hidden;max-width:100%}
/* Almarai = FilGoal's Arabic UI font (Google Fonts, display=swap so text
   never blocks); Segoe/Tahoma stay as the pre-load + no-JS fallback.
   Almarai's heaviest weight is 800 — the CSS's font-weight:900 rules
   resolve to it automatically. */
body{margin:0;font-family:'Almarai','Segoe UI',Tahoma,Arial,sans-serif;background:var(--bg);color:var(--ink);line-height:1.6}
.wrap{max-width:1600px;margin:0 auto;padding:0 20px}
a{color:inherit}
.site-head{background:linear-gradient(90deg,var(--green-d),var(--green));box-shadow:0 2px 10px rgba(15,23,42,.18);position:sticky;top:0;z-index:9}
.head-in{display:flex;align-items:center;height:78px;position:relative;z-index:1}
/* Egyptian fans facing the camera (CC BY-SA, WC 2018) across the header,
   dissolving into the green gradient before the brand */
.head-crowd{position:absolute;left:0;top:0;height:78px;width:calc(100% - 300px);
  background:url("/media/fans-header.jpg") left center/auto 78px repeat-x;
  /* fans-header.jpg = one wide 3473x156 band composed from four DIFFERENT
     regions of the CC BY-SA WC-2018 crowd photo (blended seams, faces fill
     the height) - renders 1737px @78px, no visible repeat on normal screens */
  -webkit-mask-image:linear-gradient(to right,rgba(0,0,0,.95) 55%,transparent 97%);
  mask-image:linear-gradient(to right,rgba(0,0,0,.95) 55%,transparent 97%);
  pointer-events:none}
.brand{color:#fff;font-weight:900;font-size:1.3rem;text-decoration:none;display:inline-flex;align-items:center;gap:8px}
.brand .ball{width:30px;height:30px;border-radius:50%;border:2px solid rgba(255,255,255,.9);box-shadow:0 1px 5px rgba(0,0,0,.25);background:#1f94d3}
.beta{font-size:.62rem;font-weight:800;color:#ffe08a;border:1px solid rgba(255,224,138,.55);background:rgba(0,0,0,.18);padding:2px 9px;border-radius:999px;letter-spacing:.02em;white-space:nowrap}
/* second row: navigation tabs (like the app) */
.site-nav{position:relative;z-index:1;background:rgba(0,0,0,.16);border-top:1px solid rgba(255,255,255,.12)}
.nav-in{display:flex;align-items:stretch;height:46px;overflow-x:auto;scrollbar-width:none}
.nav-in::-webkit-scrollbar{display:none}
.navtab{display:inline-flex;align-items:center;gap:7px;padding:0 18px;color:rgba(255,255,255,.85);text-decoration:none;font-weight:800;font-size:.95rem;border-bottom:3px solid transparent;transition:background .12s,color .12s;white-space:nowrap}
.navtab:hover{background:rgba(255,255,255,.10);color:#fff}
.navtab.is-active{color:#fff;border-bottom-color:#fff;background:rgba(255,255,255,.08)}
.navtab .ico{font-size:1.1rem;display:inline-block;transition:transform .18s}
.navtab:hover .ico{transform:scale(1.25) rotate(-8deg)}
.navtab.is-active .ico{transform:scale(1.1)}
.page-h{color:var(--green-d);font-weight:900;margin:22px 0 12px}
/* featured */
.feat{display:block;position:relative;height:340px;border-radius:18px;overflow:hidden;text-decoration:none;color:#fff;box-shadow:0 14px 34px rgba(15,23,42,.24);margin-bottom:16px;background:linear-gradient(135deg,var(--green-d),#071f2c)}
.feat-img{position:absolute;inset:0;background-size:cover;background-position:50% 22%}
.feat.noimg .feat-img,.feat-img.noimg{background:linear-gradient(135deg,var(--green),#0d3e59)}
.feat::after{content:"";position:absolute;inset:0;background:linear-gradient(to top,rgba(4,18,28,.95) 8%,rgba(4,18,28,.15) 70%)}
.feat-body{position:absolute;inset-inline:0;bottom:0;padding:22px 26px;z-index:2}
.feat-body h2{margin:0 0 8px;font-size:1.55rem;font-weight:900;text-shadow:0 2px 10px rgba(0,0,0,.5)}
.feat-body p{margin:0;opacity:.94}
.feat-when{margin-top:8px!important;font-size:.82rem;font-weight:800;opacity:.85}
/* /fb.html internal helper page */
.fbp{background:#fff;border:1px solid #e2e8f0;border-radius:14px;padding:14px;margin:0 0 14px}
.fbp-h{color:var(--muted);font-size:.85rem;font-weight:800;margin-bottom:8px}
.fbp-t{width:100%;min-height:170px;border:1px solid #e2e8f0;border-radius:10px;padding:10px;
  font:inherit;font-size:.95rem;line-height:1.7;resize:vertical;background:#f8fafc}
.fbp-c{margin-top:8px;border:0;border-radius:999px;padding:9px 26px;font:inherit;
  font-weight:800;background:var(--brand,#0a7c3f);color:#fff;cursor:pointer}
.fbp-note{color:var(--muted);font-weight:700;margin:0 0 16px}
/* grid */
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:15px}
.card{display:block;background:var(--card);border:1px solid #e6ebf1;border-radius:14px;overflow:hidden;text-decoration:none;box-shadow:0 3px 10px rgba(15,23,42,.08);transition:transform .16s,box-shadow .16s}
.card:hover{transform:translateY(-5px);box-shadow:0 16px 30px rgba(15,23,42,.17)}
.card-img{height:140px;background-size:cover;background-position:50% 22%;display:flex;align-items:center;justify-content:center;font-size:2.4rem;color:rgba(255,255,255,.35)}
.card-img.noimg{background:linear-gradient(135deg,var(--green),#0d3e59)}
.card-b{padding:13px 15px}
.card-b h3{margin:0 0 7px;font-size:1rem;font-weight:800;line-height:1.4}
.meta{color:var(--muted);font-size:.78rem;font-weight:700;margin:0}
.more{margin:10px 2px}.more a{color:var(--green-d);font-weight:800;text-decoration:none}
/* article */
.back{display:inline-block;color:var(--green-d);font-weight:800;text-decoration:none;margin:14px 0 6px}
.article{background:#fff;border-radius:16px;padding:24px 28px;box-shadow:0 6px 22px rgba(15,23,42,.10);margin-bottom:24px}
.article h1{font-size:1.7rem;font-weight:900;line-height:1.3;margin:.2em 0 .3em}
.a-meta{color:var(--muted);font-weight:700;font-size:.85rem;border-bottom:1px solid #e2e8f0;padding-bottom:12px}
.a-tnote{font-weight:600;opacity:.85}
.a-fig{margin:14px 0}
.a-img{width:100%;max-height:400px;object-fit:cover;object-position:50% 18%;border-radius:14px;display:block}
.a-credit{color:var(--muted);font-size:.72rem;font-weight:600;margin-top:6px;text-align:center}
.lead{font-size:1.1rem;font-weight:700;color:#334155}
.a-body{font-size:1.06rem;line-height:1.95}.a-body p{margin:0 0 14px}
.a-body h2{font-size:1.25rem;font-weight:900;color:var(--green-d);margin:22px 0 8px}
.legal{max-width:820px}.legal a{color:var(--green-d);font-weight:700}
.foot-links{margin:6px 0}.foot-links a{color:#cbd5e1;text-decoration:none;font-weight:700}
.foot-links a:hover{color:#fff}
/* matches — FotMob-style 3 columns: leagues | matches | extra */
.mpage{display:grid;grid-template-columns:240px minmax(0,1fr) 300px;gap:18px;align-items:start}
.mp-main{min-width:0}
.mp-side{background:#fff;border:1px solid #e6ebf1;border-radius:14px;padding:12px;box-shadow:0 1px 3px rgba(15,23,42,.05);position:sticky;top:120px}
.mp-h{margin:2px 0 10px;font-size:.95rem;font-weight:900;color:var(--green-d)}
.lg-list{display:flex;flex-direction:column;gap:2px}
.lg-item{display:flex;align-items:center;gap:9px;width:100%;text-align:start;background:transparent;border:0;border-radius:9px;padding:9px 10px;font:inherit;font-weight:800;font-size:.86rem;color:var(--ink);cursor:pointer;transition:background .12s}
.lg-item:hover{background:#f1f5f9}
.lg-item.is-active{background:#eaf3fa;color:var(--green-d)}
.lg-ico{font-size:1.05rem;width:22px;text-align:center;flex:0 0 auto}
.lg-logo{width:22px;height:22px;object-fit:contain;flex:0 0 auto}
.lt-head .lg-logo{width:24px;height:24px}
.comp-h .lg-logo,.comp-h .lg-ico{width:20px;height:20px;font-size:1rem;vertical-align:-5px;margin-inline-end:5px}
.no-comp{color:var(--muted);font-weight:700;text-align:center;padding:26px 0}
.mp-news{display:flex;flex-direction:column;gap:9px;margin-bottom:14px}
.mn-item{display:flex;gap:9px;align-items:center;text-decoration:none}
.mn-th{width:58px;height:44px;border-radius:8px;background-size:cover;background-position:center;flex:0 0 auto;background-color:#e6ebf1;display:flex;align-items:center;justify-content:center;color:rgba(255,255,255,.6);font-size:1.1rem}
.mn-th.noimg{background:linear-gradient(135deg,var(--green),#0d3e59)}
.mn-b{display:flex;flex-direction:column;min-width:0}
.mn-t{font-size:.8rem;font-weight:800;color:var(--ink);line-height:1.4;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.mn-d{font-size:.7rem;color:var(--muted);font-weight:700;margin-top:2px}
.mp-ad .ad-placeholder,.mp-ad .ad-unit{position:static;min-height:250px}
/* league standings table */
.ltable{background:#fff;border:1px solid #e6ebf1;border-radius:14px;overflow:hidden;margin-bottom:16px;box-shadow:0 1px 3px rgba(15,23,42,.05)}
.lt-head{display:flex;align-items:center;gap:8px;font-weight:900;color:var(--green-d);padding:12px 14px;border-bottom:1px solid #eef2f6}
.lt-scroll{overflow-x:auto}
.lt{width:100%;border-collapse:collapse;font-size:.82rem;font-variant-numeric:tabular-nums}
.lt th,.lt td{padding:9px 6px;text-align:center;white-space:nowrap}
.lt thead th{color:var(--muted);font-weight:800;font-size:.72rem;border-bottom:1px solid #eef2f6}
/* 404 page */
.nf{text-align:center;padding:46px 16px 30px;max-width:520px;margin:0 auto}
.nf-emoji{font-size:3rem;margin-bottom:6px}
.nf .page-h{margin-top:0}
.nf-p{color:var(--muted);font-weight:700}
.nf-wait{color:var(--green-d)}
.nf-spin{display:inline-block;width:12px;height:12px;border:2px solid var(--green-d);
  border-inline-start-color:transparent;border-radius:50%;vertical-align:-2px;
  animation:nfspin .9s linear infinite}
@keyframes nfspin{to{transform:rotate(360deg)}}
@media (prefers-reduced-motion: reduce){.nf-spin{animation:none;border-inline-start-color:var(--green-d)}}
.nf-links{display:flex;gap:10px;justify-content:center;flex-wrap:wrap;margin-top:20px}
.nf-btn{background:var(--green-d);color:#fff;text-decoration:none;font-weight:800;
  border-radius:999px;padding:9px 22px;font-size:.9rem}
.nf-btn2{background:#fff;color:var(--green-d);border:1.5px solid var(--green-d)}
/* stats dashboard */
.hintline{color:var(--muted);font-weight:700;font-size:.85rem;margin:-6px 0 18px}
.stats-sec{background:#fff;border:1px solid #e6ebf1;border-radius:14px;padding:18px;margin:0 0 18px;
  box-shadow:0 1px 3px rgba(15,23,42,.05)}
.stats-h3{font-size:.9rem;font-weight:900;color:var(--muted);margin:16px 0 8px}
/* league view tabs (/matches, one league selected) */
.ltabs{display:flex;gap:6px;overflow-x:auto;scrollbar-width:none;
  margin:0 0 14px;padding-bottom:2px;border-bottom:2px solid #e6ebf1}
.ltabs::-webkit-scrollbar{display:none}
.ltab{flex:0 0 auto;appearance:none;background:none;border:0;cursor:pointer;
  font-family:inherit;font-size:.86rem;font-weight:800;color:var(--muted);
  padding:9px 14px;border-radius:9px 9px 0 0;margin-bottom:-2px;
  border-bottom:2px solid transparent;transition:color .12s,border-color .12s}
.ltab:hover{color:var(--ink);background:#f4f8fb}
.ltab.is-on{color:var(--green-d);border-bottom-color:var(--green)}
.ltab:focus-visible{outline:2px solid var(--green);outline-offset:2px}
.lpane .stats-sec{background:none;border:0;box-shadow:none;padding:0;margin:0}
.lpane .stats-h3:first-child{margin-top:0}
.lpane .lg-fix{display:block}
@media(max-width:560px){.ltab{font-size:.8rem;padding:8px 11px}}
.stat-tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}
.tile{background:#f8fafc;border:1px solid #eef2f6;border-radius:11px;padding:12px;text-align:center}
.tile b{display:block;font-size:1.05rem;color:#15658f}
.tile span{font-size:.72rem;color:var(--muted);font-weight:700}
.tile-res{grid-column:span 2}
.tile-ms{display:flex;align-items:center;justify-content:center;gap:6px;margin-top:7px}
.tile-ms .tm{display:inline-flex;align-items:center;gap:4px;min-width:0;font-size:.78rem;font-weight:700}
.tile-ms .tm bdi{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.tile-ms img{width:18px;height:18px;object-fit:contain;flex:0 0 auto}
.tile-ms .ph{font-size:.8rem;flex:0 0 auto}
.tile-ms i{font-style:normal;color:var(--muted);font-size:.72rem;flex:0 0 auto}
.tile-when{margin-top:4px;font-size:.68rem;color:var(--muted);font-weight:700}
.tile-sc .tile-ms{gap:5px}
/* one narrow column, so let a long Arabic name wrap instead of truncating */
.tile-sc .tile-ms .tm{max-width:100%}
.tile-sc .tile-ms .tm bdi{white-space:normal;overflow:visible;text-overflow:clip}
.sc-face{border-radius:50%;background:#eef2f6}
/* two charts side by side on wide screens, stacked on a phone */
.chart-cols{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:14px;align-items:start}
.chart-cols .stats-h3{margin-top:0}
/* a 320px min column would overflow a phone-width container - stack instead */
@media(max-width:760px){.chart-cols{grid-template-columns:1fr}}
/* league percentages */
.pct-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}
@media(max-width:560px){.pct-grid{grid-template-columns:repeat(2,1fr);gap:8px}
  .pct{padding:9px 10px}}
.pct{background:#f8fafc;border:1px solid #eef2f6;border-radius:11px;padding:10px 12px}
.pct-l{display:block;font-size:.72rem;color:var(--muted);font-weight:700}
.pct b{display:block;font-size:1.05rem;color:#15658f;margin:2px 0 5px}
.pct-bar{display:block;height:5px;border-radius:3px;background:#e6edf3;overflow:hidden}
.pct-bar i{display:block;height:100%;background:var(--green);border-radius:3px}
.pct-s{display:block;margin-top:5px;font-size:.66rem;color:var(--muted);font-weight:700}
/* curated clubs panel */
.cl-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:10px}
.cl-card{display:flex;flex-direction:column;gap:6px;text-decoration:none;background:#f8fafc;
         border:1px solid #eef2f6;border-radius:12px;padding:11px 12px;transition:box-shadow .15s,transform .15s}
.cl-card:hover{box-shadow:0 4px 14px rgba(15,23,42,.10);transform:translateY(-1px)}
.cl-top{display:flex;align-items:center;gap:8px;min-width:0}
.cl-top img{width:28px;height:28px;object-fit:contain;flex:0 0 auto}
.cl-n{font-weight:800;font-size:.9rem;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.cl-lg{font-size:.68rem;color:var(--muted);font-weight:700}
.cl-row{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.cl-pos{background:var(--green-d);color:#fff;border-radius:6px;padding:1px 7px;font-size:.74rem;font-weight:800}
.cl-pts{font-size:.76rem;font-weight:700;color:var(--ink)}
.cl-soon{font-size:.72rem;color:var(--muted);font-weight:700}
.cl-form{display:inline-flex;gap:3px;margin-inline-start:auto}
/* the next-fixture line carries a rival name + date + time: let it wrap
   instead of clipping the kickoff time mid-digit in a ~205px card */
.cl-sc{font-size:.72rem;color:var(--muted);font-weight:700;line-height:1.45}
.cl-sc b{color:var(--ink)}
@media(max-width:760px){
  /* 10 stacked cards would bury the league stats - same swipe strip the
     transfers rail and the news shelf use on a phone */
  .cl-grid{display:flex;gap:10px;overflow-x:auto;scrollbar-width:none;padding-bottom:4px}
  .cl-grid::-webkit-scrollbar{display:none}
  .cl-card{flex:0 0 208px}
}
.sc-list{border:1px solid #eef2f6;border-radius:11px;overflow:hidden}
.sc-hd,.sc-row{display:grid;grid-template-columns:30px 1fr 62px 48px;align-items:center;gap:6px;padding:7px 10px}
.sc-nom .sc-hd,.sc-nom .sc-row{grid-template-columns:30px 1fr 48px}
.sc-hd{background:#f8fafc;font-size:.7rem;color:var(--muted);font-weight:800}
.sc-hd span:nth-child(3),.sc-hd span:nth-child(4){text-align:center}
.sc-row{border-top:1px solid #f1f5f9;font-size:.84rem}
.sc-row:nth-child(2){background:#f3f9fd}
.sc-n{color:var(--muted);font-weight:800;font-size:.76rem;text-align:center}
.sc-p{display:flex;align-items:center;gap:7px;min-width:0}
.sc-p img{width:26px;height:26px;object-fit:cover;flex:0 0 auto}
.sc-nm{display:flex;flex-direction:column;min-width:0;line-height:1.3}
.sc-nm bdi{font-weight:700;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.sc-club{font-size:.7rem;color:var(--muted);font-weight:700;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.sc-m{text-align:center;color:var(--muted);font-weight:700;font-size:.78rem}
.sc-g{text-align:center;color:var(--green-d);font-size:.95rem}
@media(max-width:560px){
  /* drop the matches column - the name needs the room on a phone */
  .sc-hd,.sc-row,.sc-nom .sc-hd,.sc-nom .sc-row{grid-template-columns:24px 1fr 40px;padding:7px 8px}
  .sc-m,.sc-list:not(.sc-nom) .sc-hd span:nth-child(3){display:none}
  .sc-p img{width:24px;height:24px}
}
@media(max-width:560px){
  /* 3 short number tiles in one row, the result tile full-width below it */
  .stat-tiles{grid-template-columns:repeat(3,1fr);gap:8px}
  .tile{padding:10px 6px}
  .tile b{font-size:.98rem}
  .tile span{font-size:.64rem}
  .tile-res,.tile-sc{grid-column:1/-1}
  .tile-ms .tm{font-size:.74rem}
}
.chart-wrap{overflow-x:auto}
.chart{width:100%;max-width:680px;height:auto;display:block}
.legend{display:flex;flex-wrap:wrap;gap:12px;margin:6px 0 2px;font-size:.8rem;font-weight:800;color:#334155}
.lgd i{display:inline-block;width:10px;height:10px;border-radius:3px;margin-inline-end:5px;vertical-align:baseline}
/* last-5 form dots */
.fm{display:inline-block;width:10px;height:10px;border-radius:50%;margin-inline-start:3px;vertical-align:middle}
.fm-w{background:#16a34a}.fm-d{background:#94a3b8}.fm-l{background:#e11d48}
.fm-none{color:#cbd5e1}
@media(max-width:560px){.lt-form{display:none}}
.lt tbody tr{border-bottom:1px solid #f1f5f9}
.lt tbody tr:hover{background:#f8fafc}
.lt .lt-pos{width:26px;color:var(--muted);font-weight:800}
.lt .lt-team{text-align:start;display:flex;align-items:center;gap:8px;font-weight:800;min-width:150px}
.lt .lt-team img{width:22px;height:22px;object-fit:contain;flex:0 0 auto}
.lt .lt-pts{font-weight:900;color:var(--green-d)}
.lt-past{margin-inline-start:auto;background:#fef3c7;color:#92400e;font-size:.68rem;font-weight:800;padding:3px 10px;border-radius:999px;white-space:nowrap}
.no-table{min-height:240px}
/* league fixtures side panel (FotMob-style) */
.fx-head{display:flex;align-items:center;gap:8px;font-weight:900;color:var(--green-d);font-size:.92rem;margin:0 0 8px}
.fx-day{font-size:.72rem;font-weight:800;color:var(--muted);background:#f1f5f9;border-radius:7px;padding:5px 9px;margin:10px 0 6px}
.fx{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:6px;padding:7px 2px;border-bottom:1px solid #f1f5f9;font-size:.78rem;font-weight:700}
.fx-home{display:flex;align-items:center;justify-content:flex-end;gap:6px;text-align:end;min-width:0}
.fx-away{display:flex;align-items:center;gap:6px;min-width:0}
.fx-home bdi,.fx-away bdi{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.fx img{width:20px;height:20px;object-fit:contain;flex:0 0 auto}
.fx-ph{font-size:.9rem}
.fx-time{color:var(--green-d);font-weight:800;white-space:nowrap}
.fx-sc{font-weight:900;white-space:nowrap}
/* rounds navigator */
.rnav{display:flex;align-items:center;justify-content:space-between;gap:8px;margin:2px 0 10px;
  background:#f1f5f9;border-radius:999px;padding:4px 6px}
.rnav .rn-label{flex:1;text-align:center;font-weight:900;font-size:.82rem;color:var(--green-d)}
.rn-prev,.rn-next{flex:0 0 auto;width:30px;height:30px;border:0;border-radius:50%;background:var(--green);
  color:#fff;font-size:1.1rem;font-weight:900;line-height:1;cursor:pointer}
.rn-prev:hover,.rn-next:hover{background:var(--green-d)}
.rn-prev:disabled,.rn-next:disabled{opacity:.35;cursor:default}
/* news archive: calm list rows */
.alist{display:flex;flex-direction:column;max-width:860px}
.al-row{display:flex;gap:14px;align-items:center;text-decoration:none;
  padding:14px 6px;border-bottom:1px solid #e6ebf1}
.al-row:hover{background:#f4f8fb}
.al-th{width:150px;height:96px;border-radius:10px;flex:0 0 auto;
  background-size:cover;background-position:center;background-color:#e6ebf1;
  display:flex;align-items:center;justify-content:center;color:rgba(255,255,255,.6);font-size:1.6rem}
.al-th.noimg{background:linear-gradient(135deg,var(--green),#0d3e59)}
.al-th img{width:100%;height:100%;object-fit:cover;border-radius:10px;display:block}
.al-b{display:flex;flex-direction:column;gap:4px;min-width:0}
.al-t{font-size:1rem;font-weight:900;color:var(--ink);line-height:1.55}
.al-s{font-size:.82rem;color:var(--muted);font-weight:600;line-height:1.6;
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.al-m{font-size:.72rem;color:#94a3b8;font-weight:700}
/* home «من أخبارنا أيضًا» — compact 2-col variant of the calm list */
.alist-2col{display:grid;grid-template-columns:1fr 1fr;gap:0 28px;max-width:none}
.alist-2col .al-th{width:110px;height:72px}
.alist-2col .al-t{font-size:.9rem;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
@media(max-width:760px){.alist-2col{grid-template-columns:1fr}}
@media(max-width:560px){
  .al-th{width:104px;height:74px}
  .al-t{font-size:.88rem}
  .al-s{display:none}
}
/* default rail: featured-article card */
.mp-feat{display:flex;flex-direction:column;gap:8px;text-decoration:none;margin-bottom:14px}
.mp-feat-img{width:100%;aspect-ratio:16/10;object-fit:cover;border-radius:10px;display:block}
.mp-feat-t{font-size:.92rem;font-weight:900;color:var(--ink);line-height:1.5}
.mp-feat-cta{font-size:.78rem;font-weight:800;color:var(--green-d, #15658f)}
.mp-feat:hover .mp-feat-t{color:#15658f}
@media(max-width:1080px){.mpage.league-view .mp-extra{display:block}}
@media(max-width:1080px){.mpage{grid-template-columns:210px minmax(0,1fr)}.mp-extra{display:none}}
@media(max-width:760px){
  .mpage{grid-template-columns:minmax(0,1fr);gap:10px}
  .mp-leagues{position:static;padding:8px 10px}
  .mp-leagues .mp-h{display:none}
  /* all leagues visible at once (3 per row) - no hidden horizontal scroll */
  .lg-list{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:6px}
  .lg-item{justify-content:center;gap:5px;padding:8px 4px;border:1px solid #e6ebf1;border-radius:10px;
    font-size:.74rem;line-height:1.25;text-align:center;min-width:0}
  .lg-name{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0}
  .lg-logo,.lg-ico{width:18px;height:18px;font-size:.95rem}
}
.mlist{display:flex;flex-direction:column;gap:8px;margin-bottom:16px}
.mrow{position:relative;display:grid;grid-template-columns:auto 1fr auto 1fr;grid-template-areas:"pill home mid away";gap:8px 10px;align-items:center;background:#fff;border:1px solid #e2e8f0;border-radius:12px;border-inline-start:5px solid var(--green);padding:12px 16px;box-shadow:0 1px 3px rgba(15,23,42,.05)}
/* stretched link -> the whole row opens the match page (/m/<id>.html) */
.mstretch{position:absolute;inset:0;z-index:1;border-radius:12px}
.mrow:has(.mstretch):hover{border-color:#94a3b8;box-shadow:0 2px 8px rgba(15,23,42,.12)}
/* per-match page (/m/<id>.html) */
.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}
/* تحليلات */
.an-nav{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0 16px}
.an-nav a{display:inline-flex;align-items:center;gap:6px;background:#fff;border:1px solid #e2e8f0;border-radius:999px;padding:5px 12px;font-weight:800;font-size:.85rem;color:var(--ink);text-decoration:none}
.an-nav a:hover{border-color:var(--green);color:var(--green-d)}
.an-nav .lg-logo,.an-comp .lg-logo{width:18px;height:18px;object-fit:contain}
.an-comp{display:flex;align-items:center;gap:6px;font-size:1rem;margin:16px 0 8px}
.an-comp a{color:var(--ink);text-decoration:none}
.plist{display:flex;flex-direction:column;gap:8px}
.prow{display:grid;grid-template-columns:96px 1fr 268px;grid-template-areas:"when teams bar" "when meta bar";gap:4px 14px;align-items:center;background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;padding:10px 12px;text-decoration:none;color:var(--ink)}
.prow:hover{border-color:var(--green)}
.pr-when{grid-area:when;font-size:.8rem;font-weight:800;color:var(--muted)}
.pr-teams{grid-area:teams;display:flex;align-items:center;gap:8px;font-weight:900;min-width:0}
.pr-t{display:inline-flex;align-items:center;gap:6px;min-width:0}
.pr-t img{width:22px;height:22px;object-fit:contain}
/* the two clubs in a prediction row wear their own segments' colours, the
   same way the popup head does, so the name, the slice and the label under
   it all agree instead of the name being the one neutral thing in the row */
.pr-teams>.pr-t:first-child bdi{color:var(--green)}
.pr-teams>.pr-t:last-child bdi{color:#334155}
.pr-vs{color:var(--muted);font-weight:600}
.prow .pr-bw{grid-area:bar;display:flex;flex-direction:column;gap:5px;min-width:0}
.prow .pr-probs{display:flex;flex-wrap:wrap;gap:0 10px;font-size:.72rem;line-height:1.6}
.prow .pr-probs .prb+.prb{margin-inline-start:0}
.pr-meta{grid-area:meta;display:flex;flex-wrap:wrap;gap:6px 14px;font-size:.78rem;color:var(--muted);font-weight:700}
/* RTL, like everything else on the page: the HOME segment sits on the
   right, under the home club's name, and the away segment on the left.
   This carried direction:ltr from the days when the percentages were
   printed INSIDE the segments; those moved out to prob_legend on
   2026-09-16 and the override was left behind, quietly putting the home
   side on the wrong end of its own bar (user, 2026-09-18). */
.pbar{display:flex;height:22px;border-radius:6px;overflow:hidden;background:#e2e8f0;direction:rtl}
.pb-seg{display:flex;align-items:center;justify-content:center;font-size:.72rem;color:#fff;min-width:0}
.pb-h{background:var(--green)}.pb-d{background:#94a3b8}.pb-a{background:#334155}
.pred-rec{display:block;margin:0 0 8px;padding:9px 12px;border-radius:10px;
  /* #475569, not var(--muted): the muted grey reads 4.34 against this pill's
     #f1f5f9 and WCAG AA wants 4.5 - the one contrast failure on the site
     (Lighthouse 2026-09-22) */
  background:#f1f5f9;color:#475569;font-size:.83rem;line-height:1.75;font-weight:600}
.pred-rec b{color:var(--text);font-weight:800}
.pr-probs .prb,.pd-probs .prb{white-space:nowrap}
.pr-probs .prb+.prb,.pd-probs .prb+.prb{margin-inline-start:10px}
.pr-probs i,.pd-probs i{display:inline-block;width:9px;height:9px;border-radius:2px;
  margin-inline-end:5px}
.prb-h{background:var(--green)}.prb-d{background:#94a3b8}.prb-a{background:#334155}
/* Each label wears its own segment's colour, so the eye pairs the word with
   the slice instead of hunting for the swatch (user, 2026-09-18). :has()
   keeps this in CSS - the markup already says which segment a label belongs
   to, in the popup where the label is a CLUB NAME and on /analysis and /m/
   where it is الأرض/تعادل/الضيف. A browser without :has() just gets the old
   ink colour, which is why the swatch stays. The percentage inherits it. */
.prb:has(.prb-h){color:var(--green)}
.prb:has(.prb-d){color:#94a3b8}
.prb:has(.prb-a){color:#334155}
.pd-probs{color:var(--muted);font-weight:700;font-size:.88rem}
.conf{display:inline-block;border-radius:999px;padding:1px 8px;font-size:.72rem;font-weight:800}
.conf-low{background:#fef3c7;color:#92400e}.conf-mid{background:#e0f2fe;color:#075985}.conf-high{background:#dcfce7;color:#166534}
.predict .pd-heads{display:flex;justify-content:space-between;font-weight:800;font-size:.9rem;margin-bottom:6px}
.predict .pd-heads b{color:var(--green-d)}
.pd-line{margin:8px 0;line-height:1.8}
.why-list{margin:10px 0 0;padding-inline-start:20px;line-height:1.95}
.why-list li{margin:6px 0}
.why-list b{color:var(--green-d)}
.pd-facts{color:var(--muted);font-size:.88rem;line-height:1.8}
.pd-note{color:var(--muted);font-size:.8rem;line-height:1.7;margin:10px 0 0}
.hit{font-weight:900;border-radius:6px;padding:1px 8px}.hit.ok{background:#dcfce7;color:#166534}.hit.no{background:#fee2e2;color:#991b1b}
.tbl-wrap{overflow-x:auto}
.ptable{width:100%;border-collapse:collapse;font-size:.88rem}
.ptable th,.ptable td{padding:7px 8px;text-align:center;border-bottom:1px solid #eef2f6;white-space:nowrap}
.ptable th{color:var(--muted);font-weight:800;font-size:.78rem}
.ptable .tl{text-align:start}
.ptable td.tl img{width:20px;height:20px;object-fit:contain;vertical-align:middle;margin-inline-end:6px}
.ptable td.good{color:#166534;font-weight:800}.ptable td.bad{color:#991b1b;font-weight:800}
.tbl-wrap h3,.timing h3{font-size:.95rem;margin:14px 0 8px}
.pw-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px}
.pw-card{background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;padding:10px 14px}
.pw-card h3{display:flex;align-items:center;gap:6px;font-size:.92rem;margin:0 0 6px}
.pw-card ol{margin:0;padding-inline-start:18px;font-size:.88rem;line-height:1.9}
.pw-card li b{color:var(--green-d);float:left}
.pw-card a{display:block;margin-top:6px;font-size:.8rem;font-weight:800;color:var(--green-d);text-decoration:none}
.acc-tiles{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px;margin-bottom:10px}
.tile{background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;padding:10px;text-align:center}
.tile b{display:block;font-size:1.4rem;color:var(--green-d)}
.tile b.sc-in{display:inline-flex}   /* a score tile keeps the pill's ordering */
.tile span{font-size:.74rem;color:var(--muted);font-weight:700}
.acc-list{margin:0;padding-inline-start:18px;line-height:1.9;font-size:.9rem}
.timing .tb{display:grid;grid-template-columns:64px 1fr 84px;align-items:center;gap:8px;margin:4px 0;font-size:.85rem}
.tb-bar{height:14px;background:#e2e8f0;border-radius:4px;overflow:hidden}
.tb-bar i{display:block;height:100%;background:var(--green)}
.tb-v{font-weight:800}.tb-v small{color:var(--muted);font-weight:600}
.explain ol{padding-inline-start:20px;line-height:1.9}.explain p{line-height:1.9}
.absences .abs-club{border-top:1px solid #eef2f6;padding:8px 0}
.absences .abs-club:first-of-type{border-top:0}
.absences h3{font-size:.95rem;margin:0 0 4px;color:var(--green-d)}
.absences p{margin:4px 0;line-height:1.9}
.absences small{color:var(--muted);font-weight:600}
.more-link{font-weight:800;margin:8px 0}
@media (max-width:640px){
  .prow{grid-template-columns:1fr;grid-template-areas:"when" "teams" "bar" "meta";gap:6px}
  .pr-when{font-size:.75rem}
}
.st-analysis p,.faq p{line-height:1.9;margin:8px 0}
.st-analysis a{font-weight:800;color:var(--green-d);text-decoration:none}
.faq details,.a-faq details{border-top:1px solid #e2e8f0;padding:8px 0}
.faq details:first-of-type,.a-faq details:first-of-type{border-top:0}
.faq summary,.a-faq summary{cursor:pointer;font-weight:800;color:var(--ink)}
.marticle .a-body{line-height:1.95}
.marticle .a-fig{margin:12px 0}
.marticle .a-sources,.marticle .a-faq{margin:18px 0 0;padding-top:12px;border-top:1px solid #e2e8f0}
.marticle .a-sources h3,.marticle .a-faq h3{font-size:.98rem;margin:0 0 8px}
.marticle .a-sources ul{margin:0;padding-inline-start:18px}
.marticle .a-sources li{margin:4px 0;font-size:.9rem}
.a-sources,.a-faq{margin:22px 0 0;padding-top:14px;border-top:1px solid #e2e8f0}
.a-sources h2,.a-faq h2{font-size:1.05rem;margin:0 0 8px}
.a-sources ul{margin:0;padding-inline-start:18px}
.a-sources li{margin:4px 0;font-size:.92rem}
.a-embeds{margin:22px 0 0;padding-top:14px;border-top:1px solid #e2e8f0}
.a-embeds h2{font-size:1.05rem;margin:0 0 4px}
.a-embeds .hintline{margin:0 0 10px;font-size:.8rem}
.emb{border:1px solid #e2e8f0;border-radius:12px;padding:12px 14px;margin:10px 0;background:#f8fafc}
.emb-h{display:flex;align-items:center;gap:8px;font-size:.95rem}
.emb-ico{display:inline-block;width:14px;height:14px;border-radius:3px;background:#0f172a}
.emb-instagram{background:#c13584}.emb-facebook{background:#1877f2}
.emb-l{display:block;direction:ltr;text-align:left;font-size:.82rem;color:var(--muted);margin:6px 0 10px;word-break:break-all;text-decoration:none}
.emb-l:hover{text-decoration:underline}
.emb-b{background:var(--green);color:#fff;border:0;border-radius:8px;padding:8px 14px;font-weight:800;cursor:pointer;font-family:inherit}
.emb-b:hover{background:var(--green-d)}
.emb-box{margin-top:10px;display:flex;justify-content:center}
.related{max-width:860px}
.related .mp-newslist li{margin:7px 0;line-height:1.6}
.related .mp-newslist a{font-weight:800;color:var(--ink);text-decoration:none}
.related .mp-newslist a:hover{color:var(--green-d)}
.crumbs{font-size:.8rem;color:var(--muted);margin:10px 0}
.crumbs a{color:var(--muted)}
.minfo{background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:14px 18px;margin:14px 0}
.minfo h2{font-size:1.05rem;margin:0 0 10px}
.minfo-l{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:8px 18px;margin:0}
.minfo-l div{display:flex;gap:6px}
.minfo-l dt{color:var(--muted);font-weight:600;white-space:nowrap}
.minfo-l dt::after{content:":"}
.minfo-l dd{margin:0;font-weight:700}
.mp-newslist{margin:0;padding-inline-start:18px}
.mp-newslist li{margin:5px 0}
/* club pages (/team/<slug>) */
.club-hero{display:flex;align-items:center;gap:16px;background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:16px 18px;margin:14px 0}
.club-crest{width:64px;height:64px;object-fit:contain;flex:none}
.club-hero .page-h{margin:0 0 4px}
.club-hero .hintline{margin:0}
.club-pos{margin:6px 0 0;font-size:.85rem;color:var(--green-d);font-weight:700}
.club-pos b{font-size:1rem}
.club-when{color:var(--muted);font-size:.78rem}
.club-chips{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin:14px 0;font-size:.85rem}
.club-chips span{color:var(--muted);font-weight:700}
.club-chips a{background:#fff;border:1px solid #e2e8f0;border-radius:999px;padding:4px 12px;font-weight:800;color:var(--ink);text-decoration:none}
.club-chips a:hover{border-color:var(--green);color:var(--green-d)}
@media(max-width:560px){.club-crest{width:48px;height:48px}.club-hero{gap:12px;padding:12px}}
.mrow-live{border-inline-start-color:var(--live)}.mrow-fin{border-inline-start-color:var(--fin)}
.pill{grid-area:pill;color:#fff;background:var(--up);border-radius:999px;padding:2px 12px;font-size:.68rem;font-weight:900}
.pill-live{background:var(--live)}.pill-fin{background:var(--fin)}
.team{display:flex;align-items:center;gap:8px;font-weight:800;min-width:0}
/* explicit th/ta classes: :first/last-of-type broke whenever .mcomp/.mgoals (also divs) followed the away team - it lost its area and auto-placed into the empty pill cell (team pages, 2026-09-02) */
.team.th{grid-area:home;justify-content:flex-end;text-align:end}
.team.ta{grid-area:away}
.team img{width:34px;height:34px;object-fit:contain}
.team .ph{font-size:1.4rem}
.mid{grid-area:mid;text-align:center;min-width:74px}
.score{font-size:1.5rem;font-weight:900}.ko{font-weight:800;color:var(--green-d)}
.mcomp{grid-column:1/-1;color:var(--muted);font-size:.78rem;font-weight:700;text-align:center;border-top:1px solid #eef2f6;padding-top:8px}
/* mobile: symmetric stacked teams (crest above name), pill pinned top corner */
@media(max-width:560px){
  .mrow{grid-template-columns:1fr auto 1fr;grid-template-areas:"home mid away";position:relative;padding:12px 8px}
  .mrow:has(.pill){padding-top:30px}                 /* room for the corner badge only when present */
  .pill{position:absolute;top:8px;inset-inline-start:10px;grid-area:auto}
  .team,.team.th,.team.ta{grid-area:auto;flex-direction:column;justify-content:flex-start;text-align:center;gap:4px;font-size:.76rem;line-height:1.35;min-width:0}
  .team.th{grid-area:home}
  .team.ta{grid-area:away}
  .team>span{min-width:0;max-width:100%;overflow-wrap:anywhere}   /* long names wrap, never overflow */
  .team img{width:30px;height:30px}
  .mid{min-width:52px}
  .score{font-size:1.2rem}
}
/* matches per-day navigator */
.daynav{display:flex;align-items:center;justify-content:space-between;gap:12px;max-width:820px;margin:6px auto 14px;background:#fff;border:1px solid #e2e8f0;border-radius:999px;padding:6px 10px;box-shadow:0 2px 8px rgba(15,23,42,.06);position:sticky;top:112px;z-index:5}
.dn-arrow{flex:0 0 auto;width:40px;height:40px;border:0;border-radius:50%;background:var(--green);color:#fff;font-size:1.5rem;font-weight:900;line-height:1;cursor:pointer}
.dn-arrow:hover{background:var(--green-d)}
.dn-arrow:disabled{opacity:.4;cursor:default}
.dn-label{flex:1 1 auto;text-align:center;font-weight:900;font-size:1.05rem;color:var(--ink)}
/* FotMob-style filter bar under the day navigator */
.mfilters{display:flex;align-items:center;gap:8px;max-width:820px;margin:-4px auto 14px;padding:2px;overflow-x:auto;scrollbar-width:none}
.mfilters::-webkit-scrollbar{display:none}
.mfilters[hidden]{display:none}
.mf-chip{flex:0 0 auto;display:inline-flex;align-items:center;gap:7px;border:1px solid #e2e8f0;background:#fff;border-radius:999px;padding:7px 14px;font:inherit;font-weight:800;font-size:.85rem;color:var(--ink);cursor:pointer;white-space:nowrap;transition:background .12s,color .12s,border-color .12s}
.mf-chip:hover{border-color:var(--green)}
.mf-chip.is-on{background:var(--green);border-color:var(--green);color:#fff}
.mf-dot{width:9px;height:9px;border-radius:50%;background:#cbd5e1}
.mf-chip.is-on .mf-dot{background:#fff;box-shadow:0 0 0 3px rgba(255,255,255,.35)}
.mf-search{flex:1 1 170px;min-width:130px;display:flex;align-items:center;gap:7px;border:1px solid #e2e8f0;background:#fff;border-radius:999px;padding:6px 12px;color:var(--muted)}
.mf-search:focus-within{border-color:var(--green)}
.mf-search input{border:0;outline:0;flex:1 1 auto;min-width:0;font:inherit;font-weight:700;background:transparent;color:var(--ink)}
.mf-search input::-webkit-search-cancel-button{cursor:pointer}
.bytime{max-width:820px;margin:0 auto 16px}
@media(max-width:560px){.mf-chip{padding:6px 11px;font-size:.78rem}.mf-search{flex-basis:140px}}
.day{max-width:820px;margin:0 auto}
.day-h{color:var(--green-d);font-weight:900;margin:16px 0 10px}
.comp-h{font-weight:800;color:var(--muted);font-size:.8rem;text-transform:uppercase;letter-spacing:.5px;margin:14px 4px 6px}
.home-topad{margin:16px 0 18px}
.mp-main .home-topad{margin-top:0}  /* align with the rails' top on /matches */
.home-topad .ad-placeholder,.home-topad .ad-unit{position:static;min-height:130px;flex-direction:row}
/* FotMob-style home blocks: featured card + numbered trending list */
.fmb{display:grid;grid-template-columns:1.15fr 1fr;gap:20px;background:#fff;border:1px solid #e2e8f0;border-radius:16px;padding:16px;margin:0 0 18px}
.fmb-feat{display:flex;flex-direction:column;text-decoration:none;color:var(--ink);border-radius:12px;overflow:hidden;background:#f8fafc;border:1px solid #eef2f6}
.fmb-banner{background:linear-gradient(135deg,var(--green-d),var(--green));color:#fff;font-weight:900;padding:10px 14px;font-size:.95rem}
.fmb-img{aspect-ratio:16/9;background-size:cover;background-position:50% 25%}
.fmb-noimg{background:linear-gradient(135deg,var(--green),#0d3e59)}
.fmb-fb{padding:12px 14px 14px}
.fmb-fb h2{margin:0 0 8px;font-size:1.3rem;line-height:1.5;font-weight:900}
.fmb-feat:hover h2{color:var(--green-d)}
.fmb-meta{margin:0;color:var(--muted);font-size:.78rem;font-weight:700}
.fmb-list{display:flex;flex-direction:column;min-width:0}
.fmb-lh{font-weight:900;font-size:.95rem;padding-bottom:4px}
/* «آخر الأخبار» title + FotMob-style round filter chips */
/* one row: title, chips, follow pill at the END (left in RTL). Under 560px the
   chips drop to their own second row so the pill stays on the TITLE row. */
.nf-bar{display:flex;align-items:center;justify-content:flex-start;gap:16px;flex-wrap:nowrap}
/* mobile (user 2026-09-04): title, chips AND the pill on ONE row — shrink
   everything instead of wrapping; the title never breaks */
@media(max-width:560px){.nf-bar{gap:10px}.nf-bar .page-h{font-size:1.45rem;white-space:nowrap}.nf-chips{gap:8px}}
.nf-bar .page-h{margin:0}
.nf-chips{display:flex;align-items:center;gap:10px}
/* Facebook follow pill — pushed to the row END (left in RTL) */
.nf-fb,.nf-tg{display:inline-flex;align-items:center;justify-content:center;height:44px;width:44px;border-radius:50%;color:#fff;text-decoration:none;box-shadow:0 1px 3px rgba(15,23,42,.12);transition:transform .12s,background .12s;flex:none}
.nf-fb{margin-inline-start:auto;background:#1877f2}
.nf-fb:hover{background:#166fe5;transform:translateY(-1px)}
.nf-tg{margin-inline-start:8px;background:#229ed9}
.nf-tg:hover{background:#1c8dc3;transform:translateY(-1px)}
@media(max-width:560px){.nf-fb,.nf-tg{height:36px;width:36px}.nf-fb svg,.nf-tg svg{width:19px;height:19px}}
/* /editors.html — editor card */
.ed-card{border:1px solid #e2e8f0;border-radius:14px;padding:16px 18px;background:#f8fafc;margin:8px 0 18px}
.ed-name{font-weight:900;font-size:1.25rem;color:var(--green-d)}
.ed-role{color:#64748b;font-weight:700;margin-bottom:8px}
.ed-contact{margin:6px 0 0;font-size:.95rem}
.a-by{color:inherit;text-decoration:none;font-weight:800}.a-by:hover{text-decoration:underline}
.nf-chip{width:44px;height:44px;border-radius:50%;border:1px solid #e2e8f0;background:#fff;display:inline-flex;align-items:center;justify-content:center;padding:0;cursor:pointer;box-shadow:0 1px 3px rgba(15,23,42,.06);transition:transform .12s,border-color .12s,box-shadow .12s}
.nf-chip:hover{transform:translateY(-2px);border-color:var(--green)}
.nf-chip.is-on{border:2px solid #fff;background:#eaf3fa;box-shadow:0 0 0 3px rgba(31,148,211,.35)}   /* white ring inside the blue glow (user 2026-09-02) */
.nf-chip img,.nf-chip svg{width:22px;height:22px;object-fit:contain;display:block}
@media(max-width:560px){.nf-chip{width:36px;height:36px;flex:none}.nf-chip svg{width:19px;height:19px}}
/* flex:1 = the rows share the column's full height equally, so the list
   always bottoms out level with the featured card (no dead space under
   row 4 when the featured card runs tall) */
.fmb-row{display:flex;align-items:center;gap:10px;padding:10px 0;border-bottom:1px solid #eef2f6;text-decoration:none;color:var(--ink);min-width:0;flex:1}
.fmb-row:last-of-type{border-bottom:0}
.fmb-row:hover b{color:var(--green-d)}
.fmb-num{width:20px;height:20px;border-radius:50%;background:var(--green);color:#fff;font-size:.68rem;font-weight:900;display:flex;align-items:center;justify-content:center;flex:none}
.fmb-rt{display:flex;flex-direction:column;gap:3px;min-width:0;flex:1}
.fmb-rt b{font-size:.85rem;line-height:1.5;font-weight:800;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.fmb-rt small{color:var(--muted);font-size:.72rem;font-weight:700}
.fmb-th{width:88px;height:58px;object-fit:cover;border-radius:8px;flex:none;background:#eef2f6}
.fmb-more{margin-top:auto;padding-top:10px;font-size:.82rem;font-weight:800;color:var(--green-d);text-decoration:none}
.fmb-more:hover{text-decoration:underline}
.fmb-pred{display:block}
.fmb-predh{display:flex;align-items:baseline;justify-content:space-between;gap:10px;flex-wrap:wrap;padding-bottom:10px}
.fmb-predh small{font-weight:700;color:var(--muted);font-size:.75rem}
.fmb-pred .fmb-more{display:inline-block;margin-top:12px}
/* flipped variant: featured card LEFT, list RIGHT (visual alternation) */
.fmb-flip{grid-template-columns:1fr 1.15fr}
.fmb-flip .fmb-list{grid-column:1;grid-row:1}
.fmb-flip .fmb-feat{grid-column:2;grid-row:1}
@media(max-width:860px){.fmb{grid-template-columns:1fr;gap:12px;padding:12px}.fmb-fb h2{font-size:1.05rem}.fmb-th{width:76px;height:52px}
  .fmb-flip .fmb-feat,.fmb-flip .fmb-list{grid-column:auto;grid-row:auto}}
/* «توقع يلا سكور» — the button on an upcoming match row, and its popup.
   z-index:2 puts the button above .mstretch (z-index:1), which otherwise
   covers the whole row and would swallow the click. */
.pbtn-row{grid-column:1/-1;display:flex;justify-content:center;
  margin-top:7px;padding-top:7px;border-top:1px solid #eef2f6}
.pbtn{position:relative;z-index:2;font:inherit;font-size:.74rem;font-weight:800;
  color:var(--green-d);background:#f1f7fb;border:1px solid #d7e7f2;
  border-radius:999px;padding:3px 14px;cursor:pointer}
.pbtn:hover{background:var(--green);border-color:var(--green);color:#fff}
.ppop{border:0;border-radius:16px;padding:0;max-width:340px;
  width:calc(100% - 32px);color:var(--ink);
  box-shadow:0 12px 40px rgba(15,23,42,.28)}
.ppop::backdrop{background:rgba(15,23,42,.45)}
/* Safari < 15.4 has no showModal(): the script falls back to the open
   attribute, which renders the dialog in flow — this re-centres it. */
.ppop-open{position:fixed;top:50%;inset-inline-start:50%;
  transform:translate(50%,-50%);z-index:50}
.ppop-in{padding:14px 18px 16px}
.ppop-hd{display:flex;align-items:center;justify-content:space-between;gap:10px}
.ppop h3{margin:0;font-size:1rem;color:var(--green-d)}
.ppop-x{border:0;background:none;font-size:1.4rem;line-height:1;
  color:var(--muted);cursor:pointer;padding:0 2px}
.ppop-t{margin:8px 0 10px;font-weight:900;font-size:.95rem}
/* the two names in the head take their own segment colours as well, so the
   header line and the legend under the bar agree at a glance instead of
   saying the same thing in two different colours (user, 2026-09-18) */
.ppop-nh{color:var(--green)}
.ppop-na{color:#334155}
.ppop-t span{color:var(--muted);font-weight:600;margin:0 4px}
.ppop .pbar{height:18px}
.ppop-probs{margin:8px 0 0;font-size:.78rem;line-height:1.9}
/* one per line: .prb is nowrap, and three full club names do not fit the
   340px box side by side */
.ppop-probs .prb{display:block}
.ppop-probs .prb+.prb{margin-inline-start:0}
.ppop-m{display:flex;flex-wrap:wrap;align-items:center;gap:8px;
  margin:10px 0 0;font-size:.85rem;font-weight:800}
.ppop-res{margin:10px 0 0;font-size:.95rem;font-weight:900}
.ppop-res b{font-size:1.05rem}
.ppop-s{margin:6px 0 0;font-size:.85rem;color:var(--muted);font-weight:700}
.ppop-s b{color:var(--ink);font-size:.95rem}
.ppop-d{margin:10px 0 0;font-size:.7rem;line-height:1.7;color:var(--muted)}
.ppop-go,.ppop-rec{display:inline-block;margin-top:10px;font-size:.82rem;
  font-weight:800;color:var(--green-d);text-decoration:none}
.ppop-rec{margin-inline-start:14px;color:var(--muted)}
.ppop-go:hover,.ppop-rec:hover{text-decoration:underline}
/* scorers under a finished/live match row (/matches day view) */
.mgoals{grid-column:1/-1;display:grid;grid-template-columns:1fr 40px 1fr;gap:2px 6px;
  margin-top:7px;padding-top:6px;border-top:1px dashed #e8eef4}
.mg-side{display:flex;flex-direction:column;gap:2px;min-width:0;text-align:center}
.mg{font-size:.7rem;color:var(--muted);font-weight:700;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.mg bdi{color:var(--ink)}
.mg-m{font-style:normal;direction:ltr;unicode-bidi:embed;color:#15658f}
.mg small{font-size:.62rem}
@media(max-width:560px){.mgoals{grid-template-columns:1fr 20px 1fr}.mg{font-size:.66rem}}
/* match details: events timeline + starting lineups (/m/<id>.html).
   NOT «.tl» - that collided with the .tl text-start cells in every
   .ptable (standings, scorers, ratings, the prediction record) and
   turned those cells into flex boxes, which drops them out of the
   table layout entirely. Measured 2026-09-16. */
.mtl{display:flex;flex-direction:column}
.tl-r{display:grid;grid-template-columns:1fr 52px 1fr;gap:6px;align-items:center;
  font-size:.85rem;padding:5px 0;border-bottom:1px solid #f1f5f9}
.tl-r:last-child{border-bottom:0}
.tl-h{text-align:end;font-weight:700;min-width:0}
.tl-a{text-align:start;font-weight:700;min-width:0}
.tl-m{text-align:center;color:var(--muted);font-weight:900;font-size:.78rem}
.cardic{display:inline-block;width:11px;height:15px;border-radius:2px;vertical-align:-2px}
.cardic.y{background:#fbbf24}.cardic.r{background:#dc2626}
.sub-in{color:#15803d;font-weight:800}
.sub-out{color:#b91c1c;font-weight:600;font-size:.8em}
.ev-tag{color:var(--muted);font-size:.75em}
.lu{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.lu-t{min-width:0}
.lu-t h3{font-size:.95rem;margin:0 0 8px;display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.lu-f{color:var(--muted);font-weight:800;font-size:.78em;background:#eef2f6;border-radius:999px;padding:2px 10px}
.lu-l{list-style:none;margin:0;padding:0}
.lu-l li{display:flex;align-items:center;gap:8px;padding:4px 0;font-size:.85rem;font-weight:600;border-bottom:1px solid #f1f5f9;min-width:0}
.lu-l li:last-child{border-bottom:0}
.lu-l li bdi{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0}
.lu-n{flex:0 0 26px;text-align:center;background:#eef2f6;border-radius:6px;font-size:.72rem;font-weight:900;color:var(--green-d);padding:2px 0}
.lu-p{color:var(--muted);font-size:.7em;font-weight:600;margin-inline-start:auto;white-space:nowrap}
.lu-none{color:var(--muted);font-size:.85rem}
/* sofascore-style pitch lineup — vertical on mobile, horizontal on desktop
   (the desktop media block just swaps each player's --xv/--yv coordinates) */
.pitch{position:relative;max-width:460px;margin:0 auto;aspect-ratio:10/16;
  border-radius:10px;overflow:hidden;
  background-image:repeating-linear-gradient(to bottom,rgba(255,255,255,.05) 0 12.5%,rgba(0,0,0,0) 12.5% 25%),linear-gradient(#2c8f4e,#237a41)}
.pt-half{position:absolute;left:0;right:0;top:50%;border-top:2px solid rgba(255,255,255,.45)}
.pt-circle{position:absolute;left:50%;top:50%;width:22%;aspect-ratio:1;border:2px solid rgba(255,255,255,.45);
  border-radius:50%;transform:translate(-50%,-50%)}
.pt-box{position:absolute;left:50%;width:46%;height:11%;transform:translateX(-50%);
  border:2px solid rgba(255,255,255,.45)}
.pt-box-t{top:-2px;border-top:0}.pt-box-b{bottom:-2px;border-bottom:0}
.pt-lab{position:absolute;display:flex;align-items:center;gap:6px;font-weight:900;font-size:.72rem;
  color:#fff;text-shadow:0 1px 3px rgba(0,0,0,.8);z-index:2;max-width:46%}
.pt-lab bdi{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.pt-lab .lu-f{background:rgba(10,61,28,.75);color:#fff}
.pt-lab-h{top:6px;left:8px}
.pt-lab-a{bottom:6px;right:8px}
.pp{position:absolute;left:var(--xv);top:var(--yv);transform:translate(-50%,-50%);
  display:flex;flex-direction:column;align-items:center;gap:2px;width:76px;pointer-events:none}
@media(min-width:760px){
  .pitch{aspect-ratio:16/10;max-width:840px;
    background-image:repeating-linear-gradient(to right,rgba(255,255,255,.05) 0 12.5%,rgba(0,0,0,0) 12.5% 25%),linear-gradient(#2c8f4e,#237a41)}
  .pitch .pp{left:var(--yv);top:var(--xv)}
  .pt-half{top:0;bottom:0;left:50%;right:auto;border-top:0;border-left:2px solid rgba(255,255,255,.45)}
  .pt-box{width:11%;height:46%;top:50%;transform:translateY(-50%)}
  .pt-box-t{left:-2px;right:auto;border:2px solid rgba(255,255,255,.45);border-left:0}
  .pt-box-b{left:auto;right:-2px;bottom:auto;border:2px solid rgba(255,255,255,.45);border-right:0}
}
.pp-ava{position:relative;width:40px;height:40px;background:#fff;border-radius:50%;
  display:flex;align-items:center;justify-content:center;box-shadow:0 1px 4px rgba(0,0,0,.35)}
.pp-ava img{width:36px;height:36px;border-radius:50%;object-fit:cover;object-position:top}
.pp-fb{display:none;width:36px;height:36px;border-radius:50%;background:#eef2f6;
  align-items:center;justify-content:center;font-weight:900;font-size:.8rem;color:var(--green-d)}
.pp-nm{max-width:76px;font-size:.62rem;font-weight:800;color:#fff;text-shadow:0 1px 2px rgba(0,0,0,.7);
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap;text-align:center}
.pp-rt{position:absolute;top:-6px;right:-10px;font-size:.6rem;font-weight:900;color:#fff;
  border-radius:6px;padding:1px 4px;direction:ltr}
.pp-rt.r8{background:#0ea5e9}.pp-rt.r7{background:#16a34a}
.pp-rt.r65{background:#ca8a04}.pp-rt.r6{background:#ea580c}
/* «قراءة المباراة» (post-match reading): the story paragraph, the rating
   chips and the table line. Same .minfo card as every other section - the
   reading is content, not a widget. */
.mread p{line-height:1.9;margin:.4rem 0}
.mread .mr-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
  gap:.5rem;margin:.7rem 0}
.mread .mr-c{display:flex;align-items:center;gap:.45rem;background:#f6f8fa;
  border:1px solid #e2e8f0;border-radius:10px;padding:.5rem .6rem;position:relative}
.mread .mr-l{position:absolute;top:-.55rem;inset-inline-start:.6rem;font-size:.62rem;
  background:var(--card);padding:0 .3rem;color:var(--muted)}
.mread .mr-c b{font-size:.85rem;line-height:1.2}
.mread .mr-c small{color:var(--muted);font-size:.7rem;margin-inline-start:auto;
  padding-inline-end:.3rem}
.rt-b{font-size:.78rem;font-weight:900;color:#fff;border-radius:6px;padding:.12rem .34rem;
  min-width:2.1rem;text-align:center;direction:ltr}
.rt-b.r8{background:#0ea5e9}.rt-b.r7{background:#16a34a}
.rt-b.r65{background:#ca8a04}.rt-b.r6{background:#ea580c}
.mread .mr-avg small{color:var(--muted);font-weight:400}
/* prediction record (/predictions.html): filter bar, the two call columns,
   and the small-sample flag. Tables reuse .ptable. */
.pf-bar{display:flex;align-items:center;gap:.4rem;flex-wrap:wrap;margin:.6rem 0}
.pf-chip{cursor:pointer;border:1px solid #e2e8f0;background:#f6f8fa;border-radius:999px;
  padding:.28rem .7rem;font-size:.8rem;font-weight:800;color:var(--ink)}
.pf-chip.on{background:var(--green);border-color:var(--green);color:#fff;
  box-shadow:0 0 0 2px #fff inset}
.pf-bar select{border:1px solid #e2e8f0;border-radius:8px;padding:.28rem .5rem;
  font-family:inherit;font-size:.8rem;font-weight:700;background:#fff;color:var(--ink)}
.pf-n{color:var(--muted);font-size:.78rem;font-weight:700;margin-inline-start:auto}
.pf-small{color:var(--muted);font-size:.65rem;font-weight:700;background:#f1f5f9;
  border-radius:6px;padding:.05rem .3rem;white-space:nowrap}
.pf-exact{font-size:.8rem}
/* the record itself: a day-grouped list, not a six-column table. The verdict
   sits at the RTL start so it is the first thing read; the date is a group
   header instead of a column repeated on every line (user, 2026-09-16). */
.rec{border:1px solid #e6ecf2;border-radius:12px;overflow:hidden;background:#fff}
.rec-day{background:#f1f5f9;color:#41525f;font-weight:800;font-size:.76rem;
  padding:.35rem .8rem;border-block:1px solid #e6ecf2}
.rec-day:first-child{border-top:0}
.rec-i{display:flex;align-items:center;gap:.6rem;padding:.5rem .7rem;
  border-bottom:1px solid #f1f5f9;text-decoration:none;color:inherit}
.rec-i:last-child{border-bottom:0}
.rec-i:hover{background:#f8fafc}
.rec-v{flex:0 0 auto;width:22px;height:22px;border-radius:50%;display:grid;
  place-items:center;font-size:.78rem;font-weight:900}
.rec-i.ok .rec-v{background:#dcfce7;color:#166534}
.rec-i.no .rec-v{background:#fee2e2;color:#991b1b}
.rec-m{flex:1 1 auto;min-width:0}
.rec-t{display:block;font-weight:800;font-size:.92rem;white-space:nowrap;
  overflow:hidden;text-overflow:ellipsis}
.rec-s{display:block;color:var(--muted);font-size:.76rem;margin-top:.1rem}
.rec-s b{color:var(--ink);font-weight:800}
.rec-s i{font-style:normal}
.rec-s .sc-s{font-size:.76rem;font-weight:800;color:var(--ink);margin-inline:2px}
.rec-c{flex:0 0 auto;color:var(--muted);font-size:.74rem;font-weight:700}
.rec-lg{display:none}
.rec-none{color:var(--muted);font-size:.85rem;text-align:center;padding:.8rem 0}
@media(max-width:620px){
  .rec-c{display:none}
  .rec-lg{display:inline}
  .rec-t{font-size:.86rem}
}
.pf-more{display:block;width:100%;margin:.5rem 0 0;padding:.55rem;border:1px solid #e2e8f0;
  background:#f6f8fa;border-radius:10px;font-family:inherit;font-size:.85rem;font-weight:800;
  color:var(--green-d);cursor:pointer}
.pf-more:hover{background:#eef2f6}
.calls{display:grid;grid-template-columns:1fr 1fr;gap:.7rem}
.calls-c{border:1px solid #e2e8f0;border-radius:10px;padding:.6rem .7rem;background:#f8fafc}
.calls-c h3{margin:0 0 .4rem;font-size:.9rem}
.calls-c.ok h3{color:#16a34a}.calls-c.no h3{color:#e11d48}
.calls-c ul{list-style:none;margin:0;padding:0}
.calls-c li{display:flex;flex-direction:column;gap:.1rem;padding:.35rem 0;
  border-bottom:1px solid #eef2f6;font-size:.85rem}
.calls-c li:last-child{border-bottom:0}
.calls-c li span{color:var(--muted);font-size:.75rem}
.lim{margin:.3rem 0;padding-inline-start:1.1rem;line-height:1.9}
.ptable td.good{color:#16a34a;font-weight:800}.ptable td.bad{color:#e11d48;font-weight:800}
@media(max-width:620px){.calls{grid-template-columns:1fr}}
.pp-card{position:absolute;top:-5px;left:-6px;width:9px;height:13px;border-radius:2px;box-shadow:0 1px 2px rgba(0,0,0,.4)}
.pp-card.y{background:#fbbf24}.pp-card.r{background:#dc2626}
.pp-sub{position:absolute;bottom:-4px;left:-8px;width:15px;height:15px;border-radius:50%;
  background:#fff;color:#b91c1c;font-size:.62rem;font-weight:900;display:flex;align-items:center;justify-content:center;
  box-shadow:0 1px 2px rgba(0,0,0,.4)}
.pp-cap{position:absolute;bottom:-4px;right:-6px;width:14px;height:14px;border-radius:50%;
  background:#0f172a;color:#fff;font-size:.56rem;font-weight:900;display:flex;align-items:center;justify-content:center}
@media(max-width:560px){
  .lu{gap:8px}
  .lu-l li{font-size:.72rem;gap:5px}
  .lu-n{flex-basis:20px;font-size:.62rem}
  .lu-p{display:none}
  .tl-r{font-size:.72rem;grid-template-columns:1fr 38px 1fr}
  .pp{width:60px}
  .pp-ava{width:33px;height:33px}
  .pp-ava img,.pp-fb{width:29px;height:29px}
  .pp-nm{max-width:60px;font-size:.56rem}
}
.ko-pp{color:#b45309;background:#fdf3e3;border-radius:8px;padding:2px 10px;font-weight:800}
/* live minute chip (painted by LIVE_JS next to a live score) */
.lv-min{display:inline-block;font-size:.68rem;font-weight:800;color:#e11d48;
  margin-inline-start:8px;direction:ltr;unicode-bidi:embed;vertical-align:middle}
/* mobile-only slim top banner */
.ad-top{display:none}
@media(max-width:900px){
  .ad-top{display:block;margin:10px 0 2px}
  .ad-ph-top{min-height:56px;display:flex;align-items:center;justify-content:center;gap:10px;
    color:#94a3b8;font-weight:800;font-size:.82rem;border:2px dashed #cbd5e1;border-radius:12px;background:#fff}
  .ad-ph-top small{color:#c3cddb;font-weight:700}
}
/* page title + leaderboard ad beside it (desktop) */
.page-head{display:flex;align-items:center;justify-content:space-between;gap:20px}
.page-head-t{min-width:0}
.page-head .page-h,.page-head .hintline{margin:0}
.page-head .hintline{margin-top:4px}
/* never let the leaderboard squeeze the title below half the row */
.head-ad{flex:0 1 728px;max-width:min(728px,55%);min-width:0}
.head-ad .ad-placeholder,.head-ad .ad-unit{min-height:90px;flex-direction:row;gap:10px;position:static}
@media(max-width:900px){
  .page-head{display:block}
  .head-ad{display:none}   /* mobile shows .ad-top above the page instead */
}
.ad-placeholder{min-height:600px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:6px;text-align:center;color:#94a3b8;font-weight:800;border:2px dashed #cbd5e1;border-radius:14px;background:#fff}
.ad-placeholder small{color:#c3cddb;font-weight:700}
@media(max-width:900px){
  .home-topad{display:none}}  /* mobile already has .ad-top */
/* external headlines - 3 per row */
.hgrid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}
@media(max-width:760px){.hgrid{grid-template-columns:repeat(2,1fr)}}
@media(max-width:520px){.hgrid{grid-template-columns:1fr}}
.hcard{position:relative;display:flex;flex-direction:column;min-height:128px;background:#fff;border:1px solid #e6ebf1;border-radius:14px;padding:16px 16px 14px;text-decoration:none;overflow:hidden;box-shadow:0 1px 3px rgba(15,23,42,.05);transition:transform .14s,box-shadow .14s,border-color .14s}
.hcard::before{content:"";position:absolute;inset-block:0;inset-inline-start:0;width:4px;background:linear-gradient(var(--green),var(--green-d));opacity:.85;transition:width .14s}
.hcard:hover{transform:translateY(-3px);box-shadow:0 10px 22px rgba(15,23,42,.13);border-color:#cfe0ee}
.hcard:hover::before{width:6px}
.hcard .himg{display:block;height:130px;margin:0 0 10px;border-radius:10px;overflow:hidden;background:#eef2f6}
.hcard .himg:empty{display:none}
.hcard .himg img{width:100%;height:100%;object-fit:cover;display:block;transition:transform .25s}
.hcard:hover .himg img{transform:scale(1.04)}
.hcard h3{margin:0 0 10px;font-size:.95rem;font-weight:800;line-height:1.55;color:var(--ink);display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.hcard .meta{margin:auto 0 0;display:flex;align-items:center;gap:8px;font-size:.75rem;color:#94a3b8;flex-wrap:wrap}
.hsrc{background:#eaf3fa;color:var(--green-d);font-weight:800;font-size:.72rem;padding:3px 9px;border-radius:999px;white-space:nowrap;max-width:60%;overflow:hidden;text-overflow:ellipsis}
.hcard .reltime-wrap{white-space:nowrap}
.hcard .go{position:absolute;top:12px;inset-inline-end:12px;font-size:.9rem;color:var(--green);opacity:0;transform:translateY(-3px);transition:opacity .14s,transform .14s}
.hcard:hover .go{opacity:1;transform:translateY(0)}
/* news shelf (horizontal, scroll-snap, arrows) */
.shelf-wrap{position:relative}
.shelf{display:flex;gap:15px;overflow-x:auto;
  scrollbar-width:none;padding:2px 2px 6px}
.shelf::-webkit-scrollbar{display:none}
.shelf .card{flex:0 0 250px}
.sh-btn{position:absolute;top:50%;transform:translateY(-50%);z-index:2;width:38px;height:38px;
  border:0;border-radius:50%;background:var(--green);color:#fff;font-size:1.35rem;font-weight:900;
  line-height:1;cursor:pointer;box-shadow:0 4px 12px rgba(15,23,42,.28);opacity:.94}
.sh-btn:hover{background:var(--green-d)}
.sh-l{left:-13px}.sh-r{right:-13px}
@media(max-width:760px){.sh-btn{display:none}}
/* curated-clubs crest strip (end of the news page) */
.clubs{position:relative;background:#fff;border:1px solid #e6ebf1;border-radius:14px;
  padding:14px 30px;margin:22px 0 4px;box-shadow:0 3px 10px rgba(15,23,42,.06)}
/* no scroll-snap on purpose: RTL snapping in Chromium shifts the initial
   position one item in (the first club scrolled out of view on mobile) */
.cs-track{display:flex;gap:22px;overflow-x:auto;scrollbar-width:none;padding:2px 4px}
.cs-track::-webkit-scrollbar{display:none}
.cs-item{flex:0 0 auto;width:96px;display:flex;flex-direction:column;align-items:center;gap:8px;
  text-decoration:none;color:var(--ink);font-weight:800;font-size:.8rem;text-align:center;
  transition:color .12s,transform .12s}
.cs-item img,.cs-ph{width:46px;height:46px;object-fit:contain;display:flex;align-items:center;
  justify-content:center;font-size:1.7rem}
.cs-item span{line-height:1.25;max-width:96px}   /* two-line names (مانشستر يونايتد) instead of an ellipsis */
.cs-item:hover{color:var(--green);transform:translateY(-2px)}
.cs-btn{position:absolute;top:50%;transform:translateY(-50%);z-index:2;width:30px;height:30px;
  border:1px solid #e2e8f0;border-radius:50%;background:#fff;color:var(--ink);font-size:1.3rem;
  font-weight:900;line-height:1;cursor:pointer;box-shadow:0 2px 8px rgba(15,23,42,.14)}
.cs-btn:hover{background:var(--green);color:#fff;border-color:var(--green)}
.cs-l{left:-4px}.cs-r{right:-4px}
@media(max-width:760px){.clubs{padding:12px 14px}.cs-btn{display:none}.cs-track{gap:16px}.cs-item{width:80px}}
/* videos */
.sec-h{display:flex;align-items:baseline;justify-content:space-between;gap:12px;flex-wrap:wrap}
/* live card for a curated club — its own row directly above "آخر الأخبار" */
/* full-width bar: status on the start side, the match centered, minute at the end */
/* clean white card, live-red inline-start accent — same visual language as
   .mrow-live rows; crests + a bolder score pill carry the hierarchy */
.fav-wrap{display:flex;flex-direction:column;gap:8px;margin:10px 0 0}
.fav-live{display:flex;align-items:center;justify-content:space-between;gap:12px;
  text-decoration:none;background:#fff;border:1px solid #e2e8f0;
  border-inline-start:4px solid var(--live);border-radius:14px;
  padding:10px 16px;color:var(--ink);font-weight:800;font-size:.95rem;
  box-shadow:0 1px 3px rgba(15,23,42,.05);transition:box-shadow .15s,border-color .15s}
.fav-live:hover{border-color:#94a3b8;border-inline-start-color:var(--live);
  box-shadow:0 3px 12px rgba(15,23,42,.12)}
/* tighten the news heading under the bar — but only while the bar is actually
   showing, so a quiet day keeps the normal breathing room. h1 only: the h2
   section headings below must not shift with live state. */
.fav-wrap:not([hidden]) + .nf-bar{margin-top:9px}
.fv-live{display:inline-flex;align-items:center;gap:6px;background:var(--live);
  color:#fff;border-radius:999px;padding:3px 12px;font-size:.68rem;font-weight:900;
  letter-spacing:.02em;flex:0 0 auto;white-space:nowrap}
.fv-dot{width:7px;height:7px;border-radius:50%;background:#fff;flex:0 0 auto;
  animation:fvpulse 1.4s ease-in-out infinite}
@keyframes fvpulse{0%,100%{opacity:1}50%{opacity:.25}}
.fv-m{display:inline-flex;align-items:center;justify-content:center;gap:10px;
  flex:1 1 auto;min-width:0}
.fv-m bdi{white-space:nowrap}
.fv-c{width:26px;height:26px;object-fit:contain;flex:0 0 auto}
.fv-s,.tk-s,.sc-in{display:inline-flex;align-items:center;gap:1px}
.fv-s span,.tk-s span,.sc-in span{font-variant-numeric:tabular-nums}
.fv-s i,.tk-s i,.sc-in i{font-style:normal;opacity:.75}
/* a score inside a sentence or a table cell: the inline-flex IS the fix -
   it keeps the home number on the home side. Do not "simplify" to text. */
.sc-in{font-weight:900;margin-inline:2px}
.fv-s{background:var(--green-d);color:#fff;border-radius:8px;padding:2px 12px;
  font-size:.95rem;box-shadow:inset 0 -2px 0 rgba(0,0,0,.18)}
.fv-min{background:#ffe4e9;color:var(--live);border-radius:999px;padding:3px 10px;
  font-size:.72rem;font-weight:900;direction:ltr;unicode-bidi:embed;
  flex:0 0 auto;white-space:nowrap}
@media(max-width:560px){
  /* a phone row is narrow: let the bar wrap its own contents rather than
     clip a club name or push the page sideways */
  .fav-live{font-size:.8rem;padding:9px 12px;gap:8px}
  .fv-m{gap:7px}
  .fv-c{width:20px;height:20px}
  .fv-s{font-size:.82rem;padding:1px 9px}
  /* no room for the text chip on a phone row: the pulsing dot + the red
     accent border + the minute chip already say "live" */
  .fv-lt{display:none}
  .fv-live{padding:5px}
}
.see-all{color:var(--green-d);font-weight:800;text-decoration:none;font-size:.85rem;white-space:nowrap}
.see-all:hover{text-decoration:underline}
.vstrip{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}
.vgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:16px;margin-bottom:8px}
.vcat-h{font-size:1.05rem;border-inline-start:5px solid var(--green);padding-inline-start:10px;margin-top:26px}
@media(max-width:640px){.vstrip{grid-template-columns:1fr}}
.vcard{background:var(--card);border:1px solid #e6ebf1;border-radius:14px;overflow:hidden;box-shadow:0 3px 10px rgba(15,23,42,.08);transition:transform .16s,box-shadow .16s}
.vcard:hover{transform:translateY(-4px);box-shadow:0 16px 30px rgba(15,23,42,.16)}
.vthumb{display:block;width:100%;padding:0;border:0;cursor:pointer;position:relative;aspect-ratio:16/9;background:#000;overflow:hidden}
.vthumb img{width:100%;height:100%;object-fit:cover;display:block}
.vthumb.noimg{background:linear-gradient(135deg,var(--green),#0d3e59)}
.vplay{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);width:56px;height:56px;border-radius:50%;background:rgba(225,29,72,.92);color:#fff;font-size:1.35rem;display:flex;align-items:center;justify-content:center;padding-left:4px;box-shadow:0 4px 14px rgba(0,0,0,.35);transition:transform .14s,background .14s}
.vthumb:hover .vplay{transform:translate(-50%,-50%) scale(1.08);background:#e11d48}
.vframe{width:100%;aspect-ratio:16/9;border:0;display:block;background:#000}
.vb{padding:12px 14px}
.vb h3{margin:0 0 6px;font-size:.95rem;font-weight:800;line-height:1.5;color:var(--ink);display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.empty-note{color:var(--muted);font-weight:700;padding:20px 0}
/* reels: TikTok-style vertical swipe feed (one reel per screen) */
.reels-banner{display:flex;align-items:center;gap:16px;margin:6px 0 4px;padding:14px 16px;
  border-radius:16px;text-decoration:none;color:#fff;
  background:linear-gradient(135deg,var(--green-d),#081a28);
  box-shadow:0 8px 22px rgba(6,21,33,.35);transition:transform .15s,box-shadow .15s}
.reels-banner:hover{transform:translateY(-3px);box-shadow:0 14px 30px rgba(6,21,33,.45)}
.reels-banner img{width:92px;aspect-ratio:9/16;object-fit:cover;border-radius:12px;
  border:2px solid rgba(255,255,255,.35);flex:0 0 auto}
.rb-body h2{margin:0 0 4px;font-size:1.15rem;font-weight:900}
.rb-body p{margin:0 0 10px;font-size:.85rem;color:#cde4f4}
.rb-cta{display:inline-block;background:#e11d48;color:#fff;font-weight:800;font-size:.82rem;
  padding:6px 16px;border-radius:999px}
.rwrap{position:relative;max-width:430px;margin:0 auto}
.rfeed{height:calc(100dvh - 205px);min-height:460px;overflow-y:auto;
  scroll-snap-type:y mandatory;scrollbar-width:none;background:#000;border-radius:18px}
.rfeed::-webkit-scrollbar{display:none}
.rslide{height:100%;scroll-snap-align:start;scroll-snap-stop:always;
  display:flex;align-items:center;justify-content:center}
.rstage{position:relative;height:100%;width:100%;background:#000;overflow:hidden}
.rstage .vthumb{width:100%;height:100%;padding:0;border:0;cursor:pointer;background:#000;display:block;position:relative}
.rstage .vthumb img{width:100%;height:100%;object-fit:cover;display:block}
.rstage .vframe{width:100%;height:100%;border:0;display:block;background:#000}
.rtitle{position:absolute;bottom:0;inset-inline:0;padding:38px 16px 14px;z-index:2;pointer-events:none;
  color:#fff;font-weight:800;font-size:.92rem;line-height:1.5;
  background:linear-gradient(to top,rgba(0,0,0,.8),transparent)}
.sndbtn{position:absolute;top:10px;inset-inline-start:10px;z-index:3;width:44px;height:44px;
  border:0;border-radius:50%;background:rgba(0,0,0,.55);color:#fff;font-size:1.15rem;cursor:pointer;
  display:flex;align-items:center;justify-content:center;backdrop-filter:blur(2px)}
.sndbtn:hover{background:rgba(0,0,0,.75)}
.swipe-hint{position:absolute;top:12px;inset-inline:0;text-align:center;z-index:2;pointer-events:none;
  color:#fff;font-weight:800;font-size:.78rem;text-shadow:0 1px 6px rgba(0,0,0,.7);
  animation:hintbob 1.6s ease-in-out 3}
@keyframes hintbob{0%,100%{transform:translateY(0);opacity:.95}50%{transform:translateY(-7px);opacity:.6}}
.rarrows{position:absolute;top:50%;inset-inline-end:-58px;transform:translateY(-50%);
  display:flex;flex-direction:column;gap:10px}
.rarrows button{width:44px;height:44px;border:0;border-radius:50%;background:var(--green);
  color:#fff;font-size:1.15rem;font-weight:900;cursor:pointer;box-shadow:0 4px 12px rgba(15,23,42,.3)}
.rarrows button:hover{background:var(--green-d)}
@media(max-width:560px){.rfeed{height:calc(100dvh - 165px)}}
@media(hover:none){.rarrows{display:none}}
@media(max-width:560px){.rarrows{display:none}}
/* footer */
.site-foot{background:#0b1220;color:#cbd5e1;margin-top:30px;padding:22px 0}
.site-foot p{margin:2px 0}.credit{font-size:.78rem;color:#94a3b8}
@media(max-width:640px){.feat{height:300px}
  .feat-body h2{font-size:1.15rem;line-height:1.55;
    display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
  .feat-body p{font-size:.82rem;line-height:1.6;
    display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
  .article{padding:18px}}
"""

# ---- legends header strip (free CC / public-domain photos, same as the app) ----
# 8 hand-picked legends (name for tooltip/alt, 200px Wikimedia thumb).
# Every photo was visually reviewed 2026-07-25 — face-centered, good quality.
# (name, url, face position "x% y%", zoom) — the July-2026 NT photos are
# half-body shots, so each avatar is hand-cropped to a tight face close-up:
# object-position centres the face, transform:scale zooms in on it.
LEGENDS = [
  # uniform crops: every face ~same size in the circle, eyes on one line
  # (head + a hint of shoulders; was a mix of tight/loose zooms)
  ("محمد صلاح",         "https://commons.wikimedia.org/wiki/Special:FilePath/Mohamed_Salah_Argentina_v_Egypt_7_July_2026-161.jpg?width=200", "50% 18%", 1.7),
  ("إمام عاشور",        "https://commons.wikimedia.org/wiki/Special:FilePath/Emam_Ashour_Argentina_v_Egypt_7_July_2026-099.jpg?width=200", "48% 16%", 1.8),
  ("شيكابالا",          "https://commons.wikimedia.org/wiki/Special:FilePath/Shikabala_2024_(cropped).jpg?width=200", "42% 14%", 1.9),
  ("عمر مرموش",         "https://commons.wikimedia.org/wiki/Special:FilePath/Omar_Marmoush_Argentina_v_Egypt_7_July_2026-102.jpg?width=200", "52% 17%", 1.6),
  ("محمد الشناوي",      "https://commons.wikimedia.org/wiki/Special:FilePath/Mohamed_El_Shenawy_Argentina_v_Egypt_7_July_2026-015.jpg?width=200", "50% 17%", 1.7),
  ("تريزيجيه",          "https://commons.wikimedia.org/wiki/Special:FilePath/Trezeguet_Argentina_v_Egypt_7_July_2026-267.jpg?width=200", "50% 15%", 1.7),
]
# static face-circle tiles: name tooltip via title/alt.
LEGENDS_HTML = "".join(
    f'<span class="lg-ava"><img src="{u}" alt="{n}" title="{n}" loading="lazy"'
    f' style="object-position:{p};transform:scale({z});transform-origin:{p}"></span>'
    for n, u, p, z in LEGENDS)

LEGENDS_CSS = """
/* legends strip: 8 big face circles, static, name on hover */
.legends{flex:1;min-width:0;margin-inline-start:20px;display:flex;
  justify-content:center;overflow-x:auto;scrollbar-width:none}
.legends::-webkit-scrollbar{display:none}
.lg-track{display:inline-flex;align-items:center;gap:16px}
.lg-ava{width:66px;height:66px;border-radius:50%;overflow:hidden;flex:0 0 auto;
  border:2.5px solid rgba(255,255,255,.65);
  box-shadow:0 3px 10px rgba(0,0,0,.35);
  transition:transform .16s,border-color .16s,box-shadow .16s}
.lg-ava img{width:100%;height:100%;object-fit:cover;display:block}
.lg-ava:hover{transform:scale(1.18);border-color:#fff;
  box-shadow:0 6px 16px rgba(0,0,0,.45)}
/* live-scores ticker */
.ticker{display:block;background:#081a28;overflow:hidden;text-decoration:none;
  border-top:1px solid rgba(255,255,255,.07);
  position:relative;clip-path:inset(0)}  /* WebKit: animated transform escapes overflow:hidden */
.tk-track{display:inline-flex;width:max-content;align-items:center;gap:30px;
  padding:6px 0;animation:tkmove 45s linear infinite}
.ticker:hover .tk-track{animation-play-state:paused}
.tk-item{display:inline-flex;align-items:center;gap:6px;color:#d6e3ee;
  font-size:.78rem;font-weight:700;white-space:nowrap}
.tk-b{width:16px;height:16px;object-fit:contain}
.tk-s{color:#fff;background:rgba(255,255,255,.14);padding:1px 8px;border-radius:6px}
.tk-t{color:#8ed3f5;font-weight:800}
.tk-d{color:#9fb0bf;font-size:.68rem;font-weight:800;border:1px solid rgba(255,255,255,.18);
  padding:0 6px;border-radius:5px}
/* live ticker item: red score pill + a bigger dot with an expanding radar
   ring — «شغال مباشر دلوقتي» must read at a glance (user, 2026-08-23) */
.tk-s.tk-live{background:var(--live);color:#fff}
.tk-dot{width:9px;height:9px;border-radius:50%;background:#ff4d6d;
  animation:tkpulse 1.2s ease-in-out infinite,tkring 1.2s ease-out infinite}
@keyframes tkmove{from{transform:translateX(0)}to{transform:translateX(50%)}}
@keyframes tkpulse{0%,100%{opacity:1}50%{opacity:.35}}
@keyframes tkring{from{box-shadow:0 0 0 0 rgba(255,77,109,.55)}
  to{box-shadow:0 0 0 7px rgba(255,77,109,0)}}
@media(max-width:720px){
  .head-in{height:60px}
  .head-crowd{height:60px;width:calc(100% - 170px)}
  .legends{margin-inline-start:10px;justify-content:flex-start}
  .lg-track{gap:9px}
  .lg-ava{width:46px;height:46px;border-width:2px}
  .nav-en{display:none}
  .navtab{padding:0 14px}
}
@media(prefers-reduced-motion:reduce){.lg-track,.tk-track{animation:none}}
/* goal flash: LIVE_JS adds .sc-pop to the score element only when the number
   actually changed between two polls - i.e. a goal just went in. Never on the
   first paint, so a page load doesn't replay an old goal. */
@keyframes scpop{
  0%{transform:scale(1)}
  22%{transform:scale(1.28);background:var(--green);color:#fff}
  55%{transform:scale(1.05);background:var(--green);color:#fff}
  100%{transform:scale(1)}
}
/* display:inline-block is load-bearing, not cosmetic: .score is a <b>, and a
   non-replaced INLINE box ignores `transform` entirely - the scale silently
   did nothing on match rows while working in the ticker (.tk-s is inline-flex). */
.sc-pop{animation:scpop 1.4s ease-out;display:inline-block;border-radius:8px;padding-inline:4px}
.tk-s.sc-pop{padding-inline:8px}
@media(prefers-reduced-motion:reduce){.sc-pop{animation:none;outline:2px solid var(--green);outline-offset:2px}}
"""

# progressive-enhancement: show one day at a time with prev/next (like the live app).
# Without JS, every day-section stays visible (crawlable).
ROUNDS_JS = """<script>
(function(){
  [].slice.call(document.querySelectorAll('.rounds-panel')).forEach(function(panel){
    var rounds=[].slice.call(panel.querySelectorAll('.round'));
    if(!rounds.length) return;
    var label=panel.querySelector('.rn-label');
    var prev=panel.querySelector('.rn-prev'), next=panel.querySelector('.rn-next');
    /* /matches ships ONE round and no navigator (the season lives on
       /fixtures/<league> since 2026-09-20). Without this guard the missing
       .rn-label threw on the first panel and killed the navigator on every
       panel after it. */
    if(!label||!prev||!next){ rounds.forEach(function(r){ r.hidden=false; }); return; }
    var cur=panel.getAttribute('data-current');
    var idx=0;
    for(var i=0;i<rounds.length;i++){ if(rounds[i].getAttribute('data-round')===cur){ idx=i; break; } }
    function show(i){
      idx=Math.max(0,Math.min(rounds.length-1,i));
      rounds.forEach(function(r,j){ r.hidden = j!==idx; });
      label.textContent=rounds[idx].getAttribute('data-label');
      prev.disabled=(idx<=0); next.disabled=(idx>=rounds.length-1);
    }
    prev.addEventListener('click',function(){ show(idx-1); });
    next.addEventListener('click',function(){ show(idx+1); });
    show(idx);
  });
})();
</script>"""

# FotMob-style filter bar for the matches day view (user ask 2026-09-02):
# live-only, by-time (flat list sorted by kickoff, league label under each
# match) and a free-text team/league filter. Wired in MATCHES_JS. (An on-TV
# chip existed for a few hours on 2026-09-02; the user asked to remove it.)
FILTERS_HTML = (
    '<div id="mfilters" class="mfilters" hidden>'
    '<button type="button" class="mf-chip" data-f="live" aria-pressed="false"><span class="mf-dot"></span>مباشر</button>'
    '<button type="button" class="mf-chip" data-f="time" aria-pressed="false">⏱ حسب الوقت</button>'
    '<label class="mf-search"><span aria-hidden="true">🔍</span>'
    '<input type="search" id="mfQ" placeholder="فلتر: فريق أو بطولة" autocomplete="off" aria-label="فلتر المباريات"></label>'
    '</div>')

MATCHES_JS = """<script>
(function(){
  var wrap=document.getElementById('days'); if(!wrap) return;
  var sections=Array.prototype.slice.call(wrap.querySelectorAll('.day'));
  if(!sections.length) return;
  var days=sections.map(function(s){return s.getAttribute('data-day');});
  var today=wrap.getAttribute('data-today')||days[0];
  var idx=days.indexOf(today);
  if(idx<0){ for(var i=0;i<days.length;i++){ if(days[i]>=today){idx=i;break;} } }
  if(idx<0) idx=days.length-1;
  var nav=document.getElementById('daynav'); nav.hidden=false;
  var label=document.getElementById('dayLabel');
  var prev=document.getElementById('prevDay'), next=document.getElementById('nextDay');
  sections.forEach(function(s){ var h=s.querySelector('.day-h'); if(h) h.style.display='none'; });
  var filter='';   /* competition name; '' = all */
  /* ---- FotMob-style filters: live / on TV / by time / text ---- */
  var mf=document.getElementById('mfilters'); if(mf) mf.hidden=false;
  var fLive=false, fTime=false, q='';   /* the on-TV chip was removed by the user 2026-09-02 */
  function norm(t){ return (t||'').replace(/[أإآ]/g,'ا').replace(/ة/g,'ه').replace(/ى/g,'ي').toLowerCase().replace(/ +/g,' ').trim(); }
  /* remember each row's league + original list/position: "by time" moves
     rows out of their .comp blocks and must put them back in order */
  var rowIdx=0;
  [].slice.call(wrap.querySelectorAll('.comp')).forEach(function(c){
    var cn=c.getAttribute('data-comp')||'', cl=c.getAttribute('data-label')||'', list=c.querySelector('.mlist');
    [].slice.call(c.querySelectorAll('.mrow')).forEach(function(r){ r.__cname=cn; r.__clabel=cl; r.__home=list; r.__idx=rowIdx++; });
  });
  function rowOk(r){
    if(fLive && !r.classList.contains('mrow-live')) return false;
    if(filter && r.__cname!==filter) return false;
    if(q){ var hay=norm(r.getAttribute('data-h')+' '+r.getAttribute('data-a')+' '+r.__clabel+' '+r.__cname); if(hay.indexOf(q)<0) return false; }
    return true;
  }
  function byTimeList(sec){
    var bt=sec.querySelector('.bytime');
    if(!bt){ bt=document.createElement('div'); bt.className='mlist bytime'; bt.hidden=true; sec.insertBefore(bt, sec.querySelector('.no-comp')); }
    return bt;
  }
  function applyFilter(sec){
    var rows=[].slice.call(sec.querySelectorAll('.mrow')), comps=[].slice.call(sec.querySelectorAll('.comp'));
    var bt=byTimeList(sec), any=false;
    if(fTime){
      rows.sort(function(a,b){ return (a.getAttribute('data-ko')||'').localeCompare(b.getAttribute('data-ko')||''); });
      rows.forEach(function(r){
        if(!r.querySelector('.mf-comp')){ var d=document.createElement('div'); d.className='mcomp mf-comp'; d.textContent=r.__clabel||r.__cname; r.appendChild(d); }
        bt.appendChild(r);
      });
      comps.forEach(function(c){ c.style.display='none'; });
      bt.hidden=false;
    } else {
      rows.slice().sort(function(a,b){ return a.__idx-b.__idx; }).forEach(function(r){
        var d=r.querySelector('.mf-comp'); if(d) d.parentNode.removeChild(d);
        if(r.__home && r.parentNode!==r.__home) r.__home.appendChild(r);
      });
      bt.hidden=true;
    }
    rows.forEach(function(r){ var ok=rowOk(r); r.style.display=ok?'':'none'; if(ok) any=true; });
    if(!fTime){
      comps.forEach(function(c){
        var vis=[].slice.call(c.querySelectorAll('.mrow')).some(function(r){ return r.style.display!=='none'; });
        c.style.display=vis?'':'none';
      });
    }
    var note=sec.querySelector('.no-comp');
    if(note){ note.hidden=any; note.textContent=(fLive||q)?'لا مباريات تطابق الفلتر في هذا اليوم.':'لا مباريات لهذه البطولة في هذا اليوم — جرّب يومًا آخر.'; }
  }
  if(mf){
    [].slice.call(mf.querySelectorAll('.mf-chip')).forEach(function(b){
      b.addEventListener('click',function(){
        var f=b.getAttribute('data-f'), on=!b.classList.contains('is-on');
        b.classList.toggle('is-on',on); b.setAttribute('aria-pressed',on?'true':'false');
        if(f==='live') fLive=on; else if(f==='time') fTime=on;
        applyFilter(sections[idx]);
      });
    });
    var qi=document.getElementById('mfQ');
    if(qi) qi.addEventListener('input',function(){ q=norm(qi.value); applyFilter(sections[idx]); });
  }
  function show(i){
    idx=i;
    sections.forEach(function(s,j){ s.style.display=(j===idx)?'block':'none'; });
    label.textContent=sections[idx].querySelector('.day-h').textContent;
    prev.disabled=(idx<=0); next.disabled=(idx>=sections.length-1);
    applyFilter(sections[idx]);
  }
  prev.addEventListener('click',function(){ if(idx>0) show(idx-1); });
  next.addEventListener('click',function(){ if(idx<sections.length-1) show(idx+1); });
  var lviews=[].slice.call(document.querySelectorAll('.lview'));
  var lgItems=[].slice.call(document.querySelectorAll('.lg-item'));
  var pane='table';                /* remembered across league switches */
  function showPane(view,key){
    var tabs=[].slice.call(view.querySelectorAll('.ltab'));
    var panes=[].slice.call(view.querySelectorAll('.lpane'));
    var has=tabs.some(function(t){return t.getAttribute('data-pane')===key;});
    if(!has) key=tabs.length?tabs[0].getAttribute('data-pane'):'';
    tabs.forEach(function(t){ t.classList.toggle('is-on',t.getAttribute('data-pane')===key); });
    panes.forEach(function(x){ x.hidden = x.getAttribute('data-pane')!==key; });
    return key;
  }
  lviews.forEach(function(view){
    view.addEventListener('click',function(e){
      var t=e.target.closest('.ltab'); if(!t) return;
      pane=showPane(view,t.getAttribute('data-pane'));
      if(history.replaceState) history.replaceState(null,'','#'+pane);
    });
  });
  /* the daynav has CSS display:flex which overrides the [hidden] attribute,
     so toggle it via inline style.display instead */
  var noTable=document.getElementById('noTable');
  var mpDefault=document.getElementById('mpDefault');
  /* RAIL panels only - the rounds panels now also live inside .lpane tabs,
     and a bare '.lg-fix' selector would fight the tab logic for them */
  var fixPanels=[].slice.call(document.querySelectorAll('.mp-extra .lg-fix'));
  var mpage=document.querySelector('.mpage');
  function matchesShown(on){ nav.style.display = on ? '' : 'none'; wrap.style.display = on ? '' : 'none'; if(mf) mf.style.display = on ? '' : 'none'; }
  function reset(){                 /* all-matches view (default / top nav tab) */
    filter='';
    lgItems.forEach(function(x){ x.classList.remove('is-active'); });
    lviews.forEach(function(v){ v.hidden=true; });
    fixPanels.forEach(function(f){ f.hidden=true; });
    if(noTable) noTable.hidden=true;
    if(mpDefault) mpDefault.hidden=false;
    if(mpage) mpage.classList.remove('league-view');
    matchesShown(true);
    applyFilter(sections[idx]);
  }
  function selectLeague(b){
    filter=b.getAttribute('data-comp')||'';
    lgItems.forEach(function(x){ x.classList.toggle('is-active', x===b); });
    var view=lviews.filter(function(v){return v.getAttribute('data-comp')===filter;})[0];
    lviews.forEach(function(v){ v.hidden = v!==view; });
    if(view) pane=showPane(view,pane);                /* keep the reader on the same tab */
    matchesShown(false);                              /* never show fixtures in the centre */
    if(noTable) noTable.hidden = !!view;              /* nothing for this league -> placeholder */
    /* left rail: this league's fixtures instead of news */
    var fx=fixPanels.filter(function(f){return f.getAttribute('data-comp')===filter;})[0];
    fixPanels.forEach(function(f){ f.hidden = f!==fx; });
    if(mpDefault) mpDefault.hidden = !!fx;            /* has fixtures -> hide news */
    if(mpage) mpage.classList.add('league-view');
    window.scrollTo({top:0,behavior:'smooth'});
  }
  var h=(location.hash||'').replace('#','');
  if(h) pane=h;                    /* deep link: /matches.html#scorers */
  lgItems.forEach(function(b){ b.addEventListener('click',function(){ selectLeague(b); }); });
  var mTab=document.querySelector('a.navtab[href="/matches.html"]');
  if(mTab) mTab.addEventListener('click',function(e){ e.preventDefault(); reset(); window.scrollTo({top:0,behavior:'smooth'}); });
  show(idx);
})();
</script>"""

# client-side relative time ("منذ X") - always accurate to the visitor's clock.
REL_JS = """<script>
(function(){
  function unit(n,one,two,few){
    if(n===1)return 'منذ '+one;
    if(n===2)return 'منذ '+two;
    if(n>=3&&n<=10)return 'منذ '+n+' '+few;
    return 'منذ '+n+' '+one;
  }
  function rel(iso){
    var d=new Date(iso); if(isNaN(d.getTime())) return null;
    var s=Math.floor((Date.now()-d.getTime())/1000); if(s<0) s=0;
    if(s<60) return 'منذ لحظات';
    var m=Math.floor(s/60); if(m<60) return unit(m,'دقيقة','دقيقتين','دقائق');
    var h=Math.floor(m/60); if(h<24) return unit(h,'ساعة','ساعتين','ساعات');
    return unit(Math.floor(h/24),'يوم','يومين','أيام');
  }
  function sweep(){
    document.querySelectorAll('time.reltime').forEach(function(el){
      var t=rel(el.getAttribute('datetime'));
      if(t) el.textContent=t;
    });
  }
  sweep();
  setInterval(sweep,60000); /* keep 'منذ 5 دقائق' honest on a page left open */
})();
</script>"""

FBCOPY_JS = """<script>
(function(){
  document.querySelectorAll('.fbp-c').forEach(function(b){
    b.addEventListener('click',function(){
      var t=b.parentNode.querySelector('.fbp-t');
      t.select();t.setSelectionRange(0,999999);
      function ok(){b.textContent='✓ اتنسخ';setTimeout(function(){b.textContent='📋 نسخ';},1500);}
      if(navigator.clipboard&&navigator.clipboard.writeText){
        navigator.clipboard.writeText(t.value).then(ok,function(){document.execCommand('copy');ok();});
      }else{document.execCommand('copy');ok();}
    });
  });
})();
</script>"""

SHELF_JS = """<script>
(function(){
  var sh=document.getElementById('newsShelf'); if(!sh) return;
  function step(){ var c=sh.querySelector('.card'); return c ? c.offsetWidth + 15 : 265; }
  /* rAF glide: Chromium's smooth scrollBy mis-clamps negative (RTL) targets */
  function glide(delta){
    var start=sh.scrollLeft, min=-(sh.scrollWidth-sh.clientWidth), max=0;
    var target=Math.min(max, Math.max(min, start+delta));
    var t0=performance.now();
    function f(t){
      var k=Math.min(1,(t-t0)/300); k=1-Math.pow(1-k,3);
      sh.scrollLeft=start+(target-start)*k;
      if(k<1) requestAnimationFrame(f);
    }
    requestAnimationFrame(f);
  }
  var l=document.querySelector('.sh-l'), r=document.querySelector('.sh-r');
  if(l) l.addEventListener('click',function(){ glide(-step()); });
  if(r) r.addEventListener('click',function(){ glide( step()); });
})();
</script>"""

REELS_FEED_JS = """<script>
(function(){
  var feed=document.getElementById('rfeed'); if(!feed) return;
  var slides=[].slice.call(feed.querySelectorAll('.rslide'));
  slides.forEach(function(s){ s.__facade = s.querySelector('.rstage').innerHTML; });
  var userSound = localStorage.getItem('ys_reels_sound')==='1';

  function pm(f,func,args){ try{
    f.contentWindow.postMessage(JSON.stringify({event:'command',func:func,args:args||[]}),'*');
  }catch(e){} }
  function unmute(f){ pm(f,'unMute'); pm(f,'setVolume',[100]); }

  function soundBtn(st,f){
    var b=document.createElement('button');
    b.className='sndbtn'; b.type='button';
    b.textContent = userSound ? '\\uD83D\\uDD0A' : '\\uD83D\\uDD07';
    b.setAttribute('aria-label','\\u0627\\u0644\\u0635\\u0648\\u062a');
    b.addEventListener('click',function(ev){
      ev.stopPropagation();
      userSound=!userSound;
      localStorage.setItem('ys_reels_sound',userSound?'1':'0');
      if(userSound){ unmute(f); b.textContent='\\uD83D\\uDD0A'; }
      else{ pm(f,'mute'); b.textContent='\\uD83D\\uDD07'; }
    });
    st.appendChild(b);
  }

  /* autoplay (muted - browser policy) the reel of slide i; kill all others */
  function activate(i){
    i=Math.max(0,Math.min(slides.length-1,i));
    slides.forEach(function(s,j){
      var st=s.querySelector('.rstage');
      if(j!==i){ if(st.querySelector('iframe')) st.innerHTML=s.__facade; return; }
      if(st.querySelector('iframe')) return;              // already playing
      var btn=st.querySelector('.vthumb'); if(!btn) return;
      var id=st.getAttribute('data-vid');
      var f=document.createElement('iframe');
      f.className='vframe';
      f.src='https://www.youtube-nocookie.com/embed/'+id+
            '?autoplay=1&mute=1&playsinline=1&rel=0&enablejsapi=1&loop=1&playlist='+id;
      f.title='reel';
      f.allow='accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture';
      f.setAttribute('allowfullscreen','');
      btn.replaceWith(f);
      soundBtn(st,f);
      if(userSound) setTimeout(function(){ unmute(f); },800);
    });
  }

  function idx(){ return Math.round(feed.scrollTop / feed.clientHeight); }
  function go(i){ feed.scrollTo({top:Math.max(0,Math.min(slides.length-1,i))*feed.clientHeight,behavior:'smooth'}); }

  /* swipe/scroll -> activate the reel you landed on */
  var st_;
  feed.addEventListener('scroll',function(){
    clearTimeout(st_); st_=setTimeout(function(){ activate(idx()); },300);
  });
  /* backup trigger in browsers where the scroll event is throttled */
  var io=new IntersectionObserver(function(es){
    es.forEach(function(en){ if(en.isIntersecting) activate(slides.indexOf(en.target)); });
  },{root:feed,threshold:.6});
  slides.forEach(function(s){ io.observe(s); });
  /* manual tap on a facade (autoplay blocked?) - play THAT slide with sound */
  feed.addEventListener('click',function(e){
    var btn=e.target.closest('.vthumb'); if(!btn) return;
    e.stopPropagation();
    userSound=true; localStorage.setItem('ys_reels_sound','1');
    activate(slides.indexOf(e.target.closest('.rslide')));
  },true);
  /* desktop arrows */
  var up=document.getElementById('rUp'), dn=document.getElementById('rDn');
  if(up) up.addEventListener('click',function(){ go(idx()-1); });
  if(dn) dn.addEventListener('click',function(){ go(idx()+1); });
  /* start: first reel plays by itself */
  activate(0);
})();
</script>"""

VIDEO_JS = """<script>
(function(){
  if(window.__yv) return; window.__yv=1;  // idempotent (page may include twice)
  document.addEventListener('click',function(e){
    var btn=e.target.closest('.vthumb'); if(!btn) return;
    var card=btn.closest('.vcard'); if(!card) return;
    var id=card.getAttribute('data-vid'); if(!id) return;
    var src=card.getAttribute('data-src')||'youtube';
    var h3=card.querySelector('h3');
    var f=document.createElement('iframe');
    f.className='vframe';
    f.src = (src==='dailymotion')
      ? 'https://www.dailymotion.com/embed/video/'+id+'?autoplay=1'
      : 'https://www.youtube-nocookie.com/embed/'+id+'?autoplay=1&rel=0';
    f.title=h3?h3.textContent:'video';
    f.allow='accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture';
    f.setAttribute('allowfullscreen','');
    btn.replaceWith(f);
  });
})();
</script>"""

if __name__ == "__main__":
    build()
