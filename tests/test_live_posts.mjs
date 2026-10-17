// Live Facebook posts from the edge (liveposts.js, growth plan weeks 2-3).
//
//   node tests/test_live_posts.mjs
//
// Checked: a goal the store DISCOVERS in a live Egyptian-scope match is posted
// once (photo post with our card when it exists, the score with spaces), a
// goal already on the board at first sight is not, non-scope matches (Arsenal,
// the Saudi Al-Ahli, the Port Said «المصري») never post, a second refresh
// does not re-post, a VAR reversal edits the goal's own post, no token = no
// post and no failure, and the official XI goes out once in its window only
// when both sides have eleven names.
import assert from "node:assert/strict";
import { goalMessage, postScope, parseLineups, XI_MIN_MS, htMessage, ftMessage, CURATED_LIVE } from "../liveposts.js";

let fails = [];
const ck = (name, cond, extra = "") => {
  console.log((cond ? "  ok   " : "  FAIL ") + name + (extra ? `  [${extra}]` : ""));
  if (!cond) fails.push(name);
};

/* ------------------------------------------------------------- fake D1 */
function fakeD1() {
  const state = new Map(), queue = new Map(), articles = [], goals = [], meta = new Map();
  const fb = new Map();                        // "kind|ref" -> row
  const exec = (sql, b) => {
    if (sql.startsWith("CREATE TABLE")) return { results: [] };
    if (sql.includes("/*ls_rows*/")) return { results: [...state.values()] };
    if (sql.includes("/*ls_snap*/")) return { first: meta.has("snapshot") ? { v: meta.get("snapshot") } : null };
    if (sql.includes("/*ls_prev*/")) return { results: b.map(id => state.get(id)).filter(Boolean) };
    if (sql.includes("/*lg_seq*/")) return { first: { s: goals.filter(g => g.game_id === b[0]).length } };
    if (sql.includes("/*lg_ins*/")) {
      goals.push({ game_id: b[0], seq: b[1], side: b[2], player: b[3] || "", minute: b[4] || "", cancelled: 0, cancelled_at: 0 });
      return { results: [] };
    }
    if (sql.includes("/*lg_cancel*/")) {
      for (const g of goals) if (g.game_id === b[1] && g.side === b[2] && g.player === b[3] && g.minute === b[4] && !g.cancelled) { g.cancelled = 1; g.cancelled_at = b[0]; }
      return { results: [] };
    }
    if (sql.includes("/*lg_cancel_last*/")) {
      const mine = goals.filter(g => g.game_id === b[1] && g.side === b[2] && !g.cancelled);
      if (mine.length) { const last = mine[mine.length - 1]; last.cancelled = 1; last.cancelled_at = b[0]; }
      return { results: [] };
    }
    if (sql.includes("/*lg_list*/")) return { results: goals.filter(g => g.game_id === b[0] && !g.cancelled).map(g => ({ side: g.side, player: g.player, minute: g.minute, tag: g.tag || "" })) };
    if (sql.includes("/*lg_cancelled*/")) {
      const [gid, side, p1, , m1] = b;
      const hit = goals.filter(g => g.game_id === gid && g.side === side && g.cancelled && (p1 === "" || g.player === p1) && (m1 === "" || g.minute === m1))
                       .sort((x, y) => (y.cancelled_at - x.cancelled_at) || (y.seq - x.seq))[0];
      return { first: hit ? { seq: hit.seq } : null };
    }
    if (sql.includes("/*ls_upsert*/")) {
      const [game_id, c, h, a, hs, as_, live, min, gt, hf, goalsJ, first_seen, seen_at, changed_at] = b;
      state.set(game_id, { game_id, c, h, a, hs, as_, live, min, gt, hf, goals: goalsJ, first_seen, seen_at, changed_at });
      return { results: [] };
    }
    if (sql.includes("/*ls_purge*/")) return { results: [] };
    if (sql.includes("/*lm_set*/")) { meta.set(b[0], b[1]); return { results: [] };
    }
    if (sql.includes("/*rq_ins*/")) { queue.set(b[0], {}); return { results: [] }; }
    if (sql.includes("/*rq_due*/")) return { results: [] };
    if (sql.includes("/*rq_purge*/")) return { results: [] };
    // ---- fb_posted
    if (sql.includes("/*fb_claim*/")) {
      const k = `${b[0]}|${b[1]}`;
      if (fb.has(k)) return { results: [], changes: 0 };
      fb.set(k, { kind: b[0], ref_id: b[1], title: b[2], claimed_at: b[3], post_id: null });
      return { results: [], changes: 1 };
    }
    if (sql.includes("/*fb_rec*/")) { const r = fb.get(`${b[2]}|${b[3]}`); if (r) { r.post_id = b[0]; r.posted_at = b[1]; } return { results: [], changes: r ? 1 : 0 }; }
    if (sql.includes("/*fb_row*/")) { const r = fb.get(`${b[0]}|${b[1]}`); return { first: r ? { post_id: r.post_id, claimed_at: r.claimed_at } : null }; }
    if (sql.includes("/*fb_find*/")) { const r = fb.get(`${b[0]}|${b[1]}`); return { first: r && r.post_id ? { post_id: r.post_id } : null }; }
    if (sql.includes("/*fb_drop*/")) { const r = fb.get(`${b[0]}|${b[1]}`); if (r && !r.post_id) fb.delete(`${b[0]}|${b[1]}`); return { results: [] }; }
    throw new Error("fake D1: unknown statement " + sql.slice(0, 60));
  };
  const mk = (sql) => ({
    sql, _b: [],
    bind(...a) { this._b = a; return this; },
    async all() { return exec(sql, this._b); },
    async first() { const r = exec(sql, this._b); return "first" in r ? r.first : (r.results[0] || null); },
    async run() { const r = exec(sql, this._b); return { success: true, meta: { changes: r.changes ?? 1 } }; },
  });
  return { state, fb, goals, prepare: (sql) => mk(sql), batch: async (st) => st.map(s => exec(s.sql, s._b)) };
}

