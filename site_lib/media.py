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


# ---------------------------------------------------------------- highlights
# «أهداف المباراة» on a match row (user, 2026-11-02: «احنا ممكن نستغنى عن التاب
# ... فى الجزء بتاع المباريات ونحط زرار او لينك يعرض اهداف المباراة لو المباراة
# دى ليها اهداف عندنا»). data/highlights.json is written by highlights.py
# (beIN SPORTS / ON Sport YouTube uploads, each tied to one of our matches).
_HL_IDX = None


def highlight_links():
    """{match_id (str): (youtube url, channel name)} - the summary («ملخص»)
    over a goals-only upload of the same match. Read once per build."""
    global _HL_IDX
    if _HL_IDX is None:
        import json
        import os
        from site_lib.config import DATA
        _HL_IDX, rank = {}, {}
        try:
            with open(os.path.join(DATA, "highlights.json"), encoding="utf-8") as f:
                rows = json.load(f).get("results") or []
        except (OSError, ValueError):
            rows = []
        for v in rows:
            mid, vid = str(v.get("match_id") or ""), v.get("vid")
            if not mid or not vid:
                continue
            r = 1 if "ملخص" in (v.get("title") or "") else 0
            if mid not in _HL_IDX or r > rank[mid]:
                _HL_IDX[mid] = (f"https://www.youtube.com/watch?v={vid}", v.get("channel") or "")
                rank[mid] = r
    return _HL_IDX
