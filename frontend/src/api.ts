const API = "/api";

export type DeckSummary = {
  id: number;
  name: string;
  filename: string;
  created_at: string | null;
  content_preview: string;
};

/** @deprecated use DeckSummary */
export type DocumentSummary = DeckSummary;

export type Flashcard = {
  id: number;
  document_id: number;
  front: string;
  back: string;
  sort_order: number;
  created_at?: string | null;
  sm2_ease_factor?: number;
  sm2_interval_days?: number;
  sm2_repetitions?: number;
  sm2_next_review_at?: string | null;
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

export async function fetchDecks(): Promise<DeckSummary[]> {
  return handle(await fetch(`${API}/decks`));
}

export async function createDeck(name: string): Promise<DeckSummary> {
  return handle(
    await fetch(`${API}/decks`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    })
  );
}

/** Create a new deck from an uploaded file (name derived from filename). */
export async function uploadNewDeck(file: File): Promise<DeckSummary> {
  const fd = new FormData();
  fd.append("file", file);
  return handle(await fetch(`${API}/decks/upload`, { method: "POST", body: fd }));
}

/** Replace study material on an existing deck. */
export async function uploadDeckDocument(deckId: number, file: File): Promise<DeckSummary> {
  const fd = new FormData();
  fd.append("file", file);
  return handle(await fetch(`${API}/decks/${deckId}/document`, { method: "POST", body: fd }));
}

export async function deleteDeck(id: number): Promise<void> {
  const res = await fetch(`${API}/decks/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error(await res.text());
}

export async function fetchFlashcards(deckId: number): Promise<Flashcard[]> {
  return handle(await fetch(`${API}/decks/${deckId}/flashcards`));
}

export async function generateFlashcards(deckId: number): Promise<Flashcard[]> {
  return handle(
    await fetch(`${API}/decks/${deckId}/flashcards/generate`, {
      method: "POST",
    })
  );
}

export async function createFlashcard(
  deckId: number,
  front: string,
  back: string
): Promise<Flashcard> {
  return handle(
    await fetch(`${API}/decks/${deckId}/flashcards`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ front, back }),
    })
  );
}

export async function updateFlashcard(
  deckId: number,
  fcId: number,
  patch: { front?: string; back?: string }
): Promise<Flashcard> {
  return handle(
    await fetch(`${API}/decks/${deckId}/flashcards/${fcId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    })
  );
}

export type FlashcardRating = "again" | "hard" | "good" | "easy";

export async function reviewFlashcard(
  deckId: number,
  fcId: number,
  rating: FlashcardRating
): Promise<Flashcard> {
  return handle(
    await fetch(`${API}/decks/${deckId}/flashcards/${fcId}/review`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rating }),
    })
  );
}

export async function deleteFlashcard(deckId: number, fcId: number): Promise<void> {
  const res = await fetch(`${API}/decks/${deckId}/flashcards/${fcId}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error(await res.text());
}

export async function fetchChat(deckId: number): Promise<ChatMessage[]> {
  return handle(await fetch(`${API}/decks/${deckId}/chat`));
}

export async function sendChat(deckId: number, message: string): Promise<ChatMessage> {
  return handle(
    await fetch(`${API}/decks/${deckId}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    })
  );
}

export async function generateQuiz(
  deckId: number,
  numMc: number,
  numSa: number
): Promise<{ questions: QuizQuestion[] }> {
  return handle(
    await fetch(`${API}/decks/${deckId}/quiz/generate`, {
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
  deckId: number,
  questions: QuizQuestion[],
  answers: { question_id: string; question_type: "multiple_choice" | "short_answer"; user_answer: string | number }[]
): Promise<QuizResult> {
  return handle(
    await fetch(`${API}/decks/${deckId}/quiz/grade`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ questions, answers }),
    })
  );
}
