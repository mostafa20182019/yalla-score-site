// The live store (2026-09-13): /live.json served from D1, refreshed from
// 365scores in the background, goals remembered the moment they appear.
//
//   node tests/test_live_store.mjs
//
// The fake D1 below is a tiny in-memory engine for exactly the tagged
// statements worker.js issues (/*ls_rows*/, /*ls_upsert*/, ...). The tags are
// the contract: a new statement in worker.js needs a case here.
import assert from "node:assert/strict";

let fails = [];
const ck = (name, cond, extra = "") => {
  console.log((cond ? "  ok   " : "  FAIL ") + name + (extra ? `  [${extra}]` : ""));
  if (!cond) fails.push(name);
};

/* ------------------------------------------------------------- fake D1 */
function fakeD1() {
  const state = new Map();      // game_id -> row
  const rq = new Map();         // report_queue (see tools/test_report_queue.mjs)
  const goals = [];             // live_goals rows
  const meta = new Map();
  const seen = [];
  const exec = (sql, b) => {
    seen.push(sql.slice(0, 14));
    if (sql.startsWith("CREATE TABLE")) return { results: [] };
    // reads come back whole now; the SNAPSHOT decides what is servable
    if (sql.includes("/*ls_rows*/")) return { results: [...state.values()] };
    // .all() shape, not .first(): storeRead reads the snapshot with all() so
    // it can bill meta.rows_read (the read-cost accounting of 2026-09-16).
    // While this returned {first}, `metaRows.results` was undefined, the
    // snapshot read as absent and EVERY scenario served an empty games list -
    // the harness had been red since 4d581c65 for no reason in the worker.
    if (sql.includes("/*ls_snap*/")) return {
      results: meta.has("snapshot") ? [{ v: meta.get("snapshot") }] : [],
      meta: { rows_read: meta.has("snapshot") ? 1 : 0 } };
    if (sql.includes("/*ls_prev*/")) return { results: b.map(id => state.get(id)).filter(Boolean) };
    if (sql.includes("/*lg_seq*/")) {
      const s = goals.filter(g => g.game_id === b[0]).reduce((m, g) => Math.max(m, g.seq), 0);
      return { first: { s } };
    }
    if (sql.includes("/*lg_ins*/")) {
      const [game_id, seq, side, player, minute, tag, score_h, score_a, c, h, a, seen_at] = b;
      if (!goals.find(g => g.game_id === game_id && g.seq === seq))
        goals.push({ game_id, seq, side, player, minute, tag, score_h, score_a, c, h, a, seen_at, cancelled: 0 });
      return { results: [] };
    }
    if (sql.includes("/*lg_cancel_last*/")) {
      const [now, game_id, side] = b;
      const cand = goals.filter(g => g.game_id === game_id && g.side === side && !g.cancelled);
      if (cand.length) { const g = cand[cand.length - 1]; g.cancelled = 1; g.cancelled_at = now; }
      return { results: [] };
    }
    if (sql.includes("/*lg_cancel*/")) {
      const [now, game_id, side, player, minute] = b;
      for (const g of goals) if (g.game_id === game_id && g.side === side && (g.player || "") === player
                                 && (g.minute || "") === minute && !g.cancelled) { g.cancelled = 1; g.cancelled_at = now; }
      return { results: [] };
    }
    if (sql.includes("/*ls_upsert*/")) {
      const [game_id, c, h, a, hs, as_, live, min, gt, hf, goalsJ, first_seen, seen_at, changed_at] = b;
      const prev = state.get(game_id);
      state.set(game_id, { game_id, c, h, a, hs, as_, live, min, gt, hf, goals: goalsJ,
                           first_seen: prev ? prev.first_seen : first_seen, seen_at, changed_at });
      return { results: [] };
    }
    if (sql.includes("/*ls_purge*/")) {
      for (const [k, r] of [...state]) if ((r.changed_at || 0) < b[0]) state.delete(k);
      return { results: [] };
    }
    if (sql.includes("/*lm_set*/")) { meta.set(b[0], b[1]); return { results: [] }; }
    // the report queue lives in its own test (test_report_queue.mjs); here it
    // only has to exist, so the one-minute cron runs its tick end to end
    if (sql.includes("/*rq_ins*/")) { rq.set(b[0], { game_id: b[0], due_at: b[7], tries: 0, done_at: null }); return { results: [] }; }
    if (sql.includes("/*rq_due*/")) return { results: [...rq.values()].filter(r => r.done_at === null && r.due_at <= b[0]) };
    if (sql.includes("/*rq_have*/")) return { first: null };
    if (sql.includes("/*rq_today*/")) return { first: { n: 0 } };
    if (sql.includes("/*rq_try*/")) { const r = rq.get(b[1]); if (r) { r.tries += 1; r.due_at = b[0]; } return { results: [] }; }
    if (sql.includes("/*rq_done*/")) { const r = rq.get(b[2]); if (r) r.done_at = b[0]; return { results: [] }; }
    if (sql.includes("/*rq_purge*/")) return { results: [] };
    throw new Error("fake D1: unknown statement " + sql.slice(0, 60));
  };
  const mk = (sql) => ({
    sql, _b: [],
    bind(...a) { this._b = a; return this; },
    async all() { return exec(sql, this._b); },
    async first() { const r = exec(sql, this._b); return "first" in r ? r.first : (r.results[0] || null); },
    async run() { exec(sql, this._b); return { success: true }; },
  });
  return { state, goals, meta, seen, rq, prepare: (sql) => mk(sql), batch: async (st) => st.map(s => exec(s.sql, s._b)) };
}

