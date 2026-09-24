// Functional test: run worker.js's /live.json handler in Node with a mocked
// 365scores. Reproduces the 2026-09-02 screenshot: list = 1-0 @61', detail = 2-0 @63'.
import assert from "node:assert/strict";

const team = (id, name, score) => ({ id, name, score });
const goalEv = (playerId, competitorId, gameTime) =>
  ({ eventType: { name: "هدف" }, playerId, competitorId, gameTime, addedTime: 0 });

// ---- mocked upstream ---------------------------------------------------------
const LIST = { games: [
  // the screenshot game: list lags (1-0, 61')
  { id: 111, statusGroup: 3, competitionId: 552, statusText: "الشوط الثاني", shortStatusText: "2",
    gameTime: 61, gameTimeDisplay: "61'", homeCompetitor: team(1, "سيراميكا كليوباترا", 1), awayCompetitor: team(2, "مودرن سبورت", 0) },
  // a live European game, no goals yet, 1st half
  { id: 222, statusGroup: 3, competitionId: 7, statusText: "الشوط الأول", shortStatusText: "1",
    gameTime: 20, gameTimeDisplay: "20'", homeCompetitor: team(3, "ليفربول", 0), awayCompetitor: team(4, "أرسنال", 0) },
  // detail call will FAIL for this one → must keep list values
  { id: 333, statusGroup: 3, competitionId: 11, statusText: "الشوط الأول", shortStatusText: "1",
    gameTime: 30, gameTimeDisplay: "30'", homeCompetitor: team(5, "ريال مدريد", 1), awayCompetitor: team(6, "برشلونة", 1) },
  // finished, no goals → no detail call
  { id: 444, statusGroup: 4, competitionId: 17, homeCompetitor: team(7, "روما", 0), awayCompetitor: team(8, "لاتسيو", 0) },
  // just ended with a goal → detail call (goals only path, sg 4)
  { id: 555, statusGroup: 4, justEnded: true, competitionId: 25, homeCompetitor: team(9, "بايرن", 1), awayCompetitor: team(10, "دورتموند", 0) },
  // list says ENDED (just now), detail still says LIVE at 88' → must stay ended
  { id: 777, statusGroup: 4, justEnded: true, competitionId: 552, homeCompetitor: team(13, "الزمالك", 1), awayCompetitor: team(14, "المصري", 0) },
  // scheduled → skipped entirely
  { id: 666, statusGroup: 2, competitionId: 7, homeCompetitor: team(11, "تشيلسي", -1), awayCompetitor: team(12, "توتنهام", -1) },
]};

const DETAIL = {
  111: { game: { statusGroup: 3, statusText: "الشوط الثاني", shortStatusText: "2", gameTime: 63, gameTimeDisplay: "63'",
    homeCompetitor: team(1, "سيراميكا كليوباترا", 2), awayCompetitor: team(2, "مودرن سبورت", 0),
    members: [{ id: 91, name: "صديق أوجولا" }, { id: 92, name: "أحمد بلحاج" }],
    events: [goalEv(91, 1, 6), goalEv(92, 1, 63)] } },
  222: { game: { statusGroup: 3, statusText: "شوط", shortStatusText: "شوط", gameTime: 45, gameTimeDisplay: "45'",
    homeCompetitor: team(3, "ليفربول", 0), awayCompetitor: team(4, "أرسنال", 0), members: [], events: [] } },
  777: { game: { statusGroup: 3, statusText: "الشوط الثاني", shortStatusText: "2", gameTime: 88, gameTimeDisplay: "88'",
    homeCompetitor: team(13, "الزمالك", 1), awayCompetitor: team(14, "المصري", 0),
    members: [{ id: 94, name: "زيزو" }], events: [goalEv(94, 13, 30)] } },
  // 333 → HTTP 500
  555: { game: { statusGroup: 4, homeCompetitor: team(9, "بايرن", 1), awayCompetitor: team(10, "دورتموند", 0),
    members: [{ id: 93, name: "هاري كين" }], events: [goalEv(93, 9, 77)] } },
};

