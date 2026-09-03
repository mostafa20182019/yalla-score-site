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
import base64, json, os, re, html, shutil, datetime, hashlib

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

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
DIST = os.path.join(HERE, "dist")

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
    return ('<div class="ad-placeholder"><span>مساحة إعلانية</span>'
            '<small>Google AdSense</small></div>')

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
        inner = ('<div class="ad-ph-top"><span>مساحة إعلانية</span>'
                 '<small>Google AdSense</small></div>')
    return f'<div class="ad-top">{inner}</div>'

def head(title, desc, url, image=None, og_type="website", active=""):
    desc = strip_tags(desc)[:300]
    # og:image must be a raster — Facebook/Twitter ignore SVG entirely (the
    # homepage once inherited a placeholder SVG from the hero article and FB
    # rendered no preview at all) — and at least 200px. The branded 1200x630
    # banner is both the default and the SVG-placeholder replacement.
    if not image or image.lower().endswith(".svg"):
        image = SITE_BASE + "/assets/og-banner.png"
    img = image
    ha = " is-active" if active == "home" else ""
    ma = " is-active" if active == "matches" else ""
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
<link rel="canonical" href="{esc(url)}">
<meta name="robots" content="index, follow">
<meta name="google-site-verification" content="mMvVRBkeRXu37K-dU3QCrngUUJs9a2FfwpJNX3CHcpk">
<meta property="og:type" content="{og_type}">
<meta property="og:site_name" content="{esc(SITE_NAME)}">
<meta property="og:locale" content="{LOCALE}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{esc(url)}">
<meta property="og:image" content="{esc(img)}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{esc(title)}">
<meta name="twitter:description" content="{esc(desc)}">
<meta name="twitter:image" content="{esc(img)}">
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
{stats_tab}{vids_tab}{reels_tab}
  </div></nav>
</header>
<main class="wrap">
{adsense_top_banner()}
"""
    return t

def foot():
    year = "2026"
    stats_link = ' · <a href="/stats.html">إحصائيات</a>' if SHOW_STATS_PAGE else ""
    heads_link = ' · <a href="/headlines.html">عناوين الصحف</a>' if SHOW_HEADLINES else ""
    vids_link = ' · <a href="/videos.html">فيديوهات</a>' if SHOW_VIDEOS else ""
    reels_link = ' · <a href="/reels.html">ريلز</a>' if SHOW_REELS else ""
    return f"""</main>
<footer class="site-foot"><div class="wrap">
  <p>{esc(SITE_NAME)} — {esc(SITE_TAGLINE)}</p>
  <p class="foot-links"><a href="/">أخبار</a> · <a href="/news.html">كل الأخبار</a>{heads_link} · <a href="/matches.html">المباريات</a> · <a href="/standings/egypt.html">ترتيب الدوري المصري</a> · <a href="/scorers/egypt.html">هدافو الدوري المصري</a> · <a href="/team/al-ahly.html">أخبار الأهلي</a> · <a href="/team/zamalek.html">أخبار الزمالك</a>{stats_link}{vids_link}{reels_link} · <a href="/about.html">من نحن</a> · <a href="/contact.html">اتصل بنا</a> · <a href="/editorial.html">السياسة التحريرية</a> · <a href="/terms.html">شروط الاستخدام</a> · <a href="/privacy.html">سياسة الخصوصية</a> · <a href="{FB_PAGE_URL}" target="_blank" rel="noopener">فيسبوك</a></p>
  <p class="credit">صور عبر Wikimedia Commons / Unsplash — رخص حرة / المجال العام · صورة جماهير الهيدر: Кирилл Венедиктов، CC BY-SA 3.0 (مُجمّعة ومقصوصة) · صور لاعبي منتخب مصر 2026: Bryan Berlin، CC BY-SA 4.0</p>
  <p class="credit">© {year} {esc(SITE_NAME)}</p>
