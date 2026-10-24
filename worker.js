// Yalla Score edge worker.
// - fetch: serve the static site (dist/) exactly as before via the ASSETS binding.
// - scheduled: Cloudflare cron (exact, reliable) triggers the GitHub Action
//   `publish.yml` through the workflow_dispatch API, so data refreshes every
//   30 minutes even though GitHub's own free-tier cron is best-effort/delayed.
//   Requires a `GH_TOKEN` secret on the Worker (fine-grained PAT with
//   Actions: Read & write on mostafa20182019/yalla-score-site).
// - /health + the 15-minute watchdog live in health.js (see its header).

import { healthResponse, watchdog } from "./health.js";
import { pushApi } from "./push.js";
// live Facebook posts (goal / VAR / lineup) for the Egyptian scope - see its header;
// needs the Worker secret FB_PAGE_TOKEN, a no-op without it
import { livePosts, lineupPosts, postScope, curatedLive, goalFallbacks } from "./liveposts.js";

// Live-scores edge endpoint (/live.json): proxies 365scores' current-games
// feed with a 30s edge cache, so every visitor polls US (cheap, same-origin)
// and 365scores sees at most ~2 requests/minute regardless of traffic.
// Fail-empty by design: any upstream problem returns {games:[]} and the
// static site simply behaves as before (15-min refresh).
const LIVE_COMPS = "552,78,649,7,11,17,25,35,572,624,588,7016,573,627"; // EGY,TUR,KSA,PL,PD,SA,BL1,FL1,UCL,CAF-CL,AFCON-Q,UNL,UEL,CAF-CC

const S365_HEADERS = {
  "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
  "Accept": "application/json, text/plain, */*",
  "Accept-Language": "ar,en;q=0.9",
  "Origin": "https://www.365scores.com",
  "Referer": "https://www.365scores.com/",
};

const DETAIL_CAP = 12;   // per cache-miss ceiling on game/ detail calls
// 365scores competitions whose live games get detail calls FIRST (Egyptian
// league + CAF CL + AFCON qualifiers, where مصر plays) — the rest fill the
// remaining cap slots. These are also always fetched individually beside a
// healthy multi reply (the AS Port x Zamalek partial-degradation lesson).
const DETAIL_FIRST = new Set([552, 624, 588, 627]);   // + the Confederation Cup (Egyptian clubs)

// half-time: measured live on 2026-08-23 (Hull x Man Utd) - during the break
// statusText AND shortStatusText are the bare word "شوط" with gameTimeDisplay
// frozen at 45'; in play they are "الشوط الأول/الثاني" and "1"/"2". So the
// break test is EXACT equality with the bare word - a substring would match
// every in-play status too. The استراحة/half-time/HT checks stay as tolerance
// for other wordings. "نهاية الشوط الأول" is the transitional wording right
// after the HT whistle (FULL phrase only — "نهاية الشوط الثاني" is full-time,
// not a break).
function halfTime(g) {
  const stx = (g.statusText || "").trim(), ssx = (g.shortStatusText || "").trim();
  const st = `${stx} ${ssx} ${g.gameTimeDisplay || ""}`;
  return stx === "شوط" || ssx === "شوط"
    || stx.includes("نهاية الشوط الأول") || ssx.includes("نهاية الشوط الأول")
    || st.includes("استراح") || /half\s*-?\s*time/i.test(st) || /\bHT\b/.test(st);
}

