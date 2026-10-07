# CR-11：音效反馈（Audio Feedback）契约 —— 动作伴随音效接入

> **类型**：功能补齐（MVP 缺口）/ 契约扩展 —— 数据层 + 推送通道 + 前端
> **状态**：**已实施清单见 §八**；设计评审于 2026-10-07 完成，owner 逐项裁决见 §九
> **日期**：2026-10-07
> **基线**：`HEAD = f0a37d2f3d0bda631a39f3a9305a9478f0f64909`（`TAG = v1.0-webm-alpha-assets`，`COMMIT_COUNT = 150`）
> **提出背景**：Phase 4 缺口盘查 —— **音效链路在 Phase 1–3 中完全未实现**，属原始 MVP 的真实功能缺口，非优化项
> **依据**：`PROJECT_RULES.md` §七（需求变更管理）
> **关联文档**：`docs/development/phase3_asset_spec.md`（v0.4 DRAFT · 素材命名口径）· `docs/development/phase4_audio_obs_requirement.md`（**本 CR 新增** · OBS 音频环境要求）
> **编号说明**：`docs/change_request/` 现有 `cr-1…cr-7` + `cr-9`（**无 `cr-8`** —— `CR-8` 仅存于 `db.py` / `test_data_manager.py` 代码注释，专指「连接复用」，无立档）；
> ⇒ **CR-11 为可用编号**；`CR-10` **预留给运行时文档修正**（README 入口，见 F1 / §十）。

---

## 一、需求描述

为**已受理的动作**补充**伴随音效**：动作被受理时，除切换视觉素材外，同时下发并播放其对应音效。

**第一阶段范围（冻结）**：

| 角色 | 动作 | 视觉素材 | 音效 | 触发来源 |
|---|---|---|---|---|
| cat | `idle` | `idle.webm` | **无**（静音） | 回落动作 |
| cat | `heart` | `heart.webm` | **`heart.ogg`** | 礼物「小心心」（`gift_heart`） |
| cat | `happy` | `happy.webm` | **`happy.ogg`** | 点赞「like_dance」 |
| cat | `sad` / `surprise` | `*.mp4` | **暂不覆盖** | 无 UI / 规则入口（登记项 **F2**） |
| dog / panda | 全部 | `*.mp4` | **暂不覆盖** | 避免扩大 CR 面 |

**冻结理由**：① 与「WebM alpha 三资产」（CR-9）的验收面**严格对齐**，音画配对可一次性验完；
② 只覆盖**已有真实动作链**的两个动作，不为无入口动作造资产；③ 范围可加（后续 CR 增量），**不可在本阶段顺手扩展**。

**素材命名与位置（与 CR-9 同构，禁止扫目录）**：

```
assets/pets/{pet_type}/actions/{action}/{action}.ogg
```

与同名 `.webm` **同目录并存**；URL 由既有 `to_asset_url()` 自动产出
（`/assets/pets/cat/actions/heart/heart.ogg`）。

⛔ **静态挂载事实（决定性）**：`backend/app/main.py::_mount_assets()` **只挂载**
`constants.ASSET_URL_PREFIX = "/assets/pets"` → `<PROJECT_ROOT>/assets/pets`。
⇒ **任何 `/assets/audio/**` 形式的 URL 必然 404**；音频资产**必须**落在 `assets/pets/{pet}/actions/{action}/` 下。
（`.ogg` → `audio/ogg` 由 `StaticFiles` 按扩展名自动产出 MIME，**无需改 `main.py`**。）

**格式选型**：**Ogg Vorbis（`.ogg`）**。Chromium / CEF 原生支持、无需额外解码器、体积可控。
不引入第二种容器（`.mp3` 虽亦可，但无必要）。

---

## 二、为什么需要

1. **MVP 原目标包含音效，而 Phase 1–3 只交付了视频链路**：`assets/**` 下**零**音频文件；
   `backend/app/**` 与 `frontend/src/**` 内**零**处音频相关引用；`assets` 表**无**任何音频列；
   `PlaybackState` **无**音频字段；`PetPlayer` 的 `<video>` 恒 **`muted`**。⇒ **真实功能缺口**。
2. **不是「加个文件」就能补上**：涉及 **数据模型 / 增量迁移 / 下发语义 / 前端播放位置 / 直播可听性**
   五处，每一处都被既有**冻结契约**约束（`API-2 v1.1` / `FP-2/3/4` / `PC-4` / `RB-2` / `FCM-4`）。
