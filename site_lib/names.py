"""Team and competition names, the curated scope, club links.

Moved verbatim out of build_site.py (slice 3, 2026-09-25): the source
and its comments are exactly what they were there. Edit here; build_site
imports these back under the same names."""
import hashlib
from site_lib.clubs import AR_TEAM, TEAM_PAGES, TICKER_TEAMS, _EGY_TOKENS, _EUR_TOKENS
from site_lib.competitions import COMP_LABEL, S365_COMP_IDS
from site_lib.text import esc


def _crest_name(url):
    ext = ".png"
    for e in (".png", ".svg", ".jpg", ".jpeg", ".gif", ".webp"):
        if url.lower().split("?")[0].endswith(e):
            ext = e
            break
    return hashlib.md5(url.encode("utf-8")).hexdigest()[:16] + ext


def _in_scope(scope, comp):
    if scope is None:
        return True
    return comp in scope if isinstance(scope, tuple) else comp == scope


def _is_ticker_team(m):
    ha = (m.get("home") or "") + "|" + (m.get("away") or "")
    comp = m.get("competition") or ""
    return any(t in ha and _in_scope(c, comp) for t, c in TICKER_TEAMS)


def _team_match(tp, m):
    """Does match m involve club tp? Same token+scope rule as the ticker."""
    ha = (m.get("home") or "") + "|" + (m.get("away") or "")
    comp = m.get("competition") or ""
    return any(t in ha and _in_scope(c, comp)
               for t, c in tp["match_tokens"])


def _team_news(tp, a):
    """Does article a mention club tp? title+summary, with exclusions."""
    txt = (a.get("title") or "") + " " + (a.get("summary") or "")
    if any(x in txt for x in tp.get("news_excl", [])):
        return False
    return any(t in txt for t in tp["news_tokens"])


def ar_team(name):
    return AR_TEAM.get(name or "", name or "")


def _team_link(comp, raw_name):
    """Arabic team name, linked to its /team/ page when it is a curated club."""
    nm = ar_team(raw_name)
    for tp in TEAM_PAGES:
        scope = tuple(c for _, c in tp["match_tokens"] if c) or None
        in_league = (tp["league"] == comp) or (scope is not None and _in_scope(scope, comp))
        if in_league and any(t in (raw_name or "") or t == nm for t, _ in tp["match_tokens"]):
            return f'<a href="/team/{tp["slug"]}.html">{esc(nm)}</a>'
    return esc(nm)


def _egy_article(a):
    txt = (a.get("title") or "") + " " + (a.get("summary") or "")
    if "الأهلي السعودي" in txt or "أهلي جدة" in txt:
        return False
    return any(t in txt for t in _EGY_TOKENS)


def _eur_article(a):
    txt = (a.get("title") or "") + " " + (a.get("summary") or "")
    return any(t in txt for t in _EUR_TOKENS)


def comp_has_table(comp, has_table):
    """Was a /standings page written for this competition this build?"""
    return comp in (has_table or set())


def comp_label(name):
    return COMP_LABEL.get(name, name or "")


def comp_emoji(name):
    n = (name or "").lower()
    if "world cup" in n or "مونديال" in n or "كأس العالم" in n: return "🏆"
    if "egypt" in n or "المصري" in n: return "🇪🇬"   # before "premier" (Egyptian Premier League)
    if "turk" in n or "التركي" in n: return "🇹🇷"
    if "saudi" in n or "السعودي" in n: return "🇸🇦"
    if "premier" in n: return "🦁"
    if "primera" in n or "laliga" in n or "la liga" in n: return "🇪🇸"
    if "serie a" in n: return "🇮🇹"
    if "bundesliga" in n: return "🇩🇪"
    if "ligue 1" in n: return "🇫🇷"
    if "caf" in n or "أفريقيا" in n: return "🌍"   # before the generic "champions"
    if "champions" in n: return "⭐"
    return "⚽"


def fav_club_names(standings, fixtures):
    """The curated clubs as the ARABIC names the live feed uses — TICKER_TEAMS
    holds football-data tokens for the European clubs, and /live.json speaks
    365scores Arabic, so resolve each token through the real data + ar_team()
    instead of hand-maintaining a second list."""
    names = []
    for token, only_comp in TICKER_TEAMS:
        hit = None
        for st in standings:
            comp = st.get("competition")
            if not _in_scope(only_comp, comp):
                continue
            for r in st.get("table") or []:
                if token in (r.get("team") or ""):
                    hit = r.get("team")
                    break
            if hit:
                break
        if not hit:                      # no table yet: try the fixtures feed
            for fx in fixtures:
                if not _in_scope(only_comp, fx.get("competition")):
                    continue
                for rd in fx.get("rounds", []):
                    for m in rd.get("matches", []):
                        for side in ("home", "away"):
                            if token in (m.get(side) or ""):
                                hit = m[side]
                                break
                        if hit: break
                    if hit: break
                if hit: break
        nm = ar_team(hit) if hit else token
        # league scope must survive into the browser: /live.json games carry
        # the 365scores competition id (g.c), and a scoped entry only matches
        # inside its own league — otherwise Saudi Al-Ahli ("الأهلي" too)
        # hijacks the favourite-club card meant for Al Ahly Egypt.
        # a tuple scope emits one entry per league id (الأهلي in 552 AND 624)
        scopes = only_comp if isinstance(only_comp, tuple) else (only_comp,)
        for sc in scopes:
            cid = S365_COMP_IDS.get(sc) if sc else None
            if not any(e["n"] == nm and e["c"] == cid for e in names):
                names.append({"n": nm, "c": cid})
    return names


def _gnorm(s):
    """Same normalization LIVE_JS uses to pair rows with 365scores names."""
    s = (s or "")
    for a, b in (("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ة", "ه"), ("ى", "ي")):
        s = s.replace(a, b)
    return "".join(ch for ch in s if ch not in ".'’  	")


def _club_pool(fin_all, raw):
    return [x for x in (fin_all or []) if raw in (x.get("home"), x.get("away"))]
