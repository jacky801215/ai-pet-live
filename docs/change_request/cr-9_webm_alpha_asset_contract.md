# CR-9：WebM（VP9）alpha 素材契约 —— 透明背景素材接入

> **类型**：资产契约扩展 / 素材格式
> **状态**：**已实施 · 待复核（IMPLEMENTED_PENDING_REVIEW）**（2026-10-05）—— 交付与验收记录见 §八
> **日期**：2026-10-05
> **提出背景**：Phase 2-1（透明背景）链路 —— owner 裁决 `D2_ROUTE=B`（离线抠像 → VP9-alpha WebM）、`AUTHORIZE_PHASE_2-1J=YES`
> **依据**：`PROJECT_RULES.md` §七（需求变更管理）
> **关联契约**：`docs/development/phase3_asset_spec.md`（**v0.3 DRAFT · 非冻结 · 未登记 §十四**）—— 本 CR 将其修订至 **v0.4**；其余冻结文档（`step4_api_contract_decision.md` / `step4_data_layer_decision.md` / `step4_frontend_player_decision.md` / `phase2_render_boundary_decision.md`）**零条款改动**

> ⚠️ **编号说明（v1.0 原文 · 逐字保留）**：`backend/app/repositories/db.py` 与 `backend/tests/test_data_manager.py` 的注释
> 曾以 **「CR-8」** 指代「连接复用」（提交 `fded328`，见 `cr-7_sqlite_wal_journal.md` §8.1 ④ 与 §8.3 登记）。
> 该笔**从未立档**（`docs/change_request/` 下不存在 `cr-8_*.md`），编号在 CR 登记序列中处于空位。
> 本 CR 按 owner 裁决（**O2=A**）占用 **CR-8** 编号。⇒ **代码注释中的「CR-8 = 连接复用」与本 CR 同号不同义**，
> 建议 owner 在 2-1J-4 复核时择一处置（① 保留本 CR-8、把连接复用注释改为「无编号 · 见 CR-7 §8.1④」；
> ② 令本 CR 改号为 CR-9）。**本 CR 不擅自改动 `db.py` 注释**（属未授权文件面）。

> ✅ **编号裁决（2026-10-05 · PHASE 2-1J-4 REVIEW · `CR_NUMBER_DECISION = CR-9`）**：
> 采纳**备选 ②** —— 本 CR **让号**，编号由 **CR-8 改为 CR-9**。理由：避免未来检索歧义（同一编号两种含义）。
> 事实占用方（`backend/app/repositories/db.py` · `backend/tests/test_data_manager.py` ·
> `backend/scripts/p2_7_local_acceptance.py` 的注释）**一律不改**（属历史、超出本 patch 授权面）。
> ⇒ **自本裁决起：`CR-8` 专指「连接复用」，`CR-9` 专指「WebM alpha 素材契约」。**
> 本次同步范围**仅限本 patch 自己新增**的产物：本文件名、本文件内自指编号、
> `docs/development/phase3_asset_spec.md` 内对外引用、以及 2-1J-3 新增的代码注释
> （`constants.py` / `init_assets.py` / `conftest.py`（仅 2-1J-3 新增两处）/ `test_asset_manager.py` /
> `test_init_assets_alpha.py`）。

---

## 一、需求描述

为 **透明背景（alpha）素材**建立显式契约：把已验收的 **WebM / VP9（`alpha_mode=1`）** 作为
**主选**素材格式，`mp4 / H.264` 保留为**回退（fallback）**；并明确「哪些角色 + 动作」使用 alpha 素材。

**变更原因**：**mp4 / H.264 不支持 alpha 通道**。当前真实猫咪素材的 `mp4` 画面内
**烘焙了不透明浅蓝底 + 地面软阴影 + 右下角「Pavo」水印**，直接推流会整块出现在直播画面上，
无法作为独立图层与背景合成（Phase 2-1 核心目标）。

**素材来源**：Phase 2-1J-2 实验产物（`p21j_lab/webm/`，仓库外），管线与验收见
工作区报告 `phase2_1j2_webm_generation_report.md`；本次按 §四 写入正式资产目录。

---

## 二、为什么需要

