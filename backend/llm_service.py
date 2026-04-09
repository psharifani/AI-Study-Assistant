import base64
import json
import re
import uuid
from io import BytesIO
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI
from PIL import Image

from config import get_openai_credentials, get_openai_vision_model

STUDY_SYSTEM_PREFIX = """You are a study assistant for higher-education learners (psychology, political science, history, and similar).
Your answers must be grounded ONLY in the STUDY DOCUMENT provided by the user in this conversation.
If the document does not contain enough information to answer, say so and suggest what topic might be missing.
Do not invent facts, citations, or sources not supported by the document.
Use clear, student-friendly language while remaining accurate to the document."""

# Used only for the Learning chat tab (not flashcards/quiz generation).
CHAT_LEARNING_SYSTEM_PREFIX = """You are a patient tutor for students (psychology, political science, history, and similar).

Your role:
- Students often need **basics, intuition, or plain-language definitions** before they can understand their readings or flashcards. You may explain general concepts, background, and widely accepted facts using your general knowledge.
- **Do not** restrict answers to only what appears in their uploaded material. If they ask "what is X in simple terms" or need foundational knowledge, give a clear, accurate explanation at the right level first.
- When this deck includes **STUDY MATERIAL** below, **connect** to it when useful: point out how the reading fits their question, or quote/paraphrase if it helps. If the material does not cover the topic, say so briefly, and still help them learn.
- Be accurate; avoid inventing specific citations, page numbers, or quotes from a document unless they appear in the provided text.
- Use clear, friendly language suitable for learners.
- **Formatting:** When you give several points or steps, use Markdown with **blank lines between paragraphs** and **one list item per line** (numbered `1.` or bullets `-`), not a single run-on paragraph. Use `**bold**` for key terms."""


def _openai() -> tuple[AsyncOpenAI, str]:
    key, model = get_openai_credentials()
    if not key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set in backend/.env. "
            "If you already added it and http://127.0.0.1:8080/api/health shows openai_configured true, "
            "this request is probably hitting a different server (wrong port). "
            "Set VITE_API_PROXY in frontend/.env to your uvicorn URL (e.g. http://127.0.0.1:8080) and restart npm run dev."
        )
    return AsyncOpenAI(api_key=key), model


def _extract_json_array(text: str) -> list[Any]:
    text = text.strip()
    m = re.search(r"\[[\s\S]*\]", text)
    if not m:
        raise ValueError("Model did not return a JSON array")
    return json.loads(m.group())


async def generate_flashcards(document_text: str, max_cards: int = 25) -> list[dict[str, str]]:
    client, model = _openai()
    prompt = f"""From the study document below, create up to {max_cards} high-quality flashcards.
Each flashcard should target: key concepts, important definitions, or likely exam/review questions.

Layout rules (important for glossaries and two-column PDFs):
- Text may list the LEFT column first, then the RIGHT column on each page (or a single column).
- Within one column, reading order is top to bottom. A short title or term is followed by its longer definition directly below it.
- Do NOT pair a term with text that only sits beside it in another column; only pair with text that follows it in the same column block.

Return ONLY a JSON array of objects with keys "front" and "back" (strings). No markdown fences.

STUDY DOCUMENT:
---
{document_text[:120_000]}
---
"""
    resp = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": STUDY_SYSTEM_PREFIX},
            {"role": "user", "content": prompt},
        ],
        temperature=0.4,
    )
    raw = resp.choices[0].message.content or "[]"
    items = _extract_json_array(raw)
    out: list[dict[str, str]] = []
    for it in items:
        if isinstance(it, dict) and "front" in it and "back" in it:
            f, b = str(it["front"]).strip(), str(it["back"]).strip()
            if f and b:
                out.append({"front": f, "back": b})
    return out


async def learning_chat(document_text: str, history: list[dict[str, str]], user_message: str) -> str:
    """Learning chat: general tutoring + optional deck material as context (not the only allowed source)."""
    client, model = _openai()
    doc_trim = (document_text or "").strip()[:120_000]
    if doc_trim:
        doc_block = (
            "OPTIONAL CONTEXT — STUDY MATERIAL FOR THIS DECK (use when it helps; "
            "students may also need explanations that are not in this text):\n---\n"
            f"{doc_trim}\n---"
        )
    else:
        doc_block = (
            "There is no uploaded study document for this deck yet. "
            "Answer using clear, accurate general explanations; you may suggest uploading material when course-specific detail would help."
        )
    messages: list[dict[str, str]] = [
        {"role": "system", "content": CHAT_LEARNING_SYSTEM_PREFIX + "\n\n" + doc_block},
    ]
    for h in history[-20:]:
        messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": user_message})
    resp = await client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.55,
    )
    return (resp.choices[0].message.content or "").strip()