// minute fields for a LIVE game object (list item or detail game — same shape):
// min = display text, gt = numeric minute for the client-side minute clock
// (LIVE_JS advances it locally between polls), hf = half (45+/90+ cap)
// a goal's MINUTE is a number («63», «45+2»). The break label is not one:
// on 2026-10-24 a score-only goal first seen during the break (Pyramids 3-0
// El Merrikh Bentiu) went out as «الدقيقة استراحة», and the card drew the word
// unshaped in its minute chip. No minute beats a wrong one.
const MINUTE_RE = /^\d+(\+\d+)?['′]?$/;   // «70'» / «45+2'» as the feed writes them
const goalMinute = (g) => MINUTE_RE.test(g.min || "") ? g.min : null;

function liveFields(g) {
  const ht = halfTime(g);
  return {
    min: ht ? "استراحة" : (g.gameTimeDisplay || ""),
    gt: !ht && g.gameTime > 0 ? g.gameTime : 0,
    hf: (g.shortStatusText || "").trim() === "2" ? 2 : 1,
  };
}

// One game/ detail call. 2026-09-02 (Ceramica x Modern Sport): the games/current
// LIST lagged this endpoint by ~2 minutes — a 63' goal was listed while the
// list still said 1-0 at 61'. So the detail is the source of ALL numbers for a
// live game (score, minute, half, goals) and the list only discovers which
// games are live. Returns null on any failure → the caller keeps list values.
// Scorer lines mirror fetch_data._goal_rows(): goal events only (VAR-disallowed
// excluded), own-goal side flip, and the reconciliation guard against THIS
// reply's score — a list that doesn't add up is never published.
async function gameDetail(gid) {
  try {
    const r = await fetch(
      `https://webws.365scores.com/web/game/?appTypeId=5&langId=27&gameId=${gid}`,
      { headers: S365_HEADERS, cf: { cacheTtl: 12, cacheEverything: true } });
    if (!r.ok) return null;
    const game = (await r.json()).game || {};
    const home = game.homeCompetitor || {}, away = game.awayCompetitor || {};
    if (home.score == null || home.score < 0 || away.score == null || away.score < 0) return null;
    const hs = Math.round(home.score), as_ = Math.round(away.score);
    const sg = game.statusGroup;
    const out = {
      hs, as: as_,
      // apply score/status only when the detail carries a known status group
      // (3 live / 4 ended); goals are usable either way
      apply: sg === 3 || sg === 4,
      live: sg === 3,
      ...(sg === 3 ? liveFields(game) : { min: "", gt: 0, hf: 0 }),
      goals: null,
    };
    const members = {};
    for (const m of game.members || []) members[m.id] = m.name;
    const goals = [];
    for (const ev of game.events || []) {
      const et = ev.eventType || ev.type || {};
      const nm = typeof et === "object" ? (et.name || "") : String(et);
      if (!nm.includes("هدف")) continue;
      if (nm.includes("ملغ") || nm.includes("ألغي") || nm.includes("الغي")) continue;
      let cid = ev.competitorId;
      if (cid == null) cid = ev.num === 1 ? home.id : -1;
      const player = members[ev.playerId]
        || (ev.player && ev.player.name) || ev.playerName;
      if (!player) continue;
      let minute = "";
      const gt = Math.trunc(Number(ev.gameTime));
      if (gt > 0) {
        const add = Math.trunc(Number(ev.addedTime || 0));
        minute = add > 0 ? `${gt}+${add}` : String(gt);
      }
      const sub = `${nm} ${ev.subTypeName || ""}`;
      const tag = sub.includes("عكس") ? "عكسية" : (sub.includes("جزاء") ? "ج" : "");
      goals.push({ s: cid === home.id ? "h" : "a", p: player, m: minute, t: tag });
    }
    const cnt = () => [goals.filter(g => g.s === "h").length,
                       goals.filter(g => g.s === "a").length];
    let [ch, ca] = cnt();
    if (ch !== hs || ca !== as_) {
      for (const g of goals) if (g.t === "عكسية") g.s = g.s === "h" ? "a" : "h";
      [ch, ca] = cnt();
    }
    if (ch === hs && ca === as_ && goals.length) out.goals = goals;
    return out;
  } catch (e) { return null; }
}

async function fetchGames(url) {
  const r = await fetch(url, {
    headers: S365_HEADERS,
    cf: { cacheTtl: 12, cacheEverything: true },
  });
  if (!r.ok) return null;
  return (await r.json()).games || [];
}

// The upstream read, as DATA (games + flags). liveScores() wraps it in the
// Response the pre-store code served; refreshLive() feeds it into the D1 store.
async function liveScoresData() {
  const base =
    "https://webws.365scores.com/web/games/current/?appTypeId=5" +
    "&langId=27&timezoneName=Africa/Cairo&showOdds=false";
  const games = [];
  const upcoming = [];    // scheduled games of the live-post scope (lineup window), see liveposts.js
  const wantDetail = [];  // {idx, gid, live, first} — live games + just-ended with a goal
  let ok = false, src = "multi", dt = 0;
  try {
    let raw = null;
    try { raw = await fetchGames(`${base}&competitions=${LIVE_COMPS}`); } catch (e) { raw = null; }
    // 365scores intermittently serves the multi-competition query a degraded
    // near-empty reply (2026-09-01: ONE scheduled PL game, HTTP 200, while a
    // live Egyptian match was in play — single-competition queries kept
    // returning everything). A healthy multi reply carries today's whole
    // window (~dozens of games), so a tiny list = degraded → refetch split
    // per competition and merge (lists are disjoint, no dedup needed).
    if (!raw || raw.length < 5) {
      src = "split";
      const per = await Promise.all(LIVE_COMPS.split(",").map(c =>
        fetchGames(`${base}&competitions=${c}`).catch(() => null)));
      raw = [];
      ok = false;
      for (const list of per) if (list) { ok = true; raw.push(...list); }
    } else {
      ok = true;
      // Partial degradation (2026-09-04): the multi-comp reply was a healthy
      // size yet MISSED the just-ended CAF CL game (AS Port x Zamalek, sg 4)
      // that the single-comp query returned - so /live.json had no final
      // score for it and the match page stayed on the baked "مباشر" dashes.
      // The Egyptian-scope comps are what the site is FOR: always fetch them
      // individually too and merge by game id (2 extra edge-cached calls).
      const extra = await Promise.all([...DETAIL_FIRST].map(c =>
        fetchGames(`${base}&competitions=${c}`).catch(() => null)));
      const seen = new Set(raw.map(g => g.id));
      for (const list of extra) for (const g of list || []) {
        if (!seen.has(g.id)) { seen.add(g.id); raw.push(g); src = "multi+egy"; }
      }
    }
    for (const g of raw) {
        const sg = g.statusGroup;            // 2 scheduled / 3 live / 4 ended
        if (sg === 2 && g.id && g.startTime) {
          const u = { id: g.id, c: g.competitionId || 0, h: (g.homeCompetitor || {}).name || "",
                      a: (g.awayCompetitor || {}).name || "", start: Date.parse(g.startTime) };
          if (u.start && postScope(u)) upcoming.push(u);
        }
        if (sg !== 3 && sg !== 4) continue;  // live + finished (final score)
        const h = g.homeCompetitor || {}, a = g.awayCompetitor || {};
        if (h.score == null || h.score < 0 || a.score == null || a.score < 0) continue;
        // half-time / minute fields: see halfTime() + liveFields() above
        const lf = sg === 3 ? liveFields(g) : { min: "", gt: 0, hf: 0 };
        const c = g.competitionId || 0;
        games.push({
          id: g.id || 0,
          h: h.name || "", a: a.name || "",
          hs: Math.round(h.score), as: Math.round(a.score),
          live: sg === 3,
          // min/gt/hf: minute text + numeric minute + half for the client-side
          // minute clock (LIVE_JS advances it locally between polls)
          min: lf.min, gt: lf.gt, hf: lf.hf,
          // 365scores competition id — LIVE_JS disambiguates same-name clubs
          // across leagues with it (الأهلي = Al Ahly Egypt AND Al-Ahli Saudi)
          c,
        });
        // detail call: EVERY live game (fresher score/minute than the list)
        // plus just-ended games with a goal the static build hasn't caught yet
        if (g.id && (sg === 3 || (g.justEnded === true && (h.score > 0 || a.score > 0)))) {
          wantDetail.push({ idx: games.length - 1, gid: g.id, live: sg === 3,
                            first: DETAIL_FIRST.has(c) });
        }
    }
    // priority: live before just-ended, Egyptian/CAF before the rest, capped —
    // each detail call is itself edge-cached 12s so bursts collapse upstream.
    // Games past the cap simply keep their list values (the old behaviour).
    wantDetail.sort((x, y) => ((y.live ? 2 : 0) + (y.first ? 1 : 0))
                            - ((x.live ? 2 : 0) + (x.first ? 1 : 0)));
    await Promise.all(wantDetail.slice(0, DETAIL_CAP).map(async (w) => {
      const d = await gameDetail(w.gid);
      if (!d) return;
      const g = games[w.idx];
      // override ONLY games the LIST says are live: a match the list has
      // already ended must never come back to life because the detail
      // endpoint is slower to record the final whistle (live data may move
      // forward from another source, never backwards). Just-ended games get
      // their goals only.
      if (d.apply && w.live) {
        g.hs = d.hs; g.as = d.as; g.live = d.live;
        g.min = d.min; g.gt = d.gt; g.hf = d.hf;
        dt++;
      }
      if (d.goals) g.goals = d.goals;
    }));
  } catch (e) { /* fail-empty */ }
  return { games, ok, src, dt, upcoming };
}

function liveResponse(data, extra = {}) {
  // an upstream failure must NOT be cached - visitors would all go quiet
  // for minutes mid-match; mark it uncacheable instead
  return new Response(JSON.stringify({ ...data, ts: Date.now(), ...extra }), {
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": data.ok ? "public, max-age=10, s-maxage=5" : "no-store",
    },
  });
}

async function liveScores() {
  return liveResponse(await liveScoresData());
}

/* ==========================================================================
 * The live store (2026-09-13) — a goal, once seen, is REMEMBERED.
 *
 * User's diagnosis, exactly right: «هو معندوش حاجة ثابتة تقول إن فيه هدف».
 * Until now every visit re-read 365scores (a cold /live.json waited on the
 * list + up to 12 detail calls, and an upstream hiccup meant dashes), and a
 * goal existed nowhere on our side until the match was over.
 *
 * Now D1 keeps one row per game the upstream lists today (live_state: score,
 * minute, half, status, the goal list) plus an append-only goal log
 * (live_goals: one row per goal the moment it appears; a VAR reversal marks
 * it cancelled rather than deleting it). /live.json is served FROM the store
 * in milliseconds and the store is refreshed from 365scores in the
 * background - at most once per REFRESH_SEC across all visitors - and by a
 * one-minute cron when nobody is watching.
 *
 * The user's firm rule («لا نعرض رقمًا قد يكون خطأ») is kept by age: a stored
 * row is served only while upstream re-confirmed it within LIVE_TTL_SEC;
 * older rows are not shown (the page falls back to dashes exactly as before).
 * The store never overrides upstream: it is memory, not authority. This does
 * not make 365scores faster - it removes OUR waiting and OUR forgetting.
 * ======================================================================== */
const REFRESH_SEC  = 12;   // background refresh cadence while visitors poll
const LIVE_TTL_SEC = 90;   // a snapshot older than this is not served
const STATE_KEEP_MS = 2 * 24 * 3600 * 1000;   // drop state rows nobody lists any more
// One refresh writes: the snapshot row, the games that CHANGED, and any new
// goals. An unchanged game costs nothing - see storeRead for how freshness is
// proved without touching every row.
const STORE_SCHEMA = [
  "CREATE TABLE IF NOT EXISTS live_state (game_id INTEGER PRIMARY KEY, c INTEGER, h TEXT, a TEXT, " +
  "hs INTEGER, as_ INTEGER, live INTEGER, min TEXT, gt INTEGER, hf INTEGER, goals TEXT, " +
  "first_seen INTEGER, seen_at INTEGER, changed_at INTEGER)",
  "CREATE TABLE IF NOT EXISTS live_goals (game_id INTEGER, seq INTEGER, side TEXT, player TEXT, " +
  "minute TEXT, tag TEXT, score_h INTEGER, score_a INTEGER, c INTEGER, h TEXT, a TEXT, " +
  "seen_at INTEGER, cancelled INTEGER DEFAULT 0, cancelled_at INTEGER, PRIMARY KEY (game_id, seq))",
  "CREATE TABLE IF NOT EXISTS live_meta (k TEXT PRIMARY KEY, v TEXT)",
  // the post-match report queue - see THE REPORT QUEUE below
  "CREATE TABLE IF NOT EXISTS report_queue (game_id INTEGER PRIMARY KEY, c INTEGER, h TEXT, a TEXT, " +
  "hs INTEGER, as_ INTEGER, ended_at INTEGER, due_at INTEGER, tries INTEGER DEFAULT 0, " +
  "done_at INTEGER, done_why TEXT)",
];
let storeReady = false;
async function ensureStore(env) {
  if (storeReady || !env.DB) return;
  await env.DB.batch(STORE_SCHEMA.map(q => env.DB.prepare(q)));
  // live_goals.held (2026-10-24): a score-only goal waits one refresh before
  // it is posted. Added after the table existed, so it is an ALTER on its
  // own - a batch would fail as a whole on «duplicate column» every run after
  // the first.
  try { await env.DB.prepare("ALTER TABLE live_goals ADD COLUMN held INTEGER DEFAULT 0").run(); } catch (e) { /* already there */ }
  storeReady = true;
}

