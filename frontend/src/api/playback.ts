/**
 * Playback API（FC-4）：`GET /api/playback/state`。
 *
 * 边界（UB-1 / FC-4）：薄封装，无 React / store / 播放计时器（轮询节奏归 store，UB-2）。
 */

import type { PlaybackState } from "../types/api";
import { request } from "./client";

/** 读取当前播放态快照（API-2；Phase 1 由 UI 轮询驱动状态机推进）。 */
export function getPlaybackState(): Promise<PlaybackState> {
  return request<PlaybackState>("/api/playback/state");
}
