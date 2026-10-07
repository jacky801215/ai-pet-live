/**
 * usePetRuntime 编排 Hook 测试（Step 4.1-D-1 / FD-1 ~ FD-5 验收）。
 *
 * 运行：`npm test`（vitest run，node 环境、零新增依赖）。
 * 策略：三个 API 模块以 vi.mock 替换（可配置成功 / 失败）；store 用**真实** zustand store；
 *       controller / loadRuntimeData 为纯 JS，可完整测成功 / 失败 / 重拉；
 *       hook 本体经 react-dom/server 静态渲染 Probe 捕获返回值（SSR 快照读当前态，
 *       effects 不执行 —— 初始 loading 与数据投影可测）。
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { useSyncExternalStore } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../../src/api/client";
import { usePetStore } from "../../src/stores/usePetStore";
import type { EventItem, PlaybackState, StatsResponse } from "../../src/types/api";

/** API 模块 mock：默认成功返回样例数据；各用例按需改写实现。 */
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
 * store 模块 mock（与 components.test 同款）：zustand v5 的 SSR 快照读
 * getInitialState()（创建时初始态），静态渲染看不到 setState 变更。
 * 这里复用**真实** store 的 getState / setState / subscribe（行为与被测对象一致），
 * 仅把 server snapshot 指向当前态。
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

import {
  createPetRuntimeController,
  loadRuntimeData,
  usePetRuntime,
} from "../../src/hooks/usePetRuntime";

const SAMPLE_PLAYBACK: PlaybackState = {
  pet_id: "cat_001",
  state: "playing",
  action: "heart",
  asset_url: "/assets/pets/cat/actions/heart/heart.mp4",
  queue_size: 0,
  last_event: "gift",
  loop: false,
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
    created_at: "2026-09-20 12:00:00",
  };
}

const SAMPLE_RECENT = { items: [makeEvent(1), makeEvent(2)], count: 2 };
const SAMPLE_STATS: StatsResponse = { events: { gift: 5 }, actions: { heart: 5 }, total: 5 };

function mockSuccess(): void {
  apiMocks.getPlaybackState.mockResolvedValue(SAMPLE_PLAYBACK);
  apiMocks.getRecentEvents.mockResolvedValue(SAMPLE_RECENT);
  apiMocks.getStats.mockResolvedValue(SAMPLE_STATS);
}

beforeEach(() => {
  vi.clearAllMocks();
  usePetStore.setState({ playback: null, recentEvents: [], stats: null });
});

describe("loadRuntimeData（FD-1：调 API 层并整份写入 store）", () => {
  it("成功：store 三块数据被更新", async () => {
    mockSuccess();

    await loadRuntimeData();

    const state = usePetStore.getState();
    expect(state.playback).toEqual(SAMPLE_PLAYBACK);
    expect(state.recentEvents).toEqual(SAMPLE_RECENT.items);
    expect(state.stats).toEqual(SAMPLE_STATS);
    expect(apiMocks.getPlaybackState).toHaveBeenCalledTimes(1);
    expect(apiMocks.getRecentEvents).toHaveBeenCalledTimes(1);
    expect(apiMocks.getStats).toHaveBeenCalledTimes(1);
  });

  it("失败：错误**原样**向上抛出（同一实例，不改写不包装）", async () => {
    const boom = new ApiError(500, "INTERNAL_ERROR", "后端炸了");
    apiMocks.getPlaybackState.mockRejectedValue(boom);

    await expect(loadRuntimeData()).rejects.toBe(boom);
    expect(usePetStore.getState().playback).toBeNull();
  });
});

describe("createPetRuntimeController（FD-4 / FD-5：状态与手动重拉）", () => {
  it("成功路径：loading 从 true 收敛为 false，error 保持 null", async () => {
    mockSuccess();
    const controller = createPetRuntimeController();
    expect(controller.getStatus()).toEqual({ loading: true, error: null });

    await controller.refresh();

    expect(controller.getStatus()).toEqual({ loading: false, error: null });
  });

  it("失败路径：error 为原始 ApiError 实例（含 status/code），且不自动重试", async () => {
    const boom = new ApiError(400, "INVALID_REQUEST", "bad request");
    apiMocks.getPlaybackState.mockRejectedValue(boom);
    const controller = createPetRuntimeController();

    await controller.refresh();

    const status = controller.getStatus();
    expect(status.loading).toBe(false);
    expect(status.error).toBe(boom);
    expect(status.error?.name).toBe("ApiError");
    expect(apiMocks.getPlaybackState).toHaveBeenCalledTimes(1);
  });

  it("refresh 可重复调用：每次都重新拉取并更新 store", async () => {
    mockSuccess();
    const controller = createPetRuntimeController();

    await controller.refresh();
    expect(apiMocks.getPlaybackState).toHaveBeenCalledTimes(1);

    await controller.refresh();
    expect(apiMocks.getPlaybackState).toHaveBeenCalledTimes(2);
    expect(usePetStore.getState().stats).toEqual(SAMPLE_STATS);
  });
});

