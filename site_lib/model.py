"""The strength model on its own - season pool, team stats, league params.

Lifted out of site_pages/prep.prepare_model (2026-10-07) so match_brief.py can
compute a preview's prediction with the SAME code the match page uses. It
is a helper, not a page, so it lives here."""
import analysis as AN
import results_archive as RA
from site_lib.config import load


def model_core(fixtures, _res_arch):
    """The strength model on its own: (season pool, team stats, league params,
    matches archive). Pure - it reads files and writes nothing - so a caller
    outside the build (match_brief.py's preview prediction, 2026-10-07) gets
    EXACTLY the numbers the match page prints, from the same code path."""
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
    return _bycomp, _tstats, _lparams, _archive
