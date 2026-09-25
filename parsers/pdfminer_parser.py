"""PDFMiner.six — local, the layout engine several other tools build on.
Default LAParams."""
from pdfminer.high_level import extract_text

NAME = "PDFMiner"
KIND = "local"
PACKAGE = "pdfminer.six"
REQUIRES: list[str] = []


def extract(pdf_path: str) -> str:
    with open(pdf_path, "rb") as fh:
        return extract_text(fh)
