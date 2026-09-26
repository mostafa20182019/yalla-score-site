"""The curated-clubs ticker under the header (one match per club).

Moved verbatim out of build_site.py (2026-09-26, tools/move_names.py):
source and comments exactly as they were there. Edit here; build_site
imports these back under the same names."""
import datetime
from site_lib.clubs import TICKER_TEAMS
from site_lib.config import REF_TODAY
from site_lib.crests import local_crest
from site_lib.matchdata import score_pill
from site_lib.names import _in_scope, _is_ticker_team, ar_team
from site_lib.text import esc


def _tk_date(kick):
    """Short Arabic date chip: اليوم / أمس / غدًا / dd/mm."""
    try:
        d = datetime.date.fromisoformat(kick)
        t = datetime.date.fromisoformat(REF_TODAY)
    except Exception:
        return kick or ""
    delta = (d - t).days
    if delta == 0:
        return "اليوم"
    if delta == -1:
        return "أمس"
    if delta == 1:
        return "غدًا"
    return f"{d.day:02d}/{d.month:02d}"


def make_ticker(matches):
    """Header ticker: ONLY the hand-picked TICKER_TEAMS clubs — LIVE first,
    then today's, then next upcoming + latest finished, each non-today item
    carrying a short date chip. Returns "" when there's nothing to show."""
    if not matches:
        return ""
    picked = [m for m in matches
              if _is_ticker_team(m) and (m.get("status") or "") != "POSTPONED"]
    live = [m for m in picked if (m.get("status") or "") == "LIVE"]
    todays = [m for m in picked
              if m.get("kickoff") == REF_TODAY and (m.get("status") or "") != "LIVE"]
    rest = [m for m in picked if m not in live and m not in todays]

    def stale(m):
        """FINISHED match that kicked off >24h ago — user rule (2026-08-23):
        a day-old result has no place in the ticker. Missing koff_time counts
        from midnight (conservative: drops earlier rather than lingering)."""
        try:
            from zoneinfo import ZoneInfo
            cairo = ZoneInfo("Africa/Cairo")
            ko = datetime.datetime.fromisoformat(
                f"{m.get('kickoff')}T{m.get('koff_time') or '00:00'}:00"
            ).replace(tzinfo=cairo)
            return (datetime.datetime.now(cairo) - ko).total_seconds() > 86400
        except Exception:
            return False

    fin = sorted((m for m in rest if m.get("status") == "FINISHED"
                  and not stale(m)),
                 key=lambda m: (m.get("kickoff") or "", m.get("koff_time") or ""),
                 reverse=True)
    up = sorted((m for m in rest if m.get("status") == "UPCOMING"),
                key=lambda m: (m.get("kickoff") or "", m.get("koff_time") or ""))

    def one_per_team(ms):
        """Keep only the first match per picked club (nearest upcoming /
        latest finished) - a club must not appear once per future fixture."""
        seen, kept = set(), []
        for m in ms:
            ha = (m.get("home") or "") + "|" + (m.get("away") or "")
            comp = m.get("competition") or ""
            # _in_scope, NOT c == comp: Egyptian clubs carry a TUPLE scope
            # (EGY_SCOPE) so == never matched and Zamalek showed once per
            # fixture (2026-09-03 screenshot: CAF 04/09 + EPL 08/09 both)
            teams = [t for t, c in TICKER_TEAMS
                     if t in ha and _in_scope(c, comp)]
            if teams and all(t in seen for t in teams):
                continue
            seen.update(teams)
            kept.append(m)
        return kept

    # ONE match per curated club across the WHOLE pool, priority live > today
    # > next upcoming > latest finished (user rule 2026-09-03: a club must
    # never appear twice — deduping only `up` left Ahly today + Ahly next)
    pool = one_per_team(live + todays + up + fin)[:14]
    if not pool:
        return ""
    sc = lambda v: "-" if v is None else v
    its = []
    for m in pool:
        st = m.get("status")
        hb = (f'<img class="tk-b" src="{esc(local_crest(m.get("home_badge")))}" alt="" loading="lazy">'
              if m.get("home_badge") else "")
        ab = (f'<img class="tk-b" src="{esc(local_crest(m.get("away_badge")))}" alt="" loading="lazy">'
              if m.get("away_badge") else "")
        if st == "LIVE":
            # NEVER bake a live score into static HTML - it is up to 15 min
            # stale and reads as WRONG data (user rule 2026-08-31). Dashes
            # until LIVE_JS paints the real score seconds after load.
            mid = score_pill(None, None, "tk-s tk-live") + '<span class="tk-dot"></span>'
        elif st == "FINISHED":
            mid = score_pill(m.get("home_score"), m.get("away_score"), "tk-s")
        else:
            mid = f'<span class="tk-t">{esc(m.get("koff_time") or "")}</span>'
        # date chip on every non-live item, today's included (user request
        # 2026-09-03: «اليوم» next to today's matches); live rows keep the dot
        day = ("" if st == "LIVE"
               else f'<span class="tk-d">{esc(_tk_date(m.get("kickoff")))}</span>')
        its.append(f'<span class="tk-item" data-lv data-h="{esc(ar_team(m.get("home")))}" data-a="{esc(ar_team(m.get("away")))}">{day}{hb}<bdi>{esc(ar_team(m.get("home")))}</bdi> <span class="tk-mid">{mid}</span> <bdi>{esc(ar_team(m.get("away")))}</bdi>{ab}</span>')
    seq = "".join(its)
    return ('<a class="ticker" href="/matches.html" aria-label="نتائج المباريات — اضغط للتفاصيل">'
            f'<div class="tk-track">{seq}{seq}</div></a>')
