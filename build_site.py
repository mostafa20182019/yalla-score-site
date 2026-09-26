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
from site_lib.render import render, Markup   # Jinja2 page templates (site_src/templates/)
# Football reference tables (competitions, clubs, Arabic spellings, legends,
# calendar words) live in site_lib/ since slice 2 of the split - edit them
# there. Imported under the same names, so b.AR_TEAM & co. still work.
from site_lib.competitions import (  # noqa: E402,F401
    S365_COMPETITIONS, COMP_SLUG, COMP_TV, COMP_LOGO, COMP_LABEL, COMP_ORDER, S365_COMP_IDS)
from site_lib.clubs import (  # noqa: E402,F401
    EGY_SCOPE, TICKER_TEAMS, TEAM_PAGES, AR_TEAM, LEGENDS, _EGY_TOKENS, _EUR_TOKENS)
from site_lib.arabic import (  # noqa: E402,F401
    _AR_DAYS, _AR_MONTHS, _ORD_AR)
from site_lib.media import (  # noqa: E402,F401
    VIDEO_CATS, EMBED_LABEL)
# Pure helpers (text, dates, names, urls, stats, match data, widgets) live
# in site_lib/ since slice 3 - edit them there. Same names, same behaviour.
from site_lib.text import (  # noqa: E402,F401
    esc, strip_tags, strip_src, jsonld, seo_desc, article_words,
    _pct, _signed_pct, _pval, _num, _lam)
from site_lib.dates import (  # noqa: E402,F401
    fmt_day, _ar_ago, rel_ar, art_reltime, _days_between, _epoch_ms)
from site_lib.names import (  # noqa: E402,F401
    _crest_name, _in_scope, _is_ticker_team, _team_match, _team_news, ar_team,
    _team_link, _gnorm, comp_label, comp_emoji, comp_has_table, fav_club_names,
    _egy_article, _eur_article, _club_pool)
from site_lib.urls import (  # noqa: E402,F401
    article_href, is_match_piece, pick_match_article, breadcrumb_ld, match_url)
from site_lib.stats import (  # noqa: E402,F401
    _cnt, _pts, _games, _goals, _wins, _draws,
    _losses, _assists, _players, _lil, scorers_read, standings_analysis,
    AN_games, _scored, _finished_by_comp, compute_elo, team_form, form_dots,
    league_pcts, chart_is_current, _form_counts, _pts_phrase, _per_game)
from site_lib.matchdata import (  # noqa: E402,F401
    score_pill, score_txt, goal_events_index, match_goals, frozen_scores_index, apply_frozen_scores,
    match_details_index, prematch_for, absence_block, match_details_for, _min_key, _pshort,
    _athlete_img, _pitch_rows, _rt_class, _played_names, _side_of, match_story,
    match_ratings)
from site_lib.widgets import (  # noqa: E402,F401
    reel_slide, video_facade, pred_btn, done_btn, prob_bar, prob_legend,
    ratings_table, ga_table, accuracy_html, calibration_html, _pred_item_html, _calls_html,
    model_explainer)
# config, shell: moved to site_lib/ by tools/move_names.py (2026-09-26) -
# edit them there. Same names, same behaviour.
from site_lib.config import (  # noqa: E402,F401
    SITE_BASE, SITE_NAME, SITE_TAGLINE, SITE_DESC, LOCALE, BUILD_DATE,
    ADSENSE_CLIENT, ADSENSE_SLOT, ADSENSE_SLOT_TOP, CONTACT_EMAIL, FB_PAGE_URL, TG_CHANNEL_URL,
    EDITOR_NAME, EDITOR_ROLE, EDITOR_EMAIL, GENERIC_BYLINES, CF_ANALYTICS_TOKEN, SHOW_VIDEOS,
    SHOW_REELS, SHOW_HEADLINES, SHOW_STATS_PAGE, PLACEHOLDER_IMGS, HERE, DATA,
    DIST, SITE_SRC, _src, load, REF_TODAY, ARTICLE_MIN_WORDS,
    NEWLINE)
from site_lib.shell import (  # noqa: E402,F401
    adsense_slot, page_head_ad, adsense_top_banner, _OG_DIMS, _og_dims, seo_title,
    head, cf_beacon, foot, LIVE_JS, REL_JS, thumb_url,
    _HTML_URL, _clean_urls, write_text, write, _LASTMOD)
import site_lib.shell as _shell   # build() sets TICKER_HTML / KO_SCRIPT / CSS_VER on it




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




def is_thin(a):
    return article_words(a) < ARTICLE_MIN_WORDS

# ---- crest mirroring ---------------------------------------------------
# football-data's crest host has had TLS/outage problems (2026-07-27: broken
# certificate chain -> every badge vanished). Mirror each crest into
# assets/crests/ once and serve it from our own domain; keep a cache next to
# the sources so rebuilds don't re-download, and fall back to the remote URL
# if a download ever fails.
CRESTS_CACHE = os.path.join(HERE, "assets-src", "crests")
_CREST_MAP = {}          # remote url -> "/assets/crests/<file>"


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

CLUBS_JS = _src("snippets/clubs_js.html")

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

NEWS_FILTER_JS = _src("snippets/news_filter_js.html")

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
PRED_POP = _src("snippets/pred_pop.html")
PRED_POP = PRED_POP.replace("__CONF_AR__",
                            json.dumps(AN.CONF_AR, ensure_ascii=False))


def pred_pop(parts):
    """The dialog — but only on a page that actually rendered a button.

    A club page whose next fixture has no prediction, or a standings page in a
    gap between rounds, would otherwise carry 2.6 KB of markup nothing can
    open."""
    return PRED_POP if any('class="pbtn"' in x for x in parts) else ""




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
PRED_FILTER_JS = _src("snippets/pred_filter_js.html")




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






def prediction_history_page(plog, acc):
    """/predictions.html — every frozen prediction, scored, with the model's
    calibration and its misses. Returns the url (or None when nothing scored).
    Markup: site_src/templates/predictions.html (templated 2026-09-26)."""
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
    tiles = [(a["n"], "مباراة مقيَّمة"),
             (_pct(a["hit_rate"]), "إصابة الاتجاه"),
             (_pct(a["home_baseline"]), "معيار ساذج: فوز الأرض دائمًا"),
             (f'{a["brier"]:.3f}', "Brier (الأقل أفضل · 0.667 عشوائي)"),
             (a["score_hits"], "نتيجة مضبوطة"),
             (f'{cal["ece"] * 100:.1f}', "انحراف المعايرة (نقطة مئوية)")]

    # per competition, with the sample size in front of every rate
    comps = (acc or {}).get("comps") or {}
    comp_rows = []
    for comp in COMP_ORDER + [c for c in comps if c not in COMP_ORDER]:
        c = comps.get(comp)
        if not c:
            continue
        comp_rows.append({"label": comp_label(comp), "small": c["n"] < 20, "n": c["n"],
                          "rate": _pct(c["hit_rate"]), "brier": f'{c["brier"]:.3f}'})

    # the two models, apart and NOT as a race. Since 2026-09-24 every new
    # prediction is python's (one model, the user's decision); the Oracle rows
    # are its record before that date, kept exactly as scored - history is
    # not rewritten
    srcs = (acc or {}).get("by_src") or {}
    src_rows = None
    if len(srcs) > 1:
        src_rows = []
        for k in sorted(srcs):
            v = srcs[k]
            if not v:
                continue
            nm = {"oracle": "نموذج Oracle (PL/SQL)", "python": "نموذج بايثون"}.get(k, k)
            src_rows.append({"label": nm, "n": v["n"], "rate": _pct(v["hit_rate"]),
                             "brier": f'{v["brier"]:.3f}'})

    # the full record
    comp_opts = [(c, comp_label(c))
                 for c in (COMP_ORDER + [c for c in comps if c not in COMP_ORDER]) if c in comps]
    # grouped by day: the date is a header, not a column repeated on every line
    days = []
    for e in rows:
        day = e.get("kickoff") or ""
        if not days or day != days[-1][0]:
            days.append((day, Markup(_rec_day_label(day)), []))
        days[-1][2].append(Markup(_pred_item_html(e)))

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
    faq_ld = jsonld({"@context": "https://schema.org", "@type": "FAQPage",
                     "mainEntity": [{"@type": "Question", "name": q,
                                     "acceptedAnswer": {"@type": "Answer", "text": v}}
                                    for q, v in faq]})
    crumbs_ld = breadcrumb_ld([("أخبار", SITE_BASE + "/"),
                               ("تحليلات وتوقعات", SITE_BASE + "/analysis.html"),
                               ("سجل التوقعات", SITE_BASE + url)])
    write("predictions.html", render(
        "predictions.html",
        page_head=Markup(head(title, desc, SITE_BASE + url, active="analysis")),
        first=first, last=last, tiles=tiles,
        calibration=Markup(calibration_html(cal)), calls=Markup(_calls_html(ex)),
        comp_rows=comp_rows, show_comps=bool(comps), src_rows=src_rows, comp_opts=comp_opts, n_rows=len(rows),
        days=days, faq=faq, faq_ld=Markup(faq_ld), crumbs_ld=Markup(crumbs_ld),
        page_foot=Markup(foot()), filter_js=Markup(PRED_FILTER_JS)))
    _LASTMOD[url] = REF_TODAY
    return url


