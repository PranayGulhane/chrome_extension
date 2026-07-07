import io

import pdfplumber
from pypdf import PdfReader


class ResumeTextExtractionError(Exception):
    pass


def _extract_with_pdfplumber(data: bytes) -> str:
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)


def _extract_with_pypdf(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def extract_resume_text(data: bytes) -> str:
    """pdfplumber primary, pypdf fallback (never PyMuPDF — AGPL-3.0). Raises if neither
    extracts any usable text, e.g. a scanned/image-only PDF with no text layer."""
    text = ""
    try:
        text = _extract_with_pdfplumber(data)
    except Exception:
        text = ""

    if not text.strip():
        try:
            text = _extract_with_pypdf(data)
        except Exception:
            text = ""

    if not text.strip():
        raise ResumeTextExtractionError(
            "Could not extract any text from this PDF. It may be a scanned image without a text layer."
        )

    return text
