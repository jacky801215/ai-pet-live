/**
 * 人工刷新边界测试（Step 4.1-D-4 / RF-1 ~ RF-5 验收）。
 *
 * 链路：用户操作 ↓ App/UI ↓ usePetRuntime.refresh() ↓ API Client ↓ Store ↓ Components。
 * 点击等价模拟（RF 文档已记录）：静态渲染无法派发 DOM 事件（无 jsdom、零新增依赖），
 * 以调用按钮 onClick 绑定的同一函数引用（注入同一 controller 后经 probe 捕获的
 * hook 返回值 refresh）等价触发；按钮存在性 / 位置 / 文案由 ready 分支 markup 断言。
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { useSyncExternalStore } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../../src/api/client";
import App from "../../src/App";
import {
  createPetRuntimeController,
  usePetRuntime,
} from "../../src/hooks/usePetRuntime";
import { usePetStore } from "../../src/stores/usePetStore";
import type { EventItem, PlaybackState, StatsResponse } from "../../src/types/api";

const apiMocks = vi.hoisted(() => ({
  getPlaybackState: vi.fn(),
  getRecentEvents: vi.fn(),
  getStats: vi.fn(),
}));

vi.mock("../../src/api/playback", () => ({
  getPlaybackState: apiMocks.getPlaybackState,
}));
vi.mock("../../src/api/events", () => ({
  simulateEvent: vi.fn(),
  getRecentEvents: apiMocks.getRecentEvents,
}));
vi.mock("../../src/api/stats", () => ({
  getStats: apiMocks.getStats,
}));

/** store 模块 mock（同前）：SSR 快照读当前态，行为仍是真实 store。 */
vi.mock("../../src/stores/usePetStore", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("../../src/stores/usePetStore")>();
  const real = actual.usePetStore;
  const hooked = (selector?: (state: ReturnType<typeof real.getState>) => unknown) =>
    useSyncExternalStore(
      real.subscribe,
      () => (selector ? selector(real.getState()) : real.getState()),
      () => (selector ? selector(real.getState()) : real.getState()),
    );
  const usePetStoreMock = Object.assign(hooked, {
    getState: real.getState.bind(real),
    setState: real.setState.bind(real),
    subscribe: real.subscribe.bind(real),
    getInitialState: real.getInitialState.bind(real),
  });
  return { usePetStore: usePetStoreMock };
});

const SAMPLE_PLAYBACK: PlaybackState = {
  pet_id: "cat_001",
  state: "playing",
  action: "heart",
  asset_url: "/assets/pets/cat/actions/heart/heart.mp4",
  queue_size: 0,
  last_event: "gift",
};

function makeEvent(id: number): EventItem {
  return {
    id,
    event_type: "gift",
    user_id: "u_1",
    user_name: "Tom",
    pet_id: "cat_001",
    action_name: "heart",
    platform: "simulator",
    payload: {},
    created_at: "2026-09-20 13:35:00",
  };
}

const SAMPLE_RECENT = { items: [makeEvent(1)], count: 1 };

function mockSuccess(stats: StatsResponse): void {
  apiMocks.getPlaybackState.mockResolvedValue(SAMPLE_PLAYBACK);
  apiMocks.getRecentEvents.mockResolvedValue(SAMPLE_RECENT);
  apiMocks.getStats.mockResolvedValue(stats);
}

/** 经 probe 捕获 hook 返回的 refresh（与按钮 onClick 绑定的是同一函数引用来源）。 */
function captureRefresh(controller: ReturnType<typeof createPetRuntimeController>) {
  let captured: { refresh: () => Promise<void>; loading: boolean; error: unknown } | null =
    null;
  function Probe() {
    const runtime = usePetRuntime({ controller });
    captured = {
      refresh: runtime.refresh,
      loading: runtime.loading,
      error: runtime.error,
    };
    return null;
  }
  renderToStaticMarkup(<Probe />);
  return captured as { refresh: () => Promise<void>; loading: boolean; error: unknown };
}

beforeEach(() => {
  vi.clearAllMocks();
  usePetStore.setState({ playback: null, recentEvents: [], stats: null });
});

