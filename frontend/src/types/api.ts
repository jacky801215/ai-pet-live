/**
 * 后端 API DTO 类型（**唯一**来源：`docs/development/step4_api_contract_decision.md` v1.0 FROZEN）。
 *
 * 边界约束（UB-1 / FC-3）：
 * - 本文件**只**保存 API request / response 类型与错误体形状；
 * - **禁止**出现 UI state、React 组件类型、store 形状（那些归 `stores/` / `components/`）；
 * - 字段名与可空性与后端契约**逐字段一致**，不得增删改名（前端不得「顺手」归一化）。
 */

/** 统一错误体（API-4：所有端点非 2xx 时返回，码恰 3 个，UI 不得依赖细码以外含义）。 */
export interface ApiErrorBody {
  code: string;
  message: string;
}

/** 播放态快照（API-2 冻结 **6 字段**；`POST /api/events/simulate` 与 `GET /api/playback/state` 同构返回）。 */
export interface PlaybackState {
  pet_id: string;
  /** 仅 "idle" | "playing" */
  state: string;
  action: string | null;
  /** 已解析的对外素材 URL；无动作时为 null（UB-4：前端只消费，不拼接） */
  asset_url: string | null;
  queue_size: number;
  last_event: string | null;
}

/**
 * 事件模拟请求（API-1；允许键仅 4 个，未知顶层字段被后端拒 —— DA-7）。
 *
 * - `user_id` 省略补 null；`user_name` 省略补 ""、显式 null 保留；
 * - `payload` 省略补 `{}`；**显式 `null` 会被后端 400 拒绝**（类型上不收 null）。
 */
export interface SimulateEventRequest {
  event_type: string;
  user_id?: string | null;
  user_name?: string | null;
  payload?: Record<string, unknown>;
}

/** 事件明细项（API-3 冻结 **9 字段**；`payload` 库内为 JSON 字符串，响应中已是对象）。 */
export interface EventItem {
  id: number;
  event_type: string;
  user_id: string | null;
  user_name: string | null;
  pet_id: string | null;
  action_name: string | null;
  platform: string | null;
  payload: Record<string, unknown>;
  created_at: string | null;
}

/** 最近事件列表（`count` = `items` 实际条数，可能小于请求的 `limit`）。 */
export interface RecentEventsResponse {
  items: EventItem[];
  count: number;
}

/** 互动统计（`events`/`actions` 对应 stat_type ∈ {event, action}；`total` = 事件计数之和）。 */
export interface StatsResponse {
  events: Record<string, number>;
  actions: Record<string, number>;
  total: number;
}
