"""Home-page pieces: news and headline cards, the clubs strip, the news
filter bar, the feature+list block and the predictions block.

Moved verbatim out of build_site.py (2026-09-26, tools/move_names.py):
source and comments exactly as they were there. Edit here; build_site
imports these back under the same names."""
import base64
import datetime
import hashlib
import os
from site_lib.articles import byline
from site_lib.clubs import TEAM_PAGES
from site_lib.config import FB_PAGE_URL, HERE, PLACEHOLDER_IMGS, TG_CHANNEL_URL, _src
from site_lib.crests import local_crest
from site_lib.dates import art_reltime, rel_ar
from site_lib.names import _in_scope, _is_ticker_team, _team_match
from site_lib.predictions import pred_row
from site_lib.shell import thumb_url
from site_lib.text import _pct, esc, strip_src
from site_lib.urls import article_href


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
