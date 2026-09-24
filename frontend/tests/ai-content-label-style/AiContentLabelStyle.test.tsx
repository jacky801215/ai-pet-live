/**
 * AI 生成内容标识**样式**契约测试（**CR-5**；FCM-4 v1.2 验收）。
 *
 * 覆盖：样式文件存在与规则 / 字号量化（≥ 画面最短边 5%）/ 定位容器（相对画面）/
 *      样式表引入点 / ready 态 DOM 中标识与画面**同容器** / 组件仍零内联样式 /
 *      显著可见性 / 零新增依赖。
 *
 * ⚠️ 说明（owner 裁决 q-3：允许**新增**用例 + 允许同步守卫）：
 * 本套件为 CR-5 **新增**；CR-4 既有用例（`tests/ai-content-label/AiContentLabel.test.tsx`）
 * 与 `tests/components/components.test.tsx` 的 `COMPONENT_FILES` 守卫**均不改动**。
 *
 * 范式与既有测试一致：`react-dom/server` 静态渲染 + API 模块 vi.mock + 真实 store mock。
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { useSyncExternalStore } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

import App from "../../src/App";
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

function readSource(rel: string): string {
  return readFileSync(
    fileURLToPath(new URL(`../../${rel}`, import.meta.url)),
    "utf-8",
  );
}

/** 剥离块注释与行注释 —— 守卫约束代码，不约束注释里的说明文字。 */
function stripComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^\s*\/\/.*$/gm, "");
}

/** 取某个选择器的规则体（简易解析，够用于本守卫；只取出现的第一处）。 */
function ruleBody(source: string, selector: string): string {
  const idx = source.indexOf(`${selector} {`);
  if (idx < 0) return "";
  const end = source.indexOf("}", idx);
  return end < 0 ? source.slice(idx) : source.slice(idx, end);
}

const CSS = stripComments(readSource("src/styles/ai-content-label.css"));

/** 素材固有尺寸（`assets/pets/<pet>/actions/<action>/<name>.mp4` 实测 720×1280 竖屏 9:16）。 */
const FRAME_WIDTH = 720;
const FRAME_HEIGHT = 1280;
/** 画面最短边（合规口径以「最短边」为基数）。 */
const SHORTEST_SIDE = Math.min(FRAME_WIDTH, FRAME_HEIGHT);
/** 合规下限：文字高度 ≥ 画面最短边的 5%。 */
const MIN_LABEL_PX = Math.ceil(SHORTEST_SIDE * 0.05);

beforeEach(() => {
  vi.clearAllMocks();
  usePetStore.setState({ playback: null, recentEvents: [], stats: null });
});

describe("Case 1 样式文件与 .ai-content-label 规则（FCM-4 v1.2）", () => {
  it("独立样式表声明 .ai-content-label，且以绝对定位锚定右上角", () => {
    const body = ruleBody(CSS, ".ai-content-label");
    expect(body, "样式表应含 .ai-content-label 规则").not.toBe("");
    expect(body).toContain("position: absolute");
    expect(body).toContain("top: 0");
    expect(body).toContain("right: 0");
  });

  it("样式表仍无内联样式痕迹（样式只落独立文件，非组件内）", () => {
    expect(CSS).not.toContain("style=");
  });
});

describe("Case 2 字号量化（≥ 画面最短边的 5%，owner q-1 裁决）", () => {
  it("前置：素材固有尺寸 720×1280 ⇒ 最短边 720 ⇒ 5% = 36px", () => {
    expect(FRAME_WIDTH).toBe(720);
    expect(FRAME_HEIGHT).toBe(1280);
    expect(SHORTEST_SIDE).toBe(720);
    expect(MIN_LABEL_PX).toBe(36);
  });

  it("CSS 声明的字号 ≥ 合规下限", () => {
    const body = ruleBody(CSS, ".ai-content-label");
    const matched = body.match(/font-size:\s*(\d+(?:\.\d+)?)px/);
    expect(matched, "CSS 应声明 px 字号").not.toBeNull();
    const px = Number(matched![1]);
    expect(Number.isFinite(px)).toBe(true);
    expect(px).toBeGreaterThanOrEqual(MIN_LABEL_PX);
  });
});

