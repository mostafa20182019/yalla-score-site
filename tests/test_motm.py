r"""The top-rated starter card under the score (2026-11-06).

    python tests/test_motm.py

The user: «اليوزر مبيحبش القراءة بيحب يشوف المعلومات من الصور». The reading's
«الأفضل في اللقاء» line became a card: photo, rating, name, club and up to
three facts. It says «الأعلى تقييمًا في المباراة» - the rating is 365scores',
and an official man-of-the-match award can go to someone else.
"""
import os, re, sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())
from site_lib.tables import motm_html                      # noqa: E402

fails = []
def ck(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  [{extra}]" if extra else ""))
    if not cond:
        fails.append(name)

def xi(prefix, top=None, top_rt=None, st=None):
    out = [{"name": f"{prefix}{i}", "num": i, "rt": 6.0 + i / 10} for i in range(1, 12)]
    if top:
        out[5].update(name=top, rt=top_rt, **({"st": st} if st else {}))
    return out

e = {"goals": [{"side": "a", "player": "نجم ب", "minute": "30", "tag": ""},
               {"side": "a", "player": "نجم ب", "minute": "60", "tag": "", "assist": "ب3"},
               {"side": "a", "player": "ب4", "minute": "70", "tag": "", "assist": "نجم ب"}],
     "lineups": {"h": {"xi": xi("أ")},
                 "a": {"xi": xi("ب", "نجم ب", 8.9, {"3": "5", "19": "30/34 (88%)", "46": "0"})}}}
html = motm_html(e, False, "الفريق أ", "الفريق ب")
txt = re.sub(r"<[^>]+>", " ", html)
ck("1 the highest rating across BOTH teams wins, with his club", "نجم ب" in txt and "الفريق ب" in txt and "8.9" in txt, txt)
ck("2 the label is the honest one, never «رجل المباراة»", "الأعلى تقييمًا في المباراة" in txt and "رجل المباراة" not in txt)
chips = re.findall(r'<span class="motm-f">(.*)</span></span></section>', html)
facts = re.findall(r"<span>(.*?)</span>", chips[0]) if chips else []
ck("3 facts: two goals, one assist, then his first non-zero stat - three at most",
   len(facts) == 3 and "هدفان" in facts[0] and "صناعة هدف" in facts[1] and "<svg" in facts[1]
   and "تسديدات: 5" in facts[2], facts)
ck("4 a player with stats opens his pitch card (button + data-pn)",
   'role="button"' in html and 'data-pn="نجم ب"' in html)

flipped = motm_html(e, True, "الفريق أ", "الفريق ب")
ck("5 a flipped details entry names the right club", "الفريق أ" in re.sub(r"<[^>]+>", " ", flipped)
   and "الفريق ب" not in re.sub(r"<[^>]+>", " ", flipped))

gk = {"goals": [], "lineups": {"h": {"xi": xi("أ", "الحارس", 9.1, {"23": "7", "19": "20/30 (67%)"})},
                               "a": {"xi": xi("ب")}}}
g = motm_html(gk, False, "أ", "ب")
ck("6 a goalkeeper's saves lead his facts", "تصديات: 7" in g and "دقة التمرير: 67%" in g, re.sub(r"<[^>]+>", " ", g))

old = {"goals": [], "lineups": {"h": {"xi": xi("أ", "قديم", 8.0)}, "a": {"xi": xi("ب")}}}
o = motm_html(old, False, "أ", "ب")
ck("7 a match fetched before the stats has a card but no button and no facts row",
   'class="motm"' in o and 'role="button"' not in o and "motm-f" not in o)

partial = {"goals": [], "lineups": {"h": {"xi": [dict(p, rt=None) for p in xi("أ")]}, "a": {"xi": xi("ب")}}}
ck("8 fewer than 18 rated starters: no card (a partial feed crowns nobody)", motm_html(partial, False, "أ", "ب") == "")
ck("9 no lineups at all: nothing", motm_html({}, False, "أ", "ب") == "")

src = open("site_pages/matches.py", encoding="utf-8").read()
ck("10 only a FINISHED page gets the card", 'if st == "FINISHED" and _det else ""' in src)

print(f"\n{len(fails)} FAILED" if fails else "\nALL OK")
sys.exit(1 if fails else 0)
