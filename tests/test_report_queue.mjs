// The post-match report queue (2026-09-13): a curated club's match gets its
// report because the match ENDED, not because a fixed slot came round.
//
//   node tests/test_report_queue.mjs
//
// What is checked: only a curated club is queued (with the Egyptian/Turkish
// scope that keeps الأهلي السعودي out), the queue waits REPORT_DELAY before
// dispatching, it dispatches kind=report and nothing else, it never dispatches
// twice for one tick, it closes the row when the article exists, it respects
// the daily cap, it gives up after three tries, and a failure in any of that
// never breaks the live refresh.
//
// The fake D1 is the same idea as test_live_store.mjs: a tiny engine for the
// tagged statements worker.js issues. A new tag in worker.js needs a case here.
import assert from "node:assert/strict";

let fails = [];
const ck = (name, cond, extra = "") => {
  console.log((cond ? "  ok   " : "  FAIL ") + name + (extra ? `  [${extra}]` : ""));
  if (!cond) fails.push(name);
};

/* ------------------------------------------------------------- fake D1 */
function fakeD1() {
  const state = new Map();       // live_state
  const queue = new Map();       // report_queue
  const articles = [];           // the D1 articles table (id, match_id, kind, pub_date)
  const goals = [], meta = new Map();
  const exec = (sql, b) => {
    if (sql.startsWith("CREATE TABLE")) return { results: [] };
    if (sql.includes("/*ls_rows*/")) return { results: [...state.values()] };
    if (sql.includes("/*ls_snap*/")) return { first: meta.has("snapshot") ? { v: meta.get("snapshot") } : null };
    if (sql.includes("/*ls_prev*/")) return { results: b.map(id => state.get(id)).filter(Boolean) };
    if (sql.includes("/*lg_seq*/")) return { first: { s: goals.filter(g => g.game_id === b[0]).length } };
    if (sql.includes("/*lg_ins*/")) { goals.push({ game_id: b[0], seq: b[1] }); return { results: [] }; }
    if (sql.includes("/*lg_cancel")) return { results: [] };
    if (sql.includes("/*ls_upsert*/")) {
      const [game_id, c, h, a, hs, as_, live, min, gt, hf, goalsJ, first_seen, seen_at, changed_at] = b;
      state.set(game_id, { game_id, c, h, a, hs, as_, live, min, gt, hf, goals: goalsJ, first_seen, seen_at, changed_at });
      return { results: [] };
    }
    if (sql.includes("/*ls_purge*/")) {
      for (const [k, r] of [...state]) if ((r.changed_at || 0) < b[0]) state.delete(k);
      return { results: [] };
    }
    if (sql.includes("/*lm_set*/")) { meta.set(b[0], b[1]); return { results: [] }; }
    // ---- the report queue
    if (sql.includes("/*rq_ins*/")) {
      const [game_id, c, h, a, hs, as_, ended_at, due_at] = b;
      if (!queue.has(game_id))
        queue.set(game_id, { game_id, c, h, a, hs, as_, ended_at, due_at, tries: 0, done_at: null, done_why: null });
      return { results: [] };
    }
    if (sql.includes("/*rq_due*/"))
      return { results: [...queue.values()].filter(r => r.done_at === null && r.due_at <= b[0])
                                           .sort((x, y) => x.due_at - y.due_at).slice(0, 5) };
    if (sql.includes("/*rq_have*/")) {
      const a = articles.find(x => String(x.match_id) === String(b[0]) && x.kind === "report");
      return { first: a ? { article_id: a.article_id } : null };
    }
    if (sql.includes("/*rq_today*/"))
      return { first: { n: articles.filter(x => x.kind === "report" && x.pub_date === b[0]).length } };
    if (sql.includes("/*rq_try*/")) { const r = queue.get(b[1]); if (r) { r.tries += 1; r.due_at = b[0]; } return { results: [] }; }
    if (sql.includes("/*rq_done*/")) { const r = queue.get(b[2]); if (r) { r.done_at = b[0]; r.done_why = b[1]; } return { results: [] }; }
    if (sql.includes("/*rq_purge*/")) {
      for (const [k, r] of [...queue]) if (r.ended_at < b[0]) queue.delete(k);
      return { results: [] };
    }
    throw new Error("fake D1: unknown statement " + sql.slice(0, 60));
  };
  const mk = (sql) => ({
    sql, _b: [],
    bind(...a) { this._b = a; return this; },
    async all() { return exec(sql, this._b); },
    async first() { const r = exec(sql, this._b); return "first" in r ? r.first : (r.results[0] || null); },
    async run() { exec(sql, this._b); return { success: true }; },
  });
  return { state, queue, articles, prepare: (sql) => mk(sql), batch: async (st) => st.map(s => exec(s.sql, s._b)) };
}

