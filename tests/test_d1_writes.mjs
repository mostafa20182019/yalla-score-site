// The D1 write budget of one live refresh (2026-09-15).
//
//   node tests/test_d1_writes.mjs
//
// On 2026-09-15 the free tier's 100k daily row-WRITE quota ran out and blocked
// the article pipeline, which shares the database. The cause was the live
// store: it wrote one row per LISTED GAME on every refresh (an `ls_touch`
// whose only job was to move seen_at), so ~30 games x 1440 cron refreshes was
// ~46k writes a day before a single visitor polled /live.json.
//
// This harness counts the write statements of one refresh. It is the guard: a
// refresh where nothing changed must cost a constant, and a refresh where one
// score moved must cost that constant plus one.
import assert from "node:assert/strict";

let fails = [];
const ck = (name, cond, extra = "") => {
  console.log((cond ? "  ok   " : "  FAIL ") + name + (extra ? `  [${extra}]` : ""));
  if (!cond) fails.push(name);
};

const WRITE_TAGS = ["/*ls_upsert*/", "/*ls_touch*/", "/*lm_set*/", "/*ls_purge*/",
                    "/*lg_ins*/", "/*lg_cancel*/", "/*lg_cancel_last*/",
                    "/*rq_ins*/", "/*rq_try*/", "/*rq_done*/", "/*rq_purge*/"];
const isWrite = (sql) => WRITE_TAGS.some(t => sql.includes(t));

