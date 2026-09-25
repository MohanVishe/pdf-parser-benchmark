"""Each local adapter on a tiny PDF built here byte by byte (so the fixture is
readable and needs no PDF-writing library), plus the cloud-parser gating."""
import importlib
import json

import pytest

import run_benchmark

LOCAL = ["parsers.pypdf_parser", "parsers.pdfminer_parser", "parsers.pdfplumber_parser"]
CLOUD = ["parsers.llamaparse_parser", "parsers.textract_parser"]


def _minimal_pdf(lines: list[str]) -> bytes:
    """A one-page Letter PDF with each line drawn in Helvetica."""
    ops = ["BT", "/F1 12 Tf", "72 720 Td"]
    for i, line in enumerate(lines):
        if i:
            ops.append("0 -20 Td")
        ops.append("(" + line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") + ") Tj")
    ops.append("ET")
    stream = "\n".join(ops).encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


@pytest.fixture
def tiny_pdf(tmp_path):
    path = tmp_path / "tiny.pdf"
    path.write_bytes(_minimal_pdf(["Parser benchmark fixture", "Second line 42"]))
    return path


@pytest.fixture
def blank_pdf(tmp_path):
    path = tmp_path / "blank.pdf"
    path.write_bytes(_minimal_pdf([]))
    return path


@pytest.mark.parametrize("module_path", LOCAL)
def test_local_adapter_extracts_both_lines_in_order(module_path, tiny_pdf):
    module = importlib.import_module(module_path)
    text = module.extract(str(tiny_pdf))
    assert isinstance(text, str)
    words = text.split()
    assert words == ["Parser", "benchmark", "fixture", "Second", "line", "42"]


@pytest.mark.parametrize("module_path", LOCAL)
def test_local_adapter_returns_empty_text_for_a_page_without_text(module_path, blank_pdf):
    module = importlib.import_module(module_path)
    assert module.extract(str(blank_pdf)).strip() == ""


@pytest.mark.parametrize("module_path", LOCAL + CLOUD)
def test_adapter_contract(module_path):
    module = importlib.import_module(module_path)
    assert module.NAME and module.KIND in {"local", "cloud"} and module.PACKAGE
    assert callable(module.extract)
    assert (module.KIND == "cloud") == bool(module.REQUIRES)


@pytest.mark.parametrize("module_path", CLOUD)
def test_cloud_parser_skipped_without_credentials(module_path, monkeypatch):
    module = importlib.import_module(module_path)
    for key in module.REQUIRES:
        monkeypatch.delenv(key, raising=False)
    assert run_benchmark.parser_status(module, local_only=False).startswith("not run (set ")


@pytest.mark.parametrize("module_path", CLOUD)
def test_local_only_never_runs_cloud_parsers_even_with_credentials(module_path, monkeypatch):
    module = importlib.import_module(module_path)
    for key in module.REQUIRES:
        monkeypatch.setenv(key, "placeholder")
    assert run_benchmark.parser_status(module, local_only=True) == "not run (--local-only)"
    assert run_benchmark.parser_status(module, local_only=False) is None


def test_textract_renders_letter_page_at_200_dpi(tiny_pdf):
    pytest.importorskip("pymupdf")
    from parsers import textract_parser

    png = textract_parser.render_pages(str(tiny_pdf))[0]
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = int.from_bytes(png[16:20], "big"), int.from_bytes(png[20:24], "big")
    assert (width, height) == (1700, 2200)


def test_check_ignores_timings_but_catches_metric_changes(tmp_path):
    base = {"scores": [{"document": "d", "parser": "p", "status": "run", "cer": 0.1,
                        "seconds_median": 1.0, "seconds_runs": [1.0]}]}
    committed = tmp_path / "results.json"
    committed.write_text(json.dumps(base))
    slower = json.loads(json.dumps(base))
    slower["scores"][0]["seconds_median"] = 9.0
    assert run_benchmark.check(slower, committed) == 0
    worse = json.loads(json.dumps(base))
    worse["scores"][0]["cer"] = 0.2
    assert run_benchmark.check(worse, committed) == 1
