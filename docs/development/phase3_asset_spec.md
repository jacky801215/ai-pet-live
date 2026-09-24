# 宠物动作素材规格（v0.3 DRAFT）

> **状态**：**v0.3 DRAFT · 非冻结** —— **不属 v1.0 冻结条款集**，**未在 `PROJECT_RULES.md` §十四 登记**；条款化需另行走 CR。
> **依据**：仓库实测（2026-09-23，HEAD `96f13e9`）—— 路径 / 动作集 / 命名 / `config.json` 字段 / `rules.json` 映射 / `assets` 表结构 **均为实测值，非推断**。
> **取证脚本**：`tmp/asset_spec_precheck.py` · `tmp/asset_git_probe.py`（`tmp/` 已被 gitignore）
> **owner 已裁决（2026-09-23）**：§二 时长与循环 · §四 分辨率 · §五 编码 —— **采纳本文建议**；**启用范围 = 先定稿规格、暂不接入**（素材未就位前不动运行库与前端）。
> **owner 已裁决（2026-09-23 · Q1-D）**：**Phase 1 素材制作范围收窄为 `idle` / `heart` / `happy` 三个动作**；`sad` / `surprise` 标为 **Phase 2 待定 · 暂不制作**（新增 **§2.1**）。⚠️ **动作域**（`config.json.actions` / `ALLOWED_ACTIONS`）**仍恰 5 个，不变**。同时**暂停「补 `sad`/`surprise` 规则」任务**。
> **owner 已裁决（2026-09-24）**：真实猫咪素材交付后 —— **① 按实测更新规格**（§四 分辨率 → **720×1280 竖屏**；§五 帧率 → **24 fps**；§二 时长 → **4.48 s**）；**② 保留音轨**（素材含 1 条 AAC；前端 `<video muted>` 使其当前**不播放**）。

---

## 一、文件路径规范（仓库实证）

```
assets/pets/<pet_type>/actions/<action>/<action>.mp4
assets/pets/<pet_type>/config.json
assets/pets/<pet_type>/images/     （预留，当前均不存在）
assets/pets/<pet_type>/sounds/     （预留，当前均不存在）
```

⛔ **不得偏离此结构**：`init_assets.iter_seed_targets()` 按
`f"assets/pets/{pet_type}/actions/{action}/{action}{ACTION_ASSET_SUFFIX}"` 拼接路径，`AssetManager` 亦按此扫描。

实测：`assets/pets/{cat,dog,panda}` 各含 5 个动作目录（各含 1 个 mp4）+ 1 个 `config.json`；**均无** `images/` / `sounds/` 目录。

---

## 二、动作集与制作范围（owner 已确认）

| 动作 | 语义 | 时长（交付实测） | 循环 | 触发（实测见 §三） | Phase 1 状态 |
|---|---|---|---|---|---|
| `idle` | 待机 | **4.48 s** | **循环** | 默认 / 无事件 | ✅ **必需** |
| `heart` | 打赏/点赞反应 | **4.48 s** | 单次 | `gift` | ✅ **必需** |
| `happy` | 开心 | **4.48 s** | 单次 | `like`（`like_count >= 3`） | ✅ **必需** |
| `sad` | 难过 | —（Phase 2） | 单次 | ⛔ 当前无触发 | ⏸ **Phase 2 待定** |
| `surprise` | 惊讶 | —（Phase 2） | 单次 | ⛔ 当前无触发 | ⏸ **Phase 2 待定** |

- **时长实测交付值 = 4.48 s / 107 帧 @24 fps**（`idle` / `heart` / `happy` **三者一致**）。
  ⚠️ 原建议值（`idle` 2~4 s · 反应类 1~2 s **单次**）已按 owner 裁决「**按实测更新规格**」**取代**。
- ⚠️ **时长驱动状态机回落**：`AssetManager` 提供 `duration`，写入 DB `assets.duration`（**现为 4480 ms**）⇒ 反应动作会持续约 4.5 s。
- ⚠️ **`idle` 的「循环」在前端当前不可实现**：`step4_frontend_player_decision.md` **FP-3（冻结）** 的 `<video>` 属性白名单（`src`/`autoplay`/`muted`/`playsInline`/`controls={false}`/`preload`）**不含 `loop`**，且 FP-4 禁 `onEnded` ⇒ 播完**定格末帧**。改动须走 CR。

