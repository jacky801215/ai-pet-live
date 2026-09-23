/**
 * Pet Catalog —— **可用宠物列表**（MPF-1，Phase 3.2-B）。
 *
 * 来源口径（用户裁决「前端静态常量」）：backend **没有** pet 列表端点
 * （仅 `/simulate` / `/state` / `/stats` / `/events/recent` / `WS /api/ws`），
 * 且本步禁止修改 `backend/app/*`，故列表以前端静态常量声明。
 *
 * **一致性约束**：本列表的 `pet_id` 取自各宠物 `assets/pets/*\/config.json`，
 * 即 backend `AssetManager.pet_ids()` 的**子集**，保证 `?pet_id=` 一律通过
 * backend `known_pet_keys()` 校验（MP-1：「pet_id 或 pet_type 均合法」）。
 * 若 backend 侧新增/重命名宠物，本列表须同步（**后端为唯一事实来源**）。
 *
 * 边界（MPF-1）：
 * - 本文件**只**声明配置常量与类型：**禁止** HTTP / fetch / WebSocket / store 写入；
 * - **禁止**运行时扫描 `assets/`（前端无文件系统访问）；
 * - 本文件不属 `src/stores/`（FS-1：那是服务器快照消费态的位置），是**静态配置**。
 */

/** 一只可选宠物（选择器渲染用）。 */
export interface PetOption {
  /** 宠物上下文键；须为 backend 接受的合法键（本项目取 `pet_id` 形式）。 */
  pet_id: string;
  /** 展示名（取自对应 `config.json` 的 `name`）。 */
  label: string;
  /**
   * **素材待接入**标记（§7.1 收口，**可选**，缺省即非占位）。
   *
   * `true` = 该宠物的真实动画素材**尚未入库**（backend `assets` 表无该 `pet_id`
   * 的行，`AssetManager` 解析不到素材）：事件受理 / 计数写入 / WS 回帧全部正常，
   * 但播放**静默降级为 idle**、无动画。UI 据此**显式提示**，消除"静默无动画"。
   *
   * 该标记**只描述素材接入状态**，不改 `pet_id` 键集（MPF-1 冻结的 3 个 `pet_id`
   * 逐字不变）、不禁用选项、不改变 `?pet_id=` 连接语义（MPF-3 / MPF-4）。
   * 素材接入后（`python -m scripts.init_assets --all`）应同步移除此标记。
   */
  placeholder?: boolean;
}

/**
 * 可用宠物列表（顺序即选择器渲染顺序）。
 *
 * 与 `assets/pets/{cat,dog,panda}/config.json` 的 `pet_id` / `name` 逐条对应。
 *
 * `placeholder` 口径（§7.1 Step 0 实测）：`cat` 的 5 条动作素材**已登记**进
 * backend `assets` 表；`dog` / `panda` 的 15 个 mp4 虽在仓库内，但为**逐字节相同**
 * 的 1 秒占位文件（`mvhd` duration 恰 1.000s），**未登记**且不构成可用动画。
 */
export const AVAILABLE_PETS: readonly PetOption[] = [
  { pet_id: "cat_001", label: "小橘" },
  { pet_id: "dog_001", label: "旺财", placeholder: true },
  { pet_id: "panda_001", label: "团子", placeholder: true },
];

/**
 * 初始「当前宠物」= `null`。
 *
 * `null` 表示 **默认宠物**：WS 连接**不携带** `pet_id`，行为与 Phase 3.2-B 之前**逐字一致**。
 * 理由（MPF-2）：backend MP-3 裁决为「**仅显式 pet 连接按 pet 写**」——若默认也携带
 * `?pet_id=cat_001`，默认路径的聚合计数会由 `NULL` 作用域迁入 pet 作用域，
 * 使 `/api/stats`（前端 StatusBar 所读）读空，属越权行为变更。
 */
export const DEFAULT_SELECTED_PET_ID: string | null = null;
