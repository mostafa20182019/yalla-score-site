"""Clubs: the curated scope, the ticker, the club pages, the Arabic spellings, legends.

Moved verbatim out of build_site.py (slice 2, 2026-09-25) - the source
text and its comments are exactly what they were there. Edit here;
build_site imports these back under the same names."""

# a scope is None (any competition), one competition name, or a tuple of
# names — the Egyptian clubs must count in Africa too (CAF CL, 2026-09-02),
# while bare "الأهلي" must still never match Saudi Al-Ahli
EGY_SCOPE = ("Egyptian Premier League", "CAF Champions League")

TICKER_TEAMS = [
    ("Real Madrid", None), ("FC Barcelona", None), ("Manchester United", None),
    ("Manchester City", None), ("Arsenal FC", None), ("Liverpool FC", None),
    ("Chelsea FC", None),
    ("الأهلي", EGY_SCOPE),
    ("الزمالك", EGY_SCOPE),
    ("بيراميدز", EGY_SCOPE),
    ("طرابزون سبور", "Turkish Super Lig"),
]

# Evergreen club pages (/team/<slug>) — one per curated club, targeting
# "أخبار الأهلي اليوم" / "مباريات الزمالك القادمة" query families.
# match_tokens follow the TICKER_TEAMS convention: (substring token,
# competition-scope-or-None) — FD English tokens for European clubs
# ("FC Barcelona" not "Barcelona": Espanyol collision), Arabic clubs scoped
# to their league (bare "الأهلي" also matches Saudi Al-Ahli). news_tokens
# are searched in article title+summary; news_excl vetoes false positives.
TEAM_PAGES = [
    {"slug": "al-ahly", "name": "الأهلي", "league": "Egyptian Premier League",
     "match_tokens": [("الأهلي", EGY_SCOPE)],
     "news_tokens": ["الأهلي"],
     "news_excl": ["الأهلي السعودي", "أهلي جدة", "شباب الأهلي دبي", "شباب أهلي دبي"]},
    {"slug": "zamalek", "name": "الزمالك", "league": "Egyptian Premier League",
     "match_tokens": [("الزمالك", EGY_SCOPE)],
     "news_tokens": ["الزمالك"]},
    {"slug": "pyramids", "name": "بيراميدز", "league": "Egyptian Premier League",
     "match_tokens": [("بيراميدز", EGY_SCOPE)],
     "news_tokens": ["بيراميدز"]},
    {"slug": "real-madrid", "name": "ريال مدريد", "league": "Primera Division",
     "match_tokens": [("Real Madrid", None)], "news_tokens": ["ريال مدريد"]},
    {"slug": "barcelona", "name": "برشلونة", "league": "Primera Division",
     "match_tokens": [("FC Barcelona", None)], "news_tokens": ["برشلونة"]},
    {"slug": "man-united", "name": "مانشستر يونايتد", "league": "Premier League",
     "match_tokens": [("Manchester United", None)],
     "news_tokens": ["مانشستر يونايتد"]},
    {"slug": "man-city", "name": "مانشستر سيتي", "league": "Premier League",
     "match_tokens": [("Manchester City", None)],
     "news_tokens": ["مانشستر سيتي"]},
    {"slug": "arsenal", "name": "أرسنال", "league": "Premier League",
     "match_tokens": [("Arsenal FC", None)], "news_tokens": ["أرسنال", "آرسنال"]},
    {"slug": "liverpool", "name": "ليفربول", "league": "Premier League",
     "match_tokens": [("Liverpool FC", None)], "news_tokens": ["ليفربول"]},
    {"slug": "chelsea", "name": "تشيلسي", "league": "Premier League",
     "match_tokens": [("Chelsea FC", None)], "news_tokens": ["تشيلسي"]},
    {"slug": "trabzonspor", "name": "طرابزون سبور", "league": "Turkish Super Lig",
     "match_tokens": [("طرابزون سبور", "Turkish Super Lig")],
     "news_tokens": ["طرابزون", "محمد صلاح"]},
]

