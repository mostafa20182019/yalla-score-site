"""Reading the build's inputs: the articles (export or store), the goals
index, and build-info.json for /health.

Moved verbatim out of build_site.py (2026-09-26, tools/move_names.py):
source and comments exactly as they were there. Edit here; build_site
imports these back under the same names."""
import datetime
import io
import json
import os
import results_archive as RA
import store
from site_lib.config import DATA, load
from site_lib.dates import _epoch_ms
from site_lib.matchdata import goal_events_index


def articles_current():
    """(articles, source label) - the committed export when it is provably
    current, the store otherwise.

    A full store.article_all() scans the articles table plus three child
    tables on EVERY build (~48-96 runs/day), and D1's free tier bills rows
    scanned - the read quota ran out on 2026-09-16, 09-19 and 09-20. So the
    build first reads the ONE-ROW change marker every article write replaces
    (store.articles_sig) and, when it equals the sig recorded inside the
    committed export, uses the export as-is. An admin-page edit bumps the
    marker without rewriting the export, so those builds pull the full set
    until the next article_put/d1-admin export re-syncs the file - correct,
    just briefly more expensive. ARTICLES_FULL=1 is the escape hatch if a
    writer is ever suspected of forgetting the bump."""
    if store.backend() != "json" and not os.environ.get("ARTICLES_FULL"):
        sig = store.articles_sig()          # one row read
        if sig:
            try:
                with open(os.path.join(DATA, "articles.json"), encoding="utf-8") as f:
                    doc = json.load(f)
                if doc.get("sig") == sig:
                    return (doc["results"][0]["items"],
                            "the committed export (sig match, 1 row read)")
            except Exception:                               # noqa: BLE001
                pass                # unreadable export -> pull everything
    return store.article_all(), f"the {store.backend()} store"


def goals_index(goal_events=None, details=None, frozen=None):
    """THE scorers index - every consumer must use this one (2026-09-24).

    Three sources, later ones winning: match_details.json (ACCUMULATING - every
    finished match we ever fetched), goal_events.json (a ROLLING window, the
    freshest word on the last few hours) and the frozen archive (complete by
    construction). The page switched to this merge on 2026-09-13 after the
    rolling file alone made scorers vanish hours after the whistle; fb_reel,
    fb_cards and match_brief kept reading goal_events.json alone, so the reel
    found ZERO candidates (every curated match with goals looked scorer-less
    once it left the window) - caught by test_fb_reel 8 when the tests moved
    into CI. Arguments default to loading the files."""
    if details is None:
        details = load("match_details.json")
    if goal_events is None:
        goal_events = load("goal_events.json")
    if frozen is None:
        frozen = RA.frozen_entries(RA.load())
    idx = goal_events_index(details)
    idx.update(goal_events_index(goal_events))
    idx.update(goal_events_index(frozen))      # frozen wins
    return idx


def build_info(articles, preds):
    """build-info.json - what THIS deploy contains, read by the Worker's /health
    and its 15-minute watchdog (2026-09-24).

    It answers from the DEPLOYED copy on purpose: a green publish run can skip
    its deploy (main moved) and a fetch step can fail under continue-on-error,
    and in both cases every signal inside GitHub still said «success». The file
    the reader is actually being served cannot lie about its own age.
    Epoch ms everywhere, so the Worker never parses a time zone."""
    try:
        with io.open(os.path.join(DATA, "fetch_debug.json"), encoding="utf-8") as f:
            fd = json.load(f)
    except (OSError, ValueError):
        fd = {}
    # fetch_data.py writes "FAIL: <repr>" for a source that raised, and keeps
    # the previous file for it - the site still builds, just not newer data
    bad = sorted(k for k, v in fd.items() if isinstance(v, str) and v.startswith("FAIL"))
    newest = max((t for t in (_epoch_ms(a.get("pub_ts") or a.get("pub_date"))
                              for a in articles) if t), default=None)
    return {
        "built_at": int(datetime.datetime.now(datetime.timezone.utc).timestamp() * 1000),
        "fetch_at": _epoch_ms(fd.get("utc")),
        "fetch_failed": bad,
        "articles": len(articles),
        "newest_article_at": newest,
        "predictions": len(preds),
    }