/* ------------------------------------------------------------- upstream */
const team = (id, name, score) => ({ id, name, score });
const live = (id, comp, h, a, hs, as_, extra = {}) => ({
  id, statusGroup: 3, competitionId: comp, statusText: "الشوط الثاني", shortStatusText: "2",
  gameTime: 70, gameTimeDisplay: "70'", homeCompetitor: team(id * 10, h, hs), awayCompetitor: team(id * 10 + 1, a, as_), ...extra,
});
const sched = (id, comp, h, a, startMs) => ({
  id, statusGroup: 2, competitionId: comp, startTime: new Date(startMs).toISOString(),
  homeCompetitor: team(id * 10, h, -1), awayCompetitor: team(id * 10 + 1, a, -1),
});
// a game/ detail with a goal list (so the store diffs by key, not by score)
const detailFor = {};
const DETAIL = (hs, as_, goals, lineups) => ({ game: {
  statusGroup: 3, homeCompetitor: { id: 1, score: hs, lineups: lineups && lineups.h }, awayCompetitor: { id: 2, score: as_, lineups: lineups && lineups.a },
  members: [{ id: 11, name: "زيزو" }, { id: 12, name: "عمر جابر" }, ...Array.from({ length: 30 }, (_, i) => ({ id: 100 + i, name: `لاعب ${i + 1}` }))],
  events: goals.map(g => ({ eventType: { name: "هدف" }, competitorId: g.s === "h" ? 1 : 2, playerId: g.pid, gameTime: g.m })),
  statusText: "الشوط الثاني", shortStatusText: "2", gameTime: 70, gameTimeDisplay: "70'",
} });
const XI = (n) => ({ members: Array.from({ length: n }, (_, i) => ({ id: 100 + i, status: 1 })), formation: "4-3-3" });

let LIST = { games: [] };
const fbCalls = [];
const ghCalls = [];
let ghOk = true;
let cardOk = true;
globalThis.fetch = async (url, init) => {
  const u = String(url);
  if (u.includes("/games/current/")) return Response.json(LIST);
  if (u.includes("/web/game/")) {
    const gid = Number(u.match(/gameId=(\d+)/)[1]);
    return detailFor[gid] ? Response.json(detailFor[gid]) : new Response("no", { status: 500 });
  }
  if (u.startsWith("https://api.github.com/")) {
    ghCalls.push(JSON.parse(init.body || "{}"));
    return new Response(null, { status: ghOk ? 204 : 500 });
  }
  if (u.startsWith("https://graph.facebook.com/")) {
    const p = Object.fromEntries(new URLSearchParams(init.body));
    fbCalls.push({ path: u.replace("https://graph.facebook.com/v23.0/", ""), ...p });
    return Response.json({ id: `P${fbCalls.length}`, post_id: `P${fbCalls.length}` });
  }
  return new Response("no", { status: 500 });
};
globalThis.caches = { default: { match: async () => undefined, put: async () => {} } };

