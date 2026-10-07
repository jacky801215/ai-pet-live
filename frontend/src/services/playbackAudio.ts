/**
 * playbackAudio —— 动作**伴随音效**的播放模块（**CR-11**）。
 *
 * 契约来源：`docs/change_request/cr-11_audio_feedback_design.md` §4.4 / §4.5。
 *
 * 为什么**不放** `PetPlayer`（三重冻结约束）：
 *
 * - **FP-3**：`PetPlayer` 的属性白名单 = `src / autoplay / muted / playsInline /
 *   controls={false} / preload / loop` —— **不含** `<audio>`；
 * - **FP-4**：播放器内部**禁止** `useState` / `useEffect` / `ref` / 回写 `currentTime`
 *   —— 而音效必须**命令式** `play()`；
 * - **FCM-4**：白名单仅文本 / 图片 URL / className，**禁自建播放器**。
 *
 * ⇒ 音效由本**独立非 React 模块**承载：持有**单个** `Audio` 实例，
 * 暴露 `play(frame)` / `stop()` / `enableAudio()`。`PetPlayer` **零改动**。
 *
 * 关键语义（CR-11）：
 *
 * 1. **`seq` 是唯一去重依据** —— 同 `action` 不同 `seq` **必须重新播放**
 *    （状态帧是电平触发 + 变化去重，承载音效会漏播第二次；见 CR-11 §3.4 负对照）；
 * 2. **新动作到达 ⇒ `stop` 旧 + `play` 新**（生命周期规则第 1 条）；
 * 3. **全部失败静默降级**：浏览器默认 autoplay 策略下 `play()` 会被拒
 *    （`NotAllowedError`）—— 该 rejection **必须被捕获**，不得冒泡、
 *    不得影响视频链路（OBS 的 CEF 已放行无手势播放）；
 * 4. **解锁入口 `enableAudio()`**（CR-11 §4.4 第 4 条）：浏览器侧需**用户手势**解锁一次
 *    ⇒ 提供本方法供点击回调调用；**绝不假设**自动播放成功。
 */

import type { PlaybackAudioFrame } from "../types/push";

/** `Audio` 的最小形状（浏览器内建 `HTMLAudioElement` 天然满足；测试用替身只需此接口）。 */
export interface AudioLike {
  /** 媒体地址（由后端产出，本模块**不**拼接、**不**判断类型 —— RB-2）。 */
  src: string;
  /** 播放位置（秒）；`stop()` 会复位为 0。 */
  currentTime: number;
  /** 静音标志；`enableAudio()` 解锁时**临时**置 `true`（可选：测试替身可省略）。 */
  muted?: boolean;
  /** 开始播放；可能返回 Promise（被拒时**必须**被本模块吞掉）。 */
  play: () => Promise<void> | void;
  /** 暂停。 */
  pause: () => void;
}

export interface PlaybackAudioOptions {
  /** `Audio` 构造注入（测试替身）；默认使用运行时内建构造。 */
  createAudio?: () => AudioLike;
  /** 可选审计回调：播放失败 / 被拒原因（**不**影响主链路，不抛错）。 */
  onError?: (reason: string, detail: unknown) => void;
}

/** 播放控制器公开形状。 */
export interface PlaybackAudioController {
  /** 播放一帧音效（`seq` 相同则视为同一触发，不重放）。 */
  play: (frame: PlaybackAudioFrame) => void;
  /** 停止当前音效并复位播放位置。 */
  stop: () => void;
  /** 当前已处理的 `seq`（测试与守卫用）；尚未播放过时为 `null`。 */
  currentSeq: () => number | null;
  /**
   * **用户手势内**调用以解锁音频通道（浏览器 autoplay 策略；CR-11 §4.4 第 4 条）。
   *
   * 语义（冻结）：
   *
   * - **幂等**：已确认解锁后再次调用直接返回 `true`，不重复试播；
   * - 首次调用：确保 `Audio` 实例存在，并对**当前源**做一次**静音** `play()`；
   *   成功后立即 `pause()` + 复位并恢复原 `muted` ⇒ **不产出可听输出**；
   * - **不改变 `seq`**、**不打断**已受理的音效语义（去重判据仍只认 `seq`）；
   * - 尚无任何音效源（`src` 为空）⇒ 返回 `false`（合法的「暂不可解锁」态，**不报错**）；
   * - `NotAllowedError` / 任何异常 ⇒ `onError(...)` + 返回 `false`，**绝不外抛**。
   *
   * 返回 `true` = 该实例**已被确认可播**（此后带声 `play()` 在同一手势上下文内被放行）。
   */
  enableAudio: () => Promise<boolean>;
}

