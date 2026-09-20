/**
 * 事件模拟器边界测试（Step 4.1-F-1 / ES-1 ~ ES-5 验收）。
 *
 * 链路（ES-2）：click ↓ triggerEvent() ↓ simulateEvent() ↓ loadRuntimeData() ↓ store ↓ components。
 * 零依赖测试（同 RF / RS 范式）：react-dom/server 静态渲染 + vi.mock API 模块 + 真实 store mock；
 * 点击等价模拟 = 直接调用 hook 返回的同一 triggerEvent 函数引用。
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { useSyncExternalStore } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../../src/api/client";
import App from "../../src/App";
import EventSimulator, {
  SIMULATOR_EVENT_TYPES,
} from "../../src/components/EventSimulator";
import {
  createPetRuntimeController,
  usePetRuntime,
} from "../../src/hooks/usePetRuntime";
import { usePetStore } from "../../src/stores/usePetStore";
import type { EventItem, PlaybackState, StatsResponse } from "../../src/types/api";

const apiMocks = vi.hoisted(() => ({
  simulateEvent: vi.fn(),
  getPlaybackState: vi.fn(),
  getRecentEvents: vi.fn(),
  getStats: vi.fn(),
}));

vi.mock("../../src/api/playback", () => ({
  getPlaybackState: apiMocks.getPlaybackState,
}));
vi.mock("../../src/api/events", () => ({
  simulateEvent: apiMocks.simulateEvent,
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
    created_at: "2026-09-20 15:00:00",
  };
}

const SAMPLE_RECENT = { items: [makeEvent(1)], count: 1 };

function mockSuccess(stats: StatsResponse): void {
  apiMocks.simulateEvent.mockResolvedValue(SAMPLE_PLAYBACK);
  apiMocks.getPlaybackState.mockResolvedValue(SAMPLE_PLAYBACK);
  apiMocks.getRecentEvents.mockResolvedValue(SAMPLE_RECENT);
  apiMocks.getStats.mockResolvedValue(stats);
}

/** 经 probe 捕获 hook 返回的 triggerEvent / loading（与按钮 onClick 绑定同源）。 */
function captureRuntime(controller: ReturnType<typeof createPetRuntimeController>) {
  let captured: {
    triggerEvent: (eventType: string) => Promise<void>;
    loading: boolean;
    error: unknown;
  } | null = null;
  function Probe() {
    const runtime = usePetRuntime({ controller });
    captured = {
      triggerEvent: runtime.triggerEvent,
      loading: runtime.loading,
      error: runtime.error,
    };
    return null;
  }
  renderToStaticMarkup(<Probe />);
  return captured as {
    triggerEvent: (eventType: string) => Promise<void>;
    loading: boolean;
    error: unknown;
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  usePetStore.setState({ playback: null, recentEvents: [], stats: null });
});

describe("Case 1 面板渲染（ES-1 / ES-3：恰三个固定按钮）", () => {
  it("渲染 gift / comment / follow 三按钮；disabled=true 全部禁用，false 均可点", () => {
    expect(SIMULATOR_EVENT_TYPES).toEqual(["gift", "comment", "follow"]);

    const disabledHtml = renderToStaticMarkup(
      <EventSimulator disabled={true} onTrigger={() => undefined} />,
    );
    expect(disabledHtml).toContain('data-testid="event-simulator"');
    for (const eventType of SIMULATOR_EVENT_TYPES) {
      expect(disabledHtml).toContain(`data-testid="event-simulator-${eventType}"`);
      expect(disabledHtml).toContain(`>${eventType}</button>`);
    }
    expect(disabledHtml.match(/disabled/g)).not.toBeNull();

    const enabledHtml = renderToStaticMarkup(
      <EventSimulator disabled={false} onTrigger={() => undefined} />,
    );
    expect(enabledHtml).not.toContain("disabled");
  });

  it("面板零数据依赖：不消费 store / runtime，仅转交 onTrigger", () => {
    // 空置 store 下渲染不受影响（组件不读 store —— ES-1）
    const html = renderToStaticMarkup(
      <EventSimulator disabled={false} onTrigger={() => undefined} />,
    );
    expect(html).toContain("comment");
  });
});

