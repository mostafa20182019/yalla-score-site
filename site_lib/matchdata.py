"""Scores, goals, match details, lineups and the computed match story.

Moved verbatim out of build_site.py (slice 3, 2026-09-25): the source
and its comments are exactly what they were there. Edit here; build_site
imports these back under the same names."""
from site_lib.names import _gnorm, ar_team
from site_lib.stats import _games
from site_lib.text import _lam, _num, esc


def score_pill(hs, aws, cls):
    """A score sitting BETWEEN two team names must put the home number on the
    home side. "1-0" as plain text is one LTR bidi run, so in an RTL row it
    lands home-score-left = next to the AWAY team (reversed). Ordering two
    separate elements inside an RTL flex container fixes it and stays correct
    for two-digit scores, which a bidi-override would scramble.
    (The .score in match rows is fine as-is: its spaces around the hyphen
    already split it into separate runs — measured, don't "tidy" them away.)"""
    h = "-" if hs is None else hs
    a = "-" if aws is None else aws
    return (f'<b class="{cls}"><span>{h}</span><i>-</i><span>{a}</span></b>')


def score_txt(s, cls="sc-in"):
    """Same, for a score already stored as the string "H-A" (a frozen
    prediction, a saved result). A bare "1-2" in a cell of its own is an
    LTR run with no Arabic letter in front of it to turn the digits into
    Arabic numerals, so an RTL reader meets the AWAY number first and reads
    the prediction backwards (user, 2026-09-16)."""
    s = "" if s is None else str(s).strip()
    if "-" not in s:
        return esc(s or "—")
    h, a = s.split("-", 1)
    return score_pill(esc(h.strip()), esc(a.strip()), cls)


def goal_events_index(goal_events):
    """(normalized home|away, date) -> goals. Names in the feed are 365scores
    Arabic — the same spellings AR_TEAM maps the football-data names to."""
    idx = {}
    for e in goal_events:
        if e.get("goals"):
            idx[(f'{_gnorm(e.get("home"))}|{_gnorm(e.get("away"))}', e.get("date"))] = e["goals"]
    return idx


def match_goals(idx, m):
    """Scorer lines for a match row — FINISHED only.

    A live match used to get them too, and that quietly broke the rule the
    dashes exist for. The user saw «مالقا - - - فياريال» with one goal listed
    at 12': the score was hidden as possibly-stale while the goal list, which
    is exactly as stale, implied 1-0. It was 1-1 — the second goal had arrived
    after the last build. Publishing half the picture is worse than publishing
    none of it, so a live match now shows nothing until LIVE_JS paints the
    score AND the goals together from /live.json, which carries both.
    """
    if (m.get("status") or "").upper() != "FINISHED":
        return None
    h, a = _gnorm(ar_team(m.get("home"))), _gnorm(ar_team(m.get("away")))
    g = idx.get((f"{h}|{a}", m.get("kickoff")))
    if g is None:
        # the two sources can disagree on who is at home (2026-08-23:
        # football-data said PSG x Rennes, 365scores said Rennes x PSG and
        # the scorers silently vanished) — try the reversed pair and flip
        # each goal's side so scorers stay under the right club
        rg = idx.get((f"{a}|{h}", m.get("kickoff")))
        if rg is not None:
            g = [{**x, "side": "a" if x.get("side") == "h" else "h"}
                 for x in rg]
    return g


def frozen_scores_index(entries):
    """(normalized home|away, date) -> (home_score, away_score), from the frozen
    archive. Keyed by NAMES and date like the scorer index above, not by
    match_id: the site's matches come from football-data for the European
    leagues and its ids are not 365scores ids, which is the same reason
    goal_events_index exists in this shape."""
    idx = {}
    for e in entries:
        if e.get("hs") is not None and e.get("as") is not None:
            idx[(f'{_gnorm(e.get("home"))}|{_gnorm(e.get("away"))}',
                 e.get("date"))] = (e["hs"], e["as"])
    return idx


def apply_frozen_scores(matches, idx):
    """Overlay the frozen score onto every FINISHED match the archive owns.

    The archive wins here, which is the point of freezing. It should never actually differ - both numbers
    come from the same feed and a finished match does not get corrected - so
    any disagreement is worth seeing rather than hiding, and the count is
    printed in the build log. Matches the archive does not hold keep the site's
    own number, so nothing can go blank.

    Returns (filled, changed): rows taken from the archive, and how many of
    those carried a different score than the site had."""
    filled = changed = 0
    for m in matches:
        if (m.get("status") or "").upper() != "FINISHED":
            continue
        h, a = _gnorm(ar_team(m.get("home"))), _gnorm(ar_team(m.get("away")))
        hit, flip = idx.get((f"{h}|{a}", m.get("kickoff"))), False
        if hit is None:
            # same reversed-pair fallback the scorers use: the two sources can
            # disagree on who was at home
            hit, flip = idx.get((f"{a}|{h}", m.get("kickoff"))), True
        if hit is None:
            continue
        hs, asc = (hit[1], hit[0]) if flip else hit
        if m.get("home_score") != hs or m.get("away_score") != asc:
            changed += 1
        m["home_score"], m["away_score"] = hs, asc
        filled += 1
    return filled, changed


