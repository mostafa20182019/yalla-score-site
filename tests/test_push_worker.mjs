/* /push/subscribe and /push/unsubscribe (push.js via worker.js), driven with a
 * fake D1 binding.
 *
 * What this proves: the routes are wired, they refuse what a real browser
 * would never send (another origin, GET, a non-push-service endpoint - which
 * would turn the table into a list of URLs our runner POSTs to - malformed
 * keys, an oversized body), a subscribe is ONE upsert keyed on the endpoint,
 * an unsubscribe is one DELETE, and a D1 failure is a 503 JSON answer, never
 * a bare 500.
 *
 *   node tests/test_push_worker.mjs
 */
import worker from "../worker.js";
import { pushEndpointOk, pushKeysOk } from "../push.js";

let fails = [];
const ck = (name, cond, extra = "") => {
  console.log((cond ? "  ok   " : "  FAIL ") + name + (extra ? `  [${extra}]` : ""));
  if (!cond) fails.push(name);
};

function fakeDB(opts = {}) {
  const seen = [];
  return {
    seen,
    prepare(sql) {
      const st = {
        sql, binds: [],
        bind(...a) { this.binds = a; return this; },
        async run() {
          seen.push([sql, this.binds]);
          if (opts.throwOn && sql.includes(opts.throwOn)) throw new Error("D1 quota");
          return { success: true };
        },
      };
      return st;
    },
  };
}

const P256 = "B" + "A".repeat(86);         // 87 chars, like a real p256dh
const AUTH = "a".repeat(22);
const SUB = { endpoint: "https://fcm.googleapis.com/fcm/send/abc:xyz", keys: { p256dh: P256, auth: AUTH } };

function req(path, body, { method = "POST", origin = "https://elgoon.com", raw } = {}) {
  const headers = { "content-type": "application/json" };
  if (origin) headers.Origin = origin;
  return new Request("https://elgoon.com" + path, {
    method, headers, body: method === "GET" ? undefined : (raw ?? JSON.stringify(body)),
  });
}
const env = (db) => ({ DB: db, ASSETS: { fetch: async () => new Response("asset") } });
const call = async (r, db) => {
  const res = await worker.fetch(r, env(db), { waitUntil() {} });
  let j = null; try { j = await res.json(); } catch (e) {}
  return { status: res.status, j, cc: res.headers.get("cache-control") };
};

// ------------------------------------------------------------- validators
ck("1 FCM, Mozilla, WNS and Apple endpoints are push services",
   ["https://fcm.googleapis.com/fcm/send/x", "https://updates.push.services.mozilla.com/wpush/v2/x",
    "https://wns2-par02p.notify.windows.com/w/?token=x", "https://web.push.apple.com/QG9x"].every(pushEndpointOk));
ck("2 anything else is not: http, other hosts, look-alikes, credentials, ports",
   !["http://fcm.googleapis.com/x", "https://evil.example/x", "https://fcm.googleapis.com.evil.io/x",
     "https://user:pw@fcm.googleapis.com/x", "https://fcm.googleapis.com:8443/x", "not a url",
     "https://fcm.googleapis.com/" + "x".repeat(1100), 42].some(pushEndpointOk));
ck("3 keys: a 65-byte point and a 16-byte secret, base64url",
   pushKeysOk({ p256dh: P256, auth: AUTH }) && !pushKeysOk({ p256dh: "short", auth: AUTH })
   && !pushKeysOk({ p256dh: P256, auth: "a+b/c".repeat(5) }) && !pushKeysOk(null));

// ------------------------------------------------------------- the routes
let db = fakeDB();
let r = await call(req("/push/subscribe", SUB), db);
const ins = db.seen.find(([s]) => s.includes("INSERT INTO push_subs"));
ck("4 a real subscription is stored: 200 {ok}, no-store", r.status === 200 && r.j && r.j.ok && r.cc === "no-store");
ck("5 ... as ONE upsert keyed on the endpoint (tapping twice does not grow the table)",
   ins && /ON CONFLICT\(endpoint\) DO UPDATE/.test(ins[0]) && ins[1][0] === SUB.endpoint
   && ins[1][1] === P256 && ins[1][2] === AUTH
   && db.seen.filter(([s]) => s.includes("INSERT")).length === 1);
