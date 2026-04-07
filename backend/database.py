from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from config import DATABASE_URL, DATA_DIR, UPLOADS_DIR


class Base(DeclarativeBase):
    pass


engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def _migrate_flashcards_sm2_sync(connection) -> None:
    r = connection.execute(text("PRAGMA table_info(flashcards)"))
    cols = {row[1] for row in r.fetchall()}
    if "sm2_ease_factor" not in cols:
        connection.execute(text("ALTER TABLE flashcards ADD COLUMN sm2_ease_factor REAL DEFAULT 2.5"))
    if "sm2_interval_days" not in cols:
        connection.execute(text("ALTER TABLE flashcards ADD COLUMN sm2_interval_days REAL DEFAULT 0"))
    if "sm2_repetitions" not in cols:
        connection.execute(text("ALTER TABLE flashcards ADD COLUMN sm2_repetitions INTEGER DEFAULT 0"))
    if "sm2_next_review_at" not in cols:
        connection.execute(text("ALTER TABLE flashcards ADD COLUMN sm2_next_review_at TIMESTAMP"))


def _migrate_documents_name_sync(connection) -> None:
    r = connection.execute(text("PRAGMA table_info(documents)"))
    cols = {row[1] for row in r.fetchall()}
    if "name" not in cols:
        connection.execute(text("ALTER TABLE documents ADD COLUMN name VARCHAR(200)"))
        connection.execute(text("UPDATE documents SET name = filename WHERE name IS NULL OR TRIM(COALESCE(name,'')) = ''"))


def _migrate_chat_sessions_sync(connection) -> None:
    """Legacy: chat_messages keyed by document_id → chat_sessions + session_id."""
    r = connection.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='chat_sessions'"))
    if not r.fetchone():
        connection.execute(
            text(
                """
                CREATE TABLE chat_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                    title VARCHAR(200),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )

    r = connection.execute(text("PRAGMA table_info(chat_messages)"))
    cols = {row[1] for row in r.fetchall()}
    if "session_id" not in cols:
        connection.execute(
            text("ALTER TABLE chat_messages ADD COLUMN session_id INTEGER REFERENCES chat_sessions(id) ON DELETE CASCADE")
        )
        r = connection.execute(text("PRAGMA table_info(chat_messages)"))
        cols = {row[1] for row in r.fetchall()}

    doc_ids = []
    if "document_id" in cols:
        r = connection.execute(text("SELECT DISTINCT document_id FROM chat_messages WHERE session_id IS NULL"))
        doc_ids = [row[0] for row in r.fetchall()]
    for doc_id in doc_ids:
        connection.execute(
            text(
                "INSERT INTO chat_sessions (document_id, title, created_at, updated_at) "
                "VALUES (:doc_id, :title, datetime('now'), datetime('now'))"
            ),
            {"doc_id": doc_id, "title": "Chat"},
        )
        sid_row = connection.execute(text("SELECT last_insert_rowid()")).fetchone()
        sid = sid_row[0] if sid_row else None
        if sid is not None:
            connection.execute(
                text("UPDATE chat_messages SET session_id = :sid WHERE document_id = :d AND session_id IS NULL"),
                {"sid": sid, "d": doc_id},
            )

    r = connection.execute(text("PRAGMA table_info(chat_messages)"))
    cols = {row[1] for row in r.fetchall()}
    if "document_id" in cols and "session_id" in cols:
        try:
            connection.execute(text("ALTER TABLE chat_messages DROP COLUMN document_id"))
        except Exception:
            pass


def _migrate_chat_messages_document_id_sync(connection) -> None:
    """If chat_messages has session_id but no document_id (stricter migration), backfill from chat_sessions."""
    r = connection.execute(text("PRAGMA table_info(chat_messages)"))
    cols = {row[1] for row in r.fetchall()}
    if "document_id" in cols:
        return
    connection.execute(
        text("ALTER TABLE chat_messages ADD COLUMN document_id INTEGER REFERENCES documents(id) ON DELETE CASCADE")
    )
    connection.execute(
        text("""
        UPDATE chat_messages SET document_id = (
            SELECT cs.document_id FROM chat_sessions cs WHERE cs.id = chat_messages.session_id
        )
        WHERE document_id IS NULL
        """)
    )


async def init_db():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_migrate_flashcards_sm2_sync)
        await conn.run_sync(_migrate_documents_name_sync)
        await conn.run_sync(_migrate_chat_sessions_sync)
        await conn.run_sync(_migrate_chat_messages_document_id_sync)


async def get_session():
    async with AsyncSessionLocal() as session:
        yield session
