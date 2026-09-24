/**
 * PetStore —— 全前端**唯一**状态容器（FS-1 / FS-3，UB-2 落地）。
 *
 * 边界（FS-1 / FS-4 / FS-5）：
 * - 只负责「持有 server snapshot + 提供 setter」；**禁止** HTTP 请求、URL 拼接
 *   （数据获取一律经 API 层模块，由调用方把结果喂给 setter）、**禁止**动画计时器、
 *   **禁止**派生业务状态、**禁止**浏览器本地持久化；
 * - 本文件**不** import React、**不**依赖 API 层各模块（FS-4：Component → Store ← API Client 单向供给）；
 * - Phase 1 单一 store：不拆分、不新建第二 store（含 slice 组合）。
 *
 * **Phase 3.2-B 受权增量（MPF-2）**：切片数 3 → 4，新增 `petContext` 与第 5 个写出口
 * `setSelectedPet`。`playback` / `recentEvents` / `stats` 三块服务器快照的 schema 与
 * push 写入语义**零变化**；仍为**唯一** store（不新建平行 store、不引第二状态库）。
 */

import { create } from "zustand";

import { DEFAULT_SELECTED_PET_ID } from "../config/pets";
import type { EventItem, PlaybackState, StatsResponse } from "../types/api";
import type { PushEnvelope } from "../types/push";

/**
 * Pet context 切片（**MPF-2 受权增量**，Phase 3.2-B）。
 *
 * `selectedPetId === null` = **默认宠物**（WS 不携带 `pet_id`，行为与 3.2-B 之前逐字一致）。
 */
export interface PetContextState {
  /** 当前选择的宠物上下文键；`null` = 默认宠物（不携带 `pet_id`）。 */
  selectedPetId: string | null;
}

/** PetStore 形状（FS-3：Phase 1 最小集，禁止业务 action）。 */
export interface PetStoreState {
  /** 最新播放态快照；尚未受理任何数据时为 null（初始空状态）。 */
  playback: PlaybackState | null;
  /** 最近事件明细（服务端已按 `created_at DESC` 排序，store 不再排序/裁剪）。 */
  recentEvents: EventItem[];
  /** 互动统计；尚未拉取时为 null。 */
  stats: StatsResponse | null;
  /** 宠物上下文（MPF-2 受权增量）：当前选择的宠物。与三块服务器快照**互相独立**。 */
  petContext: PetContextState;

  /** 写入最新播放态快照（整份替换，不合并不归一化）。 */
  setPlayback: (snapshot: PlaybackState) => void;
  /** 写入最近事件列表（整份替换，`count` = 数组长度，不单独保存信封）。 */
  setRecentEvents: (events: EventItem[]) => void;
  /** 写入互动统计（整份替换）。 */
  setStats: (stats: StatsResponse) => void;
  /**
   * 写入当前宠物（MPF-2 第 5 个写出口）：`null` = 默认宠物。
   *
   * 语义与三个 `set*` 同级（整份替换），**不**派生业务状态、**不**校验键合法性
   * （合法性由 `src/config/pets.ts` 的目录保证；backend 侧由 `known_pet_keys()` 兜底）。
   */
  setSelectedPet: (petId: string | null) => void;

  /**
   * push 通道唯一写出口（PC-4；Phase 2.2-6 受权增量 = 第 4 个写出口）：
   * 接收 WM-1 envelope 并**只写既有切片**——schema 零变化（不新增切片 / 字段 / 第二 store）。
   *
   * 写入语义（纯函数式，无隐藏状态）：
   * 1. `recentEvents` 头部并入一条 envelope 派生明细项（`EventItem` 9 字段形状）：
   *    `created_at` = `envelope.timestamp`、`platform` = `envelope.source`、`payload` 原样；
   *    `id` = 本地负值占位（按既有负值 id 条数推导 ⇒ 唯一且无需额外状态字段）；
   *    身份/动作字段为 `null`（push 帧不含库内派生信息，**不臆造**）；
   * 2. `playback !== null` 时同步 `last_event`（其余 6 字段原样保留；**7 字段（CR-1）冻结不变**）。
   */
  applyPushEvent: (envelope: PushEnvelope) => void;
}

export const usePetStore = create<PetStoreState>()((set) => ({
  playback: null,
  recentEvents: [],
  stats: null,
  // MPF-2：初始 = 默认宠物（不携带 pet_id ⇒ WS 连接 URL 与 3.2-B 之前逐字一致）
  petContext: { selectedPetId: DEFAULT_SELECTED_PET_ID },

  setPlayback: (snapshot) => set({ playback: snapshot }),
  setRecentEvents: (events) => set({ recentEvents: events }),
  setStats: (stats) => set({ stats: stats }),

  // MPF-2：第 5 个写出口（整份替换；只写 petContext 切片，不触三块服务器快照）
  setSelectedPet: (petId) => set({ petContext: { selectedPetId: petId } }),

  // PC-4：push 写通道（只写既有切片；id 由既有负值条数推导，保证唯一且无额外状态）
  applyPushEvent: (envelope) =>
    set((state) => {
      const localCount = state.recentEvents.filter((event) => event.id < 0).length;
      const item: EventItem = {
        id: -1 - localCount,
        event_type: envelope.event_type,
        user_id: null,
        user_name: null,
        pet_id: null,
        action_name: null,
        platform: envelope.source,
        payload: envelope.payload,
        created_at: envelope.timestamp,
      };
      return {
        recentEvents: [item, ...state.recentEvents],
        playback:
          state.playback === null
            ? state.playback
            : { ...state.playback, last_event: envelope.event_type },
      };
    }),
}));
