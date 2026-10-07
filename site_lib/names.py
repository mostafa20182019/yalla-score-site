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


# match_id -> competition, for the match-piece rule in _team_news. Filled on
# first use from the same two files site_pages/articles.py reads; a caller
# that knows better (article_put with a match brief, the tests) passes
# "competition" on the record or calls set_match_comps().
_MATCH_COMPS = None
def set_match_comps(comps):
    global _MATCH_COMPS
    _MATCH_COMPS = {str(k): v or "" for k, v in (comps or {}).items()}


def _match_comp(a):
    """Competition of a match piece (preview/report), "" when unknown."""
    if a.get("competition"):
        return a["competition"]
    if not a.get("match_id"):
        return ""
    if _MATCH_COMPS is None:
        from site_lib.config import load
        set_match_comps({m["match_id"]: m.get("competition")
                         for m in load("matches_archive.json") + load("matches.json")
                         if m.get("match_id")})
    return _MATCH_COMPS.get(str(a["match_id"]), "")


def _tp_in_comp(tp, comp):
    """Can club tp play in competition comp? Its own league, or any of its
    match_tokens scopes (None = anywhere). Each scope is tested on its own:
    the old `tuple(c for ...)` nested EGY_SCOPE one level deep, so «CAF
    Champions League» never matched and _team_link left Egyptian clubs
    unlinked on African match rows."""
    return tp.get("league") == comp or any(_in_scope(c, comp) for _, c in tp["match_tokens"])


def _team_news(tp, a):
    """Does article a mention club tp? title+summary.

    Bare «الأهلي» is also Saudi Al-Ahli's name (bug 2026-10-07: the preview
    of الفتح × الأهلي, Saudi Pro League, linked to /team/al-ahly). Three rules:
    - a match piece whose competition is known belongs to a club only inside
      that club's match scope - the same rule the ticker uses, so a Saudi Pro
      League match can never land on the Egyptian club;
    - news_excl phrases name ANOTHER club («الأهلي السعودي») and are cut out
      before matching, so «الأهلي يرفض عرض الأهلي السعودي» still counts and
      «الأهلي السعودي يفوز» does not;
    - news_ctx (a foreign league: «دوري روشن») with none of news_anchor
      (Egyptian context) means the bare name is the foreign club."""
    comp = _match_comp(a) if a.get("kind") else ""
    if comp and not _tp_in_comp(tp, comp):
        return False
    txt = (a.get("title") or "") + " " + (a.get("summary") or "")
    for x in tp.get("news_excl", []):
        txt = txt.replace(x, " ")
    if any(x in txt for x in tp.get("news_ctx", [])) \
            and not any(x in txt for x in tp.get("news_anchor", [])):
        return False
    return any(t in txt for t in tp["news_tokens"])


def ar_team(name):
    return AR_TEAM.get(name or "", name or "")


def _team_link(comp, raw_name):
    """Arabic team name, linked to its /team/ page when it is a curated club."""
    nm = ar_team(raw_name)
    for tp in TEAM_PAGES:
        if _tp_in_comp(tp, comp) and any(t in (raw_name or "") or t == nm for t, _ in tp["match_tokens"]):
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