1. **渲染边界要求素材自身透明**：Phase 2-1 采用「素材即图层」路线（`D2_ROUTE=B`），
   抠像必须发生在**离线**环节 —— 运行期不做任何图像处理（`AssetManager` 零扫盘、前端禁判断素材类型，**RB-2**）。
2. **H.264 无法承载 alpha**：`mp4` 容器 + H.264 的色彩取样与解码路径不携带 alpha；
   改用 WebM/VP9 后 alpha 以**带外独立平面**存储，Chromium/CEF（OBS Browser Source）可直接解码。
3. **避免 `seed()` 静默回退**：`init_assets.seed()` 原按 `ACTION_ASSET_SUFFIX`（`.mp4`）拼路径并
   `UNIQUE(pet_type, action)` **upsert** ⇒ 若不改脚本，任何一次重跑都会把已指向 `webm` 的
   `assets.path` **静默覆盖回 `.mp4`**，透明背景将无声失效。
4. **把「格式选择」变成显式数据而非推断**：禁止扫目录 / glob / 后缀猜测 —— 那会让未来任意落盘的
   webm 静默生效，破坏 `sad` / `surprise` / dog / panda 的既有行为。

---

## 三、新契约（Contract）

### 3.1 主选（Primary）= alpha 素材

| 项 | 取值 |
|---|---|
| 容器 | **webm**（`matroska,webm`） |
| 视频编码 | **VP9**（`codec_name=vp9`） |
| alpha | **`alpha_mode=1`**（`stream_tags.alpha_mode`，带外独立平面） |
| 像素格式 | 编码侧 `-pix_fmt yuva420p`；⚠️ **探测侧主 stream 恒报 `pix_fmt=yuv420p`**（带外 alpha 的正常表现） |
| 分辨率 | **720 × 1280** |
| 帧率 | **24 fps** |
| 音轨 | **0 条**（`-an`） |

**验收判据（必须同时满足）**：`codec_name=vp9` **且** `stream_tags.alpha_mode=1`
**且** 720×1280 **且** `audio_streams=0`。
⛔ **不得以主字段 `pix_fmt=yuv420p` 判定失败**（VP9 带外 alpha 的正常表现；只有 FFV1 才报 `yuva420p`）。

**选择范围（显式映射，`ALPHA_ACTIONS`）**：

```
cat: idle / heart / happy      ⇒ 优先 webm（文件存在时）
其余（cat sad/surprise · dog/* · panda/* · 未来新角色） ⇒ 恒为 mp4
```

**编码管线（定稿）**：

```
colorkey=0xC3DCE9:0.08:0.03
  × 蓝优势掩码 (b−r) > 14 且 y > gate      （gate：idle 640 · heart 704 · happy 768）
  × 水印掩码 x[628,704] y[1216,1266]
  → libvpx-vp9 -pix_fmt yuva420p -b:v 0 -crf 18 -row-mt 1
               -auto-alt-ref 0 -deadline good -cpu-used 4 -an
```

⚠️ **gate 逐动作标定**：`happy` 若沿用 `y>640` 会**抠穿猫的双眼青蓝虹膜**（眼睛位于 y 658–757）⇒ 必须用 768。

### 3.2 回退（Fallback）= 兼容基线

| 项 | 取值 |
|---|---|
| 容器 | **mp4** |
| 视频编码 | **H.264（libx264）** |
| 像素格式 | **yuv420p**（**无 alpha**） |
| 常量 | `constants.ACTION_ASSET_SUFFIX = ".mp4"`（**保留不动**） |

### 3.3 不变项（本 CR 明确不改）

| 项 | 状态 |
|---|---|
| `AssetManager` 公开 API | **零改动**（`register/get_asset/...` 签名与语义不变；仍只读 DB、零扫盘） |
| `AssetMetadata.to_dict()` | **恰 3 字段**（`asset_id` / `asset_path` / `duration`）不变 |
| DB 表结构 | **`assets` 表零变更**（**无格式列**）；`path` 语义不变（相对项目根的路径），仅扩展名变化 |
| API 契约 | **零改动**（`PlaybackState` 7 字段；`asset_url` 仍 = `"/" + asset_path`） |
| 前端 | **零改动**（不拼路径、不判断素材类型 —— 遵守 **RB-2**）；`<video>` 按容器自动解码 |
| 静态挂载 | **零改动**（`StaticFiles` 按扩展名自动 MIME） |
| mp4 资产 | **保留**（不删除、不替换；双轨并存，回退可用） |
| 新增常量 | `constants.ALPHA_ASSET_SUFFIX = ".webm"`（**仅声明常量**，不含任何探测/回退逻辑） |

