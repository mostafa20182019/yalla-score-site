r"""«قراءة المباراة» — the post-match reading on /m/<id> (2026-09-14, layer 2).

    python tests/test_post_match.py       (from the repo root)

The block turns data the page already carries into sentences: the events into
a story, the XI rating badges into "who decided it", the official table into
"what the result changed". Every sentence must be a restatement - so the tests
are mostly about NOT saying things: no best player out of half a rated XI, no
table line when the table describes a later round, no comeback that did not
happen, and the correct side when the two sources disagree on who is at home.
"""
import os, sys
sys.stdout.reconfigure(encoding="utf-8")     # cp1252 console + Arabic output
sys.path.insert(0, os.getcwd())
import build_site as B

fails = []
def ck(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  [{extra}]" if extra else ""))
    if not cond:
        fails.append(name)

def goal(side, minute, player, tag=""):
    return {"side": side, "minute": str(minute), "player": player, "tag": tag}
def card(side, minute, player, color="y"):
    return {"side": side, "minute": str(minute), "player": player, "color": color}
def xi(prefix, ratings):
    return {"formation": "4-3-3",
            "xi": [{"name": f"{prefix}{i+1}", "num": i + 1, "ln": 1 + i % 4,
                    "rt": r} for i, r in enumerate(ratings)]}

H, A = "الأهلي", "الزمالك"

# ---------------------------------------------------------------- 1 the story
e = {"goals": [goal("a", 12, "زيزو"), goal("h", 55, "وسام أبو علي"),
               goal("h", 88, "أحمد سيد")],
     "cards": [card("a", 70, "محمد شحاتة", "r")], "subs": []}
st = B.match_story(e, False, H, A, 2, 1)
txt = " ".join(st)
ck("1 the opener names the scorer, his club and the minute (with a real lam: للزمالك)",
   "افتتح زيزو التسجيل للزمالك" in txt and "12" in txt and "لـال" not in txt, txt)
ck("2 a comeback is called a comeback (and only for the side that made it)",
   f"قلب {H} تأخره" in txt, txt)
ck("3 the goal that settled it is the one that took the lead for good, and 88' is late",
   "هدف الحسم متأخرًا" in txt and "أحمد سيد" in txt and "88" in txt, txt)
# no lineups in this entry -> we cannot prove the sent-off name was on the
# pitch, so the sentence states the red card and claims nothing about numbers
ck("4 a sending-off with no XI to check against is stated, not counted",
   "بطاقة حمراء" in txt and "محمد شحاتة" in txt and "بعشرة" not in txt, txt)

# a match with no comeback must not claim one
e2 = {"goals": [goal("h", 10, "أ"), goal("h", 60, "ب")], "cards": [], "subs": []}
t2 = " ".join(B.match_story(e2, False, H, A, 2, 0))
ck("5 no comeback sentence when the opener won it", "قلب" not in t2, t2)
ck("5b the decider sentence is dropped when the OPENER was the decisive goal",
   "هدف الحسم" not in t2, t2)
t2b = " ".join(B.match_story({"goals": [goal("a", 5, "x"), goal("h", 20, "y"),
                                        goal("h", 70, "z")], "cards": [], "subs": []},
                             False, H, A, 2, 1))
# 5'-1-0 away, 20' equaliser, 70' winner: the goal that TOOK THE LEAD for good
# is the 70th-minute one - the equaliser only levelled it
ck("5c but it stays when the lead actually changed hands", "هدف الحسم عبر z" in t2b, t2b)
ck("5d a name arriving with trailing spaces is trimmed",
   " ".join(B.match_story({"goals": [goal("h", 9, "مبابي ")], "cards": [], "subs": []},
                          False, H, A, 1, 0)).count("مبابي التسجيل") == 1)
ck("6 a clean sheet is noted", "نظافة شباكه" in t2, t2)

# flipped = the feed's home is our away
t3 = " ".join(B.match_story(e2, True, H, A, 0, 2))
ck("7 flipped details put the goals under the right club",
   f"التسجيل {B._lam(A)}" in t3 and f"نظافة شباكه" in t3 and f"قلب" not in t3, t3)

# draw after trailing, own goal, brace, goalless
t4 = " ".join(B.match_story({"goals": [goal("h", 20, "س"), goal("a", 75, "ع")],
                             "cards": [], "subs": []}, False, H, A, 1, 1))
ck("8 an equaliser is 'أدرك التعادل بعد تأخره' for the side that was behind",
   f"أدرك {A} التعادل" in t4, t4)
t5 = " ".join(B.match_story({"goals": [goal("h", 30, "مدافع", "عكسية")],
                             "cards": [], "subs": []}, False, H, A, 1, 0))
ck("9 an own goal is not credited as 'افتتح التسجيل لـ' the wrong club",
   "هدف عكسي" in t5 and "افتتح" not in t5, t5)
t6 = " ".join(B.match_story({"goals": [goal("h", 5, "لاعب"), goal("h", 65, "لاعب")],
                             "cards": [], "subs": []}, False, H, A, 2, 0))
ck("10 two goals by one player are counted", "سجّل لاعب هدفين للأهلي" in t6, t6)
t7 = " ".join(B.match_story({"goals": [], "cards": [], "subs": []}, False, H, A, 0, 0))
ck("11 a goalless draw still gets a sentence", "التعادل السلبي" in t7, t7)
t8 = B.match_story({"goals": [goal("h", "", "بدون دقيقة")], "cards": [], "subs": []},
                   False, H, A, 1, 0)
ck("12 a goal with no minute never invents one",
   all("الدقيقة" not in x for x in t8), " | ".join(t8))

# a red card shown to a MANAGER (Neom x Al-Fateh 2026: Christophe Galtier) must
# never become "the team played with ten men" - his name is in no XI and in no
# substitution, and the eleven on the pitch stayed eleven
coach = {"goals": [goal("h", 16, "لاكازيت")],
         "cards": [card("h", 45, "كريستوف غالتييه", "r")],
         "subs": [{"side": "h", "in": "بديل", "out": "أساسي2", "minute": "60"}],
         "lineups": {"h": xi("أساسي", [6.5] * 11), "a": xi("a", [6.5] * 11)}}
t9 = " ".join(B.match_story(coach, False, H, A, 1, 0))
ck("12b a red card for a name that never played is not 'ten men'",
   "بعشرة لاعبين" not in t9 and "بطاقة حمراء" in t9 and "غالتييه" in t9, t9)
onpitch = dict(coach, cards=[card("h", 45, "أساسي3", "r")])
t10 = " ".join(B.match_story(onpitch, False, H, A, 1, 0))
ck("12c a red card for a player in the XI IS 'ten men'", "بعشرة لاعبين" in t10, t10)
sub_off = dict(coach, cards=[card("h", 70, "بديل", "r")])
ck("12d a substitute sent off counts too",
   "بعشرة لاعبين" in " ".join(B.match_story(sub_off, False, H, A, 1, 0)))
two = dict(coach, cards=[card("h", 45, "أساسي3", "r"), card("h", 60, "أساسي4", "r")])
ck("12e two players off is nine, not ten",
   "بتسعة لاعبين" in " ".join(B.match_story(two, False, H, A, 1, 0)))

# ------------------------------------------------------------- 2 the ratings
full = {"lineups": {"h": xi("h", [7.2, 6.5, 6.0, 7.9, 6.8, 7.1, 6.4, 8.6, 7.0, 6.9, 5.7]),
                    "a": xi("a", [6.1, 6.3, 5.9, 6.6, 7.4, 6.2, 6.0, 6.5, 6.8, 6.1, 6.7])}}
r = B.match_ratings(full, False, H, A)
ck("13 the best player of the match is the highest rating on either side",
   r and r["best"]["name"] == "h8" and r["best"]["club"] == H, r and r["best"])
ck("14 the best of the OTHER club is named too",
   r["best_other"]["name"] == "a5" and r["best_other"]["club"] == A, r["best_other"])
ck("15 the lowest rating in the match is found across both sides",
   r["low"]["name"] == "h11", r["low"])
ck("16 team averages are the mean of the rated XI",
   r["sides"][0]["avg"] == round(sum([7.2, 6.5, 6.0, 7.9, 6.8, 7.1, 6.4, 8.6, 7.0, 6.9, 5.7]) / 11, 1),
   r["sides"][0]["avg"])
flip = B.match_ratings(full, True, H, A)
ck("17 flipped: the feed's home XI belongs to our away club",
   flip["best"]["club"] == A, flip["best"])

half = {"lineups": {"h": xi("h", [7.0, 6.0, 6.5]), "a": xi("a", [6.0] * 11)}}
ck("18 an incomplete rated XI says nothing at all (no best player out of three)",
   B.match_ratings(half, False, H, A) is None)
ck("19 no lineups at all -> nothing", B.match_ratings({}, False, H, A) is None)

# ---------------------------------------------------------- 3 the table line
TABLE = {"competition": "Egyptian Premier League", "table": [
    {"pos": 1, "team": "بيراميدز", "played": 5, "pts": 13},
    {"pos": 2, "team": "الأهلي", "played": 5, "pts": 11},
    {"pos": 3, "team": "الزمالك", "played": 5, "pts": 9},
]}
def fx(kick, home, away):
    return {"kickoff": kick, "home": home, "away": away, "status": "FINISHED",
            "home_score": 1, "away_score": 0, "competition": "Egyptian Premier League"}
M = {"home": "الأهلي", "away": "الزمالك", "kickoff": "2026-09-13",
     "competition": "Egyptian Premier League"}
FIN = [fx("2026-09-01", "الأهلي", "x"), fx("2026-09-02", "الزمالك", "y"),
       fx("2026-09-05", "z", "الأهلي"), fx("2026-09-06", "w", "الزمالك"),
       fx("2026-09-08", "الأهلي", "v"), fx("2026-09-09", "الزمالك", "u"),
       fx("2026-09-10", "t", "الأهلي"), fx("2026-09-11", "s", "الزمالك"),
       fx("2026-09-13", "الأهلي", "الزمالك")]
FORMS = {"الأهلي": ["W", "D", "W", "W", "W"], "الزمالك": ["W", "W", "D", "L", "L"]}
lines = B.table_after(M, TABLE, FORMS, FIN, H, A)
ck("20 both clubs get their place and points from the official table",
   len(lines) == 2 and "المركز الثاني" in lines[0] and "11" in lines[0], lines)
ck("21 the gap names the neighbour AND its place",
   "بفارق نقطتين خلف بيراميدز (الأول)" in lines[0], lines[0])
ck("22 a winning run is read off the form list",
   "الفوز الثالث على التوالي" in lines[0], lines[0])
ck("23 and a losing run too, with the feminine ordinal Arabic needs",
   "الخسارة الثانية على التوالي" in lines[1], lines[1])

ck("23b places past the tenth are still ordinals, not «المركز رقم 15»",
   B._ord_ar(15) == "الخامس عشر" and B._ord_ar(20) == "العشرين"
   and B._ord_ar(24) == "24" and "رقم" not in B._ord_ar(24), B._ord_ar(15))
ck("23c a long run drops the ordinal instead of inventing one",
   B._streak_ar(["W"] * 12) == "12 انتصارات متتالية", B._streak_ar(["W"] * 12))

late = FIN + [fx("2026-09-16", "الأهلي", "q")]
ck("24 NOTHING is said when a later match has been played since",
   B.table_after(M, TABLE, FORMS, late, H, A) == [])
behind = {"competition": "Egyptian Premier League", "table": [
    dict(TABLE["table"][0]), dict(TABLE["table"][1], played=4), dict(TABLE["table"][2])]}
ck("25 NOTHING is said when the official table has not counted this match yet",
   B.table_after(M, behind, FORMS, FIN, H, A) == [])
ck("26 a pre-season (zeroed) table is never read",
   B.table_after(M, dict(TABLE, zeroed=True), FORMS, FIN, H, A) == [])
ck("27 a competition with no table (a cup) is skipped",
   B.table_after(M, None, FORMS, FIN, H, A) == [])

# ------------------------------------------------------------- 4 the section
html, faq = B.post_match_read(M, dict(full, **e), False, H, A, 2, 1,
                              "الدوري المصري", TABLE, FORMS, FIN)
ck("28 the section renders with the story, the chips, the averages and the table line",
   'class="minfo st-analysis mread"' in html and "rt-b" in html
   and "متوسط تقييم التشكيلة" in html and "بعد هذه النتيجة" in html)
ck("29 the FAQ answers the score, the scorers, the best player and the table",
   faq.count("<details>") == 4 and "FAQPage" in faq and "زيزو" in faq, faq.count("<details>"))
# a finished match whose details entry carries no usable events (it exists only
# because the XI was announced, or the feed's goal list failed the score
# reconciliation): no empty card, no half-sentence - the section is not rendered
ck("30 nothing at all when there is no story, no ratings and no table",
   B.post_match_read(M, {"goals": [], "cards": [], "subs": []}, False, H, A,
                     3, 1, "الدوري المصري", None, {}, []) == ("", ""))

# two players tied on the top rating: neither is crowned "best of the match"
tied = {"lineups": {"h": xi("h", [8.5] + [6.0] * 10), "a": xi("a", [8.5] + [6.0] * 10)}}
h2, f2 = B.post_match_read(M, dict(tied, goals=[], cards=[], subs=[]), False, H, A,
                           1, 0, "الدوري المصري", None, {}, [])
ck("31 a tie on the top rating is not crowned 'الأفضل في اللقاء'",
   "الأفضل في اللقاء" not in h2 and f'الأفضل في {H}' in h2 and f'الأفضل في {A}' in h2)
ck("32 and the FAQ says the two tied instead of picking one", "تساوى" in f2)

print()
print(f"{len(fails)} FAILED: {', '.join(fails)}" if fails else "ALL POST-MATCH TESTS PASSED")
sys.exit(1 if fails else 0)