describe("Case 2 触发成功（ES-2 链路 + ES-3 请求体固定）", () => {
  it("simulateEvent 恰一次且 body 固定 { event_type, payload: {} }；成功后回读写 store", async () => {
    mockSuccess({ events: {}, actions: {}, total: 1 });
    const controller = createPetRuntimeController();
    await controller.refresh(); // 初始加载

    apiMocks.getPlaybackState.mockClear();
    apiMocks.getRecentEvents.mockClear();
    apiMocks.getStats.mockClear();

    const runtime = captureRuntime(controller);
    await runtime.triggerEvent("gift");

    // ES-3：请求体恰两个字段，user_id / user_name 省略
    expect(apiMocks.simulateEvent).toHaveBeenCalledTimes(1);
    expect(apiMocks.simulateEvent).toHaveBeenCalledWith({
      event_type: "gift",
      payload: {},
    });
    // ES-2：成功后回读三端点并整份写 store
    expect(apiMocks.getPlaybackState).toHaveBeenCalledTimes(1);
    expect(apiMocks.getRecentEvents).toHaveBeenCalledTimes(1);
    expect(apiMocks.getStats).toHaveBeenCalledTimes(1);
    expect(usePetStore.getState().playback?.pet_id).toBe("cat_001");
    expect(usePetStore.getState().stats?.total).toBe(1);
    expect(runtime.loading).toBe(false);
    expect(runtime.error).toBeNull();
  });

  it("触发进行中 loading=true（复用 hook 通道，无第二套状态），结束后 false", async () => {
    mockSuccess({ events: {}, actions: {}, total: 0 });
    const controller = createPetRuntimeController();
    await controller.refresh();

    let resolveSim!: (value: PlaybackState) => void;
    apiMocks.simulateEvent.mockImplementation(
      () => new Promise<PlaybackState>((resolve) => { resolveSim = resolve; }),
    );

    const runtime = captureRuntime(controller);
    const pending = runtime.triggerEvent("comment");
    // captureRuntime 捕获的是渲染时刻快照；进行中状态以 controller.getStatus()（活状态源）为准
    expect(controller.getStatus().loading).toBe(true); // ES-4：复用 loading
    resolveSim(SAMPLE_PLAYBACK);
    await pending;
    expect(controller.getStatus().loading).toBe(false);
  });
});

describe("Case 3 触发失败（ES-4：ApiError 原样进入既有 error 通道）", () => {
  it("失败时 error 保持同一实例；loadRuntimeData 不被调用；页面切换到错误区", async () => {
    mockSuccess({ events: {}, actions: {}, total: 1 });
    const controller = createPetRuntimeController();
    await controller.refresh();

    const boom = new ApiError(503, "SERVICE_UNAVAILABLE", "模拟事件提交失败");
    apiMocks.simulateEvent.mockRejectedValue(boom);
    apiMocks.getPlaybackState.mockClear();

    const runtime = captureRuntime(controller);
    await runtime.triggerEvent("follow");

    // 快照不具响应性，错误实例以 controller.getStatus()（活状态源）为准
    expect(controller.getStatus().error).toBe(boom); // 原样，不改写不包装
    expect(controller.getStatus().loading).toBe(false);
    expect(apiMocks.getPlaybackState).not.toHaveBeenCalled(); // 失败不回读

    const html = renderToStaticMarkup(<App controller={controller} />);
    expect(html).toContain('data-testid="app-error"');
    expect(html).toContain("SERVICE_UNAVAILABLE");
    expect(html).toContain("模拟事件提交失败");
  });
});

describe("Case 4 边界（RF-1 不变 + §五静态核验）", () => {
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

  it("refresh 仍不涉及 simulateEvent（RF-1：triggerEvent 不替代 refresh）", async () => {
    mockSuccess({ events: {}, actions: {}, total: 0 });
    const controller = createPetRuntimeController();
    await controller.refresh();
    expect(apiMocks.simulateEvent).not.toHaveBeenCalled();

    expect(typeof controller.refresh).toBe("function");
    expect(typeof controller.triggerEvent).toBe("function");
  });

  it("App ready 分支挂载模拟器；按钮经 onTrigger 注入 triggerEvent（组合根模式）", async () => {
    mockSuccess({ events: {}, actions: {}, total: 1 });
    const controller = createPetRuntimeController();
    await controller.refresh();

    const html = renderToStaticMarkup(<App controller={controller} />);
    expect(html).toContain('data-testid="event-simulator"');
    expect(html).toContain('data-testid="event-simulator-gift"');
  });

  it("EventSimulator 零 import / 零 API / 零状态 / 零计时器（ES-1 / ES-4 / ES-5）", () => {
    const code = read("src/components/EventSimulator.tsx");
    expect(code).not.toMatch(/import\s/); // 全文件零 import（含 React / api / store / hook）
    expect(code).not.toContain("fetch(");
    expect(code).not.toContain("/api/");
    expect(code).not.toContain("useState(");
    expect(code).not.toContain("useEffect(");
    expect(code).not.toContain("useRef(");
    expect(code).not.toContain("setInterval");
    expect(code).not.toContain("setTimeout");
    expect(code).not.toContain("localStorage");
    expect(code).not.toMatch(/from\s+["']zustand/);
  });

  it("usePetRuntime 是编排层：import simulateEvent；请求体 payload 固定空对象（ES-2/ES-3）", () => {
    const hook = read("src/hooks/usePetRuntime.ts");
    expect(hook).toMatch(/import\s+\{[^}]*simulateEvent[^}]*\}\s+from\s+["'][^"']*api\/events["']/);
    expect(hook).toContain("payload: {}");
    expect(hook).toContain("triggerEvent");

    const app = read("src/App.tsx");
    expect(app).toContain("EventSimulator");
    expect(app).toContain("triggerEvent");
    expect(app).not.toMatch(/from\s+["'][^"']*api/); // App 仍零 API import
  });
});
