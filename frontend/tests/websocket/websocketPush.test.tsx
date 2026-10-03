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
 * 8. **CR-6 受权增量（PC-2 / PC-4 / FS-3 v1.1）**：状态帧按帧型分流 →
 *    `store.applyPlaybackSnapshot()`（Case A）· 非法状态帧拒收且**不回退**（Case B）·
 *    两类帧**互斥**且事件帧回归不变（Case C）。
 * 9. **CR-6 / F4 = α 受权增量（出站方向）**：WM-1 出站 envelope 组装（Case D）·
 *    活动通道登记 / 注销与身份判定（Case E）· `simulateEvent` 经活动通道发送（Case F）。
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { beforeEach, describe, expect, it, vi } from "vitest";

import { simulateEvent } from "../../src/api/events";
import {
  buildPushEnvelope,
  createWebSocketClient,
  getActivePushChannel,
  parsePushEnvelope,
  parseStateSnapshot,
  releaseActivePushChannel,
  resolvePushUrl,
  sendActiveEnvelope,
  setActivePushChannel,
  FALLBACK_WS_ORIGIN,
  PUSH_PATH,
  type SocketLike,
} from "../../src/services/websocketClient";
import { startRuntimePush } from "../../src/hooks/useRuntimePush";
import { usePetStore } from "../../src/stores/usePetStore";
import type { EventItem, PlaybackState } from "../../src/types/api";
import { PUSH_EVENT_TYPES, type PushEnvelope } from "../../src/types/push";

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
  loop: false,
};

/** CR-6：服务端推送的**运行时**状态快照（与 SAMPLE_PLAYBACK 逐字段不同，便于断言「整份替换」）。 */
const RUNTIME_SNAPSHOT: PlaybackState = {
  pet_id: "cat_001",
  state: "playing",
  action: "heart",
  asset_url: "/assets/pets/cat/actions/heart/heart.mp4",
  queue_size: 0,
  last_event: "gift",
  loop: false,
};

/** CR-6 状态帧（PC-2 v1.1 形态：`{type, snapshot}`）。 */
const STATE_FRAME = { type: "playback_state", snapshot: RUNTIME_SNAPSHOT };

/** 注入式假 socket（node 环境无真实 WebSocket；零依赖替身）。 */
class FakeSocket implements SocketLike {
  close = vi.fn();
  /** CR-6 / F4 = α：出站捕获（触发通道改走 push 后，发送行为在此断言）。 */
  send = vi.fn();
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
  snapshots: PlaybackState[];
  factoryCalls: () => number;
}

