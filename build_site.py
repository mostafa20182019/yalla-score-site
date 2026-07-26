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
import json, os, html, shutil, datetime

# ---------------------------------------------------------------- config
SITE_BASE = "https://old-credit-e926.mustafa-abdelsalam95.workers.dev"  # Cloudflare Workers static
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
ADSENSE_CLIENT = ""
ADSENSE_SLOT = ""

# Optional contact email shown on the Privacy Policy page (leave "" to omit).
CONTACT_EMAIL = ""

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

def head(title, desc, url, image=None, og_type="website", active=""):
    desc = strip_tags(desc)[:300]
    img = image or (SITE_BASE + "/assets/logo.png")
    ha = " is-active" if active == "home" else ""
    ma = " is-active" if active == "matches" else ""
    va = " is-active" if active == "videos" else ""
    ra = " is-active" if active == "reels" else ""
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
<link rel="icon" href="/assets/logo.png">
<link rel="stylesheet" href="/assets/style.css">
{ads_head}
</head>
<body>
<header class="site-head">
  <div class="wrap head-in">
    <a class="brand" href="/"><span class="ball">⚽</span> {esc(SITE_NAME)}<span class="beta">بث تجريبي</span></a>
    <div class="legends" aria-hidden="true"><div class="lg-track">{LEGENDS_HTML}</div></div>
  </div>
  {TICKER_HTML}
  <nav class="site-nav"><div class="wrap nav-in">
    <a href="/" class="navtab{ha}"><span class="ico">🏠</span> الرئيسية<span class="nav-en"> | Home</span></a>
    <a href="/matches.html" class="navtab{ma}"><span class="ico">⚽</span> المباريات<span class="nav-en"> | Matches</span></a>
    <a href="/videos.html" class="navtab{va}"><span class="ico">🎬</span> فيديوهات<span class="nav-en"> | Videos</span></a>
    <a href="/reels.html" class="navtab{ra}"><span class="ico">⚡</span> ريلز<span class="nav-en"> | Reels</span></a>
  </div></nav>
</header>
<main class="wrap">
"""
    return t

def foot():
    year = "2026"
    return f"""</main>
<footer class="site-foot"><div class="wrap">
  <p>{esc(SITE_NAME)} — {esc(SITE_TAGLINE)}</p>
  <p class="foot-links"><a href="/">الرئيسية</a> · <a href="/news.html">كل الأخبار</a> · <a href="/headlines.html">عناوين الصحف</a> · <a href="/matches.html">المباريات</a> · <a href="/videos.html">فيديوهات</a> · <a href="/reels.html">ريلز</a> · <a href="/privacy.html">سياسة الخصوصية</a></p>
  <p class="credit">صور عبر Wikimedia Commons / Unsplash — رخص حرة / المجال العام</p>
  <p class="credit">© {year} {esc(SITE_NAME)}</p>
