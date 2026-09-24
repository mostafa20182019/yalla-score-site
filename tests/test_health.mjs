// /health + the watchdog (health.js, 2026-09-24).
//
//   node tests/test_health.mjs
//
// The guard for the piece that is supposed to catch everything else: it must
// FAIL on the incidents we actually had (a deploy that stopped, a fetch that
// kept failing, three dead Claude slots, the D1 quota wall, a frozen live
// store), stay QUIET on the normal cadence (the overnight article gap, one
// failed slot, a cancelled refresh), and page ONCE per incident - a watchdog
// that repeats itself every 15 minutes gets muted and then catches nothing.
const H = await import(new URL("../health.js", import.meta.url).href);
const { evaluate, decideAlert, watchdog, healthResponse, LIMITS } = H;

let fails = [];
const ck = (name, cond, extra = "") => {
  console.log((cond ? "  ok   " : "  FAIL ") + name + (extra ? `  [${extra}]` : ""));
  if (!cond) fails.push(name);
};
const MIN = 60e3, HOUR = 60 * MIN;
// the real clock: /health and the cron path read Date.now() themselves, so the
// fixtures must be relative to it (a pinned date passed once, then went stale)
const NOW = Date.now();

const healthyBuild = () => ({
  built_at: NOW - 10 * MIN, fetch_at: NOW - 12 * MIN, fetch_failed: [],
  articles: 580, newest_article_at: NOW - 2 * HOUR, predictions: 40, predictions_oracle: 0,
});
const healthyBeats = () => ({
  publish: { ts: NOW - 8 * MIN, ok: 1, fails: 0, detail: "" },
  "article:daily": { ts: NOW - 3 * HOUR, ok: 1, fails: 0, detail: "" },
  "article:match": { ts: NOW - 5 * HOUR, ok: 1, fails: 0, detail: "" },
});
const healthy = () => ({ build: healthyBuild(), beats: healthyBeats(), snapshot: { ts: NOW - 40e3 }, d1Error: null });

// ---- 1. the verdict --------------------------------------------------------
console.log("1. evaluate()");
let v = evaluate(healthy(), NOW);
ck("a healthy site is ok on every check", v.status === "ok",
   Object.entries(v.checks).filter(([, c]) => c.status !== "ok").map(([k]) => k).join(","));
ck("all eight checks are present",
   ["deploy", "fetch", "articles", "predictions", "d1", "publish", "claude", "live"].every(k => v.checks[k]));

let i = healthy(); i.build.built_at = NOW - 60 * MIN;
ck("a 60-min-old deploy warns (two skipped deploys are normal)", evaluate(i, NOW).checks.deploy.status === "warn");
i.build.built_at = NOW - 95 * MIN;
ck("a 95-min-old deploy FAILS (the 2026-09-13 skipped-deploy incident)", evaluate(i, NOW).checks.deploy.status === "fail");

i = healthy(); i.build.fetch_failed = ["goals"];
v = evaluate(i, NOW);
ck("one failed fetch source only warns, and is named", v.checks.fetch.status === "warn" && v.checks.fetch.msg.includes("goals"));
i.build.fetch_at = NOW - 4 * HOUR;
ck("no fresh fetch for 4 h FAILS", evaluate(i, NOW).checks.fetch.status === "fail");

i = healthy(); i.build.newest_article_at = NOW - 9.5 * HOUR;
ck("the 9.5 h overnight article gap (23:30 -> 09:00 Cairo) stays ok", evaluate(i, NOW).checks.articles.status === "ok");
i.build.newest_article_at = NOW - 17 * HOUR;
ck("17 h without an article FAILS", evaluate(i, NOW).checks.articles.status === "fail");

i = healthy(); i.beats["article:daily"].fails = 1;
ck("one failed Claude slot is ok (the next slot retries - the user's rule)", evaluate(i, NOW).checks.claude.status === "ok");
i.beats["article:daily"].fails = 2;
ck("two in a row warn", evaluate(i, NOW).checks.claude.status === "warn");
i.beats["article:match"].fails = 3;
v = evaluate(i, NOW);
ck("three in a row FAIL and name the worst workflow", v.checks.claude.status === "fail" && v.checks.claude.msg.startsWith("match:"), v.checks.claude.msg);