def analysis_pages(matches, upcoming, preds, plog, acc, tstats, lparams, pins, sins,
                   forms, has_table=None):
    """Write /analysis.html (hub) + /analysis/<slug>.html per league. Returns urls.
    Markup: site_src/templates/analysis.html + analysis_league.html (templated
    2026-09-26); the pieces are built here in the same order as before."""
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
    page_head = head("تحليلات وتوقعات المباريات بالأرقام — يلا سكور",
                     "توقعات مباريات الأسبوع باحتمالات مبنية على بيانات الموسم، تقييم قوة الأندية، تحليل اللاعبين، "
                     "وسجل شفاف لدقة التوقعات في الدوري المصري وأبرز الدوريات.",
                     SITE_BASE + "/analysis.html", active="analysis")
    crumbs_ld = breadcrumb_ld([("أخبار", SITE_BASE + "/"), ("تحليلات", SITE_BASE + "/analysis.html")])
    nav = [(COMP_SLUG[c], Markup(comp_icon(c)), comp_label(c)) for c in comps if c in COMP_SLUG]
    week = []
    for c in comps:
        rows = by_comp.get(c)
        if not rows:
            continue
        week.append({"icon": Markup(comp_icon(c)), "slug": COMP_SLUG.get(c, ""), "label": comp_label(c),
                     "rows": [Markup(pred_row(m, p)) for m, p in rows[:8]],
                     "more": len(rows) if len(rows) > 8 and c in COMP_SLUG else 0})
    # power snapshot: top 5 per league
    power = []
    for c in comps:
        rows = sorted(tstats[c].values(), key=lambda r: -r["elo"])[:5]
        if not rows or all(r["played"] == 0 for r in rows):
            continue
        power.append({"icon": Markup(comp_icon(c)), "label": comp_label(c),
                      "rows": [(ar_team(r["team"]), round(r["elo"])) for r in rows],
                      "slug": COMP_SLUG[c] if c in COMP_SLUG else None})
    # players snapshot: best-rated across leagues (n>=2)
    best = []
    for c, d in pins.items():
        for r in d.get("ratings", [])[:5]:
            best.append(dict(r, comp=c))
    best.sort(key=lambda r: (-r["avg"], -r["n"]))
    best_rows = [{"name": r["name"], "club": r["club"], "comp": comp_label(r["comp"]), "n": r["n"],
                  "avg": f'{r["avg"]:.2f}'} for r in best[:12]]
    write("analysis.html", render(
        "analysis.html", page_head=Markup(page_head), crumbs_ld=Markup(crumbs_ld),
        n_comps=len(comps), n_pred=n_pred, nav=nav, week=week, disclaimer=Markup(AN_DISCLAIMER),
        power=power, best=best_rows, accuracy=Markup(accuracy_html(acc)),
        explainer=Markup(model_explainer()), page_foot=Markup(foot())))
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
        page_head = head(f"تحليلات {label}: توقعات المباريات وقوة الأندية واللاعبون — يلا سكور",
                         f"توقعات مباريات {label} القادمة باحتمالات مبنية على نتائج الموسم، ترتيب قوة الأندية (Elo) "
                         f"ومؤشرات الهجوم والدفاع، توقيت الأهداف، وأعلى اللاعبين تقييمًا.",
                         SITE_BASE + f"/analysis/{slug}.html", active="analysis")
        crumbs_ld = breadcrumb_ld([("أخبار", SITE_BASE + "/"), ("تحليلات", SITE_BASE + "/analysis.html"),
                                   (label, SITE_BASE + f"/analysis/{slug}.html")])
        # all upcoming of this comp within 14 days
        wk2 = (today + datetime.timedelta(days=14)).isoformat()
        rows = sorted([(m, preds[str(m["match_id"])]) for m in upcoming
                       if m.get("competition") == c and str(m.get("match_id")) in preds and (m.get("kickoff") or "") <= wk2],
                      key=lambda t: (t[0].get("kickoff") or "", t[0].get("koff_time") or ""))
        pred_rows = [Markup(pred_row(m, p)) for m, p in rows]
        power_html = Markup(power_table(c, stats, params, forms.get(c, {})))
        pi = pins.get(c)
        si = sins.get(c)
        players = None
        if pi or si:
            players = ""
            if si and si.get("ga"):
                players += ga_table(si["ga"], si.get("share", []), "الأكثر مساهمة في الأهداف (أهداف + صناعة)")
            if pi and pi.get("ratings"):
                players += ratings_table(pi["ratings"][:10], "أعلى اللاعبين تقييمًا (مرتان أساسيًا على الأقل)")
            players = Markup(players)
        timing = None
        if pi and sum(pi["timing"].values()) >= 10:
            late = sorted(pi["club_late"].items(), key=lambda kv: -kv[1]["late_share"])[:3]
            early = sorted(pi["club_late"].items(), key=lambda kv: -(kv[1]["early"] / kv[1]["total"]))[:3]
            timing = {
                "goals": sum(pi["timing"].values()), "games": _games(pi["n_matches"]),
                "bars": Markup(timing_bars(pi["timing"], "الأهداف حسب فترة المباراة (بالدقائق)")),
                "late": Markup('، '.join(f'<bdi>{esc(k)}</bdi> ({v["late"]} من {v["total"]})'
                                         for k, v in late if v["late"])) if late else None,
                "early": Markup('، '.join(f'<bdi>{esc(k)}</bdi> ({v["early"]} من {v["total"]})'
                                          for k, v in early if v["early"])) if early else None}
        ca = {"all": acc["comps"].get(c), "comps": {}, "recent": [e for e in acc.get("recent", []) if e.get("comp") == c]}
        # the standings page exists only for a competition with ONE table; a
        # cup (CAF CL) has group tables and no /standings page, so linking it
        # unconditionally left a dead link on that league's analysis page
        write(f"analysis/{slug}.html", render(
            "analysis_league.html", page_head=Markup(page_head), crumbs_ld=Markup(crumbs_ld),
            label=label, slug=slug, games=_games(params["n"]), gpm=f'{(params["gpm"] or 0):.2f}',
            home_win=_pct(params["home_win"]) if params["home_win"] is not None else None,
            draw=_pct(params["draw"]) if params["home_win"] is not None else None,
            rows=pred_rows, disclaimer=Markup(AN_DISCLAIMER), power=power_html,
            players=players, timing=timing, accuracy=Markup(accuracy_html(ca, anchor=False)),
            has_table=bool((has_table or set()) and comp_has_table(c, has_table)),
            page_foot=Markup(foot())))
        urls.append(f"/analysis/{slug}.html")
    return urls


# ---- slice 4: build()'s page sections as functions (tools/extract_sections.py) ----
_UNSET = object()      # 'this build() variable was not bound at the call'


def _bound(scope, names):
    return {k: scope[k] for k in names if k in scope}


