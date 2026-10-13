// Real API client. No mock fallback: every render path is fed by these endpoints.
//
// Auth/session contract (from root backend):
//  GET /api/session sets an HTTPOnly session cookie and returns a CSRF token.
//  After a server restart the old cookie/token pair is dead and EVERY request
//  (including GET /api/state) returns 401. We then re-establish the session and
//  retry ONCE. The retried request is rebuilt from scratch with the NEW token —
//  stale X-CSRF-Token headers are never replayed.
import type { ApiError, ObservatoryState, SessionInfo, Settings } from "./types.ts";

const SUMMARY_URL = "/api/summary";
const SESSION_URL = "/api/session";

interface TransportOptions {
  signal?: AbortSignal;
}

export function getCsrf(): string | null {
  return sessionStorage.getItem("so.csrf");
}

function isOffline(): boolean {
  return typeof navigator !== "undefined" && navigator.onLine === false;
}

function isAbortError(err: unknown, signal?: AbortSignal): boolean {
  return signal?.aborted === true || (err as { name?: string } | null)?.name === "AbortError";
}

function transportError(err: unknown, signal?: AbortSignal): ApiError {
  const aborted = isAbortError(err, signal);
  return {
    status: 0,
    message: aborted ? "ABORTED" : ((err as Error)?.message ?? "Unknown error"),
    offline: !aborted && isOffline(),
    aborted,
  };
}

function extractReasonCode(data: unknown): string | undefined {
  if (!data || typeof data !== "object") return undefined;
  const obj = data as Record<string, unknown>;
  if (typeof obj.reason_code === "string") return obj.reason_code;
  const detail = obj.detail;
  if (detail && typeof detail === "object") {
    const d = detail as Record<string, unknown>;
    if (typeof d.reason_code === "string") return d.reason_code;
  }
  return undefined;
}

interface RequestOptions extends Omit<RequestInit, "headers"> {
  headers?: Record<string, string>;
  /** Inject the current CSRF token at send time (so a retry always uses a fresh one). */
  csrf?: boolean;
}

async function request<T>(input: string, opts: RequestOptions = {}, attempt = 0): Promise<T> {
  // RequestInit permits null; normalize it so retry/session helpers keep a
  // strict optional AbortSignal contract.
  const signal = opts.signal ?? undefined;
  if (signal?.aborted) {
    throw { status: 0, message: "ABORTED", offline: false, aborted: true } satisfies ApiError;
  }
  if (isOffline()) {
    throw { offline: true, status: 0, message: "OFFLINE" } satisfies ApiError;
  }

  // Build a fresh header set on every physical attempt so a post-restart retry
  // never replays the dead token.
  const headers = new Headers(opts.headers);
  if (opts.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (opts.csrf) headers.set("X-CSRF-Token", getCsrf() ?? "");

  let res: Response;
  try {
    const { headers: _h, csrf: _c, ...init } = opts;
    void _h;
    void _c;
    res = await fetch(input, { ...init, signal, credentials: "same-origin", headers });
  } catch (err) {
    throw transportError(err, signal);
  }

  // Dead session (server restart) or stale token: establish once and retry with
  // a brand-new session. The signal remains owned by the original caller.
  if ((res.status === 401 || res.status === 403) && attempt === 0) {
    await establishSession({ signal });
    return request<T>(input, opts, attempt + 1);
  }

  if (!res.ok) {
    let message = `HTTP ${res.status}`;
    let reasonCode: string | undefined;
    try {
      const data: unknown = await res.json();
      reasonCode = extractReasonCode(data);
      if (data && typeof data === "object") {
        const obj = data as Record<string, unknown>;
        if (typeof obj.message === "string") message = obj.message;
        else if (typeof obj.error === "string") message = obj.error;
      }
    } catch {
      /* non-json error body */
    }
    throw { status: res.status, message, reason_code: reasonCode } satisfies ApiError;
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export async function establishSession(options: TransportOptions = {}): Promise<SessionInfo> {
  // Do not go through request(): a session bootstrap failure must not recurse.
  if (options.signal?.aborted) {
    throw { status: 0, message: "ABORTED", offline: false, aborted: true } satisfies ApiError;
  }
  if (isOffline()) {
    throw { offline: true, status: 0, message: "OFFLINE" } satisfies ApiError;
  }
  let res: Response;
  try {
    res = await fetch(SESSION_URL, {
      signal: options.signal,
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    });
  } catch (err) {
    throw transportError(err, options.signal);
  }
  if (!res.ok) throw { status: res.status, message: `HTTP ${res.status}` } satisfies ApiError;
  const data = (await res.json()) as Record<string, unknown>;
  const csrf =
    typeof data.csrf === "string"
      ? data.csrf
      : typeof data.csrf_token === "string"
        ? data.csrf_token
        : typeof data.token === "string"
          ? data.token
          : "";
  if (csrf) sessionStorage.setItem("so.csrf", csrf);
  return { csrf };
}

/**
 * Fetch the small first-screen summary. The route returns the existing
 * ObservatoryState shape with bounded rows, a revision, and pagination facts.
 * The function name remains stable for existing callers.
 */
export async function fetchState(options: TransportOptions = {}): Promise<ObservatoryState> {
  return request<ObservatoryState>(SUMMARY_URL, {
    ...options,
    headers: { Accept: "application/json" },
  });
}

export async function saveSettings(settings: Settings): Promise<void> {
  return request<void>("/api/settings", {
    method: "POST",
    csrf: true,
    body: JSON.stringify(Object.fromEntries(Object.entries(settings).filter(([key]) => ["locale", "timezone", "paused", "automatic_review"].includes(key)))),
  });
}

export async function retryJob(jobId: string): Promise<void> {
  return request<void>(`/api/jobs/${encodeURIComponent(jobId)}/retry`, {
    method: "POST",
    csrf: true,
  });
}

export async function rollbackInstallation(installationId: string): Promise<void> {
  return request<void>(`/api/installations/${encodeURIComponent(installationId)}/rollback`, {
    method: "POST",
    csrf: true,
  });
}