</div></footer>
</body></html>{KO_SCRIPT}{REL_JS}{LIVE_JS}"""

def jsonld(obj):
    return '<script type="application/ld+json">' + json.dumps(obj, ensure_ascii=False) + '</script>'

# Live-scores ticker in the header. Built once per build from matches.json
# (site rebuilds every 30 min, so it stays fresh). Set by build().
TICKER_HTML = ""
CSS_VER = "1"   # cache-buster for /assets/style.css, set from CSS content hash in build()
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
     "news_tokens": ["الأهلي"], "news_excl": ["الأهلي السعودي", "أهلي جدة"]},
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

def article_url(a):
    return f"{SITE_BASE}/a/{a['article_id']}.html"

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
    img = a.get("image_url")
    thumb = (f'<div class="card-img" style="background-image:url(\'{esc(img)}\')"></div>'
             if img else '<div class="card-img noimg">⚽</div>')
    t = art_reltime(a)
    return (f'<a class="card" href="/a/{a["article_id"]}.html">{thumb}'
            f'<div class="card-b"><h3>{esc(a["title"])}</h3>'
            f'<p class="meta">{esc(a.get("author"))}{" · " + t if t else ""}</p></div></a>')

def _art_meta(a):
    """author · منذ X — the byline under FotMob-block titles."""
    t = art_reltime(a)
    return esc(a.get("author") or SITE_NAME) + (f" · {t}" if t else "")

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
    fb = (f'<a class="nf-fb" href="{esc(FB_PAGE_URL)}" target="_blank" rel="noopener" '
          'title="تابعنا على فيسبوك" aria-label="تابعنا على فيسبوك">'
          '<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"><path fill="#fff" '
          'd="M13.5 22v-8.2h2.8l.4-3.3h-3.2V8.4c0-.9.3-1.6 1.6-1.6h1.7V3.9c-.3 0-1.3-.1-2.5-.1'
          '-2.5 0-4.2 1.5-4.2 4.3v2.4H7.3v3.3h2.8V22h3.4z"/></svg><span class="nf-fbt">تابعنا</span></a>')
    return ('<div class="nf-bar"><h1 class="page-h">آخر الأخبار</h1>'
            f'<div class="nf-chips" role="group" aria-label="فلتر الأخبار">{btns}</div>{fb}</div>'
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
    img = feat_a.get("image_url")
    imgdiv = (f'<div class="fmb-img" style="background-image:url(\'{esc(img)}\')"></div>'
              if img else '<div class="fmb-img fmb-noimg"></div>')
    _nf = f' data-nf="{nf}"' if nf else ""     # news-filter key (NEWS_FILTER_JS)
    out = [f'<section class="fmb fmb-flip"{_nf}>' if flip else f'<section class="fmb"{_nf}>']
    out.append(f'<a class="fmb-feat" href="/a/{feat_a["article_id"]}.html">'
               + (f'<div class="fmb-banner">{banner}</div>' if banner else "")
               + imgdiv
               + f'<div class="fmb-fb"><h2>{esc(feat_a["title"])}</h2>'
               + f'<p class="fmb-meta">{_art_meta(feat_a)}</p></div></a>')
    out.append(f'<div class="fmb-list"><div class="fmb-lh">{esc(list_head)}</div>')
    for i, a in enumerate(list_items, 1):
        th = (f'<img class="fmb-th" src="{esc(a.get("image_url"))}" alt="" loading="lazy">'
              if a.get("image_url") else "")
        out.append(f'<a class="fmb-row" href="/a/{a["article_id"]}.html">'
                   f'<span class="fmb-num">{i}</span>'
                   f'<span class="fmb-rt"><b>{esc(a["title"])}</b>'
                   f'<small>{_art_meta(a)}</small></span>{th}</a>')
    out.append(f'<a class="fmb-more" href="{more_url}">المزيد ←</a></div></section>')
    return "".join(out)

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

    articles = load("articles.json")
    matches = load("matches.json")
    headlines = load("headlines.json")
    videos = load("videos.json")
    standings = load("standings.json")   # [{competition, table:[...]}]
    scorers = load("scorers.json")       # [{competition, scorers:[{name,team,goals,...}]}]
    assists = load("assists.json")       # same shape, key "assists"
    fixtures = load("fixtures.json")      # [{competition, current, rounds:[{round, matches}]}]
    goal_events = load("goal_events.json")  # [{home, away, date, goals:[{side,player,minute,tag}]}]
    ge_idx = goal_events_index(goal_events)
    # per-match lineups/cards/subs, accumulated by fetch_data (45 days)
    md_idx = match_details_index(load("match_details.json"))
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
                  image=(feat and feat.get("image_url")) or None, active="home")]
    parts.append(jsonld({
        "@context": "https://schema.org", "@type": "WebSite",
        "name": SITE_NAME, "url": SITE_BASE + "/",
        "inLanguage": "ar", "description": strip_tags(SITE_DESC)}))
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

    # ---- article pages ----
    for a in articles:
        url = article_url(a)
        img = a.get("image_url")
        ld = {"@context": "https://schema.org", "@type": "NewsArticle",
              "headline": a["title"], "description": strip_tags(a.get("summary")),
              "datePublished": a.get("pub_date"), "dateModified": a.get("pub_date"),
              "inLanguage": "ar", "mainEntityOfPage": url,
              "author": {"@type": "Organization", "name": a.get("author") or SITE_NAME},
              "publisher": {"@type": "Organization", "name": SITE_NAME,
                            "logo": {"@type": "ImageObject", "url": SITE_BASE + "/assets/logo.png"}}}
        if img: ld["image"] = [img]
        p = [head(f"{a['title']} — {SITE_NAME}", a.get("summary"), url, image=img, og_type="article")]
        p.append(jsonld(ld))
        p.append('<a class="back" href="/">→ رجوع للرئيسية</a>')
        p.append('<article class="article">')
        p.append(f'<h1>{esc(a["title"])}</h1>')
        _t = art_reltime(a)
        p.append(f'<p class="a-meta">{esc(a.get("author"))} · <time datetime="{esc(a.get("pub_date"))}">{esc(a.get("pub_date"))}</time>'
                 f'{" · " + _t if _t else ""}</p>')
        if img:
            p.append(f'<figure class="a-fig"><img class="a-img" src="{esc(img)}" alt="{esc(a["title"])}" loading="eager">')
            cr = a.get("image_credit")
            if cr:
                p.append(f'<figcaption class="a-credit">{esc(cr)}</figcaption>')
            p.append('</figure>')
        if a.get("summary"):
            p.append(f'<p class="lead">{esc(a["summary"])}</p>')
        p.append(f'<div class="a-body">{a.get("body") or ""}</div>')
        _clubs = [tp for tp in TEAM_PAGES if _team_news(tp, a)]
        if _clubs:
            p.append('<nav class="club-chips"><span>المزيد عن:</span>'
                     + "".join(f'<a href="/team/{tp["slug"]}.html">'
                               f'{esc(tp["name"])}</a>' for tp in _clubs)
                     + '</nav>')
        p.append('</article>')
        p.append(foot())
        write(f"a/{a['article_id']}.html", "".join(p))
        urls.append(f"/a/{a['article_id']}.html")

    # ---- shared per-league data + stats machinery (matches page + /stats) ----
    st_by_comp = {s.get("competition"): s for s in standings if s.get("table")}
    sc_by_comp = {s.get("competition"): (s.get("scorers") or [])
                  for s in scorers if s.get("scorers")}
    as_by_comp = {s.get("competition"): (s.get("assists") or [])
                  for s in assists if s.get("assists")}
    forms = team_form(fixtures)
    elos = compute_elo(fixtures)
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
        comp_goals[_c] = sum(m["home_score"] + m["away_score"] for _, m in _f)
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
        big_s = f'{big["home_score"]}-{big["away_score"]}'
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
               f'<div class="tile tile-res" title="{esc(big_t)}"><b>{big_s}</b>'
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
            panes["rounds"] = league_rounds_panel(c, fx_by_comp[c], embedded=True)
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
                row = match_row(m, show_time=True, show_comp=False,
                                goals=match_goals(ge_idx, m),
                                link=match_url(m))
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
        p.append(f'<a class="mp-feat" href="/a/{fa["article_id"]}.html">')
        if fa.get("image_url"):
            p.append(f'<img class="mp-feat-img" src="{esc(fa["image_url"])}" alt="" loading="lazy">')
        p.append(f'<b class="mp-feat-t">{esc(fa.get("title"))}</b>'
                 '<span class="mp-feat-cta">اقرأ الخبر ←</span></a>')
        p.append('<div class="mp-news">')
        for a in articles[1:4]:
            img = a.get("image_url")
            th = (f'<span class="mn-th" style="background-image:url(\'{esc(img)}\')"></span>'
                  if img else '<span class="mn-th noimg">⚽</span>')
            p.append(f'<a class="mn-item" href="/a/{a["article_id"]}.html">{th}'
                     f'<span class="mn-b"><span class="mn-t">{esc(a.get("title"))}</span>'
                     f'<span class="mn-d">{esc(a.get("pub_date") or "")}</span></span></a>')
        p.append('</div>')
    p.append('</div>')
    p.append('</aside>')

    p.append('</div>')  # /mpage
    p.append(MATCHES_JS)
    p.append(ROUNDS_JS)
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
    m_all = {m["match_id"]: m
             for m in load("matches_archive.json") if m.get("match_id")}
    for m in matches:
        if m.get("match_id"):
            m_all[m["match_id"]] = m      # day-window copy is always fresher
    sm_cut = (datetime.date.today() - datetime.timedelta(days=30)).isoformat()
    n_mp = 0
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
        mp = [head(title, desc, SITE_BASE + murl, image=img, active="matches")]
        mp.append(f'<nav class="crumbs"><a href="/">أخبار</a> › '
                  f'<a href="/matches.html">المباريات</a> › {esc(comp)}</nav>')
        mp.append(f'<h1 class="page-h">مباراة {esc(h_ar)} و{esc(a_ar)}</h1>')
        mp.append('<div class="mlist">')
        mp.append(match_row(m, show_time=True, show_comp=True,
                            goals=match_goals(ge_idx, m)))
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
        _det = match_details_for(md_idx, m)
        if _det:
            mp.append(match_details_html(_det[0], _det[1], h_ar, a_ar))
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
            mp.append(f'<div><dt>{esc(k)}</dt><dd>{esc(str(v))}</dd></div>')
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
        if articles:
            mp.append('<section class="minfo"><h2>آخر الأخبار</h2><ul class="mp-newslist">')
            for a in articles[:4]:
                mp.append(f'<li><a href="/a/{a["article_id"]}.html">{esc(a["title"])}</a></li>')
            mp.append('</ul></section>')
        try:
            from zoneinfo import ZoneInfo
            start_iso = datetime.datetime.fromisoformat(
                f"{m['kickoff']}T{m.get('koff_time') or '00:00'}:00"
            ).replace(tzinfo=ZoneInfo("Africa/Cairo")).isoformat()
        except Exception:
            start_iso = m["kickoff"]
        mp.append(jsonld({
            "@context": "https://schema.org", "@type": "SportsEvent",
            "name": f"{h_ar} ضد {a_ar} — {comp}",
            "startDate": start_iso,
            "eventStatus": ("https://schema.org/EventPostponed"
                            if st == "POSTPONED"
                            else "https://schema.org/EventScheduled"),
            "homeTeam": {"@type": "SportsTeam", "name": h_ar},
            "awayTeam": {"@type": "SportsTeam", "name": a_ar},
        }))
        mp.append(foot())
        write(f"m/{mid}.html", "".join(mp))
        n_mp += 1
        if m["kickoff"] >= sm_cut:      # keep the sitemap focused on ±30 days
            urls.append(murl)
    print(f"  + match pages: {n_mp}")

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
    for comp, slug in COMP_SLUG.items():
        label = comp_label(comp)
        st = st_by_comp.get(comp)
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
            sp2.append(f'<nav class="crumbs"><a href="/">أخبار</a> › '
                       f'<a href="/matches.html">المباريات</a> › ترتيب {esc(label)}</nav>')
            sp2.append(f'<h1 class="page-h">ترتيب {esc(label)} {esc(season)}</h1>')
            sp2.append(f'<p class="hintline">جدول {esc(label)} الكامل — يتحدّث '
                       'تلقائيًا بعد كل مباراة، مع نتائج آخر 5 مباريات لكل فريق.</p>')
            sp2.append(standings_table(comp, st["table"], past=st.get("past"),
                                       season_label=st.get("season_label"),
                                       zeroed=st.get("zeroed"),
                                       form_map=forms.get(comp, {}), embedded=True))
            if sc:
                sp2.append(f'<section class="minfo"><h2>'
                           f'<a href="{sc_url}">هدافو {esc(label)} ←</a></h2>'
                           + scorers_list(sc, "أهداف") + '</section>')
            if up_next:
                sp2.append(f'<section class="minfo"><h2>مباريات {esc(label)} القادمة</h2>'
                           '<div class="mlist">')
                for m in up_next:
                    sp2.append(match_row(m, show_time=True, show_comp=False,
                                         link=match_url(m)))
                sp2.append('</div></section>')
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
            if st and st.get("table"):
                cp.append(f'<p class="hintline">شاهد أيضًا: '
                          f'<a href="{st_url}">جدول ترتيب {esc(label)} كاملًا</a></p>')
            cp.append(foot())
            write(f"scorers/{slug}.html", "".join(cp))
            urls.append(sc_url)
            n_lp += 1
    print(f"  + league pages: {n_lp}")

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
                                    link=match_url(m)))
            pt.append('</div></section>')
        if last_res:
            pt.append(f'<section class="minfo"><h2>آخر نتائج {esc(name)}</h2>'
                      '<div class="mlist">')
            for m in last_res:
                pt.append(match_row(m, show_time=False, show_comp=True,
                                    link=match_url(m)))
            pt.append('</div></section>')
        pt.append(f'<section class="minfo"><h2>آخر أخبار {esc(name)}</h2>')
        if news:
            pt.append('<ul class="mp-newslist">')
            for a in news:
                _t = art_reltime(a)
                pt.append(f'<li><a href="/a/{a["article_id"]}.html">'
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
    pv.append('<h2>إعلانات الطرف الثالث — Google AdSense</h2><p>قد نعرض إعلانات عبر خدمة <b>Google AdSense</b>. تستخدم Google والشركات الشريكة لها ملفات تعريف الارتباط (بما فيها ملف <span dir="ltr">DART cookie</span>) لعرض إعلانات مبنية على زياراتك لهذا الموقع ولمواقع أخرى على الإنترنت.</p>')
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
              '<li><b>أخبار أصلية:</b> يكتب فريق التحرير مقالات بصياغة أصلية بالكامل، بعد التحقق من الخبر '
              'من مصدرين مستقلين على الأقل، دون نقل أو نسخ من مواقع أخرى.</li>'
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
              '<li>المقالات المنشورة باسم فريق التحرير ملك للموقع؛ يُسمح بالاقتباس المختصر مع ذكر '
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
    ed.append('<h2>أصالة المحتوى</h2><ul>'
              '<li>كل مقالاتنا تُكتب بصياغة أصلية بالكامل — الحقائق عامة، أما الصياغة فحقّ لكاتبها، '
              'لذلك لا ننقل ولا نعيد صياغة نصوص المواقع الأخرى.</li>'
              '<li>قسم "عناوين الصحف" تجميعي بطبيعته: يعرض العنوان ويحيل مباشرةً إلى المصدر الأصلي.</li></ul>')
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
                img = a.get("image_url")
                th = (f'<span class="al-th" style="background-image:url(\'{esc(img)}\')"></span>'
                      if img else '<span class="al-th noimg">⚽</span>')
                np_.append(
                    f'<a class="al-row" href="/a/{a["article_id"]}.html">{th}'
                    f'<span class="al-b"><b class="al-t">{esc(a.get("title"))}</b>'
                    f'<span class="al-s">{esc(strip_tags(a.get("summary") or ""))}</span>'
                    f'<span class="al-m">{esc(a.get("author") or "")} · '
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
                f"التفاصيل الكاملة على الموقع 👇\n{SITE_BASE}/a/{a['article_id']}.html\n\n#يلا_سكور")
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
                      f"<news:publication_date>{esc(a['pub_date'])}</news:publication_date>"
                      f"<news:title>{esc(a['title'])}</news:title></news:news></url>")
    ns.append("</urlset>")
    write("sitemap-news.xml", "\n".join(ns))
    if ADSENSE_CLIENT:   # AdSense seller declaration (clears the ads.txt warning)
        write("ads.txt", f"google.com, {ADSENSE_CLIENT.replace('ca-', '')}, DIRECT, f08c47fec0942fa0\n")
    sm = ['<?xml version="1.0" encoding="UTF-8"?>',
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u in urls:
        sm.append(f"  <url><loc>{esc(SITE_BASE + u)}</loc></url>")
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
        if n:
            print(f"  + media files: {n}")

    print(f"Built {len(articles)} articles, {len(matches)} matches -> {DIST}")
    print(f"SITE_BASE = {SITE_BASE}  (edit build_site.py to change, then rebuild)")

def compute_elo(fixtures):
    """competition -> {team: (rating, played)} from finished matches in the
    rounds data, chronological. Plain Elo: start 1500, K=28, home adv +70."""
    out = {}
    for f in fixtures:
        comp = f.get("competition")
        ms = []
        for rd in f.get("rounds", []):
            ms.extend(rd.get("matches", []))
        ms = [m for m in ms if m.get("status") == "FINISHED"
              and m.get("home_score") is not None and m.get("away_score") is not None]
        ms.sort(key=lambda m: (m.get("kickoff") or "", m.get("koff_time") or ""))
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

def team_form(fixtures):
    """competition -> team -> chronological 'W'/'D'/'L' list, from the rounds
    data we already carry (finished matches with scores)."""
    form = {}
    for f in fixtures:
        comp = f.get("competition")
        ms = []
        for rd in f.get("rounds", []):
            ms.extend(rd.get("matches", []))
        ms = [m for m in ms if m.get("status") == "FINISHED"
              and m.get("home_score") is not None and m.get("away_score") is not None]
        ms.sort(key=lambda m: (m.get("kickoff") or "", m.get("koff_time") or ""))
        d = form.setdefault(comp, {})
        for m in ms:
            hs, aw = m["home_score"], m["away_score"]
            d.setdefault(m.get("home"), []).append("W" if hs > aw else "D" if hs == aw else "L")
            d.setdefault(m.get("away"), []).append("W" if aw > hs else "D" if hs == aw else "L")
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
    # 365scores competition emblem (self-hosted through local_crest at build)
    "CAF Champions League": "https://imagecache.365scores.com/image/upload/"
                            "f_png,w_68,h_68,c_limit,q_auto:eco,dpr_2,"
                            "d_Competitions:default1.png/v4/Competitions/624",
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
}
# fixed sidebar order (user's pick 2026-08-13); anything unlisted goes last
COMP_ORDER = ["Egyptian Premier League", "Premier League", "Primera Division",
              "Turkish Super Lig", "Saudi Pro League", "Ligue 1",
              "Bundesliga", "Serie A", "UEFA Champions League",
              "CAF Champions League"]   # last, after UCL (user pick 2026-09-02)

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
        h = "" if m.get("home_score") is None else m.get("home_score")
        a = "" if m.get("away_score") is None else m.get("away_score")
        mid = f'<b class="fx-sc">{h}-{a}</b>'
    else:
        mid = f'<span class="fx-time">{esc(m.get("koff_time") or "")}</span>'
    return (f'<div class="fx">'
            f'<span class="fx-home"><bdi>{esc(ar_team(m.get("home")))}</bdi>{cr(m.get("home_badge"))}</span>'
            f'{mid}'
            f'<span class="fx-away">{cr(m.get("away_badge"))}<bdi>{esc(ar_team(m.get("away")))}</bdi></span></div>')

def league_rounds_panel(comp, fx, embedded=False):
    """FotMob-style rounds panel: a ‹ round › navigator + every round of the
    season, each round's matches grouped by day. JS shows one round at a time."""
    from collections import OrderedDict
    rounds = fx.get("rounds") or []
    current = fx.get("current") or (rounds[0]["round"] if rounds else 1)
    parts = [f'<div class="lg-fix rounds-panel" data-comp="{esc(comp)}" '
             f'data-current="{current}"{"" if embedded else " hidden"}>',
             f'<div class="fx-head">{comp_icon(comp)} {esc(comp_label(comp))}</div>',
             '<div class="rnav">'
             '<button type="button" class="rn-prev" aria-label="الجولة السابقة">‹</button>'
             '<span class="rn-label"></span>'
             '<button type="button" class="rn-next" aria-label="الجولة التالية">›</button></div>',
             '<div class="rounds">']
    for r in rounds:
        parts.append(f'<div class="round" data-round="{r["round"]}" data-label="الجولة {r["round"]}" hidden>')
        days = OrderedDict()
        for m in r.get("matches", []):
            days.setdefault(m.get("kickoff") or "", []).append(m)
        for d in sorted(days.keys()):
            parts.append(f'<div class="fx-day">{esc(fmt_day(d))}</div>')
            for m in days[d]:
                parts.append(fixture_mini(m))
        parts.append('</div>')
    parts.append('</div></div>')
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
# must agree with LIVE_COMPS in worker.js (552,78,649,7,11,17,25,35,572,624).
S365_COMP_IDS = {
    "Egyptian Premier League": 552,
    "Turkish Super Lig": 78,
    "Saudi Pro League": 649,
    "CAF Champions League": 624,
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

def match_goals(idx, m):
    if (m.get("status") or "").upper() not in ("FINISHED", "LIVE"):
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

def match_details_index(entries):
    """Same keying as goal_events_index, but keeps the whole entry
    (goals + cards + subs + lineups) for the /m/ match pages."""
    idx = {}
    for e in entries:
        idx[(f'{_gnorm(e.get("home"))}|{_gnorm(e.get("away"))}',
             e.get("date"))] = e
    return idx

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
        parts.append('<section class="minfo"><h2>أحداث المباراة</h2><div class="tl">')
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
                rc = _rt_class(p.get("rt"))
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

def match_row(m, show_time=False, show_comp=True, goals=None, link=None):
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
    stretch = (f'<a class="mstretch" href="{esc(link)}" '
               f'aria-label="تفاصيل مباراة {esc(ar_team(m.get("home")))} و{esc(ar_team(m.get("away")))}"></a>'
               if link else "")
    return f"""<div class="mrow mrow-{badge[1]}" data-lv data-h="{esc(ar_team(m.get('home')))}" data-a="{esc(ar_team(m.get('away')))}">
  {stretch}{pill}
  <div class="team th">{crest(m.get('home_badge'))}<span><bdi>{esc(ar_team(m.get('home')))}</bdi></span></div>
  <div class="mid">{mid}</div>
  <div class="team ta">{crest(m.get('away_badge'))}<span><bdi>{esc(ar_team(m.get('away')))}</bdi></span></div>
  {comp}
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
@media(max-width:560px){.nf-bar{flex-wrap:wrap;gap:12px}.nf-chips{order:3;flex-basis:100%}}
.nf-bar .page-h{margin:0}
.nf-chips{display:flex;align-items:center;gap:10px}
/* Facebook follow pill — pushed to the row END (left in RTL) */
.nf-fb{margin-inline-start:auto;display:inline-flex;align-items:center;gap:8px;height:44px;padding:0 14px 0 10px;border-radius:22px;background:#1877f2;color:#fff;font-weight:800;font-size:.85rem;text-decoration:none;box-shadow:0 1px 3px rgba(15,23,42,.12);transition:transform .12s,background .12s}
.nf-fb:hover{background:#166fe5;transform:translateY(-1px)}
@media(max-width:560px){.nf-fb{height:40px;width:40px;padding:0;justify-content:center;border-radius:50%}.nf-fb .nf-fbt{display:none}}
.nf-chip{width:44px;height:44px;border-radius:50%;border:1px solid #e2e8f0;background:#fff;display:inline-flex;align-items:center;justify-content:center;padding:0;cursor:pointer;box-shadow:0 1px 3px rgba(15,23,42,.06);transition:transform .12s,border-color .12s,box-shadow .12s}
.nf-chip:hover{transform:translateY(-2px);border-color:var(--green)}
.nf-chip.is-on{border:2px solid #fff;background:#eaf3fa;box-shadow:0 0 0 3px rgba(31,148,211,.35)}   /* white ring inside the blue glow (user 2026-09-02) */
.nf-chip img,.nf-chip svg{width:22px;height:22px;object-fit:contain;display:block}
@media(max-width:560px){.nf-chip{width:40px;height:40px}}
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
/* flipped variant: featured card LEFT, list RIGHT (visual alternation) */
.fmb-flip{grid-template-columns:1fr 1.15fr}
.fmb-flip .fmb-list{grid-column:1;grid-row:1}
.fmb-flip .fmb-feat{grid-column:2;grid-row:1}
@media(max-width:860px){.fmb{grid-template-columns:1fr;gap:12px;padding:12px}.fmb-fb h2{font-size:1.05rem}.fmb-th{width:76px;height:52px}
  .fmb-flip .fmb-feat,.fmb-flip .fmb-list{grid-column:auto;grid-row:auto}}
/* scorers under a finished/live match row (/matches day view) */
.mgoals{grid-column:1/-1;display:grid;grid-template-columns:1fr 40px 1fr;gap:2px 6px;
  margin-top:7px;padding-top:6px;border-top:1px dashed #e8eef4}
.mg-side{display:flex;flex-direction:column;gap:2px;min-width:0;text-align:center}
.mg{font-size:.7rem;color:var(--muted);font-weight:700;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.mg bdi{color:var(--ink)}
.mg-m{font-style:normal;direction:ltr;unicode-bidi:embed;color:#15658f}
.mg small{font-size:.62rem}
@media(max-width:560px){.mgoals{grid-template-columns:1fr 20px 1fr}.mg{font-size:.66rem}}
/* match details: events timeline + starting lineups (/m/<id>.html) */
.tl{display:flex;flex-direction:column}
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
.fv-s,.tk-s{display:inline-flex;align-items:center;gap:1px}
.fv-s span,.tk-s span{font-variant-numeric:tabular-nums}
.fv-s i,.tk-s i{font-style:normal;opacity:.75}
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