def match_details_index(entries):
    """Same keying as goal_events_index, but keeps the whole entry
    (goals + cards + subs + lineups) for the /m/ match pages."""
    idx = {}
    for e in entries:
        idx[(f'{_gnorm(e.get("home"))}|{_gnorm(e.get("away"))}',
             e.get("date"))] = e
    return idx


def prematch_for(idx, m):
    """(entry, flipped) for an UPCOMING match whose XI is already announced
    (fetch_data stores those with pre=True from ~1h before kick-off), else
    None. Same reversed-pair fallback as match_details_for."""
    if (m.get("status") or "").upper() != "UPCOMING":
        return None
    h, a = _gnorm(ar_team(m.get("home"))), _gnorm(ar_team(m.get("away")))
    for key, flip in ((f"{h}|{a}", False), (f"{a}|{h}", True)):
        e = idx.get((key, m.get("kickoff")))
        if e is not None and ((e.get("lineups") or {}).get("h", {}).get("xi")
                              or (e.get("lineups") or {}).get("a", {}).get("xi")):
            return e, flip
    return None


def absence_block(squad, comp, m, h_ar, a_ar):
    """«الغائبون عن التشكيل المعتاد» — presented as FACTS, not as a probability
    adjustment. The prediction model deliberately ignores this for now: on the
    25 matches it moves, the absence factor improved brier by 0.013 while the
    noise band at that sample is ±0.18 (backtest.py, 2026-09-06), so moving the
    numbers would be dressing up noise. Naming who is missing needs no such
    proof — it is simply what the announced XI says."""
    if squad is None or not comp:
        return ""
    out = []
    for club_raw, label in ((m.get("home"), h_ar), (m.get("away"), a_ar)):
        club = ar_team(club_raw)
        r = squad.report(comp, club, m.get("kickoff"))
        if not r or not (r["missing"] or r["back"]):
            continue
        bits = []
        if r["missing"]:
            bits.append('<p><b>غائبون عن التشكيل المعتاد:</b> ' + '، '.join(
                f'<bdi>{esc(x["name"])}</bdi>'
                + (f' <small>(أساسي في {x["starts"]} من {_games(x["of"])}'
                   + (f'، متوسط تقييمه {x["avg"]:.1f}' if x.get("avg") else '') + ')</small>')
                for x in r["missing"][:5]) + '</p>')
        if r["back"]:
            bits.append('<p><b>عائدون للتشكيل:</b> ' + '، '.join(
                f'<bdi>{esc(x["name"])}</bdi>' for x in r["back"][:5]) + '</p>')
        out.append(f'<div class="abs-club"><h3>{esc(label)}</h3>' + "".join(bits) + '</div>')
    if not out:
        return ""
    _up = (m.get("status") or "").upper() == "UPCOMING"
    _h2 = "التشكيل المعلن — من غاب ومن عاد" if _up else "من غاب عن التشكيل المعتاد"
    return (f'<section class="minfo absences"><h2>{_h2}</h2>'
            + "".join(out)
            + '<p class="pd-note">«التشكيل المعتاد» يُحسب من التشكيلات السابقة لكل فريق هذا '
              'الموسم: من بدأ 60% منها فأكثر. الغياب هنا واقعة من التشكيل المعلن، وقد يكون '
              'سببه إصابة أو إيقافًا أو قرارًا فنيًا — لا نخمّن السبب، ولا تدخل هذه المعلومة '
              'في حساب <a href="/analysis.html#model">التوقع</a> حتى تثبت فائدتها بالأرقام.</p>'
            '</section>')


def match_details_for(idx, m):
    """(entry, flipped) for a FINISHED/LIVE match, else None — with the
    same reversed-pair fallback as match_goals (sources can disagree on
    who is at home)."""
    if (m.get("status") or "").upper() not in ("FINISHED", "LIVE"):
        return None
    h, a = _gnorm(ar_team(m.get("home"))), _gnorm(ar_team(m.get("away")))
    e = idx.get((f"{h}|{a}", m.get("kickoff")))
    if e is not None:
        return e, False
    e = idx.get((f"{a}|{h}", m.get("kickoff")))
    if e is not None:
        return e, True
    return None


def _min_key(mn):
    """'45+2' -> 45.02 for chronological event sorting."""
    try:
        base, _, add = (mn or "").partition("+")
        return int(base) + int(add or 0) / 100.0
    except ValueError:
        return 0.0


