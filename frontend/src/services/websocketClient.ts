/**
 * websocketClient —— Frontend push channel 的**transport 部分**（PC-1 / PC-2 / PC-3 / PC-6）。
 *
 * 职责**仅**：`connect()` / `close()` / `onMessage()`——建连、关闭、把入站 envelope 转交 push handler。
 *
 * **禁止**（PC-1 / PC-3）：
 * - ❌ 业务处理（不判定动作、不消费队列、不修改素材、不生成 UI）；
 * - ❌ 调用 API refresh / `loadRuntimeData()`；❌ import `src/api/**`；❌ fetch；
 * - ❌ reconnect / heartbeat / message replay / multi client / queue sync（PC-6）。
 *
 * 入站帧处理（PC-2）：形状校验（4 字段齐全 + `event_type` ∈ 白名单 + `payload` 为对象 +
 * `timestamp`/`source` 为字符串）→ 合法**转交** `onMessage`；**非法拒收**（丢弃 + 可选审计回调），
 * **不写入 store**。
 *
 * 可测试性：socket 构造经 `socketFactory` 注入（零依赖、node 环境可测，无需 jsdom）。
 *
 * **Phase 3.2-B（MPF-3 / MPF-4，受权增量）**：建连地址可携带 backend Phase 3.2-A 的
 * **连接级** pet 上下文（`?pet_id=<key>`）。本文件**仍**只是 transport——
 * 不感知 pet 业务、不监听 `close`/`error`、**不自动重连**；「切换宠物」由调用方
 * `close()` 旧实例 + 以新 `petId` 新建实例实现（PC-6 的 reconnect 禁令**原样有效**）。
 */

import type { PushEnvelope } from "../types/push";
import { PUSH_ENVELOPE_KEYS, PUSH_EVENT_TYPES } from "../types/push";

/** WS 端点路径（与 backend `api/ws.py` 的 `/api/ws` 一致；PC-2：地址属配置，不属业务）。 */
export const PUSH_PATH = "/api/ws";

/** 无 `location` 时的兜底 origin（node/测试环境；生产浏览器恒走 `location`）。 */
export const FALLBACK_WS_ORIGIN = "ws://127.0.0.1:8000";

/** socket 最小形状（`WebSocket` 子集；测试用替身只需满足此接口）。 */
export interface SocketLike {
  close: () => void;
  addEventListener?: (type: string, listener: (event: { data: unknown }) => void) => void;
  onmessage?: ((event: { data: unknown }) => void) | null;
}

export interface WebSocketClientOptions {
  /** push handler（PC-2：合法 envelope 的**唯一**去处；由 hook 接线到 store 写通道）。 */
  onMessage: (envelope: PushEnvelope) => void;
  /** 可选审计回调：非法帧原因（非业务通道，不写 store、不抛错）。 */
  onInvalid?: (reason: string, raw: unknown) => void;
  /** 显式 URL（默认 `resolvePushUrl()`）。 */
  url?: string;
  /**
   * 宠物上下文键（**MPF-3**，Phase 3.2-B）：非空时连接地址带 `?pet_id=<key>`；
   * `undefined` / `null` / 空串 ⇒ **不携带** query，与 3.2-B 之前逐字一致。
   * 仅在建连时消费（切宠物由调用方 `close()` + 新实例 `connect()`，见 MPF-4）。
   */
  petId?: string | null;
  /** socket 构造注入（测试替身）；默认使用运行时内建 `WebSocket`。 */
  socketFactory?: (url: string) => SocketLike;
}

/** push channel 公开形状（PC-1：仅 connect / close；另提供只读连接态供测试与守卫断言）。 */
export interface WebSocketClient {
  connect: () => void;
  close: () => void;
  isConnected: () => boolean;
}

/**
 * 解析 WS 连接地址：有 `location` 时按同源推导（`http→ws` / `https→wss`），
 * 否则退回本地兜底 origin。**不做**任何环境变量注入（UB-1：配置收敛，零散拼接禁止）。
 *
 * Phase 3.2-B（**MPF-3**）：`petId` 非空时追加 `?pet_id=<encodeURIComponent(petId)>`，
 * 走 backend Phase 3.2-A 的**连接级** pet 上下文；`undefined` / `null` / 空串 ⇒ 返回
 * **逐字不变**的裸地址（默认宠物，不携带上下文）。
 *
 * 为什么空串也当「不携带」：backend MP-1 对空键直接 `close(1008)`，发出去必然被拒；
 * 折叠为空 query 可避免「注定失败的连接」。
 */
