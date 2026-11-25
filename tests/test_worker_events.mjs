// «كام واحد ضغط؟» (2026-11-25): POST /e/<name> adds one to a button's number
// for the day; nothing else is stored, an unknown name or a GET writes
// nothing, a day's number stops at the cap, and a broken store never shows.
import assert from "node:assert/strict";

const worker = (await import(new URL("../worker.js", import.meta.url).href)).default;

function fakeDb() {
  const rows = new Map(), log = [];
  return {
    rows, log,
    prepare(q) {
      const st = { q, args: [],
        bind(...a) { st.args = a; return st; },
        async run() {
          log.push(q);
          if (q.includes("/*ev_add*/")) {
            const [day, name, cap] = st.args, k = day + "|" + name, n = rows.get(k) || 0;
            if (!n) rows.set(k, 1); else if (n < cap) rows.set(k, n + 1);
          }
          return {};
        },
        async all() {
          log.push(q);
          return { results: [...rows].map(([k, n]) => ({ day: k.split("|")[0], name: k.split("|")[1], n })) };
        } };
      return st;
    },
  };
}
const assets = { fetch: async () => new Response("page", { status: 200 }) };
const post = (p) => new Request("https://elgoon.com" + p, { method: "POST" });

const db = fakeDb(), env = { ASSETS: assets, DB: db };
let r = await worker.fetch(post("/e/pick_img"), env, {});
assert.equal(r.status, 204);
await worker.fetch(post("/e/pick_img"), env, {});
await worker.fetch(post("/e/table_img"), env, {});
const day = new Date().toISOString().slice(0, 10);
assert.equal(db.rows.get(day + "|pick_img"), 2);
assert.equal(db.rows.get(day + "|table_img"), 1);

// an unknown name, a GET, a path under a known name: nothing is written
const before = db.log.filter(q => q.includes("ev_add")).length;
for (const req of [post("/e/anything"), post("/e/pick_img/x"), post("/e/"), new Request("https://elgoon.com/e/pick_img")]) {
  r = await worker.fetch(req, env, {});
  assert.equal(r.status, 204);
}
assert.equal(db.log.filter(q => q.includes("ev_add")).length, before);

// the cap rides in the statement itself
assert.ok(db.log.some(q => q.includes("ON CONFLICT (day, name) DO UPDATE SET n = n + 1 WHERE n < ?")));
db.rows.set(day + "|shot_img", 2000);
await worker.fetch(post("/e/shot_img"), env, {});
assert.equal(db.rows.get(day + "|shot_img"), 2000);

// the numbers can be read back
r = await worker.fetch(new Request("https://elgoon.com/e/stats.json"), env, {});
assert.equal(r.status, 200);
assert.equal(r.headers.get("cache-control"), "no-store");
const got = await r.json();
assert.ok(got.events.some(e => e.name === "pick_img" && e.n === 2));

// no store, or a store that throws: still an empty 204, never an error page
r = await worker.fetch(post("/e/pick_img"), { ASSETS: assets }, {});
assert.equal(r.status, 204);
r = await worker.fetch(post("/e/pick_img"),
  { ASSETS: assets, DB: { prepare() { throw new Error("down"); } } }, {});
assert.equal(r.status, 204);

console.log("ALL OK");
