/**
 * 组件层测试（Step 4.1-C-4 / FCM-2、FCM-3、FCM-4 验收）。
 *
 * 运行：`npm test`（vitest run，node 环境、零新增依赖 ——
 * 用 react-dom/server 的静态渲染断言，无需 jsdom）。
 * 覆盖：PetStage 空态与素材展示、PetPlayer 播放快照展示、
 *       EventList 事件展示与空态、StatusBar 统计展示、App 组合接线、
 *       组件源码静态边界断言（剥注释后：零网络请求 / 零地址拼接 / 零持久化 / 零计时器）。
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { useSyncExternalStore } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

import EventList from "../../src/components/EventList";
import PetPlayer from "../../src/components/player/PetPlayer";
import PetStage from "../../src/components/PetStage";
import StatusBar from "../../src/components/StatusBar";
import App from "../../src/App";
import { usePetStore } from "../../src/stores/usePetStore";
import type { EventItem, PlaybackState, StatsResponse } from "../../src/types/api";

/**
 * zustand v5 的服务端渲染路径读取 getInitialState()（创建时初始态），
 * setState 变更在静态渲染里不可见。这里 mock store 模块：复用真实 store 的
 * getState / setState / subscribe（状态行为与被测对象完全一致），仅把
 * useSyncExternalStore 的 server snapshot 指向**当前态**，让静态渲染反映变更。
 */
vi.mock("../../src/stores/usePetStore", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("../../src/stores/usePetStore")>();
  const real = actual.usePetStore;
  const hooked = (selector?: (state: typeof real.getState) => unknown) =>
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
    payload: { gift_name: "小心心", gift_count: 1 },
    created_at: "2026-09-20 12:00:00",
  };
}

const SAMPLE_STATS: StatsResponse = {
  events: { gift: 5, like: 2 },
  actions: { heart: 5 },
  total: 7,
};

beforeEach(() => {
  usePetStore.setState({ playback: null, recentEvents: [], stats: null });
});

describe("PetStage（FCM-2 宠物展示区域）", () => {
  it("无播放快照时展示空态", () => {
    const html = renderToStaticMarkup(<PetStage />);
    expect(html).toContain("暂无宠物画面");
    expect(html).toContain("data-testid=\"pet-stage-empty\"");
    expect(html).not.toContain("<img");
  });

  it("有 asset_url 时只消费该地址展示素材（不自拼地址）", () => {
    usePetStore.getState().setPlayback(SAMPLE_PLAYBACK);

    const html = renderToStaticMarkup(<PetStage />);
    expect(html).toContain(`<img`);
    expect(html).toContain(`src="${SAMPLE_PLAYBACK.asset_url}"`);
  });
});

describe("PetPlayer（FCM-2 当前动作展示）", () => {
  it("无播放快照时展示空态", () => {
    const html = renderToStaticMarkup(<PetPlayer />);
    expect(html).toContain("暂无播放内容");
  });

  it("展示 playback 的 pet_id / state / action", () => {
    usePetStore.getState().setPlayback(SAMPLE_PLAYBACK);

    const html = renderToStaticMarkup(<PetPlayer />);
    expect(html).toContain("cat_001");
    expect(html).toContain("playing");
    expect(html).toContain("heart");
  });

  it("action 为 null 时展示占位符", () => {
    usePetStore.getState().setPlayback({ ...SAMPLE_PLAYBACK, action: null });

    const html = renderToStaticMarkup(<PetPlayer />);
    expect(html).toContain("—");
  });
});

describe("EventList（FCM-2 最近事件列表）", () => {
  it("空列表展示空态", () => {
    const html = renderToStaticMarkup(<EventList />);
    expect(html).toContain("暂无最近事件");
  });

  it("展示事件的 event_type / action_name / created_at", () => {
    usePetStore.getState().setRecentEvents([makeEvent(1)]);

    const html = renderToStaticMarkup(<EventList />);
    expect(html).toContain("gift");
    expect(html).toContain("heart");
    expect(html).toContain("2026-09-20 12:00:00");
  });

  it("可空字段（action_name / created_at）为 null 时展示占位符", () => {
    const event = makeEvent(1);
    usePetStore
      .getState()
      .setRecentEvents([{ ...event, action_name: null, created_at: null }]);

    const html = renderToStaticMarkup(<EventList />);
    expect(html).toContain("—");
  });
});

