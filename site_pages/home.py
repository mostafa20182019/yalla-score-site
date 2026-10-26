"""The home page (/). Its standing rules live in site_src/templates/home.html.

Moved verbatim out of build_site.py (2026-09-26, tools/move_names.py):
source and comments exactly as they were there. Edit here; build_site
imports these back under the same names."""
import json
from site_lib.articles import pinned_first
from site_lib.cards import follow_pills
from site_lib.config import FB_PAGE_URL, SITE_BASE, SITE_DESC, SITE_NAME, SITE_TAGLINE, TG_CHANNEL_URL
from site_lib.crests import local_crest
from site_lib.names import _is_ticker_team, ar_team, fav_club_names
from site_lib.render import Markup, render
from site_lib.shell import adsense_slot, foot, head, write
from site_lib.text import jsonld, strip_tags
from site_lib.today_strip import match_centre
from site_lib.urls import match_url


def home_page(articles, fixtures, ge_idx, matches, standings):
    """/ - the match centre and nothing else (user, 2026-10-26: phones first,
    then the desktop «دى هتكون الرئيسية، والاخبار اللى تحت تظهر فى تاب اسمها
    اخبار وشيل ترتيب الدوريات»): leagues | every day's matches with the
    /matches filters | latest news, under the live card of the featured clubs.
    The news, analyses, clubs block and its league tables live in their tabs
    (/news, /insights, /leagues). Markup: site_src/templates/home.html."""
    articles = pinned_first(articles)   # HOME_PIN (site_lib/config.py)
    feat = articles[0] if articles else None    # og:image source
    page_head = head(f"{SITE_NAME} — {SITE_TAGLINE}", SITE_DESC, SITE_BASE + "/",
                     image=(feat and feat.get("image_url")) or None, active="home")
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
    # the follow pills ride on the match list's heading (user, 2026-10-22:
    # at the top of the page)
    _centre = match_centre(standings, matches, articles, ge_idx, pills=follow_pills())
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
        match_centre=Markup(_centre), fav_script=Markup(fav_script), page_foot=Markup(foot())))