- ⚠️ **动作域 = 后端 `ALLOWED_ACTIONS`（恰 5 个），不得增删**；增删须同步改后端常量与三处 `config.json`。
  本表「必需 / Phase 2 待定」划分的是 **Phase 1 的素材制作达标范围**，**不是动作域本身**（域仍 5 个，见 §2.1）。
- 建议：`idle` 支持无缝循环；反应类动作**首尾帧接近 `idle`**，便于状态机恢复。
- 占位素材实测 `mvhd` timescale/duration = 1000/1000 ⇒ **恰 1.000 s**（`ffprobe` 亦报 `duration=1.000000`）。⚠️ 截至 v0.3，真实素材已接入 `cat` 的 `idle`/`heart`/`happy`；仍为占位的是 `sad`/`surprise` 与 dog/panda 全套。

### 2.1 动作集缩减说明（owner 裁决，2026-09-23 · Q1-D）

Phase 1 **只要求 `idle` / `heart` / `happy` 三个动作可达**。

理由：

- `heart` 由 `gift` 事件触发（规则已存在：`gift_heart`）。
- `happy` 由 `like` 事件触发（规则已存在：`like_dance`）。
- `idle` 为默认兜底（无事件 / 反应结束回落）。
- `sad` / `surprise` 在 Phase 1 内**无生产者事件**：
  - `system` 事件**无任何生产者**（前端模拟器仅 `gift` / `comment` / `like`，请求体固定 `payload: {}`）⇒ 即便补 `system → surprise` 规则也是**死规则**；
  - 且 `step2_event_schema.md` 已定 `system` 命令「**仅 `startup` 类**」，而「用户进入（进场）」的同义语义 `follow` 已在事件契约 **v1.1 被明确移除**（C6 + §6.5）；
  - 挂到 `comment`（含词）或特定 `gift_name` 语义牵强，且会打破既有锁定测试。
  ⇒ **暂不追求可达**；等真实平台事件接入后再定其触发条件（届时须走 CR）。

**素材生产范围**：`dog` / `panda` 只需制作 **`idle` / `heart` / `happy` 三个动作**；`sad` / `surprise` **暂不制作**。现有 5 个占位目录**保留不动**（不删除）。

---

## 三、动作映射（**实测更正**）

`backend/app/config/rules.json` 实际**仅 2 条规则 + 1 条兜底**：

| id | event_type | match | → action | priority |
|---|---|---|---|---|
| `gift_heart` | `gift` | `payload.gift_name` **eq** `"小心心"` | **`heart`** | 50 |
| `like_dance` | `like` | `payload.like_count` **gte** `3` | **`happy`** | 50 |

`defaults` = `{"gift": "heart"}`；`ALLOWED_EVENT_TYPES` = `comment` / `gift` / `like` / `system`。

| 事件 | 结果 |
|---|---|
| `gift` | → **`heart`**（规则命中；`gift_name` 不匹配时由兜底给出同一动作） |
| `like` | `like_count >= 3` → **`happy`**；否则 → `None`（**无动作**） |
| `comment` / `system` | → `None` |

⛔ **关键更正**：`sad` 与 `surprise` **无任何规则或兜底引用它们 ⇒ 当前完全不可达**（永不触发）。

⇒ **制作范围（Phase 1）**：只做 ① `idle` → ② `heart` → ③ `happy`（**必需**）；`sad` / `surprise` 标为 **Phase 2 待定 · 暂不制作** —— 二者在 Phase 1 内**无生产者事件**，补规则也是死规则（详见 **§2.1**）。

（既定锁定：`tests/test_websocket_endpoint.py` 断言 `gift → heart`，与实测一致 ✅）

---

## 四、分辨率（owner 已确认 · 2026-09-24 按实测更新）

- **720 × 1280（竖屏 9:16）**；宽高比须与最终输出一致，**避免拉伸**。
- **依据**：真实猫咪素材**实测交付值**（`idle` / `heart` / `happy` 三者一致）。原「1920 × 1080 横屏」是无真实素材时的预设值，已按 owner 裁决「**按实测更新规格**」取代 —— 本项目面向抖音 / YY 直播，**竖屏 9:16 为主流**。
- ⚠️ 前端 `frontend/src/` **全仓无 CSS**，且 `<video>` 未设 `width` / `height` ⇒ 浏览器按**固有尺寸**渲染，实际观感须本地确认。
- 若后续改走「宠物作为独立图层合成」，则 §五 编码需相应调整（alpha 见 §五 备注）。

