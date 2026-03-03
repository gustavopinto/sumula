"""Extract text from PDF files using PyMuPDF."""
from pathlib import Path


def extract_pdf(path: str | Path) -> list[dict]:
    """Return list of {page: int, text: str} dicts, one per page."""
    import fitz  # PyMuPDF

    results = []
    doc = fitz.open(str(path))
    try:
        for page_num, page in enumerate(doc, start=1):
            text = page.get_text("text")
            if text.strip():
                results.append({"page": page_num, "text": text})
    finally:
        doc.close()
    return results
