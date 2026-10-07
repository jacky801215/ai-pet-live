/**
 * usePlaybackAudio —— 音效帧 → 播放模块的**唯一接线点**（**CR-11**）。
 *
 * 数据路径（**必须经 store** —— PC-4）：socket → transport（形状校验）→
 * `store.applyPlaybackAudio()` → **本 hook** 订阅 `lastAudio` → `playbackAudio.play()`。
 *
 * ⛔ 本 hook **不**订阅 socket、**不**新建连接、**不**做业务判定；
 * 它只把 store 里的音效帧转成一次命令式播放调用。
 *
 * `PetPlayer` **零改动**（FP-2 / FP-3 / FP-4 逐字不变）：
 * 音效由非可视模块承载，不进入播放器组件的属性面 / 状态面。
 *
 * 生命周期对齐（CR-11 §4.5）：`seq` 变化即「新动作到达」⇒ `stop` 旧 + `play` 新；
 * **同 `action` 不同 `seq` 必须重新播放**（去重只认 `seq`）。
 *
 * **CR-11 Step 5（受权增量）—— 首次用户交互接入 `enableAudio()`（Decision A）**：
 *
 * 仓库内**不存在**任何全局「首次用户交互」监听（实测：`App` 仅按钮级 `onClick`，
 * 全 `src/**` 无 `document/window.addEventListener("click"|"pointerdown"|"keydown")`）。
 * 故按 Decision A 把解锁接入**已有的唯一音频生命周期入口** —— 本 hook（App 已挂载，
 * 组合根，`usePlaybackAudio()` 零参调用）：在**同一个 hook** 内挂**一次性**监听，
 * **不新增** hook / 组件 / UI 按钮 / 第二条监听层。
 *
 * 监听仅两个，且**互不重复**：`pointerdown`（鼠标 + 触摸 + 笔）与 `keydown`（键盘）；
 * `click` 与 `pointerdown` 语义重叠 ⇒ **刻意不挂**（避免重复监听层）。
 *
 * 语义：首次交互触发 `enableAudio()`；**成功后立即移除监听**并停止响应；
 * 失败（如当时尚无音效源，`enableAudio()` 合法返回 `false`）**不阻断主流程**，
 * 保留监听等待下一次交互重试 —— 这是「成功后移除监听」的直接推论：
 * 页面加载时通常尚无任何音效源，若失败即摘除监听，自动解锁将永远无法成功。
 */

import { useEffect, useRef } from "react";

import {
  createPlaybackAudio,
  type PlaybackAudioController,
  type PlaybackAudioOptions,
} from "../services/playbackAudio";
import { usePetStore } from "../stores/usePetStore";

export interface UsePlaybackAudioOptions extends PlaybackAudioOptions {
  /** 仅供测试注入：复用外部构造的播放控制器（省略则内部构造并负责释放）。 */
  controller?: PlaybackAudioController;
}

/** hook 返回值：把控制器上的解锁入口暴露给组合根（用户手势内调用；幂等）。 */
export interface UsePlaybackAudioResult {
  /** 用户手势内调用以解锁音频通道（浏览器 autoplay 策略）。 */
  enableAudio: () => Promise<boolean>;
}

/**
 * App 级音效接线钩子：挂载时建立 store 订阅 + 首次交互解锁监听；
 * 卸载时退订、停止播放并移除解锁监听。
 *
 * 生产调用零参（`usePlaybackAudio()`）；测试可注入 `controller` / `createAudio`。
 */
export function usePlaybackAudio(
  options: UsePlaybackAudioOptions = {},
): UsePlaybackAudioResult {
  const { controller, createAudio, onError } = options;

  // 控制器在**首次渲染**惰性构造并跨渲染复用。
  // ⛔ 无副作用：`createPlaybackAudio` 只创建闭包，真正的 `Audio` 实例在首次播放时才构造
  //    （见 services/playbackAudio.ts 的惰性语义）⇒ 渲染期构造不触碰 DOM / 不产出声音。
  const ref = useRef<PlaybackAudioController | null>(null);
  if (ref.current === null) {
    ref.current = controller ?? createPlaybackAudio({ createAudio, onError });
  }
  const audio = ref.current;

  // (1) 音效帧接线：store.lastAudio → play（去重只认 seq）。
  useEffect(() => {
    let lastSeq: number | null = null;

    // PC-4：socket 回调不直写组件状态 —— 本订阅是**读** store，写只发生在 store 内部。
    const unsubscribe = usePetStore.subscribe((state) => {
      const frame = state.lastAudio;
      if (frame === null || frame.seq === lastSeq) {
        return;
      }
      lastSeq = frame.seq;
      audio.play(frame);
    });

    return () => {
      unsubscribe();
      audio.stop();
    };
  }, [audio]);

  // (2) 首次用户交互 → enableAudio()：一次性、成功即移除监听、失败不阻断主流程。
  useEffect(() => {
    if (typeof window === "undefined" || typeof window.addEventListener !== "function") {
      return; // 非浏览器环境（node 测试）不挂监听
    }
    const win = window;
    let settled = false; // 已解锁：不再响应
    let inFlight = false; // 同一时刻至多一次解锁尝试

    const detach = (): void => {
      win.removeEventListener("pointerdown", onInteraction);
      win.removeEventListener("keydown", onInteraction);
    };

    function onInteraction(): void {
      if (settled || inFlight) {
        return;
      }
      inFlight = true;
      audio.enableAudio().then(
        (ok) => {
          inFlight = false;
          if (ok) {
            settled = true;
            detach(); // 「成功后移除监听」
          }
        },
        () => {
          inFlight = false; // 「失败不阻断主流程」
        },
      );
    }

    win.addEventListener("pointerdown", onInteraction);
    win.addEventListener("keydown", onInteraction);
    return detach;
  }, [audio]);

  // `audio.enableAudio` 是控制器上的稳定箭头属性 ⇒ 引用恒定。
  return { enableAudio: audio.enableAudio };
}
