/**
 * CR-11 音效反馈测试（前端侧）—— `playback_audio` 帧 → store → 播放模块。
 *
 * 契约来源：`docs/change_request/cr-11_audio_feedback_design.md` §4.3 / §4.4 / §4.5。
 *
 * 运行：`npm test`（vitest run，**node 环境、零新增依赖、无 jsdom**）。
 * 因无 jsdom，`usePlaybackAudio` 的 `useEffect` **不在测试中执行** ——
 * 故播放语义由**可直接驱动的非 React 模块**（`services/playbackAudio`）行为测试锁定，
 * hook 本身以**接线静态守卫**锁定（与本项目 push / runtime 测试同一范式）。
 *
 * 覆盖（指令 Step 7 前端三条 + CR-11 契约）：
 *
 * - Case A **seq replay**：`seq` 变化 ⇒ `stop` 旧 + `play` 新；**同 action 不同 seq 必须重放**；
 * - Case B **interrupt**：`heart` → `happy` ⇒ STOP + PLAY（新音效从头）；
 * - Case C **非 audio event ignore**：状态帧 / 事件帧一律**不触发**播放（三类帧互斥）；
 * - Case D 静默降级：`NotAllowedError`（浏览器默认策略）被吞掉，不冒泡、不影响主链路；
 * - Case E 形状校验：音效帧键集恰 5 项、字段类型正确，否则拒收；
 * - Case F 写入边界：`applyPlaybackAudio` 只写 `lastAudio`，不触其它切片；
 * - Case G 接线守卫：`PetPlayer` 零改动（零音频引用）；
 * - Case H **enableAudio**：用户手势静音试播解锁（幂等 / 无源 false / 拒绝降级 / 不改 seq）；
 * - Case I **首次交互接入**（Step 5 · Decision A）：hook 内一次性 pointerdown + keydown、
 *   不新增重复监听层 / 不新增 UI、App 仍零参挂载。
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { beforeEach, describe, expect, it, vi } from "vitest";

import { createPlaybackAudio, type AudioLike } from "../../src/services/playbackAudio";
import {
  createWebSocketClient,
  parseAudioFrame,
  type SocketLike,
} from "../../src/services/websocketClient";
import { usePetStore } from "../../src/stores/usePetStore";
import { DEFAULT_SELECTED_PET_ID } from "../../src/config/pets";
import {
  AUDIO_FRAME_TYPE,
  PLAYBACK_AUDIO_KEYS,
  type PlaybackAudioFrame,
} from "../../src/types/push";

const HEART_URL = "/assets/pets/cat/actions/heart/heart.ogg";
const HAPPY_URL = "/assets/pets/cat/actions/happy/happy.ogg";

function frame(seq: number, action = "heart", url = HEART_URL): PlaybackAudioFrame {
  return { pet_id: "cat_001", action, audio_url: url, seq };
}

/** 注入式假 `Audio`（node 无内建 Audio；零依赖替身，记录 play / pause 次数）。 */
class FakeAudio implements AudioLike {
  src = "";
  currentTime = 0;
  muted = false;
  playCount = 0;
  pauseCount = 0;
  /** 记录「play() 被调用那一刻」的 muted 值 —— 用于证明 enableAudio 走静音试播。 */
  mutedDuringPlay: boolean | null = null;

  constructor(private readonly rejection: Error | null = null) {}

  play = (): Promise<void> | void => {
    this.playCount += 1;
    this.mutedDuringPlay = this.muted;
    return this.rejection === null ? undefined : Promise.reject(this.rejection);
  };

  pause = (): void => {
    this.pauseCount += 1;
  };
}

/** 注入式假 socket（与 `websocketPush.test.tsx` 同型）。 */
class FakeSocket implements SocketLike {
  closed = false;
  private listeners: ((event: { data: unknown }) => void)[] = [];

  addEventListener = (
    type: string,
    listener: (event: { data: unknown }) => void,
  ): void => {
    if (type === "message") {
      this.listeners.push(listener);
    }
  };

  close = (): void => {
    this.closed = true;
  };

  emit(payload: unknown): void {
    const data = typeof payload === "string" ? payload : JSON.stringify(payload);
    for (const listener of this.listeners) {
      listener({ data });
    }
  }
}

function readSource(rel: string): string {
  return readFileSync(fileURLToPath(new URL(`../../${rel}`, import.meta.url)), "utf-8");
}

/** 剥离块注释与行注释 —— 守卫约束的是**代码**，文档里提到被禁标识是合法的。 */
function stripComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^\s*\/\/.*$/gm, "");
}

