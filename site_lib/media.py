"""Video categories and embed platform labels.

Moved verbatim out of build_site.py (slice 2, 2026-09-25) - the source
text and its comments are exactly what they were there. Edit here;
build_site imports these back under the same names."""

# fixed section order on /videos.html; a section with no videos is not rendered
VIDEO_CATS = [
    ("wc",     "🏆 فيديوهات كأس العالم 2026"),
    ("epl",    "🦁 فيديوهات الدوري الإنجليزي 2026-2027"),
    ("laliga", "🇪🇸 فيديوهات الدوري الإسباني 2026-2027"),
    ("misc",   "⚽ متنوعات كروية"),
]

# ---------------------------------------------------------------- build
# ---------------------------------------------------------------- تحليلات (rendering)
# Official-post embeds under an article (user ask 2026-09-13: «النقطة 1» -
# the club's own X / Instagram / Facebook post, the one legal way to show a
# professional photo of the event without a licence: the platform serves it).
# Rendered as a CARD that loads the platform's script only when the reader
# clicks - nothing third-party on page load (speed, AdSense, privacy). Without
# JS the card is a plain link to the post.
EMBED_LABEL = {"x": "X (تويتر)", "instagram": "إنستغرام", "facebook": "فيسبوك"}
