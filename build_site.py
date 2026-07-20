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
    <a class="brand" href="/"><span class="ball">⚽</span> {esc(SITE_NAME)}</a>
  </div>
  <nav class="site-nav"><div class="wrap nav-in">
    <a href="/" class="navtab{ha}"><span class="ico">⌂</span> الرئيسية | Home</a>
    <a href="/matches.html" class="navtab{ma}"><span class="ico">☰</span> المباريات | Matches</a>
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
  <p class="foot-links"><a href="/">الرئيسية</a> · <a href="/matches.html">المباريات</a> · <a href="/privacy.html">سياسة الخصوصية</a></p>
  <p class="credit">صور عبر Wikimedia Commons / Unsplash — رخص حرة / المجال العام</p>
  <p class="credit">© {year} {esc(SITE_NAME)}</p>
</div></footer>
</body></html>"""

def jsonld(obj):
    return '<script type="application/ld+json">' + json.dumps(obj, ensure_ascii=False) + '</script>'

def article_url(a):
    return f"{SITE_BASE}/a/{a['article_id']}.html"

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
    # "أخبارنا" as a magazine split: big featured (right) + vertical side list (left)
    if feat:
        img = feat.get("image_url")
        fstyle = f' style="background-image:url(\'{esc(img)}\')"' if img else ' class="noimg"'
        feat_html = f"""<a class="feat" href="/a/{feat['article_id']}.html">
  <div class="feat-img"{fstyle}></div>
  <div class="feat-body">
    <h2>{esc(feat['title'])}</h2>
    <p>{esc(feat.get('summary'))}</p>
    <span class="feat-meta">{esc(feat.get('author') or SITE_NAME)} · {esc(feat.get('pub_date'))}</span>
  </div></a>"""
        if rest:
            side = ['<div class="mag-side">']
            for a in rest:
                img = a.get("image_url")
                mstyle = f' style="background-image:url(\'{esc(img)}\')"' if img else ' class="noimg"'
                side.append(f"""<a class="mrow" href="/a/{a['article_id']}.html">
  <div class="mrow-img"{mstyle}></div>
  <div class="mrow-b"><h3>{esc(a['title'])}</h3>
  <p class="meta">{esc(a.get('author'))} · {esc(a.get('pub_date'))}</p></div></a>""")
            side.append('</div>')
            parts.append('<div class="mag">' + feat_html + ''.join(side) + '</div>')
        else:
            parts.append(feat_html)
    # external headlines (aggregated; each links out to its source)
    if headlines:
        parts.append('<h2 class="page-h">عناوين من مصادر أخرى</h2><div class="hgrid">')
        for h in headlines:
            t = strip_src(h.get("title"), h.get("source"))
            iso = h.get("pub_iso") or ""
            when = rel_ar(iso) if iso else (h.get("pub_date") or "")
            timeel = (f'<time class="reltime" datetime="{esc(iso)}">{esc(when)}</time>'
                      if iso else esc(when))
            src = esc(h.get('source') or '')
            parts.append(f"""<a class="hcard" href="{esc(h.get('link'))}" target="_blank" rel="noopener nofollow">
  <span class="go" aria-hidden="true">↗</span>
  <h3>{esc(t)}</h3>
  <p class="meta"><span class="hsrc">{src}</span><span class="reltime-wrap">{timeel}</span></p></a>""")
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
    p = [head(f"مواعيد ونتائج المباريات — {SITE_NAME}",
              "مواعيد ونتائج مباريات كرة القدم بتوقيت القاهرة على يلا سكور.",
              SITE_BASE + "/matches.html", active="matches")]
    p.append('<h1 class="page-h">المباريات</h1>')
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
            if comp:
                p.append(f'<div class="comp-h">{esc(comp)}</div>')
            p.append('<div class="mlist">')
            for m in ms:
                p.append(match_row(m, show_time=True, show_comp=False))
            p.append('</div>')
        p.append('</section>')
    p.append('</div>')
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

    print(f"Built {len(articles)} articles, {len(matches)} matches -> {DIST}")
    print(f"SITE_BASE = {SITE_BASE}  (edit build_site.py to change, then rebuild)")

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
    return f"""<div class="mrow mrow-{badge[1]}">
  <span class="pill pill-{badge[1]}">{badge[0]}</span>
  <div class="team">{crest(m.get('home_badge'))}<span>{esc(m.get('home'))}</span></div>
  <div class="mid">{mid}</div>
  <div class="team">{crest(m.get('away_badge'))}<span>{esc(m.get('away'))}</span></div>
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
.head-in{display:flex;align-items:center;height:56px}
.brand{color:#fff;font-weight:900;font-size:1.3rem;text-decoration:none;display:inline-flex;align-items:center;gap:8px}
/* second row: navigation tabs (like the app) */
.site-nav{position:relative;z-index:1;background:rgba(0,0,0,.16);border-top:1px solid rgba(255,255,255,.12)}
.nav-in{display:flex;align-items:stretch;height:46px}
.navtab{display:inline-flex;align-items:center;gap:7px;padding:0 18px;color:rgba(255,255,255,.85);text-decoration:none;font-weight:800;font-size:.95rem;border-bottom:3px solid transparent;transition:background .12s,color .12s}
.navtab:hover{background:rgba(255,255,255,.10);color:#fff}
.navtab.is-active{color:#fff;border-bottom-color:#fff;background:rgba(255,255,255,.08)}
.navtab .ico{font-size:1.05rem;opacity:.9}
.page-h{color:var(--green-d);font-weight:900;margin:22px 0 12px}
/* featured */
.feat{display:block;position:relative;height:340px;border-radius:18px;overflow:hidden;text-decoration:none;color:#fff;box-shadow:0 14px 34px rgba(15,23,42,.24);margin-bottom:16px;background:linear-gradient(135deg,var(--green-d),#072012)}
.feat-img{position:absolute;inset:0;background-size:cover;background-position:center}
.feat.noimg .feat-img,.feat-img.noimg{background:linear-gradient(135deg,var(--green),#0a3d1c)}
.feat::after{content:"";position:absolute;inset:0;background:linear-gradient(to top,rgba(3,18,10,.95) 8%,rgba(3,18,10,.15) 70%)}
.feat-body{position:absolute;inset-inline:0;bottom:0;padding:22px 26px;z-index:2}
.feat-body h2{margin:0 0 8px;font-size:1.55rem;font-weight:900;text-shadow:0 2px 10px rgba(0,0,0,.5)}
.feat-body p{margin:0;opacity:.94}
.feat-meta{display:block;margin-top:10px;font-size:.82rem;font-weight:700;color:#cfe6d6}
/* magazine split: featured (right) + side list (left) */
.mag{display:grid;grid-template-columns:1.7fr 1fr;gap:16px;align-items:stretch;margin-bottom:16px}
.mag .feat{height:auto;min-height:360px;margin-bottom:0}
.mag .feat-body p{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.mag-side{display:flex;flex-direction:column;justify-content:space-between;gap:12px}
.mrow{display:grid;grid-template-columns:96px 1fr;gap:12px;background:var(--card);border:1px solid #e6ebf1;border-radius:12px;padding:10px;align-items:center;text-decoration:none;box-shadow:0 2px 8px rgba(15,23,42,.06);transition:transform .14s,box-shadow .14s}
.mrow:hover{transform:translateY(-2px);box-shadow:0 10px 20px rgba(15,23,42,.13)}
.mrow-img{width:96px;height:72px;flex:0 0 auto;border-radius:9px;background-color:#e6ebf1;background-size:cover;background-position:center}
.mrow-img.noimg{background:linear-gradient(135deg,var(--green),#0a3d1c)}
.mrow-b h3{margin:0 0 5px;font-size:.9rem;font-weight:800;line-height:1.45;color:var(--ink);display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
@media(max-width:760px){.mag{grid-template-columns:1fr}.mag .feat{min-height:260px}}
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
/* matches */
.mlist{display:flex;flex-direction:column;gap:8px;margin-bottom:16px}
.mrow{display:grid;grid-template-columns:auto 1fr auto 1fr;grid-template-areas:"pill home mid away" "comp comp comp comp";gap:8px 10px;align-items:center;background:#fff;border:1px solid #e2e8f0;border-radius:12px;border-inline-start:5px solid var(--up);padding:12px 16px;box-shadow:0 1px 3px rgba(15,23,42,.05)}
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
.mcomp{grid-area:comp;color:var(--muted);font-size:.78rem;font-weight:700;text-align:center;border-top:1px solid #eef2f6;padding-top:8px}
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
/* footer */
.site-foot{background:#0b1220;color:#cbd5e1;margin-top:30px;padding:22px 0}
.site-foot p{margin:2px 0}.credit{font-size:.78rem;color:#94a3b8}
@media(max-width:640px){.feat{height:260px}.feat-body h2{font-size:1.2rem}.article{padding:18px}}
"""

# ---- legends header strip (free CC / public-domain photos, same as the app) ----
LEGENDS = [
  "https://upload.wikimedia.org/wikipedia/commons/4/4a/Mohamed_Salah_2018.jpg",
  "https://upload.wikimedia.org/wikipedia/commons/1/19/Mohamed_Abotrika.jpg",
  "https://upload.wikimedia.org/wikipedia/commons/f/f6/Mahmoud_El-Khatib_%281977%29.jpg",
  "https://upload.wikimedia.org/wikipedia/commons/7/70/Hassan_Shehata_Egypt_%281981%29.jpg",
  "https://commons.wikimedia.org/wiki/Special:FilePath/Hazem_Emam.png",
  "https://commons.wikimedia.org/wiki/Special:FilePath/Steven_Gerrard.jpg",
  "https://commons.wikimedia.org/wiki/Special:FilePath/Frank_Lampard_(cropped).jpg",
  "https://upload.wikimedia.org/wikipedia/commons/8/8c/Cristiano_Ronaldo_2018.jpg",
  "https://commons.wikimedia.org/wiki/Special:FilePath/Zinedine_Zidane_by_Tasnim_01.jpg",
  "https://commons.wikimedia.org/wiki/Special:FilePath/Rivaldo_bunyodkor_2010.jpg",
  "https://upload.wikimedia.org/wikipedia/commons/c/c1/Lionel_Messi_20180626.jpg",
  "https://upload.wikimedia.org/wikipedia/commons/d/df/Lamine_Yamal_in_2025_%28cropped2%29.jpg",
  "https://commons.wikimedia.org/wiki/Special:FilePath/Erling_Haaland_2023_(cropped_square).jpg",
  "https://commons.wikimedia.org/wiki/Special:FilePath/Francesco_Totti_Vicario_(crop).jpg",
  "https://commons.wikimedia.org/wiki/Special:FilePath/Alessandro_Del_Piero_2008_cropped.jpg",
  "https://commons.wikimedia.org/wiki/Special:FilePath/Andrea_Pirlo_NYCFC.JPG",
  "https://commons.wikimedia.org/wiki/Special:FilePath/Gianluigi_Buffon_(31784615942)_(cropped).jpg",
]
def _legends_css():
    w = 46
    imgs  = ",".join("url('%s')" % u for u in LEGENDS)
    sizes = ",".join(["%dpx 52px" % w] * len(LEGENDS))
    poss  = ",".join("left %dpx top 0" % (i * w) for i in range(len(LEGENDS)))
    return ("\n.site-head{overflow:hidden}.head-in{position:relative;z-index:1}\n"
            ".site-head::after{content:'';position:absolute;top:2px;height:52px;left:0;right:0;"
            "pointer-events:none;z-index:0;opacity:.5;background-repeat:no-repeat;"
            "background-image:%s;background-size:%s;background-position:%s;"
            "-webkit-mask-image:linear-gradient(to right,transparent,#000 5%%,#000 95%%,transparent);"
            "mask-image:linear-gradient(to right,transparent,#000 5%%,#000 95%%,transparent)}\n"
            "@media(max-width:720px){.site-head::after{display:none}}\n" % (imgs, sizes, poss))
LEGENDS_CSS = _legends_css()

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
  function show(i){
    idx=i;
    sections.forEach(function(s,j){ s.style.display=(j===idx)?'block':'none'; });
    label.textContent=sections[idx].querySelector('.day-h').textContent;
    prev.disabled=(idx<=0); next.disabled=(idx>=sections.length-1);
  }
  prev.addEventListener('click',function(){ if(idx>0) show(idx-1); });
  next.addEventListener('click',function(){ if(idx<sections.length-1) show(idx+1); });
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

if __name__ == "__main__":
    build()