---

## 四、影响模块

| 模块 | 影响 |
|---|---|
| `assets/pets/cat/actions/{idle,heart,happy}/{action}.webm` | **新增 3 个文件**（原 mp4 保留） |
| `backend/app/core/constants.py` | 新增 1 个常量（`ALPHA_ASSET_SUFFIX`）；`ACTION_ASSET_SUFFIX` 不变 |
| `backend/scripts/init_assets.py` | **改动点**：新增 `ALPHA_ACTIONS` 显式映射 + `resolve_action_asset()`；`iter_seed_targets()` 增 `assets_root` 参数并返回 `is_alpha`；`SeedReport` 增 `alpha` 字段 |
| `database/pet_live.db` | `assets` 表 **3 行** `path` 更新为 `*.webm`（**无 migration / 无 schema change / 无新增字段**；`duration` 未改） |
| `backend/tests/**` | `conftest.py` 增 `asset_rel_path()`/`asset_suffix`（唯一构造点）；`test_api_contract.py` / `test_asset_manager.py` 去 `.mp4` 硬编码；**新增** `test_init_assets_alpha.py` |
| `docs/development/phase3_asset_spec.md` | 修订至 **v0.4**（§一/§五/§六/§八/§九/§十 + 变更历史） |
| `docs/change_request/cr-9_webm_alpha_asset_contract.md` | 本文件（新增；2-1J-4 由 `cr-8_*` 更名） |
| 前端 / API / `asset_manager.py` / `schema.sql` / `config.json` | **零改动** |

**架构合规**：素材选择属 **seed 脚本层**（`backend/scripts/**`），不进入 `app/services/**`；
`AssetManager` 仍只消费「显式传入的 path」⇒ 未越层、未破坏「SQL 仅在 `repositories/**` + `data_manager.py`」的边界。

---

## 五、是否影响 MVP 范围

**不影响**。不新增/删除任何动作、事件类型、API 端点或 `PlaybackState` 字段；
`ALLOWED_ACTIONS` 仍恰 5 个；前端零改动。本 CR 只改变**素材文件格式**与**seed 时的格式选择**。

---

## 六、验证方案

1. **静态守卫**：后端静态守卫脚本全 `ok: true`（`api/**` 不 import 引擎、无 SQL 等）。
2. **后端全量回归（提交前）**：判据 `N passed / 0 failed / 0 errors` + `safe_delete=False`。
3. **资产验收**：`ffprobe` 逐动作确认 `codec_name=vp9` + `stream_tags.alpha_mode=1` + 720×1280 + 无音轨。
4. **DB 验收**：`SELECT pet_type, action, path FROM assets` ⇒ cat idle/heart/happy 为 `*.webm`，其余行逐字不变。
5. **API 验收**：`GET /api/playback/state`（或 simulate 响应）的 `asset_url` 形如
   `/assets/pets/cat/actions/idle/idle.webm`；**前端无需修改**。
6. **运行验收（OBS）**：便携 OBS 31.0.2 + obs-browser（CEF 127）Browser Source ——
   期望 30 FPS 稳定、`render skipped = 0` / `output skipped = 0`、**alpha 可见**、阴影与水印移除。
7. **`seed()` 幂等复验**：重跑 `python -m scripts.init_assets` 不得把 `path` 覆盖回 `mp4`
   （由 `test_init_assets_alpha.py` 锁定）。

---

## 七、变更历史

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.1 | 2026-10-05 | **2-1J-4 编号裁决**：本 CR 由 **CR-8** 更名/改号为 **CR-9**（文件名 `cr-9_webm_alpha_asset_contract.md`），以消除与代码注释中「CR-8 = 连接复用」的同号不同义；历史注释零改动。文本其余条款不变。 |
| v1.0 | 2026-10-05 | 首次立档。owner 裁决 **O1=A**（保留 `ACTION_ASSET_SUFFIX=".mp4"` + 新增 `ALPHA_ASSET_SUFFIX=".webm"`）· **O2=A**（新建本 CR 后修订 asset_spec 至 v0.4）· **O3=A**（OBS 运行约束并入 asset_spec §九/§十）· **O4=cat idle/heart/happy only**。确立「Primary = webm/VP9/alpha_mode=1（无音轨）· Fallback = mp4/H.264/yuv420p」双轨契约与「显式映射 · 禁止扫目录/后缀猜测」红线。**并登记 CR-8 编号与代码注释中「连接复用」重号一事（见文首编号说明）。** |

