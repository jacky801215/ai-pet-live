/**
 * Events API（FC-4）：`POST /api/events/simulate` 与 `GET /api/events/recent`。
 *
 * 边界（UB-1 / FC-4）：本模块只做「路径 + 方法 + DTO」的薄封装；
 * **禁止** React / store / localStorage / 业务判断（事件合法性由后端裁定）。
 */

import type { PlaybackState, RecentEventsResponse, SimulateEventRequest } from "../types/api";
import { request } from "./client";

/** 模拟一条原始事件，返回最新播放态快照（API-1）。 */
export function simulateEvent(body: SimulateEventRequest): Promise<PlaybackState> {
  return request<PlaybackState>("/api/events/simulate", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/**
 * 查询最近事件明细（API-3）。
 *
 * @param limit - 可选；省略时用后端默认（20）。边界 1..200 由**后端**裁定，
 *                  越界返回 400（客户端不复刻校验，避免两份规则漂移）。
 */
export function getRecentEvents(limit?: number): Promise<RecentEventsResponse> {
  const query = limit === undefined ? "" : `?limit=${limit}`;
  return request<RecentEventsResponse>(`/api/events/recent${query}`);
}
