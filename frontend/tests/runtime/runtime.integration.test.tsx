/**
 * 运行时联通集成测试（Step 4.1-D-2 / RV-1 ~ RV-5 验收）。
 *
 * 链路：API 层（vi.mock）→ usePetRuntime 的 loadRuntimeData/controller → 真实 zustand store
 *       → 真实组件 / App（react-dom/server 静态渲染，零新增依赖）。
 * 已知限制（RV 文档已记录）：静态渲染不执行 effects，挂载触发的「那一次」加载
 * 在 controller 层验证（refresh 即 hook 挂载调用的同一函数）。
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { useSyncExternalStore } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../../src/api/client";
import { usePetStore } from "../../src/stores/usePetStore";
import type { EventItem, PlaybackState, StatsResponse } from "../../src/types/api";

/** API 三模块 mock（唯一 mock 面：传输不落地，其余全链路真实）。 */
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

/**
 * store 模块 mock（同 hooks 测试）：zustand v5 的 SSR 快照读 getInitialState()，
 * 复用真实 store 的 getState / setState / subscribe，仅把 server snapshot 指向当前态。
 */
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

import App from "../../src/App";
import {
  createPetRuntimeController,
  usePetRuntime,
} from "../../src/hooks/usePetRuntime";

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
    created_at: "2026-09-20 13:00:00",
  };
}

/** 静态渲染捕获 hook 返回值（可注入同一 controller，使 await 的实例与 hook 使用的一致）。 */
function captureRuntime(
  controller?: ReturnType<typeof createPetRuntimeController>,
): Record<string, unknown> {
  let captured: Record<string, unknown> | null = null;
  function Probe() {
    const runtime = usePetRuntime(controller ? { controller } : undefined);
    captured = runtime as unknown as Record<string, unknown>;
    return null;
  }
  renderToStaticMarkup(<Probe />);
  return captured ?? {};
}

beforeEach(() => {
  vi.clearAllMocks();
  usePetStore.setState({ playback: null, recentEvents: [], stats: null });
});

describe("Case 1 首次加载（RV-2：mount → loadRuntimeData 恰一次）", () => {
  it("loading true → false 转移，store 三字段更新，hook 投影一致", async () => {
    apiMocks.getPlaybackState.mockResolvedValue(SAMPLE_PLAYBACK);
    apiMocks.getRecentEvents.mockResolvedValue({ items: [makeEvent(1)], count: 1 });
    apiMocks.getStats.mockResolvedValue({ events: { gift: 1 }, actions: {}, total: 1 });

    const controller = createPetRuntimeController();
    const transitions: boolean[] = [];
    controller.subscribe(() => transitions.push(controller.getStatus().loading));

    expect(controller.getStatus().loading).toBe(true); // 挂载即拉取的初始态
    const before = captureRuntime(controller);
    expect(before["loading"]).toBe(true);
    expect(before["error"]).toBeNull();

    await controller.refresh(); // hook 挂载 effect 调用的正是这同一函数

    const after = captureRuntime(controller);
    expect(after["loading"]).toBe(false);
    expect(after["error"]).toBeNull();
    expect(after["playback"]).toEqual(SAMPLE_PLAYBACK);
    expect(after["recentEvents"]).toEqual([makeEvent(1)]);
    expect(after["stats"]).toEqual({ events: { gift: 1 }, actions: {}, total: 1 });

    const state = usePetStore.getState();
    expect(state.playback).toEqual(SAMPLE_PLAYBACK);
    expect(state.recentEvents).toEqual([makeEvent(1)]);
    expect(state.stats).toEqual({ events: { gift: 1 }, actions: {}, total: 1 });

    // 恰一次收敛：refresh 开始 emit（loading 仍 true）→ 结束 emit（false），无重复触发
    expect(transitions).toEqual([true, false]);
    expect(apiMocks.getPlaybackState).toHaveBeenCalledTimes(1);
    expect(apiMocks.getRecentEvents).toHaveBeenCalledTimes(1);
    expect(apiMocks.getStats).toHaveBeenCalledTimes(1);
  });
});

describe("Case 2 APIError（RV-4：原样可见）", () => {
  it("hook.error === 同一 ApiError 实例（status/code/message 不被改写）", async () => {
    const boom = new ApiError(500, "INTERNAL_ERROR", "后端不可用");
    apiMocks.getPlaybackState.mockRejectedValue(boom);

    const controller = createPetRuntimeController();
    await controller.refresh();

    const runtime = captureRuntime(controller);
    expect(runtime["error"]).toBe(boom);
    expect((runtime["error"] as ApiError).status).toBe(500);
    expect((runtime["error"] as ApiError).code).toBe("INTERNAL_ERROR");
    expect((runtime["error"] as ApiError).message).toBe("后端不可用");
    expect(runtime["loading"]).toBe(false);
  });
});

