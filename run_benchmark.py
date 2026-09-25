"""Run every available parser over the scored corpus, score each extraction
against its hand-verified reference, and write the results.

    uv run python run_benchmark.py --local-only --repeats 5

writes
    results/extractions/<document>/<parser>.txt   raw output, for diffing
    results/results.json                          every metric + environment
    results/RESULTS.md                            tables rendered from the JSON
and refreshes the results block in README.md.

Local parsers always run. Cloud parsers run only when their credentials are
set, and never with --local-only. `--check results/results.json` re-runs the
benchmark and fails if any quality metric differs from the committed file
(timings are ignored), which is how CI proves the published table reproduces.

`--input DIR` runs the parsers over your own PDFs instead, unscored: it
records characters and seconds only.
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib
import importlib.metadata
import json
import logging
import os
import platform
import statistics
import sys
import time
from pathlib import Path

import scoring

ROOT = Path(__file__).resolve().parent
PARSER_MODULES = [
    "parsers.pypdf_parser",
    "parsers.pdfminer_parser",
    "parsers.pdfplumber_parser",
    "parsers.llamaparse_parser",
    "parsers.textract_parser",
]
README_START = "<!-- results:start -->"
README_END = "<!-- results:end -->"
TIMING_KEYS = {"seconds_median", "seconds_runs"}


def load_parsers():
    return [importlib.import_module(m) for m in PARSER_MODULES]


def parser_status(module, local_only: bool) -> str | None:
    """None when the parser should run, otherwise why it does not."""
    if module.KIND == "cloud" and local_only:
        return "not run (--local-only)"
    missing = [k for k in module.REQUIRES if not os.getenv(k)]
    if missing:
        return f"not run (set {', '.join(missing)})"
    return None


def package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def run_one(module, pdf_path: Path, repeats: int):
    """Return (text, [seconds...], error). Never raises, so one broken parser
    does not abandon the run."""
    text, runs = None, []
    for _ in range(repeats):
        start = time.perf_counter()
        try:
            text = module.extract(str(pdf_path))
        except Exception as exc:  # noqa: BLE001 - reporting, not handling
            return None, runs, f"{type(exc).__name__}: {exc}"
        runs.append(time.perf_counter() - start)
    return text, runs, None


def score(text: str, reference: str, checks: dict) -> dict:
    out = {
        "characters": len(text),
        "cer": round(scoring.cer(reference, text), 4),
        "wer": round(scoring.wer(reference, text), 4),
        "bow_f1": round(scoring.bow_f1(reference, text), 4),
        **scoring.line_stats(text),
    }
    if checks.get("tables"):
        totals = {"rows_intact": 0, "rows_total": 0, "cells_found": 0, "cells_total": 0}
        for rows in checks["tables"]:
            for key, value in scoring.table_scores(text, rows).items():
                totals[key] += value
        out["table"] = totals
    if checks.get("rtl"):
        out["rtl"] = {lang: scoring.rtl_order(text, s) for lang, s in checks["rtl"].items()}
    if checks.get("indic"):
        out["indic"] = {lang: scoring.indic_intact(text, s) for lang, s in checks["indic"].items()}
    return out


def run_corpus(args) -> dict:
    manifest = json.loads((args.corpus / "manifest.json").read_text(encoding="utf-8"))
    parsers = load_parsers()
    out_root = args.out
    rows, parser_info = [], {}

    for module in parsers:
        parser_info[module.NAME] = {
            "kind": module.KIND,
            "package": module.PACKAGE,
            "version": package_version(module.PACKAGE),
            "status": parser_status(module, args.local_only) or "run",
        }

    documents = []
    for doc in manifest["documents"]:
        pdf = args.corpus / doc["file"]
        reference = (args.corpus / doc["reference"]).read_text(encoding="utf-8")
        reference_chars = len(scoring.normalize(reference))
        image_only = doc.get("image_only_text", [])
        image_chars = reference_chars if image_only == "all" else sum(len(scoring.normalize(s)) for s in image_only)
        documents.append({
            "id": doc["id"], "file": doc["file"], "title": doc["title"],
            "categories": doc["categories"], "licence": doc["licence"],
            "source_url": doc.get("source_url"),
            "reference_characters": reference_chars,
            "image_only_characters": image_chars,
        })
        print(f"\n{doc['id']}  ({pdf.name})")
        for module in parsers:
            status = parser_status(module, args.local_only)
            if status:
                print(f"  {module.NAME:<13} {status}")
                rows.append({"document": doc["id"], "parser": module.NAME, "status": status})
                continue
            text, runs, error = run_one(module, pdf, args.repeats)
            if error:
                print(f"  {module.NAME:<13} FAILED  {error}")
                rows.append({"document": doc["id"], "parser": module.NAME, "status": f"failed: {error}"})
                continue
            destination = out_root / "extractions" / doc["id"]
            destination.mkdir(parents=True, exist_ok=True)
            (destination / f"{module.NAME}.txt").write_text(text, encoding="utf-8", newline="\n")
            metrics = score(text, reference, doc.get("checks", {}))
            row = {
                "document": doc["id"], "parser": module.NAME, "status": "run",
                "seconds_median": round(statistics.median(runs), 4),
                "seconds_runs": [round(s, 4) for s in runs],
                **metrics,
            }
            rows.append(row)
            print(f"  {module.NAME:<13} {row['seconds_median']:7.3f}s  CER {row['cer']:.3f}  "
                  f"WER {row['wer']:.3f}  BoW-F1 {row['bow_f1']:.3f}  {row['characters']:>6,} chars")

    return {
        "generated": dt.date.today().isoformat(),
        "command": " ".join(["python", "run_benchmark.py", *sys.argv[1:]]),
        "repeats": args.repeats,
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor() or None,
        },
        "parsers": parser_info,
        "documents": documents,
        "scores": rows,
    }


# ---------------------------------------------------------------- rendering

def _fmt(value, digits=3):
    return "–" if value is None else f"{value:.{digits}f}"


def render_markdown(results: dict) -> str:
    docs = results["documents"]
    scores = {(r["document"], r["parser"]): r for r in results["scores"]}
    parsers = list(results["parsers"])
    ran = [p for p in parsers if results["parsers"][p]["status"] == "run"]
    skipped = [p for p in parsers if p not in ran]
    env = results["environment"]
    versions = ", ".join(
        f"{p} ({results['parsers'][p]['package']} {results['parsers'][p]['version']})" for p in ran
    )

    out = [
        f"Generated {results['generated']} by `{results['command']}` "
        f"(median of {results['repeats']} runs; Python {env['python']}, {env['platform']}). "
        f"Parsers: {versions}.",
        "",
        "**Corpus** (reference characters after normalization; text that exists only inside images is out of reach for text-layer parsers)",
        "",
        "| Document | Stresses | Reference chars | Only in images |",
        "|---|---|---:|---:|",
    ]
    for doc in docs:
        share = doc["image_only_characters"] / doc["reference_characters"]
        out.append(f"| {doc['id']} | {', '.join(doc['categories'])} | {doc['reference_characters']:,} "
                   f"| {doc['image_only_characters']:,} ({share:.0%}) |")
    out += [
        "",
        "**Text fidelity** (lower CER/WER is better, higher BoW-F1 is better; seconds are wall-clock medians on the machine above)",
        "",
        "| Document | Parser | CER | WER | BoW-F1 | Chars out / ref | Seconds |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for doc in docs:
        for p in parsers:
            r = scores[(doc["id"], p)]
            if r["status"] != "run":
                out.append(f"| {doc['id']} | {p} | {r['status']} | | | | |")
                continue
            out.append(
                f"| {doc['id']} | {p} | {_fmt(r['cer'])} | {_fmt(r['wer'])} | {_fmt(r['bow_f1'])} "
                f"| {r['characters']:,} / {doc['reference_characters']:,} | {_fmt(r['seconds_median'])} |"
            )

    table_docs = [d for d in docs if any("table" in scores[(d["id"], p)] for p in ran)]
    if table_docs:
        out += ["", "**Table structure** (rows whose cells all come out on one line, in order / cells found anywhere)", "",
                "| Document | " + " | ".join(ran) + " |", "|---|" + "---:|" * len(ran)]
        for doc in table_docs:
            cells = []
            for p in ran:
                t = scores[(doc["id"], p)]["table"]
                cells.append(f"rows {t['rows_intact']}/{t['rows_total']} · cells {t['cells_found']}/{t['cells_total']}")
            out.append(f"| {doc['id']} | " + " | ".join(cells) + " |")

    script_docs = [d for d in docs if any("rtl" in scores[(d["id"], p)] or "indic" in scores[(d["id"], p)] for p in ran)]
    for doc in script_docs:
        first = scores[(doc["id"], ran[0])]
        out += ["", f"**Scripts in `{doc['id']}`** (RTL: reading order of the sentence; Indic: sentence intact, share of words exact)", "",
                "| Script | " + " | ".join(ran) + " |", "|---|" + "---|" * len(ran)]
        for lang in first.get("rtl", {}):
            out.append(f"| {lang} (RTL) | " + " | ".join(scores[(doc["id"], p)]["rtl"][lang]["verdict"] for p in ran) + " |")
        for lang in first.get("indic", {}):
            vals = []
            for p in ran:
                v = scores[(doc["id"], p)]["indic"][lang]
                vals.append(f"{'intact' if v['intact'] else 'broken'}, {v['words_exact']:.0%} of words exact")
            out.append(f"| {lang} | " + " | ".join(vals) + " |")
        out.append("| Lines out (words per line) | " + " | ".join(
            f"{scores[(doc['id'], p)]['lines']} ({scores[(doc['id'], p)]['words_per_line']})" for p in ran) + " |")

    if skipped:
        out += ["", "Not run in this table: " + "; ".join(f"{p}: {results['parsers'][p]['status']}" for p in skipped) + "."]
    return "\n".join(out) + "\n"


def write_outputs(results: dict, out_root: Path, update_readme: bool) -> None:
    out_root.mkdir(parents=True, exist_ok=True)
    (out_root / "results.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    markdown = render_markdown(results)
    (out_root / "RESULTS.md").write_text("# Results\n\n" + markdown, encoding="utf-8", newline="\n")
    if update_readme:
        readme = ROOT / "README.md"
        text = readme.read_text(encoding="utf-8")
        start, end = text.index(README_START) + len(README_START), text.index(README_END)
        readme.write_text(text[:start] + "\n" + markdown + text[end:], encoding="utf-8", newline="\n")


# ------------------------------------------------------------------ checking

def quality_view(results: dict) -> dict:
    """Everything that should reproduce exactly: all metrics except timings."""
    return {
        (r["document"], r["parser"]): {k: v for k, v in r.items() if k not in TIMING_KEYS}
        for r in results["scores"] if r["status"] == "run"
    }


def check(results: dict, committed_path: Path) -> int:
    committed = quality_view(json.loads(committed_path.read_text(encoding="utf-8")))
    fresh = quality_view(results)
    problems = []
    for key in sorted(set(committed) | set(fresh)):
        if committed.get(key) != fresh.get(key):
            problems.append(f"{key}: committed {committed.get(key)} != fresh {fresh.get(key)}")
    if problems:
        print("\nCHECK FAILED — quality metrics differ from", committed_path)
        print("\n".join(problems))
        return 1
    print(f"\nCHECK OK — {len(fresh)} parser×document quality results match {committed_path}")
    return 0


# -------------------------------------------------------------- ad-hoc mode

def run_unscored(args) -> None:
    pdfs = sorted(args.input.glob("*.pdf"))
    if not pdfs:
        raise SystemExit(f"No PDFs found in {args.input}/")
    summary = []
    for pdf in pdfs:
        print(f"\n{pdf.name}")
        for module in load_parsers():
            status = parser_status(module, args.local_only)
            if status:
                print(f"  {module.NAME:<13} {status}")
                continue
            text, runs, error = run_one(module, pdf, args.repeats)
            if error:
                print(f"  {module.NAME:<13} FAILED  {error}")
                summary.append({"document": pdf.name, "parser": module.NAME, "error": error})
                continue
            destination = args.out / "extractions" / pdf.stem
            destination.mkdir(parents=True, exist_ok=True)
            (destination / f"{module.NAME}.txt").write_text(text, encoding="utf-8")
            seconds = statistics.median(runs)
            print(f"  {module.NAME:<13} {seconds:7.3f}s  {len(text):>8,} chars")
            summary.append({"document": pdf.name, "parser": module.NAME,
                            "seconds_median": round(seconds, 4), "characters": len(text)})
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nUnscored run: extractions in {args.out}/extractions/, timings in {args.out}/summary.json")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus", type=Path, default=ROOT / "corpus", help="scored corpus directory")
    ap.add_argument("--input", type=Path, help="run unscored over the PDFs in this directory instead")
    ap.add_argument("--out", type=Path, default=ROOT / "results", help="output directory")
    ap.add_argument("--repeats", type=int, default=5, help="timed runs per parser and document")
    ap.add_argument("--local-only", action="store_true", help="never call the cloud parsers")
    ap.add_argument("--check", type=Path, help="compare quality metrics with this results.json and exit non-zero on any difference")
    args = ap.parse_args()

    # pypdf and pdfminer log font-descriptor warnings for these PDFs; they do
    # not change the extracted text (checked), so keep the console readable.
    for noisy in ("pypdf", "pdfminer"):
        logging.getLogger(noisy).setLevel(logging.ERROR)

    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    if args.input:
        run_unscored(args)
        return 0

    results = run_corpus(args)
    publishing = args.out.resolve() == (ROOT / "results").resolve()
    if args.check and publishing:
        raise SystemExit("--check needs --out somewhere other than results/, so the committed file is not overwritten first")
    write_outputs(results, args.out, update_readme=publishing)
    print(f"\nWrote {args.out}/results.json and RESULTS.md" + (" and refreshed README.md" if publishing else ""))
    return check(results, args.check) if args.check else 0


if __name__ == "__main__":
    sys.exit(main())
