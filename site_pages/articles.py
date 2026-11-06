"""Article pages (/a/<id>), the news archive, the Facebook paste helper and
the headlines page.

Moved verbatim out of build_site.py (2026-09-26, tools/move_names.py):
source and comments exactly as they were there. Edit here; build_site
imports these back under the same names."""
import hashlib
import os
from site_lib.articles import _MOVED_LINKS, article_clubs, author_ld, article_moved_stub, article_url, byline, embeds_block, fix_moved_links, insight_kind, match_data_sources, related_articles
from site_lib.config import ARTICLE_MIN_WORDS, BYLINE_RELTIME, DIST, FB_PAGE_URL, PLACEHOLDER_IMGS, SHOW_HEADLINES, SITE_BASE, SITE_NAME, TG_CHANNEL_URL, load
from site_lib.clubs import TEAM_PAGES
from site_lib.competitions import COMP_SLUG
from site_lib.config import REF_TODAY
from site_lib.dates import art_date, art_reltime, fmt_day, rel_ar
from site_lib.names import _egy_article, _eur_article, _team_match, ar_team, comp_label
from site_lib.render import Markup, render
from site_lib.shell import _LASTMOD, _og_dims, foot, head, noindex, push_cta, thumb_url, write
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
    # «مباريات اليوم» under every article body (2026-10-18): one strip, built once
    from site_lib.today_strip import today_strip
    _today_strip = today_strip(matches)
    # «للمتابعة» (SEO audit 2026-11-06): the links the writer kept forgetting
    # (2.2 per article, 12 with none, none to /standings), resolved from the
    # data instead - the lead club's next match and last result (/m/), its
    # league's table and scorers, its club page. Same pool as match_pages' m_all.
    _pool = {}
    for m in load("matches_archive.json") + matches:
        if m.get("match_id") and m.get("home") and m.get("kickoff"):
            _pool[m["match_id"]] = m
    _pool = sorted(_pool.values(), key=lambda m: (m.get("kickoff") or "", m.get("koff_time") or ""))
    _follow_cache = {}
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
              # the editorial team since 2026-10-07 (see BYLINE_TEAM)
              "author": author_ld(a),
              "publisher": {"@type": "Organization", "@id": SITE_BASE + "/#org",
                            "name": SITE_NAME, "url": SITE_BASE + "/",
                            "sameAs": [FB_PAGE_URL, TG_CHANNEL_URL],
                            "logo": {"@type": "ImageObject", "url": SITE_BASE + "/assets/logo.png"}}}
        # the club the TITLE names comes first (SEO audit 2026-11-06: article
        # 1080 about Pyramids got the «الأهلي» crumb, 1076 about Marmoush at
        # Tottenham got «مانشستر سيتي» - TEAM_PAGES order, not the story's);
        # when no listed club is in the title, no club crumb - better than a
        # wrong entity. keywords also carry the title itself (the names of the
        # people in it are its search phrase).
        _ttl = a.get("title") or ""
        _in_title = lambda tp: any(t in _ttl for t in tp["news_tokens"])
        # the club named FIRST in the title leads («عودة بن بوعلي إلى بيراميدز
        # قبل مواجهة الأهلي» is Pyramids' story, not Al Ahly's)
        _tpos = lambda tp: min((_ttl.find(t) for t in tp["news_tokens"] if t in _ttl), default=10**6)
        _lead = sorted(_clubs, key=lambda tp: (_tpos(tp), TEAM_PAGES.index(tp)))
        _lead_tp = _lead[0] if (_lead and _in_title(_lead[0])) else None
        if _clubs:
            ld["keywords"] = ", ".join([tp["name"] for tp in _lead] + [a["title"]])
            ld["about"] = [{"@type": "SportsTeam", "name": tp["name"],
                            "url": f'{SITE_BASE}/team/{tp["slug"]}.html'} for tp in _lead]
        if img:
            _iw, _ih = _og_dims(img)
            ld["image"] = ([{"@type": "ImageObject", "url": img, "width": _iw, "height": _ih}]
                           if _iw else [img])
        # 56 older match articles shipped without a summary and their pages
        # went out with an EMPTY meta description (audit 2026-09-22) - the
        # search snippet then falls to whatever Google scrapes. The body's
        # opening is the article's own lead; seo_desc trims it to size.
        _desc = a.get("summary") or strip_tags(a.get("body") or "")[:220]
        # a summary over the ~155 chars Google shows (236 of 431 since October,
        # SEO audit 2026-11-06) ends at its first sentence break after char 90
        # instead of mid-word with «…» - the first sentence carries the answer
        if len(_desc) > 155:
            _cut = min((i for i in (_desc.find(". ", 90), _desc.find("، ", 90), _desc.find("؛ ", 90))
                        if 0 < i <= 154), default=-1)
            if _cut > 0:
                _desc = _desc[:_cut + 1]
        page_head = Markup(head(f"{a['title']} — {SITE_NAME}", _desc, url, image=img, og_type="article"))
        article_ld = Markup(jsonld(ld))
        _crumbs = [("الرئيسية", SITE_BASE + "/"), ("كل الأخبار", SITE_BASE + "/news.html")]
        if _lead_tp:
            _crumbs.append((_lead_tp["name"], f'{SITE_BASE}/team/{_lead_tp["slug"]}.html'))
        # alt describes the picture, not the headline: the credit's own words
        # for a photo; «بطاقة <club>» for our designed card
        _credit = (a.get("image_credit") or "").strip()
        if "تصميم الجون" in _credit:
            img_alt = f"بطاقة {_lead_tp['name']} — تصميم الجون" if _lead_tp else a["title"]
        else:
            img_alt = (_credit.replace("الصورة:", "").replace("صورة:", "").split(" — ")[0].strip()
                       or a["title"])
        follow = []
        if _lead_tp:
            if _lead_tp["slug"] not in _follow_cache:
                _f = []
                _cm = [m for m in _pool if _team_match(_lead_tp, m)]
                _nx = next((m for m in _cm if (m.get("status") or "").upper() in ("UPCOMING", "LIVE")
                            and m["kickoff"] >= REF_TODAY), None)
                _ls = next((m for m in reversed(_cm) if (m.get("status") or "").upper() == "FINISHED"
                            and m.get("home_score") is not None), None)
                if _nx:
                    _f.append((f'/m/{_nx["match_id"]}.html',
                               f'موعد مباراة {ar_team(_nx["home"])} و{ar_team(_nx["away"])} يوم {fmt_day(_nx["kickoff"])}'))
                if _ls:
                    _f.append((f'/m/{_ls["match_id"]}.html',
                               f'نتيجة مباراة {ar_team(_ls["home"])} و{ar_team(_ls["away"])} '
                               f'{_ls["home_score"]}-{_ls["away_score"]}'))
                _lg = COMP_SLUG.get(_lead_tp["league"])
                if _lg:
                    _f.append((f'/standings/{_lg}.html', f'ترتيب {comp_label(_lead_tp["league"])}'))
                    _f.append((f'/scorers/{_lg}.html', f'هدافو {comp_label(_lead_tp["league"])}'))
                _f.append((f'/team/{_lead_tp["slug"]}.html', f'أخبار {_lead_tp["name"]} اليوم'))
                _follow_cache[_lead_tp["slug"]] = _f
            follow = [{"href": Markup(h), "text": t} for h, t in _follow_cache[_lead_tp["slug"]]]
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
            rel_time=Markup(" · " + _t) if (_t and BYLINE_RELTIME) else "", updated=Markup(_upd),
            img=img, img_alt=img_alt, credit=a.get("image_credit"), summary=a.get("summary"), body=body,
            follow=follow,
            sources=sources, faq=[{"q": f["q"], "a": f["a"]} for f in _faq], faq_ld=faq_ld,
            embeds=embeds, clubs=[{"slug": Markup(tp["slug"]), "name": tp["name"]} for tp in _clubs],
            related=related, push_cta=Markup(push_cta()), tg_url=TG_CHANNEL_URL,
            today_strip=Markup(_today_strip), page_foot=Markup(foot()))
        p = [_ahtml]
        if _words < ARTICLE_MIN_WORDS:
            # legacy short pieces: keep the URL alive (still linked from lists
            # and related blocks) but out of the index AND out of the sitemap -
            # a noindexed URL in the sitemap is a contradictory signal.
            _ahtml = noindex(_ahtml)
            n_thin += 1
        write(f"a/{a['article_id']}.html", _ahtml)
        if _words >= ARTICLE_MIN_WORDS:
            urls.append(f"/a/{a['article_id']}.html")
            _LASTMOD[f"/a/{a['article_id']}.html"] = _mod_iso
    print(f"  + match pieces moved into their match page: {len(_moved)}")
    print(f"  + articles: {len(articles_all)} pages, {len(articles)} listed "
          f"({n_thin} unlisted: under {ARTICLE_MIN_WORDS} words, noindexed + out of every listing)")
    return _match_arts, _moved


