"""Competitions: 365scores ids, slugs, TV, logos, Arabic labels, page order.

Moved verbatim out of build_site.py (slice 2, 2026-09-25) - the source
text and its comments are exactly what they were there. Edit here;
build_site imports these back under the same names."""

# The competitions whose match data comes from 365scores; everything else
# we cover gets its table and season numbers from football-data.org (match
# details and goals come from 365scores for all of them). This mirrors
# fetch_data.S365_LEAGUES, which cannot be imported here - fetch_data imports
# THIS module.
S365_COMPETITIONS = ("Egyptian Premier League", "Turkish Super Lig",
                     "Saudi Pro League", "CAF Champions League",
                     "Africa Cup of Nations Qualification",
                     "UEFA Nations League")

# The header ticker shows ONLY these clubs' matches (user pick 2026-08-08).
# Tokens are substring-matched against football-data team names, so keep them
# unambiguous — "FC Barcelona", NOT "Barcelona" (that would also match
# "RCD Espanyol de Barcelona").
# (token, competition-or-None): 365scores leagues use native Arabic names,
# and "الأهلي" alone is AMBIGUOUS since the Saudi league joined (Saudi
# Al-Ahli is also "الأهلي") - so Arabic tokens are scoped to their league.
# URL slugs for the per-league standings/scorers landing pages
# (/standings/<slug>.html, /scorers/<slug>.html). Keys must match the
# competition names as they appear in standings.json / scorers.json.
COMP_SLUG = {
    "Egyptian Premier League": "egypt",
    "Premier League": "england",
    "Primera Division": "spain",
    "Serie A": "italy",
    "Bundesliga": "germany",
    "Ligue 1": "france",
    "Turkish Super Lig": "turkey",
    "Saudi Pro League": "saudi",
    "UEFA Champions League": "champions-league",
    "CAF Champions League": "caf-champions-league",
    "Africa Cup of Nations Qualification": "afcon-qualifiers",
    "UEFA Nations League": "nations-league",
}

# MENA broadcast rights per competition — feeds the «القنوات الناقلة» block
# on /m/ pages. ONLY entries verified for the current season belong here
# (firm site rule: never show possibly-wrong data). A missing league gets an
# honest "لم تتوفر معلومات القناة" line instead. Per-match m["channel"]
# (if a data source ever provides it) overrides this map.
COMP_TV = {
    "Egyptian Premier League": "أون سبورت (OnTime Sports)",
    "Premier League": "beIN Sports",
    "Primera Division": "beIN Sports",
    "Ligue 1": "beIN Sports",
    "UEFA Champions League": "beIN Sports",
    "CAF Champions League": "beIN Sports",     # confirmed by the user 2026-09-02
    # Serie A / Bundesliga / Turkish / Saudi: rights unverified — add when confirmed.
}

# official competition emblems (same host as the team crests already used)
COMP_LOGO = {
    "Premier League":   "https://crests.football-data.org/PL.png",
    "Primera Division": "https://crests.football-data.org/PD.png",
    "Serie A":          "https://crests.football-data.org/SA.png",
    "Bundesliga":       "https://crests.football-data.org/BL1.png",
    "Ligue 1":          "https://crests.football-data.org/FL1.png",
    "UEFA Champions League": "https://crests.football-data.org/CL.png",
    # 365scores competition emblems (self-hosted through local_crest at build)
    "CAF Champions League": "https://imagecache.365scores.com/image/upload/"
                            "f_png,w_68,h_68,c_limit,q_auto:eco,dpr_2,"
                            "d_Competitions:default1.png/v4/Competitions/624",
    "Africa Cup of Nations Qualification":
        "https://imagecache.365scores.com/image/upload/"
        "f_png,w_68,h_68,c_limit,q_auto:eco,dpr_2,"
        "d_Competitions:default1.png/v4/Competitions/588",
    "UEFA Nations League":
        "https://imagecache.365scores.com/image/upload/"
        "f_png,w_68,h_68,c_limit,q_auto:eco,dpr_2,"
        "d_Competitions:default1.png/v4/Competitions/7016",
}

# friendlier display names (data-comp keeps the raw API name for filtering)
COMP_LABEL = {
    "Egyptian Premier League": "الدوري المصري",
    "CAF Champions League": "دوري أبطال أفريقيا",
    "Premier League": "الدوري الإنجليزي",
    "Primera Division": "الدوري الإسباني",
    "Turkish Super Lig": "الدوري التركي",
    "Saudi Pro League": "الدوري السعودي",
    "Ligue 1": "الدوري الفرنسي",
    "Bundesliga": "الدوري الألماني",
    "Serie A": "الدوري الإيطالي",
    "UEFA Champions League": "دوري أبطال أوروبا",
    "Africa Cup of Nations Qualification": "تصفيات كأس أمم إفريقيا",
    "UEFA Nations League": "دوري الأمم الأوروبية",
}

# fixed sidebar order (user's pick 2026-08-13); anything unlisted goes last
COMP_ORDER = ["Egyptian Premier League", "Premier League", "Primera Division",
              "Turkish Super Lig", "Saudi Pro League", "Ligue 1",
              "Bundesliga", "Serie A", "UEFA Champions League",
              "CAF Champions League",   # after UCL (user pick 2026-09-02)
              "Africa Cup of Nations Qualification",  # user ask 2026-09-20
              "UEFA Nations League"]                  # user ask 2026-09-21

# 365scores competition ids for the leagues TICKER_TEAMS scopes by name —
# must agree with LIVE_COMPS in worker.js
# (552,78,649,7,11,17,25,35,572,624,588,7016).
S365_COMP_IDS = {
    "Egyptian Premier League": 552,
    "Turkish Super Lig": 78,
    "Saudi Pro League": 649,
    "CAF Champions League": 624,
    "Africa Cup of Nations Qualification": 588,
    "UEFA Nations League": 7016,
}
