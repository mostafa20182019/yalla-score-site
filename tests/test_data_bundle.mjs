// worker.js /data/bundle (2026-09-24, step 3): the data store's read-only door
// for machines without a Cloudflare token (the laptop, the tests job, a local
// checkout). It must serve the KV bytes untouched, cache at the edge, and say
// 404 - not 500 - when there is no binding or nothing stored yet.
//
//   node tests/test_data_bundle.mjs
const worker = (await import(new URL("../worker.js", import.meta.url).href)).default;
let fails = 0;
const ck = (name, cond, extra = "") => { console.log((cond ? "  ok   " : "  FAIL ") + name + (extra ? `  [${extra}]` : "")); if (!cond) fails++; };

const store = new Map();
globalThis.caches = { default: { match: async (k) => store.get(k.url)?.clone(), put: async (k, r) => { store.set(k.url, r); } } };
const waits = []; const ctx = { waitUntil: (p) => waits.push(p) };
const req = () => new Request("https://yallascore.site/data/bundle");

let r = await worker.fetch(req(), {}, ctx);
ck("1 no DATA binding: 404, not a crash", r.status === 404);

const bytes = new Uint8Array([31, 139, 8, 0, 1, 2, 3, 250]);          // gzip magic + junk
let reads = 0;
const env = { DATA: { get: async (k, t) => { reads++; return k === "bundle-v1" && t === "arrayBuffer" ? bytes.buffer : null; } } };
r = await worker.fetch(req(), env, ctx); await Promise.all(waits);
const got = new Uint8Array(await r.arrayBuffer());
ck("2 the KV bytes are served untouched", r.status === 200 && got.length === bytes.length && got.every((b, i) => b === bytes[i]));
ck("3 edge-cached for 60 s", (r.headers.get("cache-control") || "").includes("s-maxage=60"));
r = await worker.fetch(req(), env, ctx);
ck("4 a second pull inside the minute costs no KV read", reads === 1 && r.status === 200, `${reads} reads`);

store.clear();
r = await worker.fetch(req(), { DATA: { get: async () => null } }, ctx);
ck("5 an empty store is a 404", r.status === 404);

console.log(fails ? `\n${fails} FAILED` : "\nALL OK");
process.exit(fails ? 1 : 0);