describe("Case 3 定位容器（owner q-2：相对画面容器，非视口 fixed）", () => {
  it(".live-stage 为相对定位，作为画面右上角的参照系", () => {
    const body = ruleBody(CSS, ".live-stage");
    expect(body, "样式表应含 .live-stage 规则").not.toBe("");
    expect(body).toContain("position: relative");
  });

  it("标识样式不含视口定位（不得用 position: fixed 冒充画面角标）", () => {
    const body = ruleBody(CSS, ".ai-content-label");
    expect(body).not.toContain("position: fixed");
  });
});

describe("Case 4 样式表引入点（组件侧零样式）", () => {
  it("样式表由应用入口 src/main.tsx 以副作用 import 引入", () => {
    const main = readSource("src/main.tsx");
    expect(main).toContain('import "./styles/ai-content-label.css";');
  });

  it("组件源码零内联样式：只输出 className 钩子", () => {
    const code = stripComments(readSource("src/components/AiContentLabel.tsx"));
    expect(code).not.toContain("style=");
    expect(code).toContain("ai-content-label");
    // 组件不 import 样式表（样式归入口，组件保持纯展示）
    expect(code).not.toContain(".css");
  });
});

describe("Case 5 ready 态 DOM：标识与画面同容器（RB-3 不新增媒体元素）", () => {
  it(".live-stage 同时包裹 AI 标识与 pet-stage，标识在画面之前", async () => {
    apiMocks.getPlaybackState.mockResolvedValue(SAMPLE_PLAYBACK);
    apiMocks.getRecentEvents.mockResolvedValue({ items: [makeEvent(1)], count: 1 });
    apiMocks.getStats.mockResolvedValue({ events: {}, actions: {}, total: 1 });

    const controller = createPetRuntimeController();
    await controller.refresh();

    const html = renderToStaticMarkup(<App controller={controller} />);

    // 同容器 + 顺序：标识紧跟容器开标签 ⇒ 证明二者同属 .live-stage
    expect(html).toContain('<div class="live-stage"><div class="ai-content-label"');
    const containerIdx = html.indexOf('<div class="live-stage">');
    const labelIdx = html.indexOf('class="ai-content-label"');
    const stageIdx = html.indexOf('data-testid="pet-stage"');
    expect(containerIdx).toBeGreaterThanOrEqual(0);
    expect(labelIdx).toBeGreaterThan(containerIdx);
    expect(stageIdx).toBeGreaterThan(labelIdx);

    // RB-3：未新增媒体元素（全页 video 仍恰 1 个，无 img）
    expect(html.match(/<video/g)?.length).toBe(1);
    expect(html).not.toContain("<img");
  });

  it("非 ready 态不渲染定位容器（loading 首帧）", () => {
    const html = renderToStaticMarkup(<App />);
    expect(html).toContain('data-testid="app-loading"');
    expect(html).not.toContain("live-stage");
    expect(html).not.toContain("ai-content-label");
  });
});

describe("Case 6 显著可见性（合规「显著」要求）", () => {
  it("标识样式含前景色 + 背景色，且不拦截画面交互（UB-3）", () => {
    const body = ruleBody(CSS, ".ai-content-label");
    expect(body).toMatch(/color:\s*#|color:\s*rgb/);
    expect(body).toContain("background-color:");
    expect(body).toContain("pointer-events: none");
  });
});

describe("Case 7 零新增依赖（RB-5）", () => {
  it("package.json dependencies 仍恰为 react / react-dom / zustand", () => {
    const pkg = JSON.parse(readSource("package.json"));
    expect(Object.keys(pkg.dependencies).sort()).toEqual([
      "react",
      "react-dom",
      "zustand",
    ]);
  });
});
