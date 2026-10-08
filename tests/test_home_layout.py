r"""Home option «أ» (2026-10-08) - the match-centre row and the block order.

    python tests/test_home_layout.py   (from the repo root)

Pins: the top row shows only predicted matches inside the next 7 days; a match
of two featured clubs comes first, then an Egyptian match of a featured club,
then kickoff; the analysis block leads with the HOME_PIN article while the pin
is on; the page order is matches -> analyses -> record -> news.
"""
import datetime
import io
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())
fails = []


def ck(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  [{extra}]" if extra else ""))
    if not cond:
        fails.append(name)


from site_lib import cards as C                            # noqa: E402

today = datetime.date(2026, 10, 8)
focus = {"Egyptian Premier League": ("الزمالك", "الأهلي", "المصري"),
         "Premier League": ("ليفربول", "مانشستر سيتي", "أرسنال")}
C.ar_team = lambda n: n                                    # names are already Arabic here
C._is_ticker_team = lambda m: False


def M(i, comp, h, a, day):
    return {"match_id": i, "competition": comp, "home": h, "away": a,
            "kickoff": f"2026-10-{day:02d}", "koff_time": "20:00"}


P = {"ph": .4, "pd": .3, "pa": .3, "conf": "mid", "top": [(1, 1, .1)]}
up = [M(1, "Premier League", "برايتون", "أرسنال", 9),          # one featured, earliest
      M(2, "Premier League", "ليفربول", "مانشستر سيتي", 11),   # both featured
      M(3, "Egyptian Premier League", "المصري", "سموحة", 10),  # Egyptian, one featured
      M(4, "Egyptian Premier League", "الزمالك", "الأهلي", 20),  # both featured but > 7 days
      M(5, "Premier League", "أرسنال", "ليفربول", 12),         # both featured, no prediction
      M(6, "Premier League", "فولهام", "برنتفورد", 9)]         # nobody featured
preds = {str(i): P for i in (1, 2, 3, 4, 6)}
got = [m["match_id"] for m, _ in C.match_focus_pick(up, preds, today, focus, n=4)]
ck("both featured first, then Egypt, then one featured, then the rest",
   got == [2, 3, 1, 6], got)
ck("nothing beyond 7 days, nothing without a prediction", 4 not in got and 5 not in got)
ck("an empty pick renders nothing", C.match_focus_block([], {}, today, focus) == "")

arts = [{"article_id": "9", "title": "news"},
        {"article_id": "8", "title": "a", "kind": "analysis"},
        {"article_id": "7", "title": "b", "kind": "analysis"}]
lead, rest = C.home_insights(arts, pinned=False)
ck("no pin: the newest analysis leads", lead["article_id"] == "8" and [a["article_id"] for a in rest] == ["7"])
lead, rest = C.home_insights(arts, pinned=True)
ck("pin on: the pinned (first) article leads", lead["article_id"] == "9" and len(rest) == 2)

src = io.open("site_pages/home.py", encoding="utf-8").read()
order = [src.index(s) for s in ("match_focus_block(", "home_insights(articles", "home_record_strip(",
                                 '"hn-grid"', "news_cols(")]
ck("page order: matches -> analyses -> record -> news -> Egypt|Europe", order == sorted(order), order)

print(f"\n{len(fails)} failed" if fails else "\nall passed")
sys.exit(1 if fails else 0)
