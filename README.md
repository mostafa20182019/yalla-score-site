# Yalla Score — static SEO site (free, no credit card, Google-indexable)

A static mirror of Yalla Score's **own** content (editorial articles + match
schedule), built as plain HTML so it can be hosted **free with no credit card**
and indexed by Google. It reuses the site's look (green theme, Arabic RTL) and
ships full SEO markup: per-page titles, meta descriptions, canonical URLs,
Open Graph + Twitter cards, JSON-LD (`NewsArticle`), `robots.txt`, `sitemap.xml`.

> It's a **snapshot**, not the live app — no live scores, no admin console.
> When you add/edit news, **regenerate and redeploy** (2 commands, below).
> Only *our* content is published (aggregated RSS headlines are intentionally
> excluded — they belong to other sites).

## Folder layout
```
static-site/
  build_site.py         generator (edit SITE_BASE at the top)
  extract_content.sql   pulls current content from the local DB -> data/*.json
  data/                 articles.json, matches.json (content snapshot)
  dist/                 <-- THE SITE TO DEPLOY (drag this folder)
```

---

## Deploy — pick ONE (all free, no card)

### Option A — Netlify Drop (easiest, ~2 min)
1. Go to **https://app.netlify.com/drop**.
2. **Drag the `dist/` folder** onto the page. It uploads and gives you a live
   URL like `https://random-name.netlify.app` immediately.
3. (Recommended) create a free Netlify account to keep the site and rename it.
4. Copy your final URL, then do **"Set your real URL" below**.

### Option B — Cloudflare Pages
1. **https://pages.cloudflare.com** → create a project → **Direct Upload**.
2. Upload the contents of `dist/`. You get `https://your-project.pages.dev`.

### Option C — GitHub Pages
1. Create a new **public** GitHub repo, put the contents of `dist/` in it.
2. Repo **Settings → Pages** → Source = `main` branch, `/root` → Save.
3. Site goes live at `https://<user>.github.io/<repo>/`.

None of these require a credit card.

---

## Set your real URL (do this once you know it)
Good SEO needs correct canonical/sitemap URLs. After you have your host URL:
1. Open `build_site.py`, set `SITE_BASE = "https://your-real-url"` (no trailing slash).
2. Rebuild + redeploy:
   ```
   "C:\Program Files\Python312\python.exe" build_site.py
   ```
   then re-drag `dist/` (Netlify) or re-upload / push again.

---

## Get it into Google
1. **Google Search Console** → https://search.google.com/search-console → add
   your site URL as a property → verify (Netlify/Pages: use the
   *HTML tag* method — paste the tag into `build_site.py`'s `head()` once, or use
   the DNS/URL-prefix method your host supports).
2. In Search Console → **Sitemaps** → submit `sitemap.xml`.
3. Indexing takes days to a couple of weeks. You can **Request indexing** for
   the home + article URLs to speed it up.
4. Tips already handled by the generator: unique titles/descriptions, clean
   URLs, mobile-friendly layout, structured data. Add fresh articles regularly —
   Google favours updated content.

---

## Google AdSense (the left-column ad slot)

The home page has a reserved left column showing a **"مساحة إعلانية"** placeholder.
To turn it into real ads once AdSense approves you:
1. In `build_site.py` (top), set:
   - `ADSENSE_CLIENT = "ca-pub-XXXXXXXXXXXXXXXX"` (your publisher id)
   - `ADSENSE_SLOT   = "XXXXXXXXXX"` (an ad-unit slot id from AdSense)
2. Rebuild + deploy (`auto-publish.cmd`, or the scheduled task).
The AdSense loader script is added automatically and the placeholder becomes a
real responsive ad. While either value is empty, the placeholder is shown.

Prerequisites AdSense needs: your **own domain** (a `*.workers.dev` subdomain is
usually not approved), a **Privacy Policy** page, and enough original content.

## Automatic publishing (set up 2026-07-19)

The site auto-refreshes itself — no manual steps:
- **Windows Scheduled Task `YallaScore-AutoPublish`** runs `auto-publish.cmd`
  **every hour**.
- `auto-publish.cmd` = extract latest content from the DB → `build_site.py` →
  **`wrangler deploy`** (uploads `dist/` to the same Cloudflare Workers project,
  same URL). Output is appended to `auto-publish.log`.
- Config: `wrangler.toml` (`name = "old-credit-e926"`, `[assets] directory = ./dist`).
- **One-time prerequisite:** `wrangler login` (OAuth, stored in the user profile).
  If deploys start failing with an auth error, run `wrangler login` again.
- **Requirements while it runs:** the machine on + the user logged in + the
  Oracle DB running (same as the DB's own 5-min news job). If the DB is down,
  `auto-publish.cmd` aborts and keeps the last good deploy.
- **The site only refreshes while the PC is on and awake.** If the PC sleeps /
  shuts down / runs on battery-saver, both the DB news job and this task pause,
  so the news freezes until the PC is back (then it catches up). For true 24/7
  updates you'd need an always-on machine or cloud host.
- Reliability settings applied (2026-07-20) so missed runs aren't lost:
  `StartWhenAvailable=True` (run ASAP after a missed slot), and battery starts
  allowed (`DisallowStartIfOnBatteries=False`, `StopIfGoingOnBatteries=False`).
  Optional: enable *Wake the computer to run this task* in Task Scheduler for
  overnight updates.
- Change the interval: Task Scheduler → `YallaScore-AutoPublish`, or
  `schtasks /Change /TN YallaScore-AutoPublish ...`. Deploy manually anytime with
  `auto-publish.cmd` (or `wrangler deploy` from this folder).

## Update the content manually (optional — the scheduled task already does this)

**Easiest — double-click `update.cmd`.** It runs all three steps (extract latest
content from the DB → rebuild the site → make the zip) and tells you the zip to
upload. Requires the local Oracle database (FREEPDB1) to be running.
Then in Cloudflare: your project → **New deployment** → drag
`yalla-score-site.zip`.

Or run the steps manually from `matches-guide/static-site/`:
```
# 1) pull the latest content from the local APEX DB (DB must be running)
$env:JAVA_HOME="F:\tools\jdk-21.0.11"
& F:\tools\sqlcl\bin\sql.exe -S -thin AILAB/ApexLab#2026@//localhost:1521/FREEPDB1 @extract_content.sql
# 2) rebuild the static site
& "C:\Program Files\Python312\python.exe" build_site.py
# 3) make the upload zip, then redeploy it (Cloudflare New deployment)
& "C:\Program Files\Python312\python.exe" make_zip.py
```

## Notes
- External images (Unsplash / team badges) are hot-linked; they load fine and
  are used as the Open-Graph share images.
- `data/*.json` is UTF-8 (Arabic verified). Don't edit by hand — regenerate.
- Keep the free-image + attribution discipline for any new article images.