beforeEach(() => {
  usePetStore.setState({
    playback: null,
    recentEvents: [],
    stats: null,
    petContext: { selectedPetId: DEFAULT_SELECTED_PET_ID },
    lastAudio: null,
  });
});

// ---------------------------------------------------------------------------
// Case A / B / D：播放语义（seq replay · interrupt · 静默降级）
// ---------------------------------------------------------------------------

describe("Case A/B/D 播放模块（services/playbackAudio）", () => {
  it("Case A 同 action 不同 seq ⇒ STOP 旧 + PLAY 新（必须重新播放，不得按 action 去重）", () => {
    const audio = new FakeAudio();
    const controller = createPlaybackAudio({ createAudio: () => audio });

    controller.play(frame(1));
    expect([audio.playCount, audio.pauseCount, audio.src]).toEqual([1, 0, HEART_URL]);

    controller.play(frame(2)); // 同 action、不同 seq
    expect(audio.playCount).toBe(2); // 重新播放
    expect(audio.pauseCount).toBe(1); // 旧音效被停止
    expect(audio.currentTime).toBe(0); // 且复位到起点
    expect(controller.currentSeq()).toBe(2);
  });

  it("同一 seq 重复投递 ⇒ 不重放（去重只认 seq）", () => {
    const audio = new FakeAudio();
    const controller = createPlaybackAudio({ createAudio: () => audio });

    controller.play(frame(1));
    controller.play(frame(1));
    controller.play(frame(1));

    expect(audio.playCount).toBe(1);
    expect(audio.pauseCount).toBe(0);
  });

  it("Case B interrupt：heart → happy ⇒ STOP + PLAY，且换源", () => {
    const audio = new FakeAudio();
    const controller = createPlaybackAudio({ createAudio: () => audio });

    controller.play(frame(3, "heart", HEART_URL));
    controller.play(frame(4, "happy", HAPPY_URL));

    expect(audio.playCount).toBe(2);
    expect(audio.pauseCount).toBe(1);
    expect(audio.src).toBe(HAPPY_URL);
    expect(audio.currentTime).toBe(0);
  });

  it("Case D NotAllowedError 被静默降级：不抛错、onError 收到原因", async () => {
    const rejected = Object.assign(new Error("no gesture"), { name: "NotAllowedError" });
    const audio = new FakeAudio(rejected);
    const errors: string[] = [];
    const controller = createPlaybackAudio({
      createAudio: () => audio,
      onError: (reason) => errors.push(reason),
    });

    expect(() => controller.play(frame(1))).not.toThrow();
    await Promise.resolve(); // 让 rejection 的 catch 落地
    await Promise.resolve();

    expect(errors).toEqual(["play rejected"]);
    expect(controller.currentSeq()).toBe(1); // 仍记为已处理，避免重复尝试
  });

  it("Audio 构造失败同样静默降级（不冒泡）", () => {
    const errors: string[] = [];
    const controller = createPlaybackAudio({
      createAudio: () => {
        throw new Error("Audio 运行时不可用");
      },
      onError: (reason) => errors.push(reason),
    });

    expect(() => controller.play(frame(1))).not.toThrow();
    expect(errors).toEqual(["play failed"]);
  });

  it("单实例复用：多次播放只构造一次 Audio", () => {
    const created: FakeAudio[] = [];
    const controller = createPlaybackAudio({
      createAudio: () => {
        const audio = new FakeAudio();
        created.push(audio);
        return audio;
      },
    });

    controller.play(frame(1));
    controller.play(frame(2));
    controller.play(frame(3));

    expect(created).toHaveLength(1);
    expect(created[0]?.playCount).toBe(3);
  });

  it("stop() 幂等：无音效实例时不抛错", () => {
    const controller = createPlaybackAudio({ createAudio: () => new FakeAudio() });
    expect(() => controller.stop()).not.toThrow();
    expect(controller.currentSeq()).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Case H：enableAudio —— 用户手势解锁（浏览器 autoplay 策略；CR-11 §4.4 第 4 条）
// ---------------------------------------------------------------------------

describe("Case H enableAudio 用户手势解锁", () => {
  it("首次解锁：静音试播 ⇒ 立刻收回；返回 true 且 **不改变 seq**", async () => {
    const audio = new FakeAudio();
    audio.src = HEART_URL; // 已有音效源（此前收到过帧）才可能解锁
    const controller = createPlaybackAudio({ createAudio: () => audio });

    expect(controller.currentSeq()).toBeNull();
    await expect(controller.enableAudio()).resolves.toBe(true);

    expect(audio.playCount).toBe(1);
    expect(audio.mutedDuringPlay).toBe(true); // 走的是静音试播
    expect(audio.muted).toBe(false); // 试播后复原
    expect(audio.pauseCount).toBe(1); // 立即收回，不产出可听输出
    expect(audio.currentTime).toBe(0);
    expect(controller.currentSeq()).toBeNull(); // 解锁不是一次「触发」
  });

  it("幂等：已解锁后再次调用直接返回 true，不再试播", async () => {
    const audio = new FakeAudio();
    audio.src = HEART_URL;
    const controller = createPlaybackAudio({ createAudio: () => audio });

    await controller.enableAudio();
    const after = audio.playCount;
    await expect(controller.enableAudio()).resolves.toBe(true);
    expect(audio.playCount).toBe(after);
  });

  it("尚无音效源（src 为空）⇒ 返回 false，且**不报错**、不试播", async () => {
    const audio = new FakeAudio();
    const errors: string[] = [];
    const controller = createPlaybackAudio({
      createAudio: () => audio,
      onError: (reason) => errors.push(reason),
    });

    await expect(controller.enableAudio()).resolves.toBe(false);
    expect(audio.playCount).toBe(0);
    expect(errors).toEqual([]);
  });

  it("NotAllowedError ⇒ 返回 false、onError 收到原因、绝不外抛", async () => {
    const rejected = Object.assign(new Error("gesture required"), {
      name: "NotAllowedError",
    });
    const audio = new FakeAudio(rejected);
    audio.src = HEART_URL;
    const errors: string[] = [];
    const controller = createPlaybackAudio({
      createAudio: () => audio,
      onError: (reason) => errors.push(reason),
    });

    await expect(controller.enableAudio()).resolves.toBe(false);
    expect(errors).toEqual(["enableAudio rejected"]);
    expect(audio.muted).toBe(false); // 失败路径同样复原静音态
  });

  it("Audio 构造失败 ⇒ 返回 false + onError，不冒泡", async () => {
    const errors: string[] = [];
    const controller = createPlaybackAudio({
      createAudio: () => {
        throw new Error("Audio 运行时不可用");
      },
      onError: (reason) => errors.push(reason),
    });

    await expect(controller.enableAudio()).resolves.toBe(false);
    expect(errors).toEqual(["enableAudio failed"]);
  });

  it("解锁不影响 seq 语义：先 play(1) 再 enableAudio ⇒ 后续 play(2) 仍重放", async () => {
    const audio = new FakeAudio();
    const controller = createPlaybackAudio({ createAudio: () => audio });

    controller.play(frame(1));
    expect(controller.currentSeq()).toBe(1);

    await controller.enableAudio(); // 此时 src 已由 play(1) 设置
    expect(controller.currentSeq()).toBe(1); // seq 不被解锁改写

    controller.play(frame(2));
    expect(audio.playCount).toBe(3); // play(1) + enableAudio 试播 + play(2)
    expect(controller.currentSeq()).toBe(2);
  });
});

// ---------------------------------------------------------------------------
// Case C / E：帧型分流（非 audio 帧一律忽略）+ 形状校验
// ---------------------------------------------------------------------------

describe("Case C/E 音效帧形状与分流", () => {
  it("Case E 合法音效帧 ⇒ 4 字段；键集恰 5 项（含判别键）", () => {
    const raw = JSON.stringify({
      type: AUDIO_FRAME_TYPE,
      pet_id: "cat_001",
      action: "heart",
      audio_url: HEART_URL,
      seq: 7,
    });
    expect(parseAudioFrame(raw)).toEqual({
      pet_id: "cat_001",
      action: "heart",
      audio_url: HEART_URL,
      seq: 7,
    });
    expect(PLAYBACK_AUDIO_KEYS).toEqual([
      "type",
      "pet_id",
      "action",
      "audio_url",
      "seq",
    ]);
  });

  it("Case E 非法音效帧一律拒收（缺字段 / 多字段 / 类型错 / 非音效帧）", () => {
    const base = {
      type: AUDIO_FRAME_TYPE,
      pet_id: "cat_001",
      action: "heart",
      audio_url: HEART_URL,
      seq: 1,
    };
    expect(parseAudioFrame(JSON.stringify({ ...base, pet_id: undefined }))).toBeNull(); // 缺字段
    expect(parseAudioFrame(JSON.stringify({ ...base, extra: 1 }))).toBeNull(); // 多字段
    expect(parseAudioFrame(JSON.stringify({ ...base, seq: "1" }))).toBeNull(); // seq 非数值
    expect(parseAudioFrame(JSON.stringify({ ...base, audio_url: 1 }))).toBeNull(); // url 非字符串
    expect(parseAudioFrame(JSON.stringify({ ...base, seq: 0 }))).not.toBeNull(); // 0 为合法序号
    expect(parseAudioFrame(JSON.stringify({ type: "playback_state" }))).toBeNull();
    expect(parseAudioFrame(JSON.stringify({ event_type: "gift" }))).toBeNull();
    expect(parseAudioFrame("{not-json")).toBeNull();
  });

  it("Case C 音效帧 → onAudio；状态帧 / 事件帧 → 一律不触发 onAudio", () => {
    const socket = new FakeSocket();
    const audio: PlaybackAudioFrame[] = [];
    const invalid: string[] = [];
    const client = createWebSocketClient({
      onMessage: vi.fn(),
      onSnapshot: vi.fn(),
      onAudio: (f) => audio.push(f),
      onInvalid: (reason) => invalid.push(reason),
      url: "ws://127.0.0.1:8000/api/ws",
      socketFactory: () => socket,
    });
    client.connect();

    socket.emit({ type: AUDIO_FRAME_TYPE, ...frame(1) });
    expect(audio).toHaveLength(1);

    // 第二类帧：状态帧（7 字段快照）—— 不得落入音效分支
    socket.emit({
      type: "playback_state",
      snapshot: {
        pet_id: "cat_001",
        state: "playing",
        action: "heart",
        asset_url: "/assets/pets/cat/actions/heart/heart.mp4",
        queue_size: 0,
        last_event: "gift",
        loop: false,
      },
    });
    // 第一类帧：WM-1 envelope —— 不得落入音效分支
    socket.emit({
      event_type: "gift",
      payload: { gift_name: "小心心" },
      timestamp: "2026-10-07T00:00:00Z",
      source: "ws",
    });

    expect(audio).toHaveLength(1);
    expect(invalid).toEqual([]);

    // 畸形音效帧 ⇒ 拒收 + 审计，不落 onAudio
    socket.emit({ type: AUDIO_FRAME_TYPE, pet_id: "cat_001", action: "heart" });
    expect(audio).toHaveLength(1);
    expect(invalid).toEqual(["invalid audio frame"]);
  });
});

// ---------------------------------------------------------------------------
// Case F：store 写入边界
// ---------------------------------------------------------------------------

describe("Case F store 音效切片（applyPlaybackAudio）", () => {
  it("初始 lastAudio 为 null；写入为整份替换", () => {
    expect(usePetStore.getState().lastAudio).toBeNull();

    const first = frame(1);
    usePetStore.getState().applyPlaybackAudio(first);
    expect(usePetStore.getState().lastAudio).toEqual(first);

    const second = frame(2);
    usePetStore.getState().applyPlaybackAudio(second);
    expect(usePetStore.getState().lastAudio).toEqual(second);
  });

  it("只写 lastAudio：不触 playback / recentEvents / stats / petContext", () => {
    const before = usePetStore.getState();
    usePetStore.getState().applyPlaybackAudio(frame(9));

    const after = usePetStore.getState();
    expect(after.playback).toBe(before.playback);
    expect(after.recentEvents).toBe(before.recentEvents);
    expect(after.stats).toBe(before.stats);
    expect(after.petContext).toBe(before.petContext);
  });
});

// ---------------------------------------------------------------------------
// Case G：接线与冻结边界（静态守卫）
// ---------------------------------------------------------------------------

describe("Case G 接线守卫（PetPlayer 零改动 / 冻结边界）", () => {
  it("PetPlayer 零音频引用：不放 <audio>、不自建播放器（FP-3 / FCM-4）", () => {
    const player = readSource("src/components/player/PetPlayer.tsx");
    expect(player).not.toContain("<audio");
    expect(player).not.toContain("Audio(");
    expect(player).not.toContain(".ogg");
    expect(player).not.toContain("playbackAudio");
    expect(player).not.toContain("lastAudio");
    expect(player).toContain("<video");
  });

  it("useRuntimePush 接线 onAudio → store.applyPlaybackAudio（PC-4：必须经 store）", () => {
    const hook = readSource("src/hooks/useRuntimePush.ts");
    expect(hook).toContain("onAudio: writeAudio");
    expect(hook).toContain("applyPlaybackAudio");
    // 负向断言剥注释：文档里说明「播放不归本 hook」是合法的，代码里不得出现。
    const code = stripComments(hook);
    expect(code).not.toContain("new Audio");
    expect(code).not.toContain("playbackAudio");
  });

  it("usePlaybackAudio 订阅 store.lastAudio 并以 seq 为判据（不订阅 socket、不拼地址）", () => {
    const hook = readSource("src/hooks/usePlaybackAudio.ts");
    expect(hook).toContain("usePetStore.subscribe");
    expect(hook).toContain("state.lastAudio");
    expect(hook).toContain("frame.seq === lastSeq");
    expect(hook).toContain("audio.play(frame)");
    expect(hook).toContain("enableAudio");
    expect(hook).not.toContain("WebSocket");
    expect(hook).not.toContain("fetch(");
    expect(hook).not.toMatch(/from\s+["'][^"']*api/);
  });

  it("App 作为组合根挂载 usePlaybackAudio（与 useRuntimePush 同构）", () => {
    const app = readSource("src/App.tsx");
    expect(app).toContain("usePlaybackAudio()");
    expect(app).toContain('from "./hooks/usePlaybackAudio"');
    expect(app).not.toContain("useState(");
  });

  it("播放模块不 import API 层 / 不硬编码域名（RB-2：地址由后端产出）", () => {
    const service = readSource("src/services/playbackAudio.ts");
    expect(service).not.toMatch(/from\s+["'][^"']*api/);
    expect(service).not.toMatch(/from\s+["'][^"']*react/);
    expect(service).not.toContain("/assets/");
  });

  it("types/push.ts 三类帧常量齐备且互斥", () => {
    const types = readSource("src/types/push.ts");
    expect(types).toContain('STATE_FRAME_TYPE = "playback_state"');
    expect(types).toContain('AUDIO_FRAME_TYPE = "playback_audio"');
    expect(AUDIO_FRAME_TYPE).not.toBe("playback_state");
  });
});

// ---------------------------------------------------------------------------
// Case I：首次用户交互 → enableAudio（CR-11 Step 5 · Decision A 静态守卫）
// ---------------------------------------------------------------------------

describe("Case I 首次交互解锁接入（Decision A：复用已有 hook，不新增 UI / 监听层）", () => {
  it("hook 在**已有 mount 点**内挂一次性 pointerdown + keydown 监听", () => {
    const hook = readSource("src/hooks/usePlaybackAudio.ts");
    expect(hook).toContain('addEventListener("pointerdown"');
    expect(hook).toContain('addEventListener("keydown"');
    expect(hook).toContain("removeEventListener");
    expect(hook).toContain("audio.enableAudio()");
    // 返回值暴露解锁入口（组合根可手势内调用）
    expect(hook).toContain("return { enableAudio: audio.enableAudio }");
  });

  it("不新增重复监听层：**不**额外挂 click（与 pointerdown 语义重叠）", () => {
    const code = stripComments(readSource("src/hooks/usePlaybackAudio.ts"));
    expect(code).not.toContain('addEventListener("click"');
    expect(code).not.toContain('addEventListener("mousedown"');
    expect(code).not.toContain('addEventListener("touchstart"');
    // 只有两个注册点
    expect(code.match(/addEventListener\(/g)?.length).toBe(2);
  });

  it("成功后移除监听 / 失败不阻断主流程（settled + inFlight 守卫、异常被吞）", () => {
    const code = stripComments(readSource("src/hooks/usePlaybackAudio.ts"));
    expect(code).toContain("settled");
    expect(code).toContain("inFlight");
    expect(code).toContain("detach()");
    // 解锁失败不得外抛：Promise 走 then(onFulfilled, onRejected) 两参形式
    expect(code).toMatch(/\.then\(\s*\(ok\)/);
  });

  it("不引入第二层监听副作用：hook 不订阅 socket、不触碰 WS / playback_state", () => {
    const code = stripComments(readSource("src/hooks/usePlaybackAudio.ts"));
    expect(code).not.toContain("WebSocket");
    expect(code).not.toContain("applyPlaybackState");
    expect(code).not.toContain("setState");
    expect(code).not.toContain("raw");
  });

  it("App 仍零参挂载（不新增 UI 按钮 / 不在 App 接线 enableAudio）", () => {
    const app = stripComments(readSource("src/App.tsx"));
    expect(app).toContain("usePlaybackAudio()");
    expect(app).not.toContain("enableAudio"); // Decision A：接入点在 hook，不在 App
    expect(app).not.toContain("useState(");
    expect(app).not.toContain("useEffect(");
    expect(app).not.toContain("<audio");
  });
});
