-- AI Pet Live — Phase 1 Step 1 数据库结构
-- 范围：仅资产元数据表（assets）
-- 说明：本 Step 不创建 events / interactions / pets / users 表，
--       相关表属于 Step 2 及以后（见 docs/development/phase1_design.md）。

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