</div></footer>
</body></html>"""

def jsonld(obj):
    return '<script type="application/ld+json">' + json.dumps(obj, ensure_ascii=False) + '</script>'

# Live-scores ticker in the header. Built once per build from matches.json
# (site rebuilds every 30 min, so it stays fresh). Set by build().
TICKER_HTML = ""

# Big clubs for the ticker's padding pool (substring match on football-data
# team names). World Cup matches always count as "big".
BIG_TEAMS = ["Real Madrid", "FC Barcelona", "Atlético", "Manchester City",
             "Manchester United", "Liverpool", "Arsenal", "Chelsea", "Tottenham",
             "Bayern", "Dortmund", "Paris Saint-Germain", "Juventus",
             "Internazionale", "AC Milan", "Napoli", "Marseille"]

def _is_big(m):
    if "World Cup" in (m.get("competition") or ""):
        return True
    ha = (m.get("home") or "") + "|" + (m.get("away") or "")
    return any(t in ha for t in BIG_TEAMS)

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

def make_ticker(matches):
    """Header ticker: LIVE first, then ALL of today's matches; on quiet days
    pad with BIG-club matches only (nearest finished + next upcoming), each
    carrying a short date chip. Returns "" when there's nothing to show."""
    if not matches:
        return ""
    live = [m for m in matches if (m.get("status") or "") == "LIVE"]
    todays = [m for m in matches
              if m.get("kickoff") == REF_TODAY and (m.get("status") or "") != "LIVE"]
    pool = live + todays
    if len(pool) < 4:
        rest = [m for m in matches if m not in pool and _is_big(m)]
        fin = sorted((m for m in rest if m.get("status") == "FINISHED"),
                     key=lambda m: (m.get("kickoff") or "", m.get("koff_time") or ""),
                     reverse=True)
        up = sorted((m for m in rest if m.get("status") == "UPCOMING"),
                    key=lambda m: (m.get("kickoff") or "", m.get("koff_time") or ""))
        pool += fin[:6] + up[:6]
    pool = pool[:14]
    if not pool:
        return ""
    sc = lambda v: "-" if v is None else v
    its = []
    for m in pool:
        st = m.get("status")
        hb = (f'<img class="tk-b" src="{esc(m.get("home_badge"))}" alt="" loading="lazy">'
              if m.get("home_badge") else "")
        ab = (f'<img class="tk-b" src="{esc(m.get("away_badge"))}" alt="" loading="lazy">'
              if m.get("away_badge") else "")
        if st == "LIVE":
            mid = f'<b class="tk-s">{sc(m.get("home_score"))}-{sc(m.get("away_score"))}</b><span class="tk-dot"></span>'
        elif st == "FINISHED":
            mid = f'<b class="tk-s">{sc(m.get("home_score"))}-{sc(m.get("away_score"))}</b>'
        else:
            mid = f'<span class="tk-t">{esc(m.get("koff_time") or "")}</span>'
        day = ("" if m.get("kickoff") == REF_TODAY or st == "LIVE"
               else f'<span class="tk-d">{esc(_tk_date(m.get("kickoff")))}</span>')
        its.append(f'<span class="tk-item">{day}{hb}<bdi>{esc(m.get("home"))}</bdi> {mid} <bdi>{esc(m.get("away"))}</bdi>{ab}</span>')
    seq = "".join(its)
    return ('<a class="ticker" href="/matches.html" aria-label="نتائج المباريات — اضغط للتفاصيل">'
            f'<div class="tk-track">{seq}{seq}</div></a>')

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
    return (f'<a class="hcard" href="{esc(h.get("link"))}" target="_blank" rel="noopener nofollow">'
            f'<span class="go" aria-hidden="true">↗</span>'
            f'<h3>{esc(t)}</h3>'
            f'<p class="meta"><span class="hsrc">{src}</span><span class="reltime-wrap">{timeel}</span></p></a>')

