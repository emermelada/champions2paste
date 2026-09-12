"""Compara la lectura del motor OCR contra la transcripcion real del fixture.

Necesita rapidocr-onnxruntime instalado; se omite si no esta.
`python tests/test_ocr.py`
"""

from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def main() -> int:
    try:
        import rapidocr_onnxruntime  # noqa: F401
    except ImportError:
        print("rapidocr-onnxruntime no instalado: prueba omitida")
        return 0

    from app import paste
    from app.vision.ocr import OcrBackend

    truth = json.loads((FIXTURES / "team.expected.json").read_text())["team"]["pokemon"]
    images = [("image/png", (FIXTURES / n).read_bytes())
              for n in ("moves-and-more.png", "stats.png")]

    team = OcrBackend().extract(images)
    read = paste.normalize_team(team)

    total = hits = 0
    misses: list[str] = []

    def compare(label: str, got, want) -> None:
        nonlocal total, hits
        total += 1
        if got == want:
            hits += 1
        else:
            misses.append(f"{label}: leido {got!r}, esperado {want!r}")

    if len(read) != len(truth):
        print(f"FALLO: leidos {len(read)} Pokemon, esperados {len(truth)}")
        return 1

    for mon, want in zip(read, truth):
        name = want["species"]
        compare(f"{name} especie", mon["species"]["value"], want["species"])
        compare(f"{name} genero", mon["gender"], want["gender"])
        compare(f"{name} habilidad", mon["ability"]["value"], want["ability"])
        compare(f"{name} objeto", mon["item"]["value"], want["item"])
        for i, move in enumerate(want["moves"]):
            compare(f"{name} mov{i + 1}", mon["moves"][i]["value"], move)
        for key, value in want["sp"].items():
            compare(f"{name} SP {key}", mon["sp"].get(key), value)
        compare(f"{name} ▲", mon["boosted_stat"], want["boosted_stat"])
        compare(f"{name} ▼", mon["hindered_stat"], want["hindered_stat"])

    print(f"{hits}/{total} campos correctos ({hits / total:.1%})")
    for m in misses:
        print("  FALLA", m)

    warnings = [w for mon in read for w in mon["warnings"]]
    print(f"\n{len(warnings)} avisos:")
    for w in warnings:
        print("  *", w)

    return 0 if hits == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
