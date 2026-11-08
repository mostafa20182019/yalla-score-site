# Elgoon (الجون)

**Live: https://elgoon.com** — an Arabic football site: scores and fixtures
for the Egyptian league, the CAF Champions League and the big European leagues,
an analysis per match, a prediction model with a public record of every call
it made (hits and misses alike), and original news. Everything on it is
produced by the code in this repository; nobody is on shift.

## How it runs

| Layer | What | Where |
|---|---|---|
| Static site | ~800 pages built by `build_site.py` (Python, Jinja2) from `data/` | served by the Cloudflare Worker's assets binding (`dist/`) |
| Edge | `worker.js`: live-scores store, cron triggers, admin API, live Facebook posts | Cloudflare Worker + D1 (`yallascore`) + KV (`yallascore-data`) |
| Jobs | fetch data, build, deploy, write articles, post to Facebook / Telegram, send web push | GitHub Actions (`.github/workflows/`), dispatched by the Worker's crons |
| Content store | articles are written to D1 (`article_put.py`, the admin page); `data/articles.json` is the export | D1 |
| Images | match cards and infographics drawn from the data (`matchup_card.py`, `h2h_card.py`, `fb_cards.py`) | `media/` |

The rule behind the schedule: **the Worker decides when, GitHub does the
work.** Cloudflare crons fire on time; GitHub's own `schedule:` is best-effort.

## Working on it

```
pip install -r requirements.txt
python data_store.py pull          # the working data (Workers KV bundle)
python build_site.py               # -> dist/
python tests/run_all.py            # the whole suite (Python + Node)
```

**News from the data** (`story_events.py`, 2026-11-08): four detectors read
the data files and turn what they find into Facebook posts - a cup round
that ended (the next round's pairings from `fixtures.json`), the first half
of a league (the table from `standings.json`, the top scorer from
`scorers.json`), a coach who left the national team (one of our articles is
the trigger, his record is the NT's matches in the archive), and «في مثل هذا
اليوم» (a derby, a big score or a final of an earlier year in
`results_archive.json`, or a `moments/*.json` that carries a `date`). Nothing
is written from memory: a fact that is not in a data file is not written.
`python story_events.py` dry-runs every detector on today's data and says
why each one is quiet; `python fb_post.py --events --dry` prints the texts
that would go out; `python fb_post.py --events` posts each once through the
store (kind = the event kind, ref = its stable ref) - but only while the
repo variable `FB_EVENTS` is `on`; until then the run prints the texts into
the Actions summary and posts nothing, so the wording is read before it goes
live. The nightly `daycard=results` dispatch runs it after the results card,
the `daycard` input accepts `events` to run it alone, and publish.yml
dispatches `daycard=events` on a refresh when `fb_post.py --events --pending`
is not 0 (switch on), so an event that became true this evening posts within
the refresh. This is a permanent editorial line («أخبار خاصة بينا»), so the
kinds live in one registry (`story_events.DETECTORS`: one pure function per
kind) and every event has one shape - title, competition, fact lines, link,
tags, plus the structured data it was made of (pairings, table rows, the
record, the match) - so the same detector can feed a site article later. `python story_events.py --moment
<match_id> --id <name>` writes a `moment_reel.py` script from an archived
match with its goals (`moments/<name>.json`); publish it with the `moment`
input once the wording is approved.

Secrets live in GitHub Actions and on the Worker; none are in the repo. The
site's editorial policy, data sources and the model's record are explained on
the site itself: https://elgoon.com/editorial and https://elgoon.com/predictions.

## Status

Built and maintained by [Moustafa Abdelsalam](https://fixednotes.dev) since
July 2026. Issues and pull requests are welcome for bugs you can reproduce.
