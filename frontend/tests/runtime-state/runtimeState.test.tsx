/**
 * 页面 runtime 状态表达测试（Step 4.1-D-3 / RS-1 ~ RS-5 验收）。
 *
 * 四态：loading / error / empty / ready。组合优先级 error ↓ loading ↓ ready。
 * 策略与 runtime 集成测试一致：API 三模块 vi.mock + 真实 store + controller 注入
 * （SSR 无 effects，注入使 App 与被 await 的是同一 controller；生产零参不变）。
 */

import { useSyncExternalStore } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../../src/api/client";
import App from "../../src/App";
import { createPetRuntimeController } from "../../src/hooks/usePetRuntime";
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
    created_at: "2026-09-20 13:20:00",
  };
}

const SAMPLE_RECENT = { items: [makeEvent(1)], count: 1 };
const SAMPLE_STATS: StatsResponse = { events: { gift: 3 }, actions: { heart: 3 }, total: 3 };

beforeEach(() => {
  vi.clearAllMocks();
  usePetStore.setState({ playback: null, recentEvents: [], stats: null });
});

describe("Case 1 Loading（RS-2：统一页面加载区）", () => {
  it("loading=true 时页面展示统一加载区，不渲染业务组件", () => {
    // 零参 App：controller 初始 loading=true（SSR 不执行 effects，恰为挂载首帧）
    const html = renderToStaticMarkup(<App />);

    expect(html).toContain('data-testid="app-loading"');
    expect(html).toContain("加载中");
    expect(html).not.toContain('data-testid="pet-stage"');
    expect(html).not.toContain('data-testid="app-error"');
  });
});

describe("Case 2 Error（RS-3：status / code / message 原样保留）", () => {
  it("error 态页面完整展示 ApiError 三元组，不渲染业务组件", async () => {
    const boom = new ApiError(500, "INTERNAL_ERROR", "后端不可用");
    apiMocks.getPlaybackState.mockRejectedValue(boom);

    const controller = createPetRuntimeController();
    await controller.refresh();

    const html = renderToStaticMarkup(<App controller={controller} />);

    expect(html).toContain('data-testid="app-error"');
    expect(html).toContain("互动服务出错");
    expect(html).toContain("500"); // status 原样
    expect(html).toContain("INTERNAL_ERROR"); // code 原样
    expect(html).toContain("后端不可用"); // message 原样
    expect(html).not.toContain('data-testid="pet-stage"');
    expect(html).not.toContain('data-testid="app-loading"');
  });
});

describe("Case 3 Empty（RS-4：空数据由既有组件空态表达）", () => {
  it("ready 态 + 空数据：页面不 crash，三组件各自展示暂无文案", async () => {
    // 模拟「服务端返回空」：加载成功但切片全空
    apiMocks.getPlaybackState.mockResolvedValue(null);
    apiMocks.getRecentEvents.mockResolvedValue({ items: [], count: 0 });
    apiMocks.getStats.mockResolvedValue(null);

    const controller = createPetRuntimeController();
    await controller.refresh();

    const state = usePetStore.getState();
    expect(state.playback).toBeNull();
    expect(state.recentEvents).toEqual([]);
    expect(state.stats).toBeNull();

    const html = renderToStaticMarkup(<App controller={controller} />);

    expect(html).toContain('data-phase="components"'); // ready 布局
    expect(html).toContain("暂无宠物画面"); // PetStage 空态
    expect(html).toContain("暂无播放内容"); // PetPlayer 空态
    expect(html).toContain("暂无最近事件"); // EventList 空态
    expect(html).toContain("暂无统计数据"); // StatusBar 空态
  });
});

describe("Case 4 Ready（数据齐备，三组件继续展示）", () => {
  it("注入完整数据后，ready 布局下 PetStage / StatusBar / EventList 正常消费", async () => {
    apiMocks.getPlaybackState.mockResolvedValue(SAMPLE_PLAYBACK);
    apiMocks.getRecentEvents.mockResolvedValue(SAMPLE_RECENT);
    apiMocks.getStats.mockResolvedValue(SAMPLE_STATS);

    const controller = createPetRuntimeController();
    await controller.refresh();

    const html = renderToStaticMarkup(<App controller={controller} />);

    expect(html).toContain('data-phase="components"');
    expect(html).toContain('data-testid="pet-stage"'); // PetStage
    expect(html).toContain('data-testid="status-bar"'); // StatusBar
    expect(html).toContain('data-testid="event-list"'); // EventList
    expect(html).toContain("cat_001");
    expect(html).toContain('src="/assets/pets/cat/actions/heart/heart.mp4"');
    expect(html).toContain("gift:3");
    expect(html).toContain("2026-09-20 13:20:00");
  });
});

