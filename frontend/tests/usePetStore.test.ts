/**
 * PetStore 单元测试（Step 4.1-C-3 / FS-3、FS-4、FS-5 验收）。
 *
 * 运行：`npm test`（vitest run，node 环境，无 jsdom —— store 不依赖 DOM）。
 * 覆盖：初始状态、三个 setter、setRecentEvents 整份替换语义、切片独立、
 *       store 源码零 `src/api` 依赖 / 零 fetch / 零 localStorage（静态文本断言）。
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { beforeEach, describe, expect, it } from "vitest";

import { usePetStore } from "../src/stores/usePetStore";
import type { EventItem, PlaybackState } from "../src/types/api";

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
    payload: { gift_name: "小心心", gift_count: 1 },
    created_at: "2026-09-20 12:00:00",
  };
}

beforeEach(() => {
  usePetStore.setState({ playback: null, recentEvents: [], stats: null });
});

describe("PetStore（FS-3 初始状态与 setter）", () => {
  it("初始状态为空：playback=null、recentEvents=[]、stats=null", () => {
    const state = usePetStore.getState();
    expect(state.playback).toBeNull();
    expect(state.recentEvents).toEqual([]);
    expect(state.stats).toBeNull();
  });

  it("setPlayback 整份替换播放快照", () => {
    usePetStore.getState().setPlayback(SAMPLE_PLAYBACK);

    const state = usePetStore.getState();
    expect(state.playback).toEqual(SAMPLE_PLAYBACK);
    expect(state.playback?.asset_url).toBe("/assets/pets/cat/actions/heart/heart.mp4");
  });

  it("setRecentEvents 整份替换列表（不合并、不去重）", () => {
    usePetStore.getState().setRecentEvents([makeEvent(1)]);
    expect(usePetStore.getState().recentEvents).toHaveLength(1);

    usePetStore.getState().setRecentEvents([makeEvent(2)]);
    const events = usePetStore.getState().recentEvents;
    expect(events).toHaveLength(1);
    expect(events[0]?.id).toBe(2);
  });

  it("setStats 整份替换统计", () => {
    usePetStore.getState().setStats({
      events: { gift: 5, like: 2 },
      actions: { heart: 5 },
      total: 7,
    });

    const stats = usePetStore.getState().stats;
    expect(stats).toEqual({ events: { gift: 5, like: 2 }, actions: { heart: 5 }, total: 7 });
    expect(stats?.total).toBe(7);
  });

  it("三个切片独立更新、互不干扰", () => {
    usePetStore.getState().setPlayback(SAMPLE_PLAYBACK);
    usePetStore.getState().setStats({ events: {}, actions: {}, total: 0 });

    const state = usePetStore.getState();
    expect(state.playback).not.toBeNull();
    expect(state.stats).not.toBeNull();
    expect(state.recentEvents).toEqual([]);
  });
});

describe("PetStore 边界（FS-1 / FS-4 静态断言）", () => {
  /** 剥离块注释与行注释 —— 守卫约束的是**代码**，docstring 里的禁止性说明是合法的。 */
  function stripComments(source: string): string {
    return source
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .replace(/^\s*\/\/.*$/gm, "");
  }

  const code = stripComments(
    readFileSync(
      fileURLToPath(new URL("../src/stores/usePetStore.ts", import.meta.url)),
      "utf-8",
    ),
  );

  it("store 不依赖 api client（无 src/api import）", () => {
    expect(code).not.toMatch(/from\s+["'](\.\.\/)?api/);
    expect(code).not.toContain("src/api");
  });

  it("store 无 fetch / 无 URL 拼接 / 无 localStorage / 无动画计时器", () => {
    expect(code).not.toContain("fetch(");
    expect(code).not.toContain("/api/");
    expect(code).not.toContain("localStorage");
    expect(code).not.toContain("setInterval");
    expect(code).not.toContain("setTimeout");
  });

  it("store 无 React import（除 zustand 外零 UI 依赖）", () => {
    expect(code).not.toMatch(/from\s+["']react/);
  });
});
