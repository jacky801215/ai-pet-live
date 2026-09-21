/**
 * Frontend push channel 测试（Phase 2.2-6 / PC-1 ~ PC-6 验收）。
 *
 * 运行：`npm test`（vitest run，**node 环境、零新增依赖、无 jsdom**）。
 *
 * 覆盖（指令 Step 6 五条 + PC 守卫）：
 * 1. 连接初始化：`connect()` 成功（socketFactory 恰一次、URL 含 `/api/ws`、幂等不重建）；
 * 2. 收到 event（gift）：store 更新（`recentEvents` 头部派生项 + `playback.last_event`）；
 * 3. 禁止 refresh：`loadRuntimeData()` **0 调用**（mock 计数 + 源码静态守卫）；
 * 4. 非法 envelope：**拒收**，store 完全不变；
 * 5. disconnect：`close()` 生效且**不触发 reconnect**（socketFactory 仍为 1 次 + 源码守卫）；
 * 6. 生命周期（PC-1）：mount → connect、cleanup → close；写入**必须经 store**（PC-5）；
 * 7. UI 更新边界：App 接线 `useRuntimePush`，组件零改动、零 socket 依赖；零新依赖。
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  createWebSocketClient,
  parsePushEnvelope,
  resolvePushUrl,
  FALLBACK_WS_ORIGIN,
  PUSH_PATH,
  type SocketLike,
} from "../../src/services/websocketClient";
import { startRuntimePush } from "../../src/hooks/useRuntimePush";
import { usePetStore } from "../../src/stores/usePetStore";
import type { EventItem, PlaybackState } from "../../src/types/api";
import type { PushEnvelope } from "../../src/types/push";

/** Test 3 专用：把 `loadRuntimeData` 换成可计数 mock（真实模块其余导出保持原样）。 */
const hookMocks = vi.hoisted(() => ({ loadRuntimeData: vi.fn() }));
vi.mock("../../src/hooks/usePetRuntime", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("../../src/hooks/usePetRuntime")>();
  return { ...actual, loadRuntimeData: hookMocks.loadRuntimeData };
});

import { loadRuntimeData } from "../../src/hooks/usePetRuntime";

const GIFT_ENVELOPE = {
  event_type: "gift",
  payload: { gift_name: "小心心", gift_count: 1 },
  timestamp: "2026-09-21T06:00:00Z",
  source: "ws",
} as const;

const SAMPLE_PLAYBACK: PlaybackState = {
  pet_id: "cat_001",
  state: "idle",
  action: null,
  asset_url: null,
  queue_size: 0,
  last_event: null,
};

/** 注入式假 socket（node 环境无真实 WebSocket；零依赖替身）。 */
class FakeSocket implements SocketLike {
  close = vi.fn();
  listeners = new Map<string, Array<(event: { data: unknown }) => void>>();

  addEventListener(type: string, listener: (event: { data: unknown }) => void): void {
    const bucket = this.listeners.get(type) ?? [];
    bucket.push(listener);
    this.listeners.set(type, bucket);
  }

  /** 模拟服务端下发一帧（本步服务端推送帧未实现——见 PC 文档「缺口声明」）。 */
  emit(type: string, data: unknown): void {
    for (const listener of this.listeners.get(type) ?? []) {
      listener({ data });
    }
  }

  listenerTypes(): string[] {
    return [...this.listeners.keys()];
  }
}

interface Harness {
  client: ReturnType<typeof createWebSocketClient>;
  sockets: FakeSocket[];
  urls: string[];
  invalid: Array<{ reason: string; raw: unknown }>;
  factoryCalls: () => number;
}

function makeHarness(): Harness {
  const sockets: FakeSocket[] = [];
  const urls: string[] = [];
  const invalid: Array<{ reason: string; raw: unknown }> = [];

  const client = createWebSocketClient({
    url: `${FALLBACK_WS_ORIGIN}${PUSH_PATH}`,
    onMessage: (envelope: PushEnvelope) => {
      usePetStore.getState().applyPushEvent(envelope);
    },
    onInvalid: (reason: string, raw: unknown) => {
      invalid.push({ reason, raw });
    },
    socketFactory: (url: string): SocketLike => {
      urls.push(url);
      const socket = new FakeSocket();
      sockets.push(socket);
      return socket;
    },
  });

  return { client, sockets, urls, invalid, factoryCalls: () => sockets.length };
}

beforeEach(() => {
  hookMocks.loadRuntimeData.mockClear();
  usePetStore.setState({ playback: null, recentEvents: [], stats: null });
});

// ---------------------------------------------------------------------------
// Test 1：连接初始化
// ---------------------------------------------------------------------------

