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
import json, os, html, shutil, datetime, hashlib

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

# Feature switches. Flip to True to bring a section back (nav tab, footer link,
# home teaser, its page, and sitemap entry all follow this flag automatically).
SHOW_VIDEOS = False
SHOW_REELS = False

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
        return f"منذ {m} دقيقة"
    h = m // 60
    if h < 24:
        return f"منذ {h} ساعة"
    return f"منذ {h // 24} يوم"

def adsense_slot():
    """Left-column ad slot: the real AdSense unit when configured, else a placeholder."""
    if ADSENSE_CLIENT and ADSENSE_SLOT:
        return ('<ins class="adsbygoogle ad-unit" style="display:block"'
                f' data-ad-client="{ADSENSE_CLIENT}" data-ad-slot="{ADSENSE_SLOT}"'
                ' data-ad-format="auto" data-full-width-responsive="true"></ins>'
                '<script>(adsbygoogle=window.adsbygoogle||[]).push({});</script>')
    return ('<div class="ad-placeholder"><span>مساحة إعلانية</span>'
            '<small>Google AdSense</small></div>')

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
    img = image or (SITE_BASE + "/assets/logo.png")
    ha = " is-active" if active == "home" else ""
    ma = " is-active" if active == "matches" else ""
    sa = " is-active" if active == "stats" else ""
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
<link rel="icon" type="image/png" href="/assets/favicon.png">
<link rel="stylesheet" href="/assets/style.css?v={CSS_VER}">
{ads_head}
</head>
<body>
<header class="site-head">
  <div class="head-crowd" aria-hidden="true"></div>
  <div class="wrap head-in">
    <a class="brand" href="/"><span class="ball">⚽</span> {esc(SITE_NAME)}</a>
  </div>
  {TICKER_HTML}
  <nav class="site-nav"><div class="wrap nav-in">
    <a href="/" class="navtab{ha}"><span class="ico">🏠</span> الرئيسية<span class="nav-en"> | Home</span></a>
    <a href="/matches.html" class="navtab{ma}"><span class="ico">⚽</span> المباريات<span class="nav-en"> | Matches</span></a>
    <a href="/stats.html" class="navtab{sa}"><span class="ico">📊</span> إحصائيات<span class="nav-en"> | Stats</span></a>{vids_tab}{reels_tab}
  </div></nav>
</header>
<main class="wrap">
{adsense_top_banner()}
"""
    return t

def foot():
    year = "2026"
    vids_link = ' · <a href="/videos.html">فيديوهات</a>' if SHOW_VIDEOS else ""
    reels_link = ' · <a href="/reels.html">ريلز</a>' if SHOW_REELS else ""
    return f"""</main>
<footer class="site-foot"><div class="wrap">
  <p>{esc(SITE_NAME)} — {esc(SITE_TAGLINE)}</p>
  <p class="foot-links"><a href="/">الرئيسية</a> · <a href="/news.html">كل الأخبار</a> · <a href="/headlines.html">عناوين الصحف</a> · <a href="/matches.html">المباريات</a> · <a href="/stats.html">إحصائيات</a>{vids_link}{reels_link} · <a href="/about.html">من نحن</a> · <a href="/contact.html">اتصل بنا</a> · <a href="/editorial.html">السياسة التحريرية</a> · <a href="/terms.html">شروط الاستخدام</a> · <a href="/privacy.html">سياسة الخصوصية</a></p>
  <p class="credit">صور عبر Wikimedia Commons / Unsplash — رخص حرة / المجال العام · صورة جماهير الهيدر: Кирилл Венедиктов، CC BY-SA 3.0 (مُجمّعة ومقصوصة) · صور لاعبي منتخب مصر 2026: Bryan Berlin، CC BY-SA 4.0</p>
  <p class="credit">© {year} {esc(SITE_NAME)}</p>
