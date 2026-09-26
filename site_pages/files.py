"""Site files that are not pages: robots.txt, sitemap, ads.txt, RSS, root
passthroughs, redirects for moved match pieces, mirrored crests,
uploaded media, build-info, the CSS asset and logo.

Moved verbatim out of build_site.py (2026-09-26, tools/move_names.py):
source and comments exactly as they were there. Edit here; build_site
imports these back under the same names."""
import datetime
import hashlib
import json
import os
import shutil
import site_lib.shell as _shell
import store
from site_lib.articles import _rfc822, article_url
from site_lib.config import ADSENSE_CLIENT, DIST, HERE, NEWLINE, REF_TODAY, SITE_BASE, SITE_DESC, SITE_NAME, SITE_TAGLINE
from site_lib.crests import CRESTS_CACHE, _CREST_MAP
from site_lib.loaders import build_info
from site_lib.shell import _LASTMOD, write, write_text
from site_lib.snippets import CSS, LEGENDS_CSS
from site_lib.text import esc, strip_tags
from site_pages.glue import _UNSET


def _page_robots_sitemap_ads_txt(_img=_UNSET, a=_UNSET, articles=_UNSET, urls=_UNSET):
    if _img is _UNSET:
        del _img
    if a is _UNSET:
        del a
    if articles is _UNSET:
        del articles
    if urls is _UNSET:
        del urls
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


def _page_passthrough_root_files():
    # ---- passthrough root files (Google Search Console verification, etc.) ----
    extras = os.path.join(HERE, "root-extras")
    if os.path.isdir(extras):
        for fn in os.listdir(extras):
            src = os.path.join(extras, fn)
            if os.path.isfile(src):
                shutil.copy(src, os.path.join(DIST, fn))
                print("  + root file:", fn)
    _l = locals()
    return {k: _l[k] for k in ('fn', 'src') if k in _l}


def _page_redirects_the_match_pieces_that_moved_in(_moved=_UNSET):
    if _moved is _UNSET:
        del _moved
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


def _page_mirrored_crests(fn=_UNSET, src=_UNSET):
    if fn is _UNSET:
        del fn
    if src is _UNSET:
        del src
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
    _l = locals()
    return {k: _l[k] for k in ('fn', 'n', 'src') if k in _l}


def _page_uploaded_media(_preds=_UNSET, articles=_UNSET, fn=_UNSET, matches=_UNSET, n=_UNSET, src=_UNSET):
    if _preds is _UNSET:
        del _preds
    if articles is _UNSET:
        del articles
    if fn is _UNSET:
        del fn
    if matches is _UNSET:
        del matches
    if n is _UNSET:
        del n
    if src is _UNSET:
        del src
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


def _page_assets_css_logo():
    # ---- assets: css + logo ----
    _css = CSS + "\n" + LEGENDS_CSS
    _shell.CSS_VER = hashlib.md5(_css.encode("utf-8")).hexdigest()[:8]   # changes only when CSS changes
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
    _l = locals()
    return {k: _l[k] for k in ('f', 'urls') if k in _l}