describe("Test 1 — 连接初始化（PC-1）", () => {
  it("connect() 建立连接：socketFactory 恰一次、URL 指向 /api/ws", () => {
    const harness = makeHarness();
    expect(harness.client.isConnected()).toBe(false);

    harness.client.connect();

    expect(harness.factoryCalls()).toBe(1);
    expect(harness.urls[0]).toBe(`${FALLBACK_WS_ORIGIN}${PUSH_PATH}`);
    expect(harness.urls[0].endsWith(PUSH_PATH)).toBe(true);
    expect(harness.client.isConnected()).toBe(true);
  });

  it("connect() 幂等：重复调用不重建连接（PC-6：无重连）", () => {
    const harness = makeHarness();
    harness.client.connect();
    harness.client.connect();
    harness.client.connect();

    expect(harness.factoryCalls()).toBe(1);
  });

  it("resolvePushUrl()：无 location 时退回兜底 origin；路径恒为 /api/ws", () => {
    expect(resolvePushUrl()).toBe(`${FALLBACK_WS_ORIGIN}${PUSH_PATH}`);
    expect(PUSH_PATH).toBe("/api/ws");
  });
});

// ---------------------------------------------------------------------------
// Test 2：收到 event → store 更新
// ---------------------------------------------------------------------------

describe("Test 2 — 收到 event：store 更新（PC-4 / PC-5）", () => {
  it("gift envelope → recentEvents 头部派生项 + playback.last_event 同步", () => {
    const harness = makeHarness();
    usePetStore.getState().setPlayback(SAMPLE_PLAYBACK);
    harness.client.connect();

    harness.sockets[0].emit("message", JSON.stringify(GIFT_ENVELOPE));

    const state = usePetStore.getState();
    expect(state.recentEvents).toHaveLength(1);
    const item: EventItem = state.recentEvents[0];
    expect(item.event_type).toBe("gift");
    expect(item.payload).toEqual({ gift_name: "小心心", gift_count: 1 });
    expect(item.created_at).toBe("2026-09-21T06:00:00Z");
    expect(item.platform).toBe("ws");
    expect(item.id).toBeLessThan(0); // 本地负值占位（唯一，不冒充库内 id）
    // PlaybackState 6 字段冻结：仅 last_event 变，其余原样
    expect(state.playback).toEqual({ ...SAMPLE_PLAYBACK, last_event: "gift" });
    expect(Object.keys(state.playback ?? {})).toHaveLength(6);
  });

  it("多条 push：派生 id 唯一且新条目在前（列表可安全重渲）", () => {
    const harness = makeHarness();
    harness.client.connect();
    harness.sockets[0].emit("message", JSON.stringify(GIFT_ENVELOPE));
    harness.sockets[0].emit(
      "message",
      JSON.stringify({ ...GIFT_ENVELOPE, event_type: "like", payload: { like_count: 3 } }),
    );

    const items = usePetStore.getState().recentEvents;
    expect(items.map((i) => i.event_type)).toEqual(["like", "gift"]);
    expect(new Set(items.map((i) => i.id)).size).toBe(2);
  });

  it("playback 为 null 时不臆造快照（只并入事件明细）", () => {
    const harness = makeHarness();
    harness.client.connect();
    harness.sockets[0].emit("message", JSON.stringify(GIFT_ENVELOPE));

    expect(usePetStore.getState().playback).toBeNull();
    expect(usePetStore.getState().recentEvents).toHaveLength(1);
  });
});

// ---------------------------------------------------------------------------
// Test 3：禁止 refresh
// ---------------------------------------------------------------------------

