# Phase 4 · OBS 音频运行要求（v1.0）

> **状态**：**v1.0 · 非冻结规格（运行环境要求）** —— **不属 v1.0 冻结条款集**，**未在 `PROJECT_RULES.md` §十四 登记**；
> 条款化需另行走 CR。
> **归属**：**CR-11 音效反馈**的**运行侧**配套要求。契约本体见
> `docs/change_request/cr-11_audio_feedback_design.md`（§4.6 = 本节条款的来源）。
> **依据**：仓库与装置**实测**（2026-10-07，HEAD `f0a37d2`，tag `v1.0-webm-alpha-assets`）——
> 下表所有 dB 值、`play` 判定与设备版本号**均为实测值，非推断**。
> **取证脚本 / 原始报告**（均在**工作区**，不入仓库）：
> `tmp/p4e_reroute.py` → `out_p4d_reroute.json`；`tmp/p4f2_audio_lab.py` → `p4_audio_lab/report.json`；
> `tmp/p4cr11_s5_pipeline.py` → `tmp/out_p4cr11_s5.json`（管线端到端）。
> **装置**：便携 OBS **31.0.2** · obs-websocket **5.5.5** · CEF `chromium-127.0.6533.120`。

---

## 一、适用范围

本文件规定**音效反馈（CR-11）在 OBS 直播链路中的运行前提**。它是**环境配置要求**，
**不引入**任何代码改动 —— 仓库侧（`assets.audio_path` / `playback_audio` 帧 /
`services/playbackAudio`）按 `cr-11_audio_feedback_design.md` 落地，OBS 侧按本文件配置。

> ⚠️ **缺一不可**：若 OBS 侧未按 §二 配置，音效**不会报错**、日志**不会告警**，
> 而是**静默无声**（实测 `-91.0 dB`）。这是本文件存在的唯一理由。

---

## 二、Browser Source 音频路由（**硬性要求**）

| 项 | 取值 | 说明 |
|---|---|---|
| 源类型 | **Browser Source**（页面源） | 与视觉画面**同一个**源，**不**新建第二源 |
| `reroute_audio` | **`true`** | ⛔ **硬性要求**，见下表对照 |
| URL | `http://127.0.0.1:<port>/` | ⛔ **必须**用 `127.0.0.1`（`file://` 会被 CEF taint） |
| `restart_when_active` | **`false`** | 禁止 OBS 在源激活时重载页面（会打断播放与订阅） |

### 2.1 `reroute_audio` 对照实测（同会话三组，控制组校准）

三组使用**同一**录音配置、**同一**场景，仅切换 `reroute_audio` 与输入源：

| 组 | 输入源 | `reroute_audio` | 混音轨 `mean_volume` | `max_volume` | 有音频信号 |
|---|---|---|---|---|---|
| A（控制组） | `tone.wav`（音频输入源） | — | **-7.5 dB** | -1.5 dB | ✅ `True` |
| B（实验组） | 页面源（`<audio>` 播放） | **`false`** | **-91.0 dB** | -91.0 dB | ⛔ **`False`** |
| C（实验组） | 页面源（`<audio>` 播放） | **`true`** | **-7.6 dB** | -4.3 dB | ✅ `True` |

- **控制组 A 是判定基准**：它证明「录音链本身有信号」（`-7.5 dB` / max `-1.5 dB`），
  否则 B 的 `-91.0 dB` 无法与「装置坏了」区分。
- **B = `false` ⇒ `-91.0 dB` = 数字静音**：页面源的音频**根本不进入** OBS 混音链。
  在 OBS 里**看不到**任何异常（源正常渲染、画面正常），只是**没有声音**。
- **C = `true` ⇒ `-7.6 dB`**：音频进入混音链，与控制组 A 同量级。
  ⇒ **`reroute_audio=true` 是音效可听的充分必要条件。**

> 汇总口径（`p4_audio_lab/report.json`）：`control_tone = -7.5 dB` ·
> `case_A_false = -91.0 dB` · `case_B_true = -7.5 dB`。
> ⚠️ 由于播放内容不是恒定音调、且录音起点有偏移，`true` 组在多次运行中落在
> **`-7.5 ~ -7.6 dB`**（`max` 在 `-1.5 ~ -4.3 dB`），**属正常抖动**；
> 判定只需区分「约 -7 dB 量级」与「-91 dB 数字静音」两个**离散**状态。

### 2.2 为什么用「录制混音轨」而非实时电平

⛔ **obs-websocket 5.5.5 不提供音频电平查询接口**（无 `GetInputVolume` 类的**电平**读法，
`GetInputVolume` 只读推子值，不反映是否有信号）。
⇒ 本文件的权威判据 = **录制成品的音频轨 `volumedetect`**（`mean_volume` / `max_volume`），
不用推子值 / 不用混音器 UI 截图。

---

## 三、OBS CEF 可**无用户手势**播放（实测）

浏览器侧与 OBS 侧**策略不同**，必须分别对待：

| 环境 | 无手势 `play()` | 证据 |
|---|---|---|
| Chrome（默认 autoplay 策略） | ⛔ **REJECT** `NotAllowedError` | `chrome_default_autoplay = REJECT`；原始错误串：`play() failed because the user didn't interact with the document first. https://goo.gl/xX8pDD`；`userActivation.hasBeenActive = False` |
| Chrome（注入真实点击后） | ✅ PASS | `chrome_user_activation = PASS`（`advanced = True`） |
| **OBS CEF（Browser Source）** | ✅ **PASS** | `cef_summary`：**43 / 43** 采样点 `play_OK = 1`、`play_REJECT = 0`；`max_currentTime = 9.103 s`（确有推进）；`advanced_ever = True`；且全程 **`ua_ever_active = False`**（**从未**发生任何用户激活） |