def _page_home(_acc, _cal, _preds, _upcoming, articles, fixtures, headlines, matches, reels,
               standings, videos):
    """/ - markup and the user's standing rules for it: site_src/templates/
    home.html (templated 2026-09-26). The pieces are built here in the same
    order as before; the loops' last h / m / v keep their names, as when this
    lived inside build()."""
    feat = articles[0] if articles else None    # og:image source
    page_head = head(f"{SITE_NAME} — {SITE_TAGLINE}", SITE_DESC, SITE_BASE + "/",
                     image=(feat and feat.get("image_url")) or None, active="home",
                     # the hero block renders the THUMB now - preloading the
                     # full 1600 would fetch a file the page never uses
                     preload_img=thumb_url(feat and feat.get("image_url")) or None)
    org_ld = jsonld({
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
             "publisher": {"@id": SITE_BASE + "/#org"}}]})
    ad = adsense_slot()
    news_filter = news_filter_bar()
    blocks = []
    used = set()
    if articles:
        b1 = articles[:5]
        used = {a["article_id"] for a in b1}
        blocks.append(fmb_block(b1[0], b1[1:], "الأكثر تداولًا", "/news.html", nf="trend"))
        egy = [a for a in articles
               if a["article_id"] not in used and _egy_article(a)]
        if len(egy) >= 2:
            blocks.append(fmb_block(egy[0], egy[1:5], "أخبار الكرة المصرية",
                                    "/news/egypt.html", nf="egy"))
            used |= {a["article_id"] for a in egy[:5]}
        eur = [a for a in articles
               if a["article_id"] not in used and _eur_article(a)]
        if len(eur) >= 2:
            blocks.append(fmb_block(eur[0], eur[1:5], "أخبار الكرة الأوروبية",
                                    "/news/europe.html", flip=True, nf="eur"))
            used |= {a["article_id"] for a in eur[:5]}
    predictions = pred_home_block(_upcoming, _preds, datetime.date.fromisoformat(REF_TODAY),
                                  acc=_acc, cal=_cal)
    show_videos = bool(videos and SHOW_VIDEOS)
    video_facades = []
    if show_videos:
        for v in videos[:3]:
            video_facades.append(video_facade(v))
    reels_banner = ""
    if reels and SHOW_REELS:
        r0 = reels[0]
        rthumb = f"https://i.ytimg.com/vi/{esc(r0.get('video_id'))}/oar2.jpg"
        rfb = f"https://i.ytimg.com/vi/{esc(r0.get('video_id'))}/hqdefault.jpg"
        reels_banner = f"""<a class="reels-banner" href="/reels.html">
  <img src="{rthumb}" alt="" loading="lazy" onerror="this.onerror=null;this.src='{rfb}'">
  <div class="rb-body">
    <h2>⚡ ريلز يلا سكور</h2>
    <p>مقاطع قصيرة ممتعة — اضغط للمشاهدة، واسحب لفوق تجيب اللي بعده</p>
    <span class="rb-cta">شاهد الآن ▶</span>
  </div></a>"""
    show_headlines = bool(headlines and SHOW_HEADLINES)
    headline_cards = []
    if show_headlines:
        for h in headlines[:24]:
            headline_cards.append(headline_card(h))
    strip = clubs_strip(standings, matches, fixtures)
    # crests + per-match page URL for the live card, curated clubs only
    # (keyed by the Arabic name pair - LIVE_JS normalizes both sides)
    fav_meta = {}
    for m in matches:
        if _is_ticker_team(m) and m.get("match_id"):
            fav_meta[f'{ar_team(m.get("home"))}|{ar_team(m.get("away"))}'] = {
                "hb": local_crest(m["home_badge"]) if m.get("home_badge") else "",
                "ab": local_crest(m["away_badge"]) if m.get("away_badge") else "",
                "u": match_url(m)}
    fav_script = ('<script>window.__favClubs='
                  + json.dumps(fav_club_names(standings, fixtures), ensure_ascii=False)
                  + ';window.__favMeta='
                  + json.dumps(fav_meta, ensure_ascii=False)
                  + ';</script>')
    write("index.html", render(
        "home.html", page_head=Markup(page_head), org_ld=Markup(org_ld), ad=Markup(ad),
        news_filter=Markup(news_filter), blocks=[Markup(b) for b in blocks],
        predictions=Markup(predictions), show_videos=show_videos,
        video_facades=[Markup(f) for f in video_facades], video_js=Markup(VIDEO_JS),
        reels_banner=Markup(reels_banner), show_headlines=show_headlines,
        headline_cards=[Markup(c) for c in headline_cards], clubs_strip=Markup(strip),
        fav_script=Markup(fav_script), page_foot=Markup(foot())))
    _l = locals()
    return {k: _l[k] for k in ('h', 'm', 'v') if k in _l}


def _page_article_pages(articles, articles_all, matches, urls):
    """/a/<id> for every article (listed or not - each keeps its page). The
    markup is site_src/templates/article.html (templated 2026-09-25); this
    function prepares the values, the NewsArticle / breadcrumb / FAQ JSON-LD,
    the noindex rule and the sitemap bookkeeping - in the same order as before,
    so functions with side effects still run in the same sequence.

    Match previews/reports do not get a page of their own: they render inside
    /m/<match_id> and their old /a/ URL is a stub that 301s there.

    Returns what later pages read from this section. `a`, `img`, `_clubs`,
    `_faq` and `_t` are the loop's LAST values, kept under the same names so
    they end exactly as they did when this section still lived inside build()."""
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
    _l = locals()
    return {k: _l[k] for k in ('_clubs', '_faq', '_match_arts', '_moved', '_t', 'a', 'img', 'p') if k in _l}


def _page_matches_page(_plog, _preds, articles, fixtures, forms, fx_by_comp, ge_idx,
                       league_stats_parts, matches, st_by_comp, standings):
    """/matches - the per-day navigator. Markup: site_src/templates/matches.html
    (templated 2026-09-26). The loops below are the ones that used to append
    HTML, in the same order and under the same names - they now fill the
    structures the template renders - so every helper runs in the same
    sequence and the loop variables build() reads afterwards (a, comp, i, img,
    k, m, st) end exactly where they used to. comp_order is the real output."""
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
    pieces = []          # every dynamic piece, for pred_pop's "any prediction button?"
    page_head = head(f"مواعيد ونتائج المباريات — {SITE_NAME}",
                     "مواعيد ونتائج مباريات كرة القدم بتوقيت القاهرة على يلا سكور.",
                     SITE_BASE + "/matches.html", active="matches")
    leagues = []
    for c in comp_order:
        leagues.append({"comp": c, "icon": Markup(comp_icon(c)), "label": comp_label(c)})
    ad = adsense_slot()
    LEAGUE_TABS = [("table", "الترتيب"), ("scorers", "الهدافون"),
                   ("numbers", "الأرقام"), ("trend", "التطور"),
                   ("rounds", "الجولات")]
    views = []
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
        tabs = []
        for i, (k, lbl) in enumerate(live):
            tabs.append((k, lbl))
        view_panes = []
        for i, (k, lbl) in enumerate(live):
            view_panes.append((k, Markup(panes[k])))
            pieces.append(panes[k])
        views.append({"comp": c, "tabs": tabs, "panes": view_panes})
    days = []
    for d in sorted_days:
        day = {"day": d, "heading": fmt_day(d), "comps": []}
        comps = OrderedDict()
        for m in daymap[d]:
            comps.setdefault(m.get("competition") or "", []).append(m)
        # same fixed league order as the sidebar
        for comp, ms in sorted(comps.items(),
                               key=lambda kv: (COMP_ORDER.index(kv[0])
                                               if kv[0] in COMP_ORDER
                                               else len(COMP_ORDER), kv[0])):
            block = {"comp": comp, "label": comp_label(comp), "rows": []}
            if comp:
                block["icon"] = Markup(comp_icon(comp))
                comp_label(comp)                 # (the old code asked twice; kept for order)
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
                block["rows"].append(Markup(row))
                pieces.append(row)
            day["comps"].append(block)
        days.append(day)
    # left rail: per-league fixtures BY DAY for leagues without round data
    comp_fix = {}
    for d in sorted_days:
        for m in daymap[d]:
            comp_fix.setdefault(m.get("competition") or "", {}).setdefault(d, []).append(m)
    rail = []
    for c in comp_order:
        if c not in fx_by_comp and comp_fix.get(c):
            entry = {"comp": c, "icon": Markup(comp_icon(c)), "label": comp_label(c), "days": []}
            for d in sorted(comp_fix[c].keys()):
                fday = {"heading": fmt_day(d), "minis": []}
                for m in comp_fix[c][d]:
                    mini = fixture_mini(m)
                    fday["minis"].append(Markup(mini))
                    pieces.append(mini)
                entry["days"].append(fday)
            rail.append(entry)
    feat, news = None, []
    if articles:
        fa = articles[0]
        feat = {"href": Markup(article_href(fa)), "has_img": bool(fa.get("image_url")),
                "img": thumb_url(fa["image_url"]) if fa.get("image_url") else "",
                "title": fa.get("title")}
        for a in articles[1:4]:
            img = thumb_url(a.get("image_url"))
            th = (f'<span class="mn-th" style="background-image:url(\'{esc(img)}\')"></span>'
                  if img else '<span class="mn-th noimg">⚽</span>')
            news.append({"href": Markup(article_href(a)), "th": Markup(th),
                         "title": a.get("title"), "date": a.get("pub_date") or ""})
    popup = pred_pop(pieces)
    write("matches.html", render(
        "matches.html", page_head=Markup(page_head), leagues=leagues, ad=Markup(ad),
        views=views, filters=Markup(FILTERS_HTML), today=REF_TODAY, days=days, rail=rail,
        feat=feat, news=news, matches_js=Markup(MATCHES_JS), rounds_js=Markup(ROUNDS_JS),
        popup=Markup(popup), page_foot=Markup(foot())))
    _l = locals()
    return {k: _l[k] for k in ('a', 'comp', 'comp_order', 'i', 'img', 'k', 'm', 'st') if k in _l}


