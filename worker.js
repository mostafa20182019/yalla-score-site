// Yalla Score edge worker.
// - fetch: serve the static site (dist/) exactly as before via the ASSETS binding.
// - scheduled: Cloudflare cron (exact, reliable) triggers the GitHub Action
//   `publish.yml` through the workflow_dispatch API, so data refreshes every
//   30 minutes even though GitHub's own free-tier cron is best-effort/delayed.
//   Requires a `GH_TOKEN` secret on the Worker (fine-grained PAT with
//   Actions: Read & write on mostafa20182019/yalla-score-site).
// - /health + the 15-minute watchdog live in health.js (see its header).

import { healthResponse, watchdog } from "./health.js";

// Live-scores edge endpoint (/live.json): proxies 365scores' current-games
// feed with a 30s edge cache, so every visitor polls US (cheap, same-origin)
// and 365scores sees at most ~2 requests/minute regardless of traffic.
// Fail-empty by design: any upstream problem returns {games:[]} and the
// static site simply behaves as before (15-min refresh).
const LIVE_COMPS = "552,78,649,7,11,17,25,35,572,624,588,7016"; // EGY,TUR,KSA,PL,PD,SA,BL1,FL1,UCL,CAF-CL,AFCON-Q,UNL

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
const DETAIL_FIRST = new Set([552, 624, 588]);

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
  return { games, ok, src, dt };
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

// The 11 curated clubs as 365scores spells them (the live feed is langId=27,
// so every name is Arabic - these are NOT the football-data names in
// matches.json). Scope repeats build_site's: الأهلي is also a Saudi club and
// a Dubai club, so the Egyptian three count only in the Egyptian league (552)
// and the CAF Champions League (624); طرابزون سبور only in the Turkish league.
const EGY_LIVE_COMPS = [552, 624];
const CURATED_LIVE = [
  { t: "الأهلي", comps: EGY_LIVE_COMPS },
  { t: "الزمالك", comps: EGY_LIVE_COMPS },
  { t: "بيراميدز", comps: EGY_LIVE_COMPS },
  { t: "طرابزون سبور", comps: [78] },
  { t: "ريال مدريد", comps: null },
  { t: "برشلونة", comps: null },
  { t: "مانشستر يونايتد", comps: null },
  { t: "مانشستر سيتي", comps: null },
  { t: "أرسنال", comps: null },
  { t: "ليفربول", comps: null },
  { t: "تشيلسي", comps: null },
];
// same normalisation match_brief._norm uses, so آرسنال matches أرسنال
const arNorm = (x) => (x || "").replace(/[أإآ]/g, "ا").replace(/ة/g, "ه").replace(/ى/g, "ي");
function curatedLive(g) {
  const ha = arNorm(g.h) + "|" + arNorm(g.a);
  return CURATED_LIVE.some(cl => ha.includes(arNorm(cl.t))
                              && (!cl.comps || cl.comps.includes(g.c)));
}
const cairoDate = (ms) => new Intl.DateTimeFormat("en-CA", {
  timeZone: "Africa/Cairo", year: "numeric", month: "2-digit", day: "2-digit",
}).format(new Date(ms));

const REPORT_INS = "/*rq_ins*/ INSERT OR IGNORE INTO report_queue (game_id, c, h, a, hs, as_, " +
  "ended_at, due_at, tries) VALUES (?,?,?,?,?,?,?,?,0)";

