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
                     "UEFA Nations League", "UEFA Europa League",
                     "CAF Confederation Cup",
                     # 2026-11-02 (user ask)
                     "Moroccan Botola Pro", "Algerian Ligue 1", "Tunisian Ligue 1",
                     "Libyan Premier League", "UEFA Conference League",
                     # 2026-11-03 (user ask)
                     "Egypt Cup", "Egyptian League Cup",
                     # 2026-11-11 (user ask)
                     "Egyptian Second Division", "FIFA U-17 World Cup")

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
    "UEFA Europa League": "europa-league",
    "CAF Confederation Cup": "caf-confederation-cup",
    "Moroccan Botola Pro": "morocco",
    "Algerian Ligue 1": "algeria",
    "Tunisian Ligue 1": "tunisia",
    "Libyan Premier League": "libya",
    "UEFA Conference League": "conference-league",
    "Egypt Cup": "egypt-cup",
    "Egyptian League Cup": "egypt-capital-cup",
    "Egyptian Second Division": "egypt-second-division",   # 2026-11-11
    "FIFA U-17 World Cup": "u17-world-cup",                 # 2026-11-11
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
    # Verified 2026-10-08 (growth plan, week 0) - MENA rights for 2026/27, one
    # dated source each; the match page says «في المنطقة العربية»:
    "Serie A": "STARZPLAY وقنوات أبوظبي الرياضية",   # dzsport-live 2026-08-05 (STARZPLAY exclusive, AD Sports partner)
    "Bundesliga": "MBC Action وشاهد",              # offsideeg 2025-08-21: MBC, seasons 2025/26-2027/28
    "Saudi Pro League": "ثمانية",                    # Ahram Gate 2026-08-13: Thmanyah exclusive to 2030/31
    "Turkish Super Lig": "beIN Sports",             # Masrawy 2026-08-05: beIN to the end of 2026/27
    "Africa Cup of Nations Qualification": "beIN Sports",   # Annahar/Alkhaleej Sep 2026 (Egypt home games also terrestrial)
    "UEFA Nations League": "beIN Sports",           # Raya 2026-09-24
    "UEFA Europa League": "beIN Sports",            # same UEFA club package as the UCL in MENA (2024/25-2026/27)
    "CAF Confederation Cup": "beIN Sports",         # the CAF club package, like the CAF CL (user-confirmed 2026-09-02)
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
    "UEFA Europa League":
        "https://imagecache.365scores.com/image/upload/"
        "f_png,w_68,h_68,c_limit,q_auto:eco,dpr_2,"
        "d_Competitions:default1.png/v4/Competitions/573",
    "CAF Confederation Cup":
        "https://imagecache.365scores.com/image/upload/"
        "f_png,w_68,h_68,c_limit,q_auto:eco,dpr_2,"
        "d_Competitions:default1.png/v4/Competitions/627",
    # 2026-11-02: the four North African leagues + the Conference League
    "Moroccan Botola Pro":
        "https://imagecache.365scores.com/image/upload/"
        "f_png,w_68,h_68,c_limit,q_auto:eco,dpr_2,"
        "d_Competitions:default1.png/v4/Competitions/557",
    "Algerian Ligue 1":
        "https://imagecache.365scores.com/image/upload/"
        "f_png,w_68,h_68,c_limit,q_auto:eco,dpr_2,"
        "d_Competitions:default1.png/v4/Competitions/560",
    "Tunisian Ligue 1":
        "https://imagecache.365scores.com/image/upload/"
        "f_png,w_68,h_68,c_limit,q_auto:eco,dpr_2,"
        "d_Competitions:default1.png/v4/Competitions/554",
    "Libyan Premier League":
        "https://imagecache.365scores.com/image/upload/"
        "f_png,w_68,h_68,c_limit,q_auto:eco,dpr_2,"
        "d_Competitions:default1.png/v4/Competitions/559",
    "UEFA Conference League":
        "https://imagecache.365scores.com/image/upload/"
        "f_png,w_68,h_68,c_limit,q_auto:eco,dpr_2,"
        "d_Competitions:default1.png/v4/Competitions/7685",
    "Egypt Cup":
        "https://imagecache.365scores.com/image/upload/"
        "f_png,w_68,h_68,c_limit,q_auto:eco,dpr_2,"
        "d_Competitions:default1.png/v4/Competitions/553",
    "Egyptian League Cup":
        "https://imagecache.365scores.com/image/upload/"
        "f_png,w_68,h_68,c_limit,q_auto:eco,dpr_2,"
        "d_Competitions:default1.png/v4/Competitions/7808",
    # 2026-11-11
    "Egyptian Second Division":
        "https://imagecache.365scores.com/image/upload/"
        "f_png,w_68,h_68,c_limit,q_auto:eco,dpr_2,"
        "d_Competitions:default1.png/v4/Competitions/6994",
    "FIFA U-17 World Cup":
        "https://imagecache.365scores.com/image/upload/"
        "f_png,w_68,h_68,c_limit,q_auto:eco,dpr_2,"
        "d_Competitions:default1.png/v4/Competitions/5582",
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
    "UEFA Europa League": "الدوري الأوروبي",
    "CAF Confederation Cup": "كأس الكونفدرالية الأفريقية",
    "Moroccan Botola Pro": "الدوري المغربي",
    "Algerian Ligue 1": "الدوري الجزائري",
    "Tunisian Ligue 1": "الدوري التونسي",
    "Libyan Premier League": "الدوري الليبي",
    "UEFA Conference League": "دوري المؤتمر الأوروبي",
    "Egypt Cup": "كأس مصر",
    "Egyptian League Cup": "كأس عاصمة مصر",   # 365scores: «كأس الرابطة المصرية»
    # 2026-11-11: the user's own words for both
    "Egyptian Second Division": "دوري المحترفين المصري",   # 365scores: «… - ممتاز أ»
    "FIFA U-17 World Cup": "كأس العالم تحت 17 سنة",
}