/**
 * 运行时内建 `Audio` 构造；不可用时**明确抛错**（由调用方收敛为 `onError`，不静默成功）。
 *
 * 注意：不在此处播放，仅构造 —— 真正的 `play()` 由 :func:`createPlaybackAudio` 的
 * 控制器在收到帧时命令式触发。
 */
function defaultCreateAudio(): AudioLike {
  const ctor = (globalThis as { Audio?: new () => AudioLike }).Audio;
  if (typeof ctor !== "function") {
    throw new Error("Audio 运行时不可用（浏览器 / OBS CEF 才内建）");
  }
  return new ctor();
}

/**
 * 构造音效播放控制器（**非 React**：可在 node 环境完整测试）。
 *
 * 行为约束：
 *
 * - **单实例复用**：`Audio` 只在首次 `play()` 时惰性构造，之后复用（不每次 `new`）；
 * - `play(frame)`：`seq` 未变化 ⇒ **不做任何事**；否则 `stop()` 旧音效 → 换 `src` → `play()`；
 * - `play()` 返回的 Promise **一律 `.catch`**（`NotAllowedError` 静默降级）；
 * - `enableAudio()`：**静音试播**一次以取得播放许可，随即收回（见接口注释）；
 * - 构造函数 / `pause` / `src` 赋值异常同样收敛为 `onError`，**绝不抛给调用方**。
 */
export function createPlaybackAudio(
  options: PlaybackAudioOptions = {},
): PlaybackAudioController {
  const createAudio = options.createAudio ?? defaultCreateAudio;
  const onError = options.onError ?? ((): void => undefined);

  let audio: AudioLike | null = null;
  let seq: number | null = null;
  /** 是否已确认解锁（仅 `enableAudio()` 试播成功后置位）。 */
  let enabled = false;

  const stop = (): void => {
    if (audio === null) {
      return;
    }
    try {
      audio.pause();
      audio.currentTime = 0;
    } catch (error) {
      onError("pause failed", error);
    }
  };

  const play = (frame: PlaybackAudioFrame): void => {
    if (frame.seq === seq) {
      return; // 同一触发（seq 未变）⇒ 不重放
    }
    seq = frame.seq;
    stop();
    try {
      if (audio === null) {
        audio = createAudio();
      }
      audio.src = frame.audio_url;
      const started = audio.play();
      // 浏览器 autoplay 策略拒绝时 play() 返回 rejected Promise —— 必须静默降级。
      if (
        started !== undefined &&
        started !== null &&
        typeof (started as Promise<void>).catch === "function"
      ) {
        (started as Promise<void>).catch((error: unknown) => {
          onError("play rejected", error);
        });
      }
    } catch (error) {
      onError("play failed", error);
    }
  };

  const enableAudio = async (): Promise<boolean> => {
    if (enabled) {
      return true; // 幂等：已确认可播
    }
    let target: AudioLike;
    try {
      if (audio === null) {
        audio = createAudio();
      }
      target = audio;
    } catch (error) {
      onError("enableAudio failed", error);
      return false;
    }
    if (!target.src) {
      // 尚无任何音效源：没有任何东西可以试播 ⇒ 合法「暂不可解锁」，不报错。
      return false;
    }
    const previousMuted = target.muted;
    try {
      target.muted = true; // 静音试播：绕过「带声 autoplay」限制
      const started = target.play();
      if (
        started !== undefined &&
        started !== null &&
        typeof (started as Promise<void>).then === "function"
      ) {
        await started;
      }
      target.pause();
      target.currentTime = 0; // 收回试播：不产出可听输出，也不改变 seq
      enabled = true;
      return true;
    } catch (error) {
      onError("enableAudio rejected", error);
      return false;
    } finally {
      target.muted = previousMuted; // 无论成败都恢复原静音态
    }
  };

  return { play, stop, currentSeq: (): number | null => seq, enableAudio };
}
