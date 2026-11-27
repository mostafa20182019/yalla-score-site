# -*- coding: utf-8 -*-
"""A league round as its own page: /fixtures/<slug>/round-N.

WHY (SEO review 2026-11-26; user 2026-11-27: «اعمل صفحة لكل جولة في الدوري
المصري»): /fixtures/egypt holds every round in one URL behind a round
picker, while people ask for ONE round - «مواعيد مباريات الجولة 10 من الدوري
المصري», «نتائج الجولة 9». A round's page answers that in its title, its
first sentence and its rows.

Everything here is computed from the round's own matches (fixtures.json,
freshened from the day's pool by the caller); nothing is judged. Pure
functions; site_pages/rounds.py writes the pages.
"""
from site_lib.competitions import COMP_SLUG, COMP_TV
from site_lib.dates import fmt_day
from site_lib.names import ar_team_in, comp_label
from site_lib.stats import _cnt
from site_lib.tables import relisted, round_on_show

# the leagues that get a page a round. One line to add a league.
ROUND_COMPS = ("Egyptian Premier League", "Saudi Pro League")
TITLE_MAX = 62           # seo_title's own limit


def round_url(comp, n):
    return f"/fixtures/{COMP_SLUG[comp]}/round-{int(n)}.html"


def numbered(fx):
    """[(n, matches)] of the rounds that carry a whole number (a cup's stage
    has a label, not a number, and gets no page), in order. A postponed row
    the feed listed again on a new date (tables.relisted) is left out: the
    match is the round's once, on the date it will be played."""
    out = []
    ghost = relisted(fx)
    for r in (fx or {}).get("rounds") or []:
        n = r.get("round")
        ms = [m for m in r.get("matches") or [] if m.get("match_id") not in ghost]
        if isinstance(n, int) and not r.get("label") and ms:
            out.append((n, ms))
    return sorted(out, key=lambda x: x[0])


def _st(m):
    return (m.get("status") or "").upper()


def _counts(ms):
    """Postponed matches are still the round's, but they do not hold it open."""
    live = [m for m in ms if _st(m) not in ("POSTPONED", "CANCELLED", "CANCELED")]
    done = [m for m in live if _st(m) == "FINISHED" and m.get("home_score") is not None]
    return live, done


def state(ms):
    """'coming' (nothing played) / 'on' (some played, some to play) /
    'done' (every match that is not postponed is played)."""
    live, done = _counts(ms)
    if not done:
        return "coming"
    return "done" if len(done) == len(live) else "on"


def is_latest(fx, n):
    """True when no LATER round has a match played or in play - only then is
    the table of today «the table after round n»."""
    for k, ms in numbered(fx):
        if k > n and any(_st(m) in ("FINISHED", "LIVE") for m in ms):
            return False
    return True


def window(fx):
    """The rounds worth advertising (the sitemap): the one on show, the one
    before it and the one after it."""
    ns = [k for k, _ in numbered(fx)]
    cur = round_on_show(fx)[0]
    if cur not in ns:
        cur = (fx or {}).get("current") if (fx or {}).get("current") in ns else (ns[-1] if ns else None)
    return [k for k in (cur - 1, cur, cur + 1) if k in ns] if cur is not None else []


def indexable(fx, n, ms):
    """A played round is content for good; a round to come is content only
    inside the window (a date weeks away is a thin page)."""
    return state(ms) != "coming" or n in window(fx)


def title(comp, n, ms, latest):
    label, st = comp_label(comp), state(ms)
    if st == "coming":
        opts = (f"مواعيد مباريات الجولة {n} من {label} والقنوات الناقلة", f"مواعيد مباريات الجولة {n} من {label}")
    elif st == "on":
        opts = (f"نتائج الجولة {n} من {label} والمباريات المتبقية", f"نتائج الجولة {n} من {label}")
    elif latest:
        opts = (f"نتائج الجولة {n} من {label} وترتيب الدوري بعدها", f"نتائج الجولة {n} من {label}")
    else:
        opts = (f"نتائج الجولة {n} من {label}: كل المباريات والأهداف", f"نتائج الجولة {n} من {label}")
    return next((t for t in opts if len(t) <= TITLE_MAX), opts[-1])