/* ------------------------------------------------------------- upstream */
const team = (id, name, score) => ({ id, name, score });
const goalEv = (playerId, competitorId, gameTime) =>
  ({ eventType: { name: "هدف" }, playerId, competitorId, gameTime, addedTime: 0 });
let LIST, DETAIL, upstreamCalls = 0, upstreamDown = false;
function scenario(hs, as_, minute, goals) {
  LIST = { games: [{ id: 900, statusGroup: 3, competitionId: 552, statusText: "الشوط الثاني", shortStatusText: "2",
    gameTime: minute, gameTimeDisplay: `${minute}'`, homeCompetitor: team(1, "الزمالك", hs), awayCompetitor: team(2, "الإسماعيلي", as_) },
    // a scheduled game must be ignored, a finished one stored as not live
    { id: 901, statusGroup: 2, competitionId: 7, homeCompetitor: team(3, "x", -1), awayCompetitor: team(4, "y", -1) },
    { id: 902, statusGroup: 4, competitionId: 7, homeCompetitor: team(5, "تشيلسي", 2), awayCompetitor: team(6, "هال", 2) },
    // Filler, and NOT decoration: the worker treats a list of fewer than five
    // games as a degraded 365scores reply (2026-09-01) and refetches
    // per-competition, which against this mock returns the same three games
    // ten times over. Every scenario then served a list of duplicates. These
    // three scheduled games keep the reply "healthy" so the tests exercise
    // the multi path the site actually runs on; sg 2 means they are ignored
    // exactly like 901.
    { id: 910, statusGroup: 2, competitionId: 11, homeCompetitor: team(7, "p", -1), awayCompetitor: team(8, "q", -1) },
    { id: 911, statusGroup: 2, competitionId: 17, homeCompetitor: team(9, "r", -1), awayCompetitor: team(10, "s", -1) },
    { id: 912, statusGroup: 2, competitionId: 25, homeCompetitor: team(13, "t", -1), awayCompetitor: team(14, "u", -1) }] };
  DETAIL = { 900: { game: { statusGroup: 3, statusText: "الشوط الثاني", shortStatusText: "2", gameTime: minute, gameTimeDisplay: `${minute}'`,
    homeCompetitor: team(1, "الزمالك", hs), awayCompetitor: team(2, "الإسماعيلي", as_),
    members: [{ id: 11, name: "زيزو" }, { id: 12, name: "ناصر ماهر" }, { id: 21, name: "لاعب الإسماعيلي" }], events: goals } } };
}
globalThis.fetch = async (url) => {
  upstreamCalls += 1;
  if (upstreamDown) return new Response("down", { status: 503 });
  if (String(url).includes("/games/current/")) return Response.json(LIST);
  const m = String(url).match(/gameId=(\d+)/);
  return m && DETAIL[m[1]] ? Response.json(DETAIL[m[1]]) : new Response("no", { status: 500 });
};
globalThis.caches = { default: { match: async () => undefined, put: async () => {} } };

