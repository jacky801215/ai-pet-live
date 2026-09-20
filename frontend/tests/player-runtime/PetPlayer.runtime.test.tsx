/**
 * 播放器运行链路验证（Step 4.1-E-2）——
 * 验证既有链路：Backend Event ↓ PlaybackState ↓ Store.playback ↓ PetPlayer ↓ native <video>。
 *
 * 本步只做运行验证与测试补强，不扩展播放器能力（零源码改动）。
 * 策略与既有测试一致：API 模块 vi.mock + 真实 zustand store（SSR 快照 mock 指向当前态）+
 * react-dom/server 静态渲染，零新增依赖。
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { useSyncExternalStore } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

import PetPlayer from "../../src/components/player/PetPlayer";
import { usePetStore } from "../../src/stores/usePetStore";
import type { PlaybackState } from "../../src/types/api";

const apiMocks = vi.hoisted(() => ({
  getPlaybackState: vi.fn(),
  getRecentEvents: vi.fn(),
  getStats: vi.fn(),
}));

/** API mock：GET /api/playback/state 的数据源（Case 3 真实数据链验证用）。 */
vi.mock("../../src/api/playback", () => ({
  getPlaybackState: apiMocks.getPlaybackState,
}));
/** loadRuntimeData 会并行拉取三个端点，其余两个 mock 为空实现（本步不消费其结果）。 */
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

import { loadRuntimeData } from "../../src/hooks/usePetRuntime";

const HEART_ASSET = "/assets/pets/cat/actions/heart/heart.mp4";

const IDLE_PLAYBACK: PlaybackState = {
  pet_id: "cat_001",
  state: "idle",
  action: null,
  asset_url: null,
  queue_size: 0,
  last_event: null,
};

const PLAYING_PLAYBACK: PlaybackState = {
  pet_id: "cat_001",
  state: "playing",
  action: "heart",
  asset_url: HEART_ASSET,
  queue_size: 0,
  last_event: "gift",
};

beforeEach(() => {
  vi.clearAllMocks();
  usePetStore.setState({ playback: null, recentEvents: [], stats: null });
});

describe("Case 1 Idle 空闲状态（无媒体资源）", () => {
  it("展示 pet_id / state=idle / action 占位符；不渲染 video", () => {
    usePetStore.getState().setPlayback(IDLE_PLAYBACK);

    const html = renderToStaticMarkup(<PetPlayer />);

    expect(html).toContain("宠物：cat_001");
    expect(html).toContain("状态：idle");
    expect(html).toContain("动作：—");
    expect(html).not.toContain("<video");
    expect(html).not.toContain('data-testid="pet-player-media"');
  });
});

describe("Case 2 Playing 动作状态", () => {
  it("渲染 video 且 src / autoplay / playsinline 就位；文本同步展示", () => {
    usePetStore.getState().setPlayback(PLAYING_PLAYBACK);

    const html = renderToStaticMarkup(<PetPlayer />);

    expect(html).toContain("<video");
    expect(html).toContain(`src="${HEART_ASSET}"`);
    expect(html).toContain("autoplay");
    expect(html).toContain("playsinline");
    expect(html).toContain("状态：playing");
    expect(html).toContain("动作：heart");
  });
});

describe("Case 3 真实动作数据链（API DTO → store playback → PetPlayer → video）", () => {
  it("GET /api/playback/state 的响应经 store 写入后，PetPlayer 渲染出 video", async () => {
    // 模拟后端响应：与冻结契约逐字段一致
    apiMocks.getPlaybackState.mockResolvedValue(PLAYING_PLAYBACK);
    // loadRuntimeData 并行拉取三端点；另两个给合法空值（本步只消费 playback）
    apiMocks.getRecentEvents.mockResolvedValue({ items: [], count: 0 });
    apiMocks.getStats.mockResolvedValue({ events: {}, actions: {}, total: 0 });

    await loadRuntimeData(); // 与 hook 挂载时调用的同一编排函数

    const state = usePetStore.getState();
    expect(state.playback).toEqual(PLAYING_PLAYBACK); // DTO 原样入 store

    const html = renderToStaticMarkup(<PetPlayer />);
    expect(html).toContain("<video");
    expect(html).toContain(`src="${HEART_ASSET}"`);
    expect(html).toContain("状态：playing");
    expect(html).toContain("动作：heart");
    expect(apiMocks.getPlaybackState).toHaveBeenCalledTimes(1);
  });
});

describe("Case 4 asset_url 边界（state=playing 但无媒体）", () => {
  it("不生成 video、不自行拼接路径；文本保留动作信息", () => {
    usePetStore.getState().setPlayback({
      ...PLAYING_PLAYBACK,
      asset_url: null,
    });

    const html = renderToStaticMarkup(<PetPlayer />);

    expect(html).not.toContain("<video");
    expect(html).not.toContain("/assets/"); // 无任何素材路径被自行生成
    expect(html).toContain("状态：playing");
    expect(html).toContain("动作：heart");
  });
});

describe("Case 5 静态边界（PetPlayer.tsx 与本测试目录）", () => {
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

  it("PetPlayer.tsx：允许 usePetStore 与 <video>；禁 API / 本地状态 / 事件监听 / 计时器", () => {
    const code = read("src/components/player/PetPlayer.tsx");
    expect(code).toContain("usePetStore");
    expect(code).toContain("<video");
    expect(code).not.toContain("fetch(");
    expect(code).not.toContain("axios");
    expect(code).not.toContain("/api/");
    expect(code).not.toContain("useState(");
    expect(code).not.toContain("useEffect(");
    expect(code).not.toContain("useRef(");
    expect(code).not.toContain("currentTime");
    expect(code).not.toContain("progress");
    expect(code).not.toContain("onEnded");
    expect(code).not.toContain("setInterval");
    expect(code).not.toContain("WebSocket");
  });

  it("本测试目录自身 import 白名单（零第三方数据/播放器依赖）", () => {
    const code = read("tests/player-runtime/PetPlayer.runtime.test.tsx");
    const imports = [...code.matchAll(/from\s+["']([^"']+)["']/g)].map((m) => m[1]);
    expect(imports).toEqual([
      "node:fs",
      "node:url",
      "react",
      "react-dom/server",
      "vitest",
      "../../src/components/player/PetPlayer",
      "../../src/stores/usePetStore",
      "../../src/types/api",
      "../../src/hooks/usePetRuntime",
    ]);
  });
});
