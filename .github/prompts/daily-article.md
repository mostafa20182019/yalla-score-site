This is an automated scheduled run on a GitHub Actions runner. The user is not present — execute autonomously, make reasonable choices, and note them in your output.

You are publishing ONE original Arabic news article about Egyptian football on the "Yalla Score" (يلا سكور) static site. The current directory is a checkout of the repo (main branch). Pushing to main gets deployed to https://yallascore.site by the separate "Publish Yalla Score" workflow — the CI pipeline dispatches it automatically after you finish, so do NOT wait for or verify the live deploy.

Python deps (requirements.txt + googlenewsdecoder + pillow) are already installed by the workflow.

## Setup (do this first)
1. `git config user.name "yalla-score-bot" && git config user.email "actions@users.noreply.github.com"`
2. `git pull --rebase origin main` (a data-refresh job commits back to the repo every ~15 min).

## APPROVED REFERENCE STYLE (user reviewed and approved on 2026-08-02 — replicate it)
Reference article "ياسر إبراهيم يوافق على تجديد عقده مع الأهلي وسط اهتمام سعودي":
- Story chosen because 3 independent sources agreed within hours; conflicting-rumor stories were deliberately skipped.
- 5 paragraphs, ~300 words, neutral news tone, "بحسب تقارير صحفية" attribution phrasing, no invented quotes/numbers/contract lengths, closes with context about the player/club.
- Image: the exact player named in the story, CC BY 4.0 from Wikimedia Commons, downloaded to media/, with an Arabic image_credit line naming subject, author and license.

## Hard constraints (protect the site's Google AdSense eligibility)
- NEVER copy or closely paraphrase text from news sites (يلا كورة، في الجول، كووورة، المصري اليوم...). Facts are free; wording is not. Write 100% original Arabic prose.
- ONE article per run, and ONLY if there is a genuinely NEW, noteworthy story not already covered. If nothing new/noteworthy, make NO changes and end the run reporting "no new story".
- Images MUST be freely licensed (CC BY / CC BY-SA / CC0 / public domain from Wikimedia Commons). Never press photos, Getty/agency images, or official club logos/crests.
- The image MUST be topically relevant: prefer (in order) a free photo of the exact player/coach mentioned in the story, then the club's stadium/team photo, then a relevant Egyptian stadium (e.g. Cairo International Stadium). Generic foreign stadiums are NOT acceptable.
- CLUB COLOURS MUST MATCH THE STORY: never illustrate a story about club X with a crowd or kit in club Y's colours. Red shirts read as الأهلي, so a red-clad crowd is WRONG on a Zamalek story — including Egypt NT crowds (Egypt also plays in red). Zamalek = white, Al Ahly = red. Identify the dominant shirt colour and reject on mismatch no matter how good the licence.
- THE PHOTO MUST SHOW THE NAMED PERSON: a story about player X must use a photo of player X himself — a photo of a DIFFERENT player in the same club kit is WRONG. The Commons file NAME or file DESCRIPTION must explicitly name the player; generic "Ahly player" identification is NOT acceptable. If no free photo of the named player exists, fall back IN THIS ORDER: (1) the named CLUB's stadium or a clearly club-identified scene (tifo/banner), (2) a relevant Egyptian stadium — and write the credit line for what the photo ACTUALLY shows. Never guess identity from kit colours alone.
- BEWARE NAME CLASHES: Egyptian football has many same-name players (e.g. إبراهيم عادل: an Ahly academy youngster AND a famous international abroad are different people). Rules: (a) never write a player's career history from your own recollection of the name — state only biography the fetched sources state about THIS story's player; (b) read the sources' qualifiers (ناشئ / الشاب / فريق الشباب / قطاع الناشئين); (c) if sources disagree on a basic attribute, say so or omit it; (d) when the story is about a namesake, add one sentence distinguishing him; (e) in a name-clash story the obvious Commons hit is probably the WRONG person.
- UNIQUE media/ FILENAME per article: pick a filename that does not already exist in media/. If `git status` shows your new image as M (modified) instead of ?? (new), you just overwrote another article's photo — pick another name.

## SCOPE — news only
Match previews and post-match reports are handled by a SEPARATE task. Do NOT write preview-style ("موعد ومعاينة") or report-style ("انتهت.. النتيجة") pieces about matches of the covered clubs — transfer news, statements, injuries, crises etc. are yours. If today's only story is a match itself, report "no new story". NOTE: a same-day preview/report by the other task does NOT block a news article on a different topic — dedup is per topic, not per day.

## Steps
1. Find candidate news from the last ~24h: fetch Google News RSS for several queries (الدوري المصري، الأهلي، الزمالك، منتخب مصر), e.g. https://news.google.com/rss/search?q=<urlencoded>&hl=ar&gl=EG&ceid=EG:ar. Decode article links with googlenewsdecoder and read at least 2 independent sources to confirm the core facts agree; skip stories where reports contradict each other.
2. Read data/articles.json and verify the story is NOT already covered (compare topics/titles of recent items — the same topic may have been covered yesterday under a different headline).
3. Write the article in Arabic: title (~60-90 chars), summary (1-2 sentences), body as HTML paragraphs (<p>...</p>, 250-450 words), author "فريق التحرير", pub_date = today in Africa/Cairo (`TZ=Africa/Cairo date +%F`).
4. Image via Wikimedia Commons API (commons.wikimedia.org/w/api.php, list=search srnamespace=6, then prop=imageinfo&iiprop=url|size|extmetadata to verify LicenseShortName is CC BY / CC BY-SA / CC0 / Public domain).
   - Quality is mandatory: at least ~800px wide; never tiny crops from group photos. For huge originals request a thumbnail via &iiurlwidth=1280 (only standard thumb widths like 1280/1920 are accepted).
   - ALWAYS OPEN THE DOWNLOADED IMAGE WITH THE Read TOOL AND LOOK AT IT BEFORE PUBLISHING. Check: correct subject, sharp, right club colours, face visible, nothing embarrassing.
   - HERO CROP CHECK: the article page renders the image with object-fit:cover; object-position:50% 18%; max-height 400px at up to ~1544px wide. Simulate that crop with PIL at 1544x400 AND 390x400 and LOOK at both — the player's head must never be sliced. For portrait/square sources, build a ~2.1:1 canvas: paste the photo centered over a blurred+darkened enlarged copy of itself (pillarbox), then re-check.
   - If the image looks sideways, rotate the pixels and view again. A gentle contrast/colour/sharpness enhance (~1.1-1.2) is fine for CC/PD as long as attribution stays.
   - Save into media/ with a short descriptive ascii filename, prefer <1 MB. Set image_url = "https://yallascore.site/media/<filename>" and image_credit = Arabic attribution: "صورة: <الموضوع> — <المصور/المصدر>، رخصة <License> (ويكيميديا كومنز)".
5. Add the article to data/articles.json: new article_id = max(int(existing ids)) + 1 (some ids may be strings — cast), insert as FIRST item in results[0].items. Keep JSON valid, ensure_ascii=False, indent=2.
6. Run `python build_site.py` and verify dist/a/<new_id>.html exists and references the new image filename and an a-credit figcaption.
7. Commit + push: `git add data/articles.json media/<file>` ; commit message "Yalla Score: original article - <short english topic> + free relevant image"; `git pull --rebase origin main` then `git push origin main` (retry the pull+push once if rejected — a data-refresh commit may land in between).

## Output
End with a short report: article title, source headlines used, image chosen + license, expected URL https://yallascore.site/a/<id> — or "no new story, skipped".
