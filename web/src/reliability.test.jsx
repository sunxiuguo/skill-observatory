import {afterEach, beforeEach, describe, expect, test, vi} from 'vitest';
import {act, cleanup, render, screen, waitFor} from '@testing-library/react';
import {StoreProvider, useStore} from './store.tsx';
import {establishSession, fetchState, saveSettings} from './api.ts';

vi.mock('./api.ts', () => ({
  establishSession: vi.fn(async () => ({csrf: 'fixture'})),
  fetchState: vi.fn(),
  saveSettings: vi.fn(),
  retryJob: vi.fn(),
  rollbackInstallation: vi.fn(),
}));

let current;
function View() {
  current = useStore();
  return <output data-testid="paused">{String(current.settings?.paused)}</output>;
}

function stateWith(paused) {
  return {
    settings: {locale: 'zh-CN', timezone: 'Asia/Shanghai', paused, automatic_review: true},
    metrics: {observed_runs: 0, reviewed_runs: 0, triaged_runs: 0, global_coverage: null, queued_jobs: 0, daemon_running: true, window_start: null, window_end: null},
    skills: [], runs: [], reviews: [], experiments: [], installations: [], jobs: [], environments: [], capabilities: {},
  };
}

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
});

afterEach(() => {
  cleanup();
  current = null;
  vi.clearAllMocks();
});

describe('server-acknowledged settings controls', () => {
  test('failed save keeps the draft but never projects a fake pause after refresh or remount', async () => {
    fetchState.mockResolvedValue(stateWith(false));
    saveSettings.mockRejectedValue({status: 500, message: 'synthetic server failure'});

    render(<StoreProvider><View/></StoreProvider>);
    await waitFor(() => expect(current.state?.settings.paused).toBe(false));

    await act(async () => {
      current.setPausedImmediate(true);
    });
    await waitFor(() => expect(current.busy.settings).toBe(false));

    expect(current.settings.paused).toBe(false);
    expect(current.state.settings.paused).toBe(false);
    expect(current.settingsDraft).toEqual({paused: true});
    expect(JSON.parse(localStorage.getItem('so.prefs.v1') || '{}')).not.toHaveProperty('paused');

    await act(async () => {
      await current.refresh();
    });
    expect(current.settings.paused).toBe(false);
    expect(screen.getByTestId('paused').textContent).toBe('false');

    cleanup();
    render(<StoreProvider><View/></StoreProvider>);
    await waitFor(() => expect(current.state?.settings.paused).toBe(false));
    expect(current.settings.paused).toBe(false);
    expect(current.settingsDraft).toEqual({paused: true});
    expect(screen.getByTestId('paused').textContent).toBe('false');
  });

  test('a successful save clears the draft only after a new-generation server readback', async () => {
    fetchState
      .mockResolvedValueOnce(stateWith(false))
      .mockResolvedValueOnce(stateWith(true));
    saveSettings.mockResolvedValueOnce(undefined);

    render(<StoreProvider><View/></StoreProvider>);
    await waitFor(() => expect(current.settings?.paused).toBe(false));

    await act(async () => {
      current.setPausedImmediate(true);
    });
    await waitFor(() => expect(current.settings?.paused).toBe(true));
    await waitFor(() => expect(current.settingsDraft).toBeNull());
    expect(current.state.settings.paused).toBe(true);
    expect(saveSettings).toHaveBeenCalledWith(expect.objectContaining({paused: true}));
  });
});

describe('state transport singleflight and generation', () => {
  test('concurrent refreshes join one request and an older response cannot overwrite a newer one', async () => {
    const deferred = [];
    fetchState.mockImplementation(({signal}) => new Promise((resolve, reject) => {
      deferred.push({resolve, reject, signal});
    }));

    render(<StoreProvider><View/></StoreProvider>);
    await waitFor(() => expect(fetchState).toHaveBeenCalledTimes(1));

    const joinedFirst = current.refresh();
    const joinedSecond = current.refresh();
    expect(joinedFirst).toBe(joinedSecond);
    expect(fetchState).toHaveBeenCalledTimes(1);

    let forced;
    act(() => {
      forced = current.refresh({force: true});
    });
    expect(fetchState).toHaveBeenCalledTimes(2);
    expect(deferred[0].signal.aborted).toBe(true);
    expect(deferred[1].signal.aborted).toBe(false);

    await act(async () => {
      deferred[1].resolve(stateWith(false));
      await forced;
    });
    expect(current.state.settings.paused).toBe(false);

    await act(async () => {
      deferred[0].resolve(stateWith(true));
      await joinedFirst;
    });
    expect(current.state.settings.paused).toBe(false);
    expect(current.error).toBeNull();
    expect(fetchState).toHaveBeenCalledTimes(2);
  });
});

describe('real API transport edge cases', () => {
  const nativeFetch = globalThis.fetch;

  afterEach(() => {
    globalThis.fetch = nativeFetch;
  });

  test('a dead session is re-established once and the fresh token is retained', async () => {
    sessionStorage.setItem('so.csrf', 'stale-token');
    let stateCalls = 0;
    globalThis.fetch = vi.fn(async (input) => {
      const url = String(input);
      if (url === '/api/session') {
        return new Response(JSON.stringify({csrf: 'fresh-token'}), {status: 200, headers: {'content-type': 'application/json'}});
      }
      stateCalls += 1;
      if (stateCalls === 1) {
        return new Response(JSON.stringify({reason_code: 'SESSION_REQUIRED'}), {status: 401, headers: {'content-type': 'application/json'}});
      }
      return new Response(JSON.stringify(stateWith(false)), {status: 200, headers: {'content-type': 'application/json'}});
    });

    const actualApi = await vi.importActual('./api.ts');
    const result = await actualApi.fetchState();
    expect(result.settings.paused).toBe(false);
    expect(stateCalls).toBe(2);
    expect(globalThis.fetch).toHaveBeenCalledTimes(3);
    expect(sessionStorage.getItem('so.csrf')).toBe('fresh-token');
  });

  test('an aborted state fetch propagates the caller-owned signal', async () => {
    globalThis.fetch = vi.fn((_input, init) => new Promise((_resolve, reject) => {
      init.signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')));
    }));
    const controller = new AbortController();
    const actualApi = await vi.importActual('./api.ts');
    const pending = actualApi.fetchState({signal: controller.signal});
    controller.abort();
    await expect(pending).rejects.toMatchObject({status: 0, message: 'ABORTED', aborted: true, offline: false});
    expect(globalThis.fetch.mock.calls[0][1].signal).toBe(controller.signal);
  });

  test('offline fails before a network request is attempted', async () => {
    const originalOnline = navigator.onLine;
    Object.defineProperty(navigator, 'onLine', {value: false, configurable: true});
    globalThis.fetch = vi.fn();
    try {
      const actualApi = await vi.importActual('./api.ts');
      await expect(actualApi.fetchState()).rejects.toMatchObject({status: 0, message: 'OFFLINE', offline: true});
      expect(globalThis.fetch).not.toHaveBeenCalled();
    } finally {
      Object.defineProperty(navigator, 'onLine', {value: originalOnline, configurable: true});
    }
  });
});
