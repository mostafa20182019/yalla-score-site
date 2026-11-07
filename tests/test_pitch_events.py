r"""Goals and assists on the lineup pitch (user, 2026-11-06).

    python tests/test_pitch_events.py

«عايزك تحط هنا جنب اللعيب اللى سجل هدف كورة وجنب اللاعب اللى عمل اسيست
حذاء». 365scores names the assister in a goal event's extraPlayers; the fetch
keeps him as goal["assist"], and the pitch draws a ball beside every scorer
in the XI and a boot beside every assister, with a count when it is more than
one. An own goal is a red-ringed ball on the player who put it in, and never
credits an assist.
"""
import os, re, sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())
import fetch_data as F                                      # noqa: E402
from site_lib.tables import match_details_html             # noqa: E402

fails = []
def ck(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  [{extra}]" if extra else ""))
    if not cond:
        fails.append(name)

# ---------------------------------------------------------------- the fetch
goal = lambda pid, cid, t, extra=None, sub="": {
    "eventType": {"name": "هدف"}, "competitorId": cid, "playerId": pid, "gameTime": t,
    "addedTime": 0, "subTypeName": sub, **({"extraPlayers": extra} if extra else {})}
game = {"homeCompetitor": {"id": 1, "score": 3}, "awayCompetitor": {"id": 2, "score": 1},
        "members": [{"id": 10, "name": "مهاجم أ"}, {"id": 11, "name": "صانع أ"},
                    {"id": 20, "name": "مدافع ب"}],
        "events": [goal(10, 1, 12, [11]), goal(10, 1, 40, [11]), goal(10, 1, 70),
                   goal(20, 2, 80, [11], "هدف عكسي")]}
rows, health = F._goal_rows(game, 1)
ck("1 the fetch keeps the assister named in extraPlayers", rows[0].get("assist") == "صانع أ", rows[0])
ck("2 a goal with no extraPlayers has no assist key", "assist" not in rows[2], rows[2])
og = next(r for r in rows if r["tag"] == "عكسية")
ck("3 an own goal never credits an assist, even when the feed lists a player", "assist" not in og, og)

# ---------------------------------------------------------------- the pitch
def xi(prefix, names):
    lines = [1, 2, 2, 2, 2, 3, 3, 3, 4, 4, 4]
    return [{"name": n, "num": i + 1, "ln": lines[i], "sd": i * 10} for i, n in enumerate(names)]
home = ["حارس أ", "مدافع أ1", "مدافع أ2", "مدافع أ3", "مدافع أ4", "وسط أ1", "وسط أ2",
        "صانع أ", "جناح أ", "مهاجم أ", "مهاجم أ2"]
away = ["حارس ب", "مدافع ب", "مدافع ب2", "مدافع ب3", "مدافع ب4", "وسط ب1", "وسط ب2",
        "وسط ب3", "جناح ب", "مهاجم ب", "مهاجم ب2"]
e = {"goals": [{"side": "h", "player": "مهاجم أ", "minute": "12", "tag": "", "assist": "صانع أ"},
               {"side": "h", "player": "مهاجم أ", "minute": "40", "tag": "", "assist": "صانع أ"},
               {"side": "h", "player": "مهاجم أ", "minute": "70", "tag": ""},
               {"side": "h", "player": "مدافع ب", "minute": "80", "tag": "عكسية"}],
     "cards": [], "subs": [],
     "lineups": {"h": {"xi": xi("أ", home), "formation": "4-3-3"},
                 "a": {"xi": xi("ب", away), "formation": "4-3-3"}}}
html = match_details_html(e, False, "الفريق أ", "الفريق ب")
chips = {re.sub(r"^\d+\s*", "", re.sub(r"<[^>]+>", "", m.group(2))).strip(): m.group(1)
         for m in re.finditer(r'<span class="pp-ava">(.*?)</span><span class="pp-nm"><bdi>(.*?)</bdi>', html, re.S)}

def badge_of(short):
    k = short if short in chips else next((k for k in chips if short in k), None)
    return chips.get(k, "") if k else ""

sc = badge_of("مهاجم أ")
ck("4 the scorer gets a ball with his tally (3)", 'class="pp-ev"' in sc and "⚽<b>3</b>" in sc, sc[-220:])
asst = badge_of("صانع")
ck("5 the assister gets a boot with his tally (2)", 'pp-ev as' in asst and "<svg" in asst and "<b>2</b>" in asst, asst[-260:])
own = badge_of("مدافع ب")
ck("6 the own goal is a red-ringed ball on the player who put it in", "pp-ev og" in own, own[-200:])
quiet = badge_of("حارس أ")
ck("7 a player who neither scored nor assisted carries no event badge", "pp-evs" not in quiet)
ck("8 the badges carry an Arabic label for screen readers",
   'aria-label="هدف"' in html and 'aria-label="صناعة هدف"' in html and 'aria-label="هدف عكسي"' in html)

# ---------------------------------------------------------------- the match row
# «تحت اللاعب اللى مسجل الهدف اللاعب صاحب الاسيست» (same day): «صناعة: X» on
# its own line under the scorer, only when the feed named one
from site_lib.tables import match_row                       # noqa: E402
row = match_row({"status": "FINISHED", "home": "أ", "away": "ب", "home_score": 2, "away_score": 0,
                 "kickoff": "2026-11-06"}, goals=[
    {"side": "h", "player": "مهاجم أ", "minute": "12", "tag": "", "assist": "صانع أ"},
    {"side": "h", "player": "مهاجم أ", "minute": "70", "tag": ""}], show_assist=True)
# the lists (day lists, club pages...) call match_row without show_assist
_list = match_row({"status": "FINISHED", "home": "أ", "away": "ب", "home_score": 2, "away_score": 0,
                   "kickoff": "2026-11-06"}, goals=[
    {"side": "h", "player": "مهاجم أ", "minute": "12", "tag": "", "assist": "صانع أ"}])
ck("9b a match LIST row shows no assister (match page only, 2026-11-07)", "mg-as" not in _list and "صانع أ" not in _list)
items = re.findall(r'<span class="mg">(.*?)</span>(?=<span class="mg">|</div>)', row, re.S)
ck("9 the scorer with a named assister carries «صناعة: X» inside his line",
   items and '<span class="mg-as"><svg' in items[0] and '<span class="sr-only">صناعة: </span><bdi>صانع أ</bdi></span>' in items[0], items[:1])
ck("10 a goal with no assister carries no assist line", len(items) == 2 and "mg-as" not in items[1], items[1:])

# ---------------------------------------------------------------- the player card
# «لما اضغط على لاعب هنا يجبلى تفاصيل عنه زى 365 scores» (same day): the fetch
# keeps PLAYER_STATS per starter, the pitch makes those starters buttons and
# ships their card data as JSON + snippets/pitch_js.html
import json                                                   # noqa: E402
mm = {"stats": [{"type": 30, "value": "86'"}, {"type": 27, "value": "1"}, {"type": 3, "value": "2"},
                {"type": 4, "value": "1"}, {"type": 999, "value": "x"}, {"type": 19, "value": "19/21 (90%)"}]}
st = F._player_stats(mm)
ck("11 the fetch keeps only the chosen stats, as strings", st == {"30": "86'", "27": "1", "3": "2", "4": "1",
                                                                  "19": "19/21 (90%)"}, st)
ck("12 a member without stats keeps no st", F._player_stats({}) is None)

e2 = json.loads(json.dumps(e))
for pl in e2["lineups"]["h"]["xi"]:
    if pl["name"] in ("مهاجم أ", "حارس أ"):
        pl["st"] = dict(st, **({"23": "4", "35": "1"} if pl["name"] == "حارس أ" else {}))
        pl["rt"] = 8.1
html2 = match_details_html(e2, False, "الفريق أ", "الفريق ب")
# count the chips' own attribute run - the card script's selector also spells role="button"
ck("13 only starters with stats are buttons", html2.count('data-i="') == 2 and html2.count('role="button" tabindex="0"') == 2,
   html2.count('data-i="'))
blob = re.search(r'<script type="application/json" id="ppData">(.*?)</script>', html2, re.S)
data = json.loads(blob.group(1)) if blob else []
striker = next((x for x in data if x["n"] == "مهاجم أ"), {})
ck("14 the card carries name, club, rating and the Arabic stat rows",
   striker.get("team") == "الفريق أ" and striker.get("rt") == "8.1"
   and ["الدقائق", "86′"] in striker.get("st", []) and ["التسديدات (على المرمى)", "2 (1)"] in striker.get("st", []),
   striker)
ck("15 his events in the match: three goals by minute",
   [x[0] for x in striker.get("ev", [])] == ["g", "g", "g"] and striker["ev"][0][1] == "12", striker.get("ev"))
gk = next((x for x in data if x["n"] == "حارس أ"), {})
ck("16 the goalkeeper's saves and goals conceded are on his card",
   ["التصديات", "4"] in gk.get("st", []) and ["أهداف استقبلها", "1"] in gk.get("st", []), gk.get("st"))
ck("17 the card script ships once, and the JSON cannot close its script tag early",
   html2.count("getElementById('ppData')") == 1 and "</" not in blob.group(1))
pre = json.loads(json.dumps(e2)); pre["pre"] = True
ck("18 a pre-match XI (no match played) has no player cards", 'data-i="' not in match_details_html(pre, False, "أ", "ب"))
ck("19 a pitch with no stats at all ships no card script", "ppData" not in html)

print(f"\n{len(fails)} FAILED" if fails else "\nALL OK")
sys.exit(1 if fails else 0)
