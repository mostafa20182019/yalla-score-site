#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Every published article as a WordPress import file (WXR 1.2).

    python tools/wp_export.py                      -> wp/yalla-score-part1.xml, part2 ...
    python tools/wp_export.py --chunk 0 --out wp/all.xml

The move to WordPress (user decision, 2026-10-21: «سننقل الى wordpress»). The
articles are the part that moves as content; the match pages, tables and the
live layer stay on the Worker, which WordPress reads through the bridge
plugin. This file is what the WordPress importer (Tools -> Import ->
WordPress, "Download and import file attachments" ticked) consumes:

- one `post` per article, body HTML as the site renders it, the FAQ and the
  sources appended as two sections so nothing the page showed is lost;
- `post_name` = the article id, so with the permalink structure `/a/%postname%`
  every indexed URL (https://yallascore.site/a/892) keeps working unchanged;
- the picture as an `attachment` item the importer downloads from the live
  site, set as the featured image, its credit as the caption;
- categories from `kind` (report / preview / analysis, else news), the clubs
  the piece talks about as tags, the two authors as WordPress users;
- the old ids and timestamps as post meta (ys_article_id, ys_match_id,
  ys_kind, ys_pub_ts, ys_updated_ts, ys_fb_post) for the bridge plugin.

The importer's upload limit on shared hosting is often 8-64 MB, hence the
chunks (150 posts each by default, a few MB each). Attachment ids are
100000 + article id so they never collide with the posts' ids.
"""
import argparse
import datetime
import json
import os
import sys
from xml.sax.saxutils import escape

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

SITE = "https://yallascore.site"
SITE_TITLE = "يلا سكور"
SITE_DESC = "أخبار الكرة ونتائج المباريات لحظة بلحظة"
CATEGORIES = {None: ("أخبار", "news"), "report": ("تقارير المباريات", "reports"),
              "preview": ("قبل المباراة", "previews"), "analysis": ("تحليلات", "analysis")}
AUTHORS = {"فريق التحرير": "editorial", "مصطفى عبدالسلام": "mustafa"}
ATTACH_BASE = 100000
try:
    from zoneinfo import ZoneInfo
    CAIRO = ZoneInfo("Africa/Cairo")
except Exception:                                   # noqa: BLE001
    CAIRO = datetime.timezone(datetime.timedelta(hours=3))


def load_articles(path=None):
    with open(path or os.path.join(HERE, "data", "articles.json"), encoding="utf-8") as f:
        doc = json.load(f)
    return doc["results"][0]["items"]


def when(a):
    """(local Cairo datetime, utc datetime): pub_ts when the row has it, else
    pub_date at 12:00 Cairo (the early rows carry a date only)."""
    ts = a.get("pub_ts")
    if ts:
        dt = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    else:
        dt = datetime.datetime.strptime(a["pub_date"], "%Y-%m-%d").replace(hour=12, tzinfo=CAIRO)
    return dt.astimezone(CAIRO), dt.astimezone(datetime.timezone.utc)


def body_html(a):
    """The body plus the FAQ and the sources, as the page shows them."""
    parts = [a.get("body") or ""]
    faq = [f for f in (a.get("faq") or []) if isinstance(f, dict) and f.get("q") and f.get("a")]
    if faq:
        parts.append("<h2>أسئلة شائعة</h2>" + "".join(f"<h3>{escape(f['q'])}</h3><p>{escape(f['a'])}</p>" for f in faq))
    src = [s for s in (a.get("sources") or []) if isinstance(s, dict) and s.get("name")]
    if src:
        items = []
        for s in src:
            name = escape(s["name"])
            if s.get("url"):
                name = f'<a href="{escape(s["url"])}" rel="nofollow noopener" target="_blank">{name}</a>'
            note = f" — {escape(s['note'])}" if s.get("note") else ""
            items.append(f"<li>{name}{note}</li>")
        parts.append("<h2>المصادر</h2><ul>" + "".join(items) + "</ul>")
    return "".join(parts)


def clubs_of(a):
    """The clubs the piece talks about (the site's own test), as tag names."""
    try:
        from site_lib.articles import article_clubs
        return [tp.get("name") or tp.get("title") for tp in article_clubs(a) if tp.get("name") or tp.get("title")]
    except Exception:                               # noqa: BLE001
        return []


def cdata(s):
    return "<![CDATA[" + (s or "").replace("]]>", "]]]]><![CDATA[>") + "]]>"


def meta(k, v):
    return f"\n\t\t<wp:postmeta><wp:meta_key>{cdata(k)}</wp:meta_key><wp:meta_value>{cdata(str(v))}</wp:meta_value></wp:postmeta>"


def item_post(a):
    aid = str(a["article_id"]).strip()
    local, utc = when(a)
    author = AUTHORS.get((a.get("author") or "").strip(), "editorial")
    cat_name, cat_slug = CATEGORIES.get(a.get("kind") or None, CATEGORIES[None])
    rfc = utc.strftime("%a, %d %b %Y %H:%M:%S +0000")
    tags = "".join(f'\n\t\t<category domain="post_tag" nicename="{escape(_slug(t))}">{cdata(t)}</category>' for t in clubs_of(a))
    img = (a.get("image_url") or "").strip()
    thumb = meta("_thumbnail_id", ATTACH_BASE + int(aid)) if img else ""
    metas = meta("ys_article_id", aid) + meta("ys_kind", a.get("kind") or "news") + meta("ys_pub_ts", a.get("pub_ts") or a.get("pub_date") or "")
    for k in ("match_id", "updated_ts", "fb_post", "image_credit"):
        if a.get(k):
            metas += meta("ys_" + k, a[k])
    return f"""
\t<item>
\t\t<title>{cdata(a.get("title") or "")}</title>
\t\t<link>{SITE}/a/{aid}</link>
\t\t<pubDate>{rfc}</pubDate>
\t\t<dc:creator>{cdata(author)}</dc:creator>
\t\t<guid isPermaLink="false">{SITE}/a/{aid}</guid>
\t\t<description></description>
\t\t<content:encoded>{cdata(body_html(a))}</content:encoded>
\t\t<excerpt:encoded>{cdata(a.get("summary") or "")}</excerpt:encoded>
\t\t<wp:post_id>{int(aid)}</wp:post_id>
\t\t<wp:post_date>{cdata(local.strftime("%Y-%m-%d %H:%M:%S"))}</wp:post_date>
\t\t<wp:post_date_gmt>{cdata(utc.strftime("%Y-%m-%d %H:%M:%S"))}</wp:post_date_gmt>
\t\t<wp:comment_status>{cdata("open")}</wp:comment_status>
\t\t<wp:ping_status>{cdata("closed")}</wp:ping_status>
\t\t<wp:post_name>{cdata(aid)}</wp:post_name>
\t\t<wp:status>{cdata("publish")}</wp:status>
\t\t<wp:post_parent>0</wp:post_parent>
\t\t<wp:menu_order>0</wp:menu_order>
\t\t<wp:post_type>{cdata("post")}</wp:post_type>
\t\t<wp:post_password></wp:post_password>
\t\t<wp:is_sticky>0</wp:is_sticky>
\t\t<category domain="category" nicename="{cat_slug}">{cdata(cat_name)}</category>{tags}{thumb}{metas}
\t</item>"""


def item_attachment(a):
    img = (a.get("image_url") or "").strip()
    if not img:
        return ""
    aid = int(str(a["article_id"]).strip())
    local, utc = when(a)
    rfc = utc.strftime("%a, %d %b %Y %H:%M:%S +0000")
    name = os.path.basename(img).rsplit(".", 1)[0]
    return f"""
\t<item>
\t\t<title>{cdata(name)}</title>
\t\t<link>{escape(img)}</link>
\t\t<pubDate>{rfc}</pubDate>
\t\t<dc:creator>{cdata("editorial")}</dc:creator>
\t\t<guid isPermaLink="false">{escape(img)}</guid>
\t\t<description></description>
\t\t<content:encoded></content:encoded>
\t\t<excerpt:encoded>{cdata(a.get("image_credit") or "")}</excerpt:encoded>
\t\t<wp:post_id>{ATTACH_BASE + aid}</wp:post_id>
\t\t<wp:post_date>{cdata(local.strftime("%Y-%m-%d %H:%M:%S"))}</wp:post_date>
\t\t<wp:post_date_gmt>{cdata(utc.strftime("%Y-%m-%d %H:%M:%S"))}</wp:post_date_gmt>
\t\t<wp:comment_status>{cdata("closed")}</wp:comment_status>
\t\t<wp:ping_status>{cdata("closed")}</wp:ping_status>
\t\t<wp:post_name>{cdata(f"img-{aid}")}</wp:post_name>
\t\t<wp:status>{cdata("inherit")}</wp:status>
\t\t<wp:post_parent>{aid}</wp:post_parent>
\t\t<wp:menu_order>0</wp:menu_order>
\t\t<wp:post_type>{cdata("attachment")}</wp:post_type>
\t\t<wp:post_password></wp:post_password>
\t\t<wp:is_sticky>0</wp:is_sticky>
\t\t<wp:attachment_url>{cdata(img)}</wp:attachment_url>{meta("_wp_attachment_image_alt", a.get("title") or "")}
\t</item>"""


def _slug(s):
    return "".join(ch if ch.isalnum() else "-" for ch in (s or "").strip()).strip("-").lower() or "tag"


# ------------------------------------------------------------ the fixed pages
# about / contact / privacy / terms / editorial / editors: lifted from the
# BUILT site (dist/<page>.html) so every template variable is filled, the
# <h1> dropped (WordPress prints the title), .html links made extensionless.
PAGES = (("about", "من نحن"), ("contact", "اتصل بنا"), ("privacy", "سياسة الخصوصية"),
         ("terms", "شروط الاستخدام"), ("editorial", "السياسة التحريرية"), ("editors", "فريق التحرير"))
PAGE_BASE = 200000


def page_body(html):
    """The page's article block without its <h1>, links extensionless."""
    import re
    m = re.search(r'<article class="article legal">(.*?)</article>', html, re.S)
    body = m.group(1) if m else html
    body = re.sub(r"<h1[^>]*>.*?</h1>", "", body, count=1, flags=re.S)
    body = re.sub(r'href="/([a-z0-9_-]+)\.html"', r'href="/\1"', body)
    return body.strip()


def item_page(slug, title, html, order, pid):
    now = datetime.datetime.now(CAIRO)
    utc = now.astimezone(datetime.timezone.utc)
    return f"""
\t<item>
\t\t<title>{cdata(title)}</title>
\t\t<link>{SITE}/{slug}</link>
\t\t<pubDate>{utc.strftime("%a, %d %b %Y %H:%M:%S +0000")}</pubDate>
\t\t<dc:creator>{cdata("editorial")}</dc:creator>
\t\t<guid isPermaLink="false">{SITE}/{slug}</guid>
\t\t<description></description>
\t\t<content:encoded>{cdata(page_body(html))}</content:encoded>
\t\t<excerpt:encoded></excerpt:encoded>
\t\t<wp:post_id>{pid}</wp:post_id>
\t\t<wp:post_date>{cdata(now.strftime("%Y-%m-%d %H:%M:%S"))}</wp:post_date>
\t\t<wp:post_date_gmt>{cdata(utc.strftime("%Y-%m-%d %H:%M:%S"))}</wp:post_date_gmt>
\t\t<wp:comment_status>{cdata("closed")}</wp:comment_status>
\t\t<wp:ping_status>{cdata("closed")}</wp:ping_status>
\t\t<wp:post_name>{cdata(slug)}</wp:post_name>
\t\t<wp:status>{cdata("publish")}</wp:status>
\t\t<wp:post_parent>0</wp:post_parent>
\t\t<wp:menu_order>{order}</wp:menu_order>
\t\t<wp:post_type>{cdata("page")}</wp:post_type>
\t\t<wp:post_password></wp:post_password>
\t\t<wp:is_sticky>0</wp:is_sticky>
\t</item>"""


def write_pages(out, dist=None):
    """The six fixed pages from dist/ -> one WXR; the pages found."""
    dist = dist or os.path.join(HERE, "dist")
    items, found = [], []
    for i, (slug, title) in enumerate(PAGES):
        path = os.path.join(dist, slug + ".html")
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            items.append(item_page(slug, title, f.read(), i, PAGE_BASE + i))
        found.append(slug)
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(header([]) + "".join(items) + FOOTER)
    return found


def header(arts):
    authors = "".join(f"""
\t<wp:author><wp:author_id>{i + 1}</wp:author_id><wp:author_login>{cdata(login)}</wp:author_login><wp:author_email>{cdata(login + "@yallascore.site")}</wp:author_email><wp:author_display_name>{cdata(name)}</wp:author_display_name><wp:author_first_name>{cdata(name)}</wp:author_first_name><wp:author_last_name></wp:author_last_name></wp:author>"""
                      for i, (name, login) in enumerate(AUTHORS.items()))
    cats = "".join(f"""
\t<wp:category><wp:term_id>{i + 1}</wp:term_id><wp:category_nicename>{cdata(slug)}</wp:category_nicename><wp:category_parent></wp:category_parent><wp:cat_name>{cdata(name)}</wp:cat_name></wp:category>"""
                   for i, (name, slug) in enumerate(CATEGORIES.values()))
    tagset = {}
    for a in arts:
        for t in clubs_of(a):
            tagset[t] = _slug(t)
    tags = "".join(f"""
\t<wp:tag><wp:term_id>{100 + i}</wp:term_id><wp:tag_slug>{cdata(slug)}</wp:tag_slug><wp:tag_name>{cdata(name)}</wp:tag_name></wp:tag>"""
                   for i, (name, slug) in enumerate(sorted(tagset.items())))
    return f"""<?xml version="1.0" encoding="UTF-8" ?>
<!-- WordPress eXtended RSS of {SITE_TITLE}, written by tools/wp_export.py on {datetime.datetime.now(CAIRO):%Y-%m-%d %H:%M} -->
<rss version="2.0"
\txmlns:excerpt="http://wordpress.org/export/1.2/excerpt/"
\txmlns:content="http://purl.org/rss/1.0/modules/content/"
\txmlns:wfw="http://wellformedweb.org/CommentAPI/"
\txmlns:dc="http://purl.org/dc/elements/1.1/"
\txmlns:wp="http://wordpress.org/export/1.2/">
<channel>
\t<title>{escape(SITE_TITLE)}</title>
\t<link>{SITE}</link>
\t<description>{escape(SITE_DESC)}</description>
\t<pubDate>{datetime.datetime.now(datetime.timezone.utc):%a, %d %b %Y %H:%M:%S} +0000</pubDate>
\t<language>ar</language>
\t<wp:wxr_version>1.2</wp:wxr_version>
\t<wp:base_site_url>{SITE}</wp:base_site_url>
\t<wp:base_blog_url>{SITE}</wp:base_blog_url>{authors}{cats}{tags}
\t<generator>yalla-score wp_export</generator>"""


FOOTER = "\n</channel>\n</rss>\n"


def write(arts, out):
    body = "".join(item_attachment(a) + item_post(a) for a in arts)
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(header(arts) + body + FOOTER)
    return os.path.getsize(out)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--chunk", type=int, default=150, help="posts per file, 0 = one file")
    ap.add_argument("--out", default=os.path.join(HERE, "wp", "yalla-score-part{n}.xml"))
    ap.add_argument("--articles", help="another export file (tests)")
    a = ap.parse_args()
    arts = sorted(load_articles(a.articles), key=lambda x: int(x["article_id"]))
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    chunks = [arts] if not a.chunk else [arts[i:i + a.chunk] for i in range(0, len(arts), a.chunk)]
    for n, part in enumerate(chunks, 1):
        out = a.out.format(n=n) if "{n}" in a.out else a.out
        size = write(part, out)
        print(f"{out}: {len(part)} posts, ids {part[0]['article_id']}-{part[-1]['article_id']}, {size / 1e6:.1f} MB")
    pages_out = os.path.join(os.path.dirname(a.out) or ".", "yalla-score-pages.xml")
    found = write_pages(pages_out)
    print(f"{pages_out}: {len(found)} pages ({', '.join(found)})" if found else f"{pages_out}: no dist/ pages found - build the site first")


if __name__ == "__main__":
    main()
