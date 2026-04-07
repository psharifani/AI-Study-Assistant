/** Formatting helpers for flashcard ID, schedule, and SM-2 fields */

export function formatAddedDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString(undefined, { dateStyle: "medium" });
  } catch {
    return "—";
  }
}

/** Scheduled interval length after the last review (SM-2 `interval_days`). */
export function formatIntervalDays(days: number | undefined): string {
  if (days == null || !Number.isFinite(days) || days <= 0) return "—";
  const n = Math.round(days);
  return `${n} day${n === 1 ? "" : "s"}`;
}

/**
 * Human-readable time until next review vs wall clock, with calendar date.
 * Example: interval 20 days total, but next due in 3 days → "in 3 days (Apr 8, 2026)".
 */
export function formatNextRead(next: string | null | undefined): string {
  if (next == null || next === "") return "Due now";
  let d: Date;
  try {
    d = new Date(next);
  } catch {
    return "—";
  }
  const t = d.getTime();
  if (Number.isNaN(t)) return "—";
  const now = Date.now();
  const diff = t - now;
  const dateStr = d.toLocaleDateString(undefined, { dateStyle: "medium" });

  if (diff <= 0) {
    const overdueMin = Math.floor(-diff / 60_000);
    if (overdueMin < 90) return `Due now (${dateStr})`;
    const overdueDays = Math.floor(-diff / 86_400_000);
    if (overdueDays <= 0) return `Due now (${dateStr})`;
    return `Due now — ${overdueDays}d overdue (${dateStr})`;
  }

  const mins = diff / 60_000;
  if (mins < 120) {
    const m = Math.max(1, Math.round(mins));
    return `in ${m} min (${dateStr})`;
  }
  const hours = diff / 3_600_000;
  if (hours < 36) {
    const h = Math.ceil(hours);
    return `in ${h} hour${h === 1 ? "" : "s"} (${dateStr})`;
  }
  const days = Math.round(diff / 86_400_000);
  if (days === 0) return `Due today (${dateStr})`;
  return `in ${days} day${days === 1 ? "" : "s"} (${dateStr})`;
}
