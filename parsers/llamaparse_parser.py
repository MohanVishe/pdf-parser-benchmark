"""LlamaParse via the llama-cloud SDK — cloud, LLM-assisted, aimed at complex
layouts, tables and scans.

Uses the current `llama-cloud` package (the old `llama-parse` package is
deprecated). Requires LLAMA_CLOUD_API_KEY. The tier defaults to
"cost_effective"; override with LLAMA_PARSE_TIER (fast, cost_effective,
agentic, agentic_plus).
"""
import os
from pathlib import Path

NAME = "LlamaParse"
KIND = "cloud"
PACKAGE = "llama-cloud"
REQUIRES = ["LLAMA_CLOUD_API_KEY"]


def extract(pdf_path: str) -> str:
    from llama_cloud import LlamaCloud

    client = LlamaCloud(api_key=os.environ["LLAMA_CLOUD_API_KEY"])
    # parse() uploads the file, creates the job and polls until it finishes.
    result = client.parsing.parse(
        tier=os.getenv("LLAMA_PARSE_TIER", "cost_effective"),
        version="latest",
        upload_file=Path(pdf_path),
        expand=["text"],
    )
    if result.job.status != "COMPLETED" or result.text is None:
        raise RuntimeError(f"LlamaParse job {result.job.id} ended {result.job.status}: {result.job.error_message}")
    return "\n\n".join(page.text for page in result.text.pages)
