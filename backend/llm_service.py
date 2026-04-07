import json
import re
import uuid
from typing import Any

from openai import AsyncOpenAI

from config import get_openai_credentials

STUDY_SYSTEM_PREFIX = """You are a study assistant for higher-education learners (psychology, political science, history, and similar).
Your answers must be grounded ONLY in the STUDY DOCUMENT provided by the user in this conversation.
If the document does not contain enough information to answer, say so and suggest what topic might be missing.
Do not invent facts, citations, or sources not supported by the document.
Use clear, student-friendly language while remaining accurate to the document."""


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


async def chat_about_document(document_text: str, history: list[dict[str, str]], user_message: str) -> str:
    client, model = _openai()
    doc_block = f"STUDY DOCUMENT (ground truth; do not contradict):\n---\n{document_text[:120_000]}\n---"
    messages: list[dict[str, str]] = [
        {"role": "system", "content": STUDY_SYSTEM_PREFIX + "\n\n" + doc_block},
    ]
    for h in history[-20:]:
        messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": user_message})
    resp = await client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.5,
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