3. **不能复用状态帧**：`playback_state` 是**电平触发 + 变化去重**（`STATE_PUSH_TICK_SECONDS = 0.25`，**仅在变化时推**）。
   若把音频塞进 `PlaybackState`：**同一动作被连续受理两次时帧内容完全相同 ⇒ 不会重推 ⇒ 第二次音效静默丢失**。
   音效必须**边缘触发**（每次受理各推一次）——这是本 CR 的核心技术裁决（见 §4.3，并有 §3.4 的机制性证明）。
4. **前端不能自行推导音频路径**：`heart.webm → heart.ogg` 的同名推导同时违反 **RB-2**
   （禁前端拼接素材路径 / 禁前端判断素材类型）与 `UI-6` ⇒ 音频地址**必须由后端产出**。
5. **直播侧可听性有环境前提**：OBS Browser Source 的 `reroute_audio` 若为 `false`，
   CEF 音频**不进入 OBS 混音链**（实测数字静音）⇒ 必须固化为**硬性环境要求**（§4.6）。

---

## 三、实测证据（可行性验证，仓库零改动）

> 全部实测在**工作区 LAB** 完成（`p4_audio_lab/`），**未写入仓库任何目录**；
> 权威产物：`p4_audio_lab/report.json`、`out_p4_audio_probe.json`、`out_p4d_reroute.json`。

> ⚠️ **必须记录的方法论事故（第一版探针作废）**：首版探针复用了 `p31_common.launch_chrome()`，
> 而该函数**硬编码** `--autoplay-policy=no-user-gesture-required` 与 `--mute-audio`
> ⇒ 其上跑出的「三组一致 = 默认策略下 autoplay OK」是**装置缺陷造成的假阳性**，已作废。
> 修正版改用**独立 launcher**（不带这两个 flag），并把 HTTP 端口与 OBS 场景源命名全部换新，避免与旧残留串台。
> ⇒ 已沉淀为**跨阶段工具链陷阱**：**任何「默认策略」音频实验必须使用独立 launcher**。

### 3.1 浏览器侧（Chrome）—— 默认策略**拒绝**无手势音频

| 组 | 条件 | `play()` 结果 | `currentTime` 递进 | 用户激活态 |
|---|---|---|---|---|
| A1 | 默认策略，headless，**无手势** | **REJECT** `NotAllowedError` | ✗ 停在 0 | `isActive=false` / `hasBeenActive=false` |
| A2 | 默认策略，headless，**注入真实鼠标点击** | 点击前 REJECT → **点击后 OK** | ✓ 递进 | 点击后 `isActive=true` / `hasBeenActive=true` |
| A3 | 默认策略 + `--autoplay-policy=no-user-gesture-required` | OK（启动参数解锁） | ✓ 递进 | 未激活 |
| A4 | 默认策略，**headful（真实窗口）**，无手势 | **REJECT** `NotAllowedError` | ✗ 停在 0 | 未激活 |

**原始错误串（A1/A4 相同）**：

```
play() failed because the user didn't interact with the document first. https://goo.gl/xX8pDD
```

⇒ **`{"default_autoplay": "REJECT", "user_activation": "PASS"}`**；
headless 与 headful 行为**一致** ⇒ Chrome 侧 autoplay 策略被**严格执行**。

### 3.2 OBS 侧（CEF）—— **可听，且无手势限制**

同一测试页由 OBS `browser_source`（`reroute_audio=true`）加载，页面自回传（每 2 s `POST`）显示：

| 组 | 回传条数 | `play` | `max_currentTime` | `advanced_ever` | `ua_ever_active` |
|---|---|---|---|---|---|
| `reroute_audio=true` | 43 | **OK**（`REJECT` 0 次） | 9.103 s | `true` | **`false`** |
| `reroute_audio=false` | 43 | **OK**（`REJECT` 0 次） | 9.109 s | `true` | **`false`** |

⇒ **OBS 的 CEF 放行无手势音频播放**（`userActivation` 全程 `false`），与 Chrome 默认策略**相反**。
（`reroute=false` 组页面**同样在播**——这正是让 §3.3 对照成立的前提。）

### 3.3 `reroute_audio` 真 / 假对照（含控制组先证明装置可用）

| 组 | 场景内容 | 音频流 | 编码 | mean / max | 判定 |
|---|---|---|---|---|---|
| **控制组** | 仅 `ffmpeg_source` → `tone.wav` | 1 | aac / 2ch | **−7.5 / −4.1 dB** | 录制管线**可承载音频** ✅ |
| **Case A** `reroute_audio=false` | 仅 `browser_source` → 测试页 | 1 | aac / 2ch | **−91.0 / −91.0 dB** | **数字静音**（不进混音链） |
| **Case B** `reroute_audio=true` | 同上 | 1 | aac / 2ch | **−7.5 / −3.0 dB** | **正常音频** ✅ |