def _pshort(name):
    """Pitch-chip name: surname only when the full name is long."""
    w = (name or "").split()
    return name if len(name or "") <= 9 or len(w) == 1 else w[-1]


def _athlete_img(p):
    """365scores athlete headshot URL (mirrored locally via local_crest)."""
    aid = p.get("aid")
    if not aid:
        return None
    try:
        v = f"v{int(p['iv'])}/" if p.get("iv") else ""
    except (TypeError, ValueError):
        v = ""
    return ("https://imagecache.365scores.com/image/upload/"
            "f_png,w_68,h_68,c_limit,q_auto:eco,dpr_2,d_Athletes:default.png/"
            f"{v}Athletes/{aid}")


def _pitch_rows(lu, top):
    """[(x%, y%, player)] for one team's XI, or None when the feed has no
    formation lines. Home (top=True) attacks downward: GK on line 1 sits
    nearest its own goal (top edge); away is mirrored from the bottom."""
    xi = (lu or {}).get("xi") or []
    if sum(1 for p in xi if p.get("ln")) < 8:
        return None
    lines = {}
    for p in xi:
        lines.setdefault(p.get("ln") or 99, []).append(p)
    rows = [lines[k] for k in sorted(lines)]
    n = len(rows)
    out = []
    for i, row in enumerate(rows):
        frac = i / (n - 1) if n > 1 else 0.0
        y = 6 + 38 * frac if top else 94 - 38 * frac
        row.sort(key=lambda p: (p.get("sd") if p.get("sd") is not None else 50))
        if not top:
            row.reverse()               # mirror left/right for the away half
        for j, p in enumerate(row):
            out.append(((j + 0.5) / len(row) * 100, y, p))
    return out


def _rt_class(rt):
    try:
        r = float(rt)
    except (TypeError, ValueError):
        return None
    return "r8" if r >= 8 else "r7" if r >= 7 else "r65" if r >= 6.5 else "r6"


def _played_names(e, flipped, side_key):
    """Names that were ON THE PITCH for one side: the XI plus everyone involved
    in a substitution. Used to tell a sent-off player from a sent-off manager."""
    sd = _side_of(flipped)
    lus = e.get("lineups") or {}
    feed_key = ("a" if side_key == "h" else "h") if flipped else side_key
    names = {(p.get("name") or "").strip()
             for p in ((lus.get(feed_key) or {}).get("xi") or []) if p.get("name")}
    for sub in (e.get("subs") or []):
        if sd(sub.get("side")) == side_key:
            names.update(x.strip() for x in (sub.get("in"), sub.get("out")) if x)
    return names


def _side_of(flipped):
    """The details entry stores sides as the FEED saw them; `flipped` means the
    feed's home is our away (the two sources disagree on who is at home)."""
    return (lambda s: ("a" if s == "h" else "h")) if flipped else (lambda s: s)


