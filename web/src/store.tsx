import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
  type SetStateAction,
} from "react";
import {
  establishSession,
  fetchState,
  retryJob as apiRetryJob,
  rollbackInstallation as apiRollback,
  saveSettings as apiSaveSettings,
} from "./api.ts";
import type { ApiError, Locale, ObservatoryState, Settings } from "./types.ts";
import { DEFAULT_LOCALE, translate } from "./i18n.ts";

const UI_STORAGE_KEY = "so.ui.v1";
const PREFS_STORAGE_KEY = "so.prefs.v1";
const POLL_MS = 8000;

export type DrawerTarget =
  | { kind: "capability"; id: string }
  | { kind: "capture"; id: string }
  | { kind: "invocation"; id: string }
  | { kind: "run"; id: string }
  | { kind: "review"; id: string }
  | { kind: "skill"; id: string }
  | { kind: "experiment"; id: string }
  | { kind: "job"; id: string }
  | { kind: "installation"; id: string }
  | { kind: "environment"; id: string }
  | null;

interface PersistedUi {
  filters: Record<string, unknown>;
  drawer: DrawerTarget;
  settingsDraft: Partial<Settings> | null;
  route: string | null;
}

type DisplayPrefs = Pick<Settings, "locale" | "timezone">;
interface RefreshOptions {
  force?: boolean;
}

interface Toast {
  id: number;
  tone: "success" | "error" | "info";
  message: string;
  reasonCode?: string;
}

interface StoreValue {
  loading: boolean;
  slow: boolean;
  error: ApiError | null;
  offline: boolean;
  state: ObservatoryState | null;
  locale: Locale;
  timezone: string;
  /** Server-acknowledged controls, with local display preferences applied only to locale/timezone. */
  settings: Settings | null;
  busy: Record<string, boolean>;
  toasts: Toast[];
  announcement: string;
  drawer: DrawerTarget;
  setDrawer: (t: DrawerTarget) => void;
  uiFilters: <T>(route: string, initial: T) => [T, (v: T) => void];
  settingsDraft: Partial<Settings> | null;
  setSettingsDraft: (d: SetStateAction<Partial<Settings> | null>) => void;
  setLocaleImmediate: (l: Locale) => void;
  setTimezoneImmediate: (tz: string) => void;
  setPausedImmediate: (paused: boolean) => void;
  persistSettings: (next: Settings) => Promise<void>;
  doRetryJob: (id: string) => Promise<void>;
  doRollback: (id: string) => Promise<void>;
  refresh: (options?: RefreshOptions) => Promise<void>;
  dismissToast: (id: number) => void;
}

const StoreContext = createContext<StoreValue | null>(null);

function readJson<T>(key: string): T | null {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

function writeJson(key: string, value: unknown): void {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* storage may be unavailable; server persistence still works */
  }
}

function loadUi(): PersistedUi {
  const parsed = readJson<Partial<PersistedUi>>(UI_STORAGE_KEY);
  return {
    filters: parsed?.filters ?? {},
    drawer: parsed?.drawer ?? null,
    settingsDraft: parsed?.settingsDraft ?? null,
    route: parsed?.route ?? null,
  };
}

function isLocale(value: unknown): value is Locale {
  return value === "zh-CN" || value === "en";
}

/**
 * The local preference mirror is intentionally display-only. Runtime controls
 * come from `/api/state`; a stale or rejected browser form must never override
 * the server's acknowledged `paused`/`automatic_review` values.
 */
function loadDisplayPrefs(): DisplayPrefs | null {
  const parsed = readJson<Partial<Settings>>(PREFS_STORAGE_KEY);
  const next: Partial<DisplayPrefs> = {};
  if (isLocale(parsed?.locale)) next.locale = parsed.locale;
  if (typeof parsed?.timezone === "string") next.timezone = parsed.timezone;
  return Object.keys(next).length ? (next as DisplayPrefs) : null;
}

function isApiError(e: unknown): ApiError {
  if (e && typeof e === "object" && "status" in e) return e as ApiError;
  return { status: 0, message: (e as Error)?.message ?? "Unknown error" };
}