describe("Test 3 — push 不触发 refresh（PC-3 / RF-1 不变）", () => {
  it("push 处理全程 loadRuntimeData() 零调用", () => {
    const harness = makeHarness();
    harness.client.connect();
    harness.sockets[0].emit("message", JSON.stringify(GIFT_ENVELOPE));

    expect(hookMocks.loadRuntimeData).not.toHaveBeenCalled();
    expect(loadRuntimeData).not.toHaveBeenCalled();
  });

  it("client / hook 源码不出现 refresh / loadRuntimeData / api import / fetch", () => {
    const client = read("src/services/websocketClient.ts");
    const hook = read("src/hooks/useRuntimePush.ts");
    for (const source of [client, hook]) {
      expect(source).not.toContain("loadRuntimeData");
      expect(source).not.toContain("refresh");
      expect(source).not.toMatch(/from\s+["'][^"']*\/api/);
      expect(source).not.toContain("fetch(");
    }
  });
});

// ---------------------------------------------------------------------------
// Test 4：非法 envelope → store 不变
// ---------------------------------------------------------------------------

describe("Test 4 — 非法 envelope 拒收（PC-2）", () => {
  it("四类非法帧全部拒收：store 完全不变", () => {
    const harness = makeHarness();
    usePetStore.getState().setPlayback(SAMPLE_PLAYBACK);
    harness.client.connect();

    const before = JSON.stringify({
      playback: usePetStore.getState().playback,
      recentEvents: usePetStore.getState().recentEvents,
    });

    const badFrames: unknown[] = [
      "{not-json",
      JSON.stringify({ event_type: "gift", payload: {}, timestamp: "t" }), // 缺 source
      JSON.stringify({ ...GIFT_ENVELOPE, event_type: "follow" }), // 白名单外
      JSON.stringify({ ...GIFT_ENVELOPE, payload: null }), // payload 非对象
    ];
    for (const frame of badFrames) {
      harness.sockets[0].emit("message", frame);
    }

    const after = JSON.stringify({
      playback: usePetStore.getState().playback,
      recentEvents: usePetStore.getState().recentEvents,
    });
    expect(after).toBe(before);
    expect(harness.invalid).toHaveLength(badFrames.length); // 拒收走审计回调
  });

  it("parsePushEnvelope：5 字段 / 非字符串 / 数组 / 额外字段 一律 null", () => {
    expect(parsePushEnvelope(JSON.stringify(GIFT_ENVELOPE))).toEqual(GIFT_ENVELOPE);
    expect(parsePushEnvelope({ ...GIFT_ENVELOPE })).toBeNull(); // 非字符串帧
    expect(parsePushEnvelope("[]")).toBeNull();
    expect(
      parsePushEnvelope(JSON.stringify({ ...GIFT_ENVELOPE, extra: 1 })),
    ).toBeNull(); // WM-1：恰 4 字段
    expect(parsePushEnvelope(JSON.stringify({ ...GIFT_ENVELOPE, timestamp: 1 }))).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Test 5：disconnect 不触发 reconnect
// ---------------------------------------------------------------------------

describe("Test 5 — disconnect 不重连（PC-6 / WS-5）", () => {
  it("close() 关闭连接；不重建、只订阅 message 事件", () => {
    const harness = makeHarness();
    harness.client.connect();
    const socket = harness.sockets[0];

    harness.client.close();

    expect(socket.close).toHaveBeenCalledTimes(1);
    expect(harness.client.isConnected()).toBe(false);
    expect(harness.factoryCalls()).toBe(1); // 未重建
    expect(socket.listenerTypes()).toEqual(["message"]); // 无 close/error/open 钩子

    // 断线后再 connect() 才新建（人工/挂载驱动；无自动重连）
    harness.client.connect();
    expect(harness.factoryCalls()).toBe(2);
  });

  it("源码守卫：无 reconnect / heartbeat / replay / timer / 自动重试", () => {
    const client = read("src/services/websocketClient.ts");
    for (const token of [
      "reconnect",
      "heartbeat",
      "message replay",
      "setTimeout",
      "setInterval",
      "queue sync",
    ]) {
      expect(client).not.toContain(token);
    }
  });
});

// ---------------------------------------------------------------------------
// Test 6/7：生命周期接线 + UI 边界
// ---------------------------------------------------------------------------

describe("Test 6 — 生命周期与 UI 边界（PC-1 / PC-5）", () => {
  it("startRuntimePush：mount → connect；cleanup → close；写入经 store", () => {
    const harness = makeHarness();
    const stop = startRuntimePush({ client: harness.client });

    expect(harness.client.isConnected()).toBe(true);
    harness.sockets[0].emit("message", JSON.stringify(GIFT_ENVELOPE));
    expect(usePetStore.getState().recentEvents).toHaveLength(1);

    stop();
    expect(harness.client.isConnected()).toBe(false);
  });

  it("App 接线 useRuntimePush，且仍无 API import / store setter / fetch / useState", () => {
    const app = read("src/App.tsx");
    expect(app).toContain("useRuntimePush");
    expect(app).not.toMatch(/from\s+["'][^"']*api/);
    expect(app).not.toContain("fetch(");
    expect(app).not.toContain("useState(");
    for (const setter of ["setPlayback", "setRecentEvents", "setStats", "applyPushEvent"]) {
      expect(app).not.toContain(setter);
    }
  });

  it("组件零改动：三个展示组件均不 import socket / 不直连 transport（PC-5）", () => {
    for (const rel of [
      "src/components/StatusBar.tsx",
      "src/components/EventList.tsx",
      "src/components/PetStage.tsx",
      "src/components/player/PetPlayer.tsx",
    ]) {
      const code = read(rel);
      expect(code).not.toContain("websocket");
      expect(code).not.toContain("WebSocket");
    }
  });

  it("零新依赖：package.json dependencies 恰 3 个（WebSocket 为运行时内建）", () => {
    const pkg = JSON.parse(read("package.json")) as {
      dependencies: Record<string, string>;
    };
    expect(Object.keys(pkg.dependencies).sort()).toEqual([
      "react",
      "react-dom",
      "zustand",
    ]);
  });
});

/** 读取源码并剥离注释（守卫约束代码本身；docstring 中的禁止性说明合法）。 */
function read(rel: string): string {
  return readFileSync(fileURLToPath(new URL(`../../${rel}`, import.meta.url)), "utf-8")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^\s*\/\/.*$/gm, "");
}
