/**
 * Events API（FC-4）：触发一条模拟事件（经 push 通道）+ `GET /api/events/recent`。
 *
 * 边界（UB-1 / FC-4）：本模块只做「传输 + DTO」的薄封装；
 * **禁止** React / store / localStorage / 业务判断（事件合法性由后端裁定）。
 *
 * **CR-6 / F4 = α（受权增量）**：`simulateEvent` 由 `POST /api/events/simulate` 改为经
 * **既有 push 通道**发送 **WM-1 envelope**（与入站帧**同格式**：恰 4 字段；后端
 * `websocket_adapter` 已支持）——使「驱动」与「观察」同源，**任意宠物**下均成立。
 * ⇒ 播放态**不再**由 HTTP 应答回传，而由服务端**状态帧**经 push 送达（前端写 `playback`）。
 */

import type { RecentEventsResponse, SimulateEventRequest } from "../types/api";
import { buildPushEnvelope, sendActiveEnvelope } from "../services/websocketClient";
import { request } from "./client";

/**
 * 触发一条模拟事件（**CR-6 / F4 = α**）：经**活动推送通道**发送 WM-1 envelope。
 *
 * 传输元数据口径（WM-1）：`timestamp` 由传输层生成、`source` 取 `PUSH_ENVELOPE_SOURCE`
 * —— 后端 `websocket_adapter` 按 WM-1 把二者作为**传输元数据丢弃**，故此处不承载业务含义；
 * `user_id` / `user_name` **不在** WM-1 承载（后端补默认），故不透传。
 *
 * @returns 已发出即 resolve（**无** HTTP 应答载荷：新播放态由状态帧推送）；
 *          **当前无活动推送通道**时 reject —— 不静默失败（错误原样进调用方 error 通道）。
 */
export function simulateEvent(body: SimulateEventRequest): Promise<void> {
  const envelope = buildPushEnvelope(body.event_type, body.payload ?? {});
  if (!sendActiveEnvelope(envelope)) {
    return Promise.reject(
      new Error("push channel unavailable: 事件触发需已建立的推送连接"),
    );
  }
  return Promise.resolve();
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
