"""What build() computes before the pages: the strength model, predictions,
accuracy, player insights, the ticker + kickoff times, and the shared
per-league data (tables, scorers, forms, fixtures).

Moved verbatim out of build_site.py (2026-09-26, tools/move_names.py):
source and comments exactly as they were there. Edit here; build_site
imports these back under the same names."""
import analysis as AN
import datetime
import json
import results_archive as RA
import site_lib.shell as _shell
import store
from site_lib.config import load
from site_lib.crests import comp_icon, local_crest
from site_lib.matchdata import score_pill
from site_lib.names import ar_team, comp_label
from site_lib.stats import chart_is_current, compute_elo, league_pcts, team_form
from site_lib.tables import _scorer_face, scorers_list
from site_lib.text import esc
from site_lib.ticker import make_ticker


def prepare_model(_details_raw, _res_arch, assists, fixtures, matches, scorers, standings):
    # ---- تحليلات: strength model + predictions + accuracy + player insights ----
    _archive = load("matches_archive.json")
    # The season pool: the results archive AHEAD of the feed's rolling files, so
    # the opening rounds the feed has forgotten still count (the Saudi 51-vs-60
    # drift of 2026-09-13) and a frozen score wins a conflict. season_matches()
    # de-duplicates by fixture, so a match on both sides is counted once.
    _bycomp = AN.season_matches(fixtures, RA.season_rows(_res_arch) + _archive)
    # season carry-over (roadmap factor 1): the five European leagues start from
    # last season's carried Elo (data/elo_seeds.json, season_carry.py); absent
    # file = flat 1500 as before. The Oracle copy reads the same seeds.
    _seeds = AN.load_elo_seeds()
    if _seeds:
        print(f'  + elo seeds: {sum(len(v) for v in _seeds.values())} clubs in {len(_seeds)} leagues')
    _tstats = AN.team_stats(_bycomp, _seeds)
    _lparams = {c: AN.league_params(ms) for c, ms in _bycomp.items()}
    def _pred(m):
        comp = m.get("competition")
        if comp not in _tstats or not m.get("home") or not m.get("away"):
            return None
        return AN.predict(_tstats[comp], _lparams[comp], m["home"], m["away"])
    _upcoming = [m for m in matches if (m.get("status") or "").upper() == "UPCOMING" and m.get("match_id")]
    _preds = {}
    for m in _upcoming:
        p = _pred(m)
        if p:
            p["src"] = "python"
            _preds[str(m["match_id"])] = p
    print(f'  + predictions: {len(_preds)} upcoming fixtures, python model')
    # The prediction log lives in the store (D1 when configured). A frozen
    # prediction that gets re-frozen with newer data would silently inflate the
    # published accuracy, which is the one thing the accuracy page exists to
    # prevent - so the freeze has to be atomic, and store.pred_freeze refuses
    # to touch a row that is already scored.
    #
    # THE BUILD MUST NOT DEPEND ON A LIVE SERVICE: if the store is unreachable,
    # fall back to the last committed export, skip persisting, and still render
    # every page. A dead database may cost us one cycle of the log; it must
    # never cost us the site.
    _plog, _pstore_ok = {}, True
    try:
        _plog = store.pred_all()
    except Exception as e:                                  # noqa: BLE001
        _pstore_ok = False
        print(f"  ! prediction store unreachable ({e}) - using the committed export")
        _plog = AN.load_log()
    # the model's own track record per stated-probability band, computed once:
    # every upcoming match page prints the band its top number falls in
    _cal = AN.calibration(_plog)
    _pch = AN.update_log(_plog, _upcoming, _preds, matches + _archive, datetime.date.today())
    if _pstore_ok:
        try:
            for _mid in _pch["frozen"]:
                store.pred_freeze(_mid, _plog[_mid])
            for _mid in _pch["scored"]:
                _e = _plog[_mid]
                store.pred_score(_mid, _e["hs"], _e["as"], _e["outcome"], _e["pick"],
                                 _e["hit"], _e["brier"], _e["score_hit"])
            if _pch["pruned"]:
                store.pred_prune(AN.PRUNE_DAYS)
            if any(_pch.values()):
                print(f'  + predictions: {len(_pch["frozen"])} frozen, '
                      f'{len(_pch["scored"])} scored, {len(_pch["pruned"])} pruned '
                      f'({len(_plog)} in the log, backend {store.backend()})')
        except Exception as e:                              # noqa: BLE001
            print(f"  ! could not persist predictions ({e}) - pages still build")
    _acc = AN.accuracy(_plog)
    for _k, _v in sorted((_acc.get("by_src") or {}).items()):
        if _v:
            print(f'  + accuracy [{_k}]: n={_v["n"]} hit={_v["hit_rate"]:.1%} brier={_v["brier"]:.4f}')
    _comp_idx = {}
    for m in matches + _archive + [mm for f in fixtures for rd in f.get("rounds", []) for mm in rd.get("matches", [])]:
        if m.get("home") and m.get("away"):
            _comp_idx[(ar_team(m["home"]), ar_team(m["away"]), m.get("kickoff"))] = m.get("competition")
    _pins = AN.player_insights(_details_raw, lambda h, a, d: _comp_idx.get((h, a, d)), ar_team)
    # who each club normally starts -> «من غاب ومن عاد» on the match pages
    _squad = AN.SquadIndex(_details_raw, lambda h, a, d: _comp_idx.get((h, a, d)))
    _sins = AN.scorer_insights(scorers, assists, {s.get("competition"): s["table"] for s in standings if s.get("table")})
    # reels: hand-picked first, then auto-pulled channel uploads (deduped)
    reels = load("reels.json")
    seen_r = {r.get("video_id") for r in reels}
    for r in load("reels_auto.json"):
        if r.get("video_id") not in seen_r:
            reels.append(r)
            seen_r.add(r.get("video_id"))

    _shell.TICKER_HTML = make_ticker(matches)

    # kickoff epochs for LIVE_JS's kickoff-aware polling (see KO_SCRIPT)
    try:
        from zoneinfo import ZoneInfo
        _cairo = ZoneInfo("Africa/Cairo")
        _now = datetime.datetime.now(_cairo)
        _kos = set()
        for _m in matches:
            if not (_m.get("kickoff") and _m.get("koff_time")):
                continue
            try:
                _dt = datetime.datetime.fromisoformat(
                    f"{_m['kickoff']}T{_m['koff_time']}:00").replace(tzinfo=_cairo)
            except ValueError:
                continue
            _delta = (_dt - _now).total_seconds()
            # recent past too: a match may already be live at build time
            if -4 * 3600 <= _delta <= 36 * 3600:
                _kos.add(int(_dt.timestamp() * 1000))
        _shell.KO_SCRIPT = (f"<script>window.__koTs={json.dumps(sorted(_kos))}</script>"
                     if _kos else "")
    except Exception:
        _shell.KO_SCRIPT = ""
    return {"acc": _acc, "bycomp": _bycomp, "cal": _cal, "lparams": _lparams,
            "pins": _pins, "plog": _plog, "preds": _preds, "sins": _sins,
            "squad": _squad, "tstats": _tstats, "upcoming": _upcoming, "reels": reels}


