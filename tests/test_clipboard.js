/* Comprueba la logica de la zona de capturas: pegado desde el portapapeles e
 * intercambio entre huecos. Las funciones se extraen de index.html para que la
 * prueba no se desincronice de la interfaz.
 *
 *   node tests/test_clipboard.js
 */
const fs = require("fs");
const path = require("path");

const html = fs.readFileSync(
  path.join(__dirname, "..", "app", "static", "index.html"), "utf8");

function grab(name) {
  const start = html.indexOf(`function ${name}(`);
  if (start === -1) throw new Error(`no encuentro ${name}() en index.html`);
  let depth = 0;
  for (let i = html.indexOf("{", start); i < html.length; i++) {
    if (html[i] === "{") depth++;
    if (html[i] === "}" && --depth === 0) return html.slice(start, i + 1);
  }
  throw new Error(`${name}() sin cerrar`);
}

// Sustitutos minimos del DOM: solo lo que tocan las funciones bajo prueba.
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
const ok = (cond, msg) => { if (!cond) { console.log("  FALLA", msg); failures++; } };
const png = (name = "a.png", size = 100) => ({ type: "image/png", size, name });
const item = (f) => ({ kind: "file", type: f.type, getAsFile: () => f });

/* --- portapapeles --- */
let r = imagesFromClipboard({ items: [item(png())], files: [] });
ok(r.length === 1, `una captura normal -> ${r.length}`);

const same = png();
r = imagesFromClipboard({ items: [item(same)], files: [same] });
ok(r.length === 1, `la misma imagen por items y por files -> ${r.length}, deberia ser 1`);

r = imagesFromClipboard({ items: [{ kind: "string", type: "text/plain" }], files: [] });
ok(r.length === 0, `pegar texto -> ${r.length}, deberia ser 0`);

ok(imagesFromClipboard(null).length === 0, "clipboardData nulo");
ok(imagesFromClipboard({}).length === 0, "clipboardData sin items ni files");

r = imagesFromClipboard({ items: [item(png("a.png")), item(png("b.png", 200))], files: [] });
ok(r.length === 2, `dos imagenes distintas -> ${r.length}`);

/* --- asignacion de huecos --- */
files = [null, null]; ok(targetSlot() === 0, "ambos vacios -> hueco 0");
files = [png(), null]; ok(targetSlot() === 1, "primero lleno -> hueco 1");
files = [null, png()]; ok(targetSlot() === 0, "segundo lleno -> hueco 0");
files = [png(), png()]; ok(targetSlot() === 0, "ambos llenos -> sustituye el 0");

/* --- intercambio --- */
const a = png("stats.png"), b = png("moves.png", 200);
files = [a, b]; rendered.length = 0; status = "";
swapSlots(0, 1);
ok(files[0] === b && files[1] === a, "intercambio de dos huecos llenos");
ok(rendered.includes(0) && rendered.includes(1), "se repintan los dos huecos");
ok(zones.every(z => z.input.value === ""), "se vacian los inputs tras intercambiar");
ok(status.includes("intercambiadas"), "avisa al usuario del intercambio");

files = [a, null]; rendered.length = 0;
swapSlots(0, 1);
ok(files[0] === null && files[1] === a, "mover a un hueco vacio deja el origen libre");

files = [a, b]; rendered.length = 0;
swapSlots(1, 1);
ok(files[0] === a && files[1] === b && rendered.length === 0,
   "soltar sobre el mismo hueco no hace nada");

console.log(failures ? `\n${failures} FALLOS` : "\n16 comprobaciones OK");
process.exit(failures ? 1 : 0);
