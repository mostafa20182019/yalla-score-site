"""Articles: bylines, data credits, URLs, moved-link fixing, embeds, the
match-article block, related articles, RSS dates, thin-article rule and
the missing-media placeholder.

Moved verbatim out of build_site.py (2026-09-26, tools/move_names.py):
source and comments exactly as they were there. Edit here; build_site
imports these back under the same names."""
import datetime
import os
import re
import store
from site_lib.clubs import TEAM_PAGES
from site_lib.competitions import S365_COMPETITIONS
from site_lib.config import ARTICLE_MIN_WORDS, EDITOR_NAME, GENERIC_BYLINES, HERE, PLACEHOLDER_IMGS, SITE_BASE, SITE_NAME
from site_lib.media import EMBED_LABEL
from site_lib.names import _team_news
from site_lib.text import article_words, esc, jsonld, strip_tags
from site_lib.urls import article_href


def byline(a):
    """The name to print (and to put in schema) for one article."""
    return EDITOR_NAME if (a.get("author") or "") in GENERIC_BYLINES else a["author"]


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


def is_thin(a):
    return article_words(a) < ARTICLE_MIN_WORDS


def article_url(a):
    return SITE_BASE + article_href(a)


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