**判据链**：控制组有声（−7.5 dB）⇒ 装置可用；随后 Case A 与 Case B **同装置、同页面、同码率**，
唯一差异是 `reroute_audio` 一个布尔值 ⇒ 结论**唯一归因于该开关**（不是「没播」也不是「串音」）。
（若控制组无声，本实验判 **INCONCLUSIVE**；本设计内置此判据，未触发。）

⇒ **`{"reroute_false": "SILENT", "reroute_true": "PASS"}`**；
`reroute_audio=true` 是**硬性环境要求**（§4.6）。

**OBS 运行环境（实测）**：OBS **31.0.2** · obs-websocket **5.5.5** · CEF `chromium-127.0.6533.120`；
输入设置 `{"width": 540, "height": 960, "fps": 30, "shutdown": false, "restart_when_active": false, "reroute_audio": true}`。

> ⚠️ **电平取证口径**：obs-websocket 5.5.5 **无音频电平查询接口** ⇒ 电平的权威证据取
> **「录制输出混音轨的 `volumedetect` dB」**——它是混音链**末端**的真实产物，强于 UI 电平表截图。

### 3.4 `seq` 机制性证明（本 CR 的核心，含负对照）

问题：`{pet_id, action, audio_url}` 在**同动作连续触发**时**逐字段相同** ⇒ 前端若按「内容」或「action」去重，**第二次必被吞掉**。

| 模式 | `seq=1`（heart） | `seq=2`（heart） | `playCount` | `stopCount` | `currentTime` | 判定 |
|---|---|---|---|---|---|---|
| **`seq` 模式**（采纳） | `PLAY` | **`STOP`+`PLAY`** | 1 → **2** | 0 → **1** | 1.157 → **1.155**（复位重放） | **PASS** |
| **按 `action` 去重**（负对照） | `PLAY` | **`SKIP`** | **1**（未增） | **0** | 1.138 → **2.352**（继续播，未重放） | **CONFIRMED（会漏播）** |

**抢占测试**（`heart seq=3` → 立即 `happy seq=4`）：`STOP`+`PLAY`，`currentTime` 1.457 → **0.338**（新音频从头），`stopCount = 1` ⇒ **PASS**。

**其他生命周期实测**：
- **自然结束**：`ended=true`，`stopCount = 0`（不产生多余外部停止）⇒ PASS。
- **非 `playback_audio` 帧**（如 `playback_state` / WM-1 envelope）：`playCount = 0`，全部 `IGNORE` ⇒ PASS。

⇒ **`{"seq_replay": "PASS", "interrupt": "PASS"}`**；
并**机制性证明**：`seq` 单调递增序号是**必需**的，缺它则「同动作连触两次」必然漏播第二次。

### 3.5 可行性结论

| 场景 | 可听性 | 条件 |
|---|---|---|
| **OBS 直播（主场景 · 产品目标）** | **✅ 可行** | `browser_source` + **`reroute_audio=true`**（硬性要求） |
| **浏览器直接预览（dev / 调试）** | **⚠️ 默认不可听** | 需**用户手势**解锁一次 ⇒ `NotAllowedError` **必须被捕获**并静默降级 |

### 3.6 OBS 装置就绪闸门（稳定性经验，非本 CR 缺陷）

`obs-websocket` 可在 **OBS 完全就绪之前**完成握手，但此时**所有请求返回空响应**
（`GetVersion.responseData = {}`），叠加 `obs.req()` **吞掉 `requestStatus`** ⇒ `CreateInput` **静默失败**、`GetSceneItemList = []`。

⇒ **本 CR 沿用既有纪律**：轮询 `GetVersion.obsVersion` 作**就绪闸门** + 写操作走 `ok()` + **场景项计数闸门** + **唯一命名**。
**属装置侧注意事项，不是项目缺陷**（登记项 **G1** 同源）。

---

## 四、新契约（Contract）

### 4.1 数据模型 —— 方案 A：`assets` 增加 `audio_path TEXT NULL`

```
pet_type | action | path                        | audio_path                                | duration
cat      | heart  | assets/pets/.../heart.webm  | assets/pets/cat/actions/heart/heart.ogg   | 4459
cat      | happy  | assets/pets/.../happy.webm  | assets/pets/cat/actions/happy/happy.ogg   | 4459
cat      | idle   | assets/pets/.../idle.webm   | (NULL)                                    | 4459
```