---

## 八、交付与验收记录（2026-10-05 · **待 2-1J-4 REVIEW**）

### 8.1 交付内容

| # | 项 | 内容 |
|---|---|---|
| ① | 正式素材 | `assets/pets/cat/actions/{idle,heart,happy}/{action}.webm`（新增 3 个；原 mp4 **保留**） |
| ② | 常量 | `constants.ALPHA_ASSET_SUFFIX = ".webm"` |
| ③ | seed 策略 | `init_assets.ALPHA_ACTIONS` + `resolve_action_asset()`（显式映射 + 存在性回退） |
| ④ | DB | `assets` 表 3 行 `path` → `*.webm`（cat idle/heart/happy） |
| ⑤ | 测试 | `conftest.py` 去硬编码（`asset_rel_path` / `asset_suffix`）；`test_api_contract.py`、`test_asset_manager.py` 同步；**新增** `test_init_assets_alpha.py` |
| ⑥ | 文档 | 本 CR + `phase3_asset_spec.md` v0.3 → **v0.4** |

### 8.2 素材清单（sha256）

| action | 文件 | 大小 | sha256 |
|---|---|---|---|
| idle | `assets/pets/cat/actions/idle/idle.webm` | 2,112,076 B | `131d1b7f96b2d6b817487f212601825127b648ffae665555ac6937999e80818e` |
| heart | `assets/pets/cat/actions/heart/heart.webm` | 2,839,112 B | `6332205031c7ec3b942de954e4495affb3b4408b81212b768a91fe33067b41cb` |
| happy | `assets/pets/cat/actions/happy/happy.webm` | 2,580,070 B | `381bb933f259b860e24660ea31c6691486047188fd98c203bb7e1e0be7f58568` |

（三者与 2-1J-2 实验产物 `p21j_lab/webm/*.webm` **逐字节相同**；源 mp4 保留未动。）

### 8.3 验收状态

| 项 | 结果 |
|---|---|
| 后端全量回归 | 见 2-1J-3 报告（`N passed / 0 failed / 0 errors`，`safe_delete=False`） |
| ffprobe 资产验收 | `codec_name=vp9` · `alpha_mode=1` · 720×1280 · 音轨 0 —— 见 2-1J-3 报告 |
| DB / API 验收 | `assets.path` 3 行 → `*.webm`；`asset_url` 返回 `*.webm` |
| OBS 运行验收 | 见 2-1J-3 报告 Phase 8 |
| 状态 | **REVIEW = PASS**（2-1J-4，见工作区 `phase2_1j4_review_result.md`）—— **仍未 commit**，等待 **PHASE 2-1J-5 COMMIT AUTHORIZATION** |

### 8.4 已知残留 / 观察项（非阻断）

1. `heart.webm` 的**粉色爱心保持不透明**（colorkey 不匹配粉色）；若产品要求爱心亦透明，须另立规则（超出本 CR 范围）。
2. 鼻部极少数半透明像素（2-1B 已知残留 **D-1**），量级很小。
3. 爱心周围极淡粉色光晕（源素材自带 soft glow），计入 `alpha_mid` 且 **< 2%**。
4. DB `duration` 仍为 **4480 ms**（源 mp4 值）；webm 实测 **4459 ms**（差 21 ms）。本 CR **只改 `path`**（按授权），
   如需对齐须另行走 CR 或重跑 `seed()`（届时 `duration` 会被 ffprobe 重读为 4459）。
5. 写入 DB 时 SQLite 将原 4,120,032 B 的 `-wal` **checkpoint 归并**进主库（`pet_live.db` 110,592 → 118,784 B），
   `-wal` / `-shm` 侧文件随之消失 —— 属 SQLite 正常生命周期，非 schema 变更。