describe("StatusBar（FCM-2 统计展示）", () => {
  it("无统计时展示空态", () => {
    const html = renderToStaticMarkup(<StatusBar />);
    expect(html).toContain("暂无统计数据");
  });

  it("展示 events / actions / total", () => {
    usePetStore.getState().setStats(SAMPLE_STATS);

    const html = renderToStaticMarkup(<StatusBar />);
    expect(html).toContain("7");
    expect(html).toContain("gift:5");
    expect(html).toContain("like:2");
    expect(html).toContain("heart:5");
  });
});

describe("App 接线（FCM-2 / RS-1：零参渲染首帧为页面加载区）", () => {
  it("零参 App（SSR 挂载首帧）展示统一加载区；ready 三区域组合由 runtime 测试覆盖", () => {
    const html = renderToStaticMarkup(<App />);
    expect(html).toContain('data-testid="app-loading"'); // RS-2：loading=true 页面加载区
    expect(html).not.toContain("fetch(");
  });
});

describe("组件边界（FCM-1 / FCM-3 / FCM-4 静态断言）", () => {
  /** 剥离块注释与行注释 —— 守卫约束的是代码，注释里的禁止性说明是合法的。 */
  function stripComments(source: string): string {
    return source
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .replace(/^\s*\/\/.*$/gm, "");
  }

  const COMPONENT_FILES = [
    "src/components/PetStage.tsx",
    "src/components/EventList.tsx",
    "src/components/StatusBar.tsx",
    "src/components/player/PetPlayer.tsx",
    "src/App.tsx",
  ];

  const sources = Object.fromEntries(
    COMPONENT_FILES.map((rel) => [
      rel,
      stripComments(
        readFileSync(
          fileURLToPath(new URL(`../../${rel}`, import.meta.url)),
          "utf-8",
        ),
      ),
    ]),
  );

  it("组件不 import API 层模块", () => {
    for (const [rel, code] of Object.entries(sources)) {
      expect(code, rel).not.toMatch(/from\s+["'][^"']*api/);
      expect(code, rel).not.toMatch(/from\s+["'][^"']*client/);
    }
  });

  it("组件零网络请求 / 零地址拼接 / 零持久化 / 零计时器", () => {
    for (const [rel, code] of Object.entries(sources)) {
      expect(code, rel).not.toContain("fetch(");
      expect(code, rel).not.toContain("/api/");
      expect(code, rel).not.toContain("XMLHttpRequest");
      expect(code, rel).not.toContain("localStorage");
      expect(code, rel).not.toContain("sessionStorage");
      expect(code, rel).not.toContain("setInterval");
      expect(code, rel).not.toContain("setTimeout");
      expect(code, rel).not.toContain("requestAnimationFrame");
    }
  });

  it("组件零 canvas / 零视频自建播放器 / 零路由 / 零动画库", () => {
    for (const [rel, code] of Object.entries(sources)) {
      expect(code, rel).not.toContain("<canvas");
      expect(code, rel).not.toContain("<video");
      expect(code, rel).not.toMatch(/from\s+["']react-router/);
      expect(code, rel).not.toMatch(/from\s+["']framer-motion/);
    }
  });

  it("组件只经 usePetStore 读数据，不直接依赖 zustand 原语", () => {
    for (const [rel, code] of Object.entries(sources)) {
      expect(code, rel).not.toMatch(/from\s+["']zustand/);
      // 除类型 import 外，允许的值 import：usePetStore、组件相对路径；
      // App 额外允许 usePetRuntime（FD-2：App 只用它初始化数据流）
      const dataImports =
        code.match(/import\s+\{[^}]+\}\s+from\s+["'][^"']+["']/g) ?? [];
      for (const line of dataImports) {
        if (/import\s+type\s/.test(line)) continue;
        const allowed =
          line.includes("usePetStore") ||
          /\/components\//.test(line) ||
          (rel === "src/App.tsx" && line.includes("usePetRuntime"));
        expect(allowed, `${rel}: ${line}`).toBe(true);
      }
    }
  });
});
