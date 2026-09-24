// worker.js scheduled(): which workflow each cron string dispatches, and that
// the match-article crons fire ONLY when the Cairo clock is on a slot - the
// crons list both the summer (UTC+3) and winter (UTC+2) hour of every slot,
// so half of their firings must be skipped.
import assert from "node:assert/strict";

const mod = await import(new URL("../worker.js", import.meta.url).href);
const worker = mod.default;
const { matchSlotCairo } = mod;

// ---- the pure slot check --------------------------------------------------
// September: Cairo = UTC+3. 10:00Z = 13:00 Cairo (slot); 09:00Z = 12:00 (not).
assert.equal(matchSlotCairo(new Date("2026-09-12T10:00:00Z")), "13:00");
assert.equal(matchSlotCairo(new Date("2026-09-12T09:00:00Z")), null);
assert.equal(matchSlotCairo(new Date("2026-09-12T14:00:00Z")), "17:00");
assert.equal(matchSlotCairo(new Date("2026-09-12T17:00:00Z")), "20:00");
assert.equal(matchSlotCairo(new Date("2026-09-12T20:30:00Z")), "23:30");
assert.equal(matchSlotCairo(new Date("2026-09-12T19:30:00Z")), null);
// December: Cairo = UTC+2. Now 09:00Z IS 11:00... no: 11:00Z = 13:00 Cairo.
assert.equal(matchSlotCairo(new Date("2026-12-12T11:00:00Z")), "13:00");
assert.equal(matchSlotCairo(new Date("2026-12-12T10:00:00Z")), null);   // 12:00 Cairo in winter
assert.equal(matchSlotCairo(new Date("2026-12-12T21:30:00Z")), "23:30");
assert.equal(matchSlotCairo(new Date("2026-12-12T20:30:00Z")), null);   // 22:30 Cairo in winter
console.log("1 OK: Cairo slot check is DST-proof (summer 10:00Z / winter 11:00Z are both 13:00 Cairo)");

// ---- the handler ----------------------------------------------------------
const dispatched = [];
globalThis.fetch = async (url) => {
  dispatched.push(url.match(/workflows\/([^/]+)\/dispatches/)[1]);
  return { status: 204, text: async () => "" };
};
const env = { GH_TOKEN: "t" };
const run = (cron, iso) => worker.scheduled({ cron, scheduledTime: Date.parse(iso) }, env, {});

await run("1,16,31,46 * * * *", "2026-09-12T10:01:00Z");
await run("0 6,8,11,14,17,19 * * *", "2026-09-12T10:00:00Z");   // cut from 10 slots to 6 on 2026-09-17 - must match wrangler.toml AND worker.js exactly
assert.deepEqual(dispatched, ["publish.yml", "daily-article.yml"]);
console.log("2 OK: the 15-minute cron -> publish, the article cron -> daily-article");

dispatched.length = 0;
await run("0 9,10,13,14,16,17 * * *", "2026-09-12T10:00:00Z");   // 13:00 Cairo: slot
await run("0 9,10,13,14,16,17 * * *", "2026-09-12T09:00:00Z");   // 12:00 Cairo: DST twin, skip
await run("30 19,20 * * *", "2026-09-12T20:30:00Z");             // 23:30 Cairo: slot
await run("30 19,20 * * *", "2026-09-12T19:30:00Z");             // 22:30 Cairo: skip
assert.deepEqual(dispatched, ["match-article.yml", "match-article.yml"]);
console.log("3 OK: match-article crons dispatch on the slot and skip the DST twin");

dispatched.length = 0;
await run("0 9,10,13,14,16,17 * * *", "2026-12-12T11:00:00Z");   // winter: 13:00 Cairo
await run("0 9,10,13,14,16,17 * * *", "2026-12-12T10:00:00Z");   // winter: 12:00 Cairo
assert.deepEqual(dispatched, ["match-article.yml"]);
console.log("4 OK: in winter the other twin is the one that fires");

// no token -> nothing at all
dispatched.length = 0;
await worker.scheduled({ cron: "30 19,20 * * *", scheduledTime: Date.parse("2026-09-12T20:30:00Z") }, {}, {});
assert.deepEqual(dispatched, []);
console.log("5 OK: without GH_TOKEN nothing is dispatched");
console.log("ALL WORKER CRON TESTS PASSED");