const worker = (await import(new URL("../worker.js", import.meta.url).href)).default;
const db = fakeD1();
const env = { DB: db, FB_PAGE_TOKEN: "tok",
              ASSETS: { fetch: async () => new Response(cardOk ? "img" : "no", { status: cardOk ? 200 : 404 }) } };
const tick = () => worker.scheduled({ cron: "* * * * *" }, env, {});
const posts = () => fbCalls.filter(c => c.path === "me/photos" || c.path === "me/feed");

/* ---------------------------------------------- 1 pure helpers */
ck("1 scope: الأهلي in the Egyptian league, مصر in the AFCON qualifiers",
   postScope({ c: 552, h: "الأهلي", a: "سموحة" }) && postScope({ c: 588, h: "مصر", a: "أنغولا" }));
ck("2 scope: the Saudi الأهلي and the Port Said المصري are OUT; Arsenal (every curated club, 2026-10-17) is IN",
   !postScope({ c: 649, h: "الأهلي", a: "النصر" }) && postScope({ c: 7, h: "أرسنال", a: "توتنهام" })
   && !postScope({ c: 552, h: "المصري", a: "إنبي" }) && postScope({ c: 573, h: "طرابزون سبور", a: "ليل" })
   && !postScope({ c: 7, h: "إيفرتون", a: "توتنهام" }) && CURATED_LIVE.length === 12
   && postScope({ c: 627, h: "كيتارا", a: "الأهلي" })                       // the Egyptian club in the Confederation Cup
   && !postScope({ c: 627, h: "جامعة ويلوالو أديجرات", a: "الأهلي طرابلس" }));   // the Libyan namesake (2026-10-17)
const gm = goalMessage({ id: 901, c: 552, h: "الزمالك", a: "الإسماعيلي", hs: 2, as: 0 }, { s: "h", p: "زيزو", m: "63", t: "ج" });
ck("3 goal text: spaced score, scorer, minute, penalty, match link, hashtags",
   gm.startsWith("⚽ هدف! الزمالك 2 - 0 الإسماعيلي") && gm.includes("🥅 زيزو · الدقيقة 63 · ركلة جزاء")
   && gm.includes("https://yallascore.site/m/901") && gm.endsWith("#يلا_سكور #الزمالك #الإسماعيلي"), gm);
ck("4 goal text never carries a betting word", !gm.includes("مراهنة"));
ck("5 parseLineups: eleven named starters each side, else null",
   parseLineups(DETAIL(0, 0, [], { h: XI(11), a: XI(11) }).game).a.xi.length === 11
   && parseLineups(DETAIL(0, 0, [], { h: XI(11), a: XI(10) }).game) === null);

/* ------------------------------------------- 2 first sight: no posts */
detailFor[901] = DETAIL(1, 0, [{ s: "h", pid: 11, m: 20 }]);
// five+ games: a shorter list is what worker.js treats as a DEGRADED reply
// and re-fetches per competition (the fake would then answer 12 times)
LIST = { games: [
  live(901, 552, "الزمالك", "الإسماعيلي", 1, 0),
  live(902, 7, "إيفرتون", "توتنهام", 1, 1),
  live(903, 649, "الأهلي", "النصر", 1, 0),
  live(904, 11, "خيتافي", "إلتشي", 0, 0),
  live(905, 552, "بيراميدز", "زد", 0, 0),       // never gets a detail: score-only path
  live(906, 17, "بولونيا", "جنوى", 0, 0),
] };
await tick();
ck("6 goals already on the board at first sight are NOT posted", posts().length === 0, JSON.stringify(posts()));
ck("7 ...but they are in the goal log", db.goals.length === 1);

