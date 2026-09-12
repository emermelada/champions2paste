# champions2paste

Turns **Pokémon Champions** team screenshots into a valid **Pokémon Showdown**
pokepaste.

Upload one or two screenshots of the *"Replicate This Battle Team?"* screen, they
are read by OCR, every name is anchored against Showdown's real vocabulary, and
out comes text ready to paste into the Teambuilder.

It runs entirely on modest hardware: **no GPU, no internet, no cost**. There is
no language model anywhere in the pipeline.

```
Salamence (F) @ Salamencite          Kingambit (M) @ Chople Berry
Ability: Intimidate                  Ability: Defiant
Level: 50                            Level: 50
EVs: 9 HP / 25 SpA / 32 Spe          EVs: 32 HP / 19 Atk / 2 Def / 4 SpD / 9 Spe
Timid Nature                         Adamant Nature
- Draco Meteor                       - Kowtow Cleave
- Hyper Voice                        - Iron Head
- Tailwind                           - Sucker Punch
- Protect                            - Low Kick
```

---

## Using it

Screenshots go in three ways: **drag them**, **click** to pick a file, or
**paste with Ctrl+V** from the clipboard. Each slot has an × to empty it, and you
can drag an image from one slot to the other.

Two in-game tabs matter:

- **Moves & More** — species, genders, abilities, held items and moves.
- **Stats** — points invested (SP) and nature.

**Order does not matter and neither tab is required.** Each screenshot is
identified by the tab it has highlighted in green, not by the slot you drop it
into:

| You upload | You get |
|---|---|
| Both | The complete paste |
| Only *Moves & More* | The team without spreads |
| Only *Stats* | Species, SP and natures, but no moves |

After converting, an editor appears with everything that was read. Fields the
vocabulary had to correct show up in **amber** and unrecognised ones in **red**,
with the warning spelled out underneath. Fixing something by hand does not call
the OCR engine again.

---

## Why the input is screenshots and not the game's code

The replica code Champions gives you (`P302HFTLGP`) **does not contain the
team**: it is an identifier resolved against the game's servers.

Ten alphanumeric characters are about 51 bits of information. Six Pokémon with
items, abilities, natures, four moves each and spreads need several hundred. The
information simply is not in there, so no local tool can decode it — however good
it is. Hence starting from screenshots.

---

## The Champions stat system

Champions does not use classic EVs or IVs, and this tool works on its scale:

- Each stat takes **0 to 32 SP**, and every Pokémon's total is **always 66**.
- **There are no IVs**: they are equivalent to 31. That is why the paste emits no
  `IVs:` line, which is exactly what Showdown assumes when one is absent.
- **The nature is never written anywhere**: it is derived from the pink arrows
  pointing up (boosted) and the blue ones pointing down (hindered).
- Battles are at **level 50**.

The paste carries **raw SP**, which is what Champions formats on Showdown expect.
The *Classic EVs (×8)* toggle converts them to the old scale (1 SP = 8 EVs,
capped at 252) for calculators that still use it; in that mode it warns that the
spread exceeds 508 EVs, because 66 SP is equivalent to 528.

### Mega evolution

Champions allows mega evolution. The tool treats mega stones like any other item
and keeps the **base form's ability** (`Intimidate`, not `Aerilate`), which is
what Showdown expects.

---

## How it works

There is no language model and no prompt: the result is deterministic and cannot
invent a value. The game screen is always drawn the same way, so each piece of
data is looked for where it actually is.

1. **The six cards are located by colour** (purple on a yellow background) and
   ordered the way the game numbers them. The active tab is detected by its green
   highlight, which is why upload order does not matter.

2. **Text** (species, ability, item, moves) is read in two passes: one detection
   over the whole image narrows down where each piece of text sits, then the
   recogniser reads those tight crops in a single batch. Neither half works
   alone: the detector splits two-word names, and the recogniser degrades when
   the crop carries a lot of empty background.

3. **Numbers self-calibrate against the bar** on each stat row, which is isolated
   by colour. The large number sits to its left and the small one to its right,
   always the same distance away measured in bar widths. This avoids depending on
   fixed positions: a couple of pixels of difference when detecting a card was
   enough to cut off the last digit.

4. **Gender and nature use no OCR at all**: they are pixel counts. The gender
   symbol by its colour, and the arrows in the band holding each stat's name.

### Four signals that correct each other

OCR makes mistakes. What makes the result trustworthy is that every value is
checked against something independent:

- **Showdown's closed vocabulary** fixes the text. The real dictionary (1416
  species, 951 moves, 583 items, 321 abilities) is baked into the image from
  `play.pokemonshowdown.com`, and every string read is anchored to the nearest
  canonical name with a threshold that scales with word length: `'Grsy Surge'` →
  `Grassy Surge`, `'Chople Bery'` → `Chople Berry`.

- **Bar length** cross-checks every SP number. Its mean error is 0.06 points and
  it never exceeds 2, so when the number that was read strays further than that,
  OCR has dropped a digit (a `17` read as `7`) and the bar wins.

- **The 66 SP checksum** gives away any number still wrong after that.

- **Recomputing the stats** closes the loop: given base stats, SP, nature, level
  50 and IVs of 31, the final value is deterministic. If it does not match the
  large number on screen, something was misread.

Nothing is corrected behind the user's back: every correction surfaces as a
warning.

### Measured accuracy

Against the two real screenshots in the fixture, comparing all 96 fields
(species, gender, ability, item, 4 moves, 6 SP and the 2 arrows per Pokémon):

