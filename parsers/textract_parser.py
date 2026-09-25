"""AWS Textract — cloud OCR. Renders each page to a 200-dpi PNG first, so like
LlamaParse it can read scanned pages and text inside images.

Requires AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY and optionally AWS_REGION.
"""
import os

NAME = "AWS Textract"
KIND = "cloud"
PACKAGE = "boto3"
REQUIRES = ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"]

# PyMuPDF's default is 72 dpi (a 612x792 image for a Letter page), which
# throws away most of the detail OCR needs. 200 dpi gives 1700x2200 for
# Letter, well inside Textract's synchronous limits (10 MB, 10000 px).
DPI = 200


def render_pages(pdf_path: str, dpi: int = DPI) -> list[bytes]:
    import pymupdf

    with pymupdf.open(pdf_path) as document:
        return [page.get_pixmap(dpi=dpi).tobytes("png") for page in document]


def extract(pdf_path: str) -> str:
    import boto3

    session = boto3.Session(
        aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
    )
    client = session.client("textract", region_name=os.getenv("AWS_REGION", "us-east-1"))

    pages = []
    for png in render_pages(pdf_path):
        response = client.detect_document_text(Document={"Bytes": png})
        # LINE blocks preserve reading order better than WORD blocks.
        lines = [b["Text"] for b in response["Blocks"] if b["BlockType"] == "LINE"]
        pages.append("\n".join(lines))
    return "\n\n".join(pages)
