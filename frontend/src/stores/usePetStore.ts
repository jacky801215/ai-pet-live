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
 *
 * **CR-6 受权增量（PC-4 / FS-3 v1.1）**：新增第 6 个写出口 `applyPlaybackSnapshot`
 * （状态帧 ⇒ 整份替换 `playback`）。切片数、三块快照 schema、以及 `applyPushEvent` 的
 * 写入语义**零变化**；仍为**唯一** store。
 *
 * **CR-11 受权增量（PC-4）**：新增第 7 个写出口 `applyPlaybackAudio` 与切片 `lastAudio`
 * （音效帧 ⇒ 整份替换 `lastAudio`）。`playback` / `recentEvents` / `stats` / `petContext`
 * 的 schema 与写入语义**零变化**；仍为**唯一** store（不新建平行 store / 第二状态库）。
 */

import { create } from "zustand";

import { DEFAULT_SELECTED_PET_ID } from "../config/pets";
import type { EventItem, PlaybackState, StatsResponse } from "../types/api";
import type { PlaybackAudioFrame, PushEnvelope } from "../types/push";

/**
 * Pet context 切片（**MPF-2 受权增量**，Phase 3.2-B）。
 *
 * `selectedPetId === null` = **默认宠物**（WS 不携带 `pet_id`，行为与 3.2-B 之前逐字一致）。
 */
export interface PetContextState {
  /** 当前选择的宠物上下文键；`null` = 默认宠物（不携带 `pet_id`）。 */
  selectedPetId: string | null;
}

/**
 * 音效切片（**CR-11 受权增量**）—— 与 :type:`PlaybackAudioFrame` 同构
 * （`pet_id` / `action` / `audio_url` / `seq`）。
 *
 * ⛔ `seq` **必需**：它是「同动作连触两次」的唯一区分依据 ——
 * 若无单调序号，订阅层无法判定「这是一次新触发」，第二次音效必然丢失。
 */
export type PlaybackAudioState = PlaybackAudioFrame;

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
  /** 最近一帧音效（**CR-11** 受权增量）；尚未收到任何音效帧时为 null。 */
  lastAudio: PlaybackAudioState | null;

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

  /**
   * 状态帧唯一写出口（PC-4 / FS-3，**CR-6 受权增量 = 第 6 个写出口**）：
   * 接收服务端推送的状态快照并**整份替换** `playback`（与 `setPlayback` 同语义、**来源不同**：
   * 服务端推送）。
   *
   * 写入语义（纯函数式，无隐藏状态）：
   * 1. **只写** `playback` 切片 —— **不触** `recentEvents` / `stats` / `petContext`；
   * 2. **天然幂等**：同一快照重复写入无额外副作用（不做合并 / 去重 / 归一化 / 排序）；
   * 3. **不派生**业务状态、**不校验**字段值（形状校验归 push transport；本写出口只做整份替换）；
   * 4. **禁止**由事件 `payload` 反推 / 合成 `playback`（`event frame ≠ playback state`）。
   */
  applyPlaybackSnapshot: (snapshot: PlaybackState) => void;

  /**
   * 音效帧唯一写出口（**CR-11 受权增量 = 第 7 个写出口**）：
   * 接收服务端推送的音效帧并**整份替换** `lastAudio`。
   *
   * 写入语义（纯函数式，无隐藏状态）：
   * 1. **只写** `lastAudio` 切片 —— **不触** `playback` / `recentEvents` / `stats` /
   *    `petContext`（音效与视觉状态**互不代偿**）；
   * 2. 整份替换 ⇒ **天然幂等**；**不做**去重（去重归播放模块，判据是 `seq`）；
   * 3. **不派生**业务状态、**不**拼接/改写 `audio_url`（URL 一律由后端产出 —— RB-2）；
   * 4. **禁止**在此触发播放 —— 播放归 `usePlaybackAudio` + `services/playbackAudio`。
   */
  applyPlaybackAudio: (frame: PlaybackAudioState) => void;
}

export const usePetStore = create<PetStoreState>()((set) => ({
  playback: null,
  recentEvents: [],
  stats: null,
  // MPF-2：初始 = 默认宠物（不携带 pet_id ⇒ WS 连接 URL 与 3.2-B 之前逐字一致）
  petContext: { selectedPetId: DEFAULT_SELECTED_PET_ID },
  // CR-11：初始无音效帧（收到第一帧前不播放任何音效）
  lastAudio: null,

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

  // PC-4 / FS-3（CR-6 受权增量）：状态帧写通道 —— 整份替换 playback，
  // 不触 recentEvents / stats / petContext；替换语义天然幂等、零派生。
  applyPlaybackSnapshot: (snapshot) => set({ playback: snapshot }),

  // PC-4（CR-11 受权增量）：音效帧写通道 —— 整份替换 lastAudio，不触其它切片；
  // 不在此触发播放（播放归 usePlaybackAudio / services/playbackAudio）。
  applyPlaybackAudio: (frame) => set({ lastAudio: frame }),
}));
