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
# glue, prep, static, articles, home, matches, leagues, clubs, predictions, files: moved to site_pages/ by tools/move_names.py (2026-09-26) -
# edit them there. Same names, same behaviour.
from site_pages.glue import (  # noqa: E402,F401
    _UNSET, _bound)
from site_pages.prep import (  # noqa: E402,F401
    _page_strength_model_predictions_accuracy_play, _page_shared_per_league_data_stats_machinery)
from site_pages.static import (  # noqa: E402,F401
    _page_404, _page_privacy_policy, _page_about, _page_contact, _page_terms, _page_editorial,
    _page_reels, _page_videos)
from site_pages.articles import (  # noqa: E402,F401
    _page_article_pages, _page_news_archive, _page_fb_html_internal_helper_ready_to_paste_f, _page_headlines_page)
from site_pages.home import (  # noqa: E402,F401
    _page_home)
from site_pages.matches import (  # noqa: E402,F401
    _page_matches_page, _page_per_match_pages)
from site_pages.leagues import (  # noqa: E402,F401
    _page_per_league_standings_top_scorers_pages, _page_per_league_season_fixtures, _page_stats_dashboard)
from site_pages.clubs import (  # noqa: E402,F401
    _page_per_club_pages)
from site_pages.predictions import (  # noqa: E402,F401
    prediction_history_page, analysis_pages, _page_analysis_hub_analysis_league)
from site_pages.files import (  # noqa: E402,F401
    _page_robots_sitemap_ads_txt, _page_passthrough_root_files, _page_redirects_the_match_pieces_that_moved_in, _page_mirrored_crests, _page_uploaded_media, _page_assets_css_logo)
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


if __name__ == "__main__":
    build()
