from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class DocumentOut(BaseModel):
    id: int
    filename: str
    created_at: datetime | None = None
    content_preview: str = ""

    class Config:
        from_attributes = True


class FlashcardOut(BaseModel):
    id: int
    document_id: int
    front: str
    back: str
    sort_order: int

    class Config:
        from_attributes = True


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
