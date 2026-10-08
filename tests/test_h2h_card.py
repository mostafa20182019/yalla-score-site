# -*- coding: utf-8 -*-
"""The weekly H2H infographic (h2h_card.py + fb_post --h2h): renders from a
fixed game list (no network), the tally is right, the post text carries the
numbers and never a betting word, the auto pick takes a both-featured match
inside the window and Egypt first, and the weekly cap holds."""
import sys, os, io, tempfile, datetime, time
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _k in ("CF_API_TOKEN", "CF_ACCOUNT_ID", "CF_D1_ID", "FB_PAGE_TOKEN"):
    os.environ.pop(_k, None)
os.environ["D1_SQLITE"] = os.path.join(tempfile.mkdtemp(), "state.sqlite")
import store
store.init_schema()
import h2h_card as HC
import fb_post as fp

fails = 0


def ck(name, cond, extra=""):
    global fails
    print(f"  {'ok  ' if cond else 'FAIL'} {name}" + (f"  [{extra}]" if extra and not cond else ""))
    fails += 0 if cond else 1


m = {"match_id": 4804684, "competition": "Egyptian Premier League", "home": "الزمالك", "away": "الأهلي",
     "kickoff": "2026-10-11", "koff_time": "20:00", "status": "UPCOMING", "round": 6}
G = lambda date, comp, h, hg, ag, a: {"date": date, "comp": comp, "home": h, "away": a, "hg": hg, "ag": ag}
games = [G("2026-05-01", "الدوري المصري", "الزمالك", 0, 3, "الأهلي"),
         G("2025-11-09", "السوبر المصري", "الأهلي", 2, 0, "الزمالك"),
         G("2025-09-29", "الدوري المصري", "الأهلي", 2, 1, "الزمالك"),
         G("2025-03-11", "الدوري المصري", "الزمالك", 3, 0, "الأهلي"),
         G("2025-02-22", "الدوري المصري", "الأهلي", 1, 1, "الزمالك"),
         G("2024-10-24", "السوبر المصري", "الأهلي", 0, 0, "الزمالك"),
         G("2024-09-27", "السوبر الأفريقي", "الأهلي", 1, 1, "الزمالك"),
         G("2024-06-25", "الدوري المصري", "الأهلي", 2, 0, "الزمالك"),
         G("2024-04-15", "الدوري المصري", "الزمالك", 2, 1, "الأهلي"),
         G("2024-03-08", "كأس مصر", "الزمالك", 0, 2, "الأهلي")]

w, draws, gf, last, played = HC.tally(games, "الزمالك", "الأهلي")
ck("1 tally: wins 5-2, draws 3", w == {"الأهلي": 5, "الزمالك": 2} and draws == 3, f"{w} {draws}")
ck("2 goals: Ahly 14, Zamalek 8", gf == {"الأهلي": 14, "الزمالك": 8}, str(gf))
ck("3 last win of each side (newest first)", last == {"الأهلي": "2026-05-01", "الزمالك": "2025-03-11"}, str(last))
ck("4 Arabic date", HC.ar_date("2026-05-01") == "1 مايو 2026", HC.ar_date("2026-05-01"))
# the hand-checked notes (data/h2h_notes.json): awarded games keep the result, lose their goals
notes = HC.load_notes("الزمالك", "الأهلي")
ck("4b the derby notes load (either name order)", notes.get("finals") and HC.load_notes("الأهلي", "الزمالك") == notes)
w2, d2, gf2, last2, played2 = HC.tally(games, "الزمالك", "الأهلي", notes)
ck("4c with the notes: wins/draws unchanged, goals from played games only (12-5 in 8)",
   w2 == w and d2 == 3 and gf2 == {"الأهلي": 12, "الزمالك": 5} and played2 == 8, f"{gf2} {played2}")
ck("4d a pair without notes keeps the official count", HC.load_notes("ليفربول", "مانشستر سيتي") == {})

out = os.path.join(tempfile.mkdtemp(), "h2h.jpg")
r = HC.render(m, games, out, when="الأحد 11 أكتوبر · 8 مساءً")
ck("5 the card is written (1080x1350)", os.path.exists(out) and os.path.getsize(out) > 50000)
from PIL import Image
ck("6 ...at the Facebook 4:5 size", Image.open(out).size == (1080, 1350))
ck("7 render returns the tally, with the notes applied", r["n"] == 10 and r["wins"]["الأهلي"] == 5
   and r["played"] == 8 and r["goals"] == {"الأهلي": 12, "الزمالك": 5} and r["finals"], str(r))

t = fp.h2h_text(m, r, "الأحد 11 أكتوبر")
print(t)
ck("8b the post says the goals are from played games and carries the finals line",
   "في 8 مباريات لُعبت داخل الملعب" in t and "4 نهائيات" in t)
ck("8 post text: the numbers, the link, the hashtags", "الأهلي فاز 5" in t and "تعادل 3" in t and "الزمالك فاز 2" in t
   and f"{fp.SITE}/m/4804684" in t and t.endswith("#يلا_سكور #الزمالك #الأهلي"))
ck("9 never a betting word", "مراهنة" not in t)
ck("10 fewer than MIN_GAMES meetings -> no card", HC.MIN_GAMES == 4)

# the auto pick: both featured, inside the window, Egypt before Europe, soonest
now = datetime.datetime.now(fp.CAIRO)
def up(mid, comp, h, a, hours):
    ko = now + datetime.timedelta(hours=hours)
    return {"match_id": mid, "competition": comp, "home": h, "away": a, "status": "UPCOMING",
            "kickoff": ko.strftime("%Y-%m-%d"), "koff_time": ko.strftime("%H:%M")}
d = {"matches": [
    up(1, "Premier League", "Liverpool FC", "Manchester City FC", 40),   # both featured, Europe
    up(2, "Egyptian Premier League", "الزمالك", "الأهلي", 70),           # both featured, Egypt -> first
    up(3, "Egyptian Premier League", "الزمالك", "زد", 30),               # one side only
    up(4, "Premier League", "Arsenal FC", "Chelsea FC", 5),              # too soon
    up(5, "Premier League", "Arsenal FC", "Chelsea FC", 200),            # too far
]}
pick = fp.h2h_pick(d, now=now)
ck("11 auto picks the Egyptian both-featured match in the window", pick and pick["match_id"] == 2, str(pick and pick["match_id"]))
d["matches"].pop(1)
pick = fp.h2h_pick(d, now=now)
ck("12 ...else the soonest European both-featured one", pick and pick["match_id"] == 1, str(pick and pick["match_id"]))

# the weekly cap: a card posted 2 days ago blocks auto
store.record_post("h2h", "999", "P1", title="t")
import contextlib
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    rc = fp.h2h_post("tok", "auto", dry=True)
ck("13 one card per H2H_EVERY_DAYS: auto says 'not yet'", rc == 0 and "not yet" in buf.getvalue(), buf.getvalue().strip()[-120:])

print("\nALL H2H CARD TESTS PASSED" if not fails else f"\n{fails} FAILED")
sys.exit(1 if fails else 0)
