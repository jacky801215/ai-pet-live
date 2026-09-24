# CR-1：实现 idle 循环播放（待机动画）

> 流程依据：`PROJECT_RULES.md` **§七「需求变更管理」**（任何新增需求必须创建 `docs/change_request/需求名称.md`）。
> 本文件是**本仓第一份正式 CR 文件**（编号空间 **CR-***；`CR-1` 此前只作为登记号出现在 §十四 与冻结文档中，从未生成文件）。
> `PlaybackState` 字段扩展另按 `PROJECT_RULES.md` §十四 `WE-5` 的**既定程序**执行，见 §六。

| 项 | 值 |
|---|---|
| 编号 | **CR-1** |
| 提出日期 | 2026-09-24 |
| 状态 | **待确认**（owner 已就方向与落地授权裁决，见 §六） |
| 关联契约 | `step4_frontend_player_decision.md`（**FP-3**）· `step4_api_contract_decision.md`（**API-2**）· `step3_playback_decision.md`（**P1**） |
| 关联验收项 | `phase1_design.md` **F5** / **P4** · `development_plan.md` 1-15（均 P0） |

---

## 一、需求描述

**Phase 1 P0 验收项「待机循环」当前不达成。**

| 出处 | 原文 |
|---|---|
| `phase1_design.md` **F5** | 「待机循环 \| `idle.mp4` **循环播放不间断**」 |
| `phase1_design.md` **P4** | 「待机无抖动 \| idle **循环 10 分钟**无中断、无跳帧」 |
| `development_plan.md` 1-15（P0） | 「前端展示端（宠物画面 + **待机循环**）」 |

**实测现状（只读核查结论，逐层可复核）**：

```
idle  ⇒  action = null  ⇒  asset_path = null  ⇒  asset_url = null
      ⇒  PetPlayer 渲染 `null`（`asset_url !== null ? <video/> : null`）
      ⇒  【待机时页面**没有任何 `<video>`**，只有三行文本】
```

证据链：

- `backend/app/services/pipeline.py` `snapshot()`：`asset_path` **仅在** `state == "playing" and pending` 时解析；
- `backend/app/services/action_engine.py`：状态恰 `idle` / `playing` 两个，**`idle` 不是队列条目**；
- `frontend/src/components/player/PetPlayer.tsx`：`asset_url !== null ? <video …/> : null`；
- 测试锁定：`frontend/tests/player-runtime/PetPlayer.runtime.test.tsx`「Idle 空闲状态（无媒体资源）… **不渲染 video**」。

⇒ **`idle.mp4`（已接入、duration 4480 ms）从未下发到前端。**
⇒ 因此「单独给 `<video>` 加 `loop`」**无法**达成 F5/P4；必须同时让待机态下发待机素材。

**本 CR 目标**：待机态下发待机素材并循环播放，达成 F5 / P4。

---

## 二、为什么需要

1. **属 Phase 1 P0 验收项** —— 缺失即未达标，不是可选增强。
2. **三处冻结条款互相扣死，缺一不可**：
   - **FP-3**（`<video>` 属性白名单，恰 6 属性）**无 `loop`** ⇒ 前端无法循环；
   - **API-2**（`PlaybackState` 恰 6 字段）**无 `loop`** ⇒ 即使 AssetManager 判定出来也**下发不了**；
   - **P1** 已裁定「`loop` 属**素材/动作属性**，由 **AssetManager** 的素材描述给出」，但**从未落地**。
3. **待机动画是直播形态的基础画面**：动作播完回落 idle 后，画面必须回到持续可见的待机动画；否则产品在「无事件」时段是空白，等于没有宠物画面。

---

## 三、影响模块

### 3.1 契约与治理（授权：owner 2026-09-24）

