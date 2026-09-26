"""Site settings: name, domain, contact, editor, ad ids, feature switches, the
paths of data/ dist/ site_src/ and the build's reference date.

IMPORTANT: SITE_BASE is the public URL every canonical / Open Graph /
sitemap link is built from.

Moved verbatim out of build_site.py (2026-09-26, tools/move_names.py):
source and comments exactly as they were there. Edit here; build_site
imports these back under the same names."""
import datetime
import io
import json
import os


# ---------------------------------------------------------------- config
SITE_BASE = "https://yallascore.site"  # custom domain on the Cloudflare Worker (since 2026-08-03)
SITE_NAME = "يلا سكور"
SITE_TAGLINE = "أخبار ونتائج كرة القدم"
SITE_DESC = "يلا سكور — أخبار كرة القدم ونتائج المباريات ومواعيد البطولات بالعربية."
LOCALE = "ar_AR"
BUILD_DATE = os.environ.get("BUILD_DATE", "")  # pass a date; else today isn't used in content
# --- Google AdSense (fill these AFTER AdSense approves your site, then rebuild) ---
# 1) ADSENSE_CLIENT: your publisher id, e.g. "ca-pub-1234567890123456"
# 2) ADSENSE_SLOT:   the ad-unit slot id from AdSense, e.g. "1234567890"
# While either is empty, a tidy "مساحة إعلانية" placeholder is shown instead.
# NOTE: AdSense usually requires your OWN domain (a *.workers.dev subdomain is
# typically not approved) + a Privacy Policy page.
ADSENSE_CLIENT = "ca-pub-3080285229612776"
ADSENSE_SLOT = ""
ADSENSE_SLOT_TOP = ""   # mobile top-banner unit id (leave empty for placeholder)
# Optional contact email shown on the Privacy Policy page (leave "" to omit).
CONTACT_EMAIL = "yallascore.eg@gmail.com"
# Facebook page «يلا سكور» — numeric id URL always resolves; swap for the
# vanity URL (facebook.com/<username>) once the page has one.
FB_PAGE_URL = "https://www.facebook.com/104238901487012"
# the owned Telegram channel (created by the user 2026-09-22; tg_post.py
# posts every new article to it after deploy, same machinery as Facebook)
TG_CHANNEL_URL = "https://t.me/yallascore"
# Editorial identity shown on /editors.html and in every article byline.
EDITOR_NAME = "مصطفى عبدالسلام"
EDITOR_ROLE = "مدير التحرير"
EDITOR_EMAIL = CONTACT_EMAIL
# The bylines Google reads as a faceless publisher. An article carrying one of
# these is signed by the named editor instead (2026-09-15): a person who can be
# looked up, mailed and held responsible is the E-E-A-T signal a generic «فريق
# التحرير» never gives, and it was one of the two decisions left open after the
# content rejection. Rendering-level on purpose — the 466 stored rows are not
# rewritten, so this is one constant away from being undone.
GENERIC_BYLINES = (SITE_NAME, "فريق التحرير", "فريق يلا سكور", "")
# Cloudflare Web Analytics (cookie-less page views / referrers / top pages).
# Paste the 32-char token from Cloudflare -> Analytics & Logs -> Web Analytics
# -> Add a site (manual install). Empty = no beacon in the pages.
CF_ANALYTICS_TOKEN = ""
# Feature switches. Flip to True to bring a section back (nav tab, footer link,
# home teaser, its page, and sitemap entry all follow this flag automatically).
SHOW_VIDEOS = False
SHOW_REELS = False
# aggregated press headlines OFF for the AdSense review (2026-08-30, user
# decision): copied titles + outbound links are the site's weakest
# originality signal. The home slot shows a deeper grid of OUR articles
# instead. fetch_data.py still refreshes headlines.json (editorial tasks
# read the RSS separately) — this flag only gates the DISPLAY.
SHOW_HEADLINES = False
# stats live inside the /matches league view now (2026-08-19, user request);
# the standalone page still builds (old links don't 404) but is unlinked,
# out of the sitemap, and noindexed. Flip to True to bring it back.
SHOW_STATS_PAGE = False
# Generic fallback thumbnails (our own SVGs in media/, no licensing worries)
# for headline cards whose source page offers no og:image.
PLACEHOLDER_IMGS = ["/media/ph-pitch.svg", "/media/ph-ball.svg"]
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # the repo root (this file is site_lib/config.py)
DATA = os.path.join(HERE, "data")
DIST = os.path.join(HERE, "dist")
# The page CSS and the <script>/<div> snippets live in site_src/ as real
# files (2026-09-25, slice 1 of the build_site split) - edit them there,
# not here. Read once at import; universal newlines, so a Windows checkout
# (CRLF) builds byte-for-byte the same site as the Linux runner.
SITE_SRC = os.path.join(HERE, "site_src")
def _src(rel):
    with io.open(os.path.join(SITE_SRC, rel), encoding="utf-8") as f:
        return f.read()


def load(name):
    """Load a SQLcl `set sqlformat json` export -> list of row dicts (tolerant)."""
    p = os.path.join(DATA, name)
    if not os.path.exists(p):
        return []
    try:
        with open(p, encoding="utf-8") as f:
            doc = json.load(f)
        return doc["results"][0]["items"]
    except Exception as e:
        print("  ! could not parse %s (%s) - skipping" % (name, e))
        return []


REF_TODAY = datetime.date.today().isoformat()  # machine clock (the sandbox is set to Jul 2026)
# Articles shorter than this are UNLISTED: the page stays online at the same
# URL, but it is noindexed, left out of the sitemap / news sitemap / RSS, and
# dropped from every listing on the site (home blocks, /news archives, club
# pages, match pages, related-article blocks).
#
# Raised 200 -> 300 on 2026-09-06 (user decision). He asked whether to DELETE
# the old archive instead; the numbers said no: 60 of these articles have a
# live Facebook post pointing at them and 35 are linked from another article,
# so deleting breaks our main traffic channel — while buying nothing back,
# since Search Console had 499/500 of them as "discovered, not indexed" anyway.
# Unlisting shows Google and a browsing reviewer exactly what deletion would,
# keeps the URL working for anyone arriving from an old post, and is reversible.
# 294 of 355 articles are under the new bar; upgrade-articles.yml rewrites 5/day
# to the 500-700-word standard and each one crosses back on its own.
ARTICLE_MIN_WORDS = 300
NEWLINE = chr(10)
