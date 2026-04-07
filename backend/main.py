import shutil
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import UPLOADS_DIR, get_openai_credentials
from database import get_session, init_db
from document_extract import extract_text_from_file
from llm_service import (
    generate_flashcards,
    generate_quiz,
    grade_short_answer,
    learning_chat,
    suggest_chat_session_title,
)
from models import ChatMessage, ChatSession, Document, Flashcard
from sm2 import apply_four_button_review
from schemas import (
    ChatRequest,
    DeckCreate,
    DeckOut,
    FlashcardCreate,
    FlashcardOut,
    FlashcardReviewBody,
    FlashcardUpdate,
    ChatMessageOut,
    ChatSessionOut,
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


def _deck_out(d: Document) -> DeckOut:
    preview = (d.content_text or "")[:280].replace("\n", " ")
    fn = d.filename or ""
    nm = (d.name or "").strip()
    if not nm:
        nm = Path(fn).stem if fn else "Untitled deck"
    if not nm:
        nm = "Untitled deck"
    return DeckOut(
        id=d.id,
        name=nm,
        filename=fn,
        created_at=d.created_at,
        content_preview=preview + ("…" if len(d.content_text or "") > 280 else ""),
    )


@app.get("/api/health")
async def health():
    key, _ = get_openai_credentials()
    return {"ok": True, "openai_configured": bool(key)}


@app.post("/api/decks", response_model=DeckOut)
async def create_deck(body: DeckCreate, session: AsyncSession = Depends(get_session)):
    doc = Document(filename="", stored_path=None, content_text="", name=body.name.strip())
    session.add(doc)
    await session.commit()
    await session.refresh(doc)
    return _deck_out(doc)


@app.post("/api/decks/upload", response_model=DeckOut)
async def upload_new_deck(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
):
    if not file.filename:
        raise HTTPException(400, "Missing filename")
    safe_name = Path(file.filename).name
    stored = UPLOADS_DIR / f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{safe_name}"
    try:
        with stored.open("wb") as f:
            shutil.copyfileobj(file.file, f)
    finally:
        await file.close()

    text = extract_text_from_file(stored, safe_name)
    stem = Path(safe_name).stem or "Deck"
    doc = Document(filename=safe_name, stored_path=str(stored), content_text=text, name=stem)
    session.add(doc)
    await session.commit()
    await session.refresh(doc)
    return _deck_out(doc)


@app.post("/api/decks/{deck_id}/document", response_model=DeckOut)
async def upload_deck_document(
    deck_id: int,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
):
    doc = await session.get(Document, deck_id)
    if not doc:
        raise HTTPException(404, "Deck not found")
    if not file.filename:
        raise HTTPException(400, "Missing filename")
    safe_name = Path(file.filename).name
    if doc.stored_path:
        p = Path(doc.stored_path)
        if p.is_file():
            try:
                p.unlink()
            except OSError:
                pass
    stored = UPLOADS_DIR / f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{safe_name}"
    try:
        with stored.open("wb") as f:
            shutil.copyfileobj(file.file, f)
    finally:
        await file.close()

    text = extract_text_from_file(stored, safe_name)
    doc.filename = safe_name
    doc.stored_path = str(stored)
    doc.content_text = text
    stem = Path(safe_name).stem
    if not (doc.name or "").strip():
        doc.name = stem
    await session.commit()
    await session.refresh(doc)
    return _deck_out(doc)


@app.get("/api/decks", response_model=list[DeckOut])
async def list_decks(session: AsyncSession = Depends(get_session)):
    r = await session.execute(select(Document).order_by(Document.created_at.desc()))
    return [_deck_out(d) for d in r.scalars().all()]


@app.get("/api/decks/{deck_id}", response_model=DeckOut)
async def get_deck(deck_id: int, session: AsyncSession = Depends(get_session)):
    doc = await session.get(Document, deck_id)
    if not doc:
        raise HTTPException(404, "Deck not found")
    return _deck_out(doc)


@app.delete("/api/decks/{deck_id}")
async def delete_deck(deck_id: int, session: AsyncSession = Depends(get_session)):
    doc = await session.get(Document, deck_id)
    if not doc:
        raise HTTPException(404, "Deck not found")
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


@app.get("/api/decks/{deck_id}/flashcards", response_model=list[FlashcardOut])
async def list_flashcards(deck_id: int, session: AsyncSession = Depends(get_session)):
    doc = await session.get(Document, deck_id)
    if not doc:
        raise HTTPException(404, "Deck not found")
    r = await session.execute(
        select(Flashcard).where(Flashcard.document_id == deck_id).order_by(Flashcard.sort_order, Flashcard.id)
    )
    return list(r.scalars().all())


@app.post("/api/decks/{deck_id}/flashcards/generate", response_model=list[FlashcardOut])
async def generate_flashcards_route(deck_id: int, session: AsyncSession = Depends(get_session)):
    doc = await session.get(Document, deck_id)
    if not doc:
        raise HTTPException(404, "Deck not found")
    if not doc.content_text.strip():
        raise HTTPException(400, "Deck has no study material — upload a document first")
    try:
        cards = await generate_flashcards(doc.content_text)
    except RuntimeError as e:
        raise HTTPException(503, str(e)) from e
    except Exception as e:
        raise HTTPException(502, f"Generation failed: {e}") from e

    r = await session.execute(select(Flashcard).where(Flashcard.document_id == deck_id))
    existing = list(r.scalars().all())
    base_order = max((f.sort_order for f in existing), default=-1) + 1
    for i, c in enumerate(cards):
        session.add(
            Flashcard(
                document_id=deck_id,
                front=c["front"],
                back=c["back"],
                sort_order=base_order + i,
            )
        )
    await session.commit()
    r2 = await session.execute(
        select(Flashcard).where(Flashcard.document_id == deck_id).order_by(Flashcard.sort_order, Flashcard.id)
    )
    return list(r2.scalars().all())


@app.post("/api/decks/{deck_id}/flashcards", response_model=FlashcardOut)
async def create_flashcard(
    deck_id: int, body: FlashcardCreate, session: AsyncSession = Depends(get_session)
):
    doc = await session.get(Document, deck_id)
    if not doc:
        raise HTTPException(404, "Deck not found")
    r = await session.execute(select(Flashcard).where(Flashcard.document_id == deck_id))
    rows = list(r.scalars().all())
    order = max((f.sort_order for f in rows), default=-1) + 1
    fc = Flashcard(document_id=deck_id, front=body.front, back=body.back, sort_order=order)
    session.add(fc)
    await session.commit()
    await session.refresh(fc)
    return fc


@app.post("/api/decks/{deck_id}/flashcards/{fc_id}/review", response_model=FlashcardOut)
async def review_flashcard(
    deck_id: int,
    fc_id: int,
    body: FlashcardReviewBody,
    session: AsyncSession = Depends(get_session),
):
    fc = await session.get(Flashcard, fc_id)
    if not fc or fc.document_id != deck_id:
        raise HTTPException(404, "Flashcard not found")
    try:
        state, next_at = apply_four_button_review(
            body.rating,
            fc.sm2_ease_factor,
            fc.sm2_interval_days,
            fc.sm2_repetitions,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    fc.sm2_ease_factor = state.ease_factor
    fc.sm2_interval_days = state.interval_days
    fc.sm2_repetitions = state.repetitions
    fc.sm2_next_review_at = next_at
    await session.commit()
    await session.refresh(fc)
    return fc


@app.put("/api/decks/{deck_id}/flashcards/{fc_id}", response_model=FlashcardOut)
async def update_flashcard(
    deck_id: int,
    fc_id: int,
    body: FlashcardUpdate,
    session: AsyncSession = Depends(get_session),
):
    fc = await session.get(Flashcard, fc_id)
    if not fc or fc.document_id != deck_id:
        raise HTTPException(404, "Flashcard not found")
    if body.front is not None:
        fc.front = body.front
    if body.back is not None:
        fc.back = body.back
    await session.commit()
    await session.refresh(fc)
    return fc


@app.delete("/api/decks/{deck_id}/flashcards/{fc_id}")
async def delete_flashcard(deck_id: int, fc_id: int, session: AsyncSession = Depends(get_session)):
    fc = await session.get(Flashcard, fc_id)
    if not fc or fc.document_id != deck_id:
        raise HTTPException(404, "Flashcard not found")
    await session.delete(fc)
    await session.commit()
    return {"deleted": True}


@app.get("/api/decks/{deck_id}/chat/sessions", response_model=list[ChatSessionOut])
async def list_chat_sessions(deck_id: int, session: AsyncSession = Depends(get_session)):
    doc = await session.get(Document, deck_id)
    if not doc:
        raise HTTPException(404, "Deck not found")
    r = await session.execute(
        select(ChatSession)
        .where(ChatSession.document_id == deck_id)
        .order_by(ChatSession.updated_at.desc())
    )
    return list(r.scalars().all())


@app.post("/api/decks/{deck_id}/chat/sessions", response_model=ChatSessionOut)
async def create_chat_session(deck_id: int, session: AsyncSession = Depends(get_session)):
    doc = await session.get(Document, deck_id)
    if not doc:
        raise HTTPException(404, "Deck not found")
    now = datetime.now(timezone.utc)
    cs = ChatSession(document_id=deck_id, title="New chat", created_at=now, updated_at=now)
    session.add(cs)
    await session.commit()
    await session.refresh(cs)
    return cs


@app.get(
    "/api/decks/{deck_id}/chat/sessions/{session_id}/messages",
    response_model=list[ChatMessageOut],
)
async def get_chat_messages(
    deck_id: int, session_id: int, session: AsyncSession = Depends(get_session)
):
    cs = await session.get(ChatSession, session_id)
    if not cs or cs.document_id != deck_id:
        raise HTTPException(404, "Chat session not found")
    r = await session.execute(
        select(ChatMessage).where(ChatMessage.session_id == session_id).order_by(ChatMessage.created_at)
    )
    return list(r.scalars().all())


@app.post(
    "/api/decks/{deck_id}/chat/sessions/{session_id}/messages",
    response_model=ChatMessageOut,
)
async def post_chat_message(
    deck_id: int, session_id: int, body: ChatRequest, session: AsyncSession = Depends(get_session)
):
    doc = await session.get(Document, deck_id)
    if not doc:
        raise HTTPException(404, "Deck not found")

    cs = await session.get(ChatSession, session_id)
    if not cs or cs.document_id != deck_id:
        raise HTTPException(404, "Chat session not found")

    user_msg = ChatMessage(session_id=session_id, document_id=deck_id, role="user", content=body.message)
    session.add(user_msg)
    await session.commit()

    r = await session.execute(
        select(ChatMessage).where(ChatMessage.session_id == session_id).order_by(ChatMessage.created_at)
    )
    history_rows = list(r.scalars().all())
    history = [{"role": m.role, "content": m.content} for m in history_rows[:-1]]

    try:
        reply = await learning_chat(doc.content_text or "", history, body.message)
    except RuntimeError as e:
        raise HTTPException(503, str(e)) from e
    except Exception as e:
        raise HTTPException(502, str(e)) from e

    now = datetime.now(timezone.utc)
    cs.updated_at = now
    if not cs.title or cs.title.strip() == "New chat":
        try:
            cs.title = await suggest_chat_session_title(body.message, reply)
        except Exception:
            preview = body.message.strip().replace("\n", " ")
            cs.title = (preview[:80] + "…") if len(preview) > 80 else preview or "Chat"

    asst = ChatMessage(session_id=session_id, document_id=deck_id, role="assistant", content=reply)
    session.add(asst)
    await session.commit()
    await session.refresh(asst)
    return asst


@app.post("/api/decks/{deck_id}/quiz/generate")
async def quiz_generate(deck_id: int, body: QuizGenerateRequest, session: AsyncSession = Depends(get_session)):
    doc = await session.get(Document, deck_id)
    if not doc:
        raise HTTPException(404, "Deck not found")
    if not doc.content_text.strip():
        raise HTTPException(400, "Deck has no study material — upload a document first")
    try:
        mc, sa = await generate_quiz(doc.content_text, body.num_multiple_choice, body.num_short_answer)
    except RuntimeError as e:
        raise HTTPException(503, str(e)) from e
    except Exception as e:
        raise HTTPException(502, str(e)) from e

    questions = mc + sa
    return {"questions": questions}


@app.post("/api/decks/{deck_id}/quiz/grade", response_model=QuizResult)
async def quiz_grade(deck_id: int, body: QuizGradeRequest, session: AsyncSession = Depends(get_session)):
    doc = await session.get(Document, deck_id)
    if not doc:
        raise HTTPException(404, "Deck not found")

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