| 保留不变 | 说明 |
|---|---|
| `UNIQUE(pet_type, action)` | **不变** —— 一个动作 = 一个视觉资产；音频是**附属产物**，非独立资产 |
| 既有查询 / 索引 / 唯一约束语义 | **不变** |
| `AssetManager` 对外方法签名 | **不变**（仅新增**可选**参数） |

**淘汰的方案**：

| 方案 | 内容 | 判定 |
|---|---|---|
| **B** | 引入 `asset_kind`（visual / audio） | **淘汰（范围扩大）**：需改 `UNIQUE(pet_type, action)` → `(pet_type, action, kind)`、改全部查询/映射/索引，并使 `AssetManager` 从「动作解析器」降级为「带 kind 的二维查询」；第一阶段收益**为零**，代价是**动摇 CR-9 已验收的资产语义** |
| **C** | 前端按同名规则推导 `.ogg` | **直接淘汰（违规）**：违反 **RB-2**（禁拼路径 + 禁判类型），同时犯两条 |

**`upsert` 语义裁决 = 全量覆盖**（`audio_path = excluded.audio_path`，未提供即写 `NULL`）：

- 理由：与 CR-9「**显式映射即事实**」一致、**可预测**、`seed` 结果 == 文件系统；
- **不采用 `COALESCE` 保留旧值**：会使 `--reset` 与普通运行的**清空语义不一致**，
  并产生「DB 指向磁盘上已不存在的音频」的**隐性陈旧引用**。

### 4.2 素材登记 —— 显式映射，禁止扫描

新增 `AUDIO_ACTIONS` **显式映射**（形如 `{"cat": {"heart": "heart.ogg", "happy": "happy.ogg"}}`），
与既有 `ALPHA_ACTIONS` **同构**：**命中映射且文件存在**才登记；**禁止**扫目录 / glob / 后缀猜测（CR-9 纪律原样沿用）。

### 4.3 推送契约 —— 新增第三类入站帧 `playback_audio`

```json
{
  "type": "playback_audio",
  "pet_id": "cat_001",
  "action": "heart",
  "audio_url": "/assets/pets/cat/actions/heart/heart.ogg",
  "seq": 1
}
```

| 项 | 规格 |
|---|---|
| 帧型判别 | `type = "playback_audio"` —— 与 `playback_state`、WM-1 envelope **三者互斥** |
| 载荷字段 | **`{pet_id, action, audio_url, seq}`**（4 字段，`extra="forbid"`） |
| `pet_id` | **对外主键口径 = `cat_001`**（与 `playback_state` 帧、DB `events.pet_id` **同源同口径**）；`cat` 是 `pet_type` |
| `audio_url` | **由后端产出**，沿用 `to_asset_url()`；前端**永不**拼接（RB-2 / UI-6） |
| `seq` | **每次触发单调递增**；**不参与状态帧去重**，也不与 `playback_state` 共享序号空间语义 |
| 触发语义 | **边缘触发** —— 动作被**受理**时各下发一次（**同 action 连续触发 ⇒ 下发两次**） |
| 不下发条件 | `audio_url` 为空（如 `idle`、未登记音频、LAB 未启用）⇒ **不下发**（不进队列、不报错） |
| 后端落点 | `backend/app/api/ws.py`（与状态帧**同一连接**，但**独立发送路径**，**不得**混入状态帧去重逻辑） |

**不影响的既有契约（逐条声明）**：
`PlaybackState` **7 字段逐字不变**（API-2 v1.1）· `PLAYBACK_STATE_KEYS` **7 键不变** ·
WM-1 envelope **恰 4 字段不变** · `GET /api/playback/state` 响应体不变 · WP-3 v1.1 出站两类不变 ·
`AssetMetadata.to_dict()` **恰 3 字段不变**。

### 4.4 前端播放位置 —— 独立非可视模块（绕开 FP-2 / FP-3 / FP-4 / FCM-4）

| 约束（冻结） | 内容 | 对音效的影响 |
|---|---|---|
| **FP-3** | 属性白名单 = `src / autoplay / muted / playsInline / controls={false} / preload / loop` | **不含 `<audio>`** ⇒ 在 `PetPlayer` 内加 `<audio>` 属契约变更 |
| **FP-4** | 播放器**禁止**内部 `useState` / `useEffect` / `ref` / 回写 `currentTime` | 音频需**命令式** `play()` ⇒ 与 FP-4 天然冲突 |
| **FCM-4** | 白名单**仅**文本 / 图片 URL / className，**禁自建播放器** | 豁免范围**不外溢**到其他组件 |
| **PC-4** | socket 回调**禁止**直写组件状态，**必须经 store** | 播放器**不能**直接挂在 push 回调上 |