| 文件 | 改动 |
|---|---|
| `step4_frontend_player_decision.md` | **FP-3** v1.1 → **v1.2**：`<video>` 属性白名单**加 `loop`**；变更历史 +1 行 |
| `step4_api_contract_decision.md` | **API-2**：`PlaybackState` **6 → 7 字段**（+ `loop: boolean`）；`asset_url` 语义补「**待机时 = 该宠物的待机素材**」；变更历史 +1 行 |
| `step3_playback_decision.md` | **P1**：明确 `loop` 由 `AssetManager` **按动作**给出（`idle` → 循环、其余单次）；变更历史 +1 行 |
| `PROJECT_RULES.md` §十四 | 摘要同步：**`FP-3`** / **`WS-4`** / **`PC-5`** / **`WP-3`** / **`WE-5`** / **`MPF-6`** |
| `phase2_websocket_boundary_decision.md` | **WS-4** + C4 冲突检查行 + 相关表行：6 → 7 字段口径 |
| `phase2_websocket_push_boundary_decision.md` | **WP-3** + **C-WP3** 解释段 + 冲突矩阵行 |
| `phase2_websocket_runtime_integration_decision.md` | **WG-4** 载荷口径行 |
| `phase2_frontend_push_channel_decision.md` | **PC-***「6 字段冻结不变」两处 |
| `phase2_websocket_event_model_decision.md` · `phase2_websocket_commit_point_decision.md` · `phase2_websocket_runtime_event_gap_resolution_decision.md` · `phase2_websocket_connection_lifecycle_boundary_decision.md` · `phase2_websocket_lifecycle_implementation_boundary_decision.md` · `step4_api_stability_decision.md` · `step4_frontend_player_interaction_decision.md` | 同一「6 字段」口径的**复述行**同步（不改任何边界裁决） |

### 3.2 生产代码

| 层 | 文件 | 改动 |
|---|---|---|
| 后端 · 素材 | `app/services/asset_manager.py` | 新增 `IDLE_ACTION` / `LOOPING_ACTIONS` / `resolve_playback_asset()` / `is_looping()` |
| 后端 · **组合根三件套** | `app/services/pipeline.py` | 新增 **`asset_manager` 只读访问器**（**owner 明确授权的授权增量**，见 §六） |
| 后端 · API | `app/api/playback.py` | `PlaybackState` **+ `loop: bool`**；`build_playback_state(snapshot, assets=None)` 增加待机素材回落与循环判定 |
| 后端 · API | `app/api/events.py` | `simulate` 调用点传入 `pipeline.asset_manager` |
| 前端 · 类型 | `src/types/api.ts` | `PlaybackState` **+ `loop: boolean`** |
| 前端 · 组件 | `src/components/player/PetPlayer.tsx` | `<video loop={playback.loop}>`（**直接消费后端值，不做业务判断**） |

### 3.3 测试

`backend/tests/**`（7 字段锁定同步 + 新增 `loop` / 待机素材用例）· `frontend/tests/**`（同上）。

### 3.4 **明确不受影响**

- `database/schema.sql` —— `loop` 是**运行时**属性，**不入库**（`assets` 表零变更）；
- `app/platform/**`（含 `websocket_dispatcher.py`，其注释口径**只上报不擅改**）· `api/ws.py`；
- 组合根另外两件：`runtime_factory.py` / `playback_state.py`；**内部 `PlaybackSnapshot` 仍为 6 字段**（`asset_path` 形态不变）；
- `rules.json` · `ALLOWED_ACTIONS`（动作域**仍恰 5 个**）· `ALLOWED_EVENT_TYPES` · Rule Schema · `WM-1` envelope（**逐字不变**）· `PC-2` 消息格式（**逐字不变**）。

---

## 四、修改方案

1. **判定归 AssetManager**（落实 P1「素材/动作属性由 AssetManager 给出」）：
   - `IDLE_ACTION = "idle"`；`LOOPING_ACTIONS = frozenset({"idle"})`（**硬编码策略表**，不入库、不读配置）；
   - `resolve_playback_asset(pet_id, action)`：`action` 为空（待机）时**回落 `IDLE_ACTION`**；宽容版（未登记 → `None`），**参数非法仍抛异常**；
   - `is_looping(action) -> bool`。
