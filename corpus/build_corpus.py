"""Rebuild the scored corpus PDFs from their public sources.

The PDFs are committed, so you never need to run this to use the benchmark.
It exists so every document's provenance is reproducible: it downloads each
source listed in manifest.json, checks the SHA-256 recorded there, keeps only
the scoped pages, applies the documented transform, and writes the result.

    uv run python corpus/build_corpus.py            # rebuild and compare
    uv run python corpus/build_corpus.py --write    # overwrite corpus/*.pdf
"""
import argparse
import hashlib
import io
import json
import sys
import urllib.request
from pathlib import Path

from pypdf import PdfReader, PdfWriter

HERE = Path(__file__).resolve().parent
CACHE = HERE / ".cache"


def fetch(url: str, expected_sha256: str) -> bytes:
    CACHE.mkdir(exist_ok=True)
    cached = CACHE / hashlib.sha256(url.encode()).hexdigest()[:16]
    if cached.exists():
        data = cached.read_bytes()
    else:
        request = urllib.request.Request(url, headers={"User-Agent": "pdf-parser-benchmark corpus builder"})
        with urllib.request.urlopen(request, timeout=60) as response:
            data = response.read()
        cached.write_bytes(data)
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected_sha256:
        raise SystemExit(f"{url}: sha256 {actual} != manifest {expected_sha256}")
    return data


def build(doc: dict) -> bytes:
    source = fetch(doc["source_url"], doc["source_sha256"])
    reader = PdfReader(io.BytesIO(source))
    writer = PdfWriter()
    for page_number in doc["source_pages"]:
        writer.add_page(reader.pages[page_number - 1])
    if doc["transform"] == "remove_text_layer":
        # Drops the invisible OCR text the scanner software added; the page
        # image stream is copied unchanged. The page then behaves like a raw scan.
        writer.remove_text()
    elif doc["transform"] != "page_subset":
        raise SystemExit(f"unknown transform {doc['transform']!r}")
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", action="store_true", help="overwrite the committed PDFs")
    args = ap.parse_args()

    manifest = json.loads((HERE / "manifest.json").read_text(encoding="utf-8"))
    for doc in manifest["documents"]:
        if "source_url" not in doc:
            print(f"{doc['id']}: authored in this repo, nothing to fetch")
            continue
        pdf = build(doc)
        target = HERE / doc["file"]
        if args.write:
            target.write_bytes(pdf)
            print(f"{doc['id']}: wrote {target.name} ({len(pdf):,} bytes)")
        else:
            # Byte equality is not guaranteed across pypdf versions, so compare
            # what matters: page count and page size.
            built, committed = PdfReader(io.BytesIO(pdf)), PdfReader(target)
            same = len(built.pages) == len(committed.pages) and all(
                a.mediabox == b.mediabox for a, b in zip(built.pages, committed.pages)
            )
            print(f"{doc['id']}: {'matches' if same else 'DIFFERS from'} committed {target.name}")
            if not same:
                return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
