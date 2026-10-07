/**
 * useRuntimePush —— Frontend push channel 的**唯一接线点**（PC-1 / PC-5）。
 *
 * 生命周期：`mount → connect()`；`cleanup → close()`（PC-1 / PC-6：不重连、不心跳、不恢复）。
 * 数据路径（PC-4 / PC-5）：socket message → transport（形状校验）→ `store.applyPushEvent()`
 * → 组件经 store 订阅自动重渲。**必须经 store**：socket 回调**禁止**直写组件状态。
 *
 * **状态帧路径（PC-2 v1.1 / PC-4 v1.1，CR-6 受权增量）**：状态帧 → transport（形状校验）→
 * `store.applyPlaybackSnapshot()`（整份替换 `playback`）→ 组件经 store 订阅自动重渲。
 * 两条 push 写通道属**同一**「唯一写出口集合」，**互不代偿**（事件帧只走前者、状态帧只走后者）。
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
 *
 * **CR-6 / F4 = α（受权增量）—— 出站登记**：本 hook 在 connect 后把该实例登记为
 * **活动推送通道**（`setActivePushChannel`），cleanup 时注销（`releaseActivePushChannel`，
 * 带身份判定以防「切换宠物」窗口内新旧串台）。触发侧（`api/events`）据此经**同一条**
 * 连接发送 ⇒ 驱动与观察同源；⛔ 本 hook **仍**不感知事件语义、**不**新建第二连接。
 *
 * **CR-11（受权增量）—— 音效写通道**：新增 `writeAudio`（音效帧 ⇒ `store.applyPlaybackAudio`）。
 * 三条 push 写通道属**同一**「唯一写出口集合」，**互不代偿**（事件帧 / 状态帧 / 音效帧
 * 各走各的落点）。⛔ 本 hook **仍**只是接线：**不**播放音频、**不**拼接地址
 * （播放归 `usePlaybackAudio` → `services/playbackAudio`）。
 */

import { useEffect } from "react";

import {
  createWebSocketClient,
  releaseActivePushChannel,
  setActivePushChannel,
  type WebSocketClient,
} from "../services/websocketClient";
import { usePetStore } from "../stores/usePetStore";
import type { PlaybackAudioFrame, PushEnvelope, PushStateSnapshot } from "../types/push";

/** store 写通道接线（PC-4）：合法 envelope 的**唯一**落点。 */
function writeEnvelope(envelope: PushEnvelope): void {
  usePetStore.getState().applyPushEvent(envelope);
}

/** store 状态写通道接线（PC-4 / PC-2 v1.1，CR-6）：合法**状态帧**的**唯一**落点。 */
function writeSnapshot(snapshot: PushStateSnapshot): void {
  usePetStore.getState().applyPlaybackSnapshot(snapshot);
}

/** store 音效写通道接线（PC-4，**CR-11**）：合法**音效帧**的**唯一**落点。 */
function writeAudio(frame: PlaybackAudioFrame): void {
  usePetStore.getState().applyPlaybackAudio(frame);
}

/**
 * 纯 JS 启停编排（零 React 依赖，可在 node 环境完整测试）：
 * 建连并返回 stop 函数（cleanup 调 `close()`）。
 *
 * **CR-6 / F4 = α**：建连后登记为**活动推送通道**；stop 时注销（含身份判定）。
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
      onSnapshot: writeSnapshot,
      onAudio: writeAudio,
      petId: options?.petId ?? null,
    });
  client.connect();
  // CR-6 / F4 = α：登记活动推送通道 —— 触发侧经**同一实例**发送（不新建第二连接）。
  setActivePushChannel(client);
  return () => {
    client.close();
    releaseActivePushChannel(client);
  };
}

/**
 * App 级生命周期钩子：挂载建立 push 通道，**宠物变化时**关闭旧连接并建立新上下文连接
 * （MPF-4），卸载关闭。生产调用由 `App` 传入 store 中的当前宠物。
 */
export function useRuntimePush(petId: string | null = null): void {
  useEffect(() => startRuntimePush({ petId }), [petId]);
}
