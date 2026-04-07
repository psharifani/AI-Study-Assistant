import shutil
from datetime import datetime
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from config import UPLOADS_DIR, get_openai_credentials
from database import get_session, init_db
from document_extract import extract_text_from_file
from llm_service import chat_about_document, generate_flashcards, generate_quiz, grade_short_answer
from models import ChatMessage, Document, Flashcard
from schemas import (
    ChatRequest,
    DocumentOut,
    FlashcardCreate,
    FlashcardOut,
    FlashcardUpdate,
    ChatMessageOut,
    QuizGenerateRequest,
    QuizGradeItem,
    QuizGradeRequest,
    QuizResult,
    QuizResultItem,
)

app = FastAPI(title="AI Study Assistant API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    await init_db()


def _doc_out(d: Document) -> DocumentOut:
    preview = (d.content_text or "")[:280].replace("\n", " ")
    return DocumentOut(
        id=d.id,
        filename=d.filename,
        created_at=d.created_at,
        content_preview=preview + ("…" if len(d.content_text or "") > 280 else ""),
    )


@app.get("/api/health")
async def health():
    key, _ = get_openai_credentials()
    return {"ok": True, "openai_configured": bool(key)}


@app.post("/api/documents", response_model=DocumentOut)
async def upload_document(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
):
    if not file.filename:
        raise HTTPException(400, "Missing filename")
    safe_name = Path(file.filename).name
    suffix = Path(safe_name).suffix or ".txt"
    stored = UPLOADS_DIR / f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{safe_name}"
    try:
        with stored.open("wb") as f:
            shutil.copyfileobj(file.file, f)
    finally:
        await file.close()

    text = extract_text_from_file(stored, safe_name)
    doc = Document(filename=safe_name, stored_path=str(stored), content_text=text)
    session.add(doc)
    await session.commit()
    await session.refresh(doc)
    return _doc_out(doc)


@app.get("/api/documents", response_model=list[DocumentOut])
async def list_documents(session: AsyncSession = Depends(get_session)):
    r = await session.execute(select(Document).order_by(Document.created_at.desc()))
    return [_doc_out(d) for d in r.scalars().all()]


@app.get("/api/documents/{doc_id}", response_model=DocumentOut)
async def get_document(doc_id: int, session: AsyncSession = Depends(get_session)):
    doc = await session.get(Document, doc_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    return _doc_out(doc)


@app.delete("/api/documents/{doc_id}")
async def delete_document(doc_id: int, session: AsyncSession = Depends(get_session)):
    doc = await session.get(Document, doc_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    if doc.stored_path:
        p = Path(doc.stored_path)
        if p.is_file():
            try:
                p.unlink()
            except OSError:
                pass
    await session.delete(doc)
    await session.commit()
    return {"deleted": True}


@app.get("/api/documents/{doc_id}/flashcards", response_model=list[FlashcardOut])
async def list_flashcards(doc_id: int, session: AsyncSession = Depends(get_session)):
    doc = await session.get(Document, doc_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    r = await session.execute(
        select(Flashcard).where(Flashcard.document_id == doc_id).order_by(Flashcard.sort_order, Flashcard.id)
    )
    return list(r.scalars().all())


@app.post("/api/documents/{doc_id}/flashcards/generate", response_model=list[FlashcardOut])
async def generate_flashcards_route(doc_id: int, session: AsyncSession = Depends(get_session)):
    doc = await session.get(Document, doc_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    if not doc.content_text.strip():
        raise HTTPException(400, "Document has no extractable text")
    try:
        cards = await generate_flashcards(doc.content_text)
    except RuntimeError as e:
        raise HTTPException(503, str(e)) from e
    except Exception as e:
        raise HTTPException(502, f"Generation failed: {e}") from e

    r = await session.execute(select(Flashcard).where(Flashcard.document_id == doc_id))
    existing = list(r.scalars().all())
    base_order = max((f.sort_order for f in existing), default=-1) + 1
    for i, c in enumerate(cards):
        session.add(
            Flashcard(
                document_id=doc_id,
                front=c["front"],
                back=c["back"],
                sort_order=base_order + i,
            )
        )
    await session.commit()
    r2 = await session.execute(
        select(Flashcard).where(Flashcard.document_id == doc_id).order_by(Flashcard.sort_order, Flashcard.id)
    )
    return list(r2.scalars().all())


@app.post("/api/documents/{doc_id}/flashcards", response_model=FlashcardOut)
async def create_flashcard(
    doc_id: int, body: FlashcardCreate, session: AsyncSession = Depends(get_session)
):
    doc = await session.get(Document, doc_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    r = await session.execute(select(Flashcard).where(Flashcard.document_id == doc_id))
    rows = list(r.scalars().all())
    order = max((f.sort_order for f in rows), default=-1) + 1
    fc = Flashcard(document_id=doc_id, front=body.front, back=body.back, sort_order=order)
    session.add(fc)
    await session.commit()
    await session.refresh(fc)
    return fc


@app.put("/api/documents/{doc_id}/flashcards/{fc_id}", response_model=FlashcardOut)
async def update_flashcard(
    doc_id: int,
    fc_id: int,
    body: FlashcardUpdate,
    session: AsyncSession = Depends(get_session),
):
    fc = await session.get(Flashcard, fc_id)
    if not fc or fc.document_id != doc_id:
        raise HTTPException(404, "Flashcard not found")
    if body.front is not None:
        fc.front = body.front
    if body.back is not None:
        fc.back = body.back
    await session.commit()
    await session.refresh(fc)
    return fc


@app.delete("/api/documents/{doc_id}/flashcards/{fc_id}")
async def delete_flashcard(doc_id: int, fc_id: int, session: AsyncSession = Depends(get_session)):
    fc = await session.get(Flashcard, fc_id)
    if not fc or fc.document_id != doc_id:
        raise HTTPException(404, "Flashcard not found")
    await session.delete(fc)
    await session.commit()
    return {"deleted": True}


@app.get("/api/documents/{doc_id}/chat", response_model=list[ChatMessageOut])
async def get_chat_history(doc_id: int, session: AsyncSession = Depends(get_session)):
    doc = await session.get(Document, doc_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    r = await session.execute(
        select(ChatMessage).where(ChatMessage.document_id == doc_id).order_by(ChatMessage.created_at)
    )
    return list(r.scalars().all())


@app.post("/api/documents/{doc_id}/chat", response_model=ChatMessageOut)
async def post_chat(doc_id: int, body: ChatRequest, session: AsyncSession = Depends(get_session)):
    doc = await session.get(Document, doc_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    if not doc.content_text.strip():
        raise HTTPException(400, "Document has no extractable text")

    user_msg = ChatMessage(document_id=doc_id, role="user", content=body.message)
    session.add(user_msg)
    await session.commit()

    r = await session.execute(
        select(ChatMessage).where(ChatMessage.document_id == doc_id).order_by(ChatMessage.created_at)
    )
    history_rows = list(r.scalars().all())
    history = [{"role": m.role, "content": m.content} for m in history_rows[:-1]]

    try:
        reply = await chat_about_document(doc.content_text, history, body.message)
    except RuntimeError as e:
        raise HTTPException(503, str(e)) from e
    except Exception as e:
        raise HTTPException(502, str(e)) from e

    asst = ChatMessage(document_id=doc_id, role="assistant", content=reply)
    session.add(asst)
    await session.commit()
    await session.refresh(asst)
    return asst


@app.post("/api/documents/{doc_id}/quiz/generate")
async def quiz_generate(doc_id: int, body: QuizGenerateRequest, session: AsyncSession = Depends(get_session)):
    doc = await session.get(Document, doc_id)
    if not doc:
        raise HTTPException(404, "Document not found")
    if not doc.content_text.strip():
        raise HTTPException(400, "Document has no extractable text")
    try:
        mc, sa = await generate_quiz(doc.content_text, body.num_multiple_choice, body.num_short_answer)
    except RuntimeError as e:
        raise HTTPException(503, str(e)) from e
    except Exception as e:
        raise HTTPException(502, str(e)) from e

    # Full payload for grading: client echoes `questions` when submitting. UI should not reveal
    # correct_index or model_answer until after results (personal study tool).
    questions = mc + sa
    return {"questions": questions}


@app.post("/api/documents/{doc_id}/quiz/grade", response_model=QuizResult)
async def quiz_grade(doc_id: int, body: QuizGradeRequest, session: AsyncSession = Depends(get_session)):
    doc = await session.get(Document, doc_id)
    if not doc:
        raise HTTPException(404, "Document not found")

    mc_by_id = {}
    sa_by_id = {}
    qtext = {}
    for q in body.questions:
        if not isinstance(q, dict):
            continue
        qid = str(q.get("id", ""))
        qtype = q.get("type")
        qtext[qid] = str(q.get("question", ""))
        if qtype == "multiple_choice":
            mc_by_id[qid] = q
        elif qtype == "short_answer":
            sa_by_id[qid] = q

    items: list[QuizResultItem] = []
    correct_n = 0
    total = len(body.answers)

    for ans in body.answers:
        qid = ans.question_id
        qt = ans.question_type
        if qt == "multiple_choice":
            q = mc_by_id.get(qid)
            if not q:
                items.append(
                    QuizResultItem(
                        question_id=qid,
                        question_type=qt,
                        question_text=qtext.get(qid, ""),
                        user_answer=str(ans.user_answer),
                        correct=False,
                        correct_answer="",
                        explanation="Question not found in submission.",
                    )
                )
                continue
            opts = q.get("options") or []
            correct_idx = int(q.get("correct_index", 0))
            correct_idx = max(0, min(correct_idx, len(opts) - 1 if opts else 0))
            try:
                ua = int(ans.user_answer) if not isinstance(ans.user_answer, int) else ans.user_answer
            except (TypeError, ValueError):
                ua = -1
            ok = ua == correct_idx
            if ok:
                correct_n += 1
            ca = opts[correct_idx] if opts and correct_idx < len(opts) else ""
            items.append(
                QuizResultItem(
                    question_id=qid,
                    question_type=qt,
                    question_text=str(q.get("question", "")),
                    user_answer=str(opts[ua]) if isinstance(ua, int) and 0 <= ua < len(opts) else str(ans.user_answer),
                    correct=ok,
                    correct_answer=ca,
                    explanation=None,
                )
            )
        else:
            q = sa_by_id.get(qid)
            if not q:
                items.append(
                    QuizResultItem(
                        question_id=qid,
                        question_type=qt,
                        question_text=qtext.get(qid, ""),
                        user_answer=str(ans.user_answer),
                        correct=False,
                        correct_answer="",
                        explanation="Question not found in submission.",
                    )
                )
                continue
            model_a = str(q.get("model_answer", ""))
            user_a = str(ans.user_answer or "").strip()
            try:
                ok, fb = await grade_short_answer(str(q.get("question", "")), model_a, user_a)
            except Exception:
                ok, fb = False, "Could not grade this answer."
            if ok:
                correct_n += 1
            items.append(
                QuizResultItem(
                    question_id=qid,
                    question_type=qt,
                    question_text=str(q.get("question", "")),
                    user_answer=user_a,
                    correct=ok,
                    correct_answer=model_a,
                    explanation=fb or None,
                )
            )

    pct = (100.0 * correct_n / total) if total else 0.0
    return QuizResult(score_percent=round(pct, 1), correct_count=correct_n, total_count=total, items=items)