const calls = [];
globalThis.fetch = async (url, opts) => {
  calls.push(String(url));
  if (String(url).includes("/games/current/")) return Response.json(LIST);
  const m = String(url).match(/gameId=(\d+)/);
  const d = m && DETAIL[m[1]];
  return d ? Response.json(d) : new Response("boom", { status: 500 });
};
const puts = [];
globalThis.caches = { default: { match: async () => undefined, put: async (k, r) => puts.push(r) } };

// ---- run ---------------------------------------------------------------------------
const worker = (await import(new URL("../worker.js", import.meta.url).href)).default;
const res = await worker.fetch(new Request("https://yallascore.site/live.json"), {}, { waitUntil() {} });
const j = await res.json();
console.log(JSON.stringify(j, null, 1));

const by = Object.fromEntries(j.games.map(g => [g.h, g]));
// 1) the screenshot bug: detail wins → 2-0 @ 63', 2 goals consistent with score
assert.equal(by["سيراميكا كليوباترا"].hs, 2);
assert.equal(by["سيراميكا كليوباترا"].as, 0);
assert.equal(by["سيراميكا كليوباترا"].min, "63'");
assert.equal(by["سيراميكا كليوباترا"].gt, 63);
assert.equal(by["سيراميكا كليوباترا"].hf, 2);
assert.equal(by["سيراميكا كليوباترا"].goals.length, 2);
assert.equal(by["سيراميكا كليوباترا"].goals[1].p, "أحمد بلحاج");
// 2) detail says half-time → استراحة, gt 0
assert.equal(by["ليفربول"].min, "استراحة");
assert.equal(by["ليفربول"].gt, 0);
assert.equal(by["ليفربول"].live, true);
// 3) detail failed → list values kept, still live
assert.equal(by["ريال مدريد"].hs, 1);
assert.equal(by["ريال مدريد"].min, "30'");
assert.equal(by["ريال مدريد"].live, true);
assert.equal(by["ريال مدريد"].goals, undefined);
// 4) finished without goals → untouched, no detail call
assert.equal(by["روما"].live, false);
assert.ok(!calls.some(u => u.includes("gameId=444")));
// 5) just-ended with goal → goals attached, stays not live
assert.equal(by["بايرن"].goals.length, 1);
assert.equal(by["بايرن"].live, false);
// 5b) list ended + detail live → stays ended, no minute, goals attached, not counted in dt
assert.equal(by["الزمالك"].live, false);
assert.equal(by["الزمالك"].min, "");
assert.equal(by["الزمالك"].gt, 0);
assert.equal(by["الزمالك"].goals.length, 1);
// 6) scheduled skipped; dt counts LIVE games whose detail was applied (111, 222 only)
assert.equal(j.games.length, 6);
assert.equal(j.dt, 2);
assert.equal(j.ok, true);
assert.equal(j.src, "multi");
// 7) goals count always equals score for every game carrying goals
for (const g of j.games) if (g.goals) {
  assert.equal(g.goals.filter(x => x.s === "h").length, g.hs, g.h);
  assert.equal(g.goals.filter(x => x.s === "a").length, g.as, g.h);
}
// 8) cacheable + cached (ok reply)
assert.match(res.headers.get("cache-control"), /s-maxage/);
assert.equal(puts.length, 1);
// 9) detail calls: exactly 111, 222, 333, 555
const gids = calls.filter(u => u.includes("gameId=")).map(u => u.match(/gameId=(\d+)/)[1]).sort();
assert.deepEqual(gids, ["111", "222", "333", "555", "777"]);
// 10) Egyptian-scope comps are ALWAYS fetched individually and merged without duplicates
const listCalls = calls.filter(u => u.includes("/games/current/"));
assert.equal(listCalls.length, 4, listCalls);                      // multi + 552 + 624 + 588
assert.ok(listCalls.some(u => u.endsWith("competitions=552")) && listCalls.some(u => u.endsWith("competitions=624"))
       && listCalls.some(u => u.endsWith("competitions=588")));    // AFCON qualifiers (2026-09-20)
assert.equal(new Set(j.games.map(g => g.h + "|" + g.a)).size, j.games.length, "duplicated game after merge");
console.log("ALL ASSERTIONS PASSED — detail calls:", gids.join(","), "dt =", j.dt);
