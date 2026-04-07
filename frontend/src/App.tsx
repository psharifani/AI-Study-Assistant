import { useCallback, useEffect, useState } from "react";
import type { Flashcard as FlashcardT, QuizQuestion, QuizResult } from "./api";
import * as api from "./api";

type Tab = "flashcards" | "chat" | "quiz";

export default function App() {
  const [docs, setDocs] = useState<api.DocumentSummary[]>([]);
  const [docId, setDocId] = useState<number | null>(null);
  const [tab, setTab] = useState<Tab>("flashcards");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refreshDocs = useCallback(async () => {
    try {
      setError(null);
      const list = await api.fetchDocuments();
      setDocs(list);
      setDocId((cur) => {
        if (cur != null && list.some((d) => d.id === cur)) return cur;
        return list[0]?.id ?? null;
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load documents");
    }
  }, []);

  useEffect(() => {
    void refreshDocs();
  }, [refreshDocs]);

  const onUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (!f) return;
    setBusy(true);
    setError(null);
    try {
      const d = await api.uploadDocument(f);
      await refreshDocs();
      setDocId(d.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  };

  const onDeleteDoc = async () => {
    if (!docId) return;
    if (!confirm("Delete this document and all saved flashcards and chat for it?")) return;
    setBusy(true);
    try {
      await api.deleteDocument(docId);
      setDocId(null);
      await refreshDocs();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Delete failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="app-shell">
      <header className="app-header">
        <h1>AI Study Assistant</h1>
        <p>
          Upload lecture notes or readings, then review with flashcards, ask grounded questions, and take a mock test.
        </p>
      </header>

      <div className="doc-bar">
        <label className="upload-btn">
          {busy ? "…" : "Upload document"}
          <input type="file" accept=".pdf,.txt,.md,.markdown" onChange={onUpload} disabled={busy} />
        </label>
        <select
          className="doc-select"
          value={docId ?? ""}
          onChange={(e) => setDocId(e.target.value ? Number(e.target.value) : null)}
        >
          <option value="">Select a document…</option>
          {docs.map((d) => (
            <option key={d.id} value={d.id}>
              {d.filename}
            </option>
          ))}
        </select>
        {docId != null && (
          <button type="button" className="btn btn-danger" onClick={onDeleteDoc} disabled={busy}>
            Delete
          </button>
        )}
      </div>

      {error && <div className="error-banner">{error}</div>}

      {!docId && (
        <div className="panel">
          <p className="empty-hint">Upload a PDF or text file to begin. Content stays on your machine in the app database.</p>
        </div>
      )}

      {docId != null && (
        <>
          <nav className="tabs" aria-label="Study modes">
            <button type="button" className={tab === "flashcards" ? "active" : ""} onClick={() => setTab("flashcards")}>
              Flashcards
            </button>
            <button type="button" className={tab === "chat" ? "active" : ""} onClick={() => setTab("chat")}>
              Learning chat
            </button>
            <button type="button" className={tab === "quiz" ? "active" : ""} onClick={() => setTab("quiz")}>
              Mock test
            </button>
          </nav>

          {tab === "flashcards" && <FlashcardsPanel docId={docId} onError={setError} />}
          {tab === "chat" && <ChatPanel docId={docId} onError={setError} />}
          {tab === "quiz" && <QuizPanel docId={docId} onError={setError} />}
        </>
      )}
    </div>
  );
}

function FlashcardsPanel({
  docId,
  onError,
}: {
  docId: number;
  onError: (s: string | null) => void;
}) {
  const [cards, setCards] = useState<FlashcardT[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState<number | null>(null);
  const [draftFront, setDraftFront] = useState("");
  const [draftBack, setDraftBack] = useState("");
  const [newFront, setNewFront] = useState("");
  const [newBack, setNewBack] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    onError(null);
    try {
      setCards(await api.fetchFlashcards(docId));
    } catch (e) {
      onError(e instanceof Error ? e.message : "Failed to load flashcards");
    } finally {
      setLoading(false);
    }
  }, [docId, onError]);

  useEffect(() => {
    load();
  }, [load]);

  const gen = async () => {
    setBusy(true);
    onError(null);
    try {
      const next = await api.generateFlashcards(docId);
      setCards(next);
    } catch (e) {
      onError(e instanceof Error ? e.message : "Generation failed");
    } finally {
      setBusy(false);
    }
  };

  const startEdit = (c: FlashcardT) => {
    setEditing(c.id);
    setDraftFront(c.front);
    setDraftBack(c.back);
  };

  const saveEdit = async () => {
    if (editing == null) return;
    setBusy(true);
    onError(null);
    try {
      await api.updateFlashcard(docId, editing, { front: draftFront, back: draftBack });
      setEditing(null);
      await load();
    } catch (e) {
      onError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setBusy(false);
    }
  };

  const remove = async (id: number) => {
    if (!confirm("Delete this flashcard?")) return;
    setBusy(true);
    try {
      await api.deleteFlashcard(docId, id);
      await load();
    } catch (e) {
      onError(e instanceof Error ? e.message : "Delete failed");
    } finally {
      setBusy(false);
    }
  };

  const addManual = async () => {
    if (!newFront.trim() || !newBack.trim()) return;
    setBusy(true);
    onError(null);
    try {
      await api.createFlashcard(docId, newFront.trim(), newBack.trim());
      setNewFront("");
      setNewBack("");
      await load();
    } catch (e) {
      onError(e instanceof Error ? e.message : "Add failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="panel">
      <h2>Flashcards</h2>
      <div className="toolbar">
        <button type="button" className="btn btn-primary" onClick={gen} disabled={busy || loading}>
          {busy ? "Generating…" : "Generate from document"}
        </button>
      </div>
      <p className="empty-hint" style={{ marginBottom: "1rem" }}>
        Cards are saved for this document. Edit or add your own anytime.
      </p>

      <div style={{ marginBottom: "1.25rem", padding: "1rem", background: "var(--surface2)", borderRadius: 8 }}>
        <span className="field-label">New flashcard</span>
        <textarea placeholder="Front (question or term)" value={newFront} onChange={(e) => setNewFront(e.target.value)} />
        <textarea placeholder="Back (answer or definition)" value={newBack} onChange={(e) => setNewBack(e.target.value)} />
        <button type="button" className="btn btn-primary" onClick={addManual} disabled={busy}>
          Add card
        </button>
      </div>

      {loading ? (
        <p className="empty-hint">Loading…</p>
      ) : cards.length === 0 ? (
        <p className="empty-hint">No flashcards yet. Generate from your document or add manually.</p>
      ) : (
        <div className="flash-list">
          {cards.map((c) => (
            <div key={c.id} className="flash-card">
              {editing === c.id ? (
                <>
                  <div className="label">Front</div>
                  <textarea value={draftFront} onChange={(e) => setDraftFront(e.target.value)} />
                  <div className="label">Back</div>
                  <textarea value={draftBack} onChange={(e) => setDraftBack(e.target.value)} />
                  <div className="actions">
                    <button type="button" className="btn btn-primary" onClick={saveEdit} disabled={busy}>
                      Save
                    </button>
                    <button type="button" className="btn" onClick={() => setEditing(null)} disabled={busy}>
                      Cancel
                    </button>
                  </div>
                </>
              ) : (
                <>
                  <div className="label">Front</div>
                  <div>{c.front}</div>
                  <div className="label" style={{ marginTop: "0.75rem" }}>
                    Back
                  </div>
                  <div>{c.back}</div>
                  <div className="actions">
                    <button type="button" className="btn" onClick={() => startEdit(c)} disabled={busy}>
                      Edit
                    </button>
                    <button type="button" className="btn btn-danger" onClick={() => remove(c.id)} disabled={busy}>
                      Delete
                    </button>
                  </div>
                </>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ChatPanel({ docId, onError }: { docId: number; onError: (s: string | null) => void }) {
  const [msgs, setMsgs] = useState<api.ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    onError(null);
    try {
      setMsgs(await api.fetchChat(docId));
    } catch (e) {
      onError(e instanceof Error ? e.message : "Failed to load chat");
    } finally {
      setLoading(false);
    }
  }, [docId, onError]);

  useEffect(() => {
    load();
  }, [load]);

  const send = async () => {
    const t = input.trim();
    if (!t || sending) return;
    setSending(true);
    onError(null);
    setInput("");
    try {
      await api.sendChat(docId, t);
      setMsgs(await api.fetchChat(docId));
    } catch (e) {
      onError(e instanceof Error ? e.message : "Message failed");
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="panel">
      <h2>Learning chat</h2>
      <p className="empty-hint" style={{ marginBottom: "1rem" }}>
        Ask for simpler explanations, summaries, definitions, or how theories in your document relate. Replies are limited to your uploaded material.
      </p>
      {loading ? (
        <p className="empty-hint">Loading…</p>
      ) : (
        <>
          <div className="chat-log">
            {msgs.length === 0 && <p className="empty-hint">No messages yet. Ask a question about your document.</p>}
            {msgs.map((m) => (
              <div key={m.id} className={`chat-bubble ${m.role === "user" ? "user" : "assistant"}`}>
                {m.content}
              </div>
            ))}
          </div>
          <div className="chat-input-row">
            <textarea
              placeholder="e.g. Summarize the main argument in simpler terms…"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  send();
                }
              }}
              disabled={sending}
            />
            <button type="button" className="btn btn-primary" onClick={send} disabled={sending || !input.trim()}>
              {sending ? "…" : "Send"}
            </button>
          </div>
        </>
      )}
    </div>
  );
}

function QuizPanel({ docId, onError }: { docId: number; onError: (s: string | null) => void }) {
  const [numMc, setNumMc] = useState(5);
  const [numSa, setNumSa] = useState(2);
  const [questions, setQuestions] = useState<QuizQuestion[] | null>(null);
  const [mcAnswers, setMcAnswers] = useState<Record<string, number>>({});
  const [saAnswers, setSaAnswers] = useState<Record<string, string>>({});
  const [result, setResult] = useState<QuizResult | null>(null);
  const [busy, setBusy] = useState(false);

  const generate = async () => {
    setBusy(true);
    onError(null);
    setResult(null);
    try {
      const { questions: q } = await api.generateQuiz(docId, numMc, numSa);
      setQuestions(q);
      setMcAnswers({});
      setSaAnswers({});
    } catch (e) {
      onError(e instanceof Error ? e.message : "Quiz generation failed");
    } finally {
      setBusy(false);
    }
  };

  const submit = async () => {
    if (!questions?.length) return;
    setBusy(true);
    onError(null);
    try {
      const answers = questions.map((q) => {
        if (q.type === "multiple_choice") {
          const idx = mcAnswers[q.id];
          return {
            question_id: q.id,
            question_type: "multiple_choice" as const,
            user_answer: idx ?? -1,
          };
        }
        return {
          question_id: q.id,
          question_type: "short_answer" as const,
          user_answer: (saAnswers[q.id] ?? "").trim(),
        };
      });
      const r = await api.gradeQuiz(docId, questions, answers);
      setResult(r);
    } catch (e) {
      onError(e instanceof Error ? e.message : "Grading failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="panel">
      <h2>Mock test</h2>
      <p className="empty-hint" style={{ marginBottom: "1rem" }}>
        Multiple-choice and short-answer questions are generated from your document. After you submit, you will see your score and the correct answers.
      </p>

      {!questions && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: "0.75rem", alignItems: "center", marginBottom: "1rem" }}>
          <label className="empty-hint">
            MC questions:{" "}
            <input
              type="number"
              min={1}
              max={20}
              value={numMc}
              onChange={(e) => setNumMc(Number(e.target.value))}
              style={{ width: 64, marginLeft: 6, background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 6, padding: "0.25rem" }}
            />
          </label>
          <label className="empty-hint">
            Short answer:{" "}
            <input
              type="number"
              min={0}
              max={10}
              value={numSa}
              onChange={(e) => setNumSa(Number(e.target.value))}
              style={{ width: 64, marginLeft: 6, background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 6, padding: "0.25rem" }}
            />
          </label>
          <button type="button" className="btn btn-primary" onClick={generate} disabled={busy}>
            {busy ? "…" : "Generate quiz"}
          </button>
        </div>
      )}

      {questions && !result && (
        <>
          <div className="toolbar">
            <button type="button" className="btn" onClick={() => setQuestions(null)} disabled={busy}>
              New quiz
            </button>
            <button type="button" className="btn btn-primary" onClick={submit} disabled={busy}>
              {busy ? "Grading…" : "Submit answers"}
            </button>
          </div>
          {questions.map((q, i) => (
            <div key={q.id} style={{ marginBottom: "1.5rem" }}>
              <strong>
                {i + 1}. {q.question}
              </strong>
              {q.type === "multiple_choice" && (
                <div className="quiz-opts">
                  {q.options.map((opt, j) => (
                    <label key={j}>
                      <input
                        type="radio"
                        name={q.id}
                        checked={mcAnswers[q.id] === j}
                        onChange={() => setMcAnswers((prev) => ({ ...prev, [q.id]: j }))}
                      />
                      <span>{opt}</span>
                    </label>
                  ))}
                </div>
              )}
              {q.type === "short_answer" && (
                <textarea
                  className="quiz-sa"
                  value={saAnswers[q.id] ?? ""}
                  onChange={(e) => setSaAnswers((prev) => ({ ...prev, [q.id]: e.target.value }))}
                  placeholder="Your answer…"
                />
              )}
            </div>
          ))}
        </>
      )}

      {result && (
        <>
          <div className="score-pill">
            Score: {result.score_percent}% ({result.correct_count}/{result.total_count} correct)
          </div>
          <div className="toolbar">
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => {
                setQuestions(null);
                setResult(null);
              }}
            >
              Start another quiz
            </button>
          </div>
          {result.items.map((it) => (
            <div key={it.question_id} className={`result-item ${it.correct ? "ok" : "bad"}`}>
              <div style={{ fontWeight: 600, marginBottom: 6 }}>{it.question_text}</div>
              <div className="empty-hint">Your answer: {it.user_answer || "(empty)"}</div>
              <div style={{ marginTop: 6 }}>
                Correct answer: <span style={{ color: "var(--success)" }}>{it.correct_answer}</span>
              </div>
              {it.explanation && <div className="empty-hint" style={{ marginTop: 6 }}>{it.explanation}</div>}
            </div>
          ))}
        </>
      )}
    </div>
  );
}
