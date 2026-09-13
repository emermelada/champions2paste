/* Checks the screenshot drop-zone logic: pasting from the clipboard (the paste
 * event and the async Clipboard API used by the Paste button) and swapping
 * between slots. The functions are extracted straight out of index.html so the
 * test cannot drift away from the interface.
 *
 *   node tests/test_clipboard.js
 */
const fs = require("fs");
const path = require("path");

const html = fs.readFileSync(
  path.join(__dirname, "..", "app", "static", "index.html"), "utf8");

function grab(name) {
  let start = html.indexOf(`function ${name}(`);
  if (start === -1) throw new Error(`cannot find ${name}() in index.html`);
  // Keep the keyword: without it, an async function would not parse.
  if (html.slice(start - 6, start) === "async ") start -= 6;
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
const flashed = [];
const makeZone = () => {
  const input = { value: "x" };
  return { querySelector: () => input, classList: { toggle() {} }, input };
};
const zones = [makeZone(), makeZone()];
const render = (i) => rendered.push(i);
const setFile = (i, file) => { files[i] = file; return true; };
const flash = (i) => flashed.push(i);
let status = "";
const setStatus = (m) => { status = m; };

eval(grab("imagesFromClipboard"));
eval(grab("targetSlot"));
eval(grab("swapSlots"));
eval(grab("placeImages"));
eval(grab("imagesFromClipboardItems"));

let checks = 0, failures = 0;
const ok = (cond, msg) => {
  checks++;
  if (!cond) { console.log("  FAIL", msg); failures++; }
};
const png = (name = "a.png", size = 100) => ({ type: "image/png", size, name });
const item = (f) => ({ kind: "file", type: f.type, getAsFile: () => f });
// What navigator.clipboard.read() hands back in Safari: a ClipboardItem per entry.
const clipItem = (blobs) => ({
  types: Object.keys(blobs),
  getType: async (type) => blobs[type],
});

async function main() {
  /* --- clipboard: paste event --- */
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

  /* --- clipboard: Paste button (async Clipboard API) --- */
  r = await imagesFromClipboardItems([
    clipItem({ "text/plain": new Blob(["hi"]), "image/png": new Blob(["png"], { type: "image/png" }) }),
  ]);
  ok(r.length === 1 && r[0].type === "image/png", "image picked out of a mixed ClipboardItem");
  ok(r[0] instanceof File && r[0].name === "pasted.png", "the blob becomes a named File");

  r = await imagesFromClipboardItems([clipItem({ "text/plain": new Blob(["hi"]) })]);
  ok(r.length === 0, `clipboard with only text -> ${r.length}, should be 0`);

  r = await imagesFromClipboardItems([]);
  ok(r.length === 0, "empty clipboard");

  r = await imagesFromClipboardItems([
    clipItem({ "image/png": new Blob(["a"], { type: "image/png" }) }),
    clipItem({ "image/jpeg": new Blob(["b"], { type: "image/jpeg" }) }),
  ]);
  ok(r.length === 2 && r[1].name === "pasted.jpeg", "two ClipboardItems -> two files");

  /* --- placing pasted images --- */
  files = [null, null]; flashed.length = 0; status = "";
  placeImages([png("x.png")]);
  ok(files[0] && files[0].name === "x.png" && flashed.join() === "0", "one image lands in slot 1");
  ok(status.includes("slot 1"), "the user is told which slot was filled");

  files = [png("old.png"), null];
  placeImages([png("y.png"), png("z.png", 300)]);
  ok(files[1].name === "y.png" && files[0].name === "z.png",
     "two images fill the free slot, then replace the first");

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

  console.log(failures ? `\n${failures} of ${checks} checks FAILED` : `\n${checks} checks passed`);
  process.exit(failures ? 1 : 0);
}

main();
