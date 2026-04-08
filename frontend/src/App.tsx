import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Flashcard as FlashcardT, QuizQuestion, QuizResult } from "./api";
import * as api from "./api";
import { formatAddedDate, formatIntervalDays, formatNextRead } from "./flashcardMeta";
import {
  bucketByInterval,
  bucketUpcomingReviews,
  countScheduledBeyondWindow,
  filterCardsWithinUpcomingWindow,
  type ReviewStatsRange,
} from "./flashcardReviewStats";

type Tab = "flashcards" | "chat" | "quiz";

const FLASHCARD_RATINGS: { rating: api.FlashcardRating; label: string; title: string }[] = [
  { rating: "again", label: "Again (10 minutes)", title: "Forgot or very hard — review again in 10 minutes" },
  { rating: "hard", label: "Hard", title: "Recalled with difficulty (SM-2: harder interval)" },
  { rating: "good", label: "Good", title: "Recalled with effort — default schedule" },
  { rating: "easy", label: "Easy", title: "Recalled easily — longer interval" },
];

function buildSm2DueQueue(cards: FlashcardT[]): FlashcardT[] {
  const now = Date.now();
  return cards
    .filter((c) => {
      const t = c.sm2_next_review_at;
      if (t == null || t === "") return true;
      return new Date(t).getTime() <= now;
    })
    .sort((a, b) => {
      const aNew = !a.sm2_next_review_at;
      const bNew = !b.sm2_next_review_at;
      if (aNew && bNew) return a.id - b.id;
      if (aNew) return -1;
      if (bNew) return 1;
      return new Date(a.sm2_next_review_at!).getTime() - new Date(b.sm2_next_review_at!).getTime();
    });
}

function FlashcardMetaLine({ card }: { card: FlashcardT }) {
  return (
    <div className="flashcard-meta">
      <span>
        <strong>ID</strong> {card.id}
      </span>
      <span className="flashcard-meta-sep" aria-hidden>
        ·
      </span>
      <span>
        <strong>Added</strong> {formatAddedDate(card.created_at)}
      </span>
      <span className="flashcard-meta-sep" aria-hidden>
        ·
      </span>
      <span>
        <strong>Interval</strong> {formatIntervalDays(card.sm2_interval_days)}
      </span>
      <span className="flashcard-meta-sep" aria-hidden>
        ·
      </span>
      <span>
        <strong>Next read</strong> {formatNextRead(card.sm2_next_review_at)}
      </span>
    </div>
  );
}

function nextFutureReview(cards: FlashcardT[]): Date | null {
  const now = Date.now();
  const times = cards
    .map((c) => c.sm2_next_review_at)
    .filter((t): t is string => !!t && new Date(t).getTime() > now)
    .map((t) => new Date(t).getTime());
  if (!times.length) return null;
  return new Date(Math.min(...times));
}

