// /live/ev/<gameId>.json - the cards and substitutions of one game for its own
// match page (2026-11-13). Runs worker.js in Node with a mocked 365scores.
//
//   node tests/test_live_events.mjs
//
// The page's events list is baked at build time; this endpoint lets the page
// repaint its card and substitution rows from the game's detail while the
// match is on. What must hold: the build's own parsing rules (fetch_data.
// _detail_rows), a failure that is never cached, and nothing for a game
// outside the competitions we cover.
import assert from "node:assert/strict";

const team = (id, name, score) => ({ id, name, score });
const DETAIL = {
  // Nigeria 3 - 1 Tanzania, 62' (the user's screenshot), AFCON qualifiers = 588
  900: { game: { id: 900, competitionId: 588, statusGroup: 3, gameTime: 62,
    homeCompetitor: team(1, "نيجيريا", 3), awayCompetitor: team(2, "تنزانيا", 1),
    members: [{ id: 11, name: "الحسن يوسف" }, { id: 12, name: "موسيس سيمون " }, { id: 13, name: "أديمولا لوكمان" },
              { id: 21, name: "نوفاتوس ديسماس" }, { id: 22, name: "ألفونس مسانغا" }, { id: 23, name: "بديل تنزانيا" }],
    events: [
      { eventType: { id: 1, name: "هدف" }, playerId: 11, competitorId: 1, gameTime: 2 },
      { eventType: { id: 2, name: "بطاقة صفراء" }, playerId: 11, competitorId: 1, gameTime: 12 },
      { eventType: { id: 1000, name: "Substitution" }, playerId: 12, extraPlayers: [13], competitorId: 1, gameTime: 45 },
      { eventType: { id: 3, name: "بطاقة حمراء" }, playerId: 21, competitorId: 2, gameTime: 45, addedTime: 2 },
      { eventType: { name: "بطاقة صفراء ثانية" }, playerId: 22, competitorId: 2, gameTime: 58 },
      { eventType: { name: "تبديل" }, playerId: 23, extraPlayers: [22], num: 2, gameTime: 60 },
      // unusable rows: a card with no known player, a change with no second player
      { eventType: { id: 2, name: "بطاقة صفراء" }, playerId: 999, competitorId: 1, gameTime: 61 },
      { eventType: { name: "تبديل" }, playerId: 12, extraPlayers: [], competitorId: 1, gameTime: 61 },
    ] } },
  // a game of a competition we do not cover
  901: { game: { id: 901, competitionId: 4242, statusGroup: 3, homeCompetitor: team(5, "x", 0), awayCompetitor: team(6, "y", 0),
    members: [{ id: 1, name: "a" }], events: [{ eventType: { id: 2, name: "card" }, playerId: 1, competitorId: 5, gameTime: 3 }] } },
};
const calls = [];
globalThis.fetch = async (url) => {
  calls.push(String(url));
  const m = String(url).match(/gameId=(\d+)/);
  const d = m && DETAIL[m[1]];
  return d ? Response.json(d) : new Response("boom", { status: 500 });
};
const puts = [];
globalThis.caches = { default: { match: async () => undefined, put: async (k, r) => puts.push(String(k.url)) } };
const worker = (await import(new URL("../worker.js", import.meta.url).href)).default;
const waits = [];
const ctx = { waitUntil(p) { waits.push(p); } };
const ASSETS = { fetch: async () => new Response("asset", { status: 200 }) };
const get = (p) => worker.fetch(new Request("https://elgoon.com" + p), { ASSETS }, ctx);

// 1) the screenshot game
const r = await get("/live/ev/900.json?b=123");
const j = await r.json();
await Promise.all(waits);
assert.equal(j.ok, true);
assert.equal(j.id, 900);
assert.equal(j.live, true);
assert.deepEqual(j.cards, [
  { s: "h", p: "الحسن يوسف", m: "12", c: "y" },
  { s: "a", p: "نوفاتوس ديسماس", m: "45+2", c: "r" },
  { s: "a", p: "ألفونس مسانغا", m: "58", c: "r" },          // a second yellow is a red
], "cards: side, player, minute with added time, colour");
assert.deepEqual(j.subs, [
  { s: "h", i: "موسيس سيمون", o: "أديمولا لوكمان", m: "45" }, // the member name is trimmed
  { s: "a", i: "بديل تنزانيا", o: "ألفونس مسانغا", m: "60" },  // no competitorId: num 2 = away
], "substitutions: who came on, who went off");
assert.ok(!JSON.stringify(j).includes("هدف"), "goals are not this endpoint's business (/live.json names them)");
assert.equal(r.headers.get("cache-control"), "public, max-age=10, s-maxage=20");
assert.equal(r.headers.get("x-robots-tag"), "noindex");
assert.deepEqual(puts, ["https://elgoon.com/live/ev/900.json"], "cached on the bare path, without the ?b= bucket");
assert.ok(calls[0].includes("/web/game/") && calls[0].includes("gameId=900"), "the same detail URL the live refresh uses");

// 2) an upstream failure: ok false, never cached
const bad = await get("/live/ev/555.json");
assert.deepEqual(await bad.json(), { ok: false });
assert.equal(bad.headers.get("cache-control"), "no-store");
assert.equal(puts.length, 1, "a failure is not cached");

// 3) a game outside the competitions we cover answers nothing
const other = await get("/live/ev/901.json");
assert.deepEqual(await other.json(), { ok: false });

// 4) only a numeric id is this route; anything else is an ordinary asset path
const before = calls.length;
const notOurs = await get("/live/ev/abc.json");
assert.equal(await notOurs.text(), "asset");
assert.equal(calls.length, before, "no upstream call for a non-numeric id");

console.log("ALL ASSERTIONS PASSED - /live/ev: cards", j.cards.length, "subs", j.subs.length);
