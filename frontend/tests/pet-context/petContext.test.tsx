/**
 * Phase 3.2-B 宠物上下文测试（**MPF-1 ~ MPF-6** 验收）。
 *
 * 运行：`npm test`（vitest run，node 环境、无 jsdom、零新增依赖）。
 *
 * 覆盖（指令 Step 2 目标 4）：
 * 1. **默认 pet context** —— 未选择宠物 ⇒ 连接地址**逐字**等于 3.2-B 之前（不带 query）；
 * 2. **cat_001 context** —— 连接地址带 `?pet_id=cat_001`；
 * 3. **dog_001 context** —— 连接地址带 `?pet_id=dog_001`；
 * 4. **selector change 行为** —— 切换 ⇒ 旧连接 `close()` + 新上下文连接 `connect()`，
 *    任一时刻**至多一条**连接（MPF-4：用户主动重建，**非**自动重连）；
 * 5. **websocket URL pet_id 拼接** —— `resolvePushUrl(petId)` 的编码 / 裁剪 / 同源推导；
 * 6. **push envelope 仍按原 schema 消费** —— WM-1 恰 4 字段；非法帧仍拒收（MPF-6）。
 *
 * 手法说明（与既有测试一致）：effects 不在本环境执行，故
 * 「生产建连路径」用 `vi.stubGlobal("WebSocket", …)` 拦截 `defaultSocketFactory`
 * 真实捕获 URL —— 不注入 client，走的就是 `App → useRuntimePush → createWebSocketClient`
 * 的同一条代码路径；React 渲染部分沿用 `react-dom/server` 静态渲染 + store 模块 mock。
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { useSyncExternalStore } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import PetSelector from "../../src/components/PetSelector";
import { AVAILABLE_PETS, DEFAULT_SELECTED_PET_ID } from "../../src/config/pets";
import { startRuntimePush } from "../../src/hooks/useRuntimePush";
import {
  FALLBACK_WS_ORIGIN,
  PUSH_PATH,
  createWebSocketClient,
  resolvePushUrl,
} from "../../src/services/websocketClient";
import { usePetStore } from "../../src/stores/usePetStore";

/**
 * zustand v5 的 SSR 路径读 `getInitialState()`（创建时初始态），`setState` 变更在静态渲染
 * 里不可见 ⇒ mock store 模块：复用真实 store 的 getState / setState / subscribe
 * （状态行为与被测对象完全一致），仅把 `useSyncExternalStore` 的 server snapshot 指向**当前态**。
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

// ---------------------------------------------------------------------------
// WM-1 契约夹具（恰 4 字段）
// ---------------------------------------------------------------------------

const GIFT_ENVELOPE = {
  event_type: "gift",
  payload: { gift_name: "小心心", gift_count: 1 },
  timestamp: "2026-09-22T08:00:00Z",
  source: "ws",
};

// ---------------------------------------------------------------------------
// 生产建连路径的 socket 拦截（替换运行时内建 WebSocket）
// ---------------------------------------------------------------------------

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];

  static urls(): string[] {
    return FakeWebSocket.instances.map((s) => s.url);
  }

  static open(): FakeWebSocket[] {
    return FakeWebSocket.instances.filter((s) => !s.closed);
  }

  static reset(): void {
    FakeWebSocket.instances = [];
  }

  readonly url: string;
  closed = false;
  onmessage: ((event: { data: unknown }) => void) | null = null;

  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
  }

  close(): void {
    this.closed = true;
  }

  /** 模拟服务端推送一帧。 */
  emit(data: unknown): void {
    this.onmessage?.({ data });
  }
}