/* ==========================================================================
 * THE REPORT QUEUE (2026-09-13) - a curated club's match gets its report
 * because the match ENDED, not because a slot came round.
 *
 * The site published a preview for 16 of the last 16 curated matches and a
 * report for 8. Nothing was broken: four fixed slots a day, one article per
 * slot, previews and reports competing for the same four - and a match that
 * ended at 23:00 had one chance the next afternoon before its window closed.
 *
 * The final whistle is a fact this Worker already learns every minute: the
 * live store sees a game go from live to ended. So it writes the match into
 * report_queue with a due time ~30 minutes later (long enough for the goal
 * list and the lineups to reach data/, short enough to still be news), and
 * the one-minute cron dispatches match-article.yml when that time comes.
 *
 * The queue row closes when a report for that match_id exists in `articles`
 * (D1 is the writer for articles since 2026-09-10), so a retry cannot produce
 * a second one. It gives up after REPORT_TRIES and leaves the match to the
 * four slots, which stay exactly as they were - a safety net, no longer the
 * only path. The dispatch carries kind=report and NO match_id: match_brief.py
 * --pick --kind report re-decides at run time and owns the daily cap, so
 * there is one place where "how many reports today" is answered.
 * ======================================================================== */
const REPORT_DELAY_MS = 30 * 60 * 1000;   // final whistle -> dispatch
const REPORT_RETRY_MS = 25 * 60 * 1000;   // and again, if no report appeared
const REPORT_TRIES    = 3;                // then leave it to the fixed slots
const REPORT_KEEP_MS  = 3 * 24 * 3600 * 1000;   // purge queue rows this old
// mirrors match_brief.REPORT_DAILY_CAP - here only to avoid dispatching a run
// that would decline anyway; match_brief.py is the authority.
const REPORT_DAILY_CAP = 4;

// The curated clubs the report queue and the live posts share live in
// liveposts.js (CURATED_LIVE / curatedLive) - one list, imported above.
const cairoDate = (ms) => new Intl.DateTimeFormat("en-CA", {
  timeZone: "Africa/Cairo", year: "numeric", month: "2-digit", day: "2-digit",
}).format(new Date(ms));

const REPORT_INS = "/*rq_ins*/ INSERT OR IGNORE INTO report_queue (game_id, c, h, a, hs, as_, " +
  "ended_at, due_at, tries) VALUES (?,?,?,?,?,?,?,?,0)";

const KICKOFF_MAX_MIN = 5;   // a game first seen in play past this minute gets no «انطلقت» post
const LS_PREV_CHUNK = 80;    // game ids per ls_prev query: D1 allows 100 bound parameters (2026-10-18)
const GOAL_INS = "/*lg_ins*/ INSERT OR IGNORE INTO live_goals (game_id, seq, side, player, minute, tag, " +
  "score_h, score_a, c, h, a, seen_at, held) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)";
// The same insert, applied only while the game's state row is still the one
// this refresh diffed against (changed_at unchanged). Two refreshes overlap
// across isolates - the one-minute cron and a visitor's background refresh -
// and both diff the same "before"; without this the second one logged the
// same goal under the next seq and posted it again (2026-10-17, Kitara x
// Al Ahly: «هدف! 1 - 2» at 82' and again at 83').
const GOAL_INS_IF = "/*lg_ins*/ INSERT OR IGNORE INTO live_goals (game_id, seq, side, player, minute, tag, " +
  "score_h, score_a, c, h, a, seen_at, held) SELECT ?,?,?,?,?,?,?,?,?,?,?,?,? " +
  "WHERE EXISTS (SELECT 1 FROM live_state WHERE game_id = ? AND changed_at IS ?)";
const META_SET = "/*lm_set*/ INSERT INTO live_meta (k, v) VALUES (?, ?) ON CONFLICT(k) DO UPDATE SET v = excluded.v";

async function storeRead(env, now) {
  // ONE ROW. This used to scan live_state on every serve, which measured at
  // 113 rows a request (two days of games) against a free tier of 5M a day -
  // about 40% of the quota spent on re-assembling an answer the refresh had
  // already assembled, and on 2026-09-16 the read limit ran out and stopped
  // article publishing. So the snapshot now carries the payload it describes,
  // exactly as the write side was fixed the day before: one row per refresh
  // instead of one per game.
  //
  // live_state is still the record - storeApply diffs against it and the goal
  // log hangs off it. It is simply no longer on the serving path.
  const metaRows = await env.DB
    .prepare("/*ls_snap*/ SELECT v FROM live_meta WHERE k = 'snapshot'").all();
  const meta = ((metaRows.results || [])[0]) || null;
  let rr = ((metaRows.meta || {}).rows_read) || 0;
  let snap = null;
  try { snap = meta && meta.v ? JSON.parse(meta.v) : null; } catch (e) { snap = null; }
  const last = snap && snap.ts ? Number(snap.ts) : 0;
  // the age rule, once for the whole answer: serve only while the last
  // upstream read is young enough to still be true
  const live = last && (now - last) <= LIVE_TTL_SEC * 1000;
  let games = live && Array.isArray(snap.games) ? snap.games : [];
  if (live && !Array.isArray(snap.games) && Array.isArray(snap.ids)) {
    // A snapshot written by the previous version: it names the ids but not the
    // games. Rather than serve dashes for the minute until the next refresh,
    // fall back to the old scan once. Nothing writes this shape any more, so
    // this path disappears on its own.
    const rows = await env.DB.prepare("/*ls_rows*/ SELECT * FROM live_state").all();
    rr += ((rows.meta || {}).rows_read) || 0;
    const ids = new Set(snap.ids);
    games = (rows.results || []).filter(r => ids.has(r.game_id)).map(r => ({
      id: r.game_id, h: r.h, a: r.a, hs: r.hs, as: r.as_, live: !!r.live,
      min: r.min || "", gt: r.gt || 0, hf: r.hf || 0, c: r.c || 0,
      ...(r.goals ? { goals: JSON.parse(r.goals) } : {}),
    }));
  }
  return { games, last, rr };
}

// the same goal on both sides: side + player + minute
const goalKey = (g) => `${g.s}|${g.p || ""}|${g.m || ""}`;

