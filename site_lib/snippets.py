"""The page CSS and the <script>/<div> snippets read from site_src/.

Moved verbatim out of build_site.py (2026-09-26, tools/move_names.py):
source and comments exactly as they were there. Edit here; build_site
imports these back under the same names."""
from site_lib.clubs import LEGENDS
from site_lib.config import _src


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