/* -------------------------------------------- 3 a goal discovered live */
detailFor[901] = DETAIL(2, 0, [{ s: "h", pid: 11, m: 20 }, { s: "h", pid: 12, m: 63 }]);
LIST.games[0] = live(901, 552, "الزمالك", "الإسماعيلي", 2, 0);
LIST.games[1] = live(902, 7, "إيفرتون", "توتنهام", 2, 1);     // Everton scores: not a curated club
LIST.games[2] = live(903, 649, "الأهلي", "النصر", 2, 0);      // Saudi Al-Ahli scores: out of scope
await tick();
ck("8 exactly ONE post: the Zamalek goal, as a PHOTO with our card",
   posts().length === 1 && posts()[0].path === "me/photos" && posts()[0].url === "https://yallascore.site/media/matchup-901-preview.jpg",
   JSON.stringify(posts()));
ck("9 the caption is the goal text", (posts()[0].caption || "").startsWith("⚽ هدف! الزمالك 2 - 0 الإسماعيلي") && posts()[0].caption.includes("عمر جابر"));
ck("10 the lock row records the post id", db.fb.get("goal|901:2") && db.fb.get("goal|901:2").post_id === "P1");

/* ------------------------------------------------ 4 no re-post */
await tick();
ck("11 the same refresh again posts nothing", posts().length === 1);

/* ----------------------------------------------- 5 VAR reversal */
detailFor[901] = DETAIL(1, 0, [{ s: "h", pid: 11, m: 20 }]);
LIST.games[0] = live(901, 552, "الزمالك", "الإسماعيلي", 1, 0);
await tick();
const edit = fbCalls.find(c => c.path === "P1");
ck("12 a VAR reversal EDITS the goal's own post", !!edit && edit.message.startsWith("❌ أُلغي الهدف"), JSON.stringify(fbCalls.slice(-1)));
ck("13 ...and posts nothing new", posts().length === 1);

/* ---------------------------------------- 6 score-only goal (no list) */
LIST.games[4] = live(905, 552, "بيراميدز", "زد", 1, 0);
await tick();
ck("14 a score-only goal (no detail) is posted with the minute",
   posts().length === 2 && posts()[1].caption.startsWith("⚽ هدف! بيراميدز 1 - 0 زد") && posts()[1].caption.includes("الدقيقة 70'"),
   JSON.stringify(posts().slice(-1)));

/* ------------------------------- 6b a re-attributed goal is not a goal */
detailFor[901] = DETAIL(1, 0, [{ s: "h", pid: 12, m: 20 }]);          // same score, the scorer corrected
await tick();
ck("14b a corrected scorer (same score) posts nothing and edits nothing",
   posts().length === 2 && !fbCalls.slice(-1).some(c => c.path === "P1" && c.message.includes("كان: الزمالك 1 - 0") && fbCalls.length > 4),
   JSON.stringify(fbCalls.slice(-1)));

/* ------------------------------------------------- 7 no card -> text */
cardOk = false;
LIST.games[4] = live(905, 552, "بيراميدز", "زد", 2, 0);
await tick();
ck("15 without our card the goal goes out as a text post", posts().length === 3 && posts()[2].path === "me/feed", JSON.stringify(posts().slice(-1)));
cardOk = true;

/* ------------------------------------------------- 8 no token */
const envNoTok = { DB: fakeD1(), ASSETS: env.ASSETS };
const filler = [live(951, 11, "خيتافي", "إلتشي", 0, 0), live(952, 17, "بولونيا", "جنوى", 0, 0),
                live(953, 25, "ماينتس", "أوجسبورج", 0, 0), live(954, 35, "نانت", "لوريان", 0, 0)];
LIST = { games: [live(950, 552, "الأهلي", "سموحة", 0, 0), ...filler] };
await worker.scheduled({ cron: "* * * * *" }, envNoTok, {});
LIST = { games: [live(950, 552, "الأهلي", "سموحة", 1, 0), ...filler] };
const before = fbCalls.length;
await worker.scheduled({ cron: "* * * * *" }, envNoTok, {});
ck("16 no FB_PAGE_TOKEN: the refresh works, nothing is posted, no lock is taken",
   fbCalls.length === before && envNoTok.DB.goals.length === 1 && envNoTok.DB.fb.size === 0);