// Compare the fresh upstream read with the stored rows, write what changed,
// append goal events. Returns {upserts, events} for the log and the tests.
async function storeApply(env, fresh, now) {
  const ids = fresh.games.map(g => g.id).filter(Boolean);
  const prev = {};
  // D1 refuses a statement with more than 100 bound parameters ("too many
  // SQL variables"). The day's list crossed 100 games on 2026-10-18 (109 with
  // the Confederation Cup and the Sunday leagues) and every refresh threw
  // here for two hours - /live.json fell back to the direct read and no
  // kick-off / half-time / goal post went out. Read the previous rows in
  // chunks well under the cap.
  for (let i = 0; i < ids.length; i += LS_PREV_CHUNK) {
    const part = ids.slice(i, i + LS_PREV_CHUNK);
    const q = `/*ls_prev*/ SELECT * FROM live_state WHERE game_id IN (${part.map(() => "?").join(",")})`;
    const r = await env.DB.prepare(q).bind(...part).all();
    for (const row of r.results || []) prev[row.game_id] = row;
  }
  const stmts = [];
  let upserts = 0, events = 0, ended = 0;
  const posts = [], cancels = [];   // goals discovered LIVE + VAR reversals -> liveposts.js
  const hts = [], ends = [], kos = [];   // half-time / final whistle / kick-off -> liveposts.js
  const goalRow = (g, seq, ev, p = null, held = 0) => (p
    ? env.DB.prepare(GOAL_INS_IF).bind(g.id, seq, ev.s, ev.p || null, ev.m || null, ev.t || null, g.hs, g.as, g.c, g.h, g.a, now, held,
                                       g.id, p.changed_at == null ? null : Number(p.changed_at))
    : env.DB.prepare(GOAL_INS).bind(g.id, seq, ev.s, ev.p || null, ev.m || null, ev.t || null, g.hs, g.as, g.c, g.h, g.a, now, held));
  for (const g of fresh.games) {
    if (!g.id) continue;
    const p = prev[g.id];
    const oldGoals = p && p.goals ? JSON.parse(p.goals) : [];
    const newGoals = g.goals || [];
    if (!p) {
      // first sight of this game today: the goals already on the board are
      // events ONLY when the detail names them (scorer + minute). A bare score
      // with no list - a match first seen at 2-2 - seeds nothing: we cannot say
      // when those goals fell, and nameless untimed rows would only pollute the
      // log. Goals from here on are caught by the score diff below.
      newGoals.forEach((ev, i) => { stmts.push(goalRow(g, i + 1, ev)); events += 1; });
    } else {
      // the open rows of this game's log in one read: the next seq, and the
      // NAMELESS rows the score-only path below logged while the detail
      // lagged - a named goal that arrives later fills one of those instead
      // of becoming a second row (2026-10-17: Betis x Barcelona's half-time
      // post listed «لامين يامال 10'» twice)
      // (every row counts for the next seq - a cancelled seq is never reused;
      // only live rows can be named)
      const logRows = ((await env.DB.prepare("/*lg_open*/ SELECT seq, side, player, minute, cancelled, held FROM live_goals WHERE game_id = ? ORDER BY seq")
        .bind(g.id).all()).results) || [];
      let seq = logRows.reduce((m, r) => Math.max(m, Number(r.seq) || 0), 0);
      const openRows = logRows.filter(r => !r.cancelled);
      const nameless = { h: openRows.filter(r => r.side === "h" && !r.player),
                         a: openRows.filter(r => r.side === "a" && !r.player) };
      // THE HOLD (user, 2026-10-24, twice: first «انشر الهدف الذي لم تسمّه
      // التفاصيل بعد تأكيد التحديث التالي», then - on a Tottenham 77' post with
      // no scorer - «عايز كله يكون فيه اسم مسجل الهدف»). A goal the detail
      // names is posted at once. A goal known only from the score going up is
      // logged with held = 1 and NOT posted, by anyone, until a detail names
      // it: the name IS the confirmation, and the post carries it. A score
      // that falls back first cancels a row nobody ever saw (Pyramids 2-1). A
      // goal the feed never names is never a goal post - the half-time and
      // full-time posts still carry the score.
      // the live-post guard (liveposts.js): a goal is POSTED only while the
      // score itself went up since the last refresh, and a reversal is posted
      // only when it went down. A re-attributed goal (new key, same score) or
      // a detail that failed this minute must never fake either.
      let up = (g.hs + g.as) - (p.hs + p.as_);
      // A fresh read with NO goal list at all (the detail was not fetched or
      // failed - e.g. an ended game the list did not flag justEnded) must go
      // by the score, never by keys: otherwise every logged goal "vanishes"
      // and is cancelled as a VAR reversal (found 2026-10-17 by the full-time
      // post, whose scorer lines came back empty).
      if (g.goals !== undefined && (newGoals.length || oldGoals.length)) {
        // the detail's goal list is the truth about WHICH goals: a new key is
        // an event, a vanished key is a VAR reversal
        const prevKeys = new Set(oldGoals.map(goalKey)), nextKeys = new Set(newGoals.map(goalKey));
        for (const ev of newGoals) if (!prevKeys.has(goalKey(ev))) {
          const open = ev.p && nameless[ev.s] && nameless[ev.s].length ? nameless[ev.s].shift() : null;
          if (open) {
            // the score-only path already logged this goal without a name:
            // name that row, no second row. Posted now if it was still held
            // (the name is the confirmation), never again if it already went out
            stmts.push(env.DB.prepare("/*lg_name*/ UPDATE live_goals SET player = ?, minute = ?, tag = ?, held = 0 WHERE game_id = ? AND seq = ?")
              .bind(ev.p, ev.m || null, ev.t || null, g.id, open.seq));
            events += 1;
            if (Number(open.held) && g.live) posts.push({ g, seq: open.seq, ev, at: stmts.length - 1 });
            continue;
          }
          seq += 1; stmts.push(goalRow(g, seq, ev, p)); events += 1;
          if (g.live && up > 0) { posts.push({ g, seq, ev, at: stmts.length - 1 }); up -= 1; }
        }
        for (const ev of oldGoals) if (!nextKeys.has(goalKey(ev))) {
          if (up < 0) { cancels.push({ g, ev }); up += 1; }
          stmts.push(env.DB.prepare("/*lg_cancel*/ UPDATE live_goals SET cancelled = 1, cancelled_at = ? " +
            "WHERE game_id = ? AND side = ? AND COALESCE(player,'') = ? AND COALESCE(minute,'') = ? AND cancelled = 0")
            .bind(now, g.id, ev.s, ev.p || "", ev.m || ""));
          events += 1;
        }
      } else {
        // no goal list on either side: go by the score alone
        for (const [side, d] of [["h", g.hs - p.hs], ["a", g.as - p.as_]]) {
          for (let i = 0; i < d; i++) {
            // held: a detail naming it posts it - see THE HOLD
            seq += 1; stmts.push(goalRow(g, seq, { s: side, m: goalMinute(g) }, p, 1)); events += 1;
          }
          if (d < 0) {   // the score went DOWN: cancel that side's latest live goal
            // (and liveposts.js edits its post, if one went out - a held row
            // never had one, so the edit finds nothing and does nothing)
            stmts.push(env.DB.prepare("/*lg_cancel_last*/ UPDATE live_goals SET cancelled = 1, cancelled_at = ? " +
              "WHERE game_id = ? AND side = ? AND cancelled = 0 AND seq = " +
              "(SELECT MAX(seq) FROM live_goals WHERE game_id = ? AND side = ? AND cancelled = 0)")
              .bind(now, g.id, side, g.id, side));
            events += 1;
            cancels.push({ g, ev: { s: side } });
          }
        }
      }
    }
    // THE FINAL WHISTLE: a game we saw live is not live any more. This is the
    // only moment we can be sure the match just ended (a game first seen
    // already finished never transitions - the four fixed slots cover that).
    if (p && p.live && !g.live && curatedLive(g)) {
      stmts.push(env.DB.prepare(REPORT_INS)
        .bind(g.id, g.c, g.h, g.a, g.hs, g.as, now, now + REPORT_DELAY_MS));
      ended += 1;
      ends.push({ g });
    }
    // THE HALF-TIME WHISTLE (2026-10-17): the first refresh that sees the
    // break (liveFields writes min = "استراحة") on a game we saw in play.
    // The lock in liveposts.js makes a repeat harmless, and `changed` below
    // rewrites the row at this transition so the next refresh does not look
    // like one.
    const breakNow = g.live && (g.min || "") === "استراحة", breakBefore = !!p && (p.min || "") === "استراحة";
    if (p && p.live && breakNow && !breakBefore && curatedLive(g)) hts.push({ g });
    // THE KICK-OFF (2026-10-18, user: «بوست عند بداية مباراة للفرق المميزة»):
    // an upcoming game has no state row (storeApply never stores sg 2), so the
    // start is the FIRST sight of a curated game in play, in its opening
    // minutes. The minute cap keeps a store that missed the start (a quiet
    // ten minutes, a cold isolate) from shouting «انطلقت» at 0-1 in the 20th.
    if (!p && g.live && (g.gt || 0) <= KICKOFF_MAX_MIN && (g.min || "") !== "استراحة" && curatedLive(g)) kos.push({ g });
    // The state row is written only when something MATERIAL changed. The
    // minute is deliberately not in that test (2026-09-17): it ticks for every
    // live game every minute, so including it cost one row write per live game
    // per minute - about 28k on a busy evening, against a free tier of 100k a
    // day that has already blocked article publishing twice this week.
    //
    // Nothing is lost by leaving it out. live_state exists to DIFF against
    // (new goal, VAR reversal, final whistle) and none of that needs the
    // clock; what visitors are served is the snapshot row below, which is
    // rewritten every refresh and carries the fresh minute. The row's own
    // min/gt/hf still update whenever anything else moves.
    // A refresh WITHOUT a usable goal list (the detail failed, or its events
    // still lag the list's score so the counts did not match) keeps the list
    // we already had. Writing null here is what duplicated goals: the next
    // detailed refresh saw an empty "before" and logged every goal on the
    // board again (2026-10-17, «لامين يامال 10'» twice at half-time).
    const goalsJson = g.goals === undefined ? (p && p.goals ? p.goals : null)
      : (newGoals.length ? JSON.stringify(newGoals) : null);
    const changed = !p || p.hs !== g.hs || p.as_ !== g.as || !!p.live !== !!g.live
      || (p.goals || null) !== goalsJson || breakNow !== breakBefore;
    if (changed) {
      // ... and only while the row is still the "before" this refresh read
      // (same race as GOAL_INS_IF: a slower overlapping refresh must not
      // write its stale picture over the one that already moved on)
      stmts.push(env.DB.prepare("/*ls_upsert*/ INSERT INTO live_state (game_id, c, h, a, hs, as_, live, min, gt, hf, goals, " +
        "first_seen, seen_at, changed_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(game_id) DO UPDATE SET " +
        "c=excluded.c, h=excluded.h, a=excluded.a, hs=excluded.hs, as_=excluded.as_, live=excluded.live, min=excluded.min, " +
        "gt=excluded.gt, hf=excluded.hf, goals=excluded.goals, seen_at=excluded.seen_at, changed_at=excluded.changed_at " +
        "WHERE live_state.changed_at IS ?")
        .bind(g.id, g.c, g.h, g.a, g.hs, g.as, g.live ? 1 : 0, g.min || "", g.gt || 0, g.hf || 0, goalsJson, now, now, now,
              p && p.changed_at != null ? Number(p.changed_at) : null));
      upserts += 1;
    }
    // an UNCHANGED game is no longer written at all - it is listed in the
    // snapshot below, which is one row for the whole refresh instead of one
    // per game (the 2026-09-15 quota wall)
  }
  // The snapshot IS the answer /live.json serves: one row, written once per
  // refresh, read once per request (see storeRead). `ids` stays for the
  // report queue and for anything that only needs to know what was listed.
  const payload = fresh.games.filter(g => g.id).map(g => ({
    id: g.id, h: g.h, a: g.a, hs: g.hs, as: g.as, live: !!g.live,
    min: g.min || "", gt: g.gt || 0, hf: g.hf || 0, c: g.c || 0,
    ...(g.goals && g.goals.length ? { goals: g.goals } : {}),
  }));
  stmts.push(env.DB.prepare(META_SET).bind("snapshot", JSON.stringify({
    ts: now, src: fresh.src, dt: fresh.dt,
    ids: payload.map(g => g.id), games: payload,
  })));
  stmts.push(env.DB.prepare("/*ls_purge*/ DELETE FROM live_state WHERE changed_at < ?")
    .bind(now - STATE_KEEP_MS));
  const res = [];
  for (let i = 0; i < stmts.length; i += 40) res.push(...(await env.DB.batch(stmts.slice(i, i + 40)) || []));   // D1 batch cap
  // a goal is posted only if ITS row was really written: the conditional
  // insert above reports 0 changes when an overlapping refresh got there
  // first (that refresh posted it), or when the seq already existed
  const applied = (i) => { const r = res[i]; return !(r && r.meta && r.meta.changes === 0); };
  return { upserts, events, ended, posts: posts.filter(x => x.at == null || applied(x.at)), cancels, hts, ends, kos };
}

