// LIVE_JS paints a row only from the feed game of the SAME day (2026-11-06).
//
//   node tests/test_live_day_match.mjs
//
// What happened: /live.json keeps recent results for days. On 2026-11-06 it
// still carried the Capital Cup's «ابو قير للاسمدة 0-2 سيراميكا كليوباترا» of
// 11-03, and LIVE_JS - which matched rows by the two names only, in both
// orders - painted «انتهت 2-0» over the clubs' Egypt Cup tie of 11-07, a
// match that had not been played. Rows now carry data-d (the kick-off day,
// Cairo) and feed games carry d; a row is painted only when the two agree.
// Either side without a day keeps the old name-only match (an older reply
// during a deploy, the day strip's cards).
//
// The script runs here against a tiny fake page: just the DOM calls LIVE_JS
// makes on a day-list row.
import { readFileSync } from "node:fs";

let fails = [];
const ck = (name, cond, extra = "") => {
  console.log((cond ? "  ok   " : "  FAIL ") + name + (extra ? `  [${extra}]` : ""));
  if (!cond) fails.push(name);
};

function el(attrs, cls) {
  const a = { ...attrs };
  const classes = new Set(cls);
  const mid = { innerHTML: '<span class="ko">17:00</span>', querySelector: () => null };
  const node = {
    a, mid, pill: null, extra: "",
    getAttribute: (k) => (k in a ? a[k] : null),
    setAttribute: (k, v) => { a[k] = String(v); },
    classList: {
      add: (c) => classes.add(c), remove: (...c) => c.forEach(x => classes.delete(x)),
      contains: (c) => classes.has(c), toggle: (c, on) => (on ? classes.add(c) : classes.delete(c)),
    },
    classes,
    querySelector: (s) => (s === ".mid" ? mid : s === ".pill" ? node.pill : s === ".mgoals" ? node.mg : null),
    mg: null,
    insertAdjacentHTML: (_, html) => { node.extra += html; },
    closest: () => null,
  };
  return node;
}
const row = (h, a, d) => el({ "data-lv": "", "data-h": h, "data-a": a, ...(d === undefined ? {} : { "data-d": d }) },
                          ["mrow", "mrow-up"]);

function run(rows, games) {
  globalThis.document = {
    querySelectorAll: (s) => (s === "[data-lv]" ? rows : []),
    querySelector: () => null,
    getElementById: () => null,
    addEventListener: () => {},
    visibilityState: "visible",
  };
  globalThis.window = globalThis;
  window.__livePromise = Promise.resolve({ json: async () => ({ ok: true, ts: Date.now(), games }) });
  window.__koTs = [];
  globalThis.addEventListener = () => {};
  globalThis.setInterval = () => 0;
  const timers = [];
  globalThis.setTimeout = (f) => { timers.push(f); return 0; };
  globalThis.clearTimeout = () => {};
  const html = readFileSync(new URL("../site_src/snippets/live_js.html", import.meta.url), "utf8");
  const js = html.replace(/^\s*<script>/, "").replace(/<\/script>\s*$/, "");
  new Function(js)();
  return new Promise((r) => setImmediate(r));
}
const painted = (r) => r.mid.innerHTML.includes('class="score"');

// the case from the screenshot: the 11-03 result, two rows of the same pair
const capital = { id: 4883433, h: "ابو قير للاسمدة", a: "سيراميكا كليوباترا", hs: 0, as: 2, live: false,
                  min: "", gt: 0, hf: 0, c: 7808, d: "2026-11-03" };
let past = row("ابو قير للاسمدة", "سيراميكا كليوباترا", "2026-11-03");
let next = row("سيراميكا كليوباترا", "ابو قير للاسمدة", "2026-11-07");
await run([past, next], [capital]);
ck("1 the 11-03 row gets its own result", painted(past) && past.mid.innerHTML.includes("0 - 2"), past.mid.innerHTML);
ck("2 the 11-07 fixture of the same pair is NOT painted (still «17:00», still upcoming)",
   !painted(next) && next.classes.has("mrow-up") && !next.extra.includes("انتهت"), next.mid.innerHTML + next.extra);

// a reversed pair on the same day still matches (the sources disagree on who is at home)
const sameDay = row("سيراميكا كليوباترا", "ابو قير للاسمدة", "2026-11-03");
await run([sameDay], [capital]);
ck("3 the reversed name order on the SAME day is still painted, with the score swapped",
   painted(sameDay) && sameDay.mid.innerHTML.includes("2 - 0"), sameDay.mid.innerHTML);

// a reply without days (an older worker during a deploy) keeps the name-only match
const noDay = { ...capital }; delete noDay.d;
const r4 = row("ابو قير للاسمدة", "سيراميكا كليوباترا", "2026-11-07");
await run([r4], [noDay]);
ck("4 a feed game without a day falls back to the old name-only match", painted(r4));

// a row without a day (cards that do not carry data-d) keeps the old match too
const r5 = row("ابو قير للاسمدة", "سيراميكا كليوباترا");
await run([r5], [capital]);
ck("5 a row without data-d falls back to the old name-only match", painted(r5));

// the assister survives the live repaint, even through swap() (2026-11-06)
const withA = { ...capital, goals: [{ s: "a", p: "هداف", m: "30", t: "", a: "صانع" }, { s: "a", p: "هداف", m: "70", t: "" }] };
const r6 = row("سيراميكا كليوباترا", "ابو قير للاسمدة", "2026-11-03");
r6.closest = (s) => (s === ".mp-hero" ? {} : null);      // the match page's own row
await run([r6], [withA]);
const r6b = row("سيراميكا كليوباترا", "ابو قير للاسمدة", "2026-11-03");   // a list row
await run([r6b], [withA]);
ck("6b a list row repainted live gets the scorers but no assister (match page only)",
   r6b.extra.includes("هداف") && !r6b.extra.includes("mg-as"), r6b.extra);
ck("6 the live repaint writes «صناعة: X» under the scorer, through the reversed-name swap",
   r6.extra.includes('<span class="mg-as"><svg') && r6.extra.includes('<span class="sr-only">صناعة: </span><bdi>صانع</bdi></span>') && (r6.extra.match(/mg-as/g) || []).length === 1, r6.extra);

// a built list that no longer adds up to the painted score is removed (2026-11-07)
const listed = (nh, na) => {
  const r = row("سيراميكا كليوباترا", "ابو قير للاسمدة", "2026-11-07");
  const side = (n) => ({ querySelectorAll: (s) => (s === ".mg" ? Array(n).fill({}) : []) });
  r.mg = { removed: false, querySelectorAll: (s) => (s === ".mg-side" ? [side(nh), side(na)] : []),
           parentNode: { removeChild: () => { r.mg.removed = true; } } };
  return r;
};
const cer = { id: 4885271, h: "سيراميكا كليوباترا", a: "ابو قير للاسمدة", hs: 3, as: 2, live: false,
              min: "", gt: 0, hf: 0, c: 553, d: "2026-11-07" };
const r7 = listed(2, 2);
await run([r7], [cer]);
ck("7 «3 - 2» over a 2-2 list, and the reply has no list: the old list goes", r7.mg.removed === true);
const r8 = listed(3, 2);
await run([r8], [cer]);
ck("8 a list that adds up to the score stays", r8.mg.removed === false);

console.log(fails.length ? `\n${fails.length} FAILED: ${fails.join("; ")}` : "\nALL LIVE DAY-MATCH TESTS PASSED");
process.exit(fails.length ? 1 : 0);