---

## 五、编码格式（owner 已确认）

| 项 | 取值 |
|---|---|
| 容器 | **mp4** |
| 视频编码 | **H.264（libx264）** |
| 像素格式 | **yuv420p** |
| 帧率 | **24 fps**（实测交付值） |
| 音频 | **保留音轨**（素材含 1 条 `aac`） |
| faststart | **启用**（moov 前置，便于边下边播） |

- 理由：`AssetManager.register()` 统一经 `ffprobe` 读真实时长 ⇒ mp4 兼容性最好；浏览器与推流对 H.264 + yuv420p 支持最广。
- ⚠️ **音轨当前不会被播放**：`PetPlayer` 的 `<video>` **硬编码 `muted`**，且 **FP-3 属性白名单不含 audio 相关** ⇒ 音轨为**惰性**（Phase 1 无行为影响）。「播放音效」若要落地，须在 Phase 2/3 走 CR 修订播放层契约（`step4_frontend_player_decision.md` FP-3）。
- **备注（当前不采用）**：若要透明背景，mp4 / H.264 **不支持 alpha**，需改 webm/VP9 或 HEVC alpha，并须同步评估播放层能力后再另行授权。

---

## 六、命名规范（仓库实证）

- 文件名必须与动作目录名一致：`<action>/<action>.mp4`
- **全小写 · 无空格 · 无下划线变体**
- ✅ `heart/heart.mp4` · ⛔ `Heart/Heart.MP4` · ⛔ `heart/heart_v2.mp4`

---

## 七、config.json 结构（**实测更正**）

实际字段（三宠物同构，224 / 224 / 228 B）：

```json
{
    "pet_id": "dog_001",
    "pet_type": "dog",
    "name": "旺财",
    "actions": ["idle", "heart", "happy", "sad", "surprise"],
    "default_action": "idle"
}
```

⚠️ **字段是 `name`，不是 `label`** —— `label` 是**前端** `frontend/src/config/pets.ts` 中 `AVAILABLE_PETS` 的字段名，**两者不同名，不得混用**。
⚠️ `pet_id` 必须与 `frontend/src/config/pets.ts` 的 `AVAILABLE_PETS` 条目**逐条对应**（**MPF-1** 冻结的 3 个 `pet_id` 逐字不变）。
⚠️ 新增宠物时**必须先读现有 `config.json` 逐字核对字段名**，不得凭记忆构造。

---

## 八、校验清单

- [ ] **Phase 1 必需动作**（`idle` / `heart` / `happy`）目录齐全，各含 `<action>.mp4`（`sad` / `surprise` 属 **Phase 2 待定**，本阶段**不作要求**）
- [ ] 文件名与目录名一致（全小写）
- [ ] `config.json` 字段与现有宠物同构（**`name`** 而非 `label`）
- [ ] `ffprobe` 能读取每个 mp4（否则 `AssetManager.register()` 抛错 → `init_assets` 记 skip）
- [ ] 文件大小合理（占位为 2451~2452 B；真实素材通常显著更大）
- [ ] 若替换占位：确认新素材与 cat 素材**不再逐字节相同**（实测 15 个占位 mp4 **去重后仅 5 份**）

### 8.1 `init_assets` 行为说明

`init_assets.py` 按 **`ALLOWED_ACTIONS`（恰 5 个）** 枚举 seed 目标（`iter_seed_targets()`），**不是**按磁盘实际目录枚举。
Phase 1 只要求 3 个动作（见 §二）⇒ 对缺失的 `sad` / `surprise`，`seed()` 捕获异常后计入 **`skipped`**，**不中断**整体流程（`init_assets.py:129-138`）。

- 示例：三只宠物各 3 个动作 ⇒ 输出 **`写入 9 / 跳过 6`**，**非失败**。
- 若跳过数**超出预期**，说明对应宠物的 **Phase 1 必需动作缺失**（见 §二 / §八 第 1 项），需排查。

---

## 九、接入流程（含实测约束）

1. **前置条件**（任一未满足 → STOP + 请裁决）：素材按本文就位 · `config.json` 就位 · `ffprobe` 全部可读 · owner 确认素材为**真实版本** · owner 确认**启用范围**。
2. **seed**：`cd backend && python -m scripts.init_assets --all`
   ⚠️ **实测约束**：脚本**只支持 `--all` / `--reset`，无按宠物参数**；`--all` = `('cat','dog','panda')` ⇒ **无法只 seed dog**，且会把 panda 一并入库。若要限定范围，只能 (a) 调用模块 API `seed(('cat','dog'))`（**不改任何代码**），或 (b) 给脚本新增 `--pet` 参数（**属生产代码改动，须新授权**）。
   ⛔ **禁止 `--reset`**（会 `delete_all()` **清空全表**）。