def news_card(a):
    """One article card (used by the home shelf and the /news.html archive)."""
    img = a.get("image_url")
    thumb = (f'<div class="card-img" style="background-image:url(\'{esc(img)}\')"></div>'
             if img else '<div class="card-img noimg">⚽</div>')
    return (f'<a class="card" href="/a/{a["article_id"]}.html">{thumb}'
            f'<div class="card-b"><h3>{esc(a["title"])}</h3>'
            f'<p class="meta">{esc(a.get("author"))} · {esc(a.get("pub_date"))}</p></div></a>')

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
    with open(os.path.join(DIST, "assets", "style.css"), "w", encoding="utf-8") as f:
        f.write(CSS + "\n" + LEGENDS_CSS)
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
    # two-column home: main content on the RIGHT, empty reserved column on the LEFT
    parts.append('<div class="home-cols"><div class="home-main">')
    parts.append('<h1 class="page-h">أخبارنا</h1>')
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
        # horizontal shelf (newest 12); the full archive lives on /news.html
        parts.append('<div class="sec-h"><h2 class="page-h">المزيد من الأخبار</h2>'
                     '<a class="see-all" href="/news.html">كل الأخبار ←</a></div>')
        parts.append('<div class="shelf-wrap">'
                     '<button type="button" class="sh-btn sh-l" aria-label="التالي">‹</button>'
                     '<div class="shelf" id="newsShelf">')
        for a in rest[:12]:
            parts.append(news_card(a))
        parts.append('</div>'
                     '<button type="button" class="sh-btn sh-r" aria-label="السابق">›</button></div>')
        parts.append(SHELF_JS)
    # latest videos teaser (full library lives on /videos.html)
    if videos:
        parts.append('<div class="sec-h"><h2 class="page-h">أحدث الفيديوهات</h2>'
                     '<a class="see-all" href="/videos.html">كل الفيديوهات ←</a></div>')
        parts.append('<div class="vstrip">')
        for v in videos[:3]:
            parts.append(video_facade(v))
        parts.append('</div>')
        parts.append(VIDEO_JS)
    # reels teaser: ONE banner -> the swipe feed on /reels.html
    if reels:
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
    # external headlines teaser (9 = 3 rows; the full list lives on /headlines.html)
    if headlines:
        parts.append('<div class="sec-h"><h2 class="page-h">عناوين من مصادر أخرى</h2>'
                     '<a class="see-all" href="/headlines.html">كل العناوين ←</a></div>')
        parts.append('<div class="hgrid">')
        for h in headlines[:9]:
            parts.append(headline_card(h))
        parts.append('</div>')
        parts.append(REL_JS)
    # (matches are NOT shown on the home page - they live on /matches.html)
    parts.append('</div>')  # /home-main
    parts.append(f'<aside class="home-side">{adsense_slot()}</aside>')  # ad slot / placeholder
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
            p.append(f'<img class="a-img" src="{esc(img)}" alt="{esc(a["title"])}" loading="eager">')
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
    # distinct competitions across the feed (for the leagues sidebar)
    comp_order = []
    for m in matches:
        c = m.get("competition") or ""
        if c and c not in comp_order:
            comp_order.append(c)

    p = [head(f"مواعيد ونتائج المباريات — {SITE_NAME}",
              "مواعيد ونتائج مباريات كرة القدم بتوقيت القاهرة على يلا سكور.",
              SITE_BASE + "/matches.html", active="matches")]
    p.append('<h1 class="page-h">المباريات</h1>')
    p.append('<div class="mpage">')

    # --- right rail (RTL start): leagues filter ---
    p.append('<aside class="mp-side mp-leagues"><h2 class="mp-h">البطولات</h2><div class="lg-list">')
    for c in comp_order:
        p.append(f'<button type="button" class="lg-item" data-comp="{esc(c)}">'
                 f'{comp_icon(c)} {esc(comp_label(c))}</button>')
    p.append('</div></aside>')

    # --- center: league tables (hidden) + day navigator + days ---
    st_by_comp = {s.get("competition"): s.get("table") for s in standings if s.get("table")}
    p.append('<div class="mp-main">')
    for comp, table in st_by_comp.items():
        p.append(standings_table(comp, table))
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
        for comp, ms in comps.items():
            p.append(f'<div class="comp" data-comp="{esc(comp)}">')
            if comp:
                p.append(f'<div class="comp-h">{comp_icon(comp)} {esc(comp_label(comp))}</div>')
            p.append('<div class="mlist">')
            for m in ms:
                p.append(match_row(m, show_time=True, show_comp=False))
            p.append('</div></div>')
        p.append('<p class="no-comp" hidden>لا مباريات لهذه البطولة في هذا اليوم — جرّب يومًا آخر.</p>')
        p.append('</section>')
    p.append('</div></div>')  # /days /mp-main

    # --- left rail (RTL end): latest news + ad ---
    p.append('<aside class="mp-side mp-extra">')
    if articles:
        p.append('<h2 class="mp-h">أحدث الأخبار</h2><div class="mp-news">')
        for a in articles[:4]:
            img = a.get("image_url")
            th = (f'<span class="mn-th" style="background-image:url(\'{esc(img)}\')"></span>'
                  if img else '<span class="mn-th noimg">⚽</span>')
            p.append(f'<a class="mn-item" href="/a/{a["article_id"]}.html">{th}'
                     f'<span class="mn-b"><span class="mn-t">{esc(a["title"])}</span>'
                     f'<span class="mn-d">{esc(a.get("pub_date"))}</span></span></a>')
        p.append('</div>')
    p.append(f'<div class="mp-ad">{adsense_slot()}</div>')
    p.append('</aside>')

    p.append('</div>')  # /mpage
    p.append(MATCHES_JS)
    p.append(foot())
    write("matches.html", "".join(p))

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

    # ---- news archive (ALL articles; the home page shows hero + shelf only) ----
    np_ = [head(f"كل الأخبار — {SITE_NAME}",
                "أرشيف أخبار كرة القدم على يلا سكور — كل المقالات والتقارير.",
                SITE_BASE + "/news.html", active="home")]
    np_.append('<h1 class="page-h">كل الأخبار</h1>')
    if articles:
        np_.append('<div class="grid">')
        for a in articles:
            np_.append(news_card(a))
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
        hp.append('<div class="hgrid">')
        for h in headlines:
            hp.append(headline_card(h))
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
    write("videos.html", "".join(vp))
    urls.append("/videos.html")

    # ---- robots + sitemap ----
    write("robots.txt", f"User-agent: *\nAllow: /\nSitemap: {SITE_BASE}/sitemap.xml\n")
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