</div></footer>
</body></html>{LIVE_JS}"""

def jsonld(obj):
    return '<script type="application/ld+json">' + json.dumps(obj, ensure_ascii=False) + '</script>'

# Live-scores ticker in the header. Built once per build from matches.json
# (site rebuilds every 30 min, so it stays fresh). Set by build().
TICKER_HTML = ""
CSS_VER = "1"   # cache-buster for /assets/style.css, set from CSS content hash in build()

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
TICKER_TEAMS = [
    ("Real Madrid", None), ("FC Barcelona", None), ("Manchester United", None),
    ("Manchester City", None), ("Arsenal FC", None), ("Liverpool FC", None),
    ("Chelsea FC", None),
    ("الأهلي", "Egyptian Premier League"),
    ("الزمالك", "Egyptian Premier League"),
    ("طرابزون سبور", "Turkish Super Lig"),
]

def _is_ticker_team(m):
    ha = (m.get("home") or "") + "|" + (m.get("away") or "")
    comp = m.get("competition") or ""
    return any(t in ha and (c is None or c == comp) for t, c in TICKER_TEAMS)

def _tk_date(kick):
    """Short Arabic date chip for non-today items: أمس / غدًا / dd/mm."""
    try:
        d = datetime.date.fromisoformat(kick)
        t = datetime.date.fromisoformat(REF_TODAY)
    except Exception:
        return kick or ""
    delta = (d - t).days
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
    "SSC Napoli": "نابولي", "SV 07 Elversberg": "إس في إلفيرسبيرج",
    "SV Werder Bremen": "فيردر بريمن", "Sevilla FC": "إشبيلية",
    "Sport Lisboa e Benfica": "بنفيكا",
    "Sporting Clube de Portugal": "سبورتينج لشبونة",
    "Stade Brestois 29": "بريست", "Stade Rennais FC 1901": "ستاد رين",
    "Sunderland AFC": "سندرلاند", "TSG 1899 Hoffenheim": "هوفنهايم",
    "Torino FC": "تورينو", "Tottenham Hotspur FC": "توتنهام هوتسبر",
    "Toulouse FC": "تولوز", "US Lecce": "ليتشي",
    "US Sassuolo Calcio": "ساسولو", "Udinese Calcio": "أودينيزي",
    "Valencia CF": "فالنسيا", "Venezia FC": "فينيسيا",
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
    picked = [m for m in matches if _is_ticker_team(m)]
    live = [m for m in picked if (m.get("status") or "") == "LIVE"]
    todays = [m for m in picked
              if m.get("kickoff") == REF_TODAY and (m.get("status") or "") != "LIVE"]
    rest = [m for m in picked if m not in live and m not in todays]
    fin = sorted((m for m in rest if m.get("status") == "FINISHED"),
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
            teams = [t for t, c in TICKER_TEAMS
                     if t in ha and (c is None or c == comp)]
            if teams and all(t in seen for t in teams):
                continue
            seen.update(teams)
            kept.append(m)
        return kept

    pool = (live + todays + one_per_team(up)[:10] + one_per_team(fin)[:6])[:14]
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
            mid = f'<b class="tk-s">{sc(m.get("home_score"))}-{sc(m.get("away_score"))}</b><span class="tk-dot"></span>'
        elif st == "FINISHED":
            mid = f'<b class="tk-s">{sc(m.get("home_score"))}-{sc(m.get("away_score"))}</b>'
        else:
            mid = f'<span class="tk-t">{esc(m.get("koff_time") or "")}</span>'
        day = ("" if m.get("kickoff") == REF_TODAY or st == "LIVE"
               else f'<span class="tk-d">{esc(_tk_date(m.get("kickoff")))}</span>')
        its.append(f'<span class="tk-item" data-lv data-h="{esc(ar_team(m.get("home")))}" data-a="{esc(ar_team(m.get("away")))}">{day}{hb}<bdi>{esc(ar_team(m.get("home")))}</bdi> <span class="tk-mid">{mid}</span> <bdi>{esc(ar_team(m.get("away")))}</bdi>{ab}</span>')
    seq = "".join(its)
    return ('<a class="ticker" href="/matches.html" aria-label="نتائج المباريات — اضغط للتفاصيل">'
            f'<div class="tk-track">{seq}{seq}</div></a>')

def transfers_widget(ts, horizontal=False):
    """FotMob-style top-transfers widget. Vertical rail (desktop left column)
    by default; horizontal=True renders a swipeable strip for mobile."""
    its = []
    for t in ts:
        fee = (f'<span class="trf-fee">{esc(t.get("price"))}</span>'
               if t.get("price") else "")
        fc = (f'<img class="trf-b" src="{esc(local_crest(t.get("from_crest")))}" alt="" loading="lazy">'
              if t.get("from_crest") else "")
        tc = (f'<img class="trf-b" src="{esc(local_crest(t.get("to_crest")))}" alt="" loading="lazy">'
              if t.get("to_crest") else "")
        its.append(
            f'<div class="trf-item"><img class="trf-face" src="{esc(local_crest(t.get("img")))}" alt="" loading="lazy"'
            f" onerror=\"this.onerror=null;this.src='/media/ph-ball.svg'\">"
            f'<div class="trf-mid"><b class="trf-name">{esc(t.get("player"))}</b>'
            f'<span class="trf-clubs">{fc}<bdi>{esc(t.get("from"))}</bdi> ← {tc}<bdi>{esc(t.get("to"))}</bdi></span></div>'
            f'{fee}</div>')
    cls = "trf-row" if horizontal else "trf-col"
    return ('<div class="trf-box"><div class="sec-h"><h2 class="page-h">🔁 أبرز الانتقالات</h2></div>'
            f'<div class="{cls}">' + "".join(its) + '</div></div>')

# Client-side live layer: polls /live.json (edge-cached 30s) and patches
# scores/minute into the ticker + match rows IN PLACE. Matching is by
# normalized Arabic team-name pair; anything unmatched just stays on the
# 15-minute static refresh - the site never depends on this script.
LIVE_JS = r"""<script>
(function(){
  var els=[].slice.call(document.querySelectorAll('[data-lv]'));
  if(!els.length||!window.fetch)return;
  function norm(s){return(s||'').replace(/[أإآ]/g,'ا')
    .replace(/ة/g,'ه').replace(/ى/g,'ي').replace(/[.'’]/g,'').replace(/\s+/g,'');}
  var map={};
  els.forEach(function(e){
    var k=norm(e.getAttribute('data-h'))+'|'+norm(e.getAttribute('data-a'));
    (map[k]=map[k]||[]).push(e);
  });
  function paint(e,g){
    var sc=g.hs+' - '+g.as;
    if(e.classList.contains('tk-item')){
      var mid=e.querySelector('.tk-mid'); if(!mid)return;
      mid.innerHTML='<b class="tk-s">'+g.hs+'-'+g.as+'</b>'+(g.live?'<span class="tk-dot"></span>':'');
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
    }
  }
  var timer=null,hadLive=!!document.querySelector('.mrow-live,.tk-dot');
  function tick(){
    fetch('/live.json',{cache:'no-store'}).then(function(r){return r.json();}).then(function(d){
      var gs=d.games||[],any=false;
      gs.forEach(function(g){
        var arr=map[norm(g.h)+'|'+norm(g.a)];
        if(arr){arr.forEach(function(e){paint(e,g);});}
        if(g.live)any=true;
      });
      if(d.ok===false){schedule(hadLive?60000:120000);return;}
      hadLive=any;
      schedule(any?45000:(hadLive?60000:300000));
    }).catch(function(){schedule(hadLive?60000:120000);});
  }
  function schedule(ms){clearTimeout(timer);timer=setTimeout(tick,ms);}
  document.addEventListener('visibilitychange',function(){
    if(document.visibilityState==='visible'){clearTimeout(timer);tick();}
    else clearTimeout(timer);
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
    return (f'<a class="card" href="/a/{a["article_id"]}.html">{thumb}'
            f'<div class="card-b"><h3>{esc(a["title"])}</h3>'
            f'<p class="meta">{esc(a.get("author"))}</p></div></a>')

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
    transfers = load("transfers.json")   # top-transfers widget (home)
    fixtures = load("fixtures.json")      # [{competition, current, rounds:[{round, matches}]}]
    # reels: hand-picked first, then auto-pulled channel uploads (deduped)
    reels = load("reels.json")
    seen_r = {r.get("video_id") for r in reels}
    for r in load("reels_auto.json"):
        if r.get("video_id") not in seen_r:
            reels.append(r)
            seen_r.add(r.get("video_id"))

    global TICKER_HTML
    TICKER_HTML = make_ticker(matches)

    # ---- assets: css + logo ----
    global CSS_VER
    _css = CSS + "\n" + LEGENDS_CSS
    CSS_VER = hashlib.md5(_css.encode("utf-8")).hexdigest()[:8]   # changes only when CSS changes
    with open(os.path.join(DIST, "assets", "style.css"), "w", encoding="utf-8") as f:
        f.write(_css)
    _fav = os.path.join(HERE, "assets-src", "favicon.png")
    if os.path.exists(_fav):
        shutil.copy(_fav, os.path.join(DIST, "assets", "favicon.png"))
    for _logo in (os.path.join(HERE, "assets-src", "logo.png"),
                  os.path.join(HERE, "..", "shared-components", "static-files", "icons", "app-icon-192.png")):
        if os.path.exists(_logo):
            shutil.copy(_logo, os.path.join(DIST, "assets", "logo.png"))
            break

    urls = ["/", "/matches.html"]

    # ---- home ----
    feat = articles[0] if articles else None
    rest = articles[1:] if articles else []
    parts = [head(f"{SITE_NAME} — {SITE_TAGLINE}", SITE_DESC, SITE_BASE + "/",
                  image=(feat and feat.get("image_url")) or None, active="home")]
    parts.append(jsonld({
        "@context": "https://schema.org", "@type": "WebSite",
        "name": SITE_NAME, "url": SITE_BASE + "/",
        "inLanguage": "ar", "description": strip_tags(SITE_DESC)}))
    # two-column home (same widths as before): main content on the RIGHT,
    # reserved empty column on the LEFT. The ad strip (future "Top Transfers"
    # widget, FotMob style) sits ABOVE the latest-news section.
    parts.append('<div class="home-cols"><div class="home-main">')
    parts.append(f'<div class="home-topad">{adsense_slot()}</div>')
    parts.append('<h1 class="page-h">آخر الأخبار</h1>')
    if feat:
        img = feat.get("image_url")
        style = f' style="background-image:url(\'{esc(img)}\')"' if img else ' class="noimg"'
        parts.append(f"""<a class="feat" href="/a/{feat['article_id']}.html">
  <div class="feat-img"{style}></div>
  <div class="feat-body">
    <h2>{esc(feat['title'])}</h2>
    <p>{esc(feat.get('summary'))}</p>
  </div></a>""")
    if rest:
        # horizontal shelf (newest 10); the full archive lives on /news.html
        parts.append('<div class="sec-h"><h2 class="page-h">المزيد من الأخبار</h2>'
                     '<a class="see-all" href="/news.html">كل الأخبار ←</a></div>')
        parts.append('<div class="shelf-wrap">'
                     '<button type="button" class="sh-btn sh-l" aria-label="التالي">‹</button>'
                     '<div class="shelf" id="newsShelf">')
        for a in rest[:10]:
            parts.append(news_card(a))
        parts.append('</div>'
                     '<button type="button" class="sh-btn sh-r" aria-label="السابق">›</button></div>')
        parts.append(SHELF_JS)
    # mobile-only transfers strip (desktop shows the left-column rail instead)
    if transfers:
        parts.append(f'<div class="trf-mob">{transfers_widget(transfers, horizontal=True)}</div>')
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
    if headlines:
        parts.append('<div class="sec-h"><h2 class="page-h">عناوين</h2>'
                     '<a class="see-all" href="/headlines.html">كل العناوين ←</a></div>')
        parts.append('<div class="hgrid">')
        for h in headlines[:24]:
            parts.append(headline_card(h))
        parts.append('</div>')
        parts.append(REL_JS)
    # (matches are NOT shown on the home page - they live on /matches.html)
    parts.append('</div>')  # /home-main
    # left column: FotMob-style top-transfers rail (empty when no data)
    side = transfers_widget(transfers) if transfers else ""
    parts.append(f'<aside class="home-side">{side}</aside>')
    parts.append('</div>')  # /home-cols
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
        p.append(f'<p class="a-meta">{esc(a.get("author"))} · <time datetime="{esc(a.get("pub_date"))}">{esc(a.get("pub_date"))}</time></p>')
        if img:
            p.append(f'<figure class="a-fig"><img class="a-img" src="{esc(img)}" alt="{esc(a["title"])}" loading="eager">')
            cr = a.get("image_credit")
            if cr:
                p.append(f'<figcaption class="a-credit">{esc(cr)}</figcaption>')
            p.append('</figure>')
        if a.get("summary"):
            p.append(f'<p class="lead">{esc(a["summary"])}</p>')
        p.append(f'<div class="a-body">{a.get("body") or ""}</div>')
        p.append('</article>')
        p.append(foot())
        write(f"a/{a['article_id']}.html", "".join(p))
        urls.append(f"/a/{a['article_id']}.html")

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
    st_by_comp = {s.get("competition"): s for s in standings if s.get("table")}
    forms = team_form(fixtures)
    elos = compute_elo(fixtures)
    p.append('<div class="mp-main">')
    # ad strip at the top of the CENTER column - matches-list width only
    p.append(f'<div class="home-topad">{adsense_slot()}</div>')
    for comp, st in st_by_comp.items():
        p.append(standings_table(comp, st.get("table"),
                                 past=st.get("past"), season_label=st.get("season_label"),
                                 zeroed=st.get("zeroed"), form_map=forms.get(comp, {})))
    p.append('<div id="noTable" class="no-table" hidden></div>')  # empty state (league with no table)
    p.append('<div id="daynav" class="daynav" hidden>'
             '<button type="button" id="prevDay" class="dn-arrow" aria-label="اليوم السابق">‹</button>'
             '<span id="dayLabel" class="dn-label"></span>'
             '<button type="button" id="nextDay" class="dn-arrow" aria-label="اليوم التالي">›</button></div>')
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
            p.append(f'<div class="comp" data-comp="{esc(comp)}">')
            if comp:
                p.append(f'<div class="comp-h">{comp_icon(comp)} {esc(comp_label(comp))}</div>')
            p.append('<div class="mlist">')
            for m in ms:
                pr = (win_probs(elos.get(comp, {}), m.get("home"), m.get("away"))
                      if (m.get("status") or "") == "UPCOMING" else None)
                p.append(match_row(m, show_time=True, show_comp=False, probs=pr))
            p.append('</div></div>')
        p.append('<p class="no-comp" hidden>لا مباريات لهذه البطولة في هذا اليوم — جرّب يومًا آخر.</p>')
        p.append('</section>')
    p.append('</div></div>')  # /days /mp-main

    # --- left rail (RTL end): per-league fixtures BY ROUND (shown on select) ---
    fx_by_comp = {f.get("competition"): f for f in fixtures if f.get("rounds")}
    # fallback (leagues with no round data): day-grouped from the day view
    comp_fix = {}
    for d in sorted_days:
        for m in daymap[d]:
            comp_fix.setdefault(m.get("competition") or "", {}).setdefault(d, []).append(m)
    p.append('<aside class="mp-side mp-extra">')
    for c in comp_order:
        if c in fx_by_comp:
            p.append(league_rounds_panel(c, fx_by_comp[c]))
        elif comp_fix.get(c):
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

    # ---- stats dashboard (/stats.html) ----
    STAT_PAL = ["#188038", "#2563eb", "#e11d48", "#f59e0b", "#7c3aed"]

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
            parts.append(f'<rect x="{cx - bw / 2:.1f}" y="{h - mb - bh:.1f}" width="{bw:.1f}" height="{max(bh, 1):.1f}" rx="3" fill="#188038" opacity="0.85"/>')
            parts.append(f'<text x="{cx:.1f}" y="{h - mb - bh - 4:.1f}" font-size="10" fill="#475569" text-anchor="middle">{goals[r]}</text>')
            parts.append(f'<text x="{cx:.1f}" y="{h - 8}" font-size="10" fill="#94a3b8" text-anchor="middle">{r}</text>')
        parts.append('</svg>')
        return f'<div class="chart-wrap">{"".join(parts)}</div>'

    sp = [head(f"إحصائيات وتحليلات — {SITE_NAME}",
               "لوحة إحصائيات مرئية: سباق النقاط، الأهداف في كل جولة، وأرقام الموسم لكل بطولة.",
               SITE_BASE + "/stats.html", active="stats")]
    sp.append('<h1 class="page-h">📊 إحصائيات وتحليلات</h1>')
    sp.append('<p class="hintline">أرقام محسوبة من نتائج الموسم الحالي — تتحدّث تلقائيًا بعد كل جولة.</p>')
    any_stats = False
    for comp in comp_order:
        fx = fx_by_comp.get(comp)
        if not fx:
            continue
        fin = _fin_ms(fx)
        if not fin:
            continue
        any_stats = True
        played = len(fin)
        goals = sum(m["home_score"] + m["away_score"] for _, m in fin)
        big = max((m for _, m in fin),
                  key=lambda m: (m["home_score"] + m["away_score"],
                                 max(m["home_score"], m["away_score"])))
        big_s = f'{big["home_score"]}-{big["away_score"]}'
        big_t = (f'{ar_team(big.get("home"))} {big["home_score"]}-{big["away_score"]} '
                 f'{ar_team(big.get("away"))}')
        top_rows = (st_by_comp.get(comp) or {}).get("table") or []
        top_teams = [r.get("team") for r in top_rows[:5]]
        if not top_teams:
            er = elos.get(comp, {})
            top_teams = [t for t, _ in sorted(er.items(), key=lambda kv: -kv[1][0])[:5]]
        sp.append('<section class="stats-sec">')
        sp.append(f'<h2 class="lt-head">{comp_icon(comp)} {esc(comp_label(comp))}</h2>')
        sp.append('<div class="stat-tiles">'
                  f'<div class="tile"><b>{played}</b><span>مباراة لُعبت</span></div>'
                  f'<div class="tile"><b>{goals}</b><span>هدفًا</span></div>'
                  f'<div class="tile"><b>{goals / played:.2f}</b><span>متوسط الأهداف/مباراة</span></div>'
                  f'<div class="tile" title="{esc(big_t)}"><b>{big_s}</b><span>أكبر نتيجة</span></div>'
                  '</div>')
        race = _pts_race_svg(fin, top_teams)
        if race:
            sp.append('<h3 class="stats-h3">سباق النقاط — المقدمة</h3>')
            sp.append(race)
        gsvg = _goals_svg(fin)
        if gsvg:
            sp.append('<h3 class="stats-h3">الأهداف في كل جولة</h3>')
            sp.append(gsvg)
        sp.append('</section>')
    if not any_stats:
        sp.append('<p class="hintline">لا توجد بيانات كافية بعد — تعود اللوحة للعمل مع انطلاق الجولات.</p>')
    sp.append(foot())
    write("stats.html", "".join(sp))
    urls.append("/stats.html")

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

    # ---- news archive (ALL articles; the home page shows hero + shelf only) ----
    np_ = [head(f"كل الأخبار — {SITE_NAME}",
                "أرشيف أخبار كرة القدم على يلا سكور — كل المقالات والتقارير.",
                SITE_BASE + "/news.html", active="home")]
    np_.append('<h1 class="page-h">كل الأخبار</h1>')
    if articles:
        # calm list rows (thumb + title + summary + date) - the old card grid
        # read as scattered ("شتات") with ragged heights
        np_.append('<div class="alist">')
        for a in articles:
            img = a.get("image_url")
            th = (f'<span class="al-th" style="background-image:url(\'{esc(img)}\')"></span>'
                  if img else '<span class="al-th noimg">⚽</span>')
            np_.append(
                f'<a class="al-row" href="/a/{a["article_id"]}.html">{th}'
                f'<span class="al-b"><b class="al-t">{esc(a.get("title"))}</b>'
                f'<span class="al-s">{esc(strip_tags(a.get("summary") or ""))}</span>'
                f'<span class="al-m">{esc(a.get("author") or "")} · {esc(a.get("pub_date") or "")}</span>'
                f'</span></a>')
        np_.append('</div>')
    else:
        np_.append('<p class="empty-note">لا توجد أخبار بعد.</p>')
    np_.append(foot())
    write("news.html", "".join(np_))
    urls.append("/news.html")

    # ---- headlines page (full aggregated list; home shows only 9) ----
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
        hp.append(REL_JS)
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
    write("robots.txt", f"User-agent: *\nAllow: /\nSitemap: {SITE_BASE}/sitemap.xml\n")
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

def win_probs(elo_comp, home, away):
    """(P_home, P_draw, P_away) as ints summing to 100, or None when the
    ratings are still too raw (fewer than 2 combined finished matches)."""
    if not elo_comp:
        return None
    rh, nh = elo_comp.get(home, (1500.0, 0))
    ra, na = elo_comp.get(away, (1500.0, 0))
    if nh + na < 2:
        return None
    e = 1.0 / (1 + 10 ** ((ra - (rh + 70)) / 400))
    # draw peaks when the sides are level (entertainment-grade model)
    pd_ = 0.26 + 0.10 * (1 - abs(2 * e - 1))
    ph = e * (1 - pd_)
    pa = (1 - e) * (1 - pd_)
    ph, pd_, pa = round(ph * 100), round(pd_ * 100), round(pa * 100)
    ph += 100 - (ph + pd_ + pa)   # rounding drift -> home bucket
    return ph, pd_, pa

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

def standings_table(comp, rows, past=False, season_label="", zeroed=False, form_map=None):
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
    return (f'<div class="ltable" data-comp="{esc(comp)}" hidden>'
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
}
# friendlier display names (data-comp keeps the raw API name for filtering)
COMP_LABEL = {
    "Egyptian Premier League": "الدوري المصري",
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
              "Bundesliga", "Serie A", "UEFA Champions League"]

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

def league_rounds_panel(comp, fx):
    """FotMob-style rounds panel: a ‹ round › navigator + every round of the
    season, each round's matches grouped by day. JS shows one round at a time."""
    from collections import OrderedDict
    rounds = fx.get("rounds") or []
    current = fx.get("current") or (rounds[0]["round"] if rounds else 1)
    parts = [f'<div class="lg-fix rounds-panel" data-comp="{esc(comp)}" data-current="{current}" hidden>',
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

def prob_bar(p):
    """Elo win-probability strip under an upcoming match row."""
    ph, pd_, pa = p
    return (f'<div class="prob" title="توقع تقديري مبني على نتائج الموسم">'
            f'<span class="p-seg p-h" style="width:{ph}%">{ph}%</span>'
            f'<span class="p-seg p-d" style="width:{pd_}%">{pd_}%</span>'
            f'<span class="p-seg p-a" style="width:{pa}%">{pa}%</span></div>')

def match_row(m, show_time=False, show_comp=True, probs=None):
    st = (m.get("status") or "").upper()
    badge = {"LIVE": ("مباشر", "live"), "FINISHED": ("انتهت", "fin"),
             "UPCOMING": ("قادمة", "up")}.get(st, ("", "up"))
    if st == "FINISHED" or st == "LIVE":
        mid = f'<b class="score">{m.get("home_score") if m.get("home_score") is not None else ""} - {m.get("away_score") if m.get("away_score") is not None else ""}</b>'
    else:
        when = (m.get("koff_time") if show_time and m.get("koff_time") else m.get("kickoff"))
        mid = f'<span class="ko">{esc(when)}</span>'
    def crest(u):
        return f'<img src="{esc(local_crest(u))}" alt="" loading="lazy">' if u else '<span class="ph">⚽</span>'
    comp = ""
    if show_comp:
        comp = f'<div class="mcomp">{esc(m.get("competition"))}{(" · " + esc(m.get("channel"))) if m.get("channel") else ""}</div>'
    # only LIVE / FINISHED get a status pill (upcoming shows its time instead)
    pill = (f'<span class="pill pill-{badge[1]}">{esc(badge[0])}</span>'
            if st in ("LIVE", "FINISHED") else "")
    return f"""<div class="mrow mrow-{badge[1]}" data-lv data-h="{esc(ar_team(m.get('home')))}" data-a="{esc(ar_team(m.get('away')))}">
  {pill}
  <div class="team">{crest(m.get('home_badge'))}<span><bdi>{esc(ar_team(m.get('home')))}</bdi></span></div>
  <div class="mid">{mid}</div>
  <div class="team">{crest(m.get('away_badge'))}<span><bdi>{esc(ar_team(m.get('away')))}</bdi></span></div>
  {prob_bar(probs) if probs else ''}
  {comp}
</div>"""

def write(rel, content):
    path = os.path.join(DIST, rel)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

# ---------------------------------------------------------------- styles
CSS = r""":root{
  --green:#1a7f37; --green-d:#0f5e28; --live:#e11d48; --fin:#64748b; --up:#2563eb;
  --ink:#0f172a; --muted:#64748b; --card:#fff; --bg:#eef2f6;
}
*{box-sizing:border-box}
html,body{overflow-x:hidden;max-width:100%}
body{margin:0;font-family:'Segoe UI',Tahoma,Arial,sans-serif;background:var(--bg);color:var(--ink);line-height:1.6}
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
.feat{display:block;position:relative;height:340px;border-radius:18px;overflow:hidden;text-decoration:none;color:#fff;box-shadow:0 14px 34px rgba(15,23,42,.24);margin-bottom:16px;background:linear-gradient(135deg,var(--green-d),#072012)}
.feat-img{position:absolute;inset:0;background-size:cover;background-position:50% 22%}
.feat.noimg .feat-img,.feat-img.noimg{background:linear-gradient(135deg,var(--green),#0a3d1c)}
.feat::after{content:"";position:absolute;inset:0;background:linear-gradient(to top,rgba(3,18,10,.95) 8%,rgba(3,18,10,.15) 70%)}
.feat-body{position:absolute;inset-inline:0;bottom:0;padding:22px 26px;z-index:2}
.feat-body h2{margin:0 0 8px;font-size:1.55rem;font-weight:900;text-shadow:0 2px 10px rgba(0,0,0,.5)}
.feat-body p{margin:0;opacity:.94}
/* grid */
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:15px}
.card{display:block;background:var(--card);border:1px solid #e6ebf1;border-radius:14px;overflow:hidden;text-decoration:none;box-shadow:0 3px 10px rgba(15,23,42,.08);transition:transform .16s,box-shadow .16s}
.card:hover{transform:translateY(-5px);box-shadow:0 16px 30px rgba(15,23,42,.17)}
.card-img{height:140px;background-size:cover;background-position:50% 22%;display:flex;align-items:center;justify-content:center;font-size:2.4rem;color:rgba(255,255,255,.35)}
.card-img.noimg{background:linear-gradient(135deg,var(--green),#0a3d1c)}
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
.lg-item.is-active{background:#eef6ef;color:var(--green-d)}
.lg-ico{font-size:1.05rem;width:22px;text-align:center;flex:0 0 auto}
.lg-logo{width:22px;height:22px;object-fit:contain;flex:0 0 auto}
.lt-head .lg-logo{width:24px;height:24px}
.comp-h .lg-logo,.comp-h .lg-ico{width:20px;height:20px;font-size:1rem;vertical-align:-5px;margin-inline-end:5px}
.no-comp{color:var(--muted);font-weight:700;text-align:center;padding:26px 0}
.mp-news{display:flex;flex-direction:column;gap:9px;margin-bottom:14px}
.mn-item{display:flex;gap:9px;align-items:center;text-decoration:none}
.mn-th{width:58px;height:44px;border-radius:8px;background-size:cover;background-position:center;flex:0 0 auto;background-color:#e6ebf1;display:flex;align-items:center;justify-content:center;color:rgba(255,255,255,.6);font-size:1.1rem}
.mn-th.noimg{background:linear-gradient(135deg,var(--green),#0a3d1c)}
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
/* stats dashboard */
.hintline{color:var(--muted);font-weight:700;font-size:.85rem;margin:-6px 0 18px}
.stats-sec{background:#fff;border:1px solid #e6ebf1;border-radius:14px;padding:18px;margin:0 0 18px;
  box-shadow:0 1px 3px rgba(15,23,42,.05)}
.stats-h3{font-size:.9rem;font-weight:900;color:var(--muted);margin:16px 0 8px}
.stat-tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}
.tile{background:#f8fafc;border:1px solid #eef2f6;border-radius:11px;padding:12px;text-align:center}
.tile b{display:block;font-size:1.05rem;color:#0f5e28}
.tile span{font-size:.72rem;color:var(--muted);font-weight:700}
.chart-wrap{overflow-x:auto}
.chart{width:100%;max-width:680px;height:auto;display:block}
.legend{display:flex;flex-wrap:wrap;gap:12px;margin:6px 0 2px;font-size:.8rem;font-weight:800;color:#334155}
.lgd i{display:inline-block;width:10px;height:10px;border-radius:3px;margin-inline-end:5px;vertical-align:baseline}
/* Elo win-probability strip (upcoming rows on /matches) */
.prob{grid-column:1/-1;display:flex;height:16px;border-radius:8px;overflow:hidden;
  margin-top:8px;font-size:.62rem;font-weight:800;color:#fff;line-height:16px;text-align:center}
.p-h{background:#188038}.p-d{background:#94a3b8}.p-a{background:#b3261e}
.p-seg{min-width:26px}
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
.al-row:hover{background:#f6f9f7}
.al-th{width:150px;height:96px;border-radius:10px;flex:0 0 auto;
  background-size:cover;background-position:center;background-color:#e6ebf1;
  display:flex;align-items:center;justify-content:center;color:rgba(255,255,255,.6);font-size:1.6rem}
.al-th.noimg{background:linear-gradient(135deg,var(--green),#0a3d1c)}
.al-th img{width:100%;height:100%;object-fit:cover;border-radius:10px;display:block}
.al-b{display:flex;flex-direction:column;gap:4px;min-width:0}
.al-t{font-size:1rem;font-weight:900;color:var(--ink);line-height:1.55}
.al-s{font-size:.82rem;color:var(--muted);font-weight:600;line-height:1.6;
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.al-m{font-size:.72rem;color:#94a3b8;font-weight:700}
@media(max-width:560px){
  .al-th{width:104px;height:74px}
  .al-t{font-size:.88rem}
  .al-s{display:none}
}
/* default rail: featured-article card */
.mp-feat{display:flex;flex-direction:column;gap:8px;text-decoration:none;margin-bottom:14px}
.mp-feat-img{width:100%;aspect-ratio:16/10;object-fit:cover;border-radius:10px;display:block}
.mp-feat-t{font-size:.92rem;font-weight:900;color:var(--ink);line-height:1.5}
.mp-feat-cta{font-size:.78rem;font-weight:800;color:var(--green-d, #0f5e28)}
.mp-feat:hover .mp-feat-t{color:#0f5e28}
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
.mrow{display:grid;grid-template-columns:auto 1fr auto 1fr;grid-template-areas:"pill home mid away";gap:8px 10px;align-items:center;background:#fff;border:1px solid #e2e8f0;border-radius:12px;border-inline-start:5px solid var(--green);padding:12px 16px;box-shadow:0 1px 3px rgba(15,23,42,.05)}
.mrow-live{border-inline-start-color:var(--live)}.mrow-fin{border-inline-start-color:var(--fin)}
.pill{grid-area:pill;color:#fff;background:var(--up);border-radius:999px;padding:2px 12px;font-size:.68rem;font-weight:900}
.pill-live{background:var(--live)}.pill-fin{background:var(--fin)}
.team{display:flex;align-items:center;gap:8px;font-weight:800;min-width:0}
.team:first-of-type{grid-area:home;justify-content:flex-end;text-align:end}
.team:last-of-type{grid-area:away}
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
  .team,.team:first-of-type,.team:last-of-type{grid-area:auto;flex-direction:column;justify-content:flex-start;text-align:center;gap:4px;font-size:.76rem;line-height:1.35;min-width:0}
  .team:first-of-type{grid-area:home}
  .team:last-of-type{grid-area:away}
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
.day{max-width:820px;margin:0 auto}
.day-h{color:var(--green-d);font-weight:900;margin:16px 0 10px}
.comp-h{font-weight:800;color:var(--muted);font-size:.8rem;text-transform:uppercase;letter-spacing:.5px;margin:14px 4px 6px}
/* two-column home: main (right) + reserved empty column (left); the ad strip
   (future Top-Transfers widget) sits above the latest-news section */
.home-cols{display:grid;grid-template-columns:2fr 1fr;gap:22px;align-items:start}
.home-main{min-width:0}
.home-topad{margin:16px 0 18px}
.mp-main .home-topad{margin-top:0}  /* align with the rails' top on /matches */
.home-topad .ad-placeholder,.home-topad .ad-unit{position:static;min-height:130px;flex-direction:row}
/* top-transfers rail (left column, FotMob style) + mobile swipe strip */
.trf-box .sec-h{margin-bottom:8px}
.trf-col{display:flex;flex-direction:column;gap:8px}
.trf-mob{display:none;margin:18px 0 4px}
.trf-row{display:flex;gap:10px;overflow-x:auto;scrollbar-width:none;padding-bottom:4px}
.trf-row::-webkit-scrollbar{display:none}
.trf-row .trf-item{flex:0 0 auto}
.trf-item{display:flex;align-items:center;gap:9px;background:#fff;
  border:1px solid #e6ebf1;border-radius:12px;padding:8px 12px;
  box-shadow:0 1px 4px rgba(15,23,42,.05)}
.trf-item .trf-fee{margin-inline-start:auto}
.trf-face{width:42px;height:42px;border-radius:50%;object-fit:cover;background:#eef2f6}
.trf-mid{display:flex;flex-direction:column;gap:2px}
.trf-name{font-size:.8rem;font-weight:800}
.trf-clubs{display:flex;align-items:center;gap:4px;font-size:.7rem;color:var(--muted);font-weight:700}
.trf-b{width:14px;height:14px;object-fit:contain}
.trf-fee{font-size:.7rem;font-weight:800;color:#0f5e28;background:#e8f6ec;
  padding:2px 8px;border-radius:999px;white-space:nowrap}
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
.ad-placeholder{min-height:600px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:6px;text-align:center;color:#94a3b8;font-weight:800;border:2px dashed #cbd5e1;border-radius:14px;background:#fff}
.ad-placeholder small{color:#c3cddb;font-weight:700}
@media(max-width:900px){.home-cols{grid-template-columns:1fr}.home-side{display:none}
  .home-topad{display:none}  /* mobile already has .ad-top */
  .trf-mob{display:block}}   /* transfers strip appears on mobile instead of the rail */
/* external headlines - 3 per row */
.hgrid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}
@media(max-width:760px){.hgrid{grid-template-columns:repeat(2,1fr)}}
@media(max-width:520px){.hgrid{grid-template-columns:1fr}}
.hcard{position:relative;display:flex;flex-direction:column;min-height:128px;background:#fff;border:1px solid #e6ebf1;border-radius:14px;padding:16px 16px 14px;text-decoration:none;overflow:hidden;box-shadow:0 1px 3px rgba(15,23,42,.05);transition:transform .14s,box-shadow .14s,border-color .14s}
.hcard::before{content:"";position:absolute;inset-block:0;inset-inline-start:0;width:4px;background:linear-gradient(var(--green),var(--green-d));opacity:.85;transition:width .14s}
.hcard:hover{transform:translateY(-3px);box-shadow:0 10px 22px rgba(15,23,42,.13);border-color:#d7e4d9}
.hcard:hover::before{width:6px}
.hcard .himg{display:block;height:130px;margin:0 0 10px;border-radius:10px;overflow:hidden;background:#eef2f6}
.hcard .himg:empty{display:none}
.hcard .himg img{width:100%;height:100%;object-fit:cover;display:block;transition:transform .25s}
.hcard:hover .himg img{transform:scale(1.04)}
.hcard h3{margin:0 0 10px;font-size:.95rem;font-weight:800;line-height:1.55;color:var(--ink);display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.hcard .meta{margin:auto 0 0;display:flex;align-items:center;gap:8px;font-size:.75rem;color:#94a3b8;flex-wrap:wrap}
.hsrc{background:#eef6ef;color:var(--green-d);font-weight:800;font-size:.72rem;padding:3px 9px;border-radius:999px;white-space:nowrap;max-width:60%;overflow:hidden;text-overflow:ellipsis}
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
/* videos */
.sec-h{display:flex;align-items:baseline;justify-content:space-between;gap:12px;flex-wrap:wrap}
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
.vthumb.noimg{background:linear-gradient(135deg,var(--green),#0a3d1c)}
.vplay{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);width:56px;height:56px;border-radius:50%;background:rgba(225,29,72,.92);color:#fff;font-size:1.35rem;display:flex;align-items:center;justify-content:center;padding-left:4px;box-shadow:0 4px 14px rgba(0,0,0,.35);transition:transform .14s,background .14s}
.vthumb:hover .vplay{transform:translate(-50%,-50%) scale(1.08);background:#e11d48}
.vframe{width:100%;aspect-ratio:16/9;border:0;display:block;background:#000}
.vb{padding:12px 14px}
.vb h3{margin:0 0 6px;font-size:.95rem;font-weight:800;line-height:1.5;color:var(--ink);display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.empty-note{color:var(--muted);font-weight:700;padding:20px 0}
/* reels: TikTok-style vertical swipe feed (one reel per screen) */
.reels-banner{display:flex;align-items:center;gap:16px;margin:6px 0 4px;padding:14px 16px;
  border-radius:16px;text-decoration:none;color:#fff;
  background:linear-gradient(135deg,var(--green-d),#06170d);
  box-shadow:0 8px 22px rgba(6,23,13,.35);transition:transform .15s,box-shadow .15s}
.reels-banner:hover{transform:translateY(-3px);box-shadow:0 14px 30px rgba(6,23,13,.45)}
.reels-banner img{width:92px;aspect-ratio:9/16;object-fit:cover;border-radius:12px;
  border:2px solid rgba(255,255,255,.35);flex:0 0 auto}
.rb-body h2{margin:0 0 4px;font-size:1.15rem;font-weight:900}
.rb-body p{margin:0 0 10px;font-size:.85rem;color:#cfe6d6}
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
.ticker{display:block;background:#06170d;overflow:hidden;text-decoration:none;
  border-top:1px solid rgba(255,255,255,.07);
  position:relative;clip-path:inset(0)}  /* WebKit: animated transform escapes overflow:hidden */
.tk-track{display:inline-flex;width:max-content;align-items:center;gap:30px;
  padding:6px 0;animation:tkmove 45s linear infinite}
.ticker:hover .tk-track{animation-play-state:paused}
.tk-item{display:inline-flex;align-items:center;gap:6px;color:#dbe7de;
  font-size:.78rem;font-weight:700;white-space:nowrap}
.tk-b{width:16px;height:16px;object-fit:contain}
.tk-s{color:#fff;background:rgba(255,255,255,.14);padding:1px 8px;border-radius:6px}
.tk-t{color:#8fe4a9;font-weight:800}
.tk-d{color:#9fb8a8;font-size:.68rem;font-weight:800;border:1px solid rgba(255,255,255,.18);
  padding:0 6px;border-radius:5px}
.tk-dot{width:7px;height:7px;border-radius:50%;background:#ff4d6d;
  animation:tkpulse 1.2s ease-in-out infinite}
@keyframes tkmove{from{transform:translateX(0)}to{transform:translateX(50%)}}
@keyframes tkpulse{0%,100%{opacity:1}50%{opacity:.2}}
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
  function applyFilter(sec){
    var any=false;
    [].slice.call(sec.querySelectorAll('.comp')).forEach(function(c){
      var vis=!filter||c.getAttribute('data-comp')===filter;
      c.style.display=vis?'':'none'; if(vis) any=true;
    });
    var note=sec.querySelector('.no-comp'); if(note) note.hidden=any;
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
  var tables=[].slice.call(document.querySelectorAll('.ltable'));
  var lgItems=[].slice.call(document.querySelectorAll('.lg-item'));
  /* the daynav has CSS display:flex which overrides the [hidden] attribute,
     so toggle it via inline style.display instead */
  var noTable=document.getElementById('noTable');
  var mpDefault=document.getElementById('mpDefault');
  var fixPanels=[].slice.call(document.querySelectorAll('.lg-fix'));
  var mpage=document.querySelector('.mpage');
  function matchesShown(on){ nav.style.display = on ? '' : 'none'; wrap.style.display = on ? '' : 'none'; }
  function reset(){                 /* all-matches view (default / top nav tab) */
    filter='';
    lgItems.forEach(function(x){ x.classList.remove('is-active'); });
    tables.forEach(function(t){ t.hidden=true; });
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
    var table=tables.filter(function(t){return t.getAttribute('data-comp')===filter;})[0];
    tables.forEach(function(t){ t.hidden = t!==table; });
    matchesShown(false);                              /* never show fixtures in the centre */
    if(noTable) noTable.hidden = !!table;             /* no table -> empty placeholder */
    /* left rail: this league's fixtures instead of news */
    var fx=fixPanels.filter(function(f){return f.getAttribute('data-comp')===filter;})[0];
    fixPanels.forEach(function(f){ f.hidden = f!==fx; });
    if(mpDefault) mpDefault.hidden = !!fx;            /* has fixtures -> hide news */
    if(mpage) mpage.classList.add('league-view');
    window.scrollTo({top:0,behavior:'smooth'});
  }
  lgItems.forEach(function(b){ b.addEventListener('click',function(){ selectLeague(b); }); });
  var mTab=document.querySelector('a.navtab[href="/matches.html"]');
  if(mTab) mTab.addEventListener('click',function(e){ e.preventDefault(); reset(); window.scrollTo({top:0,behavior:'smooth'}); });
  show(idx);
})();
</script>"""

# client-side relative time ("منذ X") - always accurate to the visitor's clock.
REL_JS = """<script>
(function(){
  function rel(iso){
    var d=new Date(iso); if(isNaN(d.getTime())) return null;
    var s=Math.floor((Date.now()-d.getTime())/1000); if(s<0) s=0;
    if(s<60) return 'منذ لحظات';
    var m=Math.floor(s/60); if(m<60) return 'منذ '+m+' دقيقة';
    var h=Math.floor(m/60); if(h<24) return 'منذ '+h+' ساعة';
    return 'منذ '+Math.floor(h/24)+' يوم';
  }
  document.querySelectorAll('time.reltime').forEach(function(el){
    var t=rel(el.getAttribute('datetime'));
    if(t) el.textContent=t;
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
