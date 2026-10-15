# -*- coding: utf-8 -*-
r"""Result card: every goal shows, whatever the score (2026-10-15).

    python tests/test_card_scorers.py     (from the repo root)

LASK 3-6 Liverpool: the card listed four of Liverpool's goals and the fourth
sat on the panel's edge. Two fixes under test: goals are grouped per scorer
(a hat-trick is one row with three minutes), and the layout tightens crest /
font / line height until the busier side fits above the panel's bottom.
No network, no real data.
"""
import os, sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.getcwd())
import fb_cards as F

fails = []
def ck(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  [{extra}]" if extra else ""))
    if not cond:
        fails.append(name)

def goal(side, player, minute, tag=None):
    g = {"side": side, "player": player, "minute": minute}
    if tag:
        g["tag"] = tag
    return g

# ------------------------------------------------------------- grouping
lask = [goal("a", "رونالد  أراوخو", 22), goal("a", "برادلي باركولا", 24), goal("a", "برادلي باركولا", 37),
        goal("a", "جيريمي فريمبونج", 51), goal("h", "روبرت ليوبيسيتش", 63), goal("a", "برادلي باركولا", 66),
        goal("a", "لويس كوماس", 72), goal("h", "فلوريان فليكر", 74), goal("h", "فلوريان فليكر", 77)]
rows = F.group_goals(lask)
away = [t for s, t in rows if s == "a"]
home = [t for s, t in rows if s == "h"]
ck("1a nine goals become four away rows and two home rows", (len(away), len(home)) == (4, 2), str(rows))
ck("1b a hat-trick is one row with its three minutes", "برادلي باركولا 24' 37' 66'" in away)
ck("1c rows keep the order of each scorer's FIRST goal", away[0].startswith("رونالد") and away[1].startswith("برادلي") and away[-1].startswith("لويس"))
ck("1d doubled spaces in the feed are collapsed", away[0] == "رونالد أراوخو 22'")
ck("1e a tag rides with its minute", F.group_goals([goal("h", "زيزو", 12, "ق.ج"), goal("h", "زيزو", 80)])[0][1] == "زيزو 12' (ق.ج) 80'")
ck("1f a goal with no minute still lists the scorer", F.group_goals([{"side": "h", "player": "زيزو"}])[0][1] == "زيزو")

# ------------------------------------------------------------- the layout
PANEL_TOP, PANEL_BOTTOM = 118 + 36, 630 - 96
def fits(n):
    rows = [("a", f"لاعب {i}") for i in range(n)]
    crest, fs, lh, y0, max_rows = F.layout_for(rows, PANEL_TOP, PANEL_BOTTOM)
    drawn = min(n, max_rows)
    return crest, fs, lh, y0 + drawn * lh <= PANEL_BOTTOM - 12, max_rows

for n in range(0, 10):
    crest, fs, lh, inside, max_rows = fits(n)
    ck(f"2 {n} scorer rows end inside the panel (crest {crest}, font {fs}, line {lh}, max {max_rows})", inside)
ck("2x three rows keep the roomy layout", fits(3)[0] == 170)
ck("2y four rows (the LASK case) tighten instead of clipping", fits(4)[0] < 170 and fits(4)[4] >= 4)

# ------------------------------------------------------------- the render
m = {"home": "LASK Linz", "away": "Liverpool FC", "home_score": 3, "away_score": 6,
     "kickoff": "2026-10-14", "competition": "UEFA Champions League"}
F.b.match_goals = lambda ge, mm: lask          # no goal index, no network
im = F.render_card(m, {})
ck("3a the card renders at its size", im.size == (F.W, F.H))
# nothing dark may be drawn on the blue band under the panel (that band is
# where the clipped fourth row used to land)
band = im.crop((300, F.H - 96 + 2, F.W - 300, F.H - 80))
dark = sum(1 for px in band.getdata() if sum(px) < 200)
ck("3b no scorer ink spills below the panel", dark == 0, f"{dark} dark pixels")
# and the panel's lower part does carry text now (the rows that used to be lost)
low = im.crop((48, F.H - 96 - 40, F.W - 48, F.H - 96 - 4))
ink = sum(1 for px in low.getdata() if sum(px) < 200)
ck("3c the last rows are drawn inside the panel", ink > 50, f"{ink} ink pixels")

print()
print("ALL OK" if not fails else f"{len(fails)} FAILED: " + ", ".join(fails))
sys.exit(1 if fails else 0)