ck("6 the table is created if missing (first subscriber ever)",
   db.seen.some(([s]) => s.startsWith("CREATE TABLE IF NOT EXISTS push_subs")));

db = fakeDB();
r = await call(req("/push/unsubscribe", { endpoint: SUB.endpoint }), db);
const del = db.seen.find(([s]) => s.includes("DELETE FROM push_subs"));
ck("7 unsubscribe deletes exactly that endpoint", r.status === 200 && del && del[1][0] === SUB.endpoint);

const refused = [
  ["8 another origin is refused (403)", req("/push/subscribe", SUB, { origin: "https://evil.example" }), 403],
  ["9 no Origin at all is refused (403)", req("/push/subscribe", SUB, { origin: null }), 403],
  ["10 GET is refused (405)", req("/push/subscribe", null, { method: "GET" }), 405],
  ["11 a non-push-service endpoint is refused (400)",
   req("/push/subscribe", { ...SUB, endpoint: "https://evil.example/hook" }), 400],
  ["12 malformed keys are refused (400)", req("/push/subscribe", { ...SUB, keys: { p256dh: "x", auth: "y" } }), 400],
  ["13 broken JSON is refused (400)", req("/push/subscribe", null, { raw: "{nope" }), 400],
  ["14 an oversized body is refused (400)", req("/push/subscribe", null, { raw: JSON.stringify({ ...SUB, pad: "x".repeat(5000) }) }), 400],
];
for (const [name, rq, want] of refused) {
  db = fakeDB();
  r = await call(rq, db);
  ck(name + " - and nothing is written", r.status === want && !db.seen.some(([s]) => /INSERT|DELETE/.test(s)), r.status);
}

db = fakeDB({ throwOn: "INSERT INTO push_subs" });
r = await call(req("/push/subscribe", SUB), db);
ck("15 a D1 failure (quota) answers 503 JSON, never a bare 500", r.status === 503 && r.j && r.j.error);

r = await call(req("/push/subscribe", SUB), undefined);
ck("16 no D1 binding: 503", r.status === 503);

const res = await worker.fetch(new Request("https://elgoon.com/sw.js"), env(fakeDB()), { waitUntil() {} });
ck("17 every other path still goes to the static assets (sw.js included)", (await res.text()) === "asset");

// ------------------------------------------- «تابع فريقك» (2026-11-19)
const teamBinds = async (body) => {
  const d = fakeDB();
  const rr = await call(req("/push/subscribe", body), d);
  const row = d.seen.find(([s]) => s.includes("INSERT INTO push_subs"));
  return [rr.status, row && row[1][4], row && row[1][5]];
};
let tb = await teamBinds({ ...SUB, team: "al-ahly" });
ck("18 a followed club is stored on the row", tb[0] === 200 && tb[1] === "al-ahly" && tb[2] === 1, String(tb));
tb = await teamBinds(SUB);
ck("19 a body WITHOUT the key leaves the stored club alone (sw.js re-subscribes without it)", tb[1] === null && tb[2] === 0, String(tb));
tb = await teamBinds({ ...SUB, team: "" });
ck("20 an empty club clears it", tb[1] === null && tb[2] === 1, String(tb));
for (const bad of ["../x", "AL-AHLY", "a", "x".repeat(41), 7, { a: 1 }, "al ahly"]) {
  tb = await teamBinds({ ...SUB, team: bad });
  ck(`21 a club that is not a slug is never stored (${JSON.stringify(bad).slice(0, 14)})`, tb[0] === 200 && tb[1] === null, String(tb));
}
const dupDb = fakeDB({ throwOn: "push_team_col" });
dupDb.prepare = ((orig) => (sql) => {
  const st = orig(sql);
  if (sql.includes("push_team_col")) st.run = async () => { throw new Error("duplicate column name: team"); };
  return st;
})(dupDb.prepare.bind(dupDb));
r = await call(req("/push/subscribe", { ...SUB, team: "zamalek" }), dupDb);
ck("22 the column already being there is not an error", r.status === 200 && r.j && r.j.ok, String(r.status));

console.log(fails.length ? `\nFAILED: ${fails.join(", ")}` : "\nall push worker checks passed");
process.exit(fails.length ? 1 : 0);