3. **提交对象（实测）**：`database/pet_live.db` 被 `.gitignore:44`（`*.db`）忽略、**不入库**；**真实素材的提交对象是 `assets/pets/<pet>/**`** —— 该目录**已被 git 跟踪**（当前 **18** 个文件 = 3 宠物 × (5 mp4 + 1 `config.json`)）。
4. **前端**：移除已启用宠物的 `placeholder: true`（`pet_id` 列表逐字不变，**MPF-1**）；同步处理 `tests/pet-placeholder/petPlaceholder.test.tsx`（全启用 ⇒ 删除该文件；部分启用 ⇒ 改写为「仅未启用宠物带 placeholder」）。`PetSelector` / `PetPlayer` **无需改代码**（提示仅在有 `placeholder` 的宠物被选中时出现）。
5. **回归**：后端 `pytest`（当前基准 **578 passed**）；前端**必须逐文件**跑（聚合 `vitest run` 在本环境不可用 —— 见 §十）。
6. **手动验证**：启动前后端 → 选宠物 → simulate → 观察动画。⚠️ **本沙箱无浏览器 / 无 jsdom 驱动 ⇒ 无法执行**，须由 owner 在本地终端完成。

---

## 十、环境限制（实测，影响复核口径）

- 前端**聚合** `npm test`（`vitest run`）在本环境**不可引用**：SSR transform 缓存的**异步**写入被 WorkBuddy 注入 node 的 FS broker shim 拒绝（`EPERM … \ssr\<hash>`；`dangerouslyDisableSandbox` 无效、`TEMP` 重定向亦无效）⇒ 每轮静默丢 2/13 个文件。**替代口径 = 逐文件** `npm test -- <file>`（全部 rc=0）。当前基线 **13 文件 / 123 用例 / 0 failed**。
- Bash shim 残缺（无 `head` / `dirname`，`cd` 可能报 null directory）⇒ 批量跑测试须用 **Python 脚本**，勿用 shell 循环。

---

## 十一、变更历史

| 版本 | 日期 | 说明 |
|---|---|---|
| v0.1 DRAFT | 2026-09-23 | 首次成文。基于 HEAD `96f13e9` 实测取证。**更正草案两处**：`config.json` 字段 `label` → **`name`**；动作映射中 `sad` / `surprise` 由「待核对」改为 **当前不可达**。**补充三项实测约束**：`init_assets` 无按宠物参数 · `database/pet_live.db` 被 gitignore · `assets/**` 已被跟踪（提交对象）。owner 裁决：时长 / 分辨率 / 编码 采纳建议，**启用范围 = 先定稿规格、暂不接入**。**非冻结，未登记 §十四。** |
| **v0.2 DRAFT** | 2026-09-23 | **动作集缩减**（owner 裁决 **Q1-D**，此前先经「`system` payload / 语义」只读核查）：Phase 1 只要求 `idle` / `heart` / `happy` 三个动作可达；`sad` / `surprise` 标为 **Phase 2 待定 · 暂不制作**（新增 **§2.1** 说明）。§二 表增「Phase 1 状态」列、§三「制作范围」、§八 校验清单第 1 项**同步收窄**。⚠️ **动作域（`config.json.actions` / `ALLOWED_ACTIONS`）不变（仍 5 个）**。同时**暂停「补 `sad`/`surprise` 规则」任务**；补 **§8.1 `init_assets` 行为说明**（skip 语义）。**非冻结，未登记 §十四。** |
| **v0.3 DRAFT** | 2026-09-24 | **按真实素材实测修订**（owner 裁决：① 按实测更新规格 ② 保留音轨）。§四 分辨率 `1920×1080 横屏` → **`720×1280 竖屏`**；§五 帧率 `30 fps` → **`24 fps`**、音频 `无音轨` → **保留音轨**（含 `aac`；前端 `muted` 故不播放）；§二 时长 → **`4.48 s`（交付实测）**。§二 另记明 **`idle` 循环在前端不可实现**（FP-3 冻结白名单无 `loop`，须 CR）。**非冻结，未登记 §十四。** |