# Arabic display names for football-data's Latin team names (365scores
# leagues arrive Arabic-native). Unmapped names fall through unchanged.
AR_TEAM = {
    "1. FC Köln": "كولن", "1. FC Union Berlin": "يونيون برلين",
    "1. FSV Mainz 05": "ماينز 05", "AC Milan": "ميلان", "AC Monza": "مونزا",
    "ACF Fiorentina": "فيورنتينا", "AFC Ajax": "أياكس",
    "AFC Bournemouth": "بورنموث", "AJ Auxerre": "أوكسير",
    "AS Monaco FC": "موناكو", "AS Roma": "روما", "Angers SCO": "أنجيه",
    "Arsenal FC": "أرسنال", "Aston Villa FC": "أستون فيلا",
    "Atalanta BC": "أتالانتا", "Athletic Club": "أتلتيك بلباو",
    "Bayer 04 Leverkusen": "باير ليفركوزن", "Bologna FC 1909": "بولونيا",
    "Borussia Dortmund": "بوروسيا دورتموند",
    "Borussia Mönchengladbach": "بوروسيا مونشنجلادباخ",
    "Brentford FC": "برينتفورد", "Brighton & Hove Albion FC": "برايتون",
    "CA Osasuna": "أوساسونا", "Cagliari Calcio": "كالياري",
    "Chelsea FC": "تشيلسي", "Club Atlético de Madrid": "أتلتيكو مدريد",
    "Club Brugge KV": "كلوب بروج", "Como 1907": "كومو",
    "Coventry City FC": "كوفنتري سيتي", "Crystal Palace FC": "كريستال بالاس",
    "Deportivo Alavés": "ألافيس", "ES Troyes AC": "تروا",
    "Eintracht Frankfurt": "آينتراخت فرانكفورت", "Elche CF": "إلتشي",
    "Everton FC": "إيفرتون", "FC Augsburg": "أوغسبورغ",
    "FC Barcelona": "برشلونة", "FC Bayern München": "بايرن ميونخ",
    "FC Internazionale Milano": "إنتر ميلان", "FC København": "كوبنهاجن",
    "FC Lorient": "لوريان", "FC Schalke 04": "شالكه",
    "FK Bodø/Glimt": "بودو جليمت", "FK Kairat": "كايرات",
    "Frosinone Calcio": "فروزينوني", "Fulham FC": "فولهام",
    "Galatasaray SK": "جالطة سراي", "Genoa CFC": "جنوى",
    "Getafe CF": "خيتافي", "Hamburger SV": "هامبورج",
    "Hull City AFC": "هال سيتي", "Ipswich Town FC": "إبسويتش تاون",
    "Juventus FC": "يوفنتوس", "Le Havre AC": "لو آفر",
    "Le Mans FC": "لومان", "Leeds United FC": "ليدز يونايتد",
    "Levante UD": "ليفانتي", "Lille OSC": "ليل", "Liverpool FC": "ليفربول",
    "Manchester City FC": "مانشستر سيتي",
    "Manchester United FC": "مانشستر يونايتد", "Málaga CF": "مالقا",
    "Newcastle United FC": "نيوكاسل يونايتد",
    "Nottingham Forest FC": "نوتنجهام فورست", "OGC Nice": "نيس",
    "Olympique Lyonnais": "أولمبيك ليون", "Olympique de Marseille": "أولمبيك مارسيليا",
    "PAE Olympiakos SFP": "أولمبياكوس", "PSV": "آيندهوفن",
    "Paphos FC": "بافوس", "Paris FC": "باريس أف.سي.",
    "Paris Saint-Germain FC": "باريس سان جيرمان",
    "Parma Calcio 1913": "بارما", "Qarabağ Ağdam FK": "قره باغ",
    "RB Leipzig": "لايبزيج", "RC Celta de Vigo": "سيلتا فيجو",
    "RC Deportivo La Coruña": "ديبورتيفو لاكورونيا",
    "RC Strasbourg Alsace": "ستراسبورج",
    "RCD Espanyol de Barcelona": "إسبانيول",
    "Racing Club de Lens": "لانس",
    "Rayo Vallecano de Madrid": "رايو فاييكانو",
    "Real Betis Balompié": "ريال بيتيس", "Real Madrid CF": "ريال مدريد",
    "Real Racing Club de Santander": "راسينج سانتاندير",
    "Real Sociedad de Fútbol": "ريال سوسيداد",
    "Royale Union Saint-Gilloise": "يونيون سان جيلواز",
    "SC Freiburg": "فرايبورج", "SC Paderborn 07": "بادربورن",
    "SK Slavia Praha": "سلافيا براج", "SS Lazio": "لاتسيو",
    "SSC Napoli": "نابولي", "SV 07 Elversberg": "إلفيرسبيرغ",
    "SV Werder Bremen": "فيردر بريمن", "Sevilla FC": "إشبيلية",
    "Sport Lisboa e Benfica": "بنفيكا",
    "Sporting Clube de Portugal": "سبورتينج لشبونة",
    "Stade Brestois 29": "بريست", "Stade Rennais FC 1901": "ستاد رين",
    "Sunderland AFC": "سندرلاند", "TSG 1899 Hoffenheim": "هوفنهايم",
    "Torino FC": "تورينو", "Tottenham Hotspur FC": "توتنهام هوتسبر",
    "Toulouse FC": "تولوز", "US Lecce": "ليتشي",
    "US Sassuolo Calcio": "ساسولو", "Udinese Calcio": "أودينيزي",
    "Valencia CF": "فالنسيا", "Venezia FC": "فينيزيا",
    "VfB Stuttgart": "شتوتجارت", "Villarreal CF": "فياريال",
}

