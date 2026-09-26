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
# crests, ticker, articles, predictions, cards, tables, reads, loaders, snippets: moved to site_lib/ by tools/move_names.py (2026-09-26) -
# edit them there. Same names, same behaviour.
from site_lib.crests import (  # noqa: E402,F401
    CRESTS_CACHE, _CREST_MAP, _CREST_FAILS, _CREST_FAIL_LIMIT, local_crest, comp_icon)
from site_lib.ticker import (  # noqa: E402,F401
    _tk_date, make_ticker)
from site_lib.articles import (  # noqa: E402,F401
    byline, match_data_sources, resolve_missing_media, is_thin, article_url, _MOVED_LINKS,
    _A_HREF, fix_moved_links, embed_platform, EMBED_JS, embeds_block, match_article_block,
    article_moved_stub, _ART_CLUBS, article_clubs, _KW_STOP, _art_kw, related_articles,
    _rfc822)
from site_lib.predictions import (  # noqa: E402,F401
    AN_DISCLAIMER, PRED_POP, pred_pop, conf_chip, pred_row, why_block,
    pred_block, power_table, timing_bars, PRED_FILTER_JS, _rec_day_label)
from site_lib.cards import (  # noqa: E402,F401
    headline_card, news_card, _art_meta, club_crest, clubs_strip, CLUBS_JS,
    _NF_ICON_TREND, _NF_ICON_EUR, _NF_ICON_EGY, _nf_icon_eur, news_filter_bar, NEWS_FILTER_JS,
    fmb_block, pred_home_block)
from site_lib.tables import (  # noqa: E402,F401
    standings_table, fixture_mini, league_rounds_panel, _scorer_face, clubs_panel, scorers_list,
    match_row, match_details_html)
from site_lib.reads import (  # noqa: E402,F401
    _ORD_AR_F, _ord_ar, _streak_ar, table_after, _form_phrase, pre_match_read,
    post_match_read)
from site_lib.loaders import (  # noqa: E402,F401
    articles_current, goals_index, build_info)
from site_lib.snippets import (  # noqa: E402,F401
    CSS, LEGENDS_HTML, LEGENDS_CSS, ROUNDS_JS, FILTERS_HTML, MATCHES_JS,
    FBCOPY_JS, SHELF_JS, REELS_FEED_JS, VIDEO_JS)
# The pages: one module per page type in site_pages/ (slice 8, 2026-09-26),
# with real names and explicit inputs/outputs since slice 9.
from site_pages.prep import prepare_model, prepare_league_data  # noqa: E402
from site_pages.static import (  # noqa: E402
    not_found_page, privacy_page, about_page, contact_page, terms_page, editorial_page,
    reels_page, videos_page)
from site_pages.articles import (  # noqa: E402
    article_pages, news_archive_pages, fb_helper_page, headlines_page)
from site_pages.home import home_page  # noqa: E402
from site_pages.matches import matches_page, match_pages  # noqa: E402
from site_pages.leagues import league_pages, fixtures_pages, stats_page  # noqa: E402
from site_pages.clubs import club_pages  # noqa: E402
from site_pages.predictions import (  # noqa: E402,F401
    prediction_history_page, analysis_pages, analysis_section)
from site_pages.files import (  # noqa: E402
    robots_sitemap_ads, copy_root_files, write_redirects, copy_crests,
    copy_media_and_build_info, write_assets)
import site_lib.shell as _shell   # build() sets TICKER_HTML / KO_SCRIPT / CSS_VER on it


# (the top-transfers widget was removed 2026-09-01 by user decision — the
# FotMob-style news blocks took its home slots; fetch_data no longer pulls
# transfers.json. Restore from git history if it ever comes back.)


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

    # تحليلات: strength model + predictions + accuracy + player insights; also
    # sets the ticker and the kickoff times on site_lib.shell
    model = prepare_model(_details_raw, _res_arch, assists, fixtures, matches, scorers, standings)
    _acc, _bycomp, _cal, _lparams = model["acc"], model["bycomp"], model["cal"], model["lparams"]
    _pins, _plog, _preds, _sins = model["pins"], model["plog"], model["preds"], model["sins"]
    _squad, _tstats, _upcoming, reels = model["squad"], model["tstats"], model["upcoming"], model["reels"]

    urls = write_assets()          # css + logo; `urls` collects the sitemap from here on

    home_page(_acc, _cal, _preds, _upcoming, articles, fixtures, headlines, matches, reels,
              standings, videos)
    _match_arts, _moved = article_pages(articles, articles_all, matches, urls)

    # shared per-league data (matches page, league pages, /stats)
    league = prepare_league_data(_bycomp, assists, fixtures, scorers, standings)
    st_by_comp, sc_by_comp, sc_ok = league["st_by_comp"], league["sc_by_comp"], league["sc_ok"]
    as_by_comp, as_ok, forms = league["as_by_comp"], league["as_ok"], league["forms"]
    fx_by_comp = league["fx_by_comp"]

    comp_order = matches_page(_plog, _preds, articles, fixtures, forms, fx_by_comp, ge_idx,
                              league["league_stats_parts"], matches, st_by_comp, standings)
    m_all = match_pages(_bycomp, _cal, _lparams, _match_arts, _plog, _preds, _squad, _tstats,
                        articles, fixtures, forms, ge_idx, matches, md_idx, st_by_comp, urls)
    _comps_with_table, season = league_pages(_bycomp, _preds, as_by_comp, as_ok, forms, matches,
                                             sc_by_comp, sc_ok, st_by_comp, urls)
    fixtures_pages(fx_by_comp, season, st_by_comp, urls)
    analysis_section(_acc, _comps_with_table, _lparams, _pins, _plog, _preds, _sins, _tstats,
                     _upcoming, forms, matches, urls)
    club_pages(_plog, _preds, articles, forms, m_all, season, st_by_comp, urls)
    stats_page(comp_order, fixtures, forms, league["league_stats_sec"], matches, sc_by_comp,
               sc_ok, st_by_comp, urls)

    not_found_page()               # served by Cloudflare for any missing asset
    privacy_page(urls)             # required for AdSense
    about_page(urls)               # من نحن - AdSense / E-E-A-T review
    contact_page(urls)
    terms_page(urls)
    editorial_page(urls)           # السياسة التحريرية - E-E-A-T signal
    news_archive_pages(articles, urls)
    fb_helper_page(articles)       # INTERNAL: not in the sitemap, linked from nowhere
    headlines_page(headlines, urls)        # gated by SHOW_HEADLINES
    reels_page(reels, urls)
    videos_page(videos, urls)

    # files that are not pages - robots/sitemap last among the writers of
    # `urls`, so the sitemap lists every page above
    robots_sitemap_ads(articles, urls)
    copy_root_files()              # Search Console verification etc.
    write_redirects(_moved)        # match pieces that moved into their match page
    copy_crests()                  # downloaded by local_crest during rendering
    copy_media_and_build_info(_preds, articles, matches)


if __name__ == "__main__":
    build()