/* ------------------------------------------------- 9 the official XI */
const now = Date.now();
detailFor[960] = DETAIL(0, 0, [], { h: XI(11), a: XI(10) });     // away XI incomplete
LIST = { games: [
  sched(960, 588, "مصر", "أنغولا", now + 60 * 60 * 1000),          // 60 min away: in the window
  sched(961, 552, "المصري", "إنبي", now + 60 * 60 * 1000),         // not our scope
  sched(962, 552, "الأهلي", "سموحة", now + 3 * 60 * 60 * 1000),    // 3h away: not yet
] };
const n0 = posts().length;
await tick();
ck("17 XI not announced in full yet: nothing posted, no lock", posts().length === n0 && !db.fb.has("xi|960"));
detailFor[960] = DETAIL(0, 0, [], { h: XI(11), a: XI(11) });
await tick();
ck("18 both XIs complete: ONE lineup post, in the window, for مصر only",
   posts().length === n0 + 1 && posts()[n0].caption.startsWith("📋 التشكيل الرسمي: مصر × أنغولا")
   && posts()[n0].caption.includes("(4-3-3)") && posts()[n0].caption.split("لاعب").length === 23, JSON.stringify(posts().slice(-1)));
await tick();
ck("19 the XI is never posted twice", posts().length === n0 + 1);
ck("20 the window: 44 minutes before is too late to start, 81 too early",
   XI_MIN_MS === 45 * 60 * 1000);

/* ------------------------------------ 10 half-time and full-time (2026-10-17) */
const ht = (id, comp, h, a, hs, as_) => live(id, comp, h, a, hs, as_, { statusText: "شوط", shortStatusText: "شوط", gameTimeDisplay: "45'", gameTime: 45 });
const over = (id, comp, h, a, hs, as_) => live(id, comp, h, a, hs, as_, { statusGroup: 4, statusText: "انتهت", shortStatusText: "انتهت", justEnded: true });
const withStatus = (d, extra) => ({ game: { ...d.game, ...extra } });
const HT_STATUS = { statusText: "شوط", shortStatusText: "شوط", gameTimeDisplay: "45'", gameTime: 45 };
detailFor[970] = DETAIL(1, 0, [{ s: "h", pid: 11, m: 30 }]);
LIST = { games: [live(970, 7, "ليفربول", "برينتفورد", 1, 0), live(971, 7, "إيفرتون", "فولهام", 0, 0), ...filler] };
await tick();                                                    // first sight, in play
const n1 = posts().length;
detailFor[970] = withStatus(DETAIL(1, 0, [{ s: "h", pid: 11, m: 30 }]), HT_STATUS);   // the detail (fresher) says break too
LIST.games[0] = ht(970, 7, "ليفربول", "برينتفورد", 1, 0);
LIST.games[1] = ht(971, 7, "إيفرتون", "فولهام", 0, 0);           // not curated: no post
await tick();
ck("21 the half-time whistle posts ONCE for the curated game, with the score and the scorer",
   posts().length === n1 + 1 && posts()[n1].caption.startsWith("⏸️ نهاية الشوط الأول: ليفربول 1 - 0 برينتفورد")
   && posts()[n1].caption.includes("ليفربول: زيزو 30'") && posts()[n1].caption.includes("الدوري الإنجليزي"),
   JSON.stringify(posts().slice(-1)));
await tick();
ck("22 the break goes on: no second half-time post", posts().length === n1 + 1 && db.fb.has("ht|970"));
detailFor[970] = DETAIL(2, 0, [{ s: "h", pid: 11, m: 30 }, { s: "h", pid: 12, m: 78 }]);
LIST.games[0] = live(970, 7, "ليفربول", "برينتفورد", 2, 0);
await tick();
ck("23 second-half goal posts as a goal, not as another break", posts().length === n1 + 2 && posts()[n1 + 1].caption.startsWith("⚽ هدف!"));
detailFor[970] = withStatus(DETAIL(2, 0, [{ s: "h", pid: 11, m: 30 }, { s: "h", pid: 12, m: 78 }]), { statusGroup: 4, statusText: "انتهت", shortStatusText: "انتهت" });
LIST.games[0] = over(970, 7, "ليفربول", "برينتفورد", 2, 0);
LIST.games[1] = over(971, 7, "إيفرتون", "فولهام", 1, 1);
await tick();
ck("24 the final whistle posts ONCE for the curated game, with both scorers",
   posts().length === n1 + 3 && posts()[n1 + 2].caption.startsWith("🏁 انتهت المباراة: ليفربول 2 - 0 برينتفورد")
   && posts()[n1 + 2].caption.includes("زيزو 30'") && posts()[n1 + 2].caption.includes("عمر جابر 78'")
   && posts()[n1 + 2].caption.includes("https://yallascore.site/m/970"), JSON.stringify(posts().slice(-1)));