describe("Case 3 refresh（RV-3：manual caller → hook → API → store）", () => {
  it("第一次 stats.total=1，refresh 后 stats.total=2，store 与 hook 投影随之更新", async () => {
    apiMocks.getPlaybackState.mockResolvedValue(SAMPLE_PLAYBACK);
    apiMocks.getRecentEvents.mockResolvedValue({ items: [], count: 0 });
    apiMocks.getStats.mockResolvedValueOnce({ events: {}, actions: {}, total: 1 });

    const controller = createPetRuntimeController();
    await controller.refresh();
    expect(usePetStore.getState().stats?.total).toBe(1);
    expect(captureRuntime(controller)["stats"]).toEqual({ events: {}, actions: {}, total: 1 });

    apiMocks.getStats.mockResolvedValueOnce({ events: {}, actions: {}, total: 2 });
    await controller.refresh();

    expect(usePetStore.getState().stats?.total).toBe(2);
    expect(captureRuntime(controller)["stats"]).toEqual({ events: {}, actions: {}, total: 2 });
    expect(controller.getStatus().error).toBeNull();
    expect(apiMocks.getStats).toHaveBeenCalledTimes(2);
  });
});

describe("Case 4 App 集成（RV-1：唯一入口，子组件消费 store）", () => {
  it("渲染 App（ready 态，注入已收敛 controller）无 crash，Stage / StatusBar / EventList 正常消费 store 数据", async () => {
    apiMocks.getPlaybackState.mockResolvedValue(SAMPLE_PLAYBACK);
    apiMocks.getRecentEvents.mockResolvedValue({ items: [makeEvent(1)], count: 1 });
    apiMocks.getStats.mockResolvedValue({ events: { gift: 3 }, actions: { heart: 3 }, total: 3 });

    const controller = createPetRuntimeController();
    await controller.refresh(); // ready：loading 收敛、error 为 null

    const html = renderToStaticMarkup(<App controller={controller} />);

    expect(html).toContain('data-phase="components"');
    expect(html).toContain("cat_001"); // PetStage/PetPlayer 消费 playback
    expect(html).toContain('src="/assets/pets/cat/actions/heart/heart.mp4"'); // 只消费 asset_url
    expect(html).toContain("gift:3"); // StatusBar 事件分布
    expect(html).toContain("gift"); // EventList event_type
    expect(html).toContain("2026-09-20 13:00:00"); // EventList created_at
  });

  it("App 为唯一数据入口：渲染本身不触发 API 调用（数据获取只在 hook）", () => {
    renderToStaticMarkup(<App />);
    expect(apiMocks.getPlaybackState).not.toHaveBeenCalled();
    expect(apiMocks.getRecentEvents).not.toHaveBeenCalled();
    expect(apiMocks.getStats).not.toHaveBeenCalled();
  });

  it("App 零参渲染（SSR 首帧）呈现统一加载区（RS-2）；真实浏览器中 effects 收敛后进入 ready/error", () => {
    const html = renderToStaticMarkup(<App />);
    expect(html).toContain('data-testid="app-loading"');
  });
});

describe("静态边界（§五）", () => {
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

  it("App 只 import 组件与 usePetRuntime；禁 API import 与 store setter", () => {
    const app = read("src/App.tsx");
    const imports = [...app.matchAll(/from\s+["']([^"']+)["']/g)].map((m) => m[1]);
    expect(imports).toEqual([
      "./components/EventList",
      "./components/PetStage",
      "./components/StatusBar",
      "./hooks/usePetRuntime",
    ]);
    expect(app).not.toContain("usePetStore");
    for (const setter of ["setPlayback", "setRecentEvents", "setStats"]) {
      expect(app).not.toContain(setter);
    }
  });

  it("组件目录零 API import（允许 import store）", () => {
    const files = [
      "src/components/PetStage.tsx",
      "src/components/EventList.tsx",
      "src/components/StatusBar.tsx",
      "src/components/player/PetPlayer.tsx",
    ];
    for (const rel of files) {
      const code = read(rel);
      expect(code, rel).not.toMatch(/from\s+["'][^"']*api/);
      expect(code, rel).toMatch(/usePetStore/); // 数据只来自 store
    }
  });
});
