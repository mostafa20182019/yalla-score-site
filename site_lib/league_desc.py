# -*- coding: utf-8 -*-
"""The league pages' meta descriptions - each opens with the live fact the
query is really after (2026-10-12, same move as the club pages the same day:
user «اعمل نفس الحاجة لصفحات الدوريات»). Helpers live here, not in
site_pages/, because build() calls every site_pages function once
(tests/test_build_split.py)."""
import re
from site_lib.dates import day_month
from site_lib.names import ar_team, comp_label


# the league titles lead with the query a reader types («ترتيب الدوري المصري
# اليوم», «مباريات الدوري المصري اليوم», «هداف الدوري المصري») and the
# descriptions open with the live fact - the top of the table, the next
# fixture and last score, the leading scorer - instead of a generic sentence.
def _ar_n(n, one, two, few, many):
    """The Arabic count forms: «نقطة واحدة» / «نقطتين» / «3 نقاط» (3-10) /
    «11 نقطة» (11 and up take the singular)."""
    n = int(n or 0)
    if n == 1:
        return one
    if n == 2:
        return two
    return f"{n} {few if 3 <= n <= 10 else many}"


def _bi(s):
    """«بـ3 نقاط» but «بنقطتين» - the joining form of the preposition."""
    return ("بـ" if s[:1].isdigit() else "ب") + s


def standings_desc(label, season, table, zeroed=False):
    rows = [r for r in (table or []) if r.get("team")]
    if zeroed or len(rows) < 3:
        return (f"جدول ترتيب {label} لموسم {season} محدثًا تلقائيًا: النقاط والمباريات "
                "والأهداف وفارق الأهداف ونتائج آخر 5 مباريات لكل فريق.")
    t1, t2, t3 = rows[0], rows[1], rows[2]
    return (f"المتصدر: {ar_team(t1.get('team'))} {_bi(_ar_n(t1.get('pts'), 'نقطة واحدة', 'نقطتين', 'نقاط', 'نقطة'))} "
            f"من {_ar_n(t1.get('played'), 'مباراة واحدة', 'مباراتين', 'مباريات', 'مباراة')}، "
            f"ثم {ar_team(t2.get('team'))} ({t2.get('pts')}) و{ar_team(t3.get('team'))} ({t3.get('pts')}). "
            f"جدول ترتيب {label} {season} كاملًا بالأهداف وفارق الأهداف ونتائج آخر 5 مباريات.")


def scorers_desc(label, season, sc):
    rows = [r for r in (sc or []) if r.get("name")]
    if len(rows) < 3:
        return (f"قائمة هدافي {label} لموسم {season} محدثة تلقائيًا بعد كل جولة، "
                "مع ترتيب صناع الأهداف (التمريرات الحاسمة).")
    g = lambda r: r.get("goals") if r.get("goals") is not None else r.get("value")
    s1, s2, s3 = rows[0], rows[1], rows[2]
    return (f"هداف {label} حتى الآن: {s1.get('name')} ({ar_team(s1.get('team'))}) "
            f"{_bi(_ar_n(g(s1), 'هدف واحد', 'هدفين', 'أهداف', 'هدفًا'))}، ثم {s2.get('name')} ({g(s2)}) "
            f"و{s3.get('name')} ({g(s3)}). ترتيب هدافي {label} {season} وصناع الأهداف "
            "محدّث بعد كل جولة.")