def _page_per_match_pages(_bycomp, _cal, _lparams, _match_arts, _plog, _preds, _squad, _tstats,
                          articles, fixtures, forms, ge_idx, matches, md_idx, st_by_comp, urls):
    """/m/<id> - one landing page per match (archive + current window): the
    long-tail queries a single /matches can never rank for («نتيجة مباراة X»،
    «موعد مباراة Y والقناة الناقلة»). Old pages persist through
    matches_archive.json so an indexed URL does not 404 once the match leaves
    the day window; pages get the live layer for free (match_row emits data-lv,
    LIVE_JS ships in foot()).

    Markup: site_src/templates/match.html (templated 2026-09-26). Everything
    else - the titles, the kick-off sentence, the readings, the noindex rule,
    the sitemap choice - is computed here in the same order and under the same
    names as before, so the helpers run in the same sequence and the values
    build() reads afterwards (m_all, and the loop's last _h, _html, _slug, a,
    comp, desc, img, m, st, title, v, when) end exactly where they used to."""
    os.makedirs(os.path.join(DIST, "m"), exist_ok=True)
    # finished matches per competition (season pool + fixtures) - table_after()
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
        page_head = head(title, desc, SITE_BASE + murl, image=img, active="matches")
        hero_row = match_row(m, show_time=True, show_comp=True, goals=_goals)
        kickoff_info = st not in ("FINISHED", "POSTPONED")
        _tw = _rd = ""
        if kickoff_info:
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
        # the match's own article (layer 3, 2026-09-16): the story sits above
        # the computed reading, which is what backs it with numbers
        _art = pick_match_article(_match_arts.get(str(mid)) or [], st)
        article_block = match_article_block(_art, m.get("competition") or "") if _art else ""
        # «قراءة قبل المباراة» (layer 1): how the two clubs arrive
        _pre_weight = 0
        pre_read = ""
        if st == "UPCOMING":
            _pre, _pre_faq, _pre_weight = pre_match_read(
                m, h_ar, a_ar, comp,
                st_by_comp.get(m.get("competition")),
                forms.get(m.get("competition")) or {},
                _fin_by_comp.get(m.get("competition")) or [], _fin_all,
                _preds.get(str(mid)))
            if _pre:
                pre_read = _pre
        _det = match_details_for(md_idx, m)
        # «قراءة المباراة» - the summary goes ABOVE the evidence
        _faq_html = _pre_faq if st == "UPCOMING" and _pre_weight else ""
        post_read = ""
        if st == "FINISHED" and _det and hs is not None and as_ is not None:
            _read, _faq_html = post_match_read(
                m, _det[0], _det[1], h_ar, a_ar, hs, as_, comp,
                st_by_comp.get(m.get("competition")),
                forms.get(m.get("competition")) or {},
                _fin_by_comp.get(m.get("competition")) or [])
            if _read:
                post_read = _read
        details = ""
        if _det:
            details = match_details_html(_det[0], _det[1], h_ar, a_ar)
        else:
            # announced XI before kick-off: the pitch, then who is missing
            _pre = prematch_for(md_idx, m)
            if _pre:
                details = match_details_html(_pre[0], _pre[1], h_ar, a_ar)
        absence = absence_block(_squad, m.get("competition"), m, h_ar, a_ar)
        # «توقع يلا سكور»: model probabilities for an upcoming match; for a
        # finished one, what the model said before kick-off vs the result
        _pb = pred_block(m, _preds.get(str(mid)) if st == "UPCOMING" else None,
                         _plog.get(str(mid)), _tstats.get(m.get("competition"), {}),
                         params=_lparams.get(m.get("competition")), cal=_cal)
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
        info_rows = []
        for k, v in info:
            # the live layer overwrites the state text while the match can still
            # move (UPCOMING -> LIVE -> FINISHED); a finished page stays static
            info_rows.append((k, str(v), k == "الحالة" and st in ("UPCOMING", "LIVE")))
        _clubs = [tp for tp in TEAM_PAGES if _team_match(tp, m)]
        stc = st_by_comp.get(m.get("competition"))
        table = table_heading = ""
        if stc and stc.get("table"):
            _slug = COMP_SLUG.get(m.get("competition"))
            _h = (f'<a href="/standings/{_slug}.html">ترتيب {esc(comp)} ←</a>'
                  if _slug else f'ترتيب {esc(comp)}')
            table_heading = _h
            table = standings_table(m.get("competition"), stc["table"],
                                    past=stc.get("past"),
                                    season_label=stc.get("season_label"),
                                    zeroed=stc.get("zeroed"),
                                    form_map=forms.get(m.get("competition"), {}),
                                    embedded=True)
        news = []
        if articles:
            for a in articles[:4]:
                news.append({"href": Markup(article_href(a)), "title": a["title"]})
        crumbs_ld = breadcrumb_ld([("أخبار", SITE_BASE + "/"),
                                   ("المباريات", SITE_BASE + "/matches.html"),
                                   (comp, SITE_BASE + murl)])
        _html = render(
            "match.html", page_head=Markup(page_head), comp=comp, h_ar=h_ar, a_ar=a_ar,
            hero_row=Markup(hero_row), kickoff_info=kickoff_info, round_txt=Markup(_rd),
            when_txt=Markup(_tw), channel=str(m["channel"]) if m.get("channel") else "",
            comp_tv=COMP_TV.get(m.get("competition")) or "",
            article_block=Markup(article_block), pre_read=Markup(pre_read),
            post_read=Markup(post_read), details=Markup(details), absence=Markup(absence),
            prediction=Markup(_pb or ""), info=info_rows,
            clubs=[{"slug": Markup(tp["slug"]), "name": tp["name"]} for tp in _clubs],
            has_table=bool(stc and stc.get("table")), table_heading=Markup(table_heading),
            table=Markup(table), faq=Markup(_faq_html or ""), news=news,
            crumbs_ld=Markup(crumbs_ld), page_foot=Markup(foot()))
        # lastmod: a page whose match is recent/upcoming changes every run;
        # an old finished match settled around its kickoff day.
        _LASTMOD[murl] = (REF_TODAY if m["kickoff"] >= (datetime.date.today()
                                                        - datetime.timedelta(days=2)).isoformat()
                          else m["kickoff"])
        # AdSense "low value content" rejection (2026-09-04): a match page with
        # no real content yet (no scorers, no lineups/details) stays reachable
        # but is NOINDEXed and out of the sitemap; it becomes indexable once the
        # data arrives. Since 2026-09-14 a fixture whose pre-match reading found
        # at least four substantive facts counts as content (a guide, not a stub).
        _rich = bool(_art) or bool(_goals) or bool(_det) or _pre_weight >= 4
        if not _rich:
            _html = _html.replace("<head>", '<head><meta name="robots" content="noindex">', 1)
        write(f"m/{mid}.html", _html)
        n_mp += 1
        if _rich:
            n_mp_idx += 1
            # WHAT WE ADVERTISE vs what we publish (2026-09-20): every rich match
            # page stays indexable and linked; the sitemap carries only the last
            # 7 days + everything to come, any curated-club match, and any page
            # carrying an original article (that URL replaced an article URL).
            if m["kickoff"] >= sm_cut or _art or _clubs:
                urls.append(murl)
                n_mp_sm += 1
    print(f"  + match pages: {n_mp} ({n_mp_idx} indexable, {n_mp_sm} in the sitemap)")
    _l = locals()
    return {k: _l[k] for k in ('_h', '_html', '_slug', 'a', 'comp', 'desc', 'img', 'm', 'm_all', 'st', 'title', 'v', 'when') if k in _l}


