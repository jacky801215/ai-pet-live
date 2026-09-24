/**
 * AI 生成内容标识测试（**CR-4**；FCM-2 v1.1 验收）。
 *
 * 覆盖：AiContentLabel 组件渲染 / 标识文字存在 / ready 态页面可见 /
 *      loading 与 error 态**不渲染**（owner 裁决：仅 ready 态）/
 *      新组件源码静态边界（零网络 / 零地址 / 零持久化 / 零计时器 / 零 API import）。
 *
 * ⚠️ 说明（owner 裁决 q-3：允许**新增**用例、不改动既有用例）：
 * 本套件**不改** `tests/components/components.test.tsx`，故 `AiContentLabel.tsx` 的静态边界
 * 断言落在**本文件**内（该文件原有的 `COMPONENT_FILES` 守卫清单保持原样）。
 *
 * 范式与既有测试一致：`react-dom/server` 静态渲染 + API 模块 vi.mock + 真实 store mock。
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { useSyncExternalStore } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../../src/api/client";
import App from "../../src/App";
import { AiContentLabel } from "../../src/components/AiContentLabel";
import { createPetRuntimeController } from "../../src/hooks/usePetRuntime";
import { usePetStore } from "../../src/stores/usePetStore";
import type { EventItem, PlaybackState } from "../../src/types/api";

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

/** store 模块 mock（同既有范式）：SSR 快照读当前态，行为仍是真实 store。 */
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
    created_at: "2026-09-24 20:00:00",
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  usePetStore.setState({ playback: null, recentEvents: [], stats: null });
});

describe("Case 1 AiContentLabel 组件渲染（CR-4 / FCM-2 v1.1）", () => {
  it("渲染标识容器、文字「AI生成」与无障碍语义", () => {
    const html = renderToStaticMarkup(<AiContentLabel />);

    expect(html).toContain('class="ai-content-label"');
    expect(html).toContain("AI生成");
    expect(html).toContain('role="note"');
    expect(html).toContain('aria-label="AI生成内容标识"');
  });

  it("组件无 props 依赖，渲染结果恒定", () => {
    expect(renderToStaticMarkup(<AiContentLabel />)).toBe(
      renderToStaticMarkup(<AiContentLabel />),
    );
  });
});

describe("Case 2 ready 态页面可见（标识随直播间画面全程展示）", () => {
  it("ready 布局下页面含 AI 标识，且与 pet-stage 同页", async () => {
    apiMocks.getPlaybackState.mockResolvedValue(SAMPLE_PLAYBACK);
    apiMocks.getRecentEvents.mockResolvedValue({ items: [makeEvent(1)], count: 1 });
    apiMocks.getStats.mockResolvedValue({ events: {}, actions: {}, total: 1 });

    const controller = createPetRuntimeController();
    await controller.refresh();

    const html = renderToStaticMarkup(<App controller={controller} />);

    expect(html).toContain('data-phase="components"');
    expect(html).toContain('class="ai-content-label"');
    expect(html).toContain("AI生成");
    expect(html).toContain('data-testid="pet-stage"');
  });
});

describe("Case 3 非 ready 态不渲染标识（owner 裁决：仅 ready 态）", () => {
  it("loading 态（挂载首帧）不含 AI 标识", () => {
    const html = renderToStaticMarkup(<App />);

    expect(html).toContain('data-testid="app-loading"');
    expect(html).not.toContain("ai-content-label");
    expect(html).not.toContain("AI生成");
  });

  it("error 态不含 AI 标识", async () => {
    apiMocks.getPlaybackState.mockRejectedValue(
      new ApiError(500, "INTERNAL_ERROR", "后端不可用"),
    );

    const controller = createPetRuntimeController();
    await controller.refresh();

    const html = renderToStaticMarkup(<App controller={controller} />);

    expect(html).toContain('data-testid="app-error"');
    expect(html).not.toContain("ai-content-label");
    expect(html).not.toContain("AI生成");
  });
});

describe("Case 4 新组件源码静态边界（FCM-1 / FCM-3 / FCM-4）", () => {
  /** 剥离块注释与行注释 —— 守卫约束代码，不约束注释里的说明文字。 */
  function stripComments(source: string): string {
    return source
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .replace(/^\s*\/\/.*$/gm, "");
  }

  const code = stripComments(
    readFileSync(
      fileURLToPath(
        new URL("../../src/components/AiContentLabel.tsx", import.meta.url),
      ),
      "utf-8",
    ),
  );

  it("零网络请求 / 零地址拼接 / 零持久化 / 零计时器", () => {
    expect(code).not.toContain("fetch(");
    expect(code).not.toContain("/api/");
    expect(code).not.toContain("XMLHttpRequest");
    expect(code).not.toContain("localStorage");
    expect(code).not.toContain("sessionStorage");
    expect(code).not.toContain("setInterval");
    expect(code).not.toContain("setTimeout");
    expect(code).not.toContain("requestAnimationFrame");
  });

  it("零 API import / 零 store 原语 / 零媒体标签 / 零动画库", () => {
    expect(code).not.toMatch(/from\s+["'][^"']*api/);
    expect(code).not.toMatch(/from\s+["'][^"']*client/);
    expect(code).not.toMatch(/from\s+["']zustand/);
    expect(code).not.toMatch(/from\s+["']react-router/);
    expect(code).not.toMatch(/from\s+["']framer-motion/);
    expect(code).not.toContain("<canvas");
    expect(code).not.toContain("<video");
    expect(code).not.toContain("<img");
  });

  it("标识文字与 FCM-4 白名单一致（文本 + 基础 className）", () => {
    expect(code).toContain("ai-content-label"); // className 钩子
    expect(code).toContain("AI生成"); // 标识文字
    expect(code).not.toContain("style="); // 不引入内联样式系统
  });
});
