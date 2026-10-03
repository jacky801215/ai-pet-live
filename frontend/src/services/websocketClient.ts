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
 * **状态帧分支（PC-2 v1.1，CR-6 受权增量）**：入站帧**先判帧型** ——
 * 顶层 `type === "playback_state"` ⇒ **状态帧**（校验 `snapshot` 为对象且字段集恰 API-2 七字段）
 * → 合法**转交** `onSnapshot`，非法**拒收**（不写 store、**不回退**为 envelope 解析）；
 * **否则** ⇒ 走**既有** WM-1 envelope 路径（逐字不变）。本文件**仍**只是 transport：
 * 不判定动作语义、不派生状态、不本地推断（`server pushed ≠ client inferred`）。
 *
 * 可测试性：socket 构造经 `socketFactory` 注入（零依赖、node 环境可测，无需 jsdom）。
 *
 * **Phase 3.2-B（MPF-3 / MPF-4，受权增量）**：建连地址可携带 backend Phase 3.2-A 的
 * **连接级** pet 上下文（`?pet_id=<key>`）。本文件**仍**只是 transport——
 * 不感知 pet 业务、不监听 `close`/`error`、**不自动重连**；「切换宠物」由调用方
 * `close()` 旧实例 + 以新 `petId` 新建实例实现（PC-6 的 reconnect 禁令**原样有效**）。
 *
 * **CR-6 / F4 = α（受权增量）—— 出站方向**：本文件新增 `send()` 与**活动通道句柄**
 * （`setActivePushChannel` / `releaseActivePushChannel` / `sendActiveEnvelope`），
 * 使「**触发**」与「**观察**」走**同一条**连接（`?pet_id=` 下即同一个 per-connection 实例）。
 * ⛔ **不新建第二连接**（WP-4「单活动连接」与 PC-1「唯一接线点」原样有效）；
 * 本文件**仍**只是 transport：句柄只登记调用方（`useRuntimePush`）传入的实例，
 * 不感知 pet 业务、不做业务判定、不接入任何事件语义。
 */

import type { PushEnvelope, PushStateSnapshot } from "../types/push";
import {
  PLAYBACK_STATE_KEYS,
  PUSH_ENVELOPE_KEYS,
  PUSH_EVENT_TYPES,
  STATE_FRAME_TYPE,
} from "../types/push";

/** WS 端点路径（与 backend `api/ws.py` 的 `/api/ws` 一致；PC-2：地址属配置，不属业务）。 */
export const PUSH_PATH = "/api/ws";

/** 无 `location` 时的兜底 origin（node/测试环境；生产浏览器恒走 `location`）。 */
export const FALLBACK_WS_ORIGIN = "ws://127.0.0.1:8000";

/**
 * 出站 envelope 的 `source` 固定取值（CR-6 / F4 = α）。
 *
 * 与后端 `websocket_dispatcher.PUSH_SOURCE`（`"ws"`）同口径；后端 `websocket_adapter`
 * 按 **WM-1** 把 `timestamp` / `source` 作为**传输元数据丢弃**，故此处取值只作形状占位。
 */
export const PUSH_ENVELOPE_SOURCE = "ws";

/** socket 最小形状（`WebSocket` 子集；测试用替身只需满足此接口）。 */
export interface SocketLike {
  close: () => void;
  /** 出站（CR-6 / F4 = α 受权增量）：仅需文本帧；缺省视为「不可发送」。 */
  send?: (data: string) => void;
  addEventListener?: (type: string, listener: (event: { data: unknown }) => void) => void;
  onmessage?: ((event: { data: unknown }) => void) | null;
}