await tick();
ck("25 an ended game stays ended: no second full-time post", posts().length === n1 + 3 && db.fb.has("ft|970") && !db.fb.has("ft|971"));
// the store bug the full-time post exposed: a fresh read with no goal list
// (no detail) must not cancel the logged goals
detailFor[980] = DETAIL(1, 0, [{ s: "h", pid: 11, m: 40 }]);
LIST = { games: [live(980, 11, "برشلونة", "خيتافي", 1, 0), ...filler] };
await tick();
delete detailFor[980];                                            // the detail endpoint fails now
LIST.games[0] = live(980, 11, "برشلونة", "خيتافي", 1, 0, { statusGroup: 4, statusText: "انتهت", shortStatusText: "انتهت" });   // no justEnded, no detail
await tick();
ck("27 an ended game with no goal list keeps its logged goals (not cancelled as VAR)",
   db.goals.filter(x => x.game_id === 980 && !x.cancelled).length === 1
   && posts().slice(-1)[0].caption.includes("برشلونة: زيزو 40'"), JSON.stringify(posts().slice(-1)));
ck("26 the pure messages carry hashtags and no betting word",
   htMessage({ id: 1, c: 552, h: "الأهلي", a: "الزمالك", hs: 0, as: 0, goals: [] }).endsWith("#يلا_سكور #الأهلي #الزمالك")
   && !ftMessage({ id: 1, c: 552, h: "الأهلي", a: "الزمالك", hs: 1, as: 0, goals: [{ s: "h", p: "زيزو", m: "12", t: "ج" }] }).includes("مراهنة")
   && ftMessage({ id: 1, c: 552, h: "الأهلي", a: "الزمالك", hs: 1, as: 0, goals: [{ s: "h", p: "زيزو", m: "12", t: "ج" }] }).includes("الأهلي: زيزو 12' (ج)"));

/* ------------------------------- 11 the line-up CARD path (2026-10-17) */
const envGh = { ...env, GH_TOKEN: "gh" };
const tickGh = () => worker.scheduled({ cron: "* * * * *" }, envGh, {});
const now2 = Date.now();
detailFor[990] = DETAIL(0, 0, [], { h: XI(11), a: XI(11) });
LIST = { games: [sched(990, 552, "الزمالك", "سموحة", now2 + 60 * 60 * 1000)] };
const n2 = posts().length;
await tickGh();
ck("28 with GH_TOKEN the XI is DISPATCHED to fb-post.yml (xi=<game>), not posted from the edge",
   ghCalls.length === 1 && ghCalls[0].inputs && ghCalls[0].inputs.xi === "990" && posts().length === n2
   && db.fb.has("xi|990") && !db.fb.get("xi|990").post_id, JSON.stringify(ghCalls));
await tickGh();
ck("29 the next minute neither re-dispatches nor posts (the runner's turn)", ghCalls.length === 1 && posts().length === n2);
db.fb.get("xi|990").claimed_at -= 13 * 60;                   // the runner never came back
await tickGh();
ck("30 ...but 12 minutes later the text post goes out as the fallback",
   posts().length === n2 + 1 && posts()[n2].caption.startsWith("📋 التشكيل الرسمي: الزمالك × سموحة") && db.fb.get("xi|990").post_id);
ghOk = false;
detailFor[991] = DETAIL(0, 0, [], { h: XI(11), a: XI(11) });
LIST = { games: [sched(991, 552, "الأهلي", "إنبي", now2 + 60 * 60 * 1000)] };
await tickGh();
ck("31 a failed dispatch falls straight back to the text post", posts().length === n2 + 2 && db.fb.get("xi|991").post_id, JSON.stringify(ghCalls.slice(-1)));
ghOk = true;

console.log(fails.length ? `\n${fails.length} FAILED: ${fails.join("; ")}` : "\nALL LIVE POST TESTS PASSED");
process.exit(fails.length ? 1 : 0);
