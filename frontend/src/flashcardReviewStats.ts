import type { Flashcard } from "./api";

export type ReviewStatsRange = "7d" | "30d" | "90d";

function startOfLocalDay(d: Date): Date {
  const t = new Date(d);
  t.setHours(0, 0, 0, 0);
  return t;
}

function bucketWindow(
  anchor: Date,
  bucketIndex: number,
  daysPerBucket: number
): { start: number; end: number } {
  const s = new Date(anchor);
  s.setDate(s.getDate() + bucketIndex * daysPerBucket);
  const e = new Date(s);
  e.setDate(e.getDate() + daysPerBucket);
  return { start: s.getTime(), end: e.getTime() };
}

function nextReviewMs(c: Flashcard): number | null {
  const t = c.sm2_next_review_at;
  if (t == null || t === "") return null;
  const ms = new Date(t).getTime();
  return Number.isNaN(ms) ? null : ms;
}

/** Cards with no next date count as due immediately (first bucket). */
export function bucketUpcomingReviews(
  cards: Flashcard[],
  range: ReviewStatsRange,
  now = new Date()
): { label: string; count: number }[] {
  const anchor = startOfLocalDay(now);
  const cfg =
    range === "7d"
      ? { n: 7, step: 1 }
      : range === "30d"
        ? { n: 5, step: 6 }
        : { n: 9, step: 10 };

  const starts: number[] = [];
  const ends: number[] = [];
  for (let i = 0; i < cfg.n; i++) {
    const w = bucketWindow(anchor, i, cfg.step);
    starts.push(w.start);
    ends.push(w.end);
  }

  const counts = new Array(cfg.n).fill(0);
  for (const c of cards) {
    const t = nextReviewMs(c);
    if (t == null) {
      counts[0]++;
      continue;
    }
    if (t < anchor.getTime()) {
      counts[0]++;
      continue;
    }
    let placed = false;
    for (let i = 0; i < cfg.n; i++) {
      if (t >= starts[i] && t < ends[i]) {
        counts[i]++;
        placed = true;
        break;
      }
    }
    if (!placed) {
      /* scheduled past this window — omit from bars */
    }
  }

  const labels: string[] = [];
  for (let i = 0; i < cfg.n; i++) {
    const s = new Date(starts[i]);
    const endIncl = new Date(ends[i]);
    endIncl.setMilliseconds(-1);
    if (cfg.step === 1) {
      labels.push(
        s.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" })
      );
    } else {
      labels.push(
        `${s.toLocaleDateString(undefined, { month: "short", day: "numeric" })} – ${endIncl.toLocaleDateString(undefined, { month: "short", day: "numeric" })}`
      );
    }
  }

  return labels.map((label, i) => ({ label, count: counts[i] }));
}

/** Cards counted in the upcoming chart for this range (excludes only those scheduled after the last bucket). */
export function filterCardsWithinUpcomingWindow(
  cards: Flashcard[],
  range: ReviewStatsRange,
  now = new Date()
): Flashcard[] {
  const anchor = startOfLocalDay(now);
  const cfg =
    range === "7d"
      ? { n: 7, step: 1 }
      : range === "30d"
        ? { n: 5, step: 6 }
        : { n: 9, step: 10 };
  const lastEnd = bucketWindow(anchor, cfg.n - 1, cfg.step).end;
  return cards.filter((c) => {
    const t = nextReviewMs(c);
    if (t == null) return true;
    if (t < anchor.getTime()) return true;
    return t < lastEnd;
  });
}

export function countScheduledBeyondWindow(cards: Flashcard[], range: ReviewStatsRange, now = new Date()): number {
  const anchor = startOfLocalDay(now);
  const cfg =
    range === "7d"
      ? { n: 7, step: 1 }
      : range === "30d"
        ? { n: 5, step: 6 }
        : { n: 9, step: 10 };
  const lastEnd = bucketWindow(anchor, cfg.n - 1, cfg.step).end;
  let n = 0;
  for (const c of cards) {
    const t = nextReviewMs(c);
    if (t == null) continue;
    if (t < anchor.getTime()) continue;
    if (t >= lastEnd) n++;
  }
  return n;
}

/** Group by current SM-2 interval length (days). */
export function bucketByInterval(cards: Flashcard[]): { label: string; count: number }[] {
  const out = [
    { label: "New / ≤1 day", count: 0 },
    { label: "2 – 6 days", count: 0 },
    { label: "1 – 2 weeks", count: 0 },
    { label: "2 – 4 weeks", count: 0 },
    { label: "1 – 3 mo", count: 0 },
    { label: "3+ mo", count: 0 },
  ];
  for (const c of cards) {
    const raw = c.sm2_interval_days;
    const d = raw == null || Number.isNaN(raw) ? 0 : Math.max(0, raw);
    let idx: number;
    if (d <= 1) idx = 0;
    else if (d <= 6) idx = 1;
    else if (d <= 13) idx = 2;
    else if (d <= 29) idx = 3;
    else if (d <= 89) idx = 4;
    else idx = 5;
    out[idx].count++;
  }
  return out;
}