const worker = (await import(new URL("../worker.js", import.meta.url).href)).default;
const db = fakeD1();
const env = { DB: db };
const waits = [];
const ctx = { waitUntil(p) { waits.push(p); } };
const call = async () => {
  const res = await worker.fetch(new Request("https://yallascore.site/live.json"), env, ctx);
  return { j: await res.json(), cc: res.headers.get("cache-control") };
};
const drain = async () => { await Promise.all(waits.splice(0)); };
// the snapshot row IS the freshness record now (one write per refresh instead
// of one per game - the D1 quota fix of 2026-09-15), so the tests age it
const snap = () => JSON.parse(db.meta.get("snapshot") || "{}");
const age = (ms) => {
  const sn = snap();
  sn.ts = Date.now() - ms;
  db.meta.set("snapshot", JSON.stringify(sn));
};

/* ------------------------------------------------------------- 1 cold */
scenario(1, 0, 30, [goalEv(11, 1, 12)]);
let r = await call();
ck("1 cold start fetches upstream synchronously and serves the fresh state",
   r.j.src === "store-fresh" && r.j.games.length === 2 && upstreamCalls > 0, JSON.stringify(r.j.games.map(g => [g.id, g.hs, g.as, g.live])));
const z = r.j.games.find(g => g.id === 900);
ck("2 the live game carries score, minute and the goal list", z.hs === 1 && z.min === "30'" && z.goals.length === 1 && z.goals[0].p === "زيزو");
ck("3 the first goal was logged the moment it was seen (with its minute)",
   db.goals.length === 1 && db.goals[0].player === "زيزو" && db.goals[0].minute === "12" && db.goals[0].score_h === 1);
ck("4 the finished game is stored as not live, the scheduled one is not stored, and a bare 2-2 seeds no nameless goals",
   db.state.get(902).live === 0 && !db.state.has(901) && !db.goals.some(g => g.game_id === 902));

/* ------------------------------------------------------------- 2 warm */
const before = upstreamCalls;
r = await call();
ck("5 a second visitor within REFRESH_SEC is served from the store, no upstream call",
   r.j.src === "store" && upstreamCalls === before && r.j.games.length === 2, `age=${r.j.age}`);
ck("6 the stored reply is edge-cacheable for a few seconds", (r.cc || "").includes("s-maxage=5"));

/* ------------------------------------------------------------- 3 goal */
// time passes: make the store's last refresh 20 s old, upstream now says 2-0 @ 41'
age(20000);
scenario(2, 0, 41, [goalEv(11, 1, 12), goalEv(12, 1, 41)]);
r = await call();
ck("7 between REFRESH_SEC and LIVE_TTL the visitor gets the stored state instantly and a background refresh is queued",
   r.j.src === "store" && r.j.games.find(g => g.id === 900).hs === 1 && waits.length >= 1);   // (+ the edge cache.put)
await drain();
ck("8 after the background refresh the store says 2-0 and the second goal is logged with its scorer and minute",
   db.state.get(900).hs === 2 && db.goals.length === 2 && db.goals[1].player === "ناصر ماهر" && db.goals[1].minute === "41" && db.goals[1].seq === 2);
r = await call();
ck("9 the next visitor sees 2-0 from the store", r.j.games.find(g => g.id === 900).hs === 2 && r.j.src === "store");

/* ------------------------------------------------------------- 4 VAR */
age(20000);
scenario(1, 0, 44, [goalEv(11, 1, 12)]);            // the 41' goal was disallowed
await call(); await drain();
const g2 = db.goals.find(g => g.seq === 2);
ck("10 a VAR reversal cancels the logged goal instead of deleting it, and the state follows upstream down to 1-0",
   g2.cancelled === 1 && db.goals.length === 2 && db.state.get(900).hs === 1);

/* ------------------------------------------------------------- 5 upstream down */
age(20000);
upstreamDown = true;
r = await call(); await drain();
ck("11 upstream failure: the visitor still gets the last confirmed state, the store is untouched, the failure is noted",
   r.j.games.length === 2 && db.state.get(900).hs === 1 && db.meta.has("last_fail"));