export function StoreProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<ObservatoryState | null>(null);
  const [loading, setLoading] = useState(true);
  const [slow, setSlow] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [offline, setOffline] = useState(typeof navigator !== "undefined" ? !navigator.onLine : false);
  const [busy, setBusy] = useState<Record<string, boolean>>({});
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [announcement, setAnnouncement] = useState("");
  const [ui, setUi] = useState<PersistedUi>(loadUi);
  const [localPrefs, setLocalPrefs] = useState<DisplayPrefs | null>(loadDisplayPrefs);

  const toastId = useRef(0);
  const refreshInFlight = useRef<Promise<void> | null>(null);
  const refreshController = useRef<AbortController | null>(null);
  const refreshGeneration = useRef(0);
  const pushToast = useCallback((tone: Toast["tone"], message: string, reasonCode?: string) => {
    toastId.current += 1;
    const id = toastId.current;
    setToasts((t) => [...t, { id, tone, message, reasonCode }]);
    window.setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 7000);
  }, []);
  const dismissToast = useCallback((id: number) => setToasts((t) => t.filter((x) => x.id !== id)), []);

  // Persist UI slice (filters / drawer / settings draft) so refresh keeps them.
  useEffect(() => writeJson(UI_STORAGE_KEY, ui), [ui]);

  const setDrawer = useCallback((t: DrawerTarget) => setUi((u) => ({ ...u, drawer: t })), []);

  const uiFilters = useCallback(
    <T,>(route: string, initial: T): [T, (v: T) => void] => {
      const value = (ui.filters[route] as T) ?? initial;
      const update = (v: T) => setUi((u) => ({ ...u, filters: { ...u.filters, [route]: v } }));
      return [value, update];
    },
    [ui.filters],
  );

  const setSettingsDraft = useCallback(
    (d: SetStateAction<Partial<Settings> | null>) =>
      setUi((u) => ({
        ...u,
        settingsDraft: typeof d === "function" ? d(u.settingsDraft) : d,
      })),
    [],
  );

  // Locale/timezone are local display preferences and may update optimistically.
  // Runtime controls are never sourced from this mirror.
  const serverSettings = state?.settings ?? null;
  const settings: Settings | null = serverSettings
    ? { ...serverSettings, ...(localPrefs ?? {}) }
    : null;
  const locale: Locale = localPrefs?.locale ?? serverSettings?.locale ?? DEFAULT_LOCALE;
  const timezone = localPrefs?.timezone ?? serverSettings?.timezone ?? "Asia/Shanghai";

  const persistPrefsLocal = useCallback((patch: Partial<Settings>) => {
    const displayPatch: Partial<DisplayPrefs> = {};
    if (isLocale(patch.locale)) displayPatch.locale = patch.locale;
    if (typeof patch.timezone === "string") displayPatch.timezone = patch.timezone;
    if (!Object.keys(displayPatch).length) return;

    setLocalPrefs((prev) => {
      const next = { ...(prev ?? {}), ...displayPatch } as DisplayPrefs;
      writeJson(PREFS_STORAGE_KEY, next);
      return next;
    });
  }, []);

  const refresh = useCallback((options: RefreshOptions = {}) => {
    // Normal calls join the current request, so polling and visibility events
    // cannot build a queue of duplicate full-state requests. Keep this function
    // non-async so joined callers receive the exact same Promise instance.
    if (!options.force && refreshInFlight.current) return refreshInFlight.current;

    // Mutations need a new generation after a write. Abort the older request and
    // ignore its response even if a slow transport eventually resolves.
    if (options.force) {
      refreshGeneration.current += 1;
      refreshController.current?.abort();
    }

    const generation = ++refreshGeneration.current;
    const controller = new AbortController();
    refreshController.current = controller;
    const request = (async () => {
      try {
        const next = await fetchState({ signal: controller.signal });
        if (generation !== refreshGeneration.current) return;
        setState(next);
        setError(null);
        setOffline(false);
      } catch (e) {
        if (generation !== refreshGeneration.current) return;
        const api = isApiError(e);
        if (!api.aborted) {
          setError(api);
          setOffline(Boolean(api.offline) || (typeof navigator !== "undefined" && !navigator.onLine));
        }
        throw api;
      } finally {
        if (generation === refreshGeneration.current) {
          refreshController.current = null;
          refreshInFlight.current = null;
        }
      }
    })();

    refreshInFlight.current = request;
    return request;
  }, []);

  // Boot: session cookie/CSRF first, then state. Then poll while visible.
  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;
    let slowTimer: number | undefined;

    const boot = async () => {
      setLoading(true);
      setSlow(false);
      slowTimer = window.setTimeout(() => setSlow(true), 5000);
      try {
        await establishSession();
        if (cancelled) return;
        await refresh();
      } catch (e) {
        if (!cancelled) {
          const api = isApiError(e);
          setError(api);
          setOffline(Boolean(api.offline));
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
          window.clearTimeout(slowTimer);
        }
      }
    };
    void boot();

    const onOnline = () => {
      setOffline(false);
      void boot();
    };
    const onOffline = () => setOffline(true);
    window.addEventListener("online", onOnline);
    window.addEventListener("offline", onOffline);

    const onVisible = () => {
      if (document.visibilityState === "visible" && !cancelled) {
        window.clearTimeout(timer);
        void refresh().catch(() => undefined);
      }
    };
    document.addEventListener("visibilitychange", onVisible);

    const interval = window.setInterval(() => {
      if (document.visibilityState === "visible" && navigator.onLine) {
        void refresh().catch(() => undefined);
      }
    }, POLL_MS);

    return () => {
      cancelled = true;
      window.clearInterval(interval);
      window.clearTimeout(timer);
      window.clearTimeout(slowTimer);
      window.removeEventListener("online", onOnline);
      window.removeEventListener("offline", onOffline);
      document.removeEventListener("visibilitychange", onVisible);
    };
    // boot once per mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  const setBusyKey = (key: string, value: boolean) =>
    setBusy((b) => ({ ...b, [key]: value }));

  const saveSettingsPatch = useCallback(
    async (patch: Partial<Settings>, options: { clearDraft?: boolean } = {}) => {
      setBusyKey("settings", true);
      try {
        await apiSaveSettings(patch as Settings);
        // Force a new generation instead of joining an older in-flight GET.
        await refresh({ force: true });
        if (options.clearDraft) setSettingsDraft(null);
        pushToast("success", "settings-saved");
        setAnnouncement(locale === "zh-CN" ? "设置已保存" : "Settings saved");
      } catch (e) {
        const api = isApiError(e);
        pushToast("error", "settings-save-failed", api.reason_code);
      } finally {
        setBusyKey("settings", false);
      }
    },
    [locale, pushToast, refresh, setSettingsDraft],
  );

  const persistSettings = useCallback(
    async (next: Settings) => saveSettingsPatch(next, { clearDraft: true }),
    [saveSettingsPatch],
  );

  const setLocaleImmediate = useCallback(
    (l: Locale) => {
      persistPrefsLocal({ locale: l });
      // Locale is independent of the unsaved control form. Save only this field.
      void saveSettingsPatch({ locale: l });
    },
    [persistPrefsLocal, saveSettingsPatch],
  );
  const setTimezoneImmediate = useCallback(
    (tz: string) => {
      persistPrefsLocal({ timezone: tz });
      void saveSettingsPatch({ timezone: tz });
    },
    [persistPrefsLocal, saveSettingsPatch],
  );
  const setPausedImmediate = useCallback(
    (paused: boolean) => {
      const base = settings ?? ({ locale, timezone, paused: false } as Settings);
      const next = { ...base, ...(ui.settingsDraft ?? {}), paused };
      // Keep the user's edit visible as an independent draft while the request
      // is pending; `settings.paused` remains the server-acknowledged value.
      setSettingsDraft((prev) => ({ ...(prev ?? {}), paused }));
      void persistSettings(next);
    },
    [locale, persistSettings, settings, setSettingsDraft, timezone, ui.settingsDraft],
  );

  const doRetryJob = useCallback(
    async (id: string) => {
      setBusyKey(`retry:${id}`, true);
      try {
        await apiRetryJob(id);
        await refresh({ force: true });
        pushToast("success", locale === "zh-CN" ? "任务已恢复" : "Job resumed");
        setAnnouncement(locale === "zh-CN" ? `任务 ${id} 已恢复` : `Job ${id} resumed`);
      } catch (e) {
        const api = isApiError(e);
        pushToast("error", locale === "zh-CN" ? "恢复失败" : "Retry failed", api.reason_code);
      } finally {
        setBusyKey(`retry:${id}`, false);
      }
    },
    [locale, pushToast, refresh],
  );

  const doRollback = useCallback(
    async (id: string) => {
      setBusyKey(`rollback:${id}`, true);
      try {
        await apiRollback(id);
        await refresh({ force: true });
        pushToast("success", locale === "zh-CN" ? "回滚已开始" : "Rollback started");
        setAnnouncement(locale === "zh-CN" ? `安装 ${id} 回滚已开始` : `Rollback started for ${id}`);
      } catch (e) {
        const api = isApiError(e);
        pushToast("error", locale === "zh-CN" ? "回滚失败" : "Rollback failed", api.reason_code);
      } finally {
        setBusyKey(`rollback:${id}`, false);
      }
    },
    [locale, pushToast, refresh],
  );

  const value = useMemo<StoreValue>(
    () => ({
      loading,
      slow,
      error,
      offline,
      state,
      locale,
      timezone,
      settings,
      busy,
      toasts,
      announcement,
      drawer: ui.drawer,
      setDrawer,
      uiFilters,
      settingsDraft: ui.settingsDraft,
      setSettingsDraft,
      setLocaleImmediate,
      setTimezoneImmediate,
      setPausedImmediate,
      persistSettings,
      doRetryJob,
      doRollback,
      refresh,
      dismissToast,
    }),
    [
      loading, slow, error, offline, state, locale, timezone, settings, busy, toasts, announcement,
      ui.drawer, ui.settingsDraft, setDrawer, uiFilters, setSettingsDraft, setLocaleImmediate,
      setTimezoneImmediate, setPausedImmediate, persistSettings, doRetryJob, doRollback, refresh,
      dismissToast,
    ],
  );

  return <StoreContext.Provider value={value}>{children}</StoreContext.Provider>;
}

export function useStore(): StoreValue {
  const ctx = useContext(StoreContext);
  if (!ctx) throw new Error("useStore must be used within StoreProvider");
  return ctx;
}

export function useT(): (key: string, vars?: Record<string, string | number>) => string {
  const { locale } = useStore();
  return useCallback(
    (key: string, vars?: Record<string, string | number>) => translate(locale, key, vars),
    [locale],
  );
}
