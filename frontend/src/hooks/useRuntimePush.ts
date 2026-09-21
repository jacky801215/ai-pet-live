/**
 * useRuntimePush —— Frontend push channel 的**唯一接线点**（PC-1 / PC-5）。
 *
 * 生命周期：`mount → connect()`；`cleanup → close()`（PC-1 / PC-6：不重连、不心跳、不恢复）。
 * 数据路径（PC-4 / PC-5）：socket message → transport（形状校验）→ `store.applyPushEvent()`
 * → 组件经 store 订阅自动重渲。**必须经 store**：socket 回调**禁止**直写组件状态。
 *
 * **禁止**（PC-1 / PC-3）：调用 API refresh / `loadRuntimeData()`；import `src/api/**`；业务处理。
 * 刷新语义不变：refresh 仍是人工按钮的唯一来源（RF-1/RF-2，PC-3）。
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
 * `options.client` 仅供测试注入既有 client；生产零参（默认创建）。
 */
export function startRuntimePush(options?: { client?: WebSocketClient }): () => void {
  const client =
    options?.client ??
    createWebSocketClient({
      onMessage: writeEnvelope,
    });
  client.connect();
  return () => {
    client.close();
  };
}

/** App 级生命周期钩子：挂载建立 push 通道，卸载关闭（生产零参）。 */
export function useRuntimePush(): void {
  useEffect(() => startRuntimePush(), []);
}