/* ------------------------------------------------------------- upstream */
const team = (id, name, score) => ({ id, name, score });
// a live game (statusGroup 3) and the same game ended (4)
const live = (id, comp, h, a, hs, as_) => ({
  id, statusGroup: 3, competitionId: comp, statusText: "الشوط الثاني", shortStatusText: "2",
  gameTime: 70, gameTimeDisplay: "70'", homeCompetitor: team(id * 10, h, hs), awayCompetitor: team(id * 10 + 1, a, as_),
});
const done = (id, comp, h, a, hs, as_) => ({
  id, statusGroup: 4, competitionId: comp,
  homeCompetitor: team(id * 10, h, hs), awayCompetitor: team(id * 10 + 1, a, as_),
});

let LIST = { games: [] };
const dispatches = [];
globalThis.fetch = async (url, init) => {
  const u = String(url);
  if (u.includes("/games/current/")) return Response.json(LIST);
  if (u.includes("/actions/workflows/")) {
    dispatches.push({ workflow: u.match(/workflows\/([^/]+)\/dispatches/)[1],
                      body: JSON.parse(init.body) });
    return { status: 204, ok: true, text: async () => "" };
  }
  return new Response("no", { status: 500 });   // game detail: not needed here
};
globalThis.caches = { default: { match: async () => undefined, put: async () => {} } };

const worker = (await import(new URL("../worker.js", import.meta.url).href)).default;
const db = fakeD1();
const env = { DB: db, GH_TOKEN: "t" };
const tick = () => worker.scheduled({ cron: "* * * * *" }, env, {});
const DELAY = 30 * 60 * 1000;
const cairoToday = new Intl.DateTimeFormat("en-CA", { timeZone: "Africa/Cairo" }).format(new Date());

/* ---------------------------------------------------- 1 the final whistle */
// four live matches: Zamalek (Egyptian league), Arsenal spelled آرسنال,
// Al-Ahli SAUDI (comp 649 - the same word, not our club) and a non-curated one
LIST = { games: [
  live(901, 552, "الزمالك", "الإسماعيلي", 2, 0),
  live(902, 7, "آرسنال", "توتنهام", 1, 1),
  live(903, 649, "الأهلي", "النصر", 0, 0),
  live(904, 7, "إيفرتون", "برنتفورد", 0, 0),
  done(905, 11, "ريال مدريد", "خيتافي", 3, 1),          // first seen ALREADY ended
] };
await tick();
ck("1 nothing is queued while the matches are still being played", db.queue.size === 0);

LIST = { games: [
  done(901, 552, "الزمالك", "الإسماعيلي", 2, 0),
  done(902, 7, "آرسنال", "توتنهام", 1, 1),
  done(903, 649, "الأهلي", "النصر", 0, 0),
  done(904, 7, "إيفرتون", "برنتفورد", 0, 0),
  done(905, 11, "ريال مدريد", "خيتافي", 3, 1),
] };
await tick();
ck("2 the two curated matches are queued at the final whistle",
   db.queue.has(901) && db.queue.has(902), [...db.queue.keys()].join(","));