def standings_table(comp, rows):
    """League standings table (FotMob-style). Hidden until its league is picked."""
    def cell(v):
        return "0" if v is None else esc(str(v))
    body = []
    for r in rows:
        crest = (f'<img src="{esc(r.get("crest"))}" alt="" loading="lazy">'
                 if r.get("crest") else "")
        body.append(
            f'<tr><td class="lt-pos">{cell(r.get("pos"))}</td>'
            f'<td class="lt-team">{crest}<bdi>{esc(r.get("team"))}</bdi></td>'
            f'<td>{cell(r.get("played"))}</td><td>{cell(r.get("won"))}</td>'
            f'<td>{cell(r.get("draw"))}</td><td>{cell(r.get("lost"))}</td>'
            f'<td>{cell(r.get("gf"))}</td><td>{cell(r.get("ga"))}</td>'
            f'<td>{cell(r.get("gd"))}</td><td class="lt-pts">{cell(r.get("pts"))}</td></tr>')
    return (f'<div class="ltable" data-comp="{esc(comp)}" hidden>'
            f'<div class="lt-head">{comp_icon(comp)} جدول ترتيب {esc(comp_label(comp))}</div>'
            f'<div class="lt-scroll"><table class="lt"><thead><tr>'
            f'<th class="lt-pos">#</th><th class="lt-team">الفريق</th>'
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
}
# friendlier display names (data-comp keeps the raw API name for filtering)
COMP_LABEL = {"Primera Division": "La Liga"}

def comp_label(name):
    return COMP_LABEL.get(name, name or "")

def comp_icon(name):
    url = COMP_LOGO.get(name)
    if url:
        return f'<img class="lg-logo" src="{esc(url)}" alt="" loading="lazy">'
    return f'<span class="lg-ico">{comp_emoji(name)}</span>'

def comp_emoji(name):
    n = (name or "").lower()
    if "world cup" in n or "مونديال" in n or "كأس العالم" in n: return "🏆"
    if "premier" in n: return "🦁"
    if "primera" in n or "laliga" in n or "la liga" in n: return "🇪🇸"
    if "serie a" in n: return "🇮🇹"
    if "bundesliga" in n: return "🇩🇪"
    if "ligue 1" in n: return "🇫🇷"
    if "champions" in n: return "⭐"
    return "⚽"