def _page_per_league_standings_top_scorers_pages(_bycomp, _preds, as_by_comp, as_ok, forms,
                                                 matches, sc_by_comp, sc_ok, st_by_comp, urls):
    """Evergreen SEO landing pages with their own URLs: «ترتيب الدوري المصري» and
    «هدافو الدوري المصري» are huge monthly queries that a tab inside /matches can
    never rank for. One /standings/<slug> per league with a table, and one
    /scorers/<slug> when the charts are current (the stale-last-season guard
    sc_ok/as_ok gates them, same as /matches). Markup: templates standings.html
    + scorers.html (2026-09-26); the pieces are built here in the same order as
    before. The loop's last comp/label/slug/st/m/up_next are returned under the
    same names, as when this lived inside build()."""
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
            page_head = Markup(head(f"ترتيب {label} {season} — جدول الترتيب الكامل | {SITE_NAME}",
                                    f"جدول ترتيب {label} لموسم {season} محدثًا تلقائيًا: "
                                    "النقاط والمباريات والأهداف وفارق الأهداف "
                                    "ونتائج آخر 5 مباريات لكل فريق.",
                                    SITE_BASE + st_url, active="matches"))
            crumbs_ld = Markup(breadcrumb_ld([("أخبار", SITE_BASE + "/"),
                                              ("المباريات", SITE_BASE + "/matches.html"),
                                              (f"ترتيب {label}", SITE_BASE + st_url)]))
            table = standings_table(comp, st["table"], past=st.get("past"),
                                    season_label=st.get("season_label"),
                                    zeroed=st.get("zeroed"),
                                    form_map=forms.get(comp, {}), embedded=True)
            _an, _faq = standings_analysis(comp, label, season, st["table"],
                                           forms.get(comp, {}), sc or [], up_next,
                                           zeroed=st.get("zeroed"))
            scorers = scorers_list(sc, "أهداف") if sc else ""
            next_rows = []
            for m in up_next:
                next_rows.append(match_row(m, show_time=True, show_comp=False,
                                           link=match_url(m),
                                           pred=_preds.get(str(m.get("match_id")))))
            # the popup is added only when a row carries a prediction button
            popup = pred_pop([table, _an, scorers] + next_rows + [_faq])
            write(f"standings/{slug}.html", render(
                "standings.html", page_head=page_head, crumbs_ld=crumbs_ld, label=label,
                season=season, table=Markup(table), analysis=Markup(_an), has_sc=bool(sc),
                sc_url=Markup(sc_url), scorers=Markup(scorers),
                next_rows=[Markup(r) for r in next_rows], faq=Markup(_faq),
                popup=Markup(popup), page_foot=Markup(foot())))
            urls.append(st_url)
            n_lp += 1
        if sc or (st and st.get("table")):
            # the page must exist whenever the league is active (the footer
            # links to /scorers/egypt.html sitewide) - a stale-gated chart
            # gets a placeholder, never last season's names
            page_head = Markup(head(f"هدافو {label} {season} — ترتيب الهدافين وصناع الأهداف | {SITE_NAME}",
                                    f"قائمة هدافي {label} لموسم {season} محدثة تلقائيًا بعد كل "
                                    "جولة، مع ترتيب صناع الأهداف (التمريرات الحاسمة).",
                                    SITE_BASE + sc_url, active="matches"))
            scorers = scorers_list(sc, "أهداف") if sc else ""
            assists = scorers_list(asst, "صناعة") if asst else ""
            # a list of ten names is not a page; the reading is what makes it
            # one (2026-09-16, after an outside audit found /scorers/egypt
            # empty - see scorers_read)
            _sr, _sfaq, _sw = scorers_read(label, season, sc, asst,
                                           (st or {}).get("table"), _bycomp.get(comp))
            _html = render(
                "scorers.html", page_head=page_head, label=label, season=season,
                has_sc=bool(sc), scorers=Markup(scorers), has_asst=bool(asst),
                assists=Markup(assists), reading=Markup(_sr or ""),
                has_table=bool(st and st.get("table")), st_url=Markup(st_url),
                reading_faq=Markup(_sfaq or ""), page_foot=Markup(foot()))
            # Indexable only once the page says something: the chart plus a
            # reading of at least three facts. Under that it stays what it was
            # before - a page for visitors and old links, out of the index and
            # out of the sitemap - because ~80 words of names is exactly the
            # thin content the AdSense rejection named.
            _rich_sc = bool(sc) and _sw >= 3
            if not _rich_sc:
                _html = _html.replace("<head>", '<head><meta name="robots" content="noindex">', 1)
            write(f"scorers/{slug}.html", _html)
            if _rich_sc:
                urls.append(sc_url)
            n_lp += 1
    print(f"  + league pages: {n_lp}")
    _l = locals()
    return {k: _l[k] for k in ('_comps_with_table', 'comp', 'label', 'm', 'season', 'slug', 'st', 'up_next') if k in _l}


def _page_per_league_season_fixtures(fx_by_comp, season, st_by_comp, urls):
    """/fixtures/<slug> - a league's whole season. These used to be INSIDE
    /matches, hidden behind the league filter: 2,206 fixture rows and 4,955
    crest tags that every visitor downloaded to look at the 82 rows of one day.
    As their own pages they cost nothing to the people who do not want them and
    answer a real query - «جدول مباريات الدوري المصري». Markup: fixtures.html
    (templated 2026-09-26). Returns the loop's last comp/label/slug, as before."""
    os.makedirs(os.path.join(DIST, "fixtures"), exist_ok=True)
    n_fx = 0
    for comp, slug in COMP_SLUG.items():
        fx = fx_by_comp.get(comp)
        rounds = (fx or {}).get("rounds") or []
        if not rounds:
            continue
        label = comp_label(comp)
        n_m = sum(len(r.get("matches") or []) for r in rounds)
        page_head = Markup(head(f"جدول مباريات {label} {season} — كل الجولات | {SITE_NAME}",
                                f"جدول مباريات {label} لموسم {season} كاملًا: {len(rounds)} جولة "
                                f"و{n_m} مباراة بمواعيدها ونتائجها، محدّثًا تلقائيًا بعد كل جولة.",
                                SITE_BASE + f"/fixtures/{slug}.html", active="matches"))
        rounds_panel = league_rounds_panel(comp, fx, embedded=True)
        _links = [f'<a href="/matches.html">مباريات اليوم ←</a>']
        if comp in st_by_comp and (st_by_comp[comp] or {}).get("table"):
            _links.append(f'<a href="/standings/{slug}.html">ترتيب {esc(label)} ←</a>')
        if comp in COMP_SLUG and os.path.exists(os.path.join(DIST, "analysis", f"{slug}.html")):
            _links.append(f'<a href="/analysis/{slug}.html">تحليلات وتوقعات {esc(label)} ←</a>')
        crumbs_ld = breadcrumb_ld([("أخبار", SITE_BASE + "/"),
                                   ("المباريات", SITE_BASE + "/matches.html"),
                                   (f"جدول {label}", SITE_BASE + f"/fixtures/{slug}.html")])
        write(f"fixtures/{slug}.html", render(
            "fixtures.html", page_head=page_head, label=label, season=season,
            n_rounds=len(rounds), n_matches=n_m, rounds_panel=Markup(rounds_panel),
            links=[Markup(x) for x in _links], crumbs_ld=Markup(crumbs_ld),
            page_foot=Markup(foot()), rounds_js=Markup(ROUNDS_JS)))
        urls.append(f"/fixtures/{slug}.html")
        _LASTMOD[f"/fixtures/{slug}.html"] = REF_TODAY
        n_fx += 1
    print(f"  + season fixture pages: {n_fx}")
    _l = locals()
    return {k: _l[k] for k in ('comp', 'label', 'slug') if k in _l}


def _page_analysis_hub_analysis_league(_acc, _comps_with_table, _lparams, _pins, _plog, _preds,
                                       _sins, _tstats, _upcoming, forms, matches, urls):
    """/analysis hub + /analysis/<league> + /predictions (the markup still lives
    in analysis_pages() and prediction_history_page() - their own templating
    step)."""
    os.makedirs(os.path.join(DIST, "analysis"), exist_ok=True)
    _hist_url = prediction_history_page(_plog, _acc)
    if _hist_url:
        urls.append(_hist_url)
        print(f"  + prediction history: {_acc['all']['n']} scored predictions")
    _an_urls = analysis_pages(matches, _upcoming, _preds, _plog, _acc, _tstats, _lparams,
                              _pins, _sins, forms, _comps_with_table)
    urls.extend(_an_urls)
    print(f"  + analysis pages: {len(_an_urls)}")


