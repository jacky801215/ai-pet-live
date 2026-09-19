-- AI Pet Live — 数据库结构（幂等建表脚本）
-- 范围（Phase 1）：
--   assets        资产元数据            Step 1
--   events        互动事件明细          Step 4.2-B
--   interactions  统计聚合（计数）      Step 4.2-B
-- 明确不创建：pets / users / sessions （裁决见 step4_data_layer_decision.md D3 / E27-A）

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------------
-- assets：资产元数据
-- ---------------------------------------------------------------------------
-- 设计要点：
--   1. (pet_type, action) 唯一，防止同一动作重复登记
--   2. action 不限定枚举值 —— 新增动作只需插入数据，无需改代码（验收 A3）
--   3. path 存相对项目根的路径，避免机器间不可移植
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS assets (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    pet_type  TEXT    NOT NULL,
    action    TEXT    NOT NULL,
    path      TEXT    NOT NULL,
    duration  INTEGER NOT NULL DEFAULT 0,
    UNIQUE (pet_type, action)
);

CREATE INDEX IF NOT EXISTS idx_assets_pet_type ON assets (pet_type);
CREATE INDEX IF NOT EXISTS idx_assets_action   ON assets (action);

-- ---------------------------------------------------------------------------
-- events：互动事件明细
-- ---------------------------------------------------------------------------
-- 契约：docs/development/step4_data_layer_decision.md（v1.0 FROZEN）D1
-- 设计要点：
--   1. 一次事件写一行；动作是否执行为「可空」—— action_name 非空 = 动作已执行（P5 / D5）
--   2. payload 存 JSON 字符串，平台字段一律留在 payload 内，不提升为独立列（§十四 事件契约）
--   3. user_id / user_name 的 NULL 语义不可改写（step2_event_schema.md §2.3）
--   4. 主键与时间列采用计划名 id / created_at（D1 命名勘误）
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type  TEXT    NOT NULL,
    user_id     TEXT,
    user_name   TEXT,
    pet_id      TEXT,
    action_name TEXT,
    platform    TEXT,
    payload     TEXT,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_events_type ON events (event_type);
CREATE INDEX IF NOT EXISTS idx_events_time ON events (created_at);

-- ---------------------------------------------------------------------------
-- interactions：统计聚合（全项目唯一统计载体）
-- ---------------------------------------------------------------------------
-- 契约：docs/development/step4_data_layer_decision.md（v1.0 FROZEN）D2
-- 设计要点：
--   1. stat_type 只允许 'event' | 'action'；stat_key = event_type 或 动作名（D6）
--   2. 扩展新维度只需加行、不改表；禁止固定统计列（like_count / gift_count ...）
--   3. created_at = 行首次创建时间（仅插入时写）；last_time = 最后更新时间（每次 UPSERT 刷新）
--      —— Step 4.2-B 裁决：两列并存（同时满足指令 §四 created_at 与冻结 D4 的 last_time 语义）
--   4. UNIQUE(stat_type, stat_key, pet_id) 提供 (stat_type, stat_key) 前缀索引（指令 §四 要求）
--   5. pet_id 为多角色隔离预留；Phase 1 恒为 NULL（aggregate_counter 不接收 pet_id）
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS interactions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    stat_type  TEXT    NOT NULL,
    stat_key   TEXT    NOT NULL,
    pet_id     TEXT,
    value      INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_time  TIMESTAMP,
    UNIQUE (stat_type, stat_key, pet_id)
);

CREATE INDEX IF NOT EXISTS idx_interactions_stat ON interactions (stat_type, stat_key);