/* ------------------------------------------------------------- 6 stale */
// everything older than LIVE_TTL: served rows vanish (the firm rule), and the
// call fetches synchronously again
for (const row of db.state.values()) row.seen_at = Date.now() - 200000;
age(200000);
r = await call();
ck("12 a stale store with upstream still down serves NOTHING rather than an old score (fail-empty, uncacheable)",
   r.j.games.length === 0 && r.j.ok === false && r.cc === "no-store");
upstreamDown = false;
scenario(1, 1, 60, [goalEv(11, 1, 12), goalEv(21, 2, 58)]);
r = await call();
ck("13 upstream back: the stale store refreshes synchronously and serves the current 1-1",
   r.j.src === "store-fresh" && r.j.games.find(g => g.id === 900).as === 1);
ck("14 the away goal joined the log as seq 3 (seq 2 stays cancelled)",
   db.goals.length === 3 && db.goals[2].side === "a" && db.goals[2].player === "لاعب الإسماعيلي" && db.goals.find(g => g.seq === 2).cancelled === 1);

/* ------------------------------------------------------------- 7 score-only game */
// a game whose detail has no usable goal list: goals are logged from the score alone
age(20000);
LIST.games.push({ id: 903, statusGroup: 3, competitionId: 649, statusText: "الشوط الأول", shortStatusText: "1",
  gameTime: 10, gameTimeDisplay: "10'", homeCompetitor: team(7, "الهلال", 0), awayCompetitor: team(8, "النصر", 0) });
await call(); await drain();
age(20000);
LIST.games.find(g => g.id === 903).homeCompetitor.score = 1;
LIST.games.find(g => g.id === 903).gameTimeDisplay = "23'";
await call(); await drain();
const sg = db.goals.filter(g => g.game_id === 903);
ck("15 without a goal list the score change itself is the event (side + the minute on the clock, no scorer)",
   sg.length === 1 && sg[0].side === "h" && sg[0].player === null && sg[0].minute === "23'");

/* ------------------------------------------------------------- 8 cron */
const callsBefore = upstreamCalls;
age(20000);
await worker.scheduled({ cron: "* * * * *" }, { DB: db }, ctx);
ck("16 the one-minute cron refreshes the store without a GitHub token",
   upstreamCalls > callsBefore && snap().ts > Date.now() - 5000);
const disp = upstreamCalls;
await worker.scheduled({ cron: "1,16,31,46 * * * *" }, { DB: db }, ctx);
ck("17 the other crons still stop at the missing GitHub token (no upstream, no dispatch)", upstreamCalls === disp);

/* ------------------------------------------------------------- 9 no D1 */
const res0 = await worker.fetch(new Request("https://yallascore.site/live.json"), {}, ctx);
ck("18 without a D1 binding the old direct path still answers", /^(multi|split)/.test((await res0.json()).src));

/* ------------------------------------------- 8 the database itself is down */
// 2026-09-15, live: the D1 daily WRITE quota ran out, storeApply threw, and
// /live.json answered HTTP 500 on every page that polls it. The endpoint's
// rule is fail-empty - dashes, never an error, never a possibly-wrong number -
// and that has to cover a broken database too.
const dead = {
  DB: {
    prepare() { throw new Error("D1 HTTP 400: exceeded daily row write limit"); },
    batch() { throw new Error("D1 HTTP 400: exceeded daily row write limit"); },
  },
};
scenario(2, 1, 70, [goalEv(11, 1, 12)]);
let deadRes = await worker.fetch(new Request("https://yallascore.site/live.json"), dead, ctx);
let deadJson = await deadRes.json();
ck("19 a D1 that throws does not become a 500 - the upstream read answers",
   deadRes.status === 200 && Array.isArray(deadJson.games), deadRes.status);
upstreamDown = true;
deadRes = await worker.fetch(new Request("https://yallascore.site/live.json"), dead, ctx);
deadJson = await deadRes.json();
ck("20 and with upstream down too it serves nothing, uncacheable",
   deadRes.status === 200 && deadJson.games.length === 0
   && (deadRes.headers.get("cache-control") || "").includes("no-store"), deadJson.src);
upstreamDown = false;
ck("21 the one-minute cron survives a dead store without throwing",
   await worker.scheduled({ cron: "* * * * *" }, dead, {}).then(() => true, () => false));

console.log(fails.length ? `\n${fails.length} FAILED: ${fails.join("; ")}` : "\nALL LIVE STORE TESTS PASSED");
process.exit(fails.length ? 1 : 0);