**裁决：音效**不放** `PetPlayer`**，由**独立非可视模块**承载：

1. **新增** `frontend/src/services/playbackAudio.ts`（**非 React**）——
   持有单个 `Audio` 实例 + `play(url, action)` / `stop()`；
   ⛔ **全部 `play()` 的 rejection 必须捕获并静默降级**（`NotAllowedError` **不得**冒泡、**不得**影响播放链路）。
2. **store 增** `lastAudio: {pet_id, action, audio_url, seq} | null`（`seq` **单调递增**）。
   ⛔ **`seq` 是必需的**：见 §3.4 —— 无单调序号则 React 订阅层无法区分「两次触发」，第二次丢失。
3. **新增** `frontend/src/hooks/usePlaybackAudio.ts` —— 订阅 store 的 `lastAudio`，**`seq` 变化**时调用
   `playbackAudio.stop()` + `playbackAudio.play(...)`；**`PetPlayer` 零改动**。
4. **解锁入口**：提供一个用户手势入口（如「🔊 启用音效」按钮，或复用首次任意点击）解锁音频通道；
   **OBS 场景无需此步骤**（CEF 已放行，§3.2）。

**推送接线**：`types/push.ts`（新常量 + 类型）· `services/websocketClient.ts`（**新增第三分支**，保持三者互斥）·
`hooks/useRuntimePush.ts`（新增 `onAudio` 接线，经 store 写入）。

> ⚠️ 该设计**触及前端冻结决策的边界**（新增 store 字段 + 新增 hook + 新增 service），
> 虽不改 `PetPlayer` 本身，但**必须**在 CR 中显式声明并获授权；不能以「不属于 player 组件」为由自行认定无需 CR。

### 4.5 生命周期规则（冻结 · 5 条）

| # | 场景 | 行为 |
|---|---|---|
| 1 | **新动作到达** | `stop` 旧音效 → `play` 新音效 |
| 2 | **动作被打断** | `stop`；被丢弃的动作**不播放** |
| 3 | **音效短于动画** | 音效自然结束，**不影响视频** |
| 4 | **音效长于动画** | 动画结束，**音效继续直到结束**（不随动画截断） |
| 5 | **总则** | **音频是视觉的伴随事件，不成为主时钟** —— 视觉仍由 `PlaybackManager` **唯一控制** |

**补充口径**：`seq` 变化即视为「新动作到达」⇒ `stop` 旧 + `play` 新；
**同 `action` 不同 `seq` 必须重新播放**（§3.4 已证明按 action 去重会漏播）。

### 4.6 OBS 环境要求（硬性）

| 项 | 要求 |
|---|---|
| 源类型 | `browser_source`（CEF） |
| **`reroute_audio`** | **必须 `true`** —— 实测 `false` ⇒ **−91.0 dB（数字静音，不进 OBS 混音链）**；`true` ⇒ **−7.5 dB（进入）** |
| `restart_when_active` | **必须 `false`**（既有纪律） |
| 无手势播放 | **OBS CEF 已放行**（实测 `play: OK` / `advanced: true`，`userActivation` 全程 `false`） |

完整运行约束（含就绪闸门、预热、唯一命名）见 **`docs/development/phase4_audio_obs_requirement.md`**。

### 4.7 不变项（本 CR 明确不改）

| 项 | 状态 |
|---|---|
| `PlaybackState` | **7 字段逐字不变**（API-2 v1.1） |
| `AssetMetadata.to_dict()` | **恰 3 字段**（`asset_id` / `asset_path` / `duration`）不变 |
| `UNIQUE(pet_type, action)` | **保留**（不引入 `asset_kind`） |
| `PetPlayer.tsx` | **零 diff** |
| WM-1 envelope / 状态帧 / HTTP 契约 | **零改动** |
| 既有 mp4 资产（15 个） | **保留**（不删除、不替换） |
| webm alpha 三资产 | **保留**（tag `v1.0-webm-alpha-assets` 不动） |
| `sad / surprise / dog / panda` | **零改动** |
| `migrations` 目录 | **不新增**（迁移落在 `db.py::initialize()`） |

---

## 五、影响模块

