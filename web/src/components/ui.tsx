import { useEffect, useRef, useState, type ReactNode } from "react";
import { Check, Copy } from "lucide-react";
import { useStore, useT } from "../store.tsx";
import { reasonText, statusText } from "../i18n.ts";
import { shortHash } from "../format.ts";

export function Badge({
  code,
  tone,
  icon,
  label,
}: {
  code?: string;
  tone?: "neutral" | "teal" | "clay" | "amber" | "green" | "danger";
  icon?: ReactNode;
  label?: string;
}) {
  const { locale } = useStore();
  return (
    <span className={`badge ${tone ?? "neutral"}`}>
      {icon && <span className="badge-icon">{icon}</span>}
      {label ?? statusText(locale, code)}
    </span>
  );
}

/** Tone policy shared across tables, cards and the drawer. */
export function runStatusTone(status?: string): "neutral" | "teal" | "clay" | "amber" | "green" | "danger" {
  switch (status) {
    case "ready":
      return "teal";
    case "reviewed":
      return "green";
    case "evidence_pending":
      return "amber";
    case "triaged":
      return "amber";
    case "observed":
    default:
      return "neutral";
  }
}

export function jobStatusTone(status?: string): "neutral" | "teal" | "clay" | "amber" | "green" | "danger" {
  switch (status) {
    case "hold":
      return "clay";
    case "running":
      return "teal";
    case "queued":
    case "waiting":
      return "amber";
    case "completed":
      return "green";
    case "failed":
    case "cancelled":
      return "danger";
    default:
      return "neutral";
  }
}

export function envStatusTone(status?: string): "neutral" | "teal" | "clay" | "amber" | "green" | "danger" {
  switch (status) {
    case "passed":
    case "available":
    case "ready":
      return "green";
    case "checking":
    case "pending_canary":
      return "amber";
    case "failed":
    case "unavailable":
      return "danger";
    default:
      return "neutral";
  }
}

export function Card({
  title,
  subtitle,
  icon,
  actions,
  tabs,
  children,
  padded = true,
}: {
  title?: ReactNode;
  subtitle?: ReactNode;
  icon?: ReactNode;
  actions?: ReactNode;
  tabs?: ReactNode;
  children: ReactNode;
  padded?: boolean;
}) {
  return (
    <section className="card">
      {(title || actions) && (
        <header className="card-head">
          {icon}
          <div className="titles">
            {title && <h3 className="card-title">{title}</h3>}
            {subtitle && <div className="card-sub">{subtitle}</div>}
          </div>
          {actions && <div className="spacer" />}
          {actions}
        </header>
      )}
      {tabs}
      <div className={padded ? "card-body" : ""}>{children}</div>
    </section>
  );
}

export function Notice({
  tone = "amber",
  icon,
  title,
  body,
  children,
}: {
  tone?: "amber" | "clay" | "teal" | "danger" | "neutral";
  icon?: ReactNode;
  title?: ReactNode;
  body?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <div className={`notice ${tone}`} role="note">
      {icon && <span className="notice-icon">{icon}</span>}
      <div>
        {title && <div className="notice-title">{title}</div>}
        {body && <div className="notice-body">{body}</div>}
        {children}
      </div>
    </div>
  );
}

export function EmptyState({
  icon,
  title,
  body,
  action,
}: {
  icon?: ReactNode;
  title: string;
  body?: string;
  action?: ReactNode;
}) {
  return (
    <div className="state-block">
      {icon && <div className="state-icon">{icon}</div>}
      <h3>{title}</h3>
      {body && <p>{body}</p>}
      {action}
    </div>
  );
}

export function LoadingState({ label }: { label?: string }) {
  const t = useT();
  return (
    <div className="state-block" role="status" aria-live="polite">
      <div className="spinner" aria-hidden="true" />
      <h3>{label ?? t("common.loading")}</h3>
    </div>
  );
}

export function ErrorState({ onRetry }: { onRetry?: () => void }) {
  const { error, offline, refresh, locale } = useStore();
  const t = useT();
  return (
    <div className="state-block" role="alert">
      <h3>{offline ? t("common.offline") : t("common.errorTitle")}</h3>
      <p>{offline ? t("common.offlineBody") : t("common.errorBody")}</p>
      {error?.reason_code && <p className="mono">{reasonText(locale, error.reason_code)}</p>}
      <button
        className="btn primary"
        onClick={() => {
          void (onRetry ?? refresh)();
        }}
      >
        {t("common.retryNow")}
      </button>
    </div>
  );
}


export function CopyButton({ value, size = 13 }: { value: string; size?: number }) {
  const t = useT();
  const [done, setDone] = useState(false);
  const timer = useRef<number | undefined>(undefined);
  return (
    <button
      type="button"
      className="copy-mini"
      aria-label={t("common.copyId")}
      onClick={(e) => {
        e.stopPropagation();
        void navigator.clipboard?.writeText(value).then(() => {
          setDone(true);
          window.clearTimeout(timer.current);
          timer.current = window.setTimeout(() => setDone(false), 1500);
        });
      }}
    >
      {done ? <Check size={size} aria-hidden="true" /> : <Copy size={size} aria-hidden="true" />}
    </button>
  );
}

export function IdCell({ id }: { id: string }) {
  return (
    <span className="cell-id">
      {shortHash(id, 14)}
      <CopyButton value={id} />
    </span>
  );
}

export function ReasonCodes({ codes }: { codes?: string[] }) {
  const { locale } = useStore();
  if (!codes || codes.length === 0) return <span aria-label="—">—</span>;
  return (
    <span style={{ display: "inline-flex", flexDirection: "column", gap: 4, alignItems: "flex-start" }}>
      {codes.map((c) => (
        <Badge key={c} tone="clay" label={reasonText(locale, c)} />
      ))}
    </span>
  );
}

export function KV({ rows }: { rows: [ReactNode, ReactNode][] }) {
  return (
    <dl className="kv">
      {rows.map(([k, v], i) => (
        <span key={i} style={{ display: "contents" }}>
          <dt>{k}</dt>
          <dd>{v}</dd>
        </span>
      ))}
    </dl>
  );
}

export function JsonBlock({ value }: { value: unknown }) {
  const [open, setOpen] = useState(false);
  const t = useT();
  return (
    <div>
      <button type="button" className="btn ghost sm" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
        {t("live.rawJson")}
      </button>
      {open && <pre className="mono" style={{ whiteSpace: "pre-wrap", background: "var(--card-alt)", border: "1px solid var(--border)", borderRadius: 8, padding: 10 }}>{JSON.stringify(value, null, 2)}</pre>}
    </div>
  );
}

export function useNow(intervalMs = 30_000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), intervalMs);
    return () => window.clearInterval(id);
  }, [intervalMs]);
  return now;
}
