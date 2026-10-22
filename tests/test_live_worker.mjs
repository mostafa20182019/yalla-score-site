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
assert.equal(listCalls.length, 5, listCalls);                      // multi + 552 + 624 + 588 + 627 (Confederation Cup, 2026-10-17)
assert.ok(listCalls.some(u => u.endsWith("competitions=552")) && listCalls.some(u => u.endsWith("competitions=624"))
       && listCalls.some(u => u.endsWith("competitions=588"))     // AFCON qualifiers (2026-09-20)
       && listCalls.some(u => u.endsWith("competitions=627")));    // CAF Confederation Cup (2026-10-17)
assert.equal(new Set(j.games.map(g => g.h + "|" + g.a)).size, j.games.length, "duplicated game after merge");
// 12) one canonical origin (2026-10-18): http and www both 301 straight to https on the bare host
for (const [from, to] of [["http://yallascore.site/m/1?b=2", "https://yallascore.site/m/1?b=2"],
                          ["http://www.yallascore.site/", "https://yallascore.site/"],
                          ["https://www.yallascore.site/news", "https://yallascore.site/news"],
                          ["https://yalla-score.someone.workers.dev/a/5", "https://yallascore.site/a/5"]]) {
  const r = await worker.fetch(new Request(from), {}, { waitUntil() {} });
  assert.equal(r.status, 301, from);
  assert.equal(r.headers.get("location"), to, from);
}
const okRes = await worker.fetch(new Request("https://yallascore.site/live.json"), {}, { waitUntil() {} });
assert.notEqual(okRes.status, 301, "the canonical origin itself is never redirected");
// 13) a missing asset is never cached for a week (2026-10-18): root-extras/_headers
// gives /media/* max-age=604800 and the assets layer puts it on the 404 too, so the
// edge kept "not found" for a photo the next deploy brought. Error answers leave
// with no-store; a found file keeps its header untouched.
{
  const ASSETS = { fetch: async (req) => new URL(req.url).pathname.endsWith("missing.jpg")
    ? new Response("not found", { status: 404, headers: { "cache-control": "public, max-age=0, must-revalidate, public, max-age=604800" } })
    : new Response("jpg", { status: 200, headers: { "cache-control": "public, max-age=604800" } }) };
  const miss = await worker.fetch(new Request("https://yallascore.site/media/missing.jpg"), { ASSETS }, { waitUntil() {} });
  assert.equal(miss.status, 404);
  assert.equal(miss.headers.get("cache-control"), "no-store", "a 404 must not inherit the 7-day media cache");
  assert.equal(await miss.text(), "not found", "the body passes through");
  const hitRes = await worker.fetch(new Request("https://yallascore.site/media/found.jpg"), { ASSETS }, { waitUntil() {} });
  assert.equal(hitRes.status, 200);
  assert.equal(hitRes.headers.get("cache-control"), "public, max-age=604800", "a found file keeps its long cache");
}
// 14) the two jobs that ride on existing crons (2026-10-22): the nightly results
// card at 22:16 UTC and the Monday 06:00 European round-up - and only then
{
  const seen = [];
  const envD = { GH_TOKEN: "gh", DB: undefined };
  const realFetch = globalThis.fetch;
  globalThis.fetch = async (url, init) => {
    const u = String(url);
    if (u.includes("/actions/workflows/")) { seen.push([u.split("/workflows/")[1].split("/")[0], JSON.parse(init.body || "{}").inputs || null]); return new Response(null, { status: 204 }); }
    return realFetch(url, init);
  };
  await worker.scheduled({ cron: "1,16,31,46 * * * *", scheduledTime: Date.UTC(2026, 9, 22, 22, 16) }, envD, { waitUntil() {} });
  await worker.scheduled({ cron: "1,16,31,46 * * * *", scheduledTime: Date.UTC(2026, 9, 22, 21, 16) }, envD, { waitUntil() {} });
  await worker.scheduled({ cron: "0 6,8,11,14,17,19 * * *", scheduledTime: Date.UTC(2026, 9, 26, 6, 0) }, envD, { waitUntil() {} });   // a Monday
  await worker.scheduled({ cron: "0 6,8,11,14,17,19 * * *", scheduledTime: Date.UTC(2026, 9, 27, 6, 0) }, envD, { waitUntil() {} });   // a Tuesday
  globalThis.fetch = realFetch;
  const day = seen.filter(x => x[0] === "fb-post.yml");
  const eu = seen.filter(x => x[0] === "round-article.yml");
  assert.deepEqual(day, [["fb-post.yml", { daycard: "results" }]], "the results card only at 22:16 UTC: " + JSON.stringify(seen));
  assert.deepEqual(eu, [["round-article.yml", { competition: "auto-europe" }]], "the European round-up only on Monday 06:00: " + JSON.stringify(seen));
  assert.equal(seen.filter(x => x[0] === "daily-article.yml").length, 2, "the daily article still goes out both mornings");
}
console.log("ALL ASSERTIONS PASSED — detail calls:", gids.join(","), "dt =", j.dt);