export interface WebSocketClientOptions {
  /** push handler（PC-2：合法 envelope 的**唯一**去处；由 hook 接线到 store 写通道）。 */
  onMessage: (envelope: PushEnvelope) => void;
  /**
   * 状态帧 handler（PC-2 v1.1：合法**状态帧**的**唯一**去处；由 hook 接线到 store 的
   * `applyPlaybackSnapshot` 写通道）。省略时状态帧**只被校验、不落 store**。
   */
  onSnapshot?: (snapshot: PushStateSnapshot) => void;
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

/** push channel 公开形状（PC-1：仅 connect / close / send；另提供只读连接态供测试与守卫断言）。 */
export interface WebSocketClient {
  connect: () => void;
  close: () => void;
  isConnected: () => boolean;
  /**
   * 经本连接发送一条 **WM-1 envelope**（CR-6 / F4 = α 受权增量）：序列化后交 socket。
   *
   * @returns `true` = 已发出；`false` = 未连接 / socket 不支持发送（调用方决定错误口径）。
   */
  send: (envelope: PushEnvelope) => boolean;
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

/** 原始帧 → JSON 对象（非字符串 / 非法 JSON / 非对象 / 数组 ⇒ `null`）。 */
function parseJsonObject(raw: unknown): Record<string, unknown> | null {
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
  return parsed as Record<string, unknown>;
}

/** 键集**恰**等于 `expected`（长度相同且逐项命中，顺序无关）。 */
function hasExactKeys(record: Record<string, unknown>, expected: readonly string[]): boolean {
  const keys = Object.keys(record);
  if (keys.length !== expected.length) {
    return false;
  }
  return expected.every((key) => keys.includes(key));
}

/**
 * 帧型判别（PC-2 v1.1 分流边界）：顶层 `type === "playback_state"` ⇒ 状态帧。
 * 两类帧**互斥** —— 判定为状态帧后**不得**回退为 envelope 解析（反之亦然）。
 */
function isStateFrame(record: Record<string, unknown>): boolean {
  return record.type === STATE_FRAME_TYPE;
}

/** 已解析对象 → WM-1 envelope（PC-2 形状校验）；`null` = 拒收。 */
function readEnvelope(record: Record<string, unknown>): PushEnvelope | null {
  if (!hasExactKeys(record, PUSH_ENVELOPE_KEYS)) {
    return null;
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
 * 已解析对象 → 状态帧载荷（PC-2 v1.1 形状校验）；`null` = 拒收。
 * `snapshot` 缺失 / 非对象 / 字段集**不等于** API-2 的 7 字段 ⇒ 拒收。
 */
function readSnapshot(record: Record<string, unknown>): PushStateSnapshot | null {
  const snapshot = record.snapshot;
  if (typeof snapshot !== "object" || snapshot === null || Array.isArray(snapshot)) {
    return null;
  }
  const fields = snapshot as Record<string, unknown>;
  return hasExactKeys(fields, PLAYBACK_STATE_KEYS)
    ? (fields as unknown as PushStateSnapshot)
    : null;
}

/**
 * 入站原始帧 → WM-1 envelope（PC-2 形状校验）。
 * 返回 `null` = **拒收**（调用方丢弃，写 store 一律不发生）。
 */
export function parsePushEnvelope(raw: unknown): PushEnvelope | null {
  const record = parseJsonObject(raw);
  return record === null ? null : readEnvelope(record);
}

/**
 * 入站原始帧 → 状态帧载荷（PC-2 v1.1 形状校验）。
 * 非状态帧（顶层无 `type` 或取值不符）/ 形状非法 ⇒ `null`（由调用方按帧型分流处理）。
 */
export function parseStateSnapshot(raw: unknown): PushStateSnapshot | null {
  const record = parseJsonObject(raw);
  if (record === null || !isStateFrame(record)) {
    return null;
  }
  return readSnapshot(record);
}

/**
 * 组装**出站** WM-1 envelope（**恰 4 字段**）—— 与入站帧**同格式**
 * （后端 `websocket_adapter` 已支持，`api/ws.py` 走既有 `adapter.handle`）。
 *
 * - `event_type` / `payload`：调用方给出，不校验业务合法性（裁定权在后端）；
 * - `timestamp`：传输侧生成，`YYYY-MM-DDTHH:MM:SSZ`（与后端 dispatcher 同格式）；
 * - `source`：固定 :data:`PUSH_ENVELOPE_SOURCE`。
 *
 * @param now 时钟注入（测试固定时序）；默认当前时刻。
 */
export function buildPushEnvelope(
  eventType: string,
  payload: Record<string, unknown>,
  now: () => Date = () => new Date(),
): PushEnvelope {
  return {
    event_type: eventType,
    payload,
    timestamp: now().toISOString().replace(/\.\d{3}Z$/, "Z"),
    source: PUSH_ENVELOPE_SOURCE,
  };
}

/**
 * **活动推送通道**（CR-6 / F4 = α）—— 由接线点（`useRuntimePush`）在 connect 时登记、
 * cleanup 时注销；供**触发侧**（`api/events`）经**既有**那一条连接发送。
 *
 * ⛔ 本句柄**不**创建连接、**不**保存业务状态、**不**做事件语义；它只回答
 * 「现在该往哪条连接发」——故 WP-4「单活动连接」与 PC-1「唯一接线点」原样有效。
 */
let activePushChannel: WebSocketClient | null = null;

/** 登记活动通道（仅接线点调用）。 */
export function setActivePushChannel(client: WebSocketClient | null): void {
  activePushChannel = client;
}

/**
 * 注销活动通道 —— **仅当**当前登记的就是该实例时才清空。
 *
 * 这条身份判定用于「切换宠物」时**新旧连接交替**的窗口：旧实例的 cleanup
 * 不得把新实例的登记一并抹掉。
 */
export function releaseActivePushChannel(client: WebSocketClient): void {
  if (activePushChannel === client) {
    activePushChannel = null;
  }
}

/** 读取当前活动通道（无连接 / 未接线时为 `null`）。 */
export function getActivePushChannel(): WebSocketClient | null {
  return activePushChannel;
}

/**
 * 经**活动通道**发送一条 envelope。
 *
 * @returns `true` = 已发出；`false` = 当前无活动通道或通道未连接（**错误口径由调用方决定**）。
 */
export function sendActiveEnvelope(envelope: PushEnvelope): boolean {
  return activePushChannel !== null && activePushChannel.send(envelope);
}

/**
 * 构造 push channel transport。
 *
 * - `connect()` 幂等：已连接则不动（**不**重连、**不**退避、**不**心跳——PC-6）；
 * - `close()` 关闭并清空句柄；**不监听** `close`/`error` 事件 ⇒ 断线**不触发**任何重连；
 * - 入站仅订阅 `message` 一种事件（守卫可断言）；
 * - `send()` 只做「序列化 + 交 socket」，**不**排队、**不**缓冲、**不**重发（PC-6）。
 */
export function createWebSocketClient(options: WebSocketClientOptions): WebSocketClient {
  let socket: SocketLike | null = null;

  const handleMessage = (event: { data: unknown }): void => {
    const record = parseJsonObject(event.data);
    if (record === null) {
      // PC-2：非法帧拒收——只走审计回调，绝不到达 store
      options.onInvalid?.("invalid envelope", event.data);
      return;
    }
    if (isStateFrame(record)) {
      // PC-2 v1.1：状态帧分支（与 envelope 互斥，不回退解析）
      const snapshot = readSnapshot(record);
      if (snapshot === null) {
        options.onInvalid?.("invalid state frame", event.data);
        return;
      }
      options.onSnapshot?.(snapshot);
      return;
    }
    const envelope = readEnvelope(record);
    if (envelope === null) {
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

  const send = (envelope: PushEnvelope): boolean => {
    if (socket === null || typeof socket.send !== "function") {
      return false;
    }
    socket.send(JSON.stringify(envelope));
    return true;
  };

  return {
    connect,
    close,
    isConnected: (): boolean => socket !== null,
    send,
  };
}
