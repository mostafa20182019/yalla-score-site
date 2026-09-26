"""The home page (/). Its standing rules live in site_src/templates/home.html.

Moved verbatim out of build_site.py (2026-09-26, tools/move_names.py):
source and comments exactly as they were there. Edit here; build_site
imports these back under the same names."""
import datetime
import json
from site_lib.cards import clubs_strip, fmb_block, headline_card, news_filter_bar, pred_home_block
from site_lib.config import FB_PAGE_URL, REF_TODAY, SHOW_HEADLINES, SHOW_REELS, SHOW_VIDEOS, SITE_BASE, SITE_DESC, SITE_NAME, SITE_TAGLINE, TG_CHANNEL_URL
from site_lib.crests import local_crest
from site_lib.names import _egy_article, _eur_article, _is_ticker_team, ar_team, fav_club_names
from site_lib.render import Markup, render
from site_lib.shell import adsense_slot, foot, head, thumb_url, write
from site_lib.snippets import VIDEO_JS
from site_lib.text import esc, jsonld, strip_tags
from site_lib.urls import match_url
from site_lib.widgets import video_facade


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