describe("usePetRuntime Hook（FD-3：返回值与 store 投影）", () => {
  /** SSR 静态渲染捕获 hook 返回值（effects 不执行，不触发真实请求）。 */
  function captureRuntime(): Record<string, unknown> {
    let captured: Record<string, unknown> | null = null;
    function Probe() {
      const runtime = usePetRuntime();
      captured = runtime as unknown as Record<string, unknown>;
      return null;
    }
    renderToStaticMarkup(<Probe />);
    return captured ?? {};
  }

  it("初始：loading=true、error=null、refresh 为函数", () => {
    const runtime = captureRuntime();
    expect(runtime["loading"]).toBe(true);
    expect(runtime["error"]).toBeNull();
    expect(typeof runtime["refresh"]).toBe("function");
  });

  it("store 已有数据时，三切片作为只读投影返回", () => {
    usePetStore.getState().setPlayback(SAMPLE_PLAYBACK);
    usePetStore.getState().setRecentEvents(SAMPLE_RECENT.items);
    usePetStore.getState().setStats(SAMPLE_STATS);

    const runtime = captureRuntime();
    expect(runtime["playback"]).toEqual(SAMPLE_PLAYBACK);
    expect(runtime["recentEvents"]).toEqual(SAMPLE_RECENT.items);
    expect(runtime["stats"]).toEqual(SAMPLE_STATS);
  });
});

describe("边界静态断言（FD-2 / §七）", () => {
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

  it("hook 无接口路径字面量 / 无浏览器存储 / 无计时器（剥注释后）", () => {
    const code = read("src/hooks/usePetRuntime.ts");
    expect(code).not.toContain("fetch(");
    // 允许 hooks -> api 层模块 import；此处约束的是接口 URL 字面量（带引号的路径串）
    expect(code).not.toContain('"/api/');
    expect(code).not.toContain("localStorage");
    expect(code).not.toContain("sessionStorage");
    expect(code).not.toContain("setInterval");
    expect(code).not.toContain("setTimeout");
  });

  it("hook 不 import 组件（编排层不依赖 UI）", () => {
    const code = read("src/hooks/usePetRuntime.ts");
    expect(code).not.toMatch(/from\s+["'][^"']*components/);
  });

  it("hook 只依赖 api 层与 store（import 白名单）", () => {
    const code = read("src/hooks/usePetRuntime.ts");
    const imports = [...code.matchAll(/from\s+["']([^"']+)["']/g)].map((m) => m[1]);
    expect(imports).toEqual([
      "react",
      "../api/events",
      "../api/playback",
      "../api/stats",
      "../stores/usePetStore",
    ]);
  });

  it("App 只引入组件与 usePetRuntime；不触 API 层、不写 store setter", () => {
    const code = read("src/App.tsx");
    const imports = [...code.matchAll(/from\s+["']([^"']+)["']/g)].map((m) => m[1]);
    // F-1（用户裁决同步扩展）：ES-1 局部修订 FCM-2 增补第五件组件 EventSimulator，
    // App 作为组合根挂载它（经 onTrigger 注入 hook 编排，ES-2）。
    // PC-1（Phase 2.2-6 受权增量）：App 额外挂载 push channel 生命周期钩子 useRuntimePush
    // （mount → connect / cleanup → close）；App 仍不 import API 层、不写 store setter。
    // MPF-5（Phase 3.2-B 受权增量）：再增补 PetSelector 组件与 usePetContext 钩子。
    // CR-4（受权增量，FCM-2 v1.1）：再增补 AiContentLabel 组件（AI 生成内容标识，仅 ready 态渲染）。
    // CR-11（受权增量）：再增补 usePlaybackAudio 钩子（音效帧 → 播放模块接线，App 作组合根挂载）。
    expect(imports).toEqual([
      "./components/AiContentLabel",
      "./components/EventList",
      "./components/EventSimulator",
      "./components/PetSelector",
      "./components/PetStage",
      "./components/StatusBar",
      "./hooks/usePetContext",
      "./hooks/usePetRuntime",
      "./hooks/usePlaybackAudio",
      "./hooks/useRuntimePush",
    ]);
    expect(code).not.toContain("usePetStore");
    expect(code).not.toContain("setPlayback");
    expect(code).not.toContain("setRecentEvents");
    expect(code).not.toContain("setStats");
    expect(code).not.toContain("setSelectedPet");
  });

  it("store 保持冻结形状：无网络请求 / 无生命周期钩子 / 无拉取方法", () => {
    const code = read("src/stores/usePetStore.ts");
    expect(code).not.toContain("fetch");
    expect(code).not.toContain("useEffect");
    expect(code).not.toMatch(/load[A-Z]/);
    expect(code).not.toMatch(/refresh[A-Z]/);
  });
});