NEWS_PAGE = 40      # rows per archive page (SEO pass, 2026-11-04)


def news_archive_pages(articles, urls):
    """/news = everything; /news/egypt + /news/europe = the section archives each
    home block's «المزيد» opens (user 2026-09-01: the blocks stay at 4 rows - the
    rest lives behind المزيد). Same calm list rows everywhere - the old card grid
    read as scattered ("شتات"). Template: site_src/templates/news_archive.html."""
    # One list of 900 rows was a 738 KB page (SEO pass, 2026-11-04): every
    # crawl of /news spent its budget on a page nobody scrolls to the end of.
    # NEWS_PAGE rows a page, the newest first; /news, /news/p2, /news/p3 ... and
    # /news/egypt, /news/egypt-p2 ... Each page is its own canonical URL and in
    # the sitemap, with «الأحدث» / «الأقدم» links so a crawler walks the whole
    # archive one page at a time.
    def news_archive(fname, h1, title, desc, arts):
        pages = [arts[i:i + NEWS_PAGE] for i in range(0, len(arts), NEWS_PAGE)] or [[]]
        stem = fname[:-len(".html")]

        def pname(k):
            if k == 1:
                return fname
            return f"news/p{k}.html" if stem == "news" else f"{stem}-p{k}.html"

        for k, chunk in enumerate(pages, 1):
            _news_archive_page(pname(k), h1, title, desc, chunk,
                               {"k": k, "n": len(pages),
                                "prev": "/" + pname(k - 1) if k > 1 else "",
                                "next": "/" + pname(k + 1) if k < len(pages) else ""})

    def _news_archive_page(fname, h1, title, desc, arts, pager):
        if pager["k"] > 1:
            title = f"{title} — صفحة {pager['k']}"
            desc = f"{desc} (الصفحة {pager['k']} من {pager['n']})"
        page_head = Markup(head(f"{title} — {SITE_NAME}", desc,
                                SITE_BASE + "/" + fname, active="news"))
        rows = []
        # the analyses live in the news lists since 2026-10-26 (user: «دخل
        # التحليلات جوه الاخبار وحذف التاب الخاصة بالتحليلات») - a piece that is
        # one wears the same chip the /insights list gave it
        from site_pages.insights import INSIGHT_KINDS
        kind_label = dict(INSIGHT_KINDS)
        for a in arts:
            img = thumb_url(a.get("image_url"))
            k = insight_kind(a)
            rows.append({
                "href": Markup(article_href(a)),
                "th": Markup(f'<span class="al-th" style="background-image:url(\'{esc(img)}\')"></span>'
                             if img else '<span class="al-th noimg">⚽</span>'),
                "title": a.get("title"),
                "summary": strip_tags(a.get("summary") or ""),
                "byline": byline(a),
                "when": Markup(art_reltime(a) or esc(a.get("pub_date") or "")) if BYLINE_RELTIME else Markup(art_date(a)),
                "k": k or "", "kl": kind_label.get(k, "") if k else "",
            })
        write(fname, render("news_archive.html", page_head=page_head, h1=h1,
                            crumbs=(fname != "news.html" and not fname.startswith("news/p")),
                            rows=rows, pager=pager, page_foot=Markup(foot())))
        urls.append("/" + fname)

    os.makedirs(os.path.join(DIST, "news"), exist_ok=True)   # /news/p2 ... live there too
    news_archive("news.html", "كل الأخبار", "كل الأخبار",
                 "أرشيف أخبار كرة القدم على الجون — كل المقالات والتقارير.",
                 articles)
    news_archive("news/egypt.html", "أخبار الكرة المصرية",
                 "أخبار الكرة المصرية اليوم",
                 "كل أخبار الكرة المصرية على الجون: الأهلي والزمالك "
                 "وبيراميدز والدوري المصري ومنتخب مصر — تتحدّث على مدار اليوم.",
                 [a for a in articles if _egy_article(a)])
    news_archive("news/europe.html", "أخبار الكرة الأوروبية",
                 "أخبار الكرة الأوروبية اليوم",
                 "كل أخبار الدوريات الأوروبية على الجون: الدوري الإنجليزي "
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
               '<p class="fbp-note">صفحة داخلية غير معلنة — اضغط «نسخ» والصق البوست على صفحة الجون.</p>')
    for a in articles[:15]:
        _w = art_reltime(a)
        fbp.append('<div class="fbp">'
                   f'<div class="fbp-h"><b>مقال {a["article_id"]}</b> · {esc(a.get("pub_date") or "")}'
                   f'{" · " + _w if _w else ""}</div>'
                   f'<textarea class="fbp-t" readonly rows="8">{esc(_fb_text(a))}</textarea>'
                   '<button type="button" class="fbp-c">📋 نسخ</button></div>')
    fbp.append(FBCOPY_JS)
    fbp.append(foot())
    write("fb.html", noindex("".join(fbp)))


def headlines_page(headlines, urls):
    # ---- headlines page (full aggregated list; gated by SHOW_HEADLINES) ----
    if SHOW_HEADLINES:
        hp = [head(f"عناوين الصحف — {SITE_NAME}",
                   "آخر عناوين كرة القدم من الصحف والمواقع الإخبارية — تتحدث تلقائيًا على مدار الساعة.",
                   SITE_BASE + "/headlines.html", active="news")]
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