def _page_per_club_pages(_plog, _preds, articles, forms, m_all, season, st_by_comp, urls):
    """/team/<slug> - evergreen SEO hubs for the highest-volume Arabic query
    family: «أخبار الأهلي اليوم»، «مباريات الزمالك القادمة»، «نتيجة ريال مدريد».
    One page per curated club: latest news + next matches + recent results +
    league standing, refreshed every publish cycle; cross-linked from article
    pages, match pages (club-chips) and the footer. Markup: club.html
    (templated 2026-09-26); the pieces are built here in the same order as
    before. Returns the loop's last _img / a / img / r under the same names."""
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
        page_head = head(title, desc, SITE_BASE + t_url, image=img)
        crumbs_ld = breadcrumb_ld([("أخبار", SITE_BASE + "/"),
                                   ("المباريات", SITE_BASE + "/matches.html"),
                                   (name, SITE_BASE + t_url)])
        _img = (f'<img class="club-crest" src="{esc(crest)}" alt="{esc(name)}" '
                'width="64" height="64" loading="eager">' if crest else "")
        _pos = ""
        if srow:
            _pos = (f'<p class="club-pos">المركز <b>{srow.get("pos")}</b> في '
                    f'{esc(league_ar)} برصيد <b>{srow.get("pts")}</b> نقطة '
                    f'من {srow.get("played")} مباراة</p>')
        up_rows = []
        for m in up_next:
            up_rows.append(match_row(m, show_time=True, show_comp=True,
                                     link=match_url(m),
                                     pred=_preds.get(str(m.get("match_id")))))
        last_rows = []
        for m in last_res:
            last_rows.append(match_row(m, show_time=False, show_comp=True,
                                       link=match_url(m),
                                       done=_plog.get(str(m.get("match_id")))))
        news_items = []
        for a in news:
            _t = art_reltime(a)
            news_items.append({"href": Markup(article_href(a)), "title": a["title"],
                               "when": Markup(_t) if _t else ""})
        table = table_heading = ""
        if st and st.get("table"):
            _slug = COMP_SLUG.get(tp["league"])
            table_heading = (f'<a href="/standings/{_slug}.html">ترتيب {esc(league_ar)} ←</a>'
                             if _slug else f'ترتيب {esc(league_ar)}')
            table = standings_table(tp["league"], st["table"],
                                    past=st.get("past"),
                                    season_label=st.get("season_label"),
                                    zeroed=st.get("zeroed"),
                                    form_map=forms.get(tp["league"], {}),
                                    embedded=True)
        others = [o for o in TEAM_PAGES if o["slug"] != slug]
        club_ld = jsonld({
            "@context": "https://schema.org", "@type": "SportsTeam",
            "name": name, "sport": "Football", "url": SITE_BASE + t_url,
            **({"logo": img} if img else {}),
            "memberOf": {"@type": "SportsOrganization", "name": league_ar},
        })
        # the popup is added only when a row carries a prediction button
        popup = pred_pop([page_head, crumbs_ld, _img, _pos] + up_rows + last_rows
                         + [table_heading, table, club_ld])
        write(f"team/{slug}.html", render(
            "club.html", page_head=Markup(page_head), crumbs_ld=Markup(crumbs_ld),
            name=name, crest_img=Markup(_img), position=Markup(_pos),
            up_rows=[Markup(x) for x in up_rows], last_rows=[Markup(x) for x in last_rows],
            news=news_items, has_table=bool(st and st.get("table")),
            table_heading=Markup(table_heading), table=Markup(table),
            others=[{"slug": Markup(o["slug"]), "name": o["name"]} for o in others],
            club_ld=Markup(club_ld), popup=Markup(popup), page_foot=Markup(foot())))
        urls.append(t_url)
    print(f"  + club pages: {len(TEAM_PAGES)}")
    _l = locals()
    return {k: _l[k] for k in ('_img', 'a', 'img', 'r') if k in _l}


def _page_stats_dashboard(comp_order, fixtures, forms, league_stats_sec, matches, sc_by_comp,
                          sc_ok, st_by_comp, urls):
    """/stats - the visual stats board. Markup: site_src/templates/stats.html
    (templated 2026-09-26). Noindexed unless SHOW_STATS_PAGE."""
    page_head = head(f"إحصائيات وتحليلات — {SITE_NAME}",
                     "لوحة إحصائيات مرئية: سباق النقاط، الأهداف في كل جولة، وأرقام الموسم لكل بطولة.",
                     SITE_BASE + "/stats.html", active="stats")
    page_title = page_head_ad(
        '<h1 class="page-h">📊 إحصائيات وتحليلات</h1>',
        'أرقام محسوبة من نتائج الموسم الحالي — تتحدّث تلقائيًا بعد كل جولة.')
    clubs = clubs_panel(st_by_comp, sc_ok, sc_by_comp, forms, matches, fixtures)
    sections = []
    for comp in comp_order:
        sec = league_stats_sec(comp)
        if sec:
            sections.append(Markup(sec))
    html_out = render("stats.html", page_head=Markup(page_head), page_title=Markup(page_title),
                      clubs=Markup(clubs), sections=sections, page_foot=Markup(foot()))
    if not SHOW_STATS_PAGE:
        html_out = html_out.replace("<head>", '<head><meta name="robots" content="noindex">', 1)
    write("stats.html", html_out)
    if SHOW_STATS_PAGE:
        urls.append("/stats.html")


def _page_404():
    """/404 - served by Cloudflare for any missing asset; not in the sitemap on
    purpose. Text: site_src/templates/404.html. The auto-retry (snippets/
    nf_retry_js.html) exists for one real case: an article page can 404 for a
    minute or two right around a deploy while the reader already holds a newer
    home page - the page re-checks itself and reloads the moment the URL starts
    resolving. Bounded: a genuinely dead link stops polling after ~2 minutes."""
    page_head = Markup(head(f"الصفحة غير موجودة — {SITE_NAME}",
                            "الصفحة التي تبحث عنها غير موجودة.",
                            SITE_BASE + "/404.html"))
    write("404.html", render("404.html", page_head=page_head,
                             retry_js=Markup(_src("snippets/nf_retry_js.html")),
                             page_foot=Markup(foot())))


def _page_privacy_policy(urls):
    """/privacy (required for AdSense). The text is site_src/templates/privacy.html;
    this function only hands it the pieces that change (templated 2026-09-25)."""
    contact = (Markup(f'راسِلنا على <a href="mailto:{esc(CONTACT_EMAIL)}">{esc(CONTACT_EMAIL)}</a>.')
               if CONTACT_EMAIL else 'يمكنك التواصل معنا عبر قنواتنا الرسمية.')
    write("privacy.html", render(
        "privacy.html",
        page_head=Markup(head("سياسة الخصوصية — " + SITE_NAME,
                              "سياسة الخصوصية وملفات تعريف الارتباط والإعلانات في موقع يلا سكور.",
                              SITE_BASE + "/privacy.html")),
        ref_today=REF_TODAY,
        contact=contact,
        page_foot=Markup(foot())))
    urls.append("/privacy.html")


def _page_about(urls):
    """/about and /editors (AdSense / E-E-A-T identity pages). Text:
    site_src/templates/about.html + editors.html (templated 2026-09-25)."""
    common = dict(site_name=SITE_NAME)
    write("about.html", render(
        "about.html",
        page_head=Markup(head("من نحن — " + SITE_NAME,
                              "تعرّف على يلا سكور: موقع عربي لأخبار كرة القدم ونتائج المباريات وجداول الترتيب.",
                              SITE_BASE + "/about.html")),
        page_foot=Markup(foot()), **common))
    urls.append("/about.html")

    # /editors - publisher identity for the AdSense / E-E-A-T review (2nd
    # rejection 2026-09-04 cited low value content); linked from every
    # article byline, the footer and /about
    page_head = Markup(head("فريق التحرير — " + SITE_NAME,
                            f"من يقف خلف {SITE_NAME}: مدير التحرير، طريقة عملنا في التحقق من الأخبار، وكيف تتواصل معنا للتصحيح.",
                            SITE_BASE + "/editors.html"))
    page_ld = Markup(jsonld({
        "@context": "https://schema.org", "@type": "ProfilePage",
        "name": f"فريق التحرير — {SITE_NAME}", "url": SITE_BASE + "/editors.html",
        "mainEntity": {"@type": "Person", "name": EDITOR_NAME, "jobTitle": EDITOR_ROLE,
                       "email": f"mailto:{EDITOR_EMAIL}", "url": SITE_BASE + "/editors.html",
                       "worksFor": {"@type": "Organization", "name": SITE_NAME, "url": SITE_BASE}},
    }))
    write("editors.html", render(
        "editors.html", page_head=page_head, page_ld=page_ld, page_foot=Markup(foot()),
        editor_name=EDITOR_NAME, editor_role=EDITOR_ROLE, editor_email=EDITOR_EMAIL,
        fb_page_url=FB_PAGE_URL, tg_channel_url=TG_CHANNEL_URL, **common))
    urls.append("/editors.html")


def _page_contact(urls):
    """/contact - text in site_src/templates/contact.html (templated 2026-09-25)."""
    write("contact.html", render(
        "contact.html",
        page_head=Markup(head("اتصل بنا — " + SITE_NAME,
                              "تواصل مع فريق يلا سكور للاستفسارات والتصحيحات والإعلانات.",
                              SITE_BASE + "/contact.html")),
        contact_email=CONTACT_EMAIL, page_foot=Markup(foot())))
    urls.append("/contact.html")


def _page_terms(urls):
    """/terms - text in site_src/templates/terms.html (templated 2026-09-25)."""
    write("terms.html", render(
        "terms.html",
        page_head=Markup(head("شروط الاستخدام — " + SITE_NAME,
                              "شروط استخدام موقع يلا سكور: حدود المسؤولية وقواعد استخدام المحتوى.",
                              SITE_BASE + "/terms.html")),
        site_name=SITE_NAME, page_foot=Markup(foot())))
    urls.append("/terms.html")


def _page_editorial(urls):
    """/editorial (the E-E-A-T editorial policy, incl. the AI disclosure) - text in
    site_src/templates/editorial.html (templated 2026-09-25)."""
    write("editorial.html", render(
        "editorial.html",
        page_head=Markup(head("السياسة التحريرية — " + SITE_NAME,
                              "منهج يلا سكور التحريري: التحقق من مصادر متعددة، صياغة أصلية، صور مرخصة، وتصحيح علني للأخطاء.",
                              SITE_BASE + "/editorial.html")),
        editor_name=EDITOR_NAME, page_foot=Markup(foot())))
    urls.append("/editorial.html")


def _page_news_archive(articles, urls):
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