| # | 模块 | 改动 | ⛔ 不可遗漏点 |
|---|---|---|---|
| 1 | `database/schema.sql` | `assets` 建表语句加 `audio_path TEXT`（**可空，无默认**） | **仅改这里不够**：`CREATE TABLE IF NOT EXISTS` 对**已存在**的表**不加列** |
| 2 | `backend/app/repositories/db.py` | `initialize()` 在 `executescript` **之后**追加**幂等**列迁移：查 `PRAGMA table_info(assets)`，缺 `audio_path` 则 `ALTER TABLE assets ADD COLUMN audio_path TEXT` | 仓库**无 migrations 目录** ⇒ 迁移只能落在此处；属「建表/结构」范畴，**未越 `db.py` 边界**；必须**重复调用幂等**；**禁止 `DROP` / 重建表** |
| 3 | `backend/app/repositories/asset_repository.py` | `_COLUMNS` 加 `audio_path`；`_row_to_record` 补映射；`upsert` 的 INSERT 列 + `ON CONFLICT DO UPDATE SET` 加 `audio_path = excluded.audio_path` | **全量覆盖**（未提供 ⇒ 写 `NULL`），已在 §4.1 声明 |
| 4 | `backend/app/models/asset.py` | `AssetRecord` 加 `audio_path: str \| None = None`（**必须有默认值**，否则破坏既有构造点）；`AssetMetadata` 加 `audio_path`；`to_dict()` **保持 3 字段逐字不变**；`to_detail_dict()` 加 `audio_path` | `AssetMetadata` 是 `frozen` dataclass ⇒ 加字段会**连带修改所有构造点**；`to_dict()` 是冻结的对外 3 字段契约，**不得**因音频而增字段 |
| 5 | `backend/app/services/asset_manager.py` | `register()` 加**可选**参 `audio_path: str \| None = None`；**不**新增音频文件存在性校验 | 与既有「登记是**声明**行为，文件允许后补」一致；`register()` 既有位置参数**不得**移位（`init_assets.py` 与测试大量调用） |
| 6 | `backend/scripts/init_assets.py` | 新增 `AUDIO_ACTIONS` 显式映射；`iter_seed_targets` 产出增加音频列；`seed()` 透传；`SeedReport` 加 `audio` 明细 | 必须与 `ALPHA_ACTIONS` 同构；**命中映射且文件存在**才登记；**禁止**扫目录 / glob / 后缀猜测 |
| 7 | `backend/app/api/ws.py` | 新增 `playback_audio` **边缘触发**发送路径 + 契约常量 | **不得**改 `PlaybackState` / 状态帧去重 / WM-1 envelope |
| 8 | `frontend/src/types/push.ts` · `services/websocketClient.ts` · `hooks/useRuntimePush.ts` | 新帧常量 + 类型 + **第三分支** + `onAudio` 接线 | 三类帧**互斥**，**不得**回退解析 |
| 9 | `frontend/src/store/**` | 增 `lastAudio: {pet_id, action, audio_url, seq} \| null` | 经 store 写入（**PC-4**） |
| 10 | `frontend/src/services/playbackAudio.ts` · `hooks/usePlaybackAudio.ts` | **新增 2 文件** | 非 React + 捕获 rejection 静默降级 |
| 11 | `backend/tests/**` · `frontend/src/**/__tests__/**` | 新增/更新测试（见 §七） | 后端基准 **605 passed** / 前端 **166 用例** 必须保持或**单调增加**，且 `safe_delete=False` |
| 12 | `docs/change_request/cr-11_audio_feedback_design.md` | **本文件**（新增） | —— |
| 13 | `docs/development/phase4_audio_obs_requirement.md` | **新增**（OBS 音频环境要求） | —— |
| 14 | `backend/app/main.py` · `PetPlayer.tsx` · `asset_manager` 公开签名 · mp4/webm 资产 · `sad/surprise/dog/panda` | **零改动** | —— |

**架构合规**：
- SQL 仍**仅**存在于 `app/repositories/**` + `services/data_manager.py`（新增列映射在 repository 内）；
- 素材选择仍属 **seed 脚本层**（`backend/scripts/**`），**不进入** `app/services/**`；`AssetManager` 仍只消费「显式传入的 path」；
- 新增 `playback_audio` 帧**不改** `normalize` / `EventGateway` / `ActionEngine` 的既有唯一 Owner 关系（它是**出站**帧，不入站）。
⇒ **未越层、未破坏既有边界。**

---

## 六、是否影响 MVP 范围

**属于 MVP 范围内的功能补齐（不是范围扩大）**：
- 音效是 MVP 原始目标之一，本 CR **补齐既有缺口**；
- **不新增/删除**任何动作、事件类型、API 端点或 `PlaybackState` 字段；`ALLOWED_ACTIONS` 仍**恰 5 个**；
- **不改** `sad / surprise / dog / panda` 的既有行为；
- 新增的是一类**出站推送帧**（`playback_audio`），与既有 `playback_state` / WM-1 envelope **互斥并存**，不影响既有消费者。

