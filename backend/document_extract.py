from pathlib import Path

from pypdf import PdfReader

# Image uploads: transcribed via OpenAI Vision in extract_text_from_file_async.
IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".webp", ".gif"})

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None


def _extract_pdf_pymupdf_column_aware(path: Path) -> str:
    """
    Order text by reading columns top-to-bottom (left column, then right),
    so glossary terms stay with the definition below them—not with text in the other column.
    Falls back to empty string if PyMuPDF is unavailable or yields nothing.
    """
    if fitz is None:
        return ""

    doc = fitz.open(path)
    page_chunks: list[str] = []

    try:
        for page in doc:
            w = float(page.rect.width)
            if w <= 0:
                continue
            mid = w * 0.5
            blocks = page.get_text("blocks")
            text_blocks = [b for b in blocks if len(b) >= 7 and b[6] == 0]
            pieces: list[tuple[float, float, str]] = []
            for b in text_blocks:
                txt = (b[4] or "").strip()
                if not txt:
                    continue
                x0, y0, x1, y1 = float(b[0]), float(b[1]), float(b[2]), float(b[3])
                cx = (x0 + x1) / 2.0
                pieces.append((cx, y0, txt))

            if not pieces:
                continue

            centers = [p[0] for p in pieces]
            all_left = all(c < mid for c in centers)
            all_right = all(c >= mid for c in centers)

            if all_left or all_right:
                pieces.sort(key=lambda p: (p[1], p[0]))
                page_chunks.append("\n".join(p[2] for p in pieces))
                continue

            left = [p for p in pieces if p[0] < mid]
            right = [p for p in pieces if p[0] >= mid]
            left.sort(key=lambda p: (p[1], p[0]))
            right.sort(key=lambda p: (p[1], p[0]))
            parts: list[str] = []
            if left:
                parts.append("\n".join(p[2] for p in left))
            if right:
                parts.append("\n".join(p[2] for p in right))
            if parts:
                page_chunks.append("\n\n".join(parts))
    finally:
        doc.close()

    return "\n\n".join(page_chunks).strip()


def _extract_pdf_pypdf_fallback(path: Path) -> str:
    reader = PdfReader(str(path))
    parts: list[str] = []
    for page in reader.pages:
        t = page.extract_text()
        if t:
            parts.append(t)
    return "\n\n".join(parts).strip()


def extract_text_from_file(path: Path, original_filename: str) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        text = _extract_pdf_pymupdf_column_aware(path)
        if not text:
            text = _extract_pdf_pypdf_fallback(path)
        return text or "[No extractable text from PDF]"
    if suffix in (".txt", ".md", ".markdown"):
        return path.read_text(encoding="utf-8", errors="replace").strip()
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return f"[Could not read file: {original_filename}]"


async def extract_text_from_file_async(path: Path, original_filename: str) -> str:
    """Like extract_text_from_file, but awaits vision transcription for image types."""
    suffix = path.suffix.lower()
    if suffix in IMAGE_EXTENSIONS:
        from llm_service import transcribe_image_file

        return await transcribe_image_file(path)
    return extract_text_from_file(path, original_filename)