// One refresh: upstream -> store. A failed upstream read changes nothing (the
// store keeps serving what it last confirmed, until LIVE_TTL ages it out).
let refreshing = null;
async function refreshLive(env) {
  if (refreshing) return refreshing;          // collapse concurrent triggers in this isolate
  refreshing = (async () => {
    const now = Date.now();
    const fresh = await liveScoresData();
    if (!fresh.ok) {
      await env.DB.prepare(META_SET).bind("last_fail", String(now)).run();
      return { ok: false };
    }
    const r = await storeApply(env, fresh, now);
    let fb = null;
    const fbDispatch = env.GH_TOKEN ? (inputs) => dispatchWorkflow(env, "fb-post.yml", inputs) : null;
    try { fb = await livePosts(env, r, fbDispatch); }     // after the batch: the store is the truth first
    catch (e) { console.log("live posts failed:", e && e.message); }
    if (fbDispatch && env.FB_PAGE_TOKEN) {
      // goal cards the runner never posted: the text, from the edge
      try { const gf = await goalFallbacks(env, now); if (gf.posted) console.log("goal fallbacks:", JSON.stringify(gf)); }
      catch (e) { console.log("goal fallbacks failed:", e && e.message); }
    }
    return { ok: true, upserts: r.upserts, events: r.events, ended: r.ended, n: fresh.games.length,
             fb, upcoming: fresh.upcoming || [] };
  })().finally(() => { refreshing = null; });
  return refreshing;
}

/* One tick of the report queue, called by the one-minute cron after the live
 * refresh. Closes rows whose report exists, dispatches at most ONE run per
 * tick (match-article.yml serialises runs anyway, and one match at a time is
 * how the writer works), and purges what it no longer needs. */
async function dueReports(env, now) {
  const out = { due: 0, closed: 0, dispatched: 0, gaveup: 0 };
  const rows = await env.DB.prepare(
    "/*rq_due*/ SELECT * FROM report_queue WHERE done_at IS NULL AND due_at <= ? " +
    "ORDER BY due_at LIMIT 5").bind(now).all();
  const list = rows.results || [];
  out.due = list.length;
  for (const r of list) {
    // already written (by this queue, by a fixed slot, or by hand)?
    const got = await env.DB.prepare(
      "/*rq_have*/ SELECT article_id FROM articles WHERE match_id = ? AND kind = 'report' LIMIT 1")
      .bind(String(r.game_id)).first();
    if (got) { await closeReport(env, r.game_id, now, "written"); out.closed += 1; continue; }
    if ((r.tries || 0) >= REPORT_TRIES) {
      await closeReport(env, r.game_id, now, "gave up - left to the fixed slots");
      out.gaveup += 1; continue;
    }
    if (out.dispatched) continue;                 // one dispatch per tick
    const cnt = await env.DB.prepare(
      "/*rq_today*/ SELECT COUNT(*) AS n FROM articles WHERE kind = 'report' AND pub_date = ?")
      .bind(cairoDate(now)).first();
    if (cnt && Number(cnt.n) >= REPORT_DAILY_CAP) {
      console.log("report queue: daily cap reached, not dispatching");
      break;                                      // try again after midnight
    }
    if (!env.GH_TOKEN) { console.log("report queue: no GH_TOKEN"); break; }
    const ok = await dispatchWorkflow(env, "match-article.yml", { kind: "report" });
    await env.DB.prepare(
      "/*rq_try*/ UPDATE report_queue SET tries = tries + 1, due_at = ? WHERE game_id = ?")
      .bind(now + REPORT_RETRY_MS, r.game_id).run();
    if (ok) out.dispatched += 1;
  }
  await env.DB.prepare("/*rq_purge*/ DELETE FROM report_queue WHERE ended_at < ?")
    .bind(now - REPORT_KEEP_MS).run();
  return out;
}

async function closeReport(env, gameId, now, why) {
  await env.DB.prepare(
    "/*rq_done*/ UPDATE report_queue SET done_at = ?, done_why = ? WHERE game_id = ?")
    .bind(now, why, gameId).run();
}