def match_row(m, show_time=False, show_comp=True):
    st = (m.get("status") or "").upper()
    badge = {"LIVE": ("مباشر", "live"), "FINISHED": ("انتهت", "fin"),
             "UPCOMING": ("قادمة", "up")}.get(st, ("", "up"))
    if st == "FINISHED" or st == "LIVE":
        mid = f'<b class="score">{m.get("home_score") if m.get("home_score") is not None else ""} - {m.get("away_score") if m.get("away_score") is not None else ""}</b>'
    else:
        when = (m.get("koff_time") if show_time and m.get("koff_time") else m.get("kickoff"))
        mid = f'<span class="ko">{esc(when)}</span>'
    def crest(u):
        return f'<img src="{esc(u)}" alt="" loading="lazy">' if u else '<span class="ph">⚽</span>'
    comp = ""
    if show_comp:
        comp = f'<div class="mcomp">{esc(m.get("competition"))}{(" · " + esc(m.get("channel"))) if m.get("channel") else ""}</div>'
    # only LIVE / FINISHED get a status pill (upcoming shows its time instead)
    pill = (f'<span class="pill pill-{badge[1]}">{esc(badge[0])}</span>'
            if st in ("LIVE", "FINISHED") else "")
    return f"""<div class="mrow mrow-{badge[1]}">
  {pill}
  <div class="team">{crest(m.get('home_badge'))}<span><bdi>{esc(m.get('home'))}</bdi></span></div>
  <div class="mid">{mid}</div>
  <div class="team">{crest(m.get('away_badge'))}<span><bdi>{esc(m.get('away'))}</bdi></span></div>
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
body{margin:0;font-family:'Segoe UI',Tahoma,Arial,sans-serif;background:var(--bg);color:var(--ink);line-height:1.6}
.wrap{max-width:1600px;margin:0 auto;padding:0 20px}
a{color:inherit}
.site-head{background:linear-gradient(90deg,var(--green-d),var(--green));box-shadow:0 2px 10px rgba(15,23,42,.18);position:sticky;top:0;z-index:9}
.head-in{display:flex;align-items:center;height:78px}
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
.feat-img{position:absolute;inset:0;background-size:cover;background-position:center}
.feat.noimg .feat-img,.feat-img.noimg{background:linear-gradient(135deg,var(--green),#0a3d1c)}
.feat::after{content:"";position:absolute;inset:0;background:linear-gradient(to top,rgba(3,18,10,.95) 8%,rgba(3,18,10,.15) 70%)}
.feat-body{position:absolute;inset-inline:0;bottom:0;padding:22px 26px;z-index:2}
.feat-body h2{margin:0 0 8px;font-size:1.55rem;font-weight:900;text-shadow:0 2px 10px rgba(0,0,0,.5)}
.feat-body p{margin:0;opacity:.94}
/* grid */
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:15px}
.card{display:block;background:var(--card);border:1px solid #e6ebf1;border-radius:14px;overflow:hidden;text-decoration:none;box-shadow:0 3px 10px rgba(15,23,42,.08);transition:transform .16s,box-shadow .16s}
.card:hover{transform:translateY(-5px);box-shadow:0 16px 30px rgba(15,23,42,.17)}
.card-img{height:140px;background-size:cover;background-position:center;display:flex;align-items:center;justify-content:center;font-size:2.4rem;color:rgba(255,255,255,.35)}
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
.a-img{width:100%;max-height:400px;object-fit:cover;border-radius:14px;margin:14px 0}
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
.lt tbody tr{border-bottom:1px solid #f1f5f9}
.lt tbody tr:hover{background:#f8fafc}
.lt .lt-pos{width:26px;color:var(--muted);font-weight:800}
.lt .lt-team{text-align:start;display:flex;align-items:center;gap:8px;font-weight:800;min-width:150px}
.lt .lt-team img{width:22px;height:22px;object-fit:contain;flex:0 0 auto}
.lt .lt-pts{font-weight:900;color:var(--green-d)}
@media(max-width:1080px){.mpage{grid-template-columns:210px minmax(0,1fr)}.mp-extra{display:none}}
@media(max-width:760px){
  .mpage{grid-template-columns:1fr;gap:10px}
  .mp-leagues{position:static;padding:8px 10px}
  .mp-leagues .mp-h{display:none}
  .lg-list{flex-direction:row;overflow-x:auto;scrollbar-width:none;gap:6px}
  .lg-list::-webkit-scrollbar{display:none}
  .lg-item{white-space:nowrap;flex:0 0 auto;padding:7px 12px;border:1px solid #e6ebf1;border-radius:999px}
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
  .mrow{grid-template-columns:1fr auto 1fr;grid-template-areas:"home mid away";position:relative;padding:30px 10px 12px}
  .pill{position:absolute;top:8px;inset-inline-start:10px;grid-area:auto}
  .team,.team:first-of-type,.team:last-of-type{grid-area:auto;flex-direction:column;justify-content:flex-start;text-align:center;gap:4px;font-size:.78rem;line-height:1.35}
  .team:first-of-type{grid-area:home}
  .team:last-of-type{grid-area:away}
  .team img{width:30px;height:30px}
  .mid{min-width:56px}
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
/* two-column home: main (right) + reserved empty column (left) */
.home-cols{display:grid;grid-template-columns:2fr 1fr;gap:22px;align-items:start}
.home-main{min-width:0}
.home-side{min-height:320px}
.ad-placeholder,.ad-unit{position:sticky;top:120px}
.ad-placeholder{min-height:600px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:6px;text-align:center;color:#94a3b8;font-weight:800;border:2px dashed #cbd5e1;border-radius:14px;background:#fff}
.ad-placeholder small{color:#c3cddb;font-weight:700}
@media(max-width:900px){.home-cols{grid-template-columns:1fr}.home-side{display:none}}
/* external headlines - 3 per row */
.hgrid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}
@media(max-width:760px){.hgrid{grid-template-columns:repeat(2,1fr)}}
@media(max-width:520px){.hgrid{grid-template-columns:1fr}}
.hcard{position:relative;display:flex;flex-direction:column;min-height:128px;background:#fff;border:1px solid #e6ebf1;border-radius:14px;padding:16px 16px 14px;text-decoration:none;overflow:hidden;box-shadow:0 1px 3px rgba(15,23,42,.05);transition:transform .14s,box-shadow .14s,border-color .14s}
.hcard::before{content:"";position:absolute;inset-block:0;inset-inline-start:0;width:4px;background:linear-gradient(var(--green),var(--green-d));opacity:.85;transition:width .14s}
.hcard:hover{transform:translateY(-3px);box-shadow:0 10px 22px rgba(15,23,42,.13);border-color:#d7e4d9}
.hcard:hover::before{width:6px}
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
@media(max-width:640px){.feat{height:260px}.feat-body h2{font-size:1.2rem}.article{padding:18px}}
"""