**DB 与 schema 会变更**（新增 1 列），不变量「业务 schema 逐列 == `schema.sql`」**仍然成立**（列集一致即可）；
本 CR **显式允许** `database/schema.sql` 与 DB 文件变更 —— 这与 3-RELEASE-EXECUTION 阶段「禁 schema change」**不冲突**（那是**上一阶段**的禁止项）。

---

## 七、验证方案

| # | 项 | 判据 |
|---|---|---|
| 1 | **静态守卫** | 后端静态守卫脚本全 `ok: true`（`api/**` 不 import 引擎、无越层 SQL 等） |
| 2 | **后端全量回归（提交前）** | `N passed / 0 failed / 0 errors` + `safe_delete=False`；基准 **605** 保持或单调增加 |
| 3 | **前端测试** | 基准 **15 文件 / 166 用例** 保持或单调增加 |
| 4 | **迁移幂等** | 对**既有** DB 重复执行 `initialize()`：首次加列成功，第二次**不报错、不重复加列**；`PRAGMA table_info(assets)` 含 `audio_path` |
| 5 | **CRUD 往返** | `upsert(audio_path=...)` → `find` 读回一致；未提供音频 ⇒ `NULL`（**全量覆盖**语义） |
| 6 | **`to_dict()` 不变** | 恰 3 字段，**不含** `audio_path` |
| 7 | **`playback_audio` 事件** | `heart` 受理 ⇒ 下发 1 帧；**同 action 连触 2 次 ⇒ 帧数 2**（证明未被去重吞掉）；`seq` **严格递增**；`idle` **不下发** |
| 8 | **既有契约不受影响** | `playback_state` 帧仍恰 7 字段；WM-1 envelope 仍恰 4 字段；`GET /api/playback/state` 响应体不变 |
| 9 | **前端 seq replay** | `seq` 变化 ⇒ `stop` 旧 + `play` 新；**同 action 不同 seq 重新播放**（§3.4 复现） |
| 10 | **前端 interrupt** | `heart → happy` ⇒ `STOP`+`PLAY`，`stopCount` 递增 |
| 11 | **前端忽略非音频帧** | `playback_state` / WM-1 envelope ⇒ `playCount` 不增 |
| 12 | **`NotAllowedError` 降级** | 浏览器默认策略下 `play()` 被拒 ⇒ **静默**，不抛错、不影响视频链路 |
| 13 | **`PetPlayer` 零 diff** | `git diff --stat` 不含 `PetPlayer.tsx` |
| 14 | **OBS 运行验收（LAB）** | 控制组有声（≈ −7.5 dB）；`reroute_audio=true` ⇒ 有音频（≈ −7.5 dB）；`=false` ⇒ 数字静音（−91.0 dB） |

---

## 八、实施与交付记录（2026-10-07）

> ⚠️ 本 CR **第一阶段不提交正式音频素材**（owner 裁决：**只验证管线**，音频源用 LAB 临时文件）。
> ⇒ `audio_path` 在正式运行中**全部为 `NULL`** ⇒ 后端**不下发** `playback_audio` 帧（符合 §4.3「不下发条件」）；
> 链路验证通过**注入等价帧**完成（§3.4）。**正式音频资产另立 CR / 另行授权**。

| 步 | 内容 | 验收标准 |
|---|---|---|
| **CR-11-1** | 数据层：`schema.sql` + `db.py` 幂等迁移 + `asset_repository` + `models/asset`（音频全 `NULL` 时行为**逐字不变**） | 605 passed 保持；真实 DB 加列成功且启动幂等；`to_dict()` 不含新字段 |
| **CR-11-2** | Seed 层：`AUDIO_ACTIONS` 显式映射 + `iter_seed_targets` / `seed` + `SeedReport` + 测试 | 幂等；无音频文件时**不登记且不报错**；alpha / audio 两映射互不干扰 |
| **CR-11-3** | 资产产出：`cat/heart.ogg`、`cat/happy.ogg`（+ SHA-256 + manifest） | **本阶段推迟**（owner 裁决 `D6 = 只验证管线`） |
| **CR-11-4** | 后端下发：`playback_audio` 帧（边缘触发）+ 契约测试 | 同动作连触 2 次 ⇒ 帧数 **2**；`idle` 不下发；WM-1 envelope 与状态帧**不受影响** |
| **CR-11-5** | 前端：`playbackAudio.ts` + `usePlaybackAudio` + store `lastAudio` + 解锁交互 + OBS 回归闸门 | `PetPlayer` 零 diff；`NotAllowedError` 静默降级 |

