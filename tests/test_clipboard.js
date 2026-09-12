/* Checks the screenshot drop-zone logic: pasting from the clipboard and
 * swapping between slots. The functions are extracted straight out of
 * index.html so the test cannot drift away from the interface.
 *
 *   node tests/test_clipboard.js
 */
const fs = require("fs");
const path = require("path");

const html = fs.readFileSync(
  path.join(__dirname, "..", "app", "static", "index.html"), "utf8");

function grab(name) {
  const start = html.indexOf(`function ${name}(`);
  if (start === -1) throw new Error(`cannot find ${name}() in index.html`);
  let depth = 0;
  for (let i = html.indexOf("{", start); i < html.length; i++) {
    if (html[i] === "{") depth++;
    if (html[i] === "}" && --depth === 0) return html.slice(start, i + 1);
  }
  throw new Error(`${name}() is never closed`);
}

// Minimal DOM stand-ins: only what the functions under test actually touch.
let files = [null, null];
const rendered = [];
const makeZone = () => {
  const input = { value: "x" };
  return { querySelector: () => input, classList: { toggle() {} }, input };
};
const zones = [makeZone(), makeZone()];
const render = (i) => rendered.push(i);
let status = "";
const setStatus = (m) => { status = m; };

eval(grab("imagesFromClipboard"));
eval(grab("targetSlot"));
eval(grab("swapSlots"));

let failures = 0;
const ok = (cond, msg) => { if (!cond) { console.log("  FAIL", msg); failures++; } };
const png = (name = "a.png", size = 100) => ({ type: "image/png", size, name });
const item = (f) => ({ kind: "file", type: f.type, getAsFile: () => f });

/* --- clipboard --- */
let r = imagesFromClipboard({ items: [item(png())], files: [] });
ok(r.length === 1, `one ordinary screenshot -> ${r.length}`);

const same = png();
r = imagesFromClipboard({ items: [item(same)], files: [same] });
ok(r.length === 1, `same image via items and files -> ${r.length}, should be 1`);

r = imagesFromClipboard({ items: [{ kind: "string", type: "text/plain" }], files: [] });
ok(r.length === 0, `pasting text -> ${r.length}, should be 0`);

ok(imagesFromClipboard(null).length === 0, "null clipboardData");
ok(imagesFromClipboard({}).length === 0, "clipboardData with neither items nor files");

r = imagesFromClipboard({ items: [item(png("a.png")), item(png("b.png", 200))], files: [] });
ok(r.length === 2, `two different images -> ${r.length}`);

/* --- slot assignment --- */
files = [null, null]; ok(targetSlot() === 0, "both empty -> slot 0");
files = [png(), null]; ok(targetSlot() === 1, "first filled -> slot 1");
files = [null, png()]; ok(targetSlot() === 0, "second filled -> slot 0");
files = [png(), png()]; ok(targetSlot() === 0, "both filled -> replaces slot 0");

/* --- swapping --- */
const a = png("stats.png"), b = png("moves.png", 200);
files = [a, b]; rendered.length = 0; status = "";
swapSlots(0, 1);
ok(files[0] === b && files[1] === a, "swapping two filled slots");
ok(rendered.includes(0) && rendered.includes(1), "both slots are repainted");
ok(zones.every(z => z.input.value === ""), "inputs are cleared after a swap");
ok(status.toLowerCase().includes("swapped"), "the user is told about the swap");

files = [a, null]; rendered.length = 0;
swapSlots(0, 1);
ok(files[0] === null && files[1] === a, "moving into an empty slot leaves the source free");

files = [a, b]; rendered.length = 0;
swapSlots(1, 1);
ok(files[0] === a && files[1] === b && rendered.length === 0,
   "dropping onto the same slot does nothing");

console.log(failures ? `\n${failures} FAILURES` : "\n16 checks passed");
process.exit(failures ? 1 : 0);