# ---- legends header strip (free CC / public-domain photos, same as the app) ----
# 8 hand-picked legends (name for tooltip/alt, 200px Wikimedia thumb).
# Every photo was visually reviewed 2026-07-25 — face-centered, good quality.
LEGENDS = [
  ("محمد صلاح",         "https://commons.wikimedia.org/wiki/Special:FilePath/Mohamed_Salah_2018.jpg?width=200"),
  ("محمد أبو تريكة",    "https://commons.wikimedia.org/wiki/Special:FilePath/Aboutrika2011.jpg?width=200"),
  ("محمود الخطيب",      "https://commons.wikimedia.org/wiki/Special:FilePath/Mahmoud_El-Khatib_(1977).jpg?width=200"),
  ("حازم إمام",         "https://commons.wikimedia.org/wiki/Special:FilePath/Hazem_Emam.png?width=200"),
  ("ليونيل ميسي",       "https://commons.wikimedia.org/wiki/Special:FilePath/Lionel_Messi_20180626.jpg?width=200"),
  ("كريستيانو رونالدو", "https://commons.wikimedia.org/wiki/Special:FilePath/Cristiano_Ronaldo_2018_(cropped).jpg?width=200"),
  ("زين الدين زيدان",   "https://commons.wikimedia.org/wiki/Special:FilePath/Zinedine_Zidane_by_Tasnim_01.jpg?width=200"),
  ("لامين يامال",       "https://commons.wikimedia.org/wiki/Special:FilePath/Lamine_Yamal_France_v_Spain_7.24.26-142_(cropped).jpg?width=200"),
]
# 8 big static tiles (no marquee): name tooltip via title/alt.
LEGENDS_HTML = "".join(
    f'<img src="{u}" alt="{n}" title="{n}" loading="lazy">' for n, u in LEGENDS)

LEGENDS_CSS = """
/* legends strip: 8 big face circles, static, name on hover */
.legends{flex:1;min-width:0;margin-inline-start:20px;display:flex;
  justify-content:center;overflow-x:auto;scrollbar-width:none}
.legends::-webkit-scrollbar{display:none}
.lg-track{display:inline-flex;align-items:center;gap:14px}
.legends img{width:62px;height:62px;border-radius:50%;object-fit:cover;
  object-position:50% 22%;flex:0 0 auto;
  border:2px solid rgba(255,255,255,.45);
  box-shadow:0 2px 8px rgba(0,0,0,.25);
  transition:transform .16s,border-color .16s,box-shadow .16s}
.legends img:hover{transform:scale(1.22);border-color:#fff;
  box-shadow:0 6px 16px rgba(0,0,0,.4)}
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
  .legends{margin-inline-start:10px;justify-content:flex-start}
  .lg-track{gap:8px}
  .legends img{width:42px;height:42px;border-width:1.5px}
  .nav-en{display:none}
  .navtab{padding:0 14px}
}
@media(prefers-reduced-motion:reduce){.lg-track,.tk-track{animation:none}}
"""

# progressive-enhancement: show one day at a time with prev/next (like the live app).
# Without JS, every day-section stays visible (crawlable).
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
  function matchesShown(on){ nav.style.display = on ? '' : 'none'; wrap.style.display = on ? '' : 'none'; }
  function reset(){                 /* all-matches view (default / top nav tab) */
    filter='';
    lgItems.forEach(function(x){ x.classList.remove('is-active'); });
    tables.forEach(function(t){ t.hidden=true; });
    matchesShown(true);
    applyFilter(sections[idx]);
  }
  function selectLeague(b){
    filter=b.getAttribute('data-comp')||'';
    lgItems.forEach(function(x){ x.classList.toggle('is-active', x===b); });
    var table=tables.filter(function(t){return t.getAttribute('data-comp')===filter;})[0];
    tables.forEach(function(t){ t.hidden = t!==table; });
    if(table){ matchesShown(false); }                             /* table only */
    else { matchesShown(true); applyFilter(sections[idx]); }      /* no table (WC) -> its matches */
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