describe("Case 1 点击刷新（RF-2：button click ↓ refresh 恰一次）", () => {
  it("ready 分支包含刷新按钮；触发调用 refresh 恰一次（API 各 +1 次）", async () => {
    mockSuccess({ events: {}, actions: {}, total: 1 });
    const controller = createPetRuntimeController();
    await controller.refresh(); // 初始加载

    const calls: number[] = [];
    const real = controller.refresh.bind(controller);
    controller.refresh = vi.fn(() => {
      calls.push(calls.length + 1);
      return real();
    });

    // ready 分支按钮存在性断言
    const html = renderToStaticMarkup(<App controller={controller} />);
    expect(html).toContain('data-testid="app-refresh"');
    expect(html).toContain("刷新");
    expect(html).toContain('data-testid="app-toolbar"');

    // 点击等价模拟：按钮 onClick 绑定的同一函数引用
    const runtime = captureRefresh(controller);
    await runtime.refresh();

    expect(calls).toEqual([1]);
    expect(apiMocks.getPlaybackState).toHaveBeenCalledTimes(2); // 初始 1 + 刷新 1
    expect(apiMocks.getStats).toHaveBeenCalledTimes(2);
  });
});

describe("Case 2 刷新成功（RF-3：复用 hook loading，store 更新）", () => {
  it("第一次 total=1，刷新后 total=2，store 与页面随之更新", async () => {
    mockSuccess({ events: {}, actions: {}, total: 1 });
    const controller = createPetRuntimeController();
    await controller.refresh();
    expect(usePetStore.getState().stats?.total).toBe(1);

    mockSuccess({ events: {}, actions: {}, total: 2 });
    const runtime = captureRefresh(controller);
    await runtime.refresh(); // 点击等价

    expect(usePetStore.getState().stats?.total).toBe(2);
    expect(runtime.loading).toBe(false);
    expect(runtime.error).toBeNull();

    const html = renderToStaticMarkup(<App controller={controller} />);
    expect(html).toContain("互动总数 2"); // StatusBar 消费刷新后的 store
    expect(html).toContain('data-phase="components"');
    expect(html).toContain("cat_001"); // 刷新后组件消费最新 store
  });
});

describe("Case 3 刷新失败（RF-4：ApiError 原样进入 error）", () => {
  it("刷新后页面切换到错误区，完整展示 status / code / message", async () => {
    mockSuccess({ events: {}, actions: {}, total: 1 });
    const controller = createPetRuntimeController();
    await controller.refresh(); // 先成功进入 ready

    const boom = new ApiError(503, "SERVICE_UNAVAILABLE", "刷新失败：服务暂不可用");
    apiMocks.getPlaybackState.mockRejectedValue(boom);

    const runtime = captureRefresh(controller);
    await runtime.refresh(); // 点击等价：失败

    const html = renderToStaticMarkup(<App controller={controller} />);

    expect(html).toContain('data-testid="app-error"'); // RS 优先级：error 覆盖 ready
    expect(html).toContain("503");
    expect(html).toContain("SERVICE_UNAVAILABLE");
    expect(html).toContain("刷新失败：服务暂不可用");
  });
});

describe("Case 4 边界（RF-1 / RF-3 / §五静态核验）", () => {
  /** 剥离块注释与行注释 —— 守卫约束的是代码，注释里的禁止性说明是合法的。 */
  function stripComments(source: string): string {
    return source
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .replace(/^\s*\/\/.*$/gm, "");
  }

  function read(rel: string): string {
    return stripComments(
      readFileSync(fileURLToPath(new URL(`../../${rel}`, import.meta.url)), "utf-8"),
    );
  }

  it("App 允许 usePetRuntime + refresh()；禁 API import / store setter / fetch / 本地 useState", () => {
    const app = read("src/App.tsx");
    expect(app).toContain("usePetRuntime");
    expect(app).toContain("runtime.refresh()");
    expect(app).not.toMatch(/from\s+["'][^"']*api/);
    for (const setter of ["setPlayback", "setRecentEvents", "setStats"]) {
      expect(app).not.toContain(setter);
    }
    expect(app).not.toContain("fetch(");
    expect(app).not.toContain("useState("); // RF-3：无本地 state
  });

  it("组件目录零 API import / 零 hooks import / 零刷新逻辑", () => {
    const files = [
      "src/components/PetStage.tsx",
      "src/components/EventList.tsx",
      "src/components/StatusBar.tsx",
      "src/components/player/PetPlayer.tsx",
    ];
    for (const rel of files) {
      const code = read(rel);
      expect(code, rel).not.toMatch(/from\s+["'][^"']*api/);
      expect(code, rel).not.toMatch(/from\s+["'][^"']*usePetRuntime/);
      expect(code, rel).not.toContain("refresh");
      expect(code, rel).not.toContain("fetch(");
    }
  });
});