- **结论**：在 OBS 里**无需**任何「先点击 / 先交互」的解锁步骤；页面加载完成后
  `<audio>.play()` 直接成功并推进播放位置。
- ⚠️ **不得**据此推断「浏览器侧也无需手势」：Chrome / 普通浏览器**默认策略下必然被拒**。
  故 `services/playbackAudio.ts` **必须**把 `play()` 的 rejection **一律 `.catch`**
  （静默降级），使浏览器侧「无声但不报错」，OBS 侧「正常发声」（CR-11 §4.4 / §4.5）。

---

## 四、装置与运行纪律（LAB 实测踩坑，必须遵守）

1. **就绪闸门**：obs-websocket 可在 **OBS 就绪前**完成握手并返回**空响应**
   （此时 `GetVersion.responseData = {}`、`CreateInput` **静默失败**、`GetSceneItemList = []`）。
   ⇒ **必须**先轮询 `GetVersion.obsVersion` 非空作为**就绪闸门**（实测 `obsVersion = 31.0.2`），
   再执行任何写操作；写操作**必须**检查 `requestStatus.result`（实测 `requestStatus` 与
   `responseData` 分离）。
2. **场景项计数闸门**：`CreateScene` / `CreateInput` 之后**必须**用
   `GetSceneItemList` 计数复核（实测 `count = 3` 才继续）；
   ⛔ `CreateInput` 在**输入名已存在**时**静默失败**（不报错、不覆盖）⇒ 必须**唯一命名**。
3. **预热**：Browser Source 首次渲染到可交互需**真实约 45 ~ 50 s** ⇒ 录制前必须预热，
   否则录到空白帧。
4. **单一节目场景**：Browser Source 只在**当前节目场景**渲染（其余恒 100 % 透明）
   ⇒ `SetCurrentProgramScene` **只切一次**。
5. **音频轨勾选**：页面源必须在目标音频轨上**已勾选**（实测 `inputAudioTracks` 1~6 全 `True`）；
   ⛔ `reroute_audio` 与「轨勾选」是**两件**独立的事，**都要**满足。
6. **不新增源 / 不改视觉**：音效**复用**视觉用的那一个 Browser Source；
   ⛔ 不得为音频新建第二源、不得改源尺寸 / 滤镜 / 混合模式。

---

## 五、不变项（本文件**不**改变任何已冻结契约）

- **WM-1** envelope **恰 4 字段**、**WP-3 v1.1** 出站帧分类、**API-2 v1.1**
  `PlaybackState` **7 字段**（`extra="forbid"`）—— **逐字不变**；
- `playback_state` 仍为**电平触发 + 变化去重**（`STATE_PUSH_TICK_SECONDS = 0.25`）；
  音效帧 `playback_audio` 为**边缘触发**（每次受理各推一次）—— 二者**语义相反**，
  **不得**合并（否则同动作连触两次会漏播第二次；CR-11 §3.4 负对照已机制性证明：
  按 `action` 去重时第二次 `taken = SKIP`，`playCount` 停在 1）；
- `PetPlayer` **零改动**（FP-2 / FP-3 / FP-4 逐字不变）：音效**不**进播放器组件，
  由 `services/playbackAudio` + `hooks/usePlaybackAudio` 承载；
- `assets` 表**保持** `UNIQUE(pet_type, action)`，**不引入** `asset_kind`、
  **不新增** `migrations/` 目录。

---

## 六、验收清单（OBS 侧）

| # | 检查项 | 判据 |
|---|---|---|
| 1 | `reroute_audio` | **`true`** |
| 2 | `restart_when_active` | `false` |
| 3 | URL 主机 | `127.0.0.1`（非 `localhost` 亦可，**非** `file://`） |
| 4 | 就绪闸门 | `GetVersion.obsVersion` 非空后才做写操作 |
| 5 | 场景项计数 | 与预期一致（防 `CreateInput` 静默失败） |
| 6 | 预热时长 | ≥ 45 s |
| 7 | 音轨勾选 | 目标轨已勾选 |
| 8 | **录音实证** | 触发一次动作后，录制混音轨 `mean_volume` **≫ -91 dB**（应落在 `-8 ~ -4 dB` 量级），且 `max_volume > -91 dB` |
| 9 | **负对照** | 无音效的动作为触发源时，`assets.audio_path` 为 `NULL` ⇒ 后端**不下发** `playback_audio` 帧（非错误） |

> 第 8 项是**唯一**的「真听得见」判据：前 7 项全部满足但 `reroute_audio` 漏配时，
> 结果与「装置未配好」无法区分（都是 `-91.0 dB`）。

---

## 七、与其它阶段文档的关系

- `docs/change_request/cr-11_audio_feedback_design.md` —— 音效契约本体（本文件的**来源**）；
- `docs/development/phase3_asset_spec.md` v0.4 §10.1 —— OBS 运行约束（**视觉**侧，
  Browser Source 渲染 / 预热 / 单场景），本文件在其上**补充音频侧**要求；
- `docs/development/phase3_6_ai_live_compliance_audit.md` —— 直播合规（AI 标识），
  与音效无交叉。

---

## 变更历史

| 版本 | 日期 | 变更 |
|---|---|---|
| v1.0 | 2026-10-07 | 首版：Browser Source `reroute_audio=true` 硬性要求；`false = -91.0 dB` / `true = -7.5 ~ -7.6 dB` 对照实测；OBS CEF 无手势可播（43/43）；装置运行纪律与验收清单（来源：CR-11 §4.6）。 |