i = healthy(); i.beats.publish = { ts: NOW - 5 * MIN, ok: 0, fails: 1, detail: "fetch" };
ck("one red publish run warns and names the step", evaluate(i, NOW).checks.publish.status === "warn" && evaluate(i, NOW).checks.publish.msg.includes("fetch"));
i.beats.publish.fails = 3;
ck("three red publish runs in a row FAIL", evaluate(i, NOW).checks.publish.status === "fail");
i = healthy(); i.beats.publish.ts = NOW - 2 * HOUR;
ck("no publish heartbeat for 2 h FAILS (dispatch token dead, Actions down)", evaluate(i, NOW).checks.publish.status === "fail");

i = healthy(); i.snapshot = { ts: NOW - 12 * MIN };
ck("a live store frozen 12 min FAILS", evaluate(i, NOW).checks.live.status === "fail");

i = healthy(); i.d1Error = "D1_ERROR: daily limit exceeded";
v = evaluate(i, NOW);
ck("the D1 quota wall FAILS as d1 and skips the D1-based checks",
   v.checks.d1.status === "fail" && !v.checks.publish && !v.checks.live && v.checks.deploy.status === "ok");

i = healthy(); i.build = null;
ck("no build-info (first deploy) only warns", evaluate(i, NOW).checks.deploy.status === "warn" && evaluate(i, NOW).status !== "fail");

// ---- 2. when to page -------------------------------------------------------
console.log("2. decideAlert()");
const failing = (() => { const x = healthy(); x.build.built_at = NOW - 2 * HOUR; return evaluate(x, NOW); })();
let d = decideAlert(null, evaluate(healthy(), NOW), NOW);
ck("healthy + no history: silent, nothing written", d.text === null && d.state === null);
d = decideAlert(null, failing, NOW);
ck("a new failure pages once, in Arabic, with the /health link",
   d.text && d.text.startsWith("🔴") && d.text.includes("النشر") && d.text.includes("/health"), d.text);
const st1 = d.state;
d = decideAlert(st1, failing, NOW + 15 * MIN);
ck("the same failure 15 min later: silent, nothing written", d.text === null && d.state === null);
d = decideAlert(st1, failing, NOW + LIMITS.remindEvery + MIN);
ck("still failing after 6 h: one reminder", d.text && d.text.startsWith("⏰"));
const both = (() => { const x = healthy(); x.build.built_at = NOW - 2 * HOUR; x.snapshot = { ts: NOW - HOUR }; return evaluate(x, NOW); })();
d = decideAlert(st1, both, NOW + 30 * MIN);
ck("a second check starts failing: an update, and `since` is kept", d.text && d.text.startsWith("🟠") && d.state.since === st1.since);
// (evaluated at NOW: the fixtures are relative to NOW, only the clock of the decision moves)
d = decideAlert(st1, evaluate(healthy(), NOW), NOW + HOUR);
ck("recovery pages once, with how long it lasted", d.text && d.text.startsWith("✅") && d.text.includes("1.0 h"), d.text);
ck("warnings never page", decideAlert(null, (() => { const x = healthy(); x.build.built_at = NOW - 60 * MIN; return evaluate(x, NOW); })(), NOW).text === null);

// ---- 3. watchdog end to end against a fake D1 + Telegram ------------------
console.log("3. watchdog()");
function fakeEnv({ build = healthyBuild(), beats = healthyBeats(), snapTs = NOW - 40e3, d1Down = false, tg = true } = {}) {
  const meta = new Map([["snapshot", JSON.stringify({ ts: snapTs })]]);
  const writes = [];
  const stmt = (sql, args = []) => ({
    bind: (...a) => stmt(sql, a),
    async run() { if (d1Down) throw new Error("D1_ERROR: limit"); if (sql.includes("/*wd_set*/")) { writes.push("wd_set"); meta.set("watchdog", args[0]); } return {}; },
    async first() { if (d1Down) throw new Error("D1_ERROR: limit"); return sql.includes("/*wd_get*/") && meta.has("watchdog") ? { v: meta.get("watchdog") } : null; },
    async all() {
      if (d1Down) throw new Error("D1_ERROR: limit");
      if (sql.includes("/*hb_rows*/")) return { results: Object.entries(beats).map(([name, b]) => ({ name, ...b })) };
      if (sql.includes("/*hb_snap*/")) return { results: [{ v: meta.get("snapshot") }] };
      return { results: [] };
    },
  });
  return {
    writes,
    ASSETS: { fetch: async () => build ? new Response(JSON.stringify(build)) : new Response("nf", { status: 404 }) },
    DB: { prepare: (sql) => stmt(sql), batch: async (ss) => { const out = []; for (const s of ss) out.push(await s.all()); return out; } },
    ...(tg ? { TG_BOT_TOKEN: "t", TG_ALERT_CHAT_ID: "123" } : {}),
  };
}
const sent = [];
globalThis.fetch = async (url, init) => { sent.push(JSON.parse(init.body).text); return new Response("{}", { status: 200 }); };