```
96/96 fields correct (100.0%)
```

In roughly 3 seconds end to end on a desktop CPU.

The scale conversion is verified separately: the **36 stat values** shown across
the six cards are reproduced exactly by the game's formula (1 SP = 8 EVs, IVs 31,
level 50, nature multiplier).

---

## Deployment

```bash
docker compose up -d --build
```

The web UI lands on `http://<host>:8321`. Nothing to configure: the `ocr` engine
is the default and runs inside the container.

Notes verified by building and running the image:

- **The build needs internet exactly once**: `scripts/build_dex.py` downloads
  Showdown's canonical names and bakes them into the image. After that the
  container works offline.
- **The image weighs ~740 MB** (onnxruntime, opencv, numpy). That is disk, not
  memory.
- **Every dependency has a `manylinux aarch64` wheel**, so on an ARM NAS they
  install without compiling. The ONNX models (13 MB) ship inside the Python
  package: nothing is downloaded at startup.
- **With `docker-compose` v1** (the old hyphenated binary), rebuilding over an
  existing container fails with `ERROR: 'ContainerConfig'`. That is a known bug in
  that version against modern Docker: run `docker-compose down` first.

### On a Synology (GUI, no SSH)

1. **File Station** → upload the project to the `docker` shared folder and
   extract it.
2. **Container Manager** → *Project* → *Create*, pointing at that folder. It
   picks up `docker-compose.yml` on its own.
3. Leave *"Set up web portal via Web Station"* **unchecked**: it gets in the way
   if you are going to publish through a reverse proxy or a tunnel.

On an ARM CPU the build can take 10-20 minutes. Nothing is compiled, but
unpacking the wheels on that hardware is slow.

### Publishing it on your own domain

With **Cloudflare Tunnel** there are no ports to open and no home IP to expose,
and Cloudflare provides the certificate. One tunnel serves as many hostnames as
you like, so if you already have one, just add a route to it:

| Field | Value |
|---|---|
| Subdomain | `champions2paste` |
| Type | `HTTP` |
| URL | `localhost:8321` *(if cloudflared uses `network_mode: host`)* |

The frontend only uses relative paths, so it works behind a proxy untouched.

Two warnings: if the domain is a **`.dev`**, browsers force HTTPS through
preloaded HSTS and there is no way to serve it over plain HTTP. And Cloudflare's
free plan **cuts requests off at 100 seconds** (error 524), which matters if OCR
on your hardware gets close to that.

---

## Local development

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/build_dex.py          # caches data/dex.json
.venv/bin/uvicorn app.main:app --reload --port 8321
```

## Tests

```bash
.venv/bin/python tests/test_pipeline.py    # normalisation and rendering
.venv/bin/python tests/test_ocr.py         # OCR accuracy, field by field
node tests/test_clipboard.js               # pasting and slot swapping
```

`test_ocr.py` is the one that matters when touching the engine: it compares all
96 fields against the fixture's real transcription, so any regression shows up
there. `test_clipboard.js` extracts its functions straight out of `index.html` so
it cannot drift away from the interface.

## Layout

```
app/
  main.py          HTTP API (FastAPI)
  dex.py           Showdown's vocabulary and typo-tolerant anchoring
  champions.py     the game's stat model and its conversion to Showdown
  paste.py         normalisation, warnings and pokepaste rendering
  schema.py        the shape of the data a vision engine returns
  vision/
    ocr.py         default engine: geometry + OCR + colour
    ollama.py      alternative using a local model (unverified)
    claude.py      alternative using the Anthropic API (unverified)
  static/index.html  the whole interface, no external dependencies
scripts/build_dex.py  downloads and caches the canonical names
tests/fixtures/       real screenshots and their transcription
```

## API

| Endpoint | What it does |
|---|---|
| `POST /api/extract` | 1-2 images (multipart) → team read, normalised, and paste |
| `POST /api/render` | Edited team (JSON) → re-normalise and re-render |
| `GET /api/vocab` | Canonical names, for the editor's autocomplete |
| `GET /api/health` | Status and active engine |

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `VISION_BACKEND` | `ocr` | `ocr`, `ollama` or `claude` |
| `MAX_IMAGE_BYTES` | `8388608` | Maximum size per screenshot |
| `OLLAMA_HOST` | `http://localhost:11434` | Only with `ollama` |
| `OLLAMA_MODEL` | `qwen3-vl:8b` | Only with `ollama` |
| `ANTHROPIC_API_KEY` | — | Only with `claude` |
| `ANTHROPIC_MODEL` | `claude-opus-5` | Only with `claude` |

`rapidocr-onnxruntime` is **pinned to 1.2.3**. Not out of purism: 1.4
reorganised its internal API and stopped exposing `text_detector` /
`text_recognizer`, the two pieces this engine drives separately to narrow down
first and read afterwards. If a version without them ever gets installed, the
engine says so with a clear message instead of failing somewhere deep inside.

---

## Known limitations

**Accuracy is measured on a single team.** Six Pokémon, 96 fields, one resolution
(1998×922). The geometry is expressed as fractions of the detected card and the
numbers self-calibrate against the bar, so it should hold at other resolutions —
but that **is not verified**.

**The `ollama` and `claude` engines have never been run.** They share a prompt
calibrated against the game's real layout, but there was neither a GPU nor
credentials available to test them. The `ocr` engine, which is the default, is
verified end to end.

**Tera type is not read**, because it does not appear on either of the two
captured tabs. The field exists in the schema and in the editor in case the game
shows it somewhere I have not seen yet.
