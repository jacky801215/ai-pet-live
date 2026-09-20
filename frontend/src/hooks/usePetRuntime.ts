/**
 * usePetRuntime —— Phase 1 唯一编排 Hook（FD-1 ~ FD-5，连接 API 层 / store / 组件）。
 *
 * 职责（FD-1）：调用 API 层三个只读函数，把结果**整份**写入 store；
 * 数据流固定 Hook → API Client、Hook → Store、Store ↓ Component。
 * 组件不知道 API 层（FCM-3）；store 不主动请求（FS-1）；API 层不持有状态（FC-2）。
 *
 * 错误（FD-4）：API 抛出的错误实例（含 ApiError 的 status/code/message）**原样**保存进
 * `error` 并暴露——不改写、不降级、**不自动重试**、不静默失败。
 *
 * 本文件**禁止**：生成 UI、DOM 操作、修改组件状态、修改 API 层模块。
 */

import { useCallback, useEffect, useMemo, useSyncExternalStore } from "react";

import { getRecentEvents, simulateEvent } from "../api/events";
import { getPlaybackState } from "../api/playback";
import { getStats } from "../api/stats";
import { usePetStore } from "../stores/usePetStore";

/** 运行时状态（FD-3：loading / error 归 hook 自身，不进 store）。 */
export interface RuntimeStatus {
  /** 初次加载或 refresh 进行中为 true；空闲为 false。创建时即为 true（挂载即拉取）。 */
  loading: boolean;
  /** 最近一次失败的原始错误实例；无错误为 null。 */
  error: Error | null;
}

export interface PetRuntime {
  playback: ReturnType<typeof usePetStore.getState>["playback"];
  recentEvents: ReturnType<typeof usePetStore.getState>["recentEvents"];
  stats: ReturnType<typeof usePetStore.getState>["stats"];
  loading: boolean;
  error: Error | null;
  /** 手动重拉：重新调用三个只读函数并整份写入 store（FD-5）。 */
  refresh: () => Promise<void>;
  /** 事件模拟器编排（ES-2）：提交事件 → 成功回读写 store；失败 error 原样进通道（ES-4）。 */
  triggerEvent: (eventType: string) => Promise<void>;
}

/** 非 Error 的可抛出值兜底（API 层只会抛 Error 子类；此分支仅为类型完备）。 */
function toError(thrown: unknown): Error {
  return thrown instanceof Error ? thrown : new Error(String(thrown));
}

/**
 * 纯数据编排（ES-2）：提交一条模拟事件，成功后回读三端点并整份写入 store。
 * 请求体固定 `{ event_type, payload: {} }`（ES-3：user_id / user_name 省略由后端补默认；
 * 事件合法性由后端裁定，客户端不复刻校验）。独立导出以便零依赖测试。
 */
export async function submitRuntimeEvent(eventType: string): Promise<void> {
  await simulateEvent({ event_type: eventType, payload: {} });
  await loadRuntimeData();
}

/**
 * 纯数据编排：并行拉取三块只读数据并**整份**写入 store。
 * 独立导出以便零依赖测试（不依赖 React 渲染环境）。
 */
export async function loadRuntimeData(): Promise<void> {
  const [snapshot, recent, counters] = await Promise.all([
    getPlaybackState(),
    getRecentEvents(),
    getStats(),
  ]);
  const setters = usePetStore.getState();
  setters.setPlayback(snapshot);
  setters.setRecentEvents(recent.items);
  setters.setStats(counters);
}

/** 可观察 controller 的公开形状（显式接口，避免 ReturnType 循环引用）。 */
export interface PetRuntimeController {
  /** 读取当前运行状态（loading / error）。 */
  getStatus: () => RuntimeStatus;
  /** 订阅状态变化；返回取消订阅函数。 */
  subscribe: (listener: () => void) => () => void;
  /** 手动重拉：重新调用三个只读函数并整份写入 store（FD-5）。 */
  refresh: () => Promise<void>;
  /** 事件模拟器编排（ES-2）：提交事件 → 成功回读写 store；失败 error 原样进通道（ES-4）。 */
  triggerEvent: (eventType: string) => Promise<void>;
}

/**
 * 纯 JS 可观察 controller：持有 loading / error 并对外提供订阅。
 * 独立于 React 存在，使成功 / 失败 / 重拉路径可被完整测试。
 */
export function createPetRuntimeController(): PetRuntimeController {
  let status: RuntimeStatus = { loading: true, error: null };
  const listeners = new Set<() => void>();
  const emit = () => listeners.forEach((notify) => notify());

  const refresh = async (): Promise<void> => {
    status = { loading: true, error: null };
    emit();
    try {
      await loadRuntimeData();
      status = { loading: false, error: null };
    } catch (thrown) {
      status = { loading: false, error: toError(thrown) };
    } finally {
      emit();
    }
  };

  // ES-4：与 refresh 同一 status 通道（复用 loading / error），RuntimeStatus 形状零改动；
  // ES-2：triggerEvent 是「提交 + 回读」编排，不替代、不复用 refresh（RF-1 不变）。
  const triggerEvent = async (eventType: string): Promise<void> => {
    status = { loading: true, error: null };
    emit();
    try {
      await submitRuntimeEvent(eventType);
      status = { loading: false, error: null };
    } catch (thrown) {
      status = { loading: false, error: toError(thrown) };
    } finally {
      emit();
    }
  };

  return {
    getStatus: (): RuntimeStatus => status,
    subscribe: (listener: () => void): (() => void) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    refresh,
    triggerEvent,
  };
}

export interface UsePetRuntimeOptions {
  /**
   * 仅测试注入用（RV 验证）：传入既有 controller 以便静态渲染环境观察同一实例的状态。
   * 生产调用**恒为零参**（App），走默认创建路径，行为不变。
   */
  controller?: PetRuntimeController;
}

/** Phase 1 唯一编排 Hook：挂载时拉取一次（空依赖），并暴露 store 只读投影 + 手动 refresh + 事件触发编排。 */
export function usePetRuntime(options?: UsePetRuntimeOptions): PetRuntime {
  const playback = usePetStore((s) => s.playback);
  const recentEvents = usePetStore((s) => s.recentEvents);
  const stats = usePetStore((s) => s.stats);

  const controller = useMemo(
    () => options?.controller ?? createPetRuntimeController(),
    [options?.controller],
  );
  const status = useSyncExternalStore(
    controller.subscribe,
    controller.getStatus,
    controller.getStatus,
  );

  useEffect(() => {
    void controller.refresh();
  }, [controller]);

  const refresh = useCallback(() => controller.refresh(), [controller]);
  const triggerEvent = useCallback(
    (eventType: string) => controller.triggerEvent(eventType),
    [controller],
  );

  return {
    playback,
    recentEvents,
    stats,
    loading: status.loading,
    error: status.error,
    refresh,
    triggerEvent,
  };
}