let env = fakeEnv();
let r = await watchdog(env, NOW);
ck("healthy site: no message, no D1 write", !r.sent && sent.length === 0 && env.writes.length === 0);

const badBuild = { ...healthyBuild(), built_at: NOW - 2 * HOUR };
// the live snapshot is stamped at the LAST tick so it stays fresh across all three
env = fakeEnv({ build: badBuild, snapTs: NOW + 30 * MIN - 40e3 });
await watchdog(env, NOW);
await watchdog(env, NOW + 15 * MIN);
await watchdog(env, NOW + 30 * MIN);
ck("three ticks of one incident send ONE message and write state ONCE", sent.length === 1 && env.writes.length === 1, `sent ${sent.length}, writes ${env.writes.length}`);

sent.length = 0;
env = fakeEnv({ build: badBuild, tg: false });
r = await watchdog(env, NOW);
ck("without the Telegram secrets it evaluates but never sends", !r.sent && sent.length === 0 && r.verdict.status === "fail");

sent.length = 0;
env = fakeEnv({ d1Down: true });
r = await watchdog(env, NOW);
ck("D1 down: the watchdog still runs and pages about d1", r.verdict.checks.d1.status === "fail" && sent.length === 1 && sent[0].includes("D1"));

// ---- 4. /health ------------------------------------------------------------
console.log("4. /health");
const store = new Map();
globalThis.caches = { default: { match: async (k) => store.get(k.url)?.clone(), put: async (k, res) => { store.set(k.url, res); } } };
const waits = [];
const ctx = { waitUntil: (p) => waits.push(p) };
let res = await healthResponse(fakeEnv(), ctx);
await Promise.all(waits);
let body = await res.json();
ck("healthy: HTTP 200 and status ok", res.status === 200 && body.status === "ok");
ck("edge-cached for 60 s (bounds the D1 reads of a public URL)", (res.headers.get("cache-control") || "").includes("s-maxage=60"));
store.clear();
res = await healthResponse(fakeEnv({ build: badBuild }), ctx);
ck("failing: HTTP 503, so an outside uptime monitor can watch one URL", res.status === 503);

// ---- 5. the Worker wiring ---------------------------------------------------
console.log("5. worker.js");
const worker = (await import(new URL("../worker.js", import.meta.url).href)).default;
store.clear();
const hres = await worker.fetch(new Request("https://yallascore.site/health"), fakeEnv(), ctx);
ck("GET /health is routed to health.js", hres.status === 200 && (await hres.json()).checks.deploy);
const cronWaits = [];
sent.length = 0;
globalThis.fetch = async (url, init) => {
  if (String(url).includes("api.telegram.org")) sent.push(JSON.parse(init.body).text);
  return new Response(null, { status: 204 });
};
await worker.scheduled({ cron: "1,16,31,46 * * * *", scheduledTime: NOW }, { ...fakeEnv({ build: badBuild }), GH_TOKEN: "x" },
                       { waitUntil: (p) => cronWaits.push(p) });
await Promise.all(cronWaits);
ck("the 15-minute cron runs the watchdog in waitUntil", cronWaits.length === 1 && sent.length === 1);
cronWaits.length = 0;
await worker.scheduled({ cron: "0 6,8,11,14,17,19 * * *", scheduledTime: NOW }, { ...fakeEnv(), GH_TOKEN: "x" },
                       { waitUntil: (p) => cronWaits.push(p) });
ck("the article cron does NOT run it", cronWaits.length === 0);

console.log(fails.length ? `\n${fails.length} FAILED` : "\nALL OK");
process.exit(fails.length ? 1 : 0);