beforeEach(() => {
  FakeWebSocket.reset();
  vi.stubGlobal("WebSocket", FakeWebSocket);
  usePetStore.setState({
    playback: null,
    recentEvents: [],
    stats: null,
    petContext: { selectedPetId: DEFAULT_SELECTED_PET_ID },
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

// ---------------------------------------------------------------------------
// 5) websocket URL pet_id 拼接（MPF-3）
// ---------------------------------------------------------------------------

describe("MPF-3 —— WS URL 的 pet_id 拼接", () => {
  const BASE = `${FALLBACK_WS_ORIGIN}${PUSH_PATH}`;

  it("未给 / null / undefined ⇒ 裸地址（与 3.2-B 之前逐字一致）", () => {
    expect(resolvePushUrl()).toBe(BASE);
    expect(resolvePushUrl(null)).toBe(BASE);
    expect(resolvePushUrl(undefined)).toBe(BASE);
    expect(resolvePushUrl("cat_001").endsWith(PUSH_PATH)).toBe(false);
  });

  it("空串 / 纯空白 ⇒ 仍为裸地址（避免发出必被 backend close(1008) 的空键）", () => {
    expect(resolvePushUrl("")).toBe(BASE);
    expect(resolvePushUrl("   ")).toBe(BASE);
  });

  it("合法键 ⇒ 追加 ?pet_id=<key>，且做 URL 编码与首尾裁剪", () => {
    expect(resolvePushUrl("cat_001")).toBe(`${BASE}?pet_id=cat_001`);
    expect(resolvePushUrl("  dog_001  ")).toBe(`${BASE}?pet_id=dog_001`);
    // 非 ASCII / 保留字符必须编码（backend 侧 strip 后按字面比对，未编码会错配）
    expect(resolvePushUrl("团子")).toBe(`${BASE}?pet_id=${encodeURIComponent("团子")}`);
  });

  it("有 location 时仍按同源推导，并保留 pet_id（http→ws / https→wss）", () => {
    vi.stubGlobal("location", { protocol: "https:", host: "pet.example.com" });
    expect(resolvePushUrl("cat_001")).toBe(
      `wss://pet.example.com${PUSH_PATH}?pet_id=cat_001`,
    );
    vi.stubGlobal("location", { protocol: "http:", host: "pet.example.com" });
    expect(resolvePushUrl()).toBe(`ws://pet.example.com${PUSH_PATH}`);
  });

  it("createWebSocketClient 透传 petId；同实例 connect() 仍幂等（PC-6）", () => {
    const client = createWebSocketClient({
      onMessage: () => {},
      petId: "cat_001",
      // 形状满足 SocketLike（close + onmessage）；仅记录，不真正连网
      socketFactory: (url) => new FakeWebSocket(url),
    });
    client.connect();
    client.connect();
    expect(FakeWebSocket.urls()).toHaveLength(1);
    expect(FakeWebSocket.urls()[0]).toBe(`${BASE}?pet_id=cat_001`);
  });
});

// ---------------------------------------------------------------------------
// 1 / 2 / 3) 默认 · cat_001 · dog_001 context（走生产建连路径）
// ---------------------------------------------------------------------------

describe("MPF-2 —— 默认 / cat_001 / dog_001 宠物上下文", () => {
  const BASE = `${FALLBACK_WS_ORIGIN}${PUSH_PATH}`;

  it("默认 pet context：store 初值为 null，建连不带 pet_id", () => {
    expect(usePetStore.getState().petContext.selectedPetId).toBeNull();

    const stop = startRuntimePush({ petId: usePetStore.getState().petContext.selectedPetId });
    expect(FakeWebSocket.urls()).toEqual([BASE]);
    expect(FakeWebSocket.open()).toHaveLength(1);
    stop();
  });

  it("cat_001 context：建连 URL 带 ?pet_id=cat_001，且只建一条连接", () => {
    startRuntimePush({ petId: "cat_001" });
    expect(FakeWebSocket.urls()).toEqual([`${BASE}?pet_id=cat_001`]);
    expect(FakeWebSocket.open()).toHaveLength(1);
  });

  it("dog_001 context：建连 URL 带 ?pet_id=dog_001（与 cat 不共用连接）", () => {
    startRuntimePush({ petId: "dog_001" });
    expect(FakeWebSocket.urls()).toEqual([`${BASE}?pet_id=dog_001`]);
    expect(FakeWebSocket.open()).toHaveLength(1);
  });

  it("目录键口径与 backend 一致：cat_001 / dog_001 / panda_001", () => {
    expect(AVAILABLE_PETS.map((p) => p.pet_id)).toEqual([
      "cat_001",
      "dog_001",
      "panda_001",
    ]);
  });
});

// ---------------------------------------------------------------------------
// 4) selector change 行为（MPF-4）
// ---------------------------------------------------------------------------

describe("MPF-4 —— 切换宠物 ⇒ 重建上下文连接", () => {
  const BASE = `${FALLBACK_WS_ORIGIN}${PUSH_PATH}`;

  /** 复刻 `useRuntimePush` 的 effect 语义：petId 变化时先 cleanup 再重新建连。 */
  function runEffectSequence(petIds: (string | null)[]): (() => void)[] {
    const stops: (() => void)[] = [];
    let current: (() => void) | null = null;
    for (const petId of petIds) {
      current?.(); // effect cleanup（close 旧连接）
      current = startRuntimePush({ petId });
      stops.push(current);
    }
    return stops;
  }

  it("null → cat_001 → dog_001：每次切换都 close 旧连接并建新连接", () => {
    runEffectSequence([null, "cat_001", "dog_001"]);

    expect(FakeWebSocket.urls()).toEqual([
      BASE,
      `${BASE}?pet_id=cat_001`,
      `${BASE}?pet_id=dog_001`,
    ]);
    // 任一时刻至多一条存活连接（切走的那条必须已关闭）
    expect(FakeWebSocket.open()).toHaveLength(1);
    expect(FakeWebSocket.open()[0].url).toBe(`${BASE}?pet_id=dog_001`);
    expect(FakeWebSocket.instances[0].closed).toBe(true);
    expect(FakeWebSocket.instances[1].closed).toBe(true);
  });

  it("切回默认宠物：连接地址回到裸地址", () => {
    runEffectSequence(["cat_001", null]);
    expect(FakeWebSocket.urls()).toEqual([`${BASE}?pet_id=cat_001`, BASE]);
    expect(FakeWebSocket.open()).toHaveLength(1);
  });

  it("store 切换只动 petContext，不触三块服务器快照", () => {
    usePetStore.getState().setPlayback({
      pet_id: "cat_001",
      state: "playing",
      action: "heart",
      asset_url: "/assets/pets/cat/actions/heart/heart.mp4",
      queue_size: 0,
      last_event: "gift",
    });
    usePetStore.getState().setStats({ events: { gift: 1 }, actions: {}, total: 1 });

    usePetStore.getState().setSelectedPet("dog_001");

    const state = usePetStore.getState();
    expect(state.petContext.selectedPetId).toBe("dog_001");
    expect(state.playback?.pet_id).toBe("cat_001");
    expect(state.stats?.total).toBe(1);

    usePetStore.getState().setSelectedPet(null);
    expect(usePetStore.getState().petContext.selectedPetId).toBeNull();
  });

  it("无自动重连：transport 不监听 close / error，也不含任何退避/心跳（PC-6 原样有效）", () => {
    const code = read("src/services/websocketClient.ts");
    expect(code).not.toContain('addEventListener("close"');
    expect(code).not.toContain('addEventListener("error"');
    expect(code).not.toContain("reconnect");
    expect(code).not.toContain("setInterval");
    expect(code).not.toContain("setTimeout");
    // 只订阅 message 一种事件
    expect(code).toContain('addEventListener("message", handleMessage)');
  });
});

// ---------------------------------------------------------------------------
// MPF-5 选择器 UI 与切换注入
// ---------------------------------------------------------------------------

describe("MPF-5 —— PetSelector 与 usePetContext", () => {
  it("选择器渲染「默认宠物」+ 全部目录项（顺序与目录一致）", () => {
    const html = renderToStaticMarkup(
      <PetSelector availablePets={AVAILABLE_PETS} onSelect={() => {}} />,
    );
    expect(html).toContain('data-testid="pet-selector"');
    const labels = [...html.matchAll(/<option[^>]*>([^<]+)<\/option>/g)].map((m) => m[1]);
    expect(labels).toEqual(["默认宠物", "小橘", "旺财", "团子"]);
  });

  it("选择器反映当前宠物（store 经 hook 供给）", () => {
    usePetStore.getState().setSelectedPet("dog_001");
    const html = renderToStaticMarkup(
      <PetSelector availablePets={AVAILABLE_PETS} onSelect={() => {}} />,
    );
    expect(html).toContain('data-selected-pet="dog_001"');

    usePetStore.getState().setSelectedPet(null);
    const htmlDefault = renderToStaticMarkup(
      <PetSelector availablePets={AVAILABLE_PETS} onSelect={() => {}} />,
    );
    expect(htmlDefault).toContain('data-selected-pet=""');
  });

  it("onSelect 契约：选项值 = 回传的 pet 键，且空串映射为 null（默认宠物）", () => {
    const seen: (string | null)[] = [];
    const html = renderToStaticMarkup(
      <PetSelector
        availablePets={AVAILABLE_PETS}
        onSelect={(petId) => seen.push(petId)}
      />,
    );
    // DOM 事件在本环境不可触发 ⇒ 断言「选项值 = 会回传的键」这一映射契约
    for (const pet of AVAILABLE_PETS) {
      expect(html).toContain(`value="${pet.pet_id}"`);
    }
    expect(html).toContain('value=""'); // 默认宠物占位项
    expect(seen).toEqual([]); // 渲染本身不触发切换

    // 空串 ↔ null 的映射在组件内显式发生；组件**不**直写 store
    const code = read("src/components/PetSelector.tsx");
    expect(code).toContain("onSelect(raw === DEFAULT_OPTION_VALUE ? null : raw)");
    expect(code).not.toContain("setSelectedPet");
  });

  it("App 把当前宠物接到 push 连接，并把切换函数注入选择器", () => {
    const app = read("src/App.tsx");
    expect(app).toContain("useRuntimePush(selectedPetId)");
    expect(app).toContain("<PetSelector");
    expect(app).toContain("onSelect={selectPet}");
    // RF-3：App 仍无本地 state
    expect(app).not.toContain("useState(");
  });

  it("useRuntimePush 的 effect 以 petId 为依赖（切换即重建）", () => {
    const hook = read("src/hooks/useRuntimePush.ts");
    expect(hook).toContain("[petId]");
    expect(hook).toContain("petId: options?.petId ?? null");
  });

  it("usePetContext 是 app 侧唯一写入口，且不触 API / 不建连接", () => {
    const code = read("src/hooks/usePetContext.ts");
    expect(code).toContain("setSelectedPet");
    expect(code).not.toMatch(/from\s+["'][^"']*api/);
    expect(code).not.toContain("WebSocket");
    expect(code).not.toContain("fetch(");
  });
});

// ---------------------------------------------------------------------------
// 6) push envelope 仍按原 schema 消费（MPF-6）
// ---------------------------------------------------------------------------

describe("MPF-6 —— push 解析与写入语义零变更", () => {
  function harnessWithPet(petId: string | null) {
    const invalid: string[] = [];
    const client = createWebSocketClient({
      onMessage: (envelope) => usePetStore.getState().applyPushEvent(envelope),
      onInvalid: (reason) => invalid.push(reason),
      petId,
      socketFactory: (url) => new FakeWebSocket(url),
    });
    client.connect();
    return { socket: FakeWebSocket.instances[0], invalid };
  }

  /** 断言一条 envelope「恰 4 字段」（WM-1）。 */
  function expectWm1Shape(envelope: Record<string, unknown>): void {
    expect(Object.keys(envelope).sort()).toEqual([
      "event_type",
      "payload",
      "source",
      "timestamp",
    ]);
  }

  it("WM-1 恰 4 字段 envelope 照常写入 store（与宠物上下文无关）", () => {
    expectWm1Shape(GIFT_ENVELOPE);
    const { socket } = harnessWithPet("cat_001");
    socket.emit(JSON.stringify(GIFT_ENVELOPE));

    const events = usePetStore.getState().recentEvents;
    expect(events).toHaveLength(1);
    expect(events[0]?.event_type).toBe("gift");
    expect(events[0]?.platform).toBe("ws"); // = envelope.source
    expect(events[0]?.created_at).toBe(GIFT_ENVELOPE.timestamp);
    expect(events[0]?.payload).toEqual({ gift_name: "小心心", gift_count: 1 });
    // push 帧不含库内派生字段 ⇒ 一律 null（PC-4 原样）
    expect(events[0]?.pet_id).toBeNull();
    expect(events[0]?.action_name).toBeNull();
  });

  it("非法帧（多发字段 / 越白名单 / 非 JSON）一律拒收，零写入", () => {
    const { socket, invalid } = harnessWithPet("dog_001");
    socket.emit(JSON.stringify({ ...GIFT_ENVELOPE, room_id: "r-1" })); // 5 字段
    socket.emit(JSON.stringify({ ...GIFT_ENVELOPE, event_type: "follow" })); // 白名单外
    socket.emit("not-json");

    expect(usePetStore.getState().recentEvents).toEqual([]);
    expect(invalid).toHaveLength(3);
  });

  it("push 写入形状不随 pet 上下文改变（null / cat_001 / dog_001 一致）", () => {
    for (const petId of [null, "cat_001", "dog_001"]) {
      usePetStore.setState({ recentEvents: [] });
      FakeWebSocket.reset();
      const { socket } = harnessWithPet(petId);
      socket.emit(JSON.stringify(GIFT_ENVELOPE));

      const events = usePetStore.getState().recentEvents;
      expect(events, String(petId)).toHaveLength(1);
      expect(events[0]?.platform, String(petId)).toBe("ws");
      expect(events[0]?.payload, String(petId)).toEqual({
        gift_name: "小心心",
        gift_count: 1,
      });
      // 连接地址带 pet_id，但写入 store 的形状与默认路径**完全一致**
      expect(FakeWebSocket.urls()[0], String(petId)).toContain(PUSH_PATH);
    }
  });
});

// ---------------------------------------------------------------------------
// 新增文件的边界静态守卫
// ---------------------------------------------------------------------------

describe("MPF-1 / MPF-7 —— 新增文件边界", () => {
  it("config/pets.ts 是纯静态配置：零网络 / 零 store / 零副作用依赖", () => {
    const code = read("src/config/pets.ts");
    expect(code).not.toContain("fetch(");
    expect(code).not.toContain("WebSocket");
    expect(code).not.toContain("usePetStore");
    expect(code).not.toMatch(/from\s+["']zustand/);
    expect(code).not.toContain("readdir");
  });

  it("PetSelector 零 API / 零 socket / 零计时器 / 零本地 state（只经 store 读）", () => {
    const code = read("src/components/PetSelector.tsx");
    expect(code).toMatch(/usePetStore/);
    expect(code).not.toMatch(/from\s+["'][^"']*api/);
    expect(code).not.toContain("WebSocket");
    expect(code).not.toContain("useState");
    expect(code).not.toContain("setInterval");
    expect(code).not.toContain("fetch(");
  });

  it("usePetContext 经 store 读当前宠物并暴露目录（不建连接、不拉数据）", () => {
    const code = read("src/hooks/usePetContext.ts");
    expect(code).toContain("petContext.selectedPetId");
    expect(code).toContain("AVAILABLE_PETS");
    expect(code).not.toContain("loadRuntimeData");
    expect(code).not.toContain("useRuntimePush");
  });
});

/** 读取源码并剥离注释（守卫约束代码本身；docstring 中的禁止性说明合法）。 */
function read(rel: string): string {
  return readFileSync(fileURLToPath(new URL(`../../${rel}`, import.meta.url)), "utf-8")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^\s*\/\/.*$/gm, "");
}