ck("3 آرسنال is recognised as أرسنال (alef normalisation)", db.queue.has(902));
ck("4 الأهلي in the SAUDI league is not our club", !db.queue.has(903));
ck("5 a non-curated match is not queued", !db.queue.has(904));
ck("6 a match first seen already ended is left to the fixed slots", !db.queue.has(905));
ck("7 the report is due ~30 minutes after the whistle, not now",
   db.queue.get(901).due_at - db.queue.get(901).ended_at === DELAY);
ck("8 nothing was dispatched yet", dispatches.length === 0);

/* ------------------------------------------------------------- 2 the tick */
// make 901 due; 902 stays in the future
db.queue.get(901).due_at = Date.now() - 1000;
await tick();
ck("9 a due match dispatches match-article with kind=report and no match_id",
   dispatches.length === 1 && dispatches[0].workflow === "match-article.yml"
   && dispatches[0].body.inputs.kind === "report" && !dispatches[0].body.inputs.match_id,
   JSON.stringify(dispatches[0] || {}));
ck("10 the row is not closed yet, it is retried later", db.queue.get(901).tries === 1
   && db.queue.get(901).done_at === null && db.queue.get(901).due_at > Date.now());
ck("11 the match that is not due yet was left alone", db.queue.get(902).tries === 0);

/* ------------------------------------------------- 3 one dispatch per tick */
dispatches.length = 0;
db.queue.get(901).due_at = Date.now() - 1000;
db.queue.get(902).due_at = Date.now() - 1000;
await tick();
ck("12 two matches due at once dispatch ONE run (the writer takes one match at a time)",
   dispatches.length === 1);

/* --------------------------------------------------- 4 the article arrives */
dispatches.length = 0;
db.articles.push({ article_id: "500", match_id: "901", kind: "report", pub_date: cairoToday });
db.queue.get(901).due_at = Date.now() - 2000;
db.queue.get(902).due_at = Date.now() - 1000;
await tick();
ck("13 the row closes when its report exists - no second report for one match",
   db.queue.get(901).done_at !== null && db.queue.get(901).done_why === "written");
ck("14 and the tick moves on to the next match in the queue", dispatches.length === 1);

/* ------------------------------------------------------------ 5 daily cap */
dispatches.length = 0;
for (const id of ["501", "502", "503"])
  db.articles.push({ article_id: id, match_id: "9" + id, kind: "report", pub_date: cairoToday });
db.queue.get(902).due_at = Date.now() - 1000;
await tick();
ck("15 at four reports today the queue stops dispatching (the cap match_brief owns)",
   dispatches.length === 0 && db.queue.get(902).done_at === null);

/* ---------------------------------------------------------- 6 giving up */
db.articles.length = 0;                       // cap free again
db.queue.get(902).tries = 3;
db.queue.get(902).due_at = Date.now() - 1000;
await tick();
ck("16 after three tries the match is left to the fixed slots",
   db.queue.get(902).done_at !== null && /gave up/.test(db.queue.get(902).done_why)
   && dispatches.length === 0);

/* ------------------------------------------------------------- 7 purge */
db.queue.set(910, { game_id: 910, ended_at: Date.now() - 5 * 24 * 3600 * 1000, due_at: Date.now(), tries: 0, done_at: null });
await tick();
ck("17 queue rows older than three days are purged", !db.queue.has(910));

/* ------------------------------------------- 8 it can never break the live */
const broken = { DB: { ...db, prepare: (sql) => sql.includes("/*rq_") ? { bind() { throw new Error("boom"); } } : db.prepare(sql) },
                 GH_TOKEN: "t" };
LIST = { games: [live(920, 552, "الأهلي", "بيراميدز", 1, 0)] };
let threw = false;
try { await worker.scheduled({ cron: "* * * * *" }, broken, {}); } catch (e) { threw = true; }
ck("18 a broken queue is logged and swallowed - the live refresh still ran",
   !threw && broken.DB.state.has(920));

console.log(fails.length ? `\n${fails.length} FAILED: ${fails.join(", ")}` : "\nALL REPORT QUEUE TESTS PASSED");
process.exit(fails.length ? 1 : 0);
