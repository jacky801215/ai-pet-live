/**
 * Push 契约类型 —— WM-1 envelope（**唯一来源**：`docs/development/phase2_websocket_event_model_decision.md`）
 * 与 **状态帧**（**唯一来源**：`docs/development/phase2_frontend_push_channel_decision.md` PC-2 v1.1 +
 * `phase2_websocket_push_boundary_decision.md` WP-3 v1.1）。
 *
 * 边界（PC-2）：
 * - envelope **恰 4 字段**（`event_type` / `payload` / `timestamp` / `source`）：不增加、不改名、不裁剪；
 * - 状态帧为**第二类入站帧**（CR-6），**不改动** envelope 的任何形态与校验口径；
 * - 本文件**只**保存 push 通道的传输契约类型；**禁止**出现 UI state、store 形状、组件类型。
 */

import type { PlaybackState } from "./api";

/** WM-1 envelope 的四字段冻结集合（客户端形状校验的白名单键）。 */
export const PUSH_ENVELOPE_KEYS: readonly string[] = [
  "event_type",
  "payload",
  "timestamp",
  "source",
];

/** 事件契约 v1.1 事件类型白名单（与 backend adapter 同表，前端**只**做形状校验不做业务判定）。 */
export const PUSH_EVENT_TYPES: readonly string[] = ["comment", "gift", "like", "system"];

/** WebSocket 推送 envelope（WM-1；与 HTTP 侧同一事件契约，WS-2）。 */
export interface PushEnvelope {
  event_type: string;
  payload: Record<string, unknown>;
  timestamp: string;
  source: string;
}

/**
 * 状态帧的类型判别值（PC-2 v1.1 分流边界）：入站帧**顶层** `type` 取此值 ⇒ 状态帧分支，
 * **否则**走既有 WM-1 envelope 路径；两类帧**互斥**，不得互相回退解析。
 */
export const STATE_FRAME_TYPE = "playback_state";

/**
 * `snapshot` 的冻结字段集 = **API-2 的 `PlaybackState` 7 字段**（CR-1 起冻结；与 `./api` 同一契约）。
 * 客户端**只**做形状（键集）校验，不做字段值归一化 / 业务判定。
 */
export const PLAYBACK_STATE_KEYS: readonly string[] = [
  "pet_id",
  "state",
  "action",
  "asset_url",
  "queue_size",
  "last_event",
  "loop",
];

/**
 * 状态帧载荷类型 = API-2 的 `PlaybackState`（**原样复用**：不新增字段、不改名、不裁剪）。
 * 类型别名而非重定义，保证与 DTO 单一事实源（`src/types/api.ts`）不漂移。
 */
export type PushStateSnapshot = PlaybackState;

