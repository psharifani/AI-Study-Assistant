const API = "/api";

export type DocumentSummary = {
  id: number;
  filename: string;
  created_at: string | null;
  content_preview: string;
};

export type Flashcard = {
  id: number;
  document_id: number;
  front: string;
  back: string;
  sort_order: number;
};

export type ChatMessage = {
  id: number;
  role: string;
  content: string;
  created_at?: string | null;
};

export type QuizQuestionMC = {
  id: string;
  type: "multiple_choice";
  question: string;
  options: string[];
  correct_index: number;
};

export type QuizQuestionSA = {
  id: string;
  type: "short_answer";
  question: string;
  model_answer: string;
};

export type QuizQuestion = QuizQuestionMC | QuizQuestionSA;

export type QuizResultItem = {
  question_id: string;
  question_type: string;
  question_text: string;
  user_answer: string;
  correct: boolean;
  correct_answer: string;
  explanation?: string | null;
};

export type QuizResult = {
  score_percent: number;
  correct_count: number;
  total_count: number;
  items: QuizResultItem[];
};

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const t = await res.text();
    throw new Error(t || res.statusText);
  }
  return res.json() as Promise<T>;
}

export async function fetchDocuments(): Promise<DocumentSummary[]> {
  return handle(await fetch(`${API}/documents`));
}

export async function uploadDocument(file: File): Promise<DocumentSummary> {
  const fd = new FormData();
  fd.append("file", file);
  return handle(
    await fetch(`${API}/documents`, { method: "POST", body: fd })
  );
}

export async function deleteDocument(id: number): Promise<void> {
  const res = await fetch(`${API}/documents/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error(await res.text());
}

export async function fetchFlashcards(docId: number): Promise<Flashcard[]> {
  return handle(await fetch(`${API}/documents/${docId}/flashcards`));
}

export async function generateFlashcards(docId: number): Promise<Flashcard[]> {
  return handle(
    await fetch(`${API}/documents/${docId}/flashcards/generate`, {
      method: "POST",
    })
  );
}

export async function createFlashcard(
  docId: number,
  front: string,
  back: string
): Promise<Flashcard> {
  return handle(
    await fetch(`${API}/documents/${docId}/flashcards`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ front, back }),
    })
  );
}

export async function updateFlashcard(
  docId: number,
  fcId: number,
  patch: { front?: string; back?: string }
): Promise<Flashcard> {
  return handle(
    await fetch(`${API}/documents/${docId}/flashcards/${fcId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    })
  );
}

export async function deleteFlashcard(docId: number, fcId: number): Promise<void> {
  const res = await fetch(`${API}/documents/${docId}/flashcards/${fcId}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error(await res.text());
}

export async function fetchChat(docId: number): Promise<ChatMessage[]> {
  return handle(await fetch(`${API}/documents/${docId}/chat`));
}

export async function sendChat(docId: number, message: string): Promise<ChatMessage> {
  return handle(
    await fetch(`${API}/documents/${docId}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    })
  );
}

export async function generateQuiz(
  docId: number,
  numMc: number,
  numSa: number
): Promise<{ questions: QuizQuestion[] }> {
  return handle(
    await fetch(`${API}/documents/${docId}/quiz/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        num_multiple_choice: numMc,
        num_short_answer: numSa,
      }),
    })
  );
}

export async function gradeQuiz(
  docId: number,
  questions: QuizQuestion[],
  answers: { question_id: string; question_type: "multiple_choice" | "short_answer"; user_answer: string | number }[]
): Promise<QuizResult> {
  return handle(
    await fetch(`${API}/documents/${docId}/quiz/grade`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ questions, answers }),
    })
  );
}
