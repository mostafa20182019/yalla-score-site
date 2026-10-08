This is an automated run on a GitHub Actions runner. The user is not present — execute autonomously, make reasonable choices, and note them in your output.

**This is a ONE-SHOT run: when you stop, the process is killed.** There is no wakeup to wait for and no later retry inside this run. If a command fails, retry it immediately (up to 3 times); if it still fails, finish with an explicit report naming what failed. NEVER end your turn saying you will wait or continue later.

You are writing ONE original Arabic **«الجولة بالأرقام»** article for "Yalla Score" (يلا سكور): a review of a completed league round built ENTIRELY from our own data. The facts pack is at `$BRIEF_JSON` (made by `round_brief.py`); competition and round are in `$COMP` and `$ROUND`.

**Why this article type exists (read it — it decides what a good article is):** Google indexes the pages that carry what only we have — our standings readings, our predictions, our analysis — and declines rewritten news that a hundred outlets already published. This article is valuable exactly as far as it says things no other site can: how OUR model's frozen predictions did, who moved in OUR strength rating (Elo), and what the round's numbers show together. Lean on those. A paragraph that any news site could have written adds nothing.

## Setup
1. `git config user.name "yalla-score-bot" && git config user.email "actions@users.noreply.github.com"`
2. `git pull --rebase origin main`
3. Read `$BRIEF_JSON` fully. Then read data/articles.json and STOP (print "already covered, skipped") if any article has a source whose `note` equals the pack's `round_key`.

## THE HARD RULE ON NUMBERS — enforced by the publisher, not by trust
Every number in the title, summary, body and FAQ must be one of the pack's numbers. **Do not compute new ones**: no percentages the pack does not carry, no sums or averages of your own, no "the third straight win" unless the pack says so. Dates are allowed only when the pack carries them (the round's days, the results' days, the next round's days). `python article_put.py --check --data-brief "$BRIEF_JSON" /tmp/draft.json` lists every number that is not in the pack — **fix the text until it passes; never "fix" it by dropping a true sentence's number for a vaguer invented one.** No press research: this article's story is our data. Never state a fact that is not in the pack (injuries, transfers, coaches' words).

## Structure — 500-750 words, HTML <p>/<h2>/<ul>/<li>/<a>
1. **Lead (1 paragraph, no heading):** the round in its sharpest numbers — the one pattern that defines it (e.g. away wins vs home wins, goals, the leader's lead). Name the competition and the round.
2. `<h2>نتائج الجولة</h2>` — a `<ul>` of every result: «<a href="{url}">الفريق أ 2-0 الفريق ب</a>». Then one sentence on the biggest margin.
3. `<h2>ماذا تغيّر في الترتيب؟</h2>` — ONLY if `table` is not null: the leader and his points, the gap to second, the top of the table, who is unbeaten / still winless, the bottom. Link the full table: `links.standings`. If `table` is null, skip the section entirely (the published table is not the table after this round).
4. `<h2>من صعد ومن هبط في تقييم القوة؟</h2>` — the Elo risers and fallers with before → after, and the top 5. Explain Elo in ONE plain sentence (a rating that rewards beating strong teams and weighs the margin). Say where it DISAGREES with the table if it does (e.g. a club level on points but rated higher) — that is our angle. Link `links.analysis`.
5. `<h2>كيف أدّت توقعات يلا سكور؟</h2>` — ONLY if `predictions` is not null: n / hits / exact scores, the best call (the probability we gave), the biggest surprise (the low probability we gave to what happened). **Misses are stated as plainly as hits — that is the site's rule.** Say the predictions were frozen before kickoff and link the full record `links.predictions`.
6. `<h2>هدافو الدوري</h2>` — the pack's scorers (name, club, goals).
7. `<h2>ما التالي؟</h2>` — the next round's dates and 2-4 of its fixtures with their links; say our predictions for them appear on each match page before kickoff. Link `links.fixtures`.

Tone: a clear sports analyst, not a press release. Every paragraph adds information the previous one did not. Team names exactly as the pack writes them.

## Article record — `/tmp/draft.json`, published with `article_put.py`
- `title`: 45-70 chars, starts with «الجولة {round} من {competition_ar} بالأرقام:» followed by the round's headline fact (shorten the competition name if needed, e.g. «الدوري المصري»).
- `summary`: 1-2 sentences. `body`: the HTML above. `author` = "مصطفى عبدالسلام"
- `pub_date` = `TZ=Africa/Cairo date +%F`, `pub_ts` = `TZ=Africa/Cairo date -Iseconds`
- NO `match_id`, NO `kind` (this is not a match piece).
- `sources`: EXACTLY two entries — the pack's `data_source` object copied VERBATIM (its `note` is the dedup key), and the match-data credit `{"name": "بيانات المباريات — <provider>", "url": "<links.fixtures>", "note": "النتائج والترتيب"}` where provider is `365scores` for the Egyptian, Turkish and Saudi leagues and `football-data.org` for the European ones.
- `faq`: 2-3 {"q","a"} a reader searches after a round («من يتصدر الدوري المصري بعد الجولة 5؟», «كم توقعًا أصاب نموذج يلا سكور في الجولة؟»); every answer's numbers are pack numbers.
- `image_url` + `image_credit`: the same rules as every article (CC BY / CC BY-SA / CC0 / PD; no rival colours; the living-story test). Prefer an already-vetted media/ photo of the round's LEADER or of the stadium of a match in the round, reusing its credit verbatim from data/articles.json or data/media_credits.json; never a file with no recorded credit. Last resort: `https://yallascore.site/media/ph-pitch.svg` with an empty credit.
- `fb_post`: line 1 = the title; 4-6 short lines with the round's key numbers (all from the article); «التفاصيل الكاملة على الموقع 👇»; the article URL; 2-4 hashtags starting #يلا_سكور. Plain text with real newlines. **USER RULE 2026-10-08: the post never carries the betting disclaimer - do not write «ليست نصيحة للمراهنة» (or any «للمراهنة» wording) in `fb_post`; it belongs in the article body only, and the publish tool refuses an fb_post that contains it.** A prediction line in the post is just the numbers: «🤖 نموذج يلا سكور: X 42% · تعادل 25% · Y 33%». The URL needs the id, which only the insert gives you: publish with the line `https://yallascore.site/a/ID`, then replace ID (step 3 below).

## Publish
1. `python article_put.py --check --data-brief "$BRIEF_JSON" /tmp/draft.json` — must print `ok:`. Fix and re-check until it does.
2. `python article_put.py --new --data-brief "$BRIEF_JSON" /tmp/draft.json` — prints the new article id. **If it exits 2 (D1 refused), the draft is parked under drafts/: commit it and report — that is a success.**
3. Put the real id in the post: write `/tmp/fb.json` = `{"fb_post": "<the post with ID replaced>"}` and run `python article_put.py --update <id> /tmp/fb.json`.
4. `python build_site.py` and check that dist/a/<id>.html exists and contains the title.
5. `git add data/articles.json` (plus `media/<file>` if you saved a new photo, plus `drafts/` if step 2 parked the draft); commit "Yalla Score: round article - <competition> round <n> by the numbers"; `git pull --rebase origin main && git push origin main` (retry once on rejection).

## Output
End with a short report: title, word count, how many pack numbers were used, whether the guard refused anything on the first check (and what), the image + licence, URL https://yallascore.site/a/<id> — or "already covered, skipped" with the reason.