function StatsBarChartPanel({
  title,
  hint,
  bars,
  beyond,
  listKey,
  range,
  onRangeChange,
  rangeGroupLabel,
}: {
  title: string;
  hint: string;
  bars: { label: string; count: number }[];
  beyond?: ReactNode;
  listKey: string;
  range: ReviewStatsRange;
  onRangeChange: (r: ReviewStatsRange) => void;
  rangeGroupLabel: string;
}) {
  const max = Math.max(1, ...bars.map((b) => b.count));
  const chartFadeAfterMount = useRef(false);
  useEffect(() => {
    chartFadeAfterMount.current = true;
  }, []);
  return (
    <div className="review-stats-panel review-stats-panel--fadein">
      <div className="review-stats-panel-head">
        <h4 className="review-stats-chart-title">{title}</h4>
        <div className="review-stats-toggle-group" role="group" aria-label={rangeGroupLabel}>
          {(["7d", "30d", "90d"] as const).map((r) => (
            <button key={r} type="button" className={range === r ? "active" : ""} onClick={() => onRangeChange(r)}>
              {r === "7d" ? "7d" : r === "30d" ? "30d" : "90d"}
            </button>
          ))}
        </div>
      </div>
      <p className="review-stats-panel-hint empty-hint">{hint}</p>
      <div className="review-stats-vchart-xscroll">
        <div
          key={listKey}
          className={`review-stats-vchart${chartFadeAfterMount.current ? " review-stats-vchart--fadein" : ""}`}
          role="list"
          aria-label={`${title} bar chart`}
        >
          {bars.map((b) => (
            <div key={b.label} className="review-stats-vcol" role="listitem">
              <span className="review-stats-vcount">{b.count}</span>
              <div className="review-stats-vtrack" aria-hidden>
                <div className="review-stats-vfill" style={{ height: `${(b.count / max) * 100}%` }} />
              </div>
              <div className="review-stats-vlabel-wrap">
                <span className="review-stats-vlabel">{b.label}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
      {beyond}
    </div>
  );
}

function FlashcardReviewStats({ cards }: { cards: FlashcardT[] }) {
  const [upcomingRange, setUpcomingRange] = useState<ReviewStatsRange>("7d");
  const [intervalRange, setIntervalRange] = useState<ReviewStatsRange>("7d");

  const upcomingBars = useMemo(() => bucketUpcomingReviews(cards, upcomingRange), [cards, upcomingRange]);
  const intervalSubset = useMemo(
    () => filterCardsWithinUpcomingWindow(cards, intervalRange),
    [cards, intervalRange]
  );
  const intervalBars = useMemo(() => bucketByInterval(intervalSubset), [intervalSubset]);
  const beyondUpcoming = useMemo(
    () => countScheduledBeyondWindow(cards, upcomingRange),
    [cards, upcomingRange]
  );
  const beyondInterval = useMemo(
    () => countScheduledBeyondWindow(cards, intervalRange),
    [cards, intervalRange]
  );

  const upcomingKey = `up-${upcomingRange}-${upcomingBars.map((b) => b.count).join("-")}`;
  const intervalKey = `iv-${intervalRange}-${intervalBars.map((b) => b.count).join("-")}`;

  const windowLabel = (r: ReviewStatsRange) =>
    r === "7d" ? "week" : r === "30d" ? "30-day window" : "90-day window";

  return (
    <section className="review-stats review-stats-dual" aria-labelledby="review-stats-heading">
      <div className="review-stats-top">
        <h3 id="review-stats-heading" className="review-stats-title">
          Review statistics
        </h3>
      </div>
      <div className="review-stats-charts-stack">
        <StatsBarChartPanel
          title="Upcoming"
          hint="Next review date (local). First bar: today, overdue, and new cards."
          bars={upcomingBars}
          listKey={upcomingKey}
          range={upcomingRange}
          onRangeChange={setUpcomingRange}
          rangeGroupLabel="Upcoming chart time span"
          beyond={
            beyondUpcoming > 0 ? (
              <p className="review-stats-beyond empty-hint">
                +{beyondUpcoming} more after this {windowLabel(upcomingRange)}
              </p>
            ) : undefined
          }
        />
        <StatsBarChartPanel
          title="By interval"
          hint="Interval distribution for cards included in this time span (same window as Upcoming for the selected range)."
          bars={intervalBars}
          listKey={intervalKey}
          range={intervalRange}
          onRangeChange={setIntervalRange}
          rangeGroupLabel="By interval chart time span"
          beyond={
            beyondInterval > 0 ? (
              <p className="review-stats-beyond empty-hint">
                +{beyondInterval} cards scheduled after this {windowLabel(intervalRange)} (excluded from chart)
              </p>
            ) : undefined
          }
        />
      </div>
    </section>
  );
}

function DeckPicker({
  decks,
  busy,
  onCreate,
  onOpen,
  onRename,
}: {
  decks: api.DeckSummary[];
  busy: boolean;
  onCreate: (name: string) => Promise<void>;
  onOpen: (id: number) => void;
  onRename: (id: number, name: string) => Promise<void>;
}) {
  const [name, setName] = useState("");
  const [renaming, setRenaming] = useState<{ id: number; currentName: string } | null>(null);
  const [renameDraft, setRenameDraft] = useState("");
  const renameInputRef = useRef<HTMLInputElement>(null);

  const closeRenameModal = useCallback(() => {
    setRenaming(null);
    setRenameDraft("");
  }, []);

  useEffect(() => {
    if (!renaming) return;
    renameInputRef.current?.focus();
    renameInputRef.current?.select();
  }, [renaming]);

  useEffect(() => {
    if (!renaming) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") closeRenameModal();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [renaming, closeRenameModal]);

  const handleCreate = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    void onCreate(name.trim());
    setName("");
  };

  const handleRenameSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!renaming) return;
    const t = renameDraft.trim();
    if (!t) return;
    if (t === renaming.currentName) {
      closeRenameModal();
      return;
    }
    try {
      await onRename(renaming.id, t);
      closeRenameModal();
    } catch {
      /* error surfaced by parent; keep modal open */
    }
  };

  return (
    <div className="deck-picker">
      <div className="deck-cluster-frame">
        <div className="panel deck-picker-actions deck-panel-tile deck-create-strip">
          <h2 className="deck-picker-title">Create a deck</h2>
          <form onSubmit={handleCreate} className="deck-create-form">
            <input
              className="doc-select"
              placeholder="New deck name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              disabled={busy}
              aria-label="New deck name"
            />
            <button type="submit" className="btn btn-primary" disabled={busy || !name.trim()}>
              Create deck
            </button>
          </form>
        </div>
        <div className="deck-grid">
          {decks.length === 0 ? (
            <p className="empty-hint deck-grid-empty">No decks yet. Create one above.</p>
          ) : (
            decks.map((d) => (
              <div key={d.id} className="panel deck-card deck-panel-tile deck-card-strip">
                <div className="deck-card-head">
                  <div className="deck-card-name" title={d.name}>
                    {d.name}
                  </div>
                  <button
                    type="button"
                    className="deck-card-rename"
                    disabled={busy}
                    onClick={() => {
                      setRenaming({ id: d.id, currentName: d.name });
                      setRenameDraft(d.name);
                    }}
                  >
                    Rename
                  </button>
                </div>
                <div className="deck-card-preview empty-hint" title={d.content_preview || undefined}>
                  {d.content_preview || "No material yet — open to upload."}
                </div>
                <div className="deck-card-actions">
                  <button type="button" className="btn btn-primary" onClick={() => onOpen(d.id)} disabled={busy}>
                    Open
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {renaming != null && (
        <div
          className="rename-modal-backdrop"
          role="presentation"
          onMouseDown={(e) => {
            if (e.target === e.currentTarget) closeRenameModal();
          }}
        >
          <div
            className="rename-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="rename-deck-title"
            onMouseDown={(e) => e.stopPropagation()}
          >
            <h2 id="rename-deck-title" className="rename-modal-title">
              Rename deck
            </h2>
            <form onSubmit={handleRenameSubmit} className="rename-modal-form">
              <label className="rename-modal-label" htmlFor="rename-deck-input">
                Deck name
              </label>
              <input
                id="rename-deck-input"
                ref={renameInputRef}
                className="doc-select rename-modal-input"
                value={renameDraft}
                onChange={(e) => setRenameDraft(e.target.value)}
                disabled={busy}
                maxLength={200}
                autoComplete="off"
              />
              <div className="rename-modal-actions">
                <button type="button" className="btn" onClick={closeRenameModal} disabled={busy}>
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary" disabled={busy || !renameDraft.trim()}>
                  Save
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

export default function App() {
  const [decks, setDecks] = useState<api.DeckSummary[]>([]);
  const [deckId, setDeckId] = useState<number | null>(null);
  const [tab, setTab] = useState<Tab>("flashcards");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [deckMenuOpen, setDeckMenuOpen] = useState(false);
  const deckMenuRef = useRef<HTMLDivElement>(null);

  const currentDeck = useMemo(() => decks.find((d) => d.id === deckId), [decks, deckId]);

  const refreshDecks = useCallback(async () => {
    try {
      setError(null);
      const list = await api.fetchDecks();
      setDecks(list);
      setDeckId((cur) => {
        if (cur != null && list.some((d) => d.id === cur)) return cur;
        return null;
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load decks");
    }
  }, []);

  useEffect(() => {
    void refreshDecks();
  }, [refreshDecks]);

  useEffect(() => {
    setDeckMenuOpen(false);
  }, [deckId]);

  useEffect(() => {
    if (!deckMenuOpen) return;
    const onDoc = (e: MouseEvent) => {
      if (deckMenuRef.current && !deckMenuRef.current.contains(e.target as Node)) {
        setDeckMenuOpen(false);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setDeckMenuOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [deckMenuOpen]);

  const onCreateDeck = async (name: string) => {
    setBusy(true);
    setError(null);
    try {
      await api.createDeck(name);
      await refreshDecks();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create deck");
    } finally {
      setBusy(false);
    }
  };

  const onUploadToDeck = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (!f || deckId == null) return;
    setBusy(true);
    setError(null);
    try {
      await api.uploadDeckDocument(deckId, f);
      await refreshDecks();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  };

  const onRemoveDeckDocument = async () => {
    if (deckId == null) return;
    if (
      !confirm(
        "Remove the uploaded document from this deck? The file will be deleted from storage. Existing flashcards stay in the deck."
      )
    ) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.removeDeckDocument(deckId);
      await refreshDecks();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not remove document");
    } finally {
      setBusy(false);
    }
  };

  const onDeleteDeck = async () => {
    if (!deckId) return;
    if (!confirm("Delete this deck and all flashcards and chat in it?")) return;
    setBusy(true);
    try {
      await api.deleteDeck(deckId);
      setDeckId(null);
      await refreshDecks();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Delete failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="app-shell">
      <header className={deckId == null ? "app-header app-header-with-rule" : "app-header"}>
        <h1>AI Study Assistant</h1>
        <p>
          Create a deck, then open it to upload material if you want. Each deck has its own flashcards, learning chat, and
          mock test.
        </p>
      </header>

      {error && <div className="error-banner">{error}</div>}

      {deckId == null ? (
        <DeckPicker
          decks={decks}
          busy={busy}
          onCreate={onCreateDeck}
          onOpen={(id) => {
            setDeckId(id);
            setTab("flashcards");
          }}
          onRename={async (id, name) => {
            setBusy(true);
            setError(null);
            try {
              await api.renameDeck(id, name);
              await refreshDecks();
            } catch (e) {
              const msg = e instanceof Error ? e.message : "Could not rename deck";
              setError(msg);
              throw e;
            } finally {
              setBusy(false);
            }
          }}
        />
      ) : (
        <>
          <div className="deck-toolbar">
            <button
              type="button"
              className="btn"
              onClick={() => {
                setDeckId(null);
                setError(null);
              }}
            >
              ← All decks
            </button>
            <h2 className="deck-toolbar-title">{currentDeck?.name ?? "Deck"}</h2>
            <label className="upload-btn deck-toolbar-upload">
              {busy ? "…" : "Upload / replace material"}
              <input type="file" accept=".pdf,.txt,.md,.markdown" onChange={onUploadToDeck} disabled={busy} />
            </label>
            <div className="deck-toolbar-menu" ref={deckMenuRef}>
              <button
                type="button"
                className="btn deck-toolbar-more"
                aria-expanded={deckMenuOpen}
                aria-haspopup="menu"
                aria-label="Deck options"
                disabled={busy}
                onClick={() => setDeckMenuOpen((o) => !o)}
              >
                ⋮
              </button>
              {deckMenuOpen && (
                <div className="deck-toolbar-dropdown" role="menu" aria-label="Deck options">
                  <button
                    type="button"
                    role="menuitem"
                    className="deck-toolbar-dropdown-item deck-toolbar-dropdown-danger"
                    onClick={() => {
                      setDeckMenuOpen(false);
                      void onDeleteDeck();
                    }}
                  >
                    Delete deck
                  </button>
                </div>
              )}
            </div>
          </div>

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

          {tab === "flashcards" && (
            <FlashcardsPanel
              deckId={deckId}
              onError={setError}
              studyFilename={currentDeck?.filename ?? ""}
              hasStudyMaterial={currentDeck?.has_study_material ?? false}
              onRemoveDocument={() => void onRemoveDeckDocument()}
              documentBusy={busy}
            />
          )}
          {tab === "chat" && <ChatPanel deckId={deckId} onError={setError} />}
          {tab === "quiz" && <QuizPanel deckId={deckId} onError={setError} />}
        </>
      )}
    </div>
  );
}

function FlashcardsPanel({
  deckId,
  onError,
  studyFilename,
  hasStudyMaterial,
  onRemoveDocument,
  documentBusy,
}: {
  deckId: number;
  onError: (s: string | null) => void;
  studyFilename: string;
  hasStudyMaterial: boolean;
  onRemoveDocument: () => void;
  documentBusy: boolean;
}) {
  const [section, setSection] = useState<"review" | "manage" | "statistics">("review");
  const [cards, setCards] = useState<FlashcardT[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [generatingFromDoc, setGeneratingFromDoc] = useState(false);
  const [editing, setEditing] = useState<number | null>(null);
  const [draftFront, setDraftFront] = useState("");
  const [draftBack, setDraftBack] = useState("");
  const [newFront, setNewFront] = useState("");
  const [newBack, setNewBack] = useState("");
  const [manageSearch, setManageSearch] = useState("");

  const [flipped, setFlipped] = useState(false);
  const [reviewSessionActive, setReviewSessionActive] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    onError(null);
    try {
      setCards(await api.fetchFlashcards(deckId));
    } catch (e) {
      onError(e instanceof Error ? e.message : "Failed to load flashcards");
    } finally {
      setLoading(false);
    }
  }, [deckId, onError]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    setFlipped(false);
  }, [cards]);

  const dueQueue = useMemo(() => buildSm2DueQueue(cards), [cards]);
  const nextDueLater = useMemo(() => nextFutureReview(cards), [cards]);
  const reviewCard = dueQueue[0] ?? null;

  useEffect(() => {
    if (section !== "review") {
      setReviewSessionActive(false);
    }
  }, [section]);

  useEffect(() => {
    if (section !== "manage") {
      setManageSearch("");
    }
  }, [section]);

  const manageFilteredCards = useMemo(() => {
    const q = manageSearch.trim().toLowerCase();
    if (!q) return cards;
    return cards.filter((c) => {
      const src = c.source_document_name?.toLowerCase() ?? "";
      return c.front.toLowerCase().includes(q) || c.back.toLowerCase().includes(q) || src.includes(q);
    });
  }, [cards, manageSearch]);

  useEffect(() => {
    if (!reviewCard) {
      setReviewSessionActive(false);
    }
  }, [reviewCard]);

  useEffect(() => {
    if (section !== "review" || !reviewSessionActive) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLTextAreaElement || e.target instanceof HTMLInputElement) return;
      if (e.key === " " || e.key === "Enter") {
        e.preventDefault();
        setFlipped((f) => !f);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [section, reviewSessionActive]);

  const submitFlashcardRating = async (rating: api.FlashcardRating) => {
    if (!reviewCard) return;
    setBusy(true);
    onError(null);
    try {
      await api.reviewFlashcard(deckId, reviewCard.id, rating);
      setFlipped(false);
      await load();
    } catch (e) {
      onError(e instanceof Error ? e.message : "Could not save review");
    } finally {
      setBusy(false);
    }
  };

  const gen = async () => {
    setBusy(true);
    setGeneratingFromDoc(true);
    onError(null);
    try {
      const next = await api.generateFlashcards(deckId);
      setCards(next);
    } catch (e) {
      onError(e instanceof Error ? e.message : "Generation failed");
    } finally {
      setGeneratingFromDoc(false);
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
      await api.updateFlashcard(deckId, editing, { front: draftFront, back: draftBack });
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
      await api.deleteFlashcard(deckId, id);
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
      await api.createFlashcard(deckId, newFront.trim(), newBack.trim());
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
      <nav className="subtabs" aria-label="Flashcard sections">
        <button type="button" className={section === "review" ? "active" : ""} onClick={() => setSection("review")}>
          Review flashcards
        </button>
        <button type="button" className={section === "manage" ? "active" : ""} onClick={() => setSection("manage")}>
          Manage flashcards
        </button>
        <button type="button" className={section === "statistics" ? "active" : ""} onClick={() => setSection("statistics")}>
          Statistics
        </button>
      </nav>

      {section === "review" && (
        <>
          {loading ? (
            <p className="empty-hint">Loading…</p>
          ) : cards.length === 0 ? (
            <p className="empty-hint">
              No flashcards yet. Switch to <strong>Manage flashcards</strong> to generate or add cards.
            </p>
          ) : !reviewCard ? (
            <div className="review-wrap">
              <p className="empty-hint" style={{ marginBottom: "0.75rem" }}>
                <strong>SuperMemo-2 (SM-2):</strong> nothing is due right now. Use Again / Hard / Good / Easy when cards are
                due — Again reschedules in 10 minutes.
              </p>
              {nextDueLater && (
                <p className="review-progress">
                  Next card due: {nextDueLater.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })}
                </p>
              )}
            </div>
          ) : !reviewSessionActive ? (
            <div className="review-wrap">
              <div className="review-queue-frame">
                <span className="field-label review-queue-frame-label">Due for review</span>
                <div className="review-queue-count" aria-live="polite">
                  {dueQueue.length}
                </div>
                <p className="review-queue-sublabel empty-hint">
                  {dueQueue.length === 1 ? "card in your queue" : "cards in your queue"}
                </p>
              </div>
              <div className="review-nav">
                <button
                  type="button"
                  className="btn btn-primary btn-wide"
                  onClick={() => {
                    setFlipped(false);
                    setReviewSessionActive(true);
                  }}
                >
                  Review
                </button>
              </div>
            </div>
          ) : (
            <div className="review-wrap">
              <p className="empty-hint" style={{ marginBottom: "0.75rem" }}>
                Reviews use <strong>SM-2</strong> with four grades. Recall the answer, reveal it to check (question stays visible), then pick{" "}
                <strong>Again</strong> (10 min), <strong>Hard</strong>, <strong>Good</strong>, or <strong>Easy</strong>. Queue:{" "}
                {dueQueue.length} due now.
              </p>
              <div className="review-meta">
                <span className="review-progress">
                  Due now · {dueQueue.length} in queue
                  {reviewCard.sm2_ease_factor != null && (
                    <> · EF {(reviewCard.sm2_ease_factor ?? 2.5).toFixed(2)}</>
                  )}
                </span>
              </div>
              <FlashcardMetaLine card={reviewCard} />
              <div className="review-card-outer">
                <div
                  role="button"
                  tabIndex={0}
                  className="review-card-stack"
                  onClick={() => setFlipped((f) => !f)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      setFlipped((f) => !f);
                    }
                  }}
                  aria-label={flipped ? "Hide answer" : "Show answer (question stays visible)"}
                >
                  <div className="review-face-panel">
                    <div className="review-tab" id="review-tab-q">
                      Question / term
                    </div>
                    <div
                      className="review-face-body review-face-body-question"
                      role="region"
                      aria-labelledby="review-tab-q"
                    >
                      <div className="review-face-text">{reviewCard.front}</div>
                    </div>
                  </div>
                  {flipped && (
                    <div className="review-face-panel">
                      <div className="review-tab" id="review-tab-a">
                        Answer
                      </div>
                      <div
                        className="review-face-body review-face-body-answer"
                        role="region"
                        aria-labelledby="review-tab-a"
                      >
                        <div className="review-face-text">{reviewCard.back}</div>
                      </div>
                    </div>
                  )}
                </div>
              </div>
              <p className="review-hint">
                Click the card or press Space to reveal the answer · the question stays above · then rate with Again, Hard,
                Good, or Easy
              </p>
              {!flipped ? (
                <div className="review-nav">
                  <button type="button" className="btn btn-primary btn-wide" onClick={() => setFlipped((f) => !f)}>
                    Show answer
                  </button>
                </div>
              ) : (
                <>
                  <div className="sm2-quality">
                    <div className="field-label">How well did you recall?</div>
                    <div className="sm2-quality-grid">
                      {FLASHCARD_RATINGS.map(({ rating, label, title }) => (
                        <button
                          key={rating}
                          type="button"
                          className={`btn sm2-q sm2-q-${rating}`}
                          title={title}
                          onClick={() => submitFlashcardRating(rating)}
                          disabled={busy}
                        >
                          {label}
                        </button>
                      ))}
                    </div>
                    <p className="sm2-quality-legend empty-hint">
                      Again = back in 10 minutes; Hard / Good / Easy follow SM-2 spacing (Easy = longest interval).
                    </p>
                  </div>
                  <div className="review-nav">
                    <button type="button" className="btn btn-primary btn-wide" onClick={() => setFlipped((f) => !f)}>
                      Show front
                    </button>
                  </div>
                </>
              )}
            </div>
          )}
        </>
      )}

      {section === "statistics" && (
        <>
          {loading ? (
            <p className="empty-hint">Loading…</p>
          ) : cards.length === 0 ? (
            <p className="empty-hint">
              No flashcards yet. Switch to <strong>Manage flashcards</strong> to generate or add cards.
            </p>
          ) : (
            <FlashcardReviewStats cards={cards} />
          )}
        </>
      )}

      {section === "manage" && (
        <>
          <div className="flash-study-doc">
            <div className="flash-study-doc-header">
              <span className="field-label">Study document</span>
              {hasStudyMaterial && (
                <button
                  type="button"
                  className="btn btn-danger flash-remove-doc"
                  onClick={onRemoveDocument}
                  disabled={documentBusy || busy || loading}
                >
                  Remove document
                </button>
              )}
            </div>
            <p className={`flash-study-doc-name ${studyFilename.trim() ? "" : "empty-hint"}`}>
              {studyFilename.trim() ? studyFilename.trim() : "No document uploaded yet — use Upload / replace material above."}
            </p>
          </div>
          <div className="toolbar flash-generate-toolbar">
            <button
              type="button"
              className={hasStudyMaterial ? "btn btn-primary" : "btn flash-generate-disabled"}
              onClick={() => void gen()}
              disabled={!hasStudyMaterial || busy || loading}
              title={!hasStudyMaterial ? "Upload study material first" : undefined}
              aria-busy={generatingFromDoc}
            >
              Generate from document
            </button>
            {generatingFromDoc && (
              <span className="generate-dots" aria-hidden="true">
                <span className="generate-dot" />
                <span className="generate-dot" />
                <span className="generate-dot" />
              </span>
            )}
          </div>
          <p className="empty-hint" style={{ marginBottom: "1rem" }}>
            Cards are saved for this document. Edit or add your own anytime.
          </p>

          <div className="flash-new-card-form">
            <span className="field-label">New flashcard</span>
            <div className="flash-new-card-row">
              <textarea
                className="flash-new-card-field"
                placeholder="Front (question or term)"
                value={newFront}
                onChange={(e) => setNewFront(e.target.value)}
              />
              <textarea
                className="flash-new-card-field"
                placeholder="Back (answer or definition)"
                value={newBack}
                onChange={(e) => setNewBack(e.target.value)}
              />
              <button type="button" className="btn btn-primary flash-new-card-submit" onClick={addManual} disabled={busy}>
                Add card
              </button>
            </div>
          </div>

          {!loading && cards.length > 0 && (
            <div className="flash-manage-search">
              <label className="field-label" htmlFor="flash-manage-search-input">
                Search cards
              </label>
              <input
                id="flash-manage-search-input"
                type="search"
                className="doc-select flash-manage-search-input"
                placeholder="Search front, back, or source…"
                value={manageSearch}
                onChange={(e) => setManageSearch(e.target.value)}
                autoComplete="off"
                aria-controls="flash-manage-list"
              />
            </div>
          )}

          {loading ? (
            <p className="empty-hint">Loading…</p>
          ) : cards.length === 0 ? (
            <p className="empty-hint">No flashcards yet. Generate from your document or add manually.</p>
          ) : manageFilteredCards.length === 0 ? (
            <p className="empty-hint" id="flash-manage-list">
              No cards match your search.
            </p>
          ) : (
            <div className="flash-list" id="flash-manage-list">
              {manageFilteredCards.map((c) => (
                <div key={c.id} className="flash-card">
                  <FlashcardMetaLine card={c} />
                  {c.source_document_name?.trim() ? (
                    <p className="flashcard-source">
                      <span className="flashcard-source-label">Source</span> {c.source_document_name.trim()}
                    </p>
                  ) : null}
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
        </>
      )}
    </div>
  );
}

function formatChatSessionTime(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function ChatSessionRow({
  deckId,
  session,
  active,
  onSelect,
  onDeleted,
  onError,
}: {
  deckId: number;
  session: api.ChatSession;
  active: boolean;
  onSelect: () => void;
  onDeleted: () => void;
  onError: (s: string | null) => void;
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menuOpen) return;
    const onDoc = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setMenuOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [menuOpen]);

  const onDelete = async () => {
    if (!confirm("Delete this chat and all its messages?")) return;
    setMenuOpen(false);
    onError(null);
    try {
      await api.deleteChatSession(deckId, session.id);
      onDeleted();
    } catch (e) {
      onError(e instanceof Error ? e.message : "Delete failed");
    }
  };

  return (
    <li className="chat-session-row">
      <button type="button" className={`chat-session-item ${active ? "active" : ""}`} onClick={onSelect}>
        <span className="chat-session-item-title">{session.title?.trim() || "New chat"}</span>
        <span className="chat-session-item-meta">{formatChatSessionTime(session.updated_at ?? session.created_at)}</span>
      </button>
      <div className="deck-toolbar-menu chat-session-menu" ref={menuRef}>
        <button
          type="button"
          className="btn deck-toolbar-more"
          aria-expanded={menuOpen}
          aria-haspopup="menu"
          aria-label={`Options for chat: ${session.title?.trim() || "New chat"}`}
          onClick={(e) => {
            e.stopPropagation();
            setMenuOpen((o) => !o);
          }}
        >
          ⋮
        </button>
        {menuOpen && (
          <div className="deck-toolbar-dropdown" role="menu" aria-label="Chat options">
            <button
              type="button"
              role="menuitem"
              className="deck-toolbar-dropdown-item deck-toolbar-dropdown-danger"
              onClick={() => void onDelete()}
            >
              Delete chat
            </button>
          </div>
        )}
      </div>
    </li>
  );
}

function ChatPanel({ deckId, onError }: { deckId: number; onError: (s: string | null) => void }) {
  const [sessions, setSessions] = useState<api.ChatSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<number | null>(null);
  const [msgs, setMsgs] = useState<api.ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(true);
  const [msgsLoading, setMsgsLoading] = useState(false);
  const [sending, setSending] = useState(false);

  const loadSessions = useCallback(async () => {
    setLoading(true);
    onError(null);
    try {
      let list = await api.fetchChatSessions(deckId);
      if (list.length === 0) {
        const created = await api.createChatSession(deckId);
        list = [created];
      }
      setSessions(list);
      setActiveSessionId((cur) => {
        if (cur != null && list.some((x) => x.id === cur)) return cur;
        return list[0]?.id ?? null;
      });
    } catch (e) {
      onError(e instanceof Error ? e.message : "Failed to load chats");
    } finally {
      setLoading(false);
    }
  }, [deckId, onError]);

  useEffect(() => {
    void loadSessions();
  }, [loadSessions]);

  useEffect(() => {
    if (activeSessionId == null) return;
    let cancelled = false;
    const loadMsgs = async () => {
      setMsgsLoading(true);
      onError(null);
      try {
        const m = await api.fetchChatMessages(deckId, activeSessionId);
        if (!cancelled) setMsgs(m);
      } catch (e) {
        if (!cancelled) onError(e instanceof Error ? e.message : "Failed to load messages");
      } finally {
        if (!cancelled) setMsgsLoading(false);
      }
    };
    void loadMsgs();
    return () => {
      cancelled = true;
    };
  }, [deckId, activeSessionId, onError]);

  const newChat = async () => {
    onError(null);
    try {
      const s = await api.createChatSession(deckId);
      setSessions((prev) => [s, ...prev]);
      setActiveSessionId(s.id);
      setMsgs([]);
    } catch (e) {
      onError(e instanceof Error ? e.message : "Could not start chat");
    }
  };

  const afterSessionDeleted = async () => {
    onError(null);
    try {
      let list = await api.fetchChatSessions(deckId);
      if (list.length === 0) {
        const created = await api.createChatSession(deckId);
        list = [created];
      }
      setSessions(list);
      setActiveSessionId((cur) => {
        if (cur != null && list.some((x) => x.id === cur)) return cur;
        return list[0]?.id ?? null;
      });
    } catch (e) {
      onError(e instanceof Error ? e.message : "Failed to refresh chats");
    }
  };

  const send = async () => {
    const t = input.trim();
    if (!t || sending || activeSessionId == null) return;
    setSending(true);
    onError(null);
    setInput("");
    try {
      await api.sendChatMessage(deckId, activeSessionId, t);
      const [nextMsgs, nextSessions] = await Promise.all([
        api.fetchChatMessages(deckId, activeSessionId),
        api.fetchChatSessions(deckId),
      ]);
      setMsgs(nextMsgs);
      setSessions(nextSessions);
    } catch (e) {
      onError(e instanceof Error ? e.message : "Message failed");
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="panel chat-panel-outer">
      <h2>Learning chat</h2>
      <p className="empty-hint" style={{ marginBottom: "1rem" }}>
        Ask for basics, simple definitions, or deeper explanations at any level. The tutor can use general knowledge to help you understand; your uploaded material is optional context when you want ties to your reading.
      </p>
      {loading ? (
        <p className="empty-hint">Loading…</p>
      ) : (
        <div className="chat-layout">
          <aside className="chat-sidebar" aria-label="Past chats">
            <div className="chat-sidebar-header">
              <span className="chat-sidebar-title">Chats</span>
              <button type="button" className="btn btn-primary chat-sidebar-new" onClick={() => void newChat()}>
                New chat
              </button>
            </div>
            <ul className="chat-session-list">
              {sessions.map((s) => (
                <ChatSessionRow
                  key={s.id}
                  deckId={deckId}
                  session={s}
                  active={s.id === activeSessionId}
                  onSelect={() => setActiveSessionId(s.id)}
                  onDeleted={() => void afterSessionDeleted()}
                  onError={onError}
                />
              ))}
            </ul>
          </aside>
          <div className="chat-main">
            {msgsLoading ? (
              <p className="empty-hint">Loading messages…</p>
            ) : (
              <>
                <div className="chat-log">
                  {msgs.length === 0 && (
                    <p className="empty-hint">No messages yet. Ask anything you&apos;re studying—simple definitions, or how your reading fits together.</p>
                  )}
                  {msgs.map((m) => (
                    <div key={m.id} className={`chat-bubble ${m.role === "user" ? "user" : "assistant"}`}>
                      <div className="chat-md">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown>
                      </div>
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
                        void send();
                      }
                    }}
                    disabled={sending}
                  />
                  <button type="button" className="btn btn-primary" onClick={() => void send()} disabled={sending || !input.trim()}>
                    {sending ? "…" : "Send"}
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function QuizPanel({ deckId, onError }: { deckId: number; onError: (s: string | null) => void }) {
  const [numMc, setNumMc] = useState(5);
  const [numSa, setNumSa] = useState(2);
  const [questions, setQuestions] = useState<QuizQuestion[] | null>(null);
  const [mcAnswers, setMcAnswers] = useState<Record<string, number>>({});
  const [saAnswers, setSaAnswers] = useState<Record<string, string>>({});
  const [result, setResult] = useState<QuizResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [generatingQuiz, setGeneratingQuiz] = useState(false);

  const generate = async () => {
    setBusy(true);
    setGeneratingQuiz(true);
    onError(null);
    setResult(null);
    try {
      const { questions: q } = await api.generateQuiz(deckId, numMc, numSa);
      setQuestions(q);
      setMcAnswers({});
      setSaAnswers({});
    } catch (e) {
      onError(e instanceof Error ? e.message : "Quiz generation failed");
    } finally {
      setGeneratingQuiz(false);
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
      const r = await api.gradeQuiz(deckId, questions, answers);
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
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => void generate()}
            disabled={busy}
            aria-busy={generatingQuiz}
          >
            Generate quiz
          </button>
          {generatingQuiz && (
            <span className="generate-dots" aria-hidden="true">
              <span className="generate-dot" />
              <span className="generate-dot" />
              <span className="generate-dot" />
            </span>
          )}
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