// /live.json from the store: instant when warm, background-refreshed when
// due, synchronous (the old path) only when cold or stale.
async function liveFromStore(env, ctx) {
  await ensureStore(env);
  const now = Date.now();
  let { games, last, rr } = await storeRead(env, now);
  const age = last ? (now - last) / 1000 : Infinity;
  if (age > LIVE_TTL_SEC) {
    // cold start or a stale store: fetch now, then serve what landed
    const r = await refreshLive(env);
    if (!r.ok && !games.length) return liveResponse({ games: [], ok: false, src: "store-cold" });
    let rr2;
    ({ games, last, rr: rr2 } = await storeRead(env, Date.now()));
    return liveResponse({ games, ok: true, src: "store-fresh" }, { age: 0, rr: rr + rr2 });
  }
  if (age > REFRESH_SEC && ctx && ctx.waitUntil) ctx.waitUntil(refreshLive(env));
  return liveResponse({ games, ok: true, src: "store" }, { age: Math.round(age), rr });
}

/* ==========================================================================
 * /admin/api — the admin page's door to D1.
 *
 * A browser cannot talk to D1: access is through a Worker binding (or an
 * account-wide API token, which would then be sitting in localStorage on a
 * laptop). So the Worker that already serves this site holds the binding and
 * exposes the few operations the admin page needs.
 *
 * FAIL CLOSED. Every route needs the x-admin-token header to match the
 * ADMIN_TOKEN Worker secret, and when that secret is not set the routes
 * answer 503 rather than being open. Cloudflare Access can be layered in
 * front later for a second factor; trusting its Cf-Access-* headers without
 * verifying the JWT would be security theatre, so that is deliberately not
 * done here.
 *
 * Writes go through the SAME rules as article_put.py: the id is allocated
 * inside the INSERT, and the unique index on (match_id, kind) refuses a
 * duplicate match piece.
 * ======================================================================== */

const ADMIN_ORIGINS = ["http://localhost:8123", "http://127.0.0.1:8123",
                       "https://yallascore.site"];

function corsHeaders(request) {
  const origin = request.headers.get("Origin") || "";
  const allow = ADMIN_ORIGINS.includes(origin) ? origin : ADMIN_ORIGINS[0];
  return {
    "Access-Control-Allow-Origin": allow,
    "Access-Control-Allow-Methods": "GET, POST, PUT, OPTIONS",
    "Access-Control-Allow-Headers": "content-type, x-admin-token",
    "Access-Control-Max-Age": "86400",
    "Vary": "Origin",
  };
}

function jsonReply(request, body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
      ...corsHeaders(request),
    },
  });
}

/* the json shape the admin page and data/articles.json both use */
const ART_FIELDS = ["title", "summary", "body", "author", "pub_date", "pub_ts",
                    "match_id", "kind", "image_url", "image_credit", "fb_post",
                    "updated_ts", "upgraded_ts"];

function words(html) {
  return (String(html || "").replace(/<[^>]+>/g, " ").trim().split(/\s+/)
          .filter(Boolean)).length;
}

/* official-post embeds (2026-09-13): the same host rule as store.embed_platform */
const EMBED_HOSTS = { "x.com": "x", "twitter.com": "x", "mobile.twitter.com": "x",
                      "instagram.com": "instagram", "facebook.com": "facebook",
                      "m.facebook.com": "facebook", "fb.watch": "facebook" };
function embedPlatform(u) {
  try {
    const h = new URL(String(u || ""));
    if (h.protocol !== "https:" || !h.pathname || h.pathname === "/") return null;
    return EMBED_HOSTS[h.hostname.toLowerCase().replace(/^www\./, "")] || null;
  } catch (e) { return null; }
}
let embedsReady = false;
async function ensureEmbeds(env) {
  if (embedsReady) return;
  await env.DB.prepare("CREATE TABLE IF NOT EXISTS article_embeds (article_id TEXT NOT NULL, " +
    "seq INTEGER NOT NULL, url TEXT NOT NULL, platform TEXT, PRIMARY KEY (article_id, seq))").run();
  embedsReady = true;
}
function badEmbeds(rec) {
  if (!("embeds" in rec)) return null;
  if (!Array.isArray(rec.embeds)) return "embeds must be a list of URLs";
  const bad = rec.embeds.filter(u => !embedPlatform(u));
  return bad.length ? `not an X/Instagram/Facebook post URL: ${bad[0]}` : null;
}

async function articleRow(env, id) {
  const a = await env.DB.prepare(
    "SELECT article_id, title, summary, body, author, pub_date, pub_ts, " +
    "match_id, kind, image_url, image_credit, fb_post, updated_ts, " +
    "upgraded_ts, words, thin FROM articles WHERE article_id = ?"
  ).bind(String(id)).first();
  if (!a) return null;
  await ensureEmbeds(env);
  const kids = await env.DB.batch([
    env.DB.prepare("SELECT name, url, note FROM article_sources WHERE article_id = ? ORDER BY seq").bind(String(id)),
    env.DB.prepare("SELECT q, a FROM article_faq WHERE article_id = ? ORDER BY seq").bind(String(id)),
    env.DB.prepare("SELECT url FROM article_embeds WHERE article_id = ? ORDER BY seq").bind(String(id)),
  ]);
  a.sources = kids[0].results || [];
  a.faq = kids[1].results || [];
  a.embeds = (kids[2].results || []).map(r => r.url);
  return a;
}

async function writeChildren(env, id, sources, faq, embeds) {
  const stmts = [
    env.DB.prepare("DELETE FROM article_sources WHERE article_id = ?").bind(id),
    env.DB.prepare("DELETE FROM article_faq WHERE article_id = ?").bind(id),
  ];
  if (embeds !== undefined) {
    await ensureEmbeds(env);
    stmts.push(env.DB.prepare("DELETE FROM article_embeds WHERE article_id = ?").bind(id));
    (embeds || []).filter(embedPlatform).forEach((u, i) => stmts.push(env.DB.prepare(
      "INSERT INTO article_embeds (article_id, seq, url, platform) VALUES (?, ?, ?, ?)"
    ).bind(id, i, u, embedPlatform(u))));
  }
  (sources || []).forEach((x, i) => stmts.push(env.DB.prepare(
    "INSERT INTO article_sources (article_id, seq, name, url, note) VALUES (?, ?, ?, ?, ?)"
  ).bind(id, i, x.name || null, x.url || null, x.note || null)));
  (faq || []).forEach((x, i) => stmts.push(env.DB.prepare(
    "INSERT INTO article_faq (article_id, seq, q, a) VALUES (?, ?, ?, ?)"
  ).bind(id, i, x.q || null, x.a || null)));
  await env.DB.batch(stmts);
}

/* the one-row change marker the BUILD reads before pulling every article
 * table (store.articles_sig on the python side, which bumps it the same way
 * from article_put.py). Every admin write replaces it, so a build whose
 * committed export still matches can skip the full pull. */
async function bumpArticlesSig(env) {
  await ensureStore(env);   // live_meta lives in the live store's schema
  await env.DB.prepare(META_SET).bind("articles_sig", crypto.randomUUID()).run();
}

/* ask GitHub to rebuild: writing to D1 makes the article EXIST, but the site
 * is static HTML - it only appears once publish.yml has rebuilt the pages.
 * reason=article marks the run uncancellable (it carries new content). */