2. **组合根只读访问器**：`SimulationPipeline.asset_manager` —— API 层取素材与循环值的**唯一入口**（形态与既有 `stat_repository` / `event_repository` / `gateway` 一致）。
3. **API 层纯协议转换**：`build_playback_state(snapshot, assets=None)` —— 向 `AssetManager` 取素材与循环值，**不做规则判断、不拼路径**；`assets=None`（不经组合根的直接调用）退化为既有行为（`asset_url` 沿用快照路径、`loop=False`）。
4. **前端纯消费**：`<video loop={playback.loop}>`；**禁止**写成 `action === "idle"`（FP-1「禁止业务判断」）。
5. **白名单与摘要**：FP-3 白名单加 `loop`；§十四 六处摘要同步。

---

## 五、是否影响 MVP 范围

**是 —— 属 Phase 1 P0 验收项，必做。**

不扩范围：不改 `ALLOWED_ACTIONS`（动作域仍恰 5 个）、不改 `rules.json`、不新增事件类型、不扩 Rule Schema、不改文件尺寸（组合根 `pipeline.py` 仍 **< 300 行**）、不新增依赖。

---

## 六、落地授权记录（owner 裁决，2026-09-24）

| 裁决 | 内容 |
|---|---|
| **方案 ③** | `AssetManager` 下发 `loop` → `PlaybackState` 加字段 → 前端消费（**不做前端判断**） |
| **合并为一份 CR** | **FP-3 + API-2 + P1 联动**（本文件） |
| **扩大授权范围** | **授权**把 `WS-4` / `WP-3` / `WG-4` / `PC-*` / `C-WP3` 及其 §十四 摘要一并纳入本 CR 的契约修订 |
| **组合根授权** | **授权**在 `pipeline.py` 新增 `asset_manager` **只读访问器**（仿真既有 `gateway` 先例；实测 `290 → ≤297` 行，仍 < 300） |

### 按 §十四 `WE-5` 既定程序执行（原文）

> `WE-5`（Coverage freeze）：**禁** 新 `event_type` / 修改 WM-1 envelope / 修改 PC whitelist /
> **新 PlaybackState 字段** / observer·listener·event bus；**G1 修复必须**先修订 `WM-1 FROZEN` + `PC-2` + separate decision

**本 CR 的处置**：

1. 走 **§七 CR 流程**（本文件）+ **契约修订**（§三）+ **独立决策记录**（本 CR 即该记录载体）；
2. **`WM-1` envelope 逐字不变**（仍恰 4 字段）、**`PC-2` 消息格式逐字不变** —— 本次**只解除「`PlaybackState` 字段数」这一条**，不放宽任何推送 / 连接 / 生命周期 / 重连 / 心跳边界；
3. `C-WP3` 的「`WS-4` / `WG-4` **不作为线上 frame schema**」结论**不变**。

---

## 七、附：音轨登记（本次**不处理**）

`PetPlayer` 的 `<video>` **硬编码 `muted`** ⇒ 素材 AAC 音轨**惰性不播**；FP-3 白名单亦不含 audio 相关。
若 Phase 2/3 要落地音效，须**另走 CR**（并衔接 `phase1_design.md` §三「音效播放 → P1，非核心验证项」）。**本次仅登记，不改动。**

---

## 八、变更历史

| 版本 | 日期 | 说明 |
|---|---|---|
| v1.0 | 2026-09-24 | 首版；owner 已裁决方向（方案 ③）、范围（FP-3 + API-2 + P1 联动）与落地授权（§六） |

## 附：回归暴露的既有缺口修复

`test_d6_http_simulate_unchanged_and_never_pushes` 回归暴露：`pet_id=""` 时 `AssetManager` 抛 `InvalidRequestError` → 400。按 C4 既有红线（asset 失败不得破坏 read/response）降级修复。

**本修复不属 CR-1 变更范围，是既有缺口的修正。**

（修复提交：`df34164`）
