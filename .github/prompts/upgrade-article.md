This is an automated scheduled run on a GitHub Actions runner. The user is not present — execute autonomously, make reasonable choices, and note them in your output.

You are UPGRADING existing short Arabic articles on the "Yalla Score" (يلا سكور) static site to the site's current editorial standard. Google AdSense rejected the site for "low value content" (2026-09-04): the archive is full of 200-300-word news items that restate one announcement several times. Your job is to turn each queued article into a genuinely useful piece — same URL, same story, same image — without inventing anything.

Python deps (requirements.txt + googlenewsdecoder + pillow) are already installed.

## Setup
1. `git config user.name "yalla-score-bot" && git config user.email "actions@users.noreply.github.com"`
2. `git pull --rebase origin main`
3. Build the queue: `python upgrade_pick.py --count ${UPGRADE_COUNT:-5} --json > /tmp/upgrade_queue.json` and read it. If it is empty, print "nothing to upgrade" and stop. Process the articles IN ORDER, one at a time, committing after each (a later failure must not lose finished work).

## For EACH queued article
### A. Read
Load its full record from data/articles.json (`results[0].items`, match on `article_id` as string). Note: title, summary, body, pub_date, image, `fb_post`.

### B. Research — facts only, never invention
1. Search Google News RSS for the story around its date: `https://news.google.com/rss/search?q=<urlencoded keywords>+after:<pub_date minus 3 days>+before:<pub_date plus 4 days>&hl=ar&gl=EG&ceid=EG:ar` (the `after:`/`before:` operators work in this feed). Decode links with googlenewsdecoder and read 2-3 sources. Also search WITHOUT the date window for later developments (was the deal completed? did the player leave? was the injury duration confirmed?).
2. Our own data is a legitimate, dated source: data/standings.json, data/scorers.json, data/assists.json, data/fixtures.json, data/matches_archive.json, data/goal_events.json, data/match_details.json. Numbers taken from them must be framed with their date («حتى <today's date>» or «بعد الجولة X»), because they describe NOW, not the day of the story.
3. Our archive: `data/articles.json` — find earlier AND later articles about the same club/player/topic. Link 1-3 of them inline as `<a href="/a/<id>">…</a>`; a later article about the same story becomes the «تطورات لاحقة» section.
4. If the web has nothing anymore (old story, dead links): expand ONLY from facts already in the body + our data files + our archive. A shorter honest article beats a padded one. Never add a quote, a fee, a contract length, an age or a statistic you did not read in a source or a data file.

### C. Rewrite the body — 500-700 words, HTML
Use `<p>` and `<h2>` (and `<ul>` where a list is natural). Fixed structure — skip a section only when the sources truly give nothing for it:
1. Lead paragraph: the news in two sentences (what, who, when).
2. `<h2>ماذا حدث؟</h2>` — the announcement/event with the exact date and who announced it.
3. `<h2>الخلفية</h2>` — the situation BEFORE (previous contract/status/standing, how the story developed over the preceding weeks).
4. `<h2>ماذا قالت المصادر؟</h2>` — attributed paraphrases, naming each outlet («بحسب موقع في الجول»), distinguishing المؤكد رسميًا from المنسوب إلى تقارير. «بحسب تقارير صحفية» at most once and only when outlets cannot be named.
5. `<h2>الأرقام</h2>` — age/position/appearances/goals/minutes/standings/dates that the sources or our data files support; each number dated.
6. `<h2>لماذا يهم الخبر؟</h2>` — what it means for the club/player/competition; competition for the position; squad impact.
7. `<h2>ما التالي؟</h2>` — next match, deadline, expected decision (from data/matches.json or fixtures when it exists).
8. `<h2>تطورات لاحقة</h2>` — ONLY if a later article in our archive or a later source shows how the story moved on since publication (with links).
VALUE CHECK before saving: every paragraph adds information the previous ones did not; nothing repeats the title; the reader who finishes knows what/when/why/numbers/next/confirmed-vs-reported. Delete any paragraph that only rephrases.

### D. Update the record (keep the URL and identity intact)
- KEEP unchanged: `article_id`, `image_url`, `image_credit`, `pub_date`, `pub_ts`, `author`, `fb_post`, `kind`/`match_id` if present, and the item's POSITION in the list.
- `title`: keep it unless it is longer than 70 characters — then shorten to 45-65 chars with the same meaning (no clickbait).
- `summary`: 1-2 sentences, may be improved.
- `body`: the new HTML.
- `sources`: list of {"name": "<outlet / official account>", "url": "<decoded URL>", "note": "<what it confirmed>"} for every source you actually read (2-4). Official statements first. If you found none, use an empty list — do not fabricate.
- `faq`: 2-3 {"q", "a"} pairs readers search for (e.g. «متى ينتهي عقد X؟», «كم هدفًا سجل X هذا الموسم؟», «هل رحل X عن النادي؟») — every answer is a fact stated in the body.
- `updated_ts` = `TZ=Africa/Cairo date -Iseconds` (shown on the page as «آخر تحديث» and used as the sitemap lastmod) and `upgraded_ts` = the same value (marks the article done for the picker).
- Write data/articles.json back with ensure_ascii=False, indent=2. Keep the JSON valid.

### E. Verify and commit this article
1. `python build_site.py` must succeed; check that `dist/a/<id>.html` contains `<h2>`, the «المصادر» block (when sources exist) and «أسئلة شائعة».
2. Word count check: `python -c "import json,re;a=[x for x in json.load(open('data/articles.json',encoding='utf-8'))['results'][0]['items'] if str(x['article_id'])=='<id>'][0];print(len(re.sub('<[^>]+>',' ',a['body']).split()))"` → must be 500-700 (a little under is acceptable when sources are scarce; over 750 is not).
3. `git add data/articles.json && git commit -m "Yalla Score: upgrade article <id> - <short english topic> (<before>w -> <after>w)"`

## Finish
`git pull --rebase origin main && git push origin main` (retry once on rejection). Do NOT touch media/ files, do NOT re-post to Facebook, do NOT create new articles.

## Output
End with a table: article_id | title | words before → after | sources found | sections written — plus any article you skipped and why (e.g. "no source and body too thin to expand honestly").
