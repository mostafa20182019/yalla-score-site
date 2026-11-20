// The live minute in EXTRA TIME (2026-11-20).
//
//     node tests/test_live_period.mjs      (from the repo root)
//
// كهرباء الإسماعيلية 2-2 سيراميكا كليوباترا (Egypt Cup) went to extra time and
// the home list showed «45+» through all of it: the Worker called every
// period that was not the feed's "2" a first half, and the page's minute
// clock caps a first half at 45. worker.period() now names four periods and
// the page caps each at its own end: 45+ / 90+ / 105+ / 120+.
import fs from "node:fs";

let fails = 0;
const ck = (msg, cond, extra = "") => {
  console.log((cond ? "  ok   " : "  FAIL ") + msg + (extra && !cond ? `  [${extra}]` : ""));
  if (!cond) fails += 1;
};

const { period, liveFields } = await import(new URL("../worker.js", import.meta.url).href);
const g = (ss, gt, stx = "") => ({ shortStatusText: ss, gameTime: gt, statusText: stx, gameTimeDisplay: `${gt}'` });

console.log("1. the Worker: which period");
ck("the two halves as the feed names them", period(g("1", 30, "الشوط الأول")) === 1 && period(g("2", 70, "الشوط الثاني")) === 2);
ck("stoppage time stays in its own half: 45+3 is the first, 90+5 the second",
   period(g("1", 48, "الشوط الأول")) === 1 && period(g("2", 95, "الشوط الثاني")) === 2);
ck("extra time named by the feed: first period 3, second period 4",
   period(g("ET", 97, "الشوط الإضافي الأول")) === 3 && period(g("ET", 112, "الشوط الإضافي الثاني")) === 4);
ck("extra time the feed does not name: read off the minute - past 90 is 3, past 105 is 4",
   period(g("", 97)) === 3 && period(g("و.إ", 104)) === 3 && period(g("", 108)) === 4 && period(g("x", 119)) === 4);
ck("the feed restarting at \"1\" / \"2\" for the two periods of extra time is still extra time",
   period(g("1", 96)) === 3 && period(g("2", 110)) === 4);
ck("NEVER a first half past minute 90 - the bug", [91, 97, 104, 106, 112, 120].every(m => period(g("", m)) >= 3));
ck("a status the feed leaves empty in normal time: the minute decides the half", period(g("", 20)) === 1 && period(g("", 60)) === 2);
const lf = liveFields(g("", 100));
ck("liveFields carries it to the page (hf) with the numeric minute", lf.hf === 3 && lf.gt === 100 && lf.min === "100'");
ck("the break is still the break", liveFields({ statusText: "شوط", shortStatusText: "شوط", gameTime: 45, gameTimeDisplay: "45'" }).min === "استراحة");

console.log("2. the page's minute clock");
const js = fs.readFileSync(new URL("../site_src/snippets/live_js.html", import.meta.url), "utf8");
const m = js.match(/var CAP=\{[^}]*\};\s*function calcMin\(g,at\)\{[\s\S]*?\n  \}/);
ck("calcMin is found in live_js.html", !!m);
if (m) {
  const calc = new Function(`var STALE=150000; ${m[0]}; return calcMin;`)();
  const at = Date.now();                       // no time has passed: the minute is the feed's
  const show = (hf, gt) => { const x = { live: true, min: "", gt, hf }; calc(x, at); return x.min; };
  ck("in play: the minute itself", show(1, 30) === "30'" && show(2, 70) === "70'" && show(3, 97) === "97'" && show(4, 112) === "112'");
  ck("past the end of a period: that period's own cap",
     show(1, 47) === "45+" && show(2, 93) === "90+" && show(3, 107) === "105+" && show(4, 122) === "120+");
  ck("extra time never shows «45+» again", ![91, 97, 104, 108, 119].some(mm => show(mm > 105 ? 4 : 3, mm) === "45+"));
  ck("an old cached reply with no period: the cap is read off the minute, not assumed to be 45",
     show(0, 97) === "97'" && show(0, 30) === "30'" && show(undefined, 112) === "112'");
  const br = { live: true, min: "استراحة", gt: 0, hf: 1 }; calc(br, at);
  ck("the break label is left alone", br.min === "استراحة");
}

console.log(fails ? `\n${fails} FAILED` : "\nALL OK");
process.exit(fails ? 1 : 0);
