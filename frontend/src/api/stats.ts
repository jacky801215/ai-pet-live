/**
 * Stats API（FC-4）：`GET /api/stats`。
 *
 * 边界（UB-1 / FC-4）：薄封装，无 React / store / 统计口径判断（口径归后端 D6）。
 */

import type { StatsResponse } from "../types/api";
import { request } from "./client";

/** 读取互动统计（`events` / `actions` 两维度 + `total`，API-3）。 */
export function getStats(): Promise<StatsResponse> {
  return request<StatsResponse>("/api/stats");
}