# tournaments played inside ONE calendar year: their pages say «2026», not
# the league season «2026-2027» (2026-11-11: the U-17 World Cup, November)
SINGLE_YEAR_COMPS = ("FIFA U-17 World Cup",)


def comp_season(comp, season, rounds=None):
    """The season text a competition's pages print: the league season, or -
    for a single-year tournament - the year of its first match (this year
    when no fixtures are known)."""
    if comp not in SINGLE_YEAR_COMPS:
        return season
    import datetime
    days = [m.get("kickoff") or "" for r in (rounds or []) for m in (r.get("matches") or [])]
    days = [d for d in days if d[:4].isdigit()]
    return min(days)[:4] if days else str(datetime.date.today().year)


# the league chips at the top of the home page (user, 2026-10-22: «عايز دول
# بس، شيل الباقى»): these nine, in this order, nothing else
LEAGUE_BAR = ("Egyptian Premier League", "Premier League", "Primera Division",
              "Turkish Super Lig", "Saudi Pro League", "Ligue 1",
              "Bundesliga", "Serie A", "UEFA Champions League")

# fixed sidebar order (user's pick 2026-08-13); anything unlisted goes last
COMP_ORDER = ["Egyptian Premier League",
              "Egypt Cup", "Egyptian League Cup",   # right after the league (user ask 2026-11-03)
              "Premier League", "Primera Division",
              "Turkish Super Lig", "Saudi Pro League", "Ligue 1",
              "Bundesliga", "Serie A", "UEFA Champions League",
              "UEFA Europa League",     # right after the UCL (user ask 2026-10-15)
              "UEFA Conference League", # right after the UEL (user ask 2026-11-02)
              "CAF Champions League",   # after UCL (user pick 2026-09-02)
              "CAF Confederation Cup",  # right after the CAF CL (user ask 2026-10-17)
              # the national teams before the Arab leagues (user, 2026-11-11:
              # «عايز بطولة تصفيات افريقيا وبطولة دورى الامم الاوروبية تظهر
              # فوق الدورى التونسى» - an international break's day showed
              # Tunisia's postponed rows above the matches being played)
              "Africa Cup of Nations Qualification",  # user ask 2026-09-20
              "UEFA Nations League",                  # user ask 2026-09-21
              "FIFA U-17 World Cup",                  # user ask 2026-11-11
              # the North African leagues (user ask 2026-11-02)
              "Moroccan Botola Pro", "Algerian Ligue 1", "Tunisian Ligue 1",
              "Libyan Premier League",
              # a second division comes after every Arab FIRST division (user,
              # 2026-11-11: «نزل الدورى التونسى تحت» when it sat after the cups)
              "Egyptian Second Division"]

# 365scores competition ids for the leagues TICKER_TEAMS scopes by name —
# must agree with LIVE_COMPS in worker.js
# (552,78,649,7,11,17,25,35,572,624,588,7016,573,627,557,560,554,559,7685,553,7808,6994,5582).
S365_COMP_IDS = {
    "Egyptian Premier League": 552,
    "Turkish Super Lig": 78,
    "Saudi Pro League": 649,
    "CAF Champions League": 624,
    "Africa Cup of Nations Qualification": 588,
    "UEFA Nations League": 7016,
    "UEFA Europa League": 573,
    "CAF Confederation Cup": 627,
    "Moroccan Botola Pro": 557,
    "Algerian Ligue 1": 560,
    "Tunisian Ligue 1": 554,
    "Libyan Premier League": 559,
    "UEFA Conference League": 7685,
    "Egypt Cup": 553,
    "Egyptian League Cup": 7808,
    "Egyptian Second Division": 6994,   # 2026-11-11
    "FIFA U-17 World Cup": 5582,        # 2026-11-11
}
