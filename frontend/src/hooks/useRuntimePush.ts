/**
 * useRuntimePush —— Frontend push channel 的**唯一接线点**（PC-1 / PC-5）。
 *
 * 生命周期：`mount → connect()`；`cleanup → close()`（PC-1 / PC-6：不重连、不心跳、不恢复）。
 * 数据路径（PC-4 / PC-5）：socket message → transport（形状校验）→ `store.applyPushEvent()`
 * → 组件经 store 订阅自动重渲。**必须经 store**：socket 回调**禁止**直写组件状态。
 *
 * **禁止**（PC-1 / PC-3）：调用 API refresh / `loadRuntimeData()`；import `src/api/**`；业务处理。
 * 刷新语义不变：refresh 仍是人工按钮的唯一来源（RF-1/RF-2，PC-3）。
 *
 * **Phase 3.2-B（MPF-3 / MPF-4，受权增量）**：接线点多了一个依赖维度 —— `petId`。
 *
 * - 本步仍是**唯一**接线点（PC-1 归属不变）；
 * - `petId`（`null` = 默认宠物）在**建连时**解析为 `?pet_id=<key>`；
 * - effect 依赖 `petId`：**用户切换宠物** → 旧 effect cleanup `close()` → 新 effect `connect()`。
 *   这是**用户主动**驱动的一次性重建，**不是**自动重连 —— `close`/`error` 事件监听、
 *   退避、重试、心跳、消息重放、多连接并存**一律仍然禁止**（PC-6 / PH-6 原样有效）。
 */

import { useEffect } from "react";

import { createWebSocketClient, type WebSocketClient } from "../services/websocketClient";
import { usePetStore } from "../stores/usePetStore";
import type { PushEnvelope } from "../types/push";

/** store 写通道接线（PC-4）：合法 envelope 的**唯一**落点。 */
function writeEnvelope(envelope: PushEnvelope): void {
  usePetStore.getState().applyPushEvent(envelope);
}

/**
 * 纯 JS 启停编排（零 React 依赖，可在 node 环境完整测试）：
 * 建连并返回 stop 函数（cleanup 调 `close()`）。
 *
 * @param options.client 仅供测试注入既有 client；生产零参（默认创建）。
 * @param options.petId 宠物上下文键（MPF-3）：`null`/省略 = 默认宠物（地址不带 `pet_id`）。
 *   仅用于**默认创建**路径；注入 `client` 时由调用方自行决定其地址。
 */
export function startRuntimePush(options?: {
  client?: WebSocketClient;
  petId?: string | null;
}): () => void {
  const client =
    options?.client ??
    createWebSocketClient({
      onMessage: writeEnvelope,
      petId: options?.petId ?? null,
    });
  client.connect();
  return () => {
    client.close();
  };
}

/**
 * App 级生命周期钩子：挂载建立 push 通道，**宠物变化时**关闭旧连接并建立新上下文连接
 * （MPF-4），卸载关闭。生产调用由 `App` 传入 store 中的当前宠物。
 */
export function useRuntimePush(petId: string | null = null): void {
  useEffect(() => startRuntimePush({ petId }), [petId]);
}
