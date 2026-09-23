/**
 * §7.1 收口（路线①：维持现状 + UI 最小强化）——
 * 「素材待接入」标记与提示的验收测试。
 *
 * 背景：`AVAILABLE_PETS` 暴露 3 只宠物，但 backend `assets` 表**只登记 cat** 的 5 条动作；
 * 选 dog / panda 时事件受理 / 计数写入 / WS 回帧全部正常，却**静默降级 idle、无动画**。
 * 本步只在 UI 层显式提示，**不改** `pet_id` 键集、**不改**后端、**不改**冻结断言。
 *
 * 覆盖：
 * 1. `AVAILABLE_PETS` 的 `placeholder` 标记口径（dog / panda = true；cat 无该字段）；
 * 2. 提示在三处渲染点就位（PetSelector 旁提示 / PetPlayer 视频区域 / PetStage 透传），
 *    且 `<option>` 可见文本、`<video>` 的 `src` 渲染逻辑**逐字不变**。
 *
 * 范式与既有测试一致：store 模块 mock（SSR 快照读当前态）+ `react-dom/server` 静态渲染，
 * node 环境、零新增依赖。
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { useSyncExternalStore } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

import PetSelector from "../../src/components/PetSelector";
import PetStage from "../../src/components/PetStage";
import PetPlayer from "../../src/components/player/PetPlayer";
import { AVAILABLE_PETS } from "../../src/config/pets";
import { usePetStore } from "../../src/stores/usePetStore";
import type { PlaybackState } from "../../src/types/api";

/** store 模块 mock：复用真实 store 状态与行为，仅让 SSR 快照指向**当前态**。 */
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

beforeEach(() => {
  usePetStore.setState({ playback: null, recentEvents: [], stats: null });
  usePetStore.getState().setSelectedPet(null);
});

describe("§7.1 —— AVAILABLE_PETS 的「素材待接入」标记口径", () => {
  it("dog_001 / panda_001 标记 placeholder；cat_001 不标记；目录键与展示名逐字不变", () => {
    const byId = new Map(AVAILABLE_PETS.map((pet) => [pet.pet_id, pet]));

    // 未登记素材（backend `assets` 表无行）⇒ 显式标记
    expect(byId.get("dog_001")?.placeholder).toBe(true);
    expect(byId.get("panda_001")?.placeholder).toBe(true);
    // 素材已登记 ⇒ **不**加该字段（缺省即非占位）
    expect(byId.get("cat_001")?.placeholder).toBeUndefined();

    // MPF-1 冻结面不变：3 个 pet_id 与展示名逐字不变（本步只**增**可选字段）
    expect(AVAILABLE_PETS.map((pet) => pet.pet_id)).toEqual([
      "cat_001",
      "dog_001",
      "panda_001",
    ]);
    expect(AVAILABLE_PETS.map((pet) => pet.label)).toEqual(["小橘", "旺财", "团子"]);
  });
});

describe("§7.1 —— 「素材待接入」提示的渲染点", () => {
  /** 读取源码（守卫约束代码本身；注释中的说明文字不计）。 */
  function readSource(rel: string): string {
    return readFileSync(fileURLToPath(new URL(`../../${rel}`, import.meta.url)), "utf-8")
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .replace(/^\s*\/\/.*$/gm, "");
  }

  function renderSelector(): string {
    return renderToStaticMarkup(
      <PetSelector availablePets={AVAILABLE_PETS} onSelect={() => {}} />,
    );
  }

  it("选中占位宠物时三处提示就位；非占位 / 默认宠物无提示；option 文本与 video src 逻辑不变", () => {
    // --- PetSelector：提示在 <select> 旁，选项文本不动 -----------------------
    usePetStore.getState().setSelectedPet("dog_001");
    const placeholderHtml = renderSelector();
    expect(placeholderHtml).toContain('data-testid="pet-selector-placeholder-hint"');
    expect(placeholderHtml).toContain("素材待接入");
    // 冻结面：<option> 可见文本仍恰为「默认宠物 + 3 只」，不含任何后缀
    const labels = [...placeholderHtml.matchAll(/<option[^>]*>([^<]+)<\/option>/g)].map(
      (m) => m[1],
    );
    expect(labels).toEqual(["默认宠物", "小橘", "旺财", "团子"]);

    usePetStore.getState().setSelectedPet("cat_001"); // 素材已接入
    expect(renderSelector()).not.toContain('data-testid="pet-selector-placeholder-hint"');

    usePetStore.getState().setSelectedPet(null); // 默认宠物
    expect(renderSelector()).not.toContain('data-testid="pet-selector-placeholder-hint"');

    // --- PetPlayer：prop 为 true 时在视频区域提示，video 渲染逻辑不变 ---------
    usePetStore.getState().setPlayback(SAMPLE_PLAYBACK);

    const withFlag = renderToStaticMarkup(<PetPlayer placeholder />);
    expect(withFlag).toContain('data-testid="pet-player-placeholder-hint"');
    expect(withFlag).toContain("该宠物素材待接入");
    // FP-2 / FP-3 不变：asset_url 非空 ⇒ 仍渲染 <video> 且 src 为原值
    expect(withFlag).toContain("<video");
    expect(withFlag).toContain(`src="${SAMPLE_PLAYBACK.asset_url}"`);

    const withoutFlag = renderToStaticMarkup(<PetPlayer />);
    expect(withoutFlag).not.toContain('data-testid="pet-player-placeholder-hint"');
    expect(withoutFlag).toContain(`src="${SAMPLE_PLAYBACK.asset_url}"`);

    // --- PetStage：可选 prop 原样透传（容器仍不消费 store） -------------------
    expect(renderToStaticMarkup(<PetStage placeholder />)).toContain(
      'data-testid="pet-player-placeholder-hint"',
    );
    expect(renderToStaticMarkup(<PetStage />)).not.toContain(
      'data-testid="pet-player-placeholder-hint"',
    );

    // --- 接线静态面：App 计算并下传；PetPlayer 不新增目录 import -------------
    const app = readSource("src/App.tsx");
    expect(app).toContain("<PetStage placeholder={selectedIsPlaceholder} />");
    expect(app).toContain("availablePets.find");

    const player = readSource("src/components/player/PetPlayer.tsx");
    expect(player).not.toMatch(/from\s+["'][^"']*config/);
  });
});
