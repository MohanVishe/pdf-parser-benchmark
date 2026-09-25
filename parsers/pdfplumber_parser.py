"""PDFPlumber — local, character-position aware; default extract_text()."""
import pdfplumber

NAME = "PDFPlumber"
KIND = "local"
PACKAGE = "pdfplumber"
REQUIRES: list[str] = []


def extract(pdf_path: str) -> str:
    with pdfplumber.open(pdf_path) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)
