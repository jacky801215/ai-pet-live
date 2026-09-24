/**
 * PetPlayer 原生播放实现测试（Step 4.1-E-1 / FP-1..FP-5 验收）。
 *
 * 运行：`npm test`（vitest run，node 环境、零新增依赖 ——
 * react-dom/server 静态渲染 + store 模块 mock，SSR 快照读当前态）。
 *
 * 已知 React SSR 行为（记录性）：`muted` 属性在服务端渲染输出中不落 attributes
 * （React 既有问题，客户端挂载时以 DOM property 生效）—— muted 的存在以**源码静态断言**验证。
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { useSyncExternalStore } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

import PetPlayer from "../../src/components/player/PetPlayer";
import { usePetStore } from "../../src/stores/usePetStore";
import type { PlaybackState } from "../../src/types/api";

/** store 模块 mock（同前各测试文件）：SSR 快照读当前态，行为仍是真实 store。 */
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

function makePlayback(assetUrl: string | null, loop = false): PlaybackState {
  return {
    pet_id: "cat_001",
    state: "playing",
    action: "heart",
    asset_url: assetUrl,
    queue_size: 0,
    last_event: "gift",
    loop,
  };
}

beforeEach(() => {
  usePetStore.setState({ playback: null, recentEvents: [], stats: null });
});

describe("Case 1 playback=null（FP-2：空态，无媒体区）", () => {
  it("展示空态，无 video 元素", () => {
    const html = renderToStaticMarkup(<PetPlayer />);

    expect(html).toContain("暂无播放内容");
    expect(html).toContain('data-testid="pet-player-empty"');
    expect(html).not.toContain("<video");
    expect(html).not.toContain('data-testid="pet-player-media"');
  });
});

describe("Case 2 asset_url=null（FP-2 v1.1：不渲染媒体区域，文本保留）", () => {
  it("无 video 元素；pet_id / state / action 文本正常展示", () => {
    usePetStore.getState().setPlayback(makePlayback(null));

    const html = renderToStaticMarkup(<PetPlayer />);

    expect(html).not.toContain("<video");
    expect(html).not.toContain('data-testid="pet-player-media"');
    expect(html).toContain("宠物：cat_001");
    expect(html).toContain("状态：playing");
    expect(html).toContain("动作：heart");
  });
});

describe("Case 3 asset_url 非空（FP-2/FP-3：原生 video，src 只消费）", () => {
  it("渲染 video，src 为 asset_url 原值；autoplay / playsInline 落到 markup；controls 不出现", () => {
    const assetUrl = "/assets/pets/cat/actions/heart/heart.mp4";
    usePetStore.getState().setPlayback(makePlayback(assetUrl));

    const html = renderToStaticMarkup(<PetPlayer />);

    expect(html).toContain("<video");
    expect(html).toContain(`src="${assetUrl}"`); // 原样消费，无拼接
    expect(html).toContain("autoplay");
    expect(html).toContain("playsinline");
    expect(html).not.toContain("controls"); // controls={false}
    expect(html).toContain("宠物：cat_001"); // 状态文本继续展示
    expect(html).toContain("动作：heart");
  });

  it("muted / autoPlay / muted / playsInline / controls={false} 以源码静态断言验证（muted 不落 SSR markup）", () => {
    const source = readSource("src/components/player/PetPlayer.tsx");
    expect(source).toContain("autoPlay");
    expect(source).toContain("muted");
    expect(source).toContain("playsInline");
    expect(source).toContain("controls={false}");
    expect(source).toContain("loop={playback.loop}");
    expect(source).toContain("src={playback.asset_url}");
  });

  it("CR-1：loop 属白名单属性，只消费后端值（前端不做动作语义判断）", () => {
    const source = readSource("src/components/player/PetPlayer.tsx");
    expect(source).toContain("loop={playback.loop}");
    // FP-1：不得出现动作名比较（判断权归 AssetManager）
    expect(source).not.toMatch(/action\s*===\s*["']idle["']/);
  });
});

describe("Case 3b 循环属性直通（CR-1：只渲染，不判断语义）", () => {
  it("loop=true → video 携带 loop；loop=false → 不落 loop 属性", () => {
    usePetStore
      .getState()
      .setPlayback(makePlayback("/assets/pets/cat/actions/idle/idle.mp4", true));
    const looping = renderToStaticMarkup(<PetPlayer />);
    expect(looping).toContain("<video");
    expect(looping).toContain("loop");

    usePetStore
      .getState()
      .setPlayback(makePlayback("/assets/pets/cat/actions/heart/heart.mp4"));
    const single = renderToStaticMarkup(<PetPlayer />);
    expect(single).toContain("<video");
    expect(single).not.toContain("loop");
  });
});

describe("Case 4 静态扫描（FP-1/FP-4：无 API / 无 setter / 无计时器 / 无播放状态）", () => {
  it("PetPlayer 无 API import / store setter / timer / 动画 / 第三方播放器", () => {
    const code = readSource("src/components/player/PetPlayer.tsx");
    expect(code).not.toMatch(/from\s+["'][^"']*api/);
    for (const setter of ["setPlayback", "setRecentEvents", "setStats"]) {
      expect(code).not.toContain(setter);
    }
    expect(code).not.toContain("setInterval");
    expect(code).not.toContain("setTimeout");
    expect(code).not.toContain("requestAnimationFrame");
    expect(code).not.toMatch(/from\s+["']framer-motion/);
    expect(code).not.toMatch(/from\s+["']react-player/);
  });

  it("PetPlayer 无本地播放状态（FP-4：无 useState/useEffect/ref/currentTime/progress/onEnded）", () => {
    const code = readSource("src/components/player/PetPlayer.tsx");
    expect(code).not.toContain("useState");
    expect(code).not.toContain("useEffect");
    expect(code).not.toContain("useRef");
    expect(code).not.toContain("currentTime");
    expect(code).not.toContain("progress");
    expect(code).not.toContain("onEnded");
    expect(code).not.toContain("localStorage");
  });
});

/** 剥离块注释与行注释 —— 守卫约束的是代码，注释里的禁止性说明是合法的。 */
function readSource(rel: string): string {
  const source = readFileSync(
    fileURLToPath(new URL(`../../${rel}`, import.meta.url)),
    "utf-8",
  );
  return source
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^\s*\/\/.*$/gm, "");
}
