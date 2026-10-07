/**
 * Push 契约类型 —— WM-1 envelope（**唯一来源**：`docs/development/phase2_websocket_event_model_decision.md`）
 * 与 **状态帧**（**唯一来源**：`docs/development/phase2_frontend_push_channel_decision.md` PC-2 v1.1 +
 * `phase2_websocket_push_boundary_decision.md` WP-3 v1.1）。
 *
 * 边界（PC-2）：
 * - envelope **恰 4 字段**（`event_type` / `payload` / `timestamp` / `source`）：不增加、不改名、不裁剪；
 * - 状态帧为**第二类入站帧**（CR-6），**不改动** envelope 的任何形态与校验口径；
 * - **音效帧**为**第三类入站帧**（**CR-11**，`playback_audio`），同样不改动 envelope 与状态帧；
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

/**
 * **音效帧**的类型判别值（**CR-11**）：入站帧**顶层** `type` 取此值 ⇒ 音效帧分支。
 *
 * 三类帧**两两互斥**（`playback_state` / `playback_audio` / WM-1 envelope）；
 * 判定为某一类后**不得**回退解析为其它类。
 * 契约来源：`docs/change_request/cr-11_audio_feedback_design.md` §4.3。
 */
export const AUDIO_FRAME_TYPE = "playback_audio";

/**
 * 音效帧的**冻结键集（含判别键 `type`）** —— 恰 5 个。
 *
 * 客户端**只**做形状（键集）校验，**不**拼接路径、**不**判断素材类型（RB-2）。
 */
export const PLAYBACK_AUDIO_KEYS: readonly string[] = [
  "type",
  "pet_id",
  "action",
  "audio_url",
  "seq",
];

/**
 * 音效帧载荷（**CR-11**）—— 去掉判别键后的 4 字段。
 *
 * - `pet_id`：对外主键（与状态帧同口径，如 `cat_001`）；
 * - `action`：动作名（供前端做生命周期对齐）；
 * - `audio_url`：**由后端产出**的音频 URL（前端永不拼接 —— RB-2 / UI-6）；
 * - `seq`：**每次触发单调递增**的序号 —— 前端**唯一**的「新触发」判据
 *   （同 `action` 连触两次时其余字段完全相同，缺 `seq` 必然漏播第二次）。
 */
export interface PlaybackAudioFrame {
  pet_id: string;
  action: string;
  audio_url: string;
  seq: number;
}

