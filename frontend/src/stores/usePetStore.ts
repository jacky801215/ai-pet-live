/**
 * PetStore —— 全前端**唯一**状态容器（FS-1 / FS-3，UB-2 落地）。
 *
 * 边界（FS-1 / FS-4 / FS-5）：
 * - 只负责「持有 server snapshot + 提供 setter」；**禁止** HTTP 请求、URL 拼接
 *   （数据获取一律经 API 层模块，由调用方把结果喂给 setter）、**禁止**动画计时器、
 *   **禁止**派生业务状态、**禁止**浏览器本地持久化；
 * - 本文件**不** import React、**不**依赖 API 层各模块（FS-4：Component → Store ← API Client 单向供给）；
 * - Phase 1 单一 store：不拆分、不新建第二 store（含 slice 组合）。
 */

import { create } from "zustand";

import type { EventItem, PlaybackState, StatsResponse } from "../types/api";

/** PetStore 形状（FS-3：Phase 1 最小集，禁止业务 action）。 */
export interface PetStoreState {
  /** 最新播放态快照；尚未受理任何数据时为 null（初始空状态）。 */
  playback: PlaybackState | null;
  /** 最近事件明细（服务端已按 `created_at DESC` 排序，store 不再排序/裁剪）。 */
  recentEvents: EventItem[];
  /** 互动统计；尚未拉取时为 null。 */
  stats: StatsResponse | null;

  /** 写入最新播放态快照（整份替换，不合并不归一化）。 */
  setPlayback: (snapshot: PlaybackState) => void;
  /** 写入最近事件列表（整份替换，`count` = 数组长度，不单独保存信封）。 */
  setRecentEvents: (events: EventItem[]) => void;
  /** 写入互动统计（整份替换）。 */
  setStats: (stats: StatsResponse) => void;
}

export const usePetStore = create<PetStoreState>()((set) => ({
  playback: null,
  recentEvents: [],
  stats: null,

  setPlayback: (snapshot) => set({ playback: snapshot }),
  setRecentEvents: (events) => set({ recentEvents: events }),
  setStats: (stats) => set({ stats: stats }),
}));