# home block 2 filter: Egyptian-football stories (clubs, league, NT)
_EGY_TOKENS = ["الأهلي", "الزمالك", "بيراميدز", "الدوري المصري",
               "منتخب مصر", "كأس مصر"]

# home block 3 filter: European-football stories (big clubs + leagues).
# Runs AFTER the Egyptian block, so a story naming both (بيراميدز يفاوض
# لاعب برشلونة) lands in the Egyptian block and never duplicates here.
_EUR_TOKENS = ["ريال مدريد", "برشلونة", "مانشستر يونايتد", "مانشستر سيتي",
               "أرسنال", "آرسنال", "ليفربول", "تشيلسي", "توتنهام",
               "نيوكاسل", "بايرن ميونخ", "بوروسيا دورتموند",
               "باريس سان جيرمان", "يوفنتوس", "إنتر ميلان", "ميلان",
               "نابولي", "أتلتيكو مدريد", "الدوري الإنجليزي",
               "الدوري الإسباني", "الدوري الإيطالي", "الدوري الألماني",
               "الدوري الفرنسي", "دوري أبطال أوروبا", "الدوري الأوروبي",
               "طرابزون سبور"]

# ---- legends header strip (free CC / public-domain photos, same as the app) ----
# 8 hand-picked legends (name for tooltip/alt, 200px Wikimedia thumb).
# Every photo was visually reviewed 2026-07-25 — face-centered, good quality.
# (name, url, face position "x% y%", zoom) — the July-2026 NT photos are
# half-body shots, so each avatar is hand-cropped to a tight face close-up:
# object-position centres the face, transform:scale zooms in on it.
LEGENDS = [
  # uniform crops: every face ~same size in the circle, eyes on one line
  # (head + a hint of shoulders; was a mix of tight/loose zooms)
  ("محمد صلاح",         "https://commons.wikimedia.org/wiki/Special:FilePath/Mohamed_Salah_Argentina_v_Egypt_7_July_2026-161.jpg?width=200", "50% 18%", 1.7),
  ("إمام عاشور",        "https://commons.wikimedia.org/wiki/Special:FilePath/Emam_Ashour_Argentina_v_Egypt_7_July_2026-099.jpg?width=200", "48% 16%", 1.8),
  ("شيكابالا",          "https://commons.wikimedia.org/wiki/Special:FilePath/Shikabala_2024_(cropped).jpg?width=200", "42% 14%", 1.9),
  ("عمر مرموش",         "https://commons.wikimedia.org/wiki/Special:FilePath/Omar_Marmoush_Argentina_v_Egypt_7_July_2026-102.jpg?width=200", "52% 17%", 1.6),
  ("محمد الشناوي",      "https://commons.wikimedia.org/wiki/Special:FilePath/Mohamed_El_Shenawy_Argentina_v_Egypt_7_July_2026-015.jpg?width=200", "50% 17%", 1.7),
  ("تريزيجيه",          "https://commons.wikimedia.org/wiki/Special:FilePath/Trezeguet_Argentina_v_Egypt_7_July_2026-267.jpg?width=200", "50% 15%", 1.7),
]
