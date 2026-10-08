import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
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
  settings: Settings | null;
  busy: Record<string, boolean>;
  toasts: Toast[];
  announcement: string;
  drawer: DrawerTarget;
  setDrawer: (t: DrawerTarget) => void;
  uiFilters: <T>(route: string, initial: T) => [T, (v: T) => void];
  settingsDraft: Partial<Settings> | null;
  setSettingsDraft: (d: Partial<Settings> | null) => void;
  setLocaleImmediate: (l: Locale) => void;
  setTimezoneImmediate: (tz: string) => void;
  setPausedImmediate: (paused: boolean) => void;
  persistSettings: (next: Settings) => Promise<void>;
  doRetryJob: (id: string) => Promise<void>;
  doRollback: (id: string) => Promise<void>;
  refresh: () => Promise<void>;
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
  const [localPrefs, setLocalPrefs] = useState<Partial<Settings> | null>(
    () => readJson<Partial<Settings>>(PREFS_STORAGE_KEY),
  );

  const toastId = useRef(0);
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
    (d: React.SetStateAction<Partial<Settings> | null>) =>
      setUi((u) => ({
        ...u,
        settingsDraft: typeof d === "function" ? d(u.settingsDraft) : d,
      })),
    [],
  );

  // Locale/timezone resolution: server settings are the durable truth; a local
  // mirror lets the UI switch instantly before the first response and offline.
  const serverSettings = state?.settings ?? null;
  const settings: Settings | null = serverSettings
    ? { ...serverSettings, ...(localPrefs ?? {}) }
    : localPrefs
      ? ({ locale: DEFAULT_LOCALE, timezone: "Asia/Shanghai", paused: false, ...localPrefs } as Settings)
      : null;
  const locale: Locale = settings?.locale ?? DEFAULT_LOCALE;
  const timezone = settings?.timezone ?? "Asia/Shanghai";

  const persistPrefsLocal = useCallback((patch: Partial<Settings>) => {
    setLocalPrefs((prev) => {
      const next = { ...(prev ?? {}), ...patch };
      writeJson(PREFS_STORAGE_KEY, next);
      return next;
    });
  }, []);

  const refresh = useCallback(async () => {
    try {
      const next = await fetchState();
      setState(next);
      setError(null);
      setOffline(false);
    } catch (e) {
      const api = isApiError(e);
      setError(api);
      setOffline(Boolean(api.offline) || (typeof navigator !== "undefined" && !navigator.onLine));
      throw api;
    }
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

  const persistSettings = useCallback(
    async (next: Settings) => {
      persistPrefsLocal(next);
      setBusyKey("settings", true);
      try {
        await apiSaveSettings(next);
        await refresh();
        setSettingsDraft(null);
        pushToast("success", "settings-saved");
        setAnnouncement(locale === "zh-CN" ? "设置已保存" : "Settings saved");
      } catch (e) {
        const api = isApiError(e);
        pushToast("error", "settings-save-failed", api.reason_code);
      } finally {
        setBusyKey("settings", false);
      }
    },
    [locale, persistPrefsLocal, pushToast, refresh, setSettingsDraft],
  );

  const setLocal = useCallback(
    (patch: Partial<Settings>) => {
      // Optimistic, local-first; flushed to server with persistSettings.
      persistPrefsLocal(patch);
      setSettingsDraft((prev) => ({ ...(prev ?? {}), ...patch }));
      return { ...(settings ?? ({ locale: DEFAULT_LOCALE, timezone: "Asia/Shanghai", paused: false } as Settings)), ...patch };
    },
    [persistPrefsLocal, setSettingsDraft, settings],
  );

  const setLocaleImmediate = useCallback(
    (l: Locale) => {
      persistPrefsLocal({ locale: l });
      // Locale is independent of the unsaved form. Never clear or submit it.
      void apiSaveSettings({ locale: l } as Settings).then(refresh).catch((e) => {
        pushToast("error", "settings-save-failed", isApiError(e).reason_code);
      });
    },
    [persistPrefsLocal, refresh, pushToast],
  );
  const setTimezoneImmediate = useCallback(
    (tz: string) => {
      const merged = setLocal({ timezone: tz });
      void persistSettings(merged);
    },
    [persistSettings, setLocal],
  );
  const setPausedImmediate = useCallback(
    (paused: boolean) => {
      const merged = setLocal({ paused });
      void persistSettings(merged);
    },
    [persistSettings, setLocal],
  );

  const doRetryJob = useCallback(
    async (id: string) => {
      setBusyKey(`retry:${id}`, true);
      try {
        await apiRetryJob(id);
        await refresh();
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
        await refresh();
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