def fixtures_desc(label, season, rounds, n_m):
    flat = [(r.get("round"), m) for r in rounds for m in (r.get("matches") or [])]
    fin = [(rn, m) for rn, m in flat if (m.get("status") or "").upper() == "FINISHED"
           and m.get("home_score") is not None]
    up = [(rn, m) for rn, m in flat if (m.get("status") or "").upper() in ("UPCOMING", "LIVE", "TIMED", "SCHEDULED")]
    fin.sort(key=lambda x: (x[1].get("kickoff") or "", x[1].get("koff_time") or ""))
    up.sort(key=lambda x: (x[1].get("kickoff") or "", x[1].get("koff_time") or ""))
    parts = []
    if up:
        rn, m = up[0]
        parts.append(f"القادمة: {ar_team(m.get('home'))} × {ar_team(m.get('away'))} "
                     f"{day_month(m.get('kickoff'), weekday=True)}"
                     + (f" {m.get('koff_time')} بتوقيت القاهرة" if m.get("koff_time") else "")
                     + (f" (الجولة {rn})." if rn else "."))
    if fin:
        rn, m = fin[-1]
        parts.append(f"آخر نتيجة: {ar_team(m.get('home'))} {m.get('home_score')} - "
                     f"{m.get('away_score')} {ar_team(m.get('away'))} ({day_month(m.get('kickoff'))}).")
    parts.append(f"جدول مباريات {label} {season}: {len(rounds)} جولة و{n_m} مباراة بمواعيدها ونتائجها.")
    return " ".join(parts)


def _pick_headline(ms, team_pages, comp_order):
    """The match of the day: both clubs curated, else one, else the first
    league in COMP_ORDER; ties by kick-off time."""
    from site_lib.names import _team_match

    def key(m):
        n = sum(1 for tp in team_pages if _team_match(tp, m))
        c = m.get("competition") or ""
        return (-n, comp_order.index(c) if c in comp_order else len(comp_order),
                m.get("koff_time") or "")
    return sorted(ms, key=key)[0] if ms else None


def matches_desc(matches, today, team_pages, comp_order):
    """/matches: «N مباريات اليوم» + the headline fixture + the latest score.
    today = the navigator's default day (REF_TODAY), so the number matches
    what the page opens on."""
    todays = [m for m in matches if (m.get("kickoff") or "") == today]
    fin = [m for m in matches if (m.get("status") or "").upper() == "FINISHED"
           and m.get("home_score") is not None and (m.get("kickoff") or "") <= today]
    fin.sort(key=lambda m: ((m.get("kickoff") or ""), (m.get("koff_time") or "")))
    parts = []
    if todays:
        parts.append(f"مباريات اليوم {day_month(today, weekday=True)}: "
                     f"{_ar_n(len(todays), 'مباراة واحدة', 'مباراتان', 'مباريات', 'مباراة')}.")
        h = _pick_headline(todays, team_pages, comp_order)
        if h:
            parts.append(f"أبرزها: {ar_team(h.get('home'))} × {ar_team(h.get('away'))}"
                         + (f" {h.get('koff_time')} بتوقيت القاهرة" if h.get("koff_time") else "")
                         + f" ({comp_label(h.get('competition') or '')}).")
    else:
        nxt = sorted((m for m in matches if (m.get("kickoff") or "") > today),
                     key=lambda m: ((m.get("kickoff") or ""), (m.get("koff_time") or "")))
        parts.append("لا مباريات اليوم.")
        if nxt:
            n = nxt[0]
            parts.append(f"القادمة: {ar_team(n.get('home'))} × {ar_team(n.get('away'))} "
                         f"{day_month(n.get('kickoff'), weekday=True)}"
                         + (f" {n.get('koff_time')} بتوقيت القاهرة." if n.get("koff_time") else "."))
    if fin:
        m = _pick_headline([x for x in fin if x.get("kickoff") == fin[-1].get("kickoff")],
                           team_pages, comp_order) or fin[-1]
        parts.append(f"آخر نتيجة: {ar_team(m.get('home'))} {m.get('home_score')} - "
                     f"{m.get('away_score')} {ar_team(m.get('away'))}.")
    # the snippet is cut at seo_desc's limit: drop the generic tail first,
    # then the league in parentheses, so the score is never the cut point
    from site_lib.shell import seo_desc
    tail = "النتائج تتحدّث تلقائيًا."
    for cand in (parts + [tail], parts, [re.sub(r" \([^()]*\)\.", ".", p) for p in parts]):
        text = " ".join(cand)
        if seo_desc(text) == text:
            return text
    return " ".join(cand)

