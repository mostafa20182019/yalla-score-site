# Yalla Score (يلا سكور)

**Live: https://yallascore.site** — an Arabic football site: scores and fixtures
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

Secrets live in GitHub Actions and on the Worker; none are in the repo. The
site's editorial policy, data sources and the model's record are explained on
the site itself: https://yallascore.site/editorial and https://yallascore.site/predictions.

## Status

Built and maintained by [Moustafa Abdelsalam](https://fixednotes.dev) since
July 2026. Issues and pull requests are welcome for bugs you can reproduce.