def prepare_league_data(_bycomp, assists, fixtures, scorers, standings):
    # ---- shared per-league data + stats machinery (matches page + /stats) ----
    st_by_comp = {s.get("competition"): s for s in standings if s.get("table")}
    sc_by_comp = {s.get("competition"): (s.get("scorers") or [])
                  for s in scorers if s.get("scorers")}
    as_by_comp = {s.get("competition"): (s.get("assists") or [])
                  for s in assists if s.get("assists")}
    # both read the season pool (_bycomp) so a truncated fixtures.json cannot
    # empty the «آخر 5» column or the tile fallback (2026-09-13)
    forms = team_form(fixtures, standings, _bycomp)
    elos = compute_elo(fixtures, _bycomp)
    fx_by_comp = {f.get("competition"): f for f in fixtures if f.get("rounds")}
    STAT_PAL = ["#1f94d3", "#e11d48", "#f59e0b", "#7c3aed", "#334155"]

    def _fin_ms(fx):
        """(round, match) pairs for finished matches with scores, chronological."""
        ms = []
        for rd in fx.get("rounds", []):
            for m in rd.get("matches", []):
                if (m.get("status") == "FINISHED"
                        and m.get("home_score") is not None
                        and m.get("away_score") is not None):
                    ms.append((rd.get("round"), m))
        ms.sort(key=lambda t: (t[1].get("kickoff") or "", t[1].get("koff_time") or ""))
        return ms

    def _pts_race_svg(fin, top_teams):
        """Cumulative points per round for the leading teams, inline SVG line chart."""
        rounds = sorted({r for r, _ in fin if r is not None})
        top_teams = [t for t in top_teams if t]
        if len(rounds) < 2 or not top_teams:
            return ""
        per = {}
        for r, m in fin:
            if r is None:
                continue
            hs, aw = m["home_score"], m["away_score"]
            d = per.setdefault(r, {})
            d[m.get("home")] = d.get(m.get("home"), 0) + (3 if hs > aw else 1 if hs == aw else 0)
            d[m.get("away")] = d.get(m.get("away"), 0) + (3 if aw > hs else 1 if hs == aw else 0)
        series = {}
        for t in top_teams:
            c, vals = 0, []
            for r in rounds:
                c += per.get(r, {}).get(t, 0)
                vals.append(c)
            series[t] = vals
        w, h, ml, mr, mt, mb = 680, 240, 30, 12, 12, 26
        ymax = max(max(v) for v in series.values()) or 1
        def x(i): return ml + (w - ml - mr) * (i / max(1, len(rounds) - 1))
        def y(v): return mt + (h - mt - mb) * (1 - v / ymax)
        parts = [f'<svg class="chart" viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="سباق النقاط">']
        step = max(1, ymax // 4)
        for g in range(0, ymax + 1, step):
            parts.append(f'<line x1="{ml}" y1="{y(g):.1f}" x2="{w - mr}" y2="{y(g):.1f}" stroke="#eef2f6"/>')
            parts.append(f'<text x="{ml - 5}" y="{y(g) + 4:.1f}" font-size="10" fill="#94a3b8" text-anchor="end">{g}</text>')
        for i, r in enumerate(rounds):
            parts.append(f'<text x="{x(i):.1f}" y="{h - 8}" font-size="10" fill="#94a3b8" text-anchor="middle">{r}</text>')
        for k, (t, vals) in enumerate(series.items()):
            col = STAT_PAL[k % len(STAT_PAL)]
            pl = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(vals))
            parts.append(f'<polyline points="{pl}" fill="none" stroke="{col}" stroke-width="2.5" stroke-linejoin="round"/>')
            parts.append(f'<circle cx="{x(len(vals) - 1):.1f}" cy="{y(vals[-1]):.1f}" r="3.5" fill="{col}"/>')
        parts.append('</svg>')
        legend = "".join(
            f'<span class="lgd"><i style="background:{STAT_PAL[k % len(STAT_PAL)]}"></i><bdi>{esc(ar_team(t))}</bdi></span>'
            for k, t in enumerate(series))
        return f'<div class="chart-wrap">{"".join(parts)}</div><div class="legend">{legend}</div>'

    def _goals_svg(fin):
        """Total goals per round, inline SVG bar chart (needs 2+ rounds —
        a single bar just repeats the season-total tile)."""
        rounds = sorted({r for r, _ in fin if r is not None})
        if len(rounds) < 2:
            return ""
        goals = {r: 0 for r in rounds}
        for r, m in fin:
            if r is not None:
                goals[r] += m["home_score"] + m["away_score"]
        w, h, ml, mr, mt, mb = 680, 200, 30, 12, 14, 26
        ymax = max(goals.values()) or 1
        bw = min((w - ml - mr) / len(rounds) * 0.6, 64)
        parts = [f'<svg class="chart" viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="الأهداف في كل جولة">']
        for i, r in enumerate(rounds):
            cx = ml + (w - ml - mr) * ((i + .5) / len(rounds))
            bh = (h - mt - mb) * goals[r] / ymax
            parts.append(f'<rect x="{cx - bw / 2:.1f}" y="{h - mb - bh:.1f}" width="{bw:.1f}" height="{max(bh, 1):.1f}" rx="3" fill="#1f94d3" opacity="0.85"/>')
            parts.append(f'<text x="{cx:.1f}" y="{h - mb - bh - 4:.1f}" font-size="10" fill="#475569" text-anchor="middle">{goals[r]}</text>')
            parts.append(f'<text x="{cx:.1f}" y="{h - 8}" font-size="10" fill="#94a3b8" text-anchor="middle">{r}</text>')
        parts.append('</svg>')
        return f'<div class="chart-wrap">{"".join(parts)}</div>'

    # season totals per competition, so the player charts can be checked
    # against the season they claim to describe (see chart_is_current)
    comp_goals, comp_maxp = {}, {}
    for _c, _fx in fx_by_comp.items():
        _f = _fin_ms(_fx)
        # The denominator has to be the SEASON POOL, not this one file. For the
        # 365scores leagues fixtures.json carries scores for only a few rounds
        # (Egypt on 2026-09-16: 11 goals in the file against the 93 the season
        # actually holds), and an understated denominator makes
        # chart_is_current reject a perfectly current top-scorer list as "last
        # season's": 13 goals across the top five > 11 for the whole league.
        # That is what emptied /scorers/egypt - the guard was right about the
        # arithmetic and wrong about the world. Found by an outside HTML audit
        # of the live site, 2026-09-16.
        comp_goals[_c] = max(
            sum(int(m["home_score"]) + int(m["away_score"]) for m in (_bycomp.get(_c) or [])),
            sum(m["home_score"] + m["away_score"] for _, m in _f))
        _tbl = (st_by_comp.get(_c) or {}).get("table") or []
        comp_maxp[_c] = (max((r.get("played") or 0) for r in _tbl) if _tbl
                         else max((r or 0 for r, _ in _f), default=0))
    sc_ok = {c: chart_is_current(rows, comp_goals.get(c), comp_maxp.get(c))
             for c, rows in sc_by_comp.items()}
    as_ok = {c: chart_is_current(rows, comp_goals.get(c), comp_maxp.get(c))
             for c, rows in as_by_comp.items()}
    stats_cutoff = (datetime.date.today() - datetime.timedelta(days=30)).isoformat()

    def league_stats_parts(comp):
        """One league's stats, split into the tab panes the matches page uses:
        {"numbers": tiles + percentages, "scorers": scorers + assists charts,
         "trend": points race + goals per round}. Missing pieces are absent.
        /stats.html stitches them back into one section."""
        parts = []
        fx = fx_by_comp.get(comp)
        if not fx:
            return {}
        fin = _fin_ms(fx)
        if not fin:
            return {}
        fx = fx_by_comp.get(comp)
        if not fx:
            return ""
        fin = _fin_ms(fx)
        if not fin:
            return ""
        # a season that ended long ago (e.g. last season's Champions League
        # rounds still in the feed) must not pose as current-season numbers:
        # skip when nothing is left to play AND the last match is >30 days old
        all_ms = [m for rd in fx.get("rounds", []) for m in rd.get("matches", [])]
        pending = any((m.get("status") or "").upper() != "FINISHED" for m in all_ms)
        last_day = max((m.get("kickoff") or "" for m in all_ms), default="")
        if not pending and last_day and last_day < stats_cutoff:
            return {}
        played = len(fin)
        goals = sum(m["home_score"] + m["away_score"] for _, m in fin)
        big = max((m for _, m in fin),
                  key=lambda m: (m["home_score"] + m["away_score"],
                                 max(m["home_score"], m["away_score"])))
        big_t = (f'{ar_team(big.get("home"))} {big["home_score"]}-{big["away_score"]} '
                 f'{ar_team(big.get("away"))}')
        # who played it: same home-first order as every match row on the site
        def _tile_side(name, badge):
            img = (f'<img src="{esc(local_crest(badge))}" alt="" loading="lazy">'
                   if badge else '<span class="ph">⚽</span>')
            return f'<span class="tm">{img}<bdi>{esc(ar_team(name))}</bdi></span>'
        big_ms = (f'<div class="tile-ms">{_tile_side(big.get("home"), big.get("home_badge"))}'
                  f'<i>×</i>{_tile_side(big.get("away"), big.get("away_badge"))}</div>')
        big_bits = []
        if big.get("round") is not None:
            big_bits.append(f'الجولة {esc(str(big["round"]))}')
        if big.get("kickoff"):
            try:
                _d = datetime.date.fromisoformat(big["kickoff"])
                big_bits.append(f'{_d.day:02d}/{_d.month:02d}/{_d.year}')
            except Exception:
                pass
        big_when = (f'<div class="tile-when">{" · ".join(big_bits)}</div>'
                    if big_bits else "")
        top_rows = (st_by_comp.get(comp) or {}).get("table") or []
        top_teams = [r.get("team") for r in top_rows[:5]]
        if not top_teams:
            er = elos.get(comp, {})
            top_teams = [t for t, _ in sorted(er.items(), key=lambda kv: -kv[1][0])[:5]]
        panes = {}
        # player charts, only when they describe THIS season (chart_is_current)
        sc = sc_by_comp.get(comp) or [] if sc_ok.get(comp) else []
        asst = as_by_comp.get(comp) or [] if as_ok.get(comp) else []
        sc_tile = ""
        if sc:
            lead = sc[0]
            sc_tile = (f'<div class="tile tile-sc" title="{esc(lead.get("name"))}'
                       f' - {esc(lead.get("team"))}"><b>{lead.get("goals")}</b>'
                       f'<span>هداف الدوري</span>'
                       f'<div class="tile-ms">{_scorer_face(lead)}'
                       f'<span class="tm"><bdi>{esc(lead.get("name"))}</bdi></span></div>'
                       f'<div class="tile-when">{esc(lead.get("team"))}</div></div>')
        num = ['<div class="stat-tiles">'
               f'<div class="tile"><b>{played}</b><span>مباراة لُعبت</span></div>'
               f'<div class="tile"><b>{goals}</b><span>هدفًا</span></div>'
               f'<div class="tile"><b>{goals / played:.2f}</b><span>متوسط الأهداف/مباراة</span></div>'
               f'<div class="tile tile-res" title="{esc(big_t)}">'
               f'{score_pill(big["home_score"], big["away_score"], "sc-in")}'
               f'<span>أكبر نتيجة</span>{big_ms}{big_when}</div>'
               f'{sc_tile}'
               '</div>']
        pcts = league_pcts(fin)
        if pcts:
            num.append('<h3 class="stats-h3">📐 نِسَب البطولة</h3>')
            num.append(pcts)
        panes["numbers"] = "".join(num)
        if sc or asst:
            chart = ['<div class="chart-cols">']
            if sc:
                chart.append('<div><h3 class="stats-h3">⚽ ترتيب الهدافين</h3>'
                             + scorers_list(sc, "أهداف") + '</div>')
            if asst:
                chart.append('<div><h3 class="stats-h3">🎯 صانعو الأهداف</h3>'
                             + scorers_list(asst, "صناعة") + '</div>')
            chart.append('</div>')
            panes["scorers"] = "".join(chart)
        trend = []
        race = _pts_race_svg(fin, top_teams)
        if race:
            trend.append('<h3 class="stats-h3">سباق النقاط — المقدمة</h3>')
            trend.append(race)
        gsvg = _goals_svg(fin)
        if gsvg:
            trend.append('<h3 class="stats-h3">الأهداف في كل جولة</h3>')
            trend.append(gsvg)
        if trend:
            panes["trend"] = "".join(trend)
        return panes

    def league_stats_sec(comp, heading=True):
        """All of a league's stats as one section — used by /stats.html."""
        panes = league_stats_parts(comp)
        if not panes:
            return ""
        head_html = (f'<h2 class="lt-head">{comp_icon(comp)} {esc(comp_label(comp))}</h2>'
                     if heading else "")
        body = "".join(panes.get(k, "") for k in ("numbers", "scorers", "trend"))
        return f'<section class="stats-sec">{head_html}{body}</section>' 
    return {"st_by_comp": st_by_comp, "sc_by_comp": sc_by_comp, "sc_ok": sc_ok,
            "as_by_comp": as_by_comp, "as_ok": as_ok, "forms": forms,
            "fx_by_comp": fx_by_comp, "league_stats_parts": league_stats_parts,
            "league_stats_sec": league_stats_sec}