function fakeD1() {
  const state = new Map(), goals = [], meta = new Map(), writes = [];
  const exec = (sql, b) => {
    if (isWrite(sql)) writes.push(sql.match(/\/\*(\w+)\*\//)[1]);
    if (sql.startsWith("CREATE TABLE")) return { results: [] };
    if (sql.includes("/*ls_rows*/")) {
      const r = [...state.values()];
      return { results: r, meta: { rows_read: r.length } };      // a full scan costs a row per row
    }
    if (sql.includes("/*ls_snap*/")) {
      const r = meta.has("snapshot") ? [{ v: meta.get("snapshot") }] : [];
      return { results: r, meta: { rows_read: r.length } };
    }
    if (sql.includes("/*ls_prev*/")) return { results: b.map(id => state.get(id)).filter(Boolean) };
    if (sql.includes("/*lg_seq*/")) return { first: { s: goals.filter(g => g.game_id === b[0]).length } };
    if (sql.includes("/*lg_ins*/")) { goals.push({ game_id: b[0], seq: b[1] }); return { results: [] }; }
    if (sql.includes("/*lg_cancel")) return { results: [] };
    if (sql.includes("/*ls_upsert*/")) {
      const [game_id, c, h, a, hs, as_, live, min, gt, hf, goalsJ, first_seen, seen_at, changed_at] = b;
      state.set(game_id, { game_id, c, h, a, hs, as_, live, min, gt, hf, goals: goalsJ,
                           first_seen, seen_at, changed_at });
      return { results: [] };
    }
    if (sql.includes("/*ls_purge*/")) {
      for (const [k, r] of [...state]) if ((r.changed_at || 0) < b[0]) state.delete(k);
      return { results: [] };
    }
    if (sql.includes("/*lm_set*/")) { meta.set(b[0], b[1]); return { results: [] }; }
    if (sql.includes("/*rq_due*/")) return { results: [] };
    if (sql.includes("/*rq_")) return { results: [], first: null };
    throw new Error("fake D1: unknown statement " + sql.slice(0, 60));
  };
  const mk = (sql) => ({
    sql, _b: [],
    bind(...a) { this._b = a; return this; },
    async all() { return exec(sql, this._b); },
    async first() { const r = exec(sql, this._b); return "first" in r ? r.first : (r.results[0] || null); },
    async run() { exec(sql, this._b); return { success: true }; },
  });
  return { state, meta, writes, prepare: (sql) => mk(sql),
           batch: async (st) => st.map(s => exec(s.sql, s._b)) };
}

// thirty live games, the size of a normal evening's upstream list
const team = (id, name, score) => ({ id, name, score });
const game = (i, hs, as_) => ({
  id: 1000 + i, statusGroup: 3, competitionId: 7, statusText: "الشوط الثاني",
  shortStatusText: "2", gameTime: 70, gameTimeDisplay: "70'",
  homeCompetitor: team(i * 2, `h${i}`, hs), awayCompetitor: team(i * 2 + 1, `a${i}`, as_),
});
let LIST = { games: Array.from({ length: 30 }, (_, i) => game(i, 1, 0)) };

globalThis.fetch = async (url) => {
  const u = String(url);
  if (u.includes("/games/current/")) return Response.json(LIST);
  return new Response("no", { status: 500 });      // no detail calls needed
};
globalThis.caches = { default: { match: async () => undefined, put: async () => {} } };

const worker = (await import(new URL("../worker.js", import.meta.url).href)).default;
const db = fakeD1();
const env = { DB: db };
const tick = async () => { db.writes.length = 0; await worker.scheduled({ cron: "* * * * *" }, env, {}); return db.writes; };
const serve = async () => {
  // the canonical host: the worker 301s anything else before routing
  const res = await worker.fetch(new Request("https://yallascore.site/live.json"),
                                 env, { waitUntil: () => {} });
  return res.json();
};

// first sight of 30 games: 30 upserts + the snapshot + the purge
let w = await tick();
ck("1 the first refresh stores the thirty games it has never seen",
   w.filter(x => x === "ls_upsert").length === 30, w.length);

// nothing moved: the expensive part must disappear entirely
w = await tick();
const perRefresh = w.length;
ck("2 a refresh where NOTHING changed writes no game rows at all",
   w.filter(x => x === "ls_upsert").length === 0, JSON.stringify(w));
ck("3 and costs a small constant (the snapshot + the purge), not one row per game",
   perRefresh <= 3, perRefresh);
ck("4 no ls_touch statement exists any more (that was the quota bug)",
   !w.includes("ls_touch"));

// one score moves: exactly one game row
LIST.games[7] = game(7, 2, 0);
w = await tick();
ck("5 one changed score costs exactly one game row",
   w.filter(x => x === "ls_upsert").length === 1, JSON.stringify(w));
ck("6 a goal event is logged with it", w.includes("lg_ins"));

// the daily arithmetic that matters: a one-minute cron for a whole day
const perDay = perRefresh * 1440;
ck("7 a full day of cron refreshes stays far under the 100k free-tier quota",
   perDay < 10000, `${perDay} writes/day for the idle cron`);

// ---- the clock must not cost anything (2026-09-17) ------------------------
// The minute ticks for every live game every minute. While it was part of the
// "has this row changed?" test, that was one row write per live game per
// minute - ~28k on a busy evening against a 100k daily quota. live_state is
// only ever diffed against; the minute visitors see comes from the snapshot.
LIST.games = LIST.games.map(g => ({ ...g, gameTime: 71, gameTimeDisplay: "71'" }));
w = await tick();
ck("7b a minute ticking on every game writes NO game rows",
   w.filter(x => x === "ls_upsert").length === 0, JSON.stringify(w));
const ticked = await serve();
ck("7c and the fresh minute still reaches the visitor, from the snapshot",
   ticked.games.every(g => g.min === "71'"), ticked.games[0] && ticked.games[0].min);

// ---- the OTHER quota: rows READ, which ran out on 2026-09-16 --------------
// One serve of /live.json is a full scan of live_state plus the snapshot row.
// These two assertions exist to MEASURE, not to pass: the cost is reported on
// the response so it can be watched in production with curl, and the day it
// stops scaling with the table is the day the fix landed.
const served = await serve();
ck("10 a serve reports what it cost in rows read", typeof served.rr === "number", JSON.stringify(served).slice(0, 120));
// THE read guard (2026-09-17): this used to scan live_state, which measured at
// 113 rows a serve in production - ~40% of the daily free tier spent
// re-assembling an answer the refresh had already assembled. The snapshot now
// carries the payload, so the cost is ONE row and stays there however many
// games the table holds.
ck("11 a serve costs exactly one row, whatever the table holds",
   served.rr === 1, `${served.rr} rows for ${db.state.size} stored games`);
ck("12 and it still serves every live game, with its numbers",
   served.games.length === db.state.size
   && served.games.every(g => g.h && typeof g.hs === "number" && "live" in g),
   `${served.games.length} served of ${db.state.size}`);
const servesPerDay = 20000;   // a modest day of visitors polling during matches
ck("13 the arithmetic that matters, against the 5M daily read quota",
   served.rr * servesPerDay < 100000,
   `${served.rr} x ${servesPerDay} serves = ${served.rr * servesPerDay} rows/day ` +
   `(was ${(db.state.size + 1) * servesPerDay})`);
// what it used to be, kept as the reason this test exists
ck("8 the old per-game path would have blown the quota on its own",
   (30 + 2) * 1440 > 45000, `${(30 + 2) * 1440} writes/day before the fix`);

// freshness is still proved - the snapshot names the games and carries the time
const snap = JSON.parse(db.meta.get("snapshot"));
ck("9 the snapshot carries the moment and every listed game id",
   snap.ts > Date.now() - 5000 && snap.ids.length === 30, snap.ids.length);

console.log(fails.length ? `\n${fails.length} FAILED: ${fails.join(", ")}`
                         : "\nALL D1 WRITE-BUDGET TESTS PASSED");
process.exit(fails.length ? 1 : 0);
