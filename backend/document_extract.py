from pathlib import Path

from pypdf import PdfReader


def extract_text_from_file(path: Path, original_filename: str) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        reader = PdfReader(str(path))
        parts = []
        for page in reader.pages:
            t = page.extract_text()
            if t:
                parts.append(t)
        return "\n\n".join(parts).strip() or "[No extractable text from PDF]"
    if suffix in (".txt", ".md", ".markdown"):
        return path.read_text(encoding="utf-8", errors="replace").strip()
    # Try as text for unknown extensions
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return f"[Could not read file: {original_filename}]"
