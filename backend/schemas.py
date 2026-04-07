from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class DeckOut(BaseModel):
    id: int
    name: str
    filename: str
    created_at: datetime | None = None
    content_preview: str = ""
    has_study_material: bool = False

    class Config:
        from_attributes = True


class DeckCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)


# Alias for older code paths
DocumentOut = DeckOut


class FlashcardOut(BaseModel):
    id: int
    document_id: int
    front: str
    back: str
    sort_order: int
    created_at: datetime | None = None
    sm2_ease_factor: float = 2.5
    sm2_interval_days: float = 0.0
    sm2_repetitions: int = 0
    sm2_next_review_at: datetime | None = None
    source_document_name: str | None = None

    class Config:
        from_attributes = True


class FlashcardReviewBody(BaseModel):
    rating: Literal["again", "hard", "good", "easy"] = Field(
        ...,
        description="again=10m reschedule; hard/good/easy map to SM-2 qualities 3/4/5",
    )


class FlashcardCreate(BaseModel):
    front: str = Field(..., min_length=1)
    back: str = Field(..., min_length=1)


class FlashcardUpdate(BaseModel):
    front: str | None = None
    back: str | None = None


class ChatMessageOut(BaseModel):
    id: int
    role: str
    content: str
    created_at: datetime | None = None

    class Config:
        from_attributes = True


class ChatSessionOut(BaseModel):
    id: int
    document_id: int
    title: str | None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)


class MCQuestion(BaseModel):
    id: str
    type: Literal["multiple_choice"] = "multiple_choice"
    question: str
    options: list[str] = Field(..., min_length=2)
    correct_index: int = Field(..., ge=0)


class SAQuestion(BaseModel):
    id: str
    type: Literal["short_answer"] = "short_answer"
    question: str
    model_answer: str


class QuizGenerateRequest(BaseModel):
    num_multiple_choice: int = Field(5, ge=1, le=20)
    num_short_answer: int = Field(3, ge=0, le=10)


class QuizGradeItem(BaseModel):
    question_id: str
    question_type: Literal["multiple_choice", "short_answer"]
    user_answer: str | int


class QuizGradeRequest(BaseModel):
    questions: list[dict]
    answers: list[QuizGradeItem]


class QuizResultItem(BaseModel):
    question_id: str
    question_type: str
    question_text: str
    user_answer: str
    correct: bool
    correct_answer: str
    explanation: str | None = None


class QuizResult(BaseModel):
    score_percent: float
    correct_count: int
    total_count: int
    items: list[QuizResultItem]