async def suggest_chat_session_title(user_message: str, assistant_reply: str) -> str:
    """Short sidebar label for the thread: subject/topic, not a copy of the opening line."""
    client, model = _openai()
    um = (user_message or "").strip()[:2000]
    ar = (assistant_reply or "").strip()[:1500]
    prompt = f"""Based on this exchange, what is the main SUBJECT or TOPIC of the conversation?

Student message:
{um}

Assistant reply:
{ar}

Output exactly one line: a short title (3–10 words) naming that subject, like a folder label.
Examples of good titles: "Causes of WWI", "SM-2 scheduling", "Comparing fascism and communism".
Do not repeat the student's question verbatim. No quotation marks. No trailing period."""
    resp = await client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": "You name study chat threads by topic only. Reply with a single plain title line, nothing else.",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.35,
        max_tokens=48,
    )
    raw = (resp.choices[0].message.content or "").strip()
    line = raw.split("\n")[0].strip().strip('"').strip("'").rstrip(".")
    if len(line) > 80:
        line = line[:77] + "…"
    return line or "Chat"


async def generate_quiz(
    document_text: str, num_mc: int, num_sa: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    client, model = _openai()
    prompt = f"""Create a mock test from the study document only.

The document may use two columns per page: content is ordered left column (top to bottom), then right column. Do not mix facts from unrelated side-by-side entries.

Requirements:
- Exactly {num_mc} multiple-choice questions: 4 options each, exactly one correct.
- Exactly {num_sa} short-answer questions: include a concise model answer for grading.

Return ONLY valid JSON with this shape (no markdown):
{{
  "multiple_choice": [
    {{"question": "...", "options": ["A","B","C","D"], "correct_index": 0}}
  ],
  "short_answer": [
    {{"question": "...", "model_answer": "..."}}
  ]
}}

STUDY DOCUMENT:
---
{document_text[:120_000]}
---
"""
    resp = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": STUDY_SYSTEM_PREFIX},
            {"role": "user", "content": prompt},
        ],
        temperature=0.35,
        response_format={"type": "json_object"},
    )
    raw = resp.choices[0].message.content or "{}"
    data = json.loads(raw)
    mc_raw = data.get("multiple_choice") or []
    sa_raw = data.get("short_answer") or []
    mc_out: list[dict[str, Any]] = []
    for item in mc_raw[:num_mc]:
        if not isinstance(item, dict):
            continue
        opts = item.get("options") or []
        if len(opts) < 2:
            continue
        idx = int(item.get("correct_index", 0))
        idx = max(0, min(idx, len(opts) - 1))
        mc_out.append(
            {
                "id": str(uuid.uuid4()),
                "type": "multiple_choice",
                "question": str(item.get("question", "")).strip(),
                "options": [str(o) for o in opts],
                "correct_index": idx,
            }
        )
    sa_out: list[dict[str, Any]] = []
    for item in sa_raw[:num_sa]:
        if not isinstance(item, dict):
            continue
        q = str(item.get("question", "")).strip()
        ma = str(item.get("model_answer", "")).strip()
        if q and ma:
            sa_out.append(
                {
                    "id": str(uuid.uuid4()),
                    "type": "short_answer",
                    "question": q,
                    "model_answer": ma,
                }
            )
    return mc_out, sa_out


async def grade_short_answer(question: str, model_answer: str, user_answer: str) -> tuple[bool, str]:
    client, model = _openai()
    prompt = f"""You grade a student's short answer for a mock test.

Question: {question}
Ideal answer (from materials): {model_answer}
Student answer: {user_answer}

Return ONLY JSON: {{"correct": true or false, "brief_feedback": "one short sentence"}}
Be fair: accept paraphrases that show understanding. Reject empty or irrelevant answers."""
    resp = await client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        response_format={"type": "json_object"},
    )
    raw = resp.choices[0].message.content or "{}"
    data = json.loads(raw)
    ok = bool(data.get("correct"))
    fb = str(data.get("brief_feedback", "")).strip()
    return ok, fb


_IMAGE_TRANSCRIBE_SYSTEM = (
    "You transcribe study images: printed text, slides, screenshots, and handwriting. "
    "Output only the transcribed text. Do not summarize, explain, or add commentary."
)

