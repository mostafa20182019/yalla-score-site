# -*- coding: utf-8 -*-
"""«حسابات التأهل» for a group stage (site review 2026-11-19: «محتاج إيه
للتأهل» - the question every reader of a group table asks).

COMPUTED, never generated, and never possibly-wrong:

  * every result of every remaining match of the group is tried (win / draw /
    loss: 3^k cases, k <= MAX_LEFT);
  * only POINTS are counted. A tie on points is always read AGAINST the side
    the sentence is about, because the tie-breakers (head-to-head, goal
    difference) differ by competition and are not in our data. So:
      «ضمن التأهل»   - in every case fewer than `slots` other sides reach
                        its points or more;
      «خرج»          - in every case at least `slots` other sides finish
                        with MORE points;
      «يضمن التأهل إذا وصل إلى N نقطة» - N is the lowest total from which
                        the first sentence holds in every case.
    A side for which none of the three can be said gets no sentence;
  * the group is skipped whole when our rows do not add up to the table the
    page shows (played / points per side) or the remaining matches are not
    all in the feed - a table we cannot rebuild is a table we do not reason
    about;
  * only competitions listed in QUALIFY, where the number of sides that go
    through from a group is a fixed rule of the competition. The Africa Cup
    qualifiers are NOT here: a host in the group changes the rule.
"""
import itertools
from html import escape as esc

from site_lib.names import ar_team

# competition -> how many go through from each group, and to where
QUALIFY = {
    "CAF Champions League": {"slots": 2, "to": "ربع النهائي"},
    "CAF Confederation Cup": {"slots": 2, "to": "ربع النهائي"},
}
MIN_PLAYED = 3        # before half the group stage every side «needs 13 points»: not information
MAX_LEFT = 8          # 3^8 = 6561 cases a group


def _fin(m):
    st = (m.get("status") or "").upper()
    return (not st or st == "FINISHED") and m.get("home_score") is not None and m.get("away_score") is not None


def group_outlook(table, games, slots):
    """[{team, pts, left, state, need}] for the sides we can say something
    about, in table order; [] when the group cannot be reasoned about.
    state: "in" | "out" | "need" (need = the total that guarantees it)."""
    rows = [r for r in table or [] if r.get("team")]
    names = [ar_team(r["team"]) for r in rows]
    n = len(names)
    if n < 3 or len(set(names)) != n or slots >= n:
        return []
    if min(int(r.get("played") or 0) for r in rows) < MIN_PLAYED:
        return []
    idx = {nm: i for i, nm in enumerate(names)}
    seen, done, left = set(), [], []
    for m in games or []:
        h, a = ar_team(m.get("home") or ""), ar_team(m.get("away") or "")
        if h not in idx or a not in idx or h == a:
            continue
        key = str(m.get("match_id") or (h, a, m.get("kickoff")))
        if key in seen:
            continue
        seen.add(key)
        if _fin(m):
            done.append((idx[h], idx[a], int(m["home_score"]), int(m["away_score"])))
        elif (m.get("status") or "UPCOMING").upper() not in ("CANCELLED",):
            left.append((idx[h], idx[a]))
    # our rows must rebuild the table the page shows
    played, pts = [0] * n, [0] * n
    for h, a, hs, as_ in done:
        played[h] += 1; played[a] += 1
        if hs > as_:
            pts[h] += 3
        elif hs < as_:
            pts[a] += 3
        else:
            pts[h] += 1; pts[a] += 1
    total = 2 * (n - 1)
    rem = [0] * n
    for h, a in left:
        rem[h] += 1; rem[a] += 1
    for i, r in enumerate(rows):
        if played[i] != int(r.get("played") or 0) or pts[i] != int(r.get("pts") or 0) or played[i] + rem[i] != total:
            return []
    if not left:
        return []                      # the group is over: the table itself is the answer
    if len(left) > MAX_LEFT:
        return []
    # every case
    safe_all = [True] * n              # in every case: fewer than `slots` others with pts >= mine
    out_all = [True] * n               # in every case: at least `slots` others with pts > mine
    unsafe_totals = [set() for _ in range(n)]   # totals at which some case is NOT safe
    reach = [set() for _ in range(n)]
    for case in itertools.product((0, 1, 2), repeat=len(left)):
        p = pts[:]
        for (h, a), r in zip(left, case):
            if r == 0:
                p[h] += 3
            elif r == 2:
                p[a] += 3
            else:
                p[h] += 1; p[a] += 1
        for i in range(n):
            ge = sum(1 for j in range(n) if j != i and p[j] >= p[i])
            gt = sum(1 for j in range(n) if j != i and p[j] > p[i])
            reach[i].add(p[i])
            if ge >= slots:
                safe_all[i] = False
                unsafe_totals[i].add(p[i])
            if gt < slots:
                out_all[i] = False
    out = []
    for i, nm in enumerate(names):
        row = {"team": nm, "pts": pts[i], "left": rem[i]}
        if safe_all[i]:
            out.append(dict(row, state="in", need=None))
        elif out_all[i]:
            out.append(dict(row, state="out", need=None))
        else:
            ok = sorted(t for t in reach[i] if t > max(unsafe_totals[i]))
            if ok:
                out.append(dict(row, state="need", need=ok[0]))
    return out


def _pts(n):
    return "نقطة واحدة" if n == 1 else "نقطتين" if n == 2 else f"{n} نقاط" if n <= 10 else f"{n} نقطة"


def _left(n):
    return "مباراة واحدة" if n == 1 else "مباراتان" if n == 2 else f"{n} مباريات"


def line(o, to):
    if o["state"] == "in":
        return f"{o['team']} ضمن التأهل إلى {to}."
    if o["state"] == "out":
        return f"{o['team']} خرج من المنافسة على التأهل."
    return (f"{o['team']} يضمن التأهل إذا وصل إلى {_pts(o['need'])}. "
            f"رصيده {_pts(o['pts']) if o['pts'] else 'صفر'}، وأمامه {_left(o['left'])}.")


def outlook_groups(comp, groups, games):
    """[(group name, [sentence, ...])] for the competition's groups that
    have something to say; [] for a competition outside QUALIFY."""
    rule = QUALIFY.get(comp)
    if not rule:
        return []
    out = []
    for g in groups or []:
        lines = [line(o, rule["to"]) for o in group_outlook(g.get("table"), games, rule["slots"])]
        if lines:
            out.append((g.get("name") or "", lines))
    return out


def outlook_html(comp, label, groups, games):
    """The section under the group tables, "" when there is nothing sure to say."""
    rows = outlook_groups(comp, groups, games)
    if not rows:
        return ""
    rule = QUALIFY[comp]
    two = "أول فريقين" if rule["slots"] == 2 else f"أول {rule['slots']} فرق"
    return ('<section class="minfo qual" id="qual">'
            f'<h2>حسابات التأهل في {esc(label)}</h2>'
            f'<p class="qual-n">يتأهل {two} من كل مجموعة إلى {esc(rule["to"])}. '
            'الحساب بالنقاط فقط على كل نتائج المباريات المتبقية، والتساوي في النقاط لا يُحسب لصالح أي فريق. '
            'لذلك كل جملة هنا مؤكدة، والفريق الذي لا تظهر له جملة مصيره لم يُحسم.</p>'
            + "".join(f'<h3 class="qual-g">{esc(name)}</h3><ul class="qual-l">'
                      + "".join(f"<li>{esc(x)}</li>" for x in lines) + "</ul>"
                      for name, lines in rows)
            + '</section>')
