/**
 * Render Boundary 守卫测试（Step 4.2-P / RB-1 ~ RB-5 验收）。
 *
 * Case1: asset_url 只有 PetPlayer 消费（页面唯一媒体元素 = pet-player-media video）
 * Case2: PetStage 不存在媒体标签（源码静态断言，剥注释）
 * Case3: PlaybackState 契约（types/api.ts；CR-1 起恰 7 字段）
 * Case4: 无新增依赖（package.json dependencies 恰 3 个）
 *
 * 零依赖范式：react-dom/server 静态渲染 + vi.mock API 模块 + 真实 store mock（同 RF/ES 范式）。
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { useSyncExternalStore } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

import App from "../../src/App";
import PetStage from "../../src/components/PetStage";
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
    created_at: "2026-09-20 23:00:00",
  };
}

function mockSuccess(): void {
  apiMocks.simulateEvent.mockResolvedValue(SAMPLE_PLAYBACK);
  apiMocks.getPlaybackState.mockResolvedValue(SAMPLE_PLAYBACK);
  apiMocks.getRecentEvents.mockResolvedValue({ items: [makeEvent(1)], count: 1 });
  apiMocks.getStats.mockResolvedValue({ events: {}, actions: {}, total: 1 });
}

beforeEach(() => {
  vi.clearAllMocks();
  usePetStore.setState({ playback: null, recentEvents: [], stats: null });
});

describe("Case 1 asset_url 只有 PetPlayer 消费（RB-3 唯一媒体消费者）", () => {
  it("有素材时页面媒体元素唯一：pet-player-media video 存在，Stage img 不存在", async () => {
    mockSuccess();
    const controller = (
      await import("../../src/hooks/usePetRuntime")
    ).createPetRuntimeController();
    await controller.refresh();

    const html = renderToStaticMarkup(<App controller={controller} />);
    // 唯一媒体：PetPlayer 的 video
    expect(html).toContain('data-testid="pet-player-media"');
    expect(html).toContain(`src="${SAMPLE_PLAYBACK.asset_url}"`);
    // RB-3：Stage 侧媒体痕迹全无
    expect(html).not.toContain('data-testid="pet-stage-asset"');
    expect(html).not.toContain("<img");
    // 全页 video 元素恰 1 个
    expect(html.match(/<video/g)?.length).toBe(1);
  });
});

describe("Case 2 PetStage 不存在媒体标签（RB-1 / RB-3 静态守卫）", () => {
  /** 剥离注释 —— 守卫约束代码，不约束注释里的说明文字。 */
  function stripComments(source: string): string {
    return source
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .replace(/^\s*\/\/.*$/gm, "");
  }

  it("PetStage 源码：零 img / 零 video / 零 asset_url 消费 / 零 store 消费", () => {
    const code = stripComments(
      readFileSync(
        fileURLToPath(new URL("../../src/components/PetStage.tsx", import.meta.url)),
        "utf-8",
      ),
    );
    expect(code).not.toContain("<img");
    expect(code).not.toContain("<video");
    expect(code).not.toContain("asset_url");
    expect(code).not.toContain("usePetStore");
    expect(code).toContain("PetPlayer"); // 内嵌唯一媒体渲染点
  });

  it("PetStage 渲染：容器 + PetPlayer，无媒体标签", () => {
    usePetStore.getState().setPlayback(SAMPLE_PLAYBACK);
    const html = renderToStaticMarkup(<PetStage />);
    expect(html).toContain('data-testid="pet-stage"');
    expect(html).not.toContain("<img");
    expect(html).toContain('data-testid="pet-player-media"');
  });
});

describe("Case 3 PlaybackState 契约（RB-5；CR-1 起 7 字段）", () => {
  it("types/api.ts 的 PlaybackState 恰 7 字段（CR-1 + loop），无派生字段", () => {
    const code = readFileSync(
      fileURLToPath(new URL("../../src/types/api.ts", import.meta.url)),
      "utf-8",
    );
    const body = code.slice(code.indexOf("export interface PlaybackState"));
    const fields = [
      "pet_id",
      "state",
      "action",
      "asset_url",
      "queue_size",
      "last_event",
      "loop",
    ];
    for (const field of fields) {
      expect(body).toMatch(new RegExp(`\\b${field}\\s*:`));
    }
    // 禁止新增播放器派生字段（C4 冻结延续）
    for (const banned of ["duration", "progress", "playingTime", "videoState", "media_type"]) {
      expect(body).not.toMatch(new RegExp(`\\b${banned}\\s*:`));
    }
  });
});

describe("Case 4 无新增依赖（RB-5）", () => {
  it("package.json dependencies 恰为 react / react-dom / zustand", () => {
    const pkg = JSON.parse(
      readFileSync(
        fileURLToPath(new URL("../../package.json", import.meta.url)),
        "utf-8",
      ),
    );
    expect(Object.keys(pkg.dependencies).sort()).toEqual([
      "react",
      "react-dom",
      "zustand",
    ]);
  });
});