export function resolvePushUrl(petId?: string | null): string {
  const loc = (globalThis as { location?: { protocol?: string; host?: string } }).location;
  const origin =
    loc !== undefined && typeof loc.host === "string" && loc.host.length > 0
      ? `${loc.protocol === "https:" ? "wss:" : "ws:"}//${loc.host}`
      : FALLBACK_WS_ORIGIN;
  return `${origin}${PUSH_PATH}${petQuery(petId)}`;
}

/** pet_id query 片段（未选择 / 空白 ⇒ 空串）。 */
function petQuery(petId?: string | null): string {
  if (petId === undefined || petId === null) {
    return "";
  }
  const key = petId.trim();
  return key.length === 0 ? "" : `?pet_id=${encodeURIComponent(key)}`;
}

/** 运行时内建 socket 构造（浏览器 / Node 22+）；不可用时明确抛错（不静默降级）。 */
function defaultSocketFactory(url: string): SocketLike {
  const ctor = (globalThis as { WebSocket?: new (target: string) => unknown }).WebSocket;
  if (typeof ctor !== "function") {
    throw new Error("WebSocket 运行时不可用（浏览器 / Node ≥22 才内建）");
  }
  return new ctor(url) as SocketLike;
}

/**
 * 入站原始帧 → WM-1 envelope（PC-2 形状校验）。
 * 返回 `null` = **拒收**（调用方丢弃，写 store 一律不发生）。
 */
export function parsePushEnvelope(raw: unknown): PushEnvelope | null {
  if (typeof raw !== "string") {
    return null;
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return null;
  }
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    return null;
  }

  const record = parsed as Record<string, unknown>;
  const keys = Object.keys(record);
  if (keys.length !== PUSH_ENVELOPE_KEYS.length) {
    return null;
  }
  for (const key of PUSH_ENVELOPE_KEYS) {
    if (!keys.includes(key)) {
      return null;
    }
  }

  const eventType = record.event_type;
  if (typeof eventType !== "string" || !PUSH_EVENT_TYPES.includes(eventType)) {
    return null;
  }
  const payload = record.payload;
  if (typeof payload !== "object" || payload === null || Array.isArray(payload)) {
    return null;
  }
  if (typeof record.timestamp !== "string" || typeof record.source !== "string") {
    return null;
  }

  return {
    event_type: eventType,
    payload: payload as Record<string, unknown>,
    timestamp: record.timestamp,
    source: record.source,
  };
}

/**
 * 构造 push channel transport。
 *
 * - `connect()` 幂等：已连接则不动（**不**重连、**不**退避、**不**心跳——PC-6）；
 * - `close()` 关闭并清空句柄；**不监听** `close`/`error` 事件 ⇒ 断线**不触发**任何重连；
 * - 入站仅订阅 `message` 一种事件（守卫可断言）。
 */
export function createWebSocketClient(options: WebSocketClientOptions): WebSocketClient {
  let socket: SocketLike | null = null;

  const handleMessage = (event: { data: unknown }): void => {
    const envelope = parsePushEnvelope(event.data);
    if (envelope === null) {
      // PC-2：非法帧拒收——只走审计回调，绝不到达 store
      options.onInvalid?.("invalid envelope", event.data);
      return;
    }
    options.onMessage(envelope);
  };

  const connect = (): void => {
    if (socket !== null) {
      return; // 幂等：不重连
    }
    const url = options.url ?? resolvePushUrl(options.petId);
    const factory = options.socketFactory ?? defaultSocketFactory;
    const created = factory(url);
    socket = created;
    if (typeof created.addEventListener === "function") {
      created.addEventListener("message", handleMessage);
    } else {
      created.onmessage = handleMessage;
    }
  };

  const close = (): void => {
    if (socket === null) {
      return;
    }
    socket.close();
    socket = null;
  };

  return {
    connect,
    close,
    isConnected: (): boolean => socket !== null,
  };
}