const GOAL_INS = "/*lg_ins*/ INSERT OR IGNORE INTO live_goals (game_id, seq, side, player, minute, tag, " +
  "score_h, score_a, c, h, a, seen_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)";
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
  if (ids.length) {
    const q = `/*ls_prev*/ SELECT * FROM live_state WHERE game_id IN (${ids.map(() => "?").join(",")})`;
    const r = await env.DB.prepare(q).bind(...ids).all();
    for (const row of r.results || []) prev[row.game_id] = row;
  }
  const stmts = [];
  let upserts = 0, events = 0, ended = 0;
  const goalRow = (g, seq, ev) => env.DB.prepare(GOAL_INS)
    .bind(g.id, seq, ev.s, ev.p || null, ev.m || null, ev.t || null, g.hs, g.as, g.c, g.h, g.a, now);
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
      const seqRow = await env.DB.prepare("/*lg_seq*/ SELECT COALESCE(MAX(seq),0) AS s FROM live_goals WHERE game_id = ?")
        .bind(g.id).first();
      let seq = seqRow ? Number(seqRow.s) : 0;
      if (newGoals.length || oldGoals.length) {
        // the detail's goal list is the truth about WHICH goals: a new key is
        // an event, a vanished key is a VAR reversal
        const prevKeys = new Set(oldGoals.map(goalKey)), nextKeys = new Set(newGoals.map(goalKey));
        for (const ev of newGoals) if (!prevKeys.has(goalKey(ev))) {
          seq += 1; stmts.push(goalRow(g, seq, ev)); events += 1;
        }
        for (const ev of oldGoals) if (!nextKeys.has(goalKey(ev))) {
          stmts.push(env.DB.prepare("/*lg_cancel*/ UPDATE live_goals SET cancelled = 1, cancelled_at = ? " +
            "WHERE game_id = ? AND side = ? AND COALESCE(player,'') = ? AND COALESCE(minute,'') = ? AND cancelled = 0")
            .bind(now, g.id, ev.s, ev.p || "", ev.m || ""));
          events += 1;
        }
      } else {
        // no goal list on either side: go by the score alone
        for (const [side, d] of [["h", g.hs - p.hs], ["a", g.as - p.as_]]) {
          for (let i = 0; i < d; i++) {
            seq += 1; stmts.push(goalRow(g, seq, { s: side, m: g.min || null })); events += 1;
          }
          if (d < 0) {   // VAR took a goal back: cancel that side's latest live goal
            stmts.push(env.DB.prepare("/*lg_cancel_last*/ UPDATE live_goals SET cancelled = 1, cancelled_at = ? " +
              "WHERE game_id = ? AND side = ? AND cancelled = 0 AND seq = " +
              "(SELECT MAX(seq) FROM live_goals WHERE game_id = ? AND side = ? AND cancelled = 0)")
              .bind(now, g.id, side, g.id, side));
            events += 1;
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
    }
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
    const goalsJson = newGoals.length ? JSON.stringify(newGoals) : null;
    const changed = !p || p.hs !== g.hs || p.as_ !== g.as || !!p.live !== !!g.live
      || (p.goals || null) !== goalsJson;
    if (changed) {
      stmts.push(env.DB.prepare("/*ls_upsert*/ INSERT INTO live_state (game_id, c, h, a, hs, as_, live, min, gt, hf, goals, " +
        "first_seen, seen_at, changed_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(game_id) DO UPDATE SET " +
        "c=excluded.c, h=excluded.h, a=excluded.a, hs=excluded.hs, as_=excluded.as_, live=excluded.live, min=excluded.min, " +
        "gt=excluded.gt, hf=excluded.hf, goals=excluded.goals, seen_at=excluded.seen_at, changed_at=excluded.changed_at")
        .bind(g.id, g.c, g.h, g.a, g.hs, g.as, g.live ? 1 : 0, g.min || "", g.gt || 0, g.hf || 0, goalsJson, now, now, now));
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
  for (let i = 0; i < stmts.length; i += 40) await env.DB.batch(stmts.slice(i, i + 40));   // D1 batch cap
  return { upserts, events, ended };
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
    return { ok: true, ...r, n: fresh.games.length };
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
  if (request.method === "POST" && parts[0] === "article") {
    let rec;
    try { rec = await request.json(); }
    catch (e) { return jsonReply(request, { error: "body is not json" }, 400); }
    for (const f of ["title", "summary", "body", "author", "pub_date"]) {
      if (!String(rec[f] || "").trim()) {
        return jsonReply(request, { error: `missing ${f}` }, 400);
      }
    }
    if (!!rec.match_id !== !!rec.kind) {
      return jsonReply(request, { error: "match_id and kind go together" }, 400);
    }
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
const MATCH_SLOTS = ["13:00", "17:00", "20:00", "23:30"];
const MATCH_CRONS = new Set(["0 9,10,13,14,16,17 * * *", "30 19,20 * * *"]);
export function matchSlotCairo(date) {
  const hm = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Africa/Cairo", hour: "2-digit", minute: "2-digit", hour12: false,
  }).format(date).replace(/^24/, "00");
  return MATCH_SLOTS.includes(hm) ? hm : null;
}

export default {
  async fetch(request, env, ctx) {
    // Permanent redirect from any non-canonical host — the legacy
    // *.workers.dev URL and the www. variant — to the bare custom domain.
    // One canonical URL keeps old links working and avoids duplicate
    // content in Google after the 2026-08-03 domain move.
    const url = new URL(request.url);
    const canonical = "yallascore.site";
    if (url.hostname !== canonical) {
      url.hostname = canonical;
      return Response.redirect(url.toString(), 301);
    }
    if (url.pathname === "/admin/api" || url.pathname.startsWith("/admin/api/")) {
      return adminApi(request, env, url);
    }
    if (url.pathname === "/health") {
      return healthResponse(env, ctx);
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
    return env.ASSETS.fetch(request);
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
        return;
      }
      console.log("live store refresh:", JSON.stringify(r));
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