async function dispatchWorkflow(env, workflow, inputs) {
  const r = await fetch(
    `https://api.github.com/repos/mostafa20182019/yalla-score-site/actions/workflows/${workflow}/dispatches`,
    {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${env.GH_TOKEN}`,
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
        "User-Agent": "yalla-score-worker",
      },
      body: JSON.stringify(inputs ? { ref: "main", inputs } : { ref: "main" }),
    }
  );
  const ok = r.status === 204 || r.ok;
  console.log("workflow dispatch:", workflow, r.status, ok ? "OK" : await r.text());
  return ok;
}

async function dispatchPublish(env) {
  if (!env.GH_TOKEN) return "no GH_TOKEN - publish not triggered";
  const ok = await dispatchWorkflow(env, "publish.yml", { reason: "article" });
  return ok ? "publish dispatched" : "publish dispatch failed";
}

async function adminApi(request, env, url) {
  if (request.method === "OPTIONS") {
    return new Response(null, { status: 204, headers: corsHeaders(request) });
  }
  if (!env.DB) {
    return jsonReply(request, { error: "D1 binding missing on the Worker" }, 503);
  }
  if (!env.ADMIN_TOKEN) {
    return jsonReply(request, {
      error: "ADMIN_TOKEN is not set on the Worker - the admin API is closed",
    }, 503);
  }
  if (request.headers.get("x-admin-token") !== env.ADMIN_TOKEN) {
    return jsonReply(request, { error: "bad or missing x-admin-token" }, 401);
  }

  const parts = url.pathname.replace(/^\/admin\/api\/?/, "").split("/");

  // GET /admin/api/articles — the list, WITHOUT bodies (403 bodies is ~800KB
  // and the list only shows titles)
  if (request.method === "GET" && parts[0] === "articles") {
    const { results } = await env.DB.prepare(
      "SELECT article_id, title, pub_date, pub_ts, author, image_url, kind, " +
      "match_id, words, thin, has_sources, has_faq, upgraded_ts FROM articles " +
      "ORDER BY CAST(article_id AS INTEGER) DESC"
    ).all();
    return jsonReply(request, { items: results || [] });
  }

  // GET /admin/api/article/<id> — the full record, for the edit form
  if (request.method === "GET" && parts[0] === "article" && parts[1]) {
    const a = await articleRow(env, parts[1]);
    return a ? jsonReply(request, a)
             : jsonReply(request, { error: "no such article" }, 404);
  }

  // POST /admin/api/article — publish a new one
  // kinds (2026-10-07): preview/report belong to a match; "analysis" is an
  // editor analysis for /insights («التحليلات») and needs no match.
  function badKind(rec) {
    const k = rec.kind || null;
    if (k && !["preview", "report", "analysis"].includes(k)) return "kind must be preview, report or analysis";
    if ((k === "preview" || k === "report") && !rec.match_id) return "a preview/report needs its match_id";
    if (rec.match_id && !k) return "a match_id needs a kind";
    return null;
  }
  if (request.method === "POST" && parts[0] === "article") {
    let rec;
    try { rec = await request.json(); }
    catch (e) { return jsonReply(request, { error: "body is not json" }, 400); }
    for (const f of ["title", "summary", "body", "author", "pub_date"]) {
      if (!String(rec[f] || "").trim()) {
        return jsonReply(request, { error: `missing ${f}` }, 400);
      }
    }
    const bk = badKind(rec);
    if (bk) return jsonReply(request, { error: bk }, 400);
    const be = badEmbeds(rec);
    if (be) return jsonReply(request, { error: be }, 400);
    const w = words(rec.body);
    const cols = ART_FIELDS.concat(["words", "thin", "has_sources", "has_faq"]);
    const vals = ART_FIELDS.map(f => (rec[f] === undefined || rec[f] === "" ? null : rec[f]))
      .concat([w, w < 300 ? 1 : 0,
               (rec.sources || []).length ? 1 : 0, (rec.faq || []).length ? 1 : 0]);
    let row;
    try {
      // the id is allocated INSIDE the statement, so two saves at the same
      // moment cannot be handed the same one
      row = await env.DB.prepare(
        "INSERT INTO articles (article_id, " + cols.join(", ") + ", as_of) " +
        "SELECT CAST(COALESCE(MAX(CAST(article_id AS INTEGER)), 0) + 1 AS TEXT), " +
        cols.map(() => "?").join(", ") + ", date('now') FROM articles " +
        "RETURNING article_id"
      ).bind(...vals).first();
    } catch (e) {
      const m = String(e);
      if (/UNIQUE|constraint/i.test(m)) {
        return jsonReply(request, {
          error: "that match already has a piece of this kind",
        }, 409);
      }
      return jsonReply(request, { error: m }, 500);
    }
    const id = String(row.article_id);
    await writeChildren(env, id, rec.sources, rec.faq, rec.embeds || []);
    await bumpArticlesSig(env);   // before the dispatch, so that build sees it
    return jsonReply(request, {
      article_id: id, words: w, thin: w < 300,
      publish: await dispatchPublish(env),
    }, 201);
  }

  // PUT /admin/api/article/<id> — edit an existing one. Only the fields in the
  // body are touched, so a partial save cannot blank a column it never sent.
  if (request.method === "PUT" && parts[0] === "article" && parts[1]) {
    const id = String(parts[1]);
    let rec;
    try { rec = await request.json(); }
    catch (e) { return jsonReply(request, { error: "body is not json" }, 400); }
    const exists = await env.DB.prepare(
      "SELECT article_id FROM articles WHERE article_id = ?").bind(id).first();
    if (!exists) return jsonReply(request, { error: "no such article" }, 404);

    const be2 = badEmbeds(rec);
    if (be2) return jsonReply(request, { error: be2 }, 400);
    if ("kind" in rec && rec.kind && rec.kind !== "analysis") {
      // the admin form only ever switches news <-> analysis; a match piece's
      // kind is owned by the match-article pipeline (its unique index)
      return jsonReply(request, { error: "only kind=analysis (or empty) can be set here" }, 400);
    }
    const sets = [], vals = [];
    for (const f of ART_FIELDS) {
      if (f in rec) { sets.push(`${f} = ?`); vals.push(rec[f] === "" ? null : rec[f]); }
    }
    let w = null;
    if ("body" in rec) {
      w = words(rec.body);
      sets.push("words = ?", "thin = ?");
      vals.push(w, w < 300 ? 1 : 0);
    }
    if ("sources" in rec) { sets.push("has_sources = ?"); vals.push((rec.sources || []).length ? 1 : 0); }
    if ("faq" in rec) { sets.push("has_faq = ?"); vals.push((rec.faq || []).length ? 1 : 0); }
    if (sets.length) {
      try {
        await env.DB.prepare(
          `UPDATE articles SET ${sets.join(", ")} WHERE article_id = ?`
        ).bind(...vals, id).run();
      } catch (e) {
        const m = String(e);
        if (/UNIQUE|constraint/i.test(m)) {
          return jsonReply(request, {
            error: "that match already has a piece of this kind",
          }, 409);
        }
        return jsonReply(request, { error: m }, 500);
      }
    }
    if ("sources" in rec || "faq" in rec || "embeds" in rec) {
      // sources/faq are always rewritten together (as before); embeds only
      // when the request carries the key, so a text-only edit keeps them
      await writeChildren(env, id, rec.sources, rec.faq, "embeds" in rec ? rec.embeds : undefined);
    }
    await bumpArticlesSig(env);   // before the dispatch, so that build sees it
    return jsonReply(request, {
      article_id: id, words: w, publish: await dispatchPublish(env),
    });
  }

  return jsonReply(request, { error: `no route for ${request.method} ${url.pathname}` }, 404);
}

// The match-article slots, on the Cairo clock. Exported for the test.
// 10:00 and 15:00 added 2026-10-07 (previews now cover the featured clubs).
const MATCH_SLOTS = ["10:00", "13:00", "15:00", "17:00", "20:00", "23:30"];
const MATCH_CRONS = new Set(["0 7,8,9,10,12,13,14,16,17 * * *", "30 19,20 * * *"]);
/* /data/bundle (2026-09-24, step 3): the site's working data - the gzip bundle
 * data_store.py pushes into Workers KV after every publish run - for the
 * machines that hold no Cloudflare token: the user's laptop (the Oracle copy
 * loads from it), the secret-less test job and a local checkout. Read-only,
 * public (it is the same football data the pages show), edge-cached for 60 s
 * so a burst of pulls costs one KV read. 404 until the first push. */
async function dataBundle(env, ctx) {
  if (!env.DATA) return new Response("no data store bound", { status: 404 });
  const cache = caches.default;
  const key = new Request("https://yallascore.site/data/bundle");
  const hit = await cache.match(key);
  if (hit) return hit;
  const blob = await env.DATA.get("bundle-v1", "arrayBuffer");
  if (!blob) return new Response("the data store is empty", { status: 404 });
  const res = new Response(blob, {
    headers: {
      "content-type": "application/octet-stream",
      "cache-control": "public, max-age=0, s-maxage=60",
    },
  });
  if (ctx && ctx.waitUntil) ctx.waitUntil(cache.put(key, res.clone()));
  return res;
}

export function matchSlotCairo(date) {
  const hm = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Africa/Cairo", hour: "2-digit", minute: "2-digit", hour12: false,
  }).format(date).replace(/^24/, "00");
  return MATCH_SLOTS.includes(hm) ? hm : null;
}

// A missing file must not be remembered for a week. root-extras/_headers gives
// /media/* a 7-day Cache-Control (crests 30 days), and Workers static assets put
// that header on the 404 too, so Cloudflare cached a "not found" for a photo
// that the next deploy brought (2026-10-18: article 847's crest image, built one
// commit before the file was pushed, stayed a 404 at the edge after it arrived).
// Any error answer leaves with no-store: the page's onerror placeholder covers
// the moment, and the first request after the deploy sees the file.
function assetResponse(res) {
  if (res.status < 400) return res;
  const out = new Response(res.body, res);
  out.headers.set("cache-control", "no-store");
  return out;
}

export default {
  async fetch(request, env, ctx) {
    // Permanent redirect from any non-canonical host — the legacy
    // *.workers.dev URL and the www. variant — to the bare custom domain.
    // One canonical URL keeps old links working and avoids duplicate
    // content in Google after the 2026-08-03 domain move.
    const url = new URL(request.url);
    const canonical = "yallascore.site";
    // 2026-10-18: the SCHEME is part of the canonical too. http://yallascore.site/
    // answered 200 (Cloudflare's "Always Use HTTPS" was never switched on for
    // the Worker's custom domain), so Bing kept the previous owner's http root
    // as a second, excluded copy of the site. http or www -> one 301 to https
    // on the bare host (two hops would cost the old links a second redirect).
    if (url.hostname !== canonical || url.protocol !== "https:") {
      url.hostname = canonical;
      url.protocol = "https:";
      return Response.redirect(url.toString(), 301);
    }
    if (url.pathname === "/admin/api" || url.pathname.startsWith("/admin/api/")) {
      return adminApi(request, env, url);
    }
    if (url.pathname === "/push/subscribe" || url.pathname === "/push/unsubscribe") {
      return pushApi(request, env, url);          // web push (push.js)
    }
    if (url.pathname === "/health") {
      return healthResponse(env, ctx);
    }
    if (url.pathname === "/data/bundle") {
      return dataBundle(env, ctx);
    }
    if (url.pathname === "/live.json") {
      const cache = caches.default;
      const key = new Request("https://yallascore.site/live.json");
      const hit = await cache.match(key);
      if (hit) return hit;
      // the D1-backed store when the binding exists; the direct upstream
      // read otherwise (local dev without D1, and the pre-store tests).
      // A store that throws must not become a 500 on every page that polls
      // this endpoint: on 2026-09-15 the D1 daily write quota ran out and
      // /live.json answered HTTP 500 instead of dashes. Fall back to reading
      // upstream directly, then to fail-empty.
      let res;
      try {
        res = env.DB ? await liveFromStore(env, ctx) : await liveScores();
      } catch (e) {
        console.log("live store unavailable:", e && e.message);
        try {
          res = await liveScores();
        } catch (e2) {
          res = liveResponse({ games: [], ok: false, src: "store-down" });
        }
      }
      if ((res.headers.get("cache-control") || "").includes("s-maxage")) {
        ctx.waitUntil(cache.put(key, res.clone()));
      }
      return res;
    }
    return assetResponse(await env.ASSETS.fetch(request), url);
  },

  async scheduled(event, env, ctx) {
    // cron 5: keep the live store warm when nobody is polling, so the first
    // visitor of a quiet evening is served from memory too. One upstream
    // list read a minute; needs no GitHub token.
    if (event.cron === "* * * * *") {
      if (!env.DB) return;
      let r = { ok: false };
      try {
        await ensureStore(env);
        r = await refreshLive(env);
      } catch (e) {          // a quota wall or an unreachable D1 skips a beat
        console.log("live store refresh failed:", e && e.message);
        // keep the LAST failure where /health can show it (2026-10-18: the
        // store went quiet for two hours and the only trace was a log line
        // nobody can read from outside); one small write per failing minute
        try {
          await env.DB.prepare(META_SET).bind("last_error",
            JSON.stringify({ ts: Date.now(), msg: String(e && e.message || e).slice(0, 300) })).run();
        } catch (e2) { /* the store may be the thing that is down */ }
        return;
      }
      console.log("live store refresh:", JSON.stringify({ ...r, upcoming: (r.upcoming || []).length }));
      // the official XI, 45-80 minutes before an Egyptian-scope kick-off (liveposts.js)
      try {
        const lp = await lineupPosts(env, r.upcoming || [], Date.now(), S365_HEADERS,
                                     env.GH_TOKEN ? (inputs) => dispatchWorkflow(env, "fb-post.yml", inputs) : null);
        if (lp.due) console.log("xi posts:", JSON.stringify(lp));
      } catch (e) {
        console.log("xi posts failed:", e && e.message);
      }
      // and the matches that ended: the report queue (see THE REPORT QUEUE)
      try {
        const q = await dueReports(env, Date.now());
        if (q.due) console.log("report queue:", JSON.stringify(q));
      } catch (e) {
        console.log("report queue failed:", e && e.message);   // never break the live refresh
      }
      return;
    }
    // cron 1 (the 15-minute refresh) also runs the watchdog. In waitUntil and
    // behind its own catch: a watchdog failure must never cost a dispatch.
    if (event.cron === "1,16,31,46 * * * *" && env.DB && env.ASSETS && ctx && ctx.waitUntil) {
      ctx.waitUntil(watchdog(env).catch(e => console.log("watchdog failed:", e && e.message)));
    }
    if (!env.GH_TOKEN) {
      console.log("GH_TOKEN secret not set yet; skipping workflow dispatch");
      return;
    }
    // four crons share this handler — event.cron says which one fired (each
    // string must equal its line in wrangler.toml [triggers] EXACTLY):
    //   cron 2          -> daily-article.yml
    //   cron 3 / cron 4 -> match-article.yml, but only when the CAIRO clock is
    //                      on one of the four slots (the crons list both the
    //                      summer and the winter UTC hour of every slot)
    //   anything else   -> publish.yml (the 15-minute refresh)
    let workflow = "publish.yml";
    // The free plan allows five cron strings and all five are taken, so two
    // daily jobs ride on existing firings (2026-10-22, user: more spotlight on
    // the global clubs' results):
    //   22:16 UTC (00:16 / 01:16 Cairo) -> fb-post.yml daycard=results, the
    //   night's results card; Monday 06:00 UTC -> round-article.yml for a
    //   European league's completed round (competition=auto-europe), beside
    //   the daily article that hour.
    const when = new Date(event.scheduledTime || Date.now());
    if (event.cron === "1,16,31,46 * * * *" && when.getUTCHours() === 22 && when.getUTCMinutes() === 16) {
      await dispatchWorkflow(env, "fb-post.yml", { daycard: "results" });
    }
    if (event.cron === "0 6,8,11,14,17,19 * * *" && when.getUTCDay() === 1 && when.getUTCHours() === 6) {
      await dispatchWorkflow(env, "round-article.yml", { competition: "auto-europe" });
    }
    if (event.cron === "0 6,8,11,14,17,19 * * *") {
      workflow = "daily-article.yml";
    } else if (MATCH_CRONS.has(event.cron)) {
      const slot = matchSlotCairo(new Date(event.scheduledTime || Date.now()));
      if (!slot) {
        console.log("match-article cron fired off-slot (DST twin) - skipping");
        return;
      }
      workflow = "match-article.yml";
    }
    // 204 = accepted; anything else is logged for debugging (visible in
    // Cloudflare dashboard -> Worker -> Logs).
    await dispatchWorkflow(env, workflow, null);
  },
};
