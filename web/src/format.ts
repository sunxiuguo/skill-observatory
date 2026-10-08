import type { Locale } from "./types.ts";

export function toDate(iso?: string | null): Date | null {
  if (!iso) return null;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d;
}

export function formatDateTime(iso: string | undefined | null, locale: Locale, tz: string): string {
  const d = toDate(iso);
  if (!d) return "—";
  try {
    return new Intl.DateTimeFormat(locale, {
      dateStyle: "medium",
      timeStyle: "short",
      timeZone: tz,
    }).format(d);
  } catch {
    return d.toLocaleString(locale);
  }
}

export function formatDate(iso: string | undefined | null, locale: Locale, tz: string): string {
  const d = toDate(iso);
  if (!d) return "—";
  try {
    return new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeZone: tz }).format(d);
  } catch {
    return d.toLocaleDateString(locale);
  }
}

export function formatTime(iso: string | undefined | null, locale: Locale, tz: string): string {
  const d = toDate(iso);
  if (!d) return "—";
  try {
    return new Intl.DateTimeFormat(locale, { timeStyle: "short", timeZone: tz }).format(d);
  } catch {
    return d.toLocaleTimeString(locale);
  }
}

export function formatNumber(value: number | undefined | null, locale: Locale): string {
  if (value === undefined || value === null) return "—";
  return new Intl.NumberFormat(locale).format(value);
}

export function formatBytes(bytes: number | undefined, locale: Locale): string {
  if (bytes === undefined || bytes === null) return "—";
  if (bytes < 1024) return `${formatNumber(bytes, locale)} B`;
  const units = ["KB", "MB", "GB"];
  let v = bytes / 1024;
  let u = 0;
  while (v >= 1024 && u < units.length - 1) {
    v /= 1024;
    u += 1;
  }
  return `${v.toLocaleString(locale, { maximumFractionDigits: 1 })} ${units[u]}`;
}

export function formatSigned(n: number | undefined, locale: Locale, digits = 1): string {
  if (n === undefined || n === null) return "—";
  const v = n.toLocaleString(locale, { maximumFractionDigits: digits, minimumFractionDigits: digits });
  return n > 0 ? `+${v}` : v;
}

export function relativeTime(iso: string | undefined | null, locale: Locale, tz: string, now = Date.now()): string {
  const d = toDate(iso);
  if (!d) return "—";
  const diffSec = Math.round((now - d.getTime()) / 1000);
  const abs = Math.abs(diffSec);
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });
  const units: [Intl.RelativeTimeFormatUnit, number][] = [
    ["minute", 60],
    ["hour", 3600],
    ["day", 86400],
  ];
  if (abs < 60) return locale === "zh-CN" ? "刚刚" : "just now";
  for (const [unit, base] of units) {
    if (abs < base * (unit === "day" ? 7 : 60) || unit === "day") {
      if (abs < base * (unit === "minute" ? 60 : unit === "hour" ? 24 : 7)) {
        return rtf.format(-Math.round(abs / base), unit);
      }
    }
  }
  return formatDate(iso, locale, tz);
}

export function shortHash(h?: string, len = 10): string {
  if (!h) return "—";
  return h.length <= len + 4 ? h : `${h.slice(0, 6)}…${h.slice(-4)}`;
}

export function evidenceSummary(
  evidence: { kind?: string; size_bytes?: number }[] | undefined,
  locale: Locale,
): { files: number; size: string; transcripts: number } {
  const list = evidence ?? [];
  const files = list.filter((e) => e.kind !== "transcript").length;
  const transcripts = list.length - files;
  const size = list.reduce((acc, e) => acc + (e.size_bytes ?? 0), 0);
  return { files: files || (transcripts === 0 ? list.length : 0), size: formatBytes(size, locale), transcripts };
}
