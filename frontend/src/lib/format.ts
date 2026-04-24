/**
 * Format an integer VND amount as e.g. "₫1.200.000".
 * Uses Intl so browser locale formatting works correctly in both VI and EN UIs.
 */
export function formatVnd(amount: number | null | undefined, locale: string = "vi-VN"): string {
  if (amount == null) return "—";
  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency: "VND",
    maximumFractionDigits: 0,
  }).format(amount);
}

/** Parse a flexible user input like "1.200.000" or "1,200,000" or "1200000" into an integer. */
export function parseVnd(input: string): number | null {
  const cleaned = input.replace(/[^\d]/g, "");
  if (!cleaned) return null;
  const n = Number(cleaned);
  return Number.isFinite(n) ? n : null;
}

export function formatDate(ts: string | Date, locale: string = "vi-VN"): string {
  const d = typeof ts === "string" ? new Date(ts) : ts;
  return new Intl.DateTimeFormat(locale, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Asia/Ho_Chi_Minh",
  }).format(d);
}