function makeHarness(): Harness {
  const sockets: FakeSocket[] = [];
  const urls: string[] = [];
  const invalid: Array<{ reason: string; raw: unknown }> = [];
  const snapshots: PlaybackState[] = [];

  const client = createWebSocketClient({
    url: `${FALLBACK_WS_ORIGIN}${PUSH_PATH}`,
    onMessage: (envelope: PushEnvelope) => {
      usePetStore.getState().applyPushEvent(envelope);
    },
    onSnapshot: (snapshot: PlaybackState) => {
      snapshots.push(snapshot);
      usePetStore.getState().applyPlaybackSnapshot(snapshot);
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

  return { client, sockets, urls, invalid, snapshots, factoryCalls: () => sockets.length };
}

beforeEach(() => {
  hookMocks.loadRuntimeData.mockClear();
  usePetStore.setState({ playback: null, recentEvents: [], stats: null });
  // CR-6 / F4 = α：活动通道是**模块级**句柄 ⇒ 用例间必须显式归零（避免跨用例串台）
  setActivePushChannel(null);
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
    // PlaybackState 字段冻结（CR-1 起 7 字段）：仅 last_event 变，其余原样
    expect(state.playback).toEqual({ ...SAMPLE_PLAYBACK, last_event: "gift" });
    expect(Object.keys(state.playback ?? {})).toHaveLength(7);
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

  it("组件零改动：展示组件均不 import socket / 不直连 transport（PC-5）", () => {
    for (const rel of [
      "src/components/PetSelector.tsx",
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

// ---------------------------------------------------------------------------
// CR-6 受权增量：状态帧消费（PC-2 v1.1 / PC-4 v1.1 / FS-3 v1.1）
// ---------------------------------------------------------------------------

describe("Case A — 状态帧写入 store（整份替换 playback）", () => {
  it("状态帧 → playback 整份替换（state/action/asset_url 等全量更新）", () => {
    const harness = makeHarness();
    usePetStore.getState().setPlayback(SAMPLE_PLAYBACK);
    harness.client.connect();

    harness.sockets[0].emit("message", JSON.stringify(STATE_FRAME));

    const state = usePetStore.getState();
    expect(state.playback).toEqual(RUNTIME_SNAPSHOT); // 非「只改 last_event」，而是整份替换
    expect(Object.keys(state.playback ?? {})).toHaveLength(7); // API-2 七字段
    expect(state.playback?.state).toBe("playing");
    expect(state.playback?.asset_url).toBe("/assets/pets/cat/actions/heart/heart.mp4");
    expect(state.playback?.loop).toBe(false);
    expect(harness.snapshots).toHaveLength(1);
    expect(harness.invalid).toHaveLength(0);
  });

  it("状态帧只写 playback 切片：recentEvents / stats 一律不动", () => {
    const harness = makeHarness();
    usePetStore.getState().setPlayback(SAMPLE_PLAYBACK);
    usePetStore.getState().setStats({ events: { gift: 1 }, actions: {}, total: 1 });
    harness.client.connect();

    harness.sockets[0].emit("message", JSON.stringify(STATE_FRAME));

    const state = usePetStore.getState();
    expect(state.recentEvents).toEqual([]); // 未派生事件明细（区别于事件帧）
    expect(state.stats?.total).toBe(1);
  });

  it("重复同一状态帧幂等（整份替换，无累积副作用）", () => {
    const harness = makeHarness();
    usePetStore.getState().setPlayback(SAMPLE_PLAYBACK);
    harness.client.connect();

    harness.sockets[0].emit("message", JSON.stringify(STATE_FRAME));
    const first = usePetStore.getState().playback;
    harness.sockets[0].emit("message", JSON.stringify(STATE_FRAME));
    const second = usePetStore.getState().playback;

    expect(second).toEqual(first);
    expect(usePetStore.getState().recentEvents).toHaveLength(0);
  });

  it("初始 playback 为 null 时，状态帧可直接建立快照（不臆造、只采纳服务端值）", () => {
    const harness = makeHarness();
    harness.client.connect();

    harness.sockets[0].emit("message", JSON.stringify(STATE_FRAME));

    expect(usePetStore.getState().playback).toEqual(RUNTIME_SNAPSHOT);
  });
});

describe("Case B — 非法状态帧拒收（PC-2 v1.1）", () => {
  it("三类非法状态帧：store 完全不变 + 审计回调记录 + 不回退为事件帧解析", () => {
    const harness = makeHarness();
    usePetStore.getState().setPlayback(SAMPLE_PLAYBACK);
    harness.client.connect();

    const before = JSON.stringify({
      playback: usePetStore.getState().playback,
      recentEvents: usePetStore.getState().recentEvents,
    });

    const badFrames: unknown[] = [
      JSON.stringify({ type: "playback_state" }), // 缺 snapshot
      JSON.stringify({ type: "playback_state", snapshot: null }), // snapshot 非对象
      JSON.stringify({ type: "playback_state", snapshot: { pet_id: "cat_001" } }), // 字段集 ≠ 7
    ];
    for (const frame of badFrames) {
      harness.sockets[0].emit("message", frame);
    }

    const after = JSON.stringify({
      playback: usePetStore.getState().playback,
      recentEvents: usePetStore.getState().recentEvents,
    });
    expect(after).toBe(before);
    expect(harness.snapshots).toHaveLength(0);
    expect(harness.invalid).toHaveLength(badFrames.length);
    // 拒收发生在**状态帧分支**（未回退到 envelope 解析，故原因恒为 state frame）
    for (const record of harness.invalid) {
      expect(record.reason).toBe("invalid state frame");
    }
  });

  it("parseStateSnapshot：非状态帧 / 形状非法一律 null；合法帧返回七字段载荷", () => {
    expect(parseStateSnapshot(JSON.stringify(STATE_FRAME))).toEqual(RUNTIME_SNAPSHOT);
    expect(parseStateSnapshot(JSON.stringify(GIFT_ENVELOPE))).toBeNull(); // 事件帧 ≠ 状态帧
    expect(parseStateSnapshot(JSON.stringify({ type: "other", snapshot: RUNTIME_SNAPSHOT }))).toBeNull();
    expect(parseStateSnapshot({ ...STATE_FRAME })).toBeNull(); // 非字符串帧
    expect(parseStateSnapshot("[]")).toBeNull();
    expect(parseStateSnapshot(JSON.stringify({ type: "playback_state", snapshot: [] }))).toBeNull();
    expect(
      parseStateSnapshot(
        JSON.stringify({ type: "playback_state", snapshot: { ...RUNTIME_SNAPSHOT, extra: 1 } }),
      ),
    ).toBeNull(); // 字段集须恰 7
    expect(
      parseStateSnapshot(
        JSON.stringify({ type: "playback_state", snapshot: { pet_id: "cat_001" } }),
      ),
    ).toBeNull();
  });
});

describe("Case C — 两类帧互斥 + 事件帧回归（PC-2 v1.1）", () => {
  it("事件帧仍走 applyPushEvent：只改 last_event + 并入 recentEvents（不误入状态分支）", () => {
    const harness = makeHarness();
    usePetStore.getState().setPlayback(SAMPLE_PLAYBACK);
    harness.client.connect();

    harness.sockets[0].emit("message", JSON.stringify(GIFT_ENVELOPE));

    const state = usePetStore.getState();
    expect(harness.snapshots).toHaveLength(0); // 未走状态写通道
    expect(state.playback).toEqual({ ...SAMPLE_PLAYBACK, last_event: "gift" });
    expect(state.recentEvents).toHaveLength(1);
  });

  it("状态帧即使携带 envelope 四键也按状态帧处理（互斥、不回退）", () => {
    const harness = makeHarness();
    usePetStore.getState().setPlayback(SAMPLE_PLAYBACK);
    harness.client.connect();

    const hybridFrame = JSON.stringify({
      ...STATE_FRAME,
      event_type: "gift",
      payload: {},
      timestamp: "2026-09-21T06:00:00Z",
      source: "ws",
    });
    harness.sockets[0].emit("message", hybridFrame);

    const state = usePetStore.getState();
    expect(state.recentEvents).toHaveLength(0); // 未走事件写通道
    expect(state.playback).toEqual(RUNTIME_SNAPSHOT); // 走了状态写通道
    expect(harness.invalid).toHaveLength(0);
  });

  it("顶层带 type 但取值不符 ⇒ 走既有 envelope 路径（不误判为状态帧）", () => {
    const harness = makeHarness();
    harness.client.connect();

    const notStateFrame = JSON.stringify({
      type: "playback_state_v2",
      event_type: "gift",
      payload: {},
      timestamp: "2026-09-21T06:00:00Z",
      source: "ws",
    });
    harness.sockets[0].emit("message", notStateFrame);

    expect(harness.snapshots).toHaveLength(0); // 未进状态分支
    expect(harness.invalid).toHaveLength(1);
    expect(harness.invalid[0].reason).toBe("invalid envelope"); // 5 键 ⇒ envelope 恰 4 键校验失败
  });
});

// ---------------------------------------------------------------------------
// CR-6 / F4 = α 受权增量：出站（触发通道改走 push）
// ---------------------------------------------------------------------------

describe("Case D — 出站 WM-1 envelope 组装与发送", () => {
  it("buildPushEnvelope：恰 4 字段 + timestamp 为秒级 ISO-8601 + source 固定", () => {
    const envelope = buildPushEnvelope(
      "gift",
      { gift_name: "小心心", gift_count: 1 },
      () => new Date("2026-10-03T01:02:03.456Z"),
    );

    expect(Object.keys(envelope).sort()).toEqual([
      "event_type",
      "payload",
      "source",
      "timestamp",
    ]);
    expect(envelope.event_type).toBe("gift");
    expect(envelope.payload).toEqual({ gift_name: "小心心", gift_count: 1 });
    expect(envelope.timestamp).toBe("2026-10-03T01:02:03Z");
    expect(envelope.source).toBe("ws");
  });

  it("client.send：已连接经 socket 发出 JSON 文本；未连接返回 false（不缓冲、不排队）", () => {
    const harness = makeHarness();
    const envelope = buildPushEnvelope(
      "like",
      { like_count: 3 },
      () => new Date("2026-10-03T01:02:03Z"),
    );

    expect(harness.client.send(envelope)).toBe(false); // 尚未 connect

    harness.client.connect();
    expect(harness.client.send(envelope)).toBe(true);
    expect(harness.sockets[0].send).toHaveBeenCalledTimes(1);
    expect(harness.sockets[0].send).toHaveBeenCalledWith(JSON.stringify(envelope));

    harness.client.close();
    expect(harness.client.send(envelope)).toBe(false); // 已关闭：不重连、不补发
    expect(harness.sockets[0].send).toHaveBeenCalledTimes(1);
  });
});

describe("Case E — 活动推送通道登记（CR-6 / F4 = α）", () => {
  it("startRuntimePush 登记活动通道；cleanup 注销（不新增第二连接）", () => {
    expect(getActivePushChannel()).toBeNull();

    const harness = makeHarness();
    const stop = startRuntimePush({ client: harness.client });

    expect(getActivePushChannel()).toBe(harness.client); // 登记的即被接线的那一条连接
    expect(harness.factoryCalls()).toBe(1); // 只 connect 注入的那一条，**未**新建第二条连接
    expect(harness.client.isConnected()).toBe(true);

    stop();
    expect(getActivePushChannel()).toBeNull();
  });

  it("releaseActivePushChannel 只注销**同一实例**（切换宠物时新旧不串台）", () => {
    const older = makeHarness();
    const newer = makeHarness();

    setActivePushChannel(newer.client);
    releaseActivePushChannel(older.client); // 旧实例 cleanup：不得抹掉新实例
    expect(getActivePushChannel()).toBe(newer.client);

    releaseActivePushChannel(newer.client);
    expect(getActivePushChannel()).toBeNull();
  });

  it("sendActiveEnvelope：无活动通道 false；有活动通道 true（经该通道 socket 发出）", () => {
    const envelope = buildPushEnvelope("comment", { content: "好可爱" });
    expect(sendActiveEnvelope(envelope)).toBe(false); // 未接线

    const harness = makeHarness();
    const stop = startRuntimePush({ client: harness.client });

    expect(sendActiveEnvelope(envelope)).toBe(true);
    expect(harness.sockets[0].send).toHaveBeenCalledWith(JSON.stringify(envelope));

    stop();
    expect(sendActiveEnvelope(envelope)).toBe(false); // 注销后不再可达
  });
});

describe("Case F — simulateEvent 经 push 发送（F4 = α 真实实现）", () => {
  it("发出 WM-1 envelope：恰 4 字段、event_type ∈ 白名单、payload 原样（后端 adapter 可直接受理）", async () => {
    const harness = makeHarness();
    const stop = startRuntimePush({ client: harness.client });

    await simulateEvent({
      event_type: "gift",
      payload: { gift_name: "小心心", gift_count: 1 },
    });

    expect(harness.sockets[0].send).toHaveBeenCalledTimes(1);
    const sent = JSON.parse(harness.sockets[0].send.mock.calls[0][0] as string) as Record<
      string,
      unknown
    >;
    expect(Object.keys(sent).sort()).toEqual([
      "event_type",
      "payload",
      "source",
      "timestamp",
    ]);
    expect(sent.event_type).toBe("gift");
    expect(PUSH_EVENT_TYPES).toContain(sent.event_type);
    expect(sent.payload).toEqual({ gift_name: "小心心", gift_count: 1 });
    expect(typeof sent.timestamp).toBe("string");
    expect(harness.client.isConnected()).toBe(true);

    stop();
  });

  it("payload 省略 ⇒ 组装为 {}（WM-1 要求 payload 为对象，非空判定归后端）", async () => {
    const harness = makeHarness();
    const stop = startRuntimePush({ client: harness.client });

    await simulateEvent({ event_type: "system" });

    const sent = JSON.parse(harness.sockets[0].send.mock.calls[0][0] as string) as Record<
      string,
      unknown
    >;
    expect(sent.payload).toEqual({});
    stop();
  });

  it("无活动通道时 reject（不静默失败：错误原样进调用方 error 通道）", async () => {
    setActivePushChannel(null);

    await expect(
      simulateEvent({ event_type: "like", payload: { like_count: 3 } }),
    ).rejects.toThrow("push channel unavailable");
  });
});

/** 读取源码并剥离注释（守卫约束代码本身；docstring 中的禁止性说明合法）。 */
function read(rel: string): string {
  return readFileSync(fileURLToPath(new URL(`../../${rel}`, import.meta.url)), "utf-8")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^\s*\/\/.*$/gm, "");
}
