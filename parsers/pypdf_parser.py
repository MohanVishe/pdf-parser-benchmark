"""PyPDF — pure-Python, local, text-layer only. Default extract_text() settings."""
from pypdf import PdfReader

NAME = "PyPDF"
KIND = "local"
PACKAGE = "pypdf"
REQUIRES: list[str] = []


def extract(pdf_path: str) -> str:
    reader = PdfReader(pdf_path)
    return "\n".join(page.extract_text() or "" for page in reader.pages)
