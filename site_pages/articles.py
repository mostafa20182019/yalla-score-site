"""Article pages (/a/<id>), the news archive, the Facebook paste helper and
the headlines page.

Moved verbatim out of build_site.py (2026-09-26, tools/move_names.py):
source and comments exactly as they were there. Edit here; build_site
imports these back under the same names."""
import hashlib
import os
from site_lib.articles import _MOVED_LINKS, article_clubs, article_moved_stub, article_url, byline, embeds_block, fix_moved_links, match_data_sources, related_articles
from site_lib.config import ARTICLE_MIN_WORDS, DIST, FB_PAGE_URL, PLACEHOLDER_IMGS, SHOW_HEADLINES, SITE_BASE, SITE_NAME, TG_CHANNEL_URL, load
from site_lib.dates import art_reltime, rel_ar
from site_lib.names import _egy_article, _eur_article
from site_lib.render import Markup, render
from site_lib.shell import _LASTMOD, _og_dims, foot, head, thumb_url, write
from site_lib.snippets import FBCOPY_JS
from site_lib.text import esc, jsonld, strip_src, strip_tags
from site_lib.urls import article_href, breadcrumb_ld, is_match_piece


def article_pages(articles, articles_all, matches, urls):
    """/a/<id> for every article (listed or not - each keeps its page). The
    markup is site_src/templates/article.html (templated 2026-09-25); this
    function prepares the values, the NewsArticle / breadcrumb / FAQ JSON-LD,
    the noindex rule and the sitemap bookkeeping - in the same order as before,
    so functions with side effects still run in the same sequence.

    Match previews/reports do not get a page of their own: they render inside
    /m/<match_id> and their old /a/ URL is a stub that 301s there.

    Returns (match_id -> its match pieces, the moved /a/ -> /m/ pairs) - read by
    match_pages() and write_redirects()."""
    # match_id -> competition, so a match piece whose writer skipped `sources`
    # still credits the right data provider (see match_data_sources)
    _mcomp = {str(m["match_id"]): (m.get("competition") or "")
              for m in (load("matches_archive.json") + matches) if m.get("match_id")}
    _match_arts = {}
    _moved = []
    _MOVED_LINKS.clear()
    _MOVED_LINKS.update({str(x["article_id"]): f"/m/{x['match_id']}"
                         for x in articles_all if is_match_piece(x)})
    n_thin = 0
    p = []
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
        # 500-700-word standard) - dateModified, «آخر تحديث» and sitemap lastmod
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
        page_head = Markup(head(f"{a['title']} — {SITE_NAME}", _desc, url, image=img, og_type="article"))
        article_ld = Markup(jsonld(ld))
        _crumbs = [("أخبار", SITE_BASE + "/"), ("كل الأخبار", SITE_BASE + "/news.html")]
        if _clubs:
            _crumbs.append((_clubs[0]["name"], f'{SITE_BASE}/team/{_clubs[0]["slug"]}.html'))
        crumbs_ld = Markup(breadcrumb_ld(_crumbs + [(a["title"], url)]))
        crumbs = [(u.replace(SITE_BASE, "") or "/", n) for n, u in _crumbs]
        _t = art_reltime(a)
        _upd = ""
        if a.get("updated_ts"):
            _upd = (f' · <span class="a-upd">آخر تحديث <time datetime="{esc(a["updated_ts"])}">'
                    f'{esc(str(a["updated_ts"])[:10])}</time></span>')
        body = Markup(fix_moved_links(a.get("body")) or "")
        _src = [s for s in (a.get("sources") or []) if isinstance(s, dict) and s.get("name")]
        if not _src and a.get("kind") in ("preview", "report"):
            _src = match_data_sources(a, _mcomp.get(str(a.get("match_id")), ""))
        sources = [{"url": s.get("url"), "name": s["name"], "note": s.get("note")} for s in _src]
        _faq = [f for f in (a.get("faq") or []) if isinstance(f, dict) and f.get("q") and f.get("a")]
        faq_ld = ""
        if _faq:
            faq_ld = Markup(jsonld({"@context": "https://schema.org", "@type": "FAQPage",
                                    "mainEntity": [{"@type": "Question", "name": f["q"],
                                                    "acceptedAnswer": {"@type": "Answer", "text": f["a"]}} for f in _faq]}))
        # official posts about the story, click-to-load (2026-09-13)
        embeds = Markup(embeds_block(a.get("embeds")))
        related = []
        for b in related_articles(a, articles):
            _bt = art_reltime(b)
            related.append({"href": Markup(article_href(b)), "title": b["title"],
                            "when": Markup(_bt) if _bt else ""})
        _ahtml = render(
            "article.html",
            page_head=page_head, article_ld=article_ld, crumbs_ld=crumbs_ld, crumbs=crumbs,
            title=a["title"], byline=byline(a), pub_date=a.get("pub_date"),
            rel_time=Markup(" · " + _t) if _t else "", updated=Markup(_upd),
            img=img, credit=a.get("image_credit"), summary=a.get("summary"), body=body,
            sources=sources, faq=[{"q": f["q"], "a": f["a"]} for f in _faq], faq_ld=faq_ld,
            embeds=embeds, clubs=[{"slug": Markup(tp["slug"]), "name": tp["name"]} for tp in _clubs],
            related=related, page_foot=Markup(foot()))
        p = [_ahtml]
        if _words < ARTICLE_MIN_WORDS:
            # legacy short pieces: keep the URL alive (still linked from lists
            # and related blocks) but out of the index AND out of the sitemap -
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
    return _match_arts, _moved


def news_archive_pages(articles, urls):
    """/news = everything; /news/egypt + /news/europe = the section archives each
    home block's «المزيد» opens (user 2026-09-01: the blocks stay at 4 rows - the
    rest lives behind المزيد). Same calm list rows everywhere - the old card grid
    read as scattered ("شتات"). Template: site_src/templates/news_archive.html."""
    def news_archive(fname, h1, title, desc, arts):
        page_head = Markup(head(f"{title} — {SITE_NAME}", desc,
                                SITE_BASE + "/" + fname, active="home"))
        rows = []
        for a in arts:
            img = thumb_url(a.get("image_url"))
            rows.append({
                "href": Markup(article_href(a)),
                "th": Markup(f'<span class="al-th" style="background-image:url(\'{esc(img)}\')"></span>'
                             if img else '<span class="al-th noimg">⚽</span>'),
                "title": a.get("title"),
                "summary": strip_tags(a.get("summary") or ""),
                "byline": byline(a),
                "when": Markup(art_reltime(a) or esc(a.get("pub_date") or "")),
            })
        write(fname, render("news_archive.html", page_head=page_head, h1=h1,
                            crumbs=(fname != "news.html"), rows=rows, page_foot=Markup(foot())))
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


def fb_helper_page(articles):
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


def headlines_page(headlines, urls):
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