def _page_fb_html_internal_helper_ready_to_paste_f(a=_UNSET, articles=_UNSET):
    if a is _UNSET:
        del a
    if articles is _UNSET:
        del articles
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
    _l = locals()
    return {k: _l[k] for k in ('a',) if k in _l}


def _page_headlines_page(h=_UNSET, headlines=_UNSET, img=_UNSET, urls=_UNSET, when=_UNSET):
    if h is _UNSET:
        del h
    if headlines is _UNSET:
        del headlines
    if img is _UNSET:
        del img
    if urls is _UNSET:
        del urls
    if when is _UNSET:
        del when
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


def _page_reels(reels, urls):
    """/reels - vertical shorts. Template: site_src/templates/reels.html."""
    page_head = Markup(head(f"ريلز كرة القدم — {SITE_NAME}",
                            "ريلز كرة القدم — مقاطع قصيرة: مهارات وأهداف ولقطات ممتعة بالفيديو.",
                            SITE_BASE + "/reels.html", active="reels"))
    slides = [Markup(reel_slide(r, first=(i == 0))) for i, r in enumerate(reels or [])]
    html_ = render("reels.html", page_head=page_head, slides=slides,
                   video_js=Markup(VIDEO_JS), reels_js=Markup(REELS_FEED_JS),
                   page_foot=Markup(foot()))
    if SHOW_REELS:
        write("reels.html", html_)
        urls.append("/reels.html")


def _page_videos(videos, urls):
    """/videos, grouped by competition (item.cat: "wc" | "epl" | "laliga" | absent
    -> "misc"); empty groups are skipped. Template: site_src/templates/videos.html."""
    page_head = Markup(head(f"فيديوهات كرة القدم — {SITE_NAME}",
                            "فيديوهات كأس العالم 2026 والدوري الإنجليزي والدوري الإسباني على يلا سكور.",
                            SITE_BASE + "/videos.html", active="videos"))
    groups = []
    if videos:
        by_cat = {}
        for v in videos:
            by_cat.setdefault((v.get("cat") or "misc"), []).append(v)
        for key, label in VIDEO_CATS:
            if by_cat.get(key):
                # the label was always printed raw (it is our own constant)
                groups.append((Markup(label), [Markup(video_facade(v)) for v in by_cat[key]]))
    html_ = render("videos.html", page_head=page_head, has_videos=bool(videos),
                   groups=groups, video_js=Markup(VIDEO_JS), page_foot=Markup(foot()))
    if SHOW_VIDEOS:
        write("videos.html", html_)
        urls.append("/videos.html")


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


# (slice 4b's page functions - they use the ONE _UNSET/_bound defined above
# the slice-4 functions. A second definition used to sit here: the 25 earlier
# functions then bound their defaults to the first _UNSET but compared against
# the second, so an unset variable kept the sentinel instead of being deleted.
# Removed 2026-09-26; tests/test_build_split.py keeps it at one.)


def _page_strength_model_predictions_accuracy_play(_details_raw=_UNSET, _res_arch=_UNSET, assists=_UNSET, e=_UNSET, fixtures=_UNSET, matches=_UNSET, p=_UNSET, scorers=_UNSET, standings=_UNSET):
    if _details_raw is _UNSET:
        del _details_raw
    if _res_arch is _UNSET:
        del _res_arch
    if assists is _UNSET:
        del assists
    if e is _UNSET:
        del e
    if fixtures is _UNSET:
        del fixtures
    if matches is _UNSET:
        del matches
    if p is _UNSET:
        del p
    if scorers is _UNSET:
        del scorers
    if standings is _UNSET:
        del standings
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

    _shell.TICKER_HTML = make_ticker(matches)

    # kickoff epochs for LIVE_JS's kickoff-aware polling (see KO_SCRIPT)
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
        _shell.KO_SCRIPT = (f"<script>window.__koTs={json.dumps(sorted(_kos))}</script>"
                     if _kos else "")
    except Exception:
        _shell.KO_SCRIPT = ""
    _l = locals()
    return {k: _l[k] for k in ('ZoneInfo', '_acc', '_bycomp', '_cal', '_dt', '_lparams', '_mid', '_pins', '_plog', '_preds', '_sins', '_squad', '_tstats', '_upcoming', 'm', 'p', 'r', 'reels') if k in _l}


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