---

## 九、裁决记录（D1–D7 · 2026-10-07）

| # | 议题 | 结论 |
|---|---|---|
| **D1** | 设计文档入库 | **YES** —— 新增本文件；**不改**已有冻结文档；**不动** tag `v1.0-webm-alpha-assets`；产生新 commit |
| **D2** | 数据模型 | `assets.audio_path TEXT NULL`（**方案 A**）；`upsert` 采用 **全量覆盖**（未提供 ⇒ `NULL`，**非** `COALESCE`） |
| **D3** | API 契约 | 新增 `playback_audio` 帧（不修改 `PlaybackState`）；⚠️ **两处修正**：`pet_id` 口径 = **`cat_001`**（非 `cat`）、`audio_url` **必须**为 `/assets/pets/...`（`/assets/audio/**` 必然 404，见 §一） |
| **D4** | 前端边界 | `PetPlayer` **untouched**；新增 `services/playbackAudio.ts` + `hooks/usePlaybackAudio.ts` + store `lastAudio` |
| **D5** | 生命周期 | **冻结 5 条**，见 §4.5 | 
| **D6** | 音频资产 | **只实现管线，不提交音频**（LAB 临时源验证；正式资产另行授权） |
| **D7** | OBS 环境 | `reroute_audio = true` **硬性要求**，写入 `docs/development/phase4_audio_obs_requirement.md`；实测 `false = −91.0 dB` / `true = −7.5 dB` |

**评审期间已被修正的提案（留痕）**：
- 提案 `pet_id = "cat"` ⇒ 改为 **`cat_001`**（对外主键口径，与 `playback_state` 帧 / DB `events.pet_id` 一致）；
- 提案 `audio_url = "/assets/audio/cat/heart.ogg"` ⇒ 改为 **`/assets/pets/cat/actions/heart/heart.ogg`**（静态挂载限制）；
- 提案 `upsert = COALESCE` ⇒ 改为 **全量覆盖**（清空语义一致性）；
- 提案 `D6 = C（不提交音频）` 与「Step 6 需实测 OBS 音频」存在张力 ⇒ 以 **LAB 临时音频 + 注入等价帧** 解耦（见 §八 前言）。

---

## 十、与既有登记项的关系

| 登记项 | 关系 |
|---|---|
| **F1 / CR-10** | README 启动命令修正 —— **独立事项**，本 CR **不**顺带处理 |
| **F2** | `rules.json` 无 `sad/surprise` 规则 —— 本 CR「暂不覆盖 sad/surprise」与之一致，**不扩大** |
| **G1 / F3** | OBS 装置脆弱点（`CreateInput` 静默失败、`Untitled.json` 跨运行持久）—— 本 CR 按既有纪律处理（就绪闸门 + 唯一命名 + 启动清理），**未新增**缺陷 |
| **方法论沉淀** | ① 复用 `p31_common.launch_chrome()` 会让任何「默认策略」音频实验**失真** ⇒ 同类实验**必须**独立 launcher；② `obs-websocket` 未就绪时请求返回空响应 ⇒ **必须**以 `GetVersion.obsVersion` 作就绪闸门 |
| **P0 远端同步** | 仍 `BLOCKED`（`BLOCKER = REMOTE_URL` 未提供），与本 CR **互不阻塞** |
| **MP-4 / `events.pet_id`** | 既往「`events.pet_id` 恒 NULL」表述**有误**：实读 `mode=ro` 为 **`cat_001`（789/789 非 NULL）**；本 CR 的 `pet_id` 口径与之对齐 |

---

## 变更历史

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.0 | 2026-10-07 | 首次立档（设计评审 → 实施）。范围冻结：**cat `heart` / `happy` 有声**，`idle` 静音，`sad/surprise/dog/panda` 暂不覆盖。数据模型裁决 **方案 A**（`audio_path TEXT NULL`，`upsert` **全量覆盖**，`UNIQUE(pet_type, action)` 保留）。API 契约裁决 **新增第三类入站帧 `playback_audio`**（保持 `PlaybackState` 7 字段不动）—— 决定性理由：状态帧为**电平触发 + 变化去重**，承载音效会**漏播同动作的第二次触发**（§3.4 负对照已机制性证明）。前端裁决 **独立非可视模块**（`playbackAudio.ts` + `usePlaybackAudio.ts` + store `lastAudio{seq}`，`PetPlayer` 零改动）。OBS 裁决 **`reroute_audio=true` 硬性要求**。基准：`f0a37d2` / tag `v1.0-webm-alpha-assets` / 后端 605 passed / 前端 166 用例。 |