_IMAGE_TRANSCRIBE_PROMPT = """Transcribe every word and symbol you can read in this image.

Rules:
- Preserve line breaks and simple paragraph breaks where they matter for readability.
- If something is unreadable, write [illegible] for that fragment only.
- If there is no text at all, reply with exactly: (no text detected)
- Do not describe the image. Do not translate unless the user language is mixed; keep original language."""


def _image_bytes_to_data_url_jpeg(raw: bytes) -> str:
    """Normalize image bytes to a JPEG data URL for the Vision API."""
    if len(raw) > 32 * 1024 * 1024:
        raise ValueError("Image file is too large (max ~32 MB). Try a smaller or cropped photo.")

    img = Image.open(BytesIO(raw))
    img.seek(0)

    if img.mode in ("RGBA", "LA"):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        alpha = img.split()[-1]
        bg.paste(img, mask=alpha)
        img = bg
    elif img.mode == "P":
        t = img.info.get("transparency")
        if t is not None:
            img = img.convert("RGBA")
            bg = Image.new("RGB", img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[-1])
            img = bg
        else:
            img = img.convert("RGB")
    elif img.mode != "RGB":
        img = img.convert("RGB")

    max_side = 2048
    w, h = img.size
    if w > 0 and h > 0 and max(w, h) > max_side:
        scale = max_side / max(w, h)
        img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.LANCZOS)

    buf = BytesIO()
    img.save(buf, format="JPEG", quality=88, optimize=True)
    b64 = base64.standard_b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


def _image_to_data_url_jpeg(path: Path) -> str:
    """Resize very large photos and normalize to JPEG for the Vision API."""
    return _image_bytes_to_data_url_jpeg(path.read_bytes())


async def _transcribe_image_data_url(data_url: str) -> str:
    """Single vision call: image data URL → transcribed text."""
    client, _ = _openai()
    vision_model = get_openai_vision_model()
    resp = await client.chat.completions.create(
        model=vision_model,
        messages=[
            {"role": "system", "content": _IMAGE_TRANSCRIBE_SYSTEM},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": _IMAGE_TRANSCRIBE_PROMPT},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            },
        ],
        temperature=0.1,
        max_tokens=4096,
    )
    text = (resp.choices[0].message.content or "").strip()
    if not text or text == "(no text detected)":
        return "[No text detected in image]"
    return text


async def transcribe_image_bytes(image_bytes: bytes) -> str:
    """Transcribe a single image given raw bytes (e.g. rendered PDF page)."""
    try:
        data_url = _image_bytes_to_data_url_jpeg(image_bytes)
    except (OSError, ValueError, Image.UnidentifiedImageError) as e:
        if isinstance(e, ValueError):
            raise
        raise ValueError("Could not read image bytes.") from e
    return await _transcribe_image_data_url(data_url)


async def transcribe_image_file(path: Path) -> str:
    """Extract text from an image file (printed or handwriting) via OpenAI vision."""
    try:
        data_url = _image_to_data_url_jpeg(path)
    except (OSError, ValueError, Image.UnidentifiedImageError) as e:
        if isinstance(e, ValueError):
            raise
        raise ValueError("Could not read this file as an image.") from e
    return await _transcribe_image_data_url(data_url)


async def transcribe_pdf_pages_vision(path: Path, max_pages: int = 25) -> str:
    """
    Rasterize PDF pages and transcribe each with the same vision model as images.
    Used when embedded PDF text extraction yields too little text (scanned / handwriting).
    """
    try:
        import fitz  # PyMuPDF
    except ImportError as e:
        raise RuntimeError("PyMuPDF is required for PDF vision fallback.") from e

    try:
        doc = fitz.open(path)
    except Exception as e:
        raise ValueError(f"Could not open PDF: {e}") from e

    try:
        n = len(doc)
        if n == 0:
            return ""
        limit = min(n, max_pages)
        parts: list[str] = []
        # ~144 dpi for readable handwriting; keeps images reasonable after JPEG resize
        matrix = fitz.Matrix(2.0, 2.0)
        for i in range(limit):
            page = doc[i]
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            png_bytes = pix.tobytes("png")
            page_text = await transcribe_image_bytes(png_bytes)
            if page_text and page_text != "[No text detected in image]":
                parts.append(f"--- Page {i + 1} ---\n{page_text}")
        out = "\n\n".join(parts).strip()
        if n > max_pages and out:
            out += f"\n\n[Note: Only the first {max_pages} of {n} pages were transcribed with vision.]"
        return out
    finally:
        doc.close()