def _span(ms):
    ds = sorted(m["kickoff"][:10] for m in ms if m.get("kickoff"))
    return (ds[0], ds[-1]) if ds else (None, None)


def intro(comp, n, ms):
    """One or two computed sentences: when the round is played, how much of
    it is done, how many goals."""
    label = comp_label(comp)
    live, done = _counts(ms)
    d1, d2 = _span(live or ms)
    n_txt = _cnt(len(live), "مباراة واحدة", "مباراتان", "مباريات", "مباراة")
    when = (f"يوم {fmt_day(d1)}" if d1 == d2 else f"من {fmt_day(d1)} إلى {fmt_day(d2)}") if d1 else ""
    st = state(ms)
    goals = sum(int(m["home_score"]) + int(m["away_score"]) for m in done)
    g_txt = _cnt(goals, "هدف واحد", "هدفان", "أهداف", "هدفًا")
    if st == "coming":
        out = f"تقام الجولة {n} من {label} {when}: {n_txt}."
    elif st == "on":
        left = len(live) - len(done)
        out = (f"لُعبت {_cnt(len(done), 'مباراة واحدة', 'مباراتان', 'مباريات', 'مباراة')} من الجولة {n} من {label} "
               f"وبقيت {_cnt(left, 'مباراة واحدة', 'مباراتان', 'مباريات', 'مباراة')}. "
               f"سُجل {g_txt} حتى الآن." if goals else
               f"لُعبت {_cnt(len(done), 'مباراة واحدة', 'مباراتان', 'مباريات', 'مباراة')} من الجولة {n} من {label} "
               f"وبقيت {_cnt(left, 'مباراة واحدة', 'مباراتان', 'مباريات', 'مباراة')}.")
    else:
        out = (f"انتهت الجولة {n} من {label} ({when}): {n_txt}. " + (f"سُجل فيها {g_txt}." if goals else "لم يُسجل فيها أي هدف."))
    post = len(ms) - len(live)
    if post:
        out += " " + _cnt(post, "مباراة واحدة مؤجلة", "مباراتان مؤجلتان", "مباريات مؤجلة", "مباراة مؤجلة") + " من الجولة."
    return out


def faq(comp, n, ms):
    """[(q, a)] - the dates of what is still to play, the results of what is
    played, the broadcaster. From the rows the page shows."""
    label = comp_label(comp)
    live, done = _counts(ms)
    todo = sorted((m for m in live if m not in done and m.get("kickoff")),
                  key=lambda m: (m["kickoff"], m.get("koff_time") or ""))
    out = []
    if todo:
        d1, d2 = todo[0]["kickoff"][:10], todo[-1]["kickoff"][:10]
        q = f"متى مباريات الجولة {n} من {label}؟" if not done else f"متى المباريات المتبقية من الجولة {n} من {label}؟"
        out.append((q, f"تقام يوم {fmt_day(d1)}." if d1 == d2 else f"تبدأ يوم {fmt_day(d1)}. تنتهي يوم {fmt_day(d2)}."))
    if done:
        res = " ".join(f"{ar_team_in(m.get('home'), comp)} {m['home_score']} - {m['away_score']} {ar_team_in(m.get('away'), comp)}."
                       for m in sorted(done, key=lambda m: (m.get("kickoff") or "", m.get("koff_time") or "")))
        out.append((f"ما نتائج الجولة {n} من {label}؟", res))
    if todo and COMP_TV.get(comp):
        out.append((f"ما القناة الناقلة لمباريات الجولة {n} من {label}؟", f"{COMP_TV[comp]} في المنطقة العربية."))
    return out


def description(comp, n, ms):
    return intro(comp, n, ms)