def _page_shared_per_league_data_stats_machinery(_bycomp=_UNSET, assists=_UNSET, fixtures=_UNSET, scorers=_UNSET, standings=_UNSET):
    if _bycomp is _UNSET:
        del _bycomp
    if assists is _UNSET:
        del assists
    if fixtures is _UNSET:
        del fixtures
    if scorers is _UNSET:
        del scorers
    if standings is _UNSET:
        del standings
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
    _l = locals()
    return {k: _l[k] for k in ('as_by_comp', 'as_ok', 'forms', 'fx_by_comp', 'league_stats_parts', 'league_stats_sec', 'sc_by_comp', 'sc_ok', 'st_by_comp') if k in _l}


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

    # تحليلات: strength model + predictions + accuracy + player insights -> _page_strength_model_predictions_accuracy_play() (moved out of build(), slice 4)
    _r = _page_strength_model_predictions_accuracy_play(**_bound(locals(), ('_details_raw', '_res_arch', 'assists', 'e', 'fixtures', 'matches', 'p', 'scorers', 'standings')))
    if 'ZoneInfo' in _r:
        ZoneInfo = _r['ZoneInfo']
    if '_acc' in _r:
        _acc = _r['_acc']
    if '_bycomp' in _r:
        _bycomp = _r['_bycomp']
    if '_cal' in _r:
        _cal = _r['_cal']
    if '_dt' in _r:
        _dt = _r['_dt']
    if '_lparams' in _r:
        _lparams = _r['_lparams']
    if '_mid' in _r:
        _mid = _r['_mid']
    if '_pins' in _r:
        _pins = _r['_pins']
    if '_plog' in _r:
        _plog = _r['_plog']
    if '_preds' in _r:
        _preds = _r['_preds']
    if '_sins' in _r:
        _sins = _r['_sins']
    if '_squad' in _r:
        _squad = _r['_squad']
    if '_tstats' in _r:
        _tstats = _r['_tstats']
    if '_upcoming' in _r:
        _upcoming = _r['_upcoming']
    if 'm' in _r:
        m = _r['m']
    if 'p' in _r:
        p = _r['p']
    if 'r' in _r:
        r = _r['r']
    if 'reels' in _r:
        reels = _r['reels']

    # assets: css + logo -> _page_assets_css_logo() (moved out of build(), slice 4)
    _r = _page_assets_css_logo()
    if 'f' in _r:
        f = _r['f']
    if 'urls' in _r:
        urls = _r['urls']

    # home -> _page_home() (moved out of build(), slice 4)
    _r = _page_home(_acc, _cal, _preds, _upcoming, articles, fixtures, headlines, matches, reels,
                    standings, videos)
    if 'h' in _r:
        h = _r['h']
    if 'm' in _r:
        m = _r['m']
    if 'v' in _r:
        v = _r['v']

    # article pages -> _page_article_pages() (moved out of build(), slice 4)
    _r = _page_article_pages(articles, articles_all, matches, urls)
    if '_clubs' in _r:
        _clubs = _r['_clubs']
    if '_faq' in _r:
        _faq = _r['_faq']
    if '_match_arts' in _r:
        _match_arts = _r['_match_arts']
    if '_moved' in _r:
        _moved = _r['_moved']
    if '_t' in _r:
        _t = _r['_t']
    if 'a' in _r:
        a = _r['a']
    if 'img' in _r:
        img = _r['img']
    if 'p' in _r:
        p = _r['p']

    # shared per-league data + stats machinery (matches page + /stats) -> _page_shared_per_league_data_stats_machinery() (moved out of build(), slice 4)
    _r = _page_shared_per_league_data_stats_machinery(**_bound(locals(), ('_bycomp', 'assists', 'fixtures', 'scorers', 'standings')))
    if 'as_by_comp' in _r:
        as_by_comp = _r['as_by_comp']
    if 'as_ok' in _r:
        as_ok = _r['as_ok']
    if 'forms' in _r:
        forms = _r['forms']
    if 'fx_by_comp' in _r:
        fx_by_comp = _r['fx_by_comp']
    if 'league_stats_parts' in _r:
        league_stats_parts = _r['league_stats_parts']
    if 'league_stats_sec' in _r:
        league_stats_sec = _r['league_stats_sec']
    if 'sc_by_comp' in _r:
        sc_by_comp = _r['sc_by_comp']
    if 'sc_ok' in _r:
        sc_ok = _r['sc_ok']
    if 'st_by_comp' in _r:
        st_by_comp = _r['st_by_comp']

    # matches page (per-day navigator, like the live app) -> _page_matches_page() (moved out of build(), slice 4)
    _r = _page_matches_page(_plog, _preds, articles, fixtures, forms, fx_by_comp, ge_idx,
                            league_stats_parts, matches, st_by_comp, standings)
    if 'a' in _r:
        a = _r['a']
    if 'comp' in _r:
        comp = _r['comp']
    if 'comp_order' in _r:
        comp_order = _r['comp_order']
    if 'i' in _r:
        i = _r['i']
    if 'img' in _r:
        img = _r['img']
    if 'k' in _r:
        k = _r['k']
    if 'm' in _r:
        m = _r['m']
    if 'st' in _r:
        st = _r['st']

    # per-match pages (/m/<id>.html) -> _page_per_match_pages() (moved out of build(), slice 4)
    _r = _page_per_match_pages(_bycomp, _cal, _lparams, _match_arts, _plog, _preds, _squad,
                               _tstats, articles, fixtures, forms, ge_idx, matches, md_idx,
                               st_by_comp, urls)
    if '_h' in _r:
        _h = _r['_h']
    if '_html' in _r:
        _html = _r['_html']
    if '_slug' in _r:
        _slug = _r['_slug']
    if 'a' in _r:
        a = _r['a']
    if 'comp' in _r:
        comp = _r['comp']
    if 'desc' in _r:
        desc = _r['desc']
    if 'img' in _r:
        img = _r['img']
    if 'm' in _r:
        m = _r['m']
    if 'm_all' in _r:
        m_all = _r['m_all']
    if 'st' in _r:
        st = _r['st']
    if 'title' in _r:
        title = _r['title']
    if 'v' in _r:
        v = _r['v']
    if 'when' in _r:
        when = _r['when']

    # per-league standings + top-scorers pages -> _page_per_league_standings_top_scorers_pages() (moved out of build(), slice 4)
    _r = _page_per_league_standings_top_scorers_pages(_bycomp, _preds, as_by_comp, as_ok, forms,
                                                      matches, sc_by_comp, sc_ok, st_by_comp, urls)
    if '_comps_with_table' in _r:
        _comps_with_table = _r['_comps_with_table']
    if 'comp' in _r:
        comp = _r['comp']
    if 'label' in _r:
        label = _r['label']
    if 'm' in _r:
        m = _r['m']
    if 'season' in _r:
        season = _r['season']
    if 'slug' in _r:
        slug = _r['slug']
    if 'st' in _r:
        st = _r['st']
    if 'up_next' in _r:
        up_next = _r['up_next']

    # per-league season fixtures (/fixtures/<slug>.html) -> _page_per_league_season_fixtures() (moved out of build(), slice 4)
    _r = _page_per_league_season_fixtures(fx_by_comp, season, st_by_comp, urls)
    if 'comp' in _r:
        comp = _r['comp']
    if 'label' in _r:
        label = _r['label']
    if 'slug' in _r:
        slug = _r['slug']

    # تحليلات: /analysis hub + /analysis/<league> -> _page_analysis_hub_analysis_league() (moved out of build(), slice 4)
    _page_analysis_hub_analysis_league(_acc, _comps_with_table, _lparams, _pins, _plog, _preds,
                                       _sins, _tstats, _upcoming, forms, matches, urls)

    # per-club pages (/team/<slug>) -> _page_per_club_pages() (moved out of build(), slice 4)
    _r = _page_per_club_pages(_plog, _preds, articles, forms, m_all, season, st_by_comp, urls)
    if '_img' in _r:
        _img = _r['_img']
    if 'a' in _r:
        a = _r['a']
    if 'img' in _r:
        img = _r['img']
    if 'r' in _r:
        r = _r['r']

    # stats dashboard (/stats.html) -> _page_stats_dashboard() (moved out of build(), slice 4)
    _page_stats_dashboard(comp_order, fixtures, forms, league_stats_sec, matches, sc_by_comp,
                          sc_ok, st_by_comp, urls)

    # 404 page (served by Cloudflare for any missing asset) -> _page_404_page() (moved out of build(), slice 4)
    _page_404()

    # privacy policy (required for AdSense) -> _page_privacy_policy() (moved out of build(), slice 4)
    _page_privacy_policy(urls)

    # about page (من نحن) — helps AdSense/E-E-A-T review -> _page_about_page_helps_adsense_e_e_a_t_review() (moved out of build(), slice 4)
    _page_about(urls)

    # contact page (اتصل بنا) -> _page_contact_page() (moved out of build(), slice 4)
    _page_contact(urls)

    # terms of use (شروط الاستخدام) -> _page_terms_of_use() (moved out of build(), slice 4)
    _page_terms(urls)

    # editorial policy (السياسة التحريرية) — E-E-A-T signal -> _page_editorial_policy_e_e_a_t_signal() (moved out of build(), slice 4)
    _page_editorial(urls)

    # news archive pages -> _page_news_archive_pages() (moved out of build(), slice 4)
    _page_news_archive(articles, urls)

    # fb.html — INTERNAL helper: ready-to-paste Facebook posts -> _page_fb_html_internal_helper_ready_to_paste_f() (moved out of build(), slice 4)
    _r = _page_fb_html_internal_helper_ready_to_paste_f(**_bound(locals(), ('a', 'articles')))
    if 'a' in _r:
        a = _r['a']
    # deliberately NOT appended to urls (sitemap) and linked from nowhere

    # headlines page (full aggregated list; gated by SHOW_HEADLINES) -> _page_headlines_page() (moved out of build(), slice 4)
    _page_headlines_page(**_bound(locals(), ('h', 'headlines', 'img', 'urls', 'when')))

    # reels page (vertical shorts; data/reels.json + reels_auto.json) -> _page_reels_page() (moved out of build(), slice 4)
    _page_reels(reels, urls)

    # videos page: grouped by competition (empty sections auto-hide) -> _page_videos_page_grouped_by_competition() (moved out of build(), slice 4)
    _page_videos(videos, urls)

    # robots + sitemap + ads.txt -> _page_robots_sitemap_ads_txt() (moved out of build(), slice 4)
    _page_robots_sitemap_ads_txt(**_bound(locals(), ('_img', 'a', 'articles', 'urls')))

    # passthrough root files (Google Search Console verification, etc.) -> _page_passthrough_root_files() (moved out of build(), slice 4)
    _r = _page_passthrough_root_files()
    if 'fn' in _r:
        fn = _r['fn']
    if 'src' in _r:
        src = _r['src']

    # _redirects: the match pieces that moved into their match page -> _page_redirects_the_match_pieces_that_moved_in() (moved out of build(), slice 4)
    _page_redirects_the_match_pieces_that_moved_in(**_bound(locals(), ('_moved',)))

    # mirrored crests (downloaded by local_crest during rendering) -> _page_mirrored_crests() (moved out of build(), slice 4)
    _r = _page_mirrored_crests(**_bound(locals(), ('fn', 'src')))
    if 'fn' in _r:
        fn = _r['fn']
    if 'n' in _r:
        n = _r['n']
    if 'src' in _r:
        src = _r['src']

    # uploaded media (article images added via the admin page) -> _page_uploaded_media() (moved out of build(), slice 4)
    _page_uploaded_media(**_bound(locals(), ('_preds', 'articles', 'fn', 'matches', 'n', 'src')))








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



def comp_icon(name):
    url = COMP_LOGO.get(name)
    if url:
        return f'<img class="lg-logo" src="{esc(local_crest(url))}" alt="" loading="lazy">'
    return f'<span class="lg-ico">{comp_emoji(name)}</span>'


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















# «الخسارة» is feminine in Arabic: الخسارة الثانية, not الخسارة الثاني
_ORD_AR_F = {n: (w + "ة") for n, w in _ORD_AR.items() if n <= 10}

def _ord_ar(n, fem=False):
    """Arabic ordinal, or the bare number for a place past the twentieth (the
    36-club Champions League league phase) - never «المركز رقم 24»."""
    n = int(n or 0)
    return (_ORD_AR_F if fem else _ORD_AR).get(n, str(n))












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






# ---------------------------------------------------------------- styles
CSS = _src("style.css")

# static face-circle tiles: name tooltip via title/alt.
LEGENDS_HTML = "".join(
    f'<span class="lg-ava"><img src="{u}" alt="{n}" title="{n}" loading="lazy"'
    f' style="object-position:{p};transform:scale({z});transform-origin:{p}"></span>'
    for n, u, p, z in LEGENDS)

LEGENDS_CSS = _src("legends.css")

# progressive-enhancement: show one day at a time with prev/next (like the live app).
# Without JS, every day-section stays visible (crawlable).
ROUNDS_JS = _src("snippets/rounds_js.html")

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

MATCHES_JS = _src("snippets/matches_js.html")


FBCOPY_JS = _src("snippets/fbcopy_js.html")

SHELF_JS = _src("snippets/shelf_js.html")

REELS_FEED_JS = _src("snippets/reels_feed_js.html")

VIDEO_JS = _src("snippets/video_js.html")

if __name__ == "__main__":
    build()
