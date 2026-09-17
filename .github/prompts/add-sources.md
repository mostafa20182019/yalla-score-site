# Add the missing sources to published articles

`/editorial` tells the reader, in writing, that a news article on this site names the sources it was built from. A number of articles published between 1 and 10 September carry none. This run closes that gap — and ONLY that gap.

**You are not rewriting anything.** The body, the title, the summary, the image and the FAQ stay exactly as they are. You are finding the sources the story was actually built from and recording them.

## The rule that matters more than the count

A source you add must be a real page, at a real outlet, that actually covers **this** story. If you cannot find two independent ones, **skip the article and say so in the report**. An invented or loosely-related source is worse than an empty field: the empty field is a gap, the invented one is a lie on a page that promises honesty. Nobody is counting how many you did.

## Steps

1. Build the queue: `python upgrade_pick.py --sources-only --count ${SOURCES_COUNT:-20} --json > /tmp/queue.json` and read it. Empty → print "nothing to source" and stop. Work them **in order**, one at a time.

2. For each article, read its full record from `data/articles.json` (`results[0].items`, match `article_id` as a string). Read the BODY — you need to know what the article actually claims before you can say where it came from.

3. Find the sources:
   - Search Google News RSS for the story, e.g. `https://news.google.com/rss/search?q=<urlencoded Arabic query>&hl=ar&gl=EG&ceid=EG:ar`. Build the query from the specific names in the article (player + club + the event), not from the headline verbatim.
   - The article is 1–2 weeks old, so add the date range when the query is noisy, and prefer results published within a few days of `pub_date`.
   - **Decode every link with `googlenewsdecoder`** — a `news.google.com/rss/articles/...` URL is not a source, it is a redirect. Record the publisher URL.
   - Open each candidate and confirm it covers the same story: the same player, the same club, the same claim. A story about the same club on the same day is NOT the same story.
   - Two **independent** outlets, counted by domain: two links from filgoal.com are one source. Never our own site.
   - When the story IS the club's or federation's own announcement, that official page or verified account is a valid source on its own; mark it `"official": true`.

4. Save, sources only:
   ```bash
   printf '%s' '{"sources": [...]}' > /tmp/draft.json
   python article_put.py --update <id> /tmp/draft.json
   ```
   - The draft carries `sources` and nothing else. Do NOT include `body`, `faq`, `title` or anything you did not change — a partial update touches only what it carries, and that is deliberate.
   - Each source is `{"name": "<outlet>", "url": "<decoded article URL>", "note": "<what this source confirms>"}`. The note is short and specific: «تأكيد مدة الغياب», «تصريح المدير الرياضي», not «تفاصيل الخبر».
   - If `article_put.py` refuses, read the message and fix the draft; never work around it.

5. Commit after EACH article, so a failure half way keeps what is done:
   ```bash
   git add data/articles.json && git commit -m "Yalla Score: sources for article <id> - <short english topic>"
   ```

6. When the queue is done (or you have skipped the rest), `git pull --rebase origin main && git push`.

## Report

End with a table: `article_id | sources found | outlets | skipped and why`. State the skips plainly — an article nobody else covered is a fact about the story, not a failure of the run.
