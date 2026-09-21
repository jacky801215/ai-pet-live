/**
 * Push 契约类型 —— WM-1 envelope（**唯一来源**：`docs/development/phase2_websocket_event_model_decision.md`）。
 *
 * 边界（PC-2）：
 * - envelope **恰 4 字段**（`event_type` / `payload` / `timestamp` / `source`）：不增加、不改名、不裁剪；
 * - 本文件**只**保存 push 通道的传输契约类型；**禁止**出现 UI state、store 形状、组件类型。
 */

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