def match_story(e, flipped, h_ar, a_ar, hs, as_):
    """The sentences a reader wants under the score: who opened, who turned it
    around, which goal settled it, what the sending-off did. Returns a list of
    plain-text sentences (the caller escapes them)."""
    sd = _side_of(flipped)
    nm = {"h": h_ar, "a": a_ar}
    goals = [{"k": _min_key(g.get("minute")), "s": sd(g.get("side")),
              "m": (g.get("minute") or "").strip(), "p": (g.get("player") or "").strip(),
              "t": g.get("tag") or ""}
             for g in (e.get("goals") or [])]
    timed = sorted([g for g in goals if g["k"] > 0 and g["s"] in ("h", "a")],
                   key=lambda g: g["k"])
    reds = sorted([{"k": _min_key(c.get("minute")), "s": sd(c.get("side")),
                    "m": (c.get("minute") or "").strip(),
                    "p": (c.get("player") or "").strip()}
                   for c in (e.get("cards") or []) if c.get("color") == "r"],
                  key=lambda c: c["k"])
    winner = "h" if (hs or 0) > (as_ or 0) else "a" if (as_ or 0) > (hs or 0) else None
    other = {"h": "a", "a": "h"}
    out = []

    if not (hs or 0) and not (as_ or 0):
        out.append(f"انتهت المباراة بالتعادل السلبي دون أهداف بين {h_ar} و{a_ar}.")
    elif timed:
        g0 = timed[0]
        if "عكس" in g0["t"]:
            out.append(f"تقدّم {nm[g0['s']]} بهدف عكسي سجله {g0['p']} في الدقيقة {g0['m']}.")
        else:
            pen = " من ركلة جزاء" if "ج" in g0["t"] else ""
            out.append(f"افتتح {g0['p']} التسجيل {_lam(nm[g0['s']])}{pen} في الدقيقة {g0['m']}.")

    # the running score: who led, who came back, which goal settled it
    run = {"h": 0, "a": 0}
    hist = []
    for g in timed:
        run[g["s"]] += 1
        lead = "h" if run["h"] > run["a"] else "a" if run["a"] > run["h"] else None
        hist.append((g, lead))
    first_lead = next((l for _, l in hist if l), None)
    if winner and first_lead and first_lead != winner:
        out.append(f"قلب {nm[winner]} تأخره أمام {nm[other[winner]]} وحسم اللقاء "
                   f"{max(hs, as_)}-{min(hs, as_)}.")
    elif not winner and first_lead and timed:
        out.append(f"أدرك {nm[other[first_lead]]} التعادل بعد تأخره أمام {nm[first_lead]}.")

    if winner and len(timed) > 1:
        dec, prev = None, None
        for g, lead in hist:
            if lead == winner and prev != winner:
                dec = g
            prev = lead
        if dec is timed[0]:
            dec = None          # already told: the opener was never caught
        if dec:
            if dec["k"] >= 80:
                out.append(f"وجاء هدف الحسم متأخرًا عبر {dec['p']} في الدقيقة {dec['m']}.")
            else:
                out.append(f"وجاء هدف الحسم عبر {dec['p']} في الدقيقة {dec['m']}.")

    # a player with more than one goal
    tally = {}
    for g in goals:
        if g["p"] and "عكس" not in g["t"] and g["s"] in ("h", "a"):
            tally[(g["p"], g["s"])] = tally.get((g["p"], g["s"]), 0) + 1
    for (pl, sside), n in sorted(tally.items(), key=lambda kv: -kv[1]):
        if n >= 3:
            out.append(f"سجّل {pl} ثلاثية كاملة مع {nm[sside]}.")
            break
        if n == 2:
            out.append(f"سجّل {pl} هدفين {_lam(nm[sside])}.")
            break

    if reds:
        r = reds[0]
        if r["s"] in ("h", "a"):
            # a red card is shown to managers and bench staff too (Neom x
            # Al-Fateh 2026: Christophe Galtier). Their name is not in the XI
            # or the substitutions, and their dismissal does NOT leave the team
            # a man short - so the ten-men sentence needs proof, not a guess.
            played = _played_names(e, flipped, r["s"])
            n_off = sum(1 for x in reds
                        if x["s"] == r["s"] and x["p"] in played)
            if r["p"] in played:
                short = {1: "بعشرة لاعبين", 2: "بتسعة لاعبين"}.get(n_off, "منقوص العدد")
                line = (f"أكمل {nm[r['s']]} المباراة {short} بعد طرد {r['p']} "
                        f"في الدقيقة {r['m']}")
                if winner == r["s"]:
                    line += "، وخرج فائزًا رغم النقص العددي."
                elif winner is None:
                    line += "، ونجح في الخروج بالتعادل رغم النقص العددي."
                else:
                    line += "."
            else:
                line = f"وتلقى {r['p']} بطاقة حمراء في الدقيقة {r['m']}."
            out.append(line)

    if winner and not (as_ if winner == "h" else hs):
        out.append(f"وحافظ {nm[winner]} على نظافة شباكه.")

    if len(timed) >= 3:
        if all(g["k"] >= 60 for g in timed):
            out.append("كل أهداف اللقاء جاءت في الثلث الأخير من زمن المباراة.")
        elif all(g["k"] <= 45 for g in timed):
            out.append("كل أهداف اللقاء جاءت في الشوط الأول.")
    return out[:6]


def match_ratings(e, flipped, h_ar, a_ar):
    """{best, best_other, low, sides} from the XI ratings the feed already
    gives us, or None when either XI is not fully rated (an incomplete set
    would name a 'best player' out of half a team)."""
    lus = e.get("lineups") or {}
    eh, ea = ("a", "h") if flipped else ("h", "a")
    sides = []
    for key, name in ((eh, h_ar), (ea, a_ar)):
        xi = ((lus.get(key) or {}).get("xi")) or []
        rated = [{"name": (p.get("name") or "").strip(), "rt": _num(p.get("rt")),
                  "club": name}
                 for p in xi if _num(p.get("rt")) and p.get("name")]
        if len(rated) < 8:
            return None
        sides.append({"club": name, "players": rated,
                      "avg": round(sum(p["rt"] for p in rated) / len(rated), 1)})
    everyone = sides[0]["players"] + sides[1]["players"]
    best = max(everyone, key=lambda p: p["rt"])
    other = [p for p in everyone if p["club"] != best["club"]]
    return {"best": best,
            "best_other": max(other, key=lambda p: p["rt"]) if other else None,
            "low": min(everyone, key=lambda p: p["rt"]),
            "sides": sides}
