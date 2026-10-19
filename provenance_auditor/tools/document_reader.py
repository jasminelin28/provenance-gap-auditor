"""Pull plain text out of an uploaded file.

Dash hands uploads over as a base64 data URL, so this decodes that and reads
PDFs with pdfplumber and text files directly. Only the first few pages are
read: a lot catalogue is short, and an unbounded page count would be an easy
way to run up the token bill.
"""

import base64
import io
from typing import List, Tuple

max_pdf_pages = 8


def extract_text(contents: str, filename: str) -> Tuple[str, List[str]]:
    """Decode a Dash upload into text. Returns the text and any warnings."""
    warnings: List[str] = []
    if not contents:
        return "", ["The uploaded file was empty."]

    try:
        _header, _, payload = contents.partition(",")
        raw = base64.b64decode(payload)
    except (ValueError, TypeError):
        return "", [f"Could not decode '{filename}'. Try pasting the text instead."]

    lowered = (filename or "").lower()

    if lowered.endswith(".pdf"):
        return _extract_pdf(raw, filename, warnings)

    if lowered.endswith((".txt", ".md", ".csv")):
        for encoding in ("utf-8", "latin-1"):
            try:
                return raw.decode(encoding), warnings
            except UnicodeDecodeError:
                continue
        return "", [f"Could not read the text encoding of '{filename}'."]

    return "", [
        f"'{filename}' is not a supported file type. Upload a PDF or a .txt file, "
        "or paste the record into the box."
    ]


def _extract_pdf(raw: bytes, filename: str, warnings: List[str]) -> Tuple[str, List[str]]:
    try:
        import pdfplumber
    except ImportError:
        return "", ["PDF support needs pdfplumber. Run: pip install -r requirements.txt"]

    pages: List[str] = []
    try:
        with pdfplumber.open(io.BytesIO(raw)) as document:
            total = len(document.pages)
            for page in document.pages[:max_pdf_pages]:
                pages.append(page.extract_text() or "")
            if total > max_pdf_pages:
                warnings.append(
                    f"'{filename}' has {total} pages; only the first {max_pdf_pages} "
                    "were read, to keep the cost of one audit bounded."
                )
    except Exception as error:  # pdfplumber raises several unrelated types
        return "", [f"Could not read '{filename}' as a PDF ({type(error).__name__})."]

    text = "\n".join(page for page in pages if page.strip())
    if not text.strip():
        warnings.append(
            f"No selectable text was found in '{filename}'. If it is a scan, it "
            "needs OCR first; this app does not read images."
        )
    return text, warnings
