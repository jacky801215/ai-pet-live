"""全局常量定义。

本模块只存放不可变的常量，禁止引入任何业务逻辑。
"""

from pathlib import Path

# ---------------------------------------------------------------------------
# 路径常量
# ---------------------------------------------------------------------------
# 本文件位于 <project_root>/backend/app/core/constants.py
# parents[0]=core, [1]=app, [2]=backend, [3]=<project_root>
PROJECT_ROOT: Path = Path(__file__).resolve().parents[3]

#: 宠物素材根目录：<project_root>/assets/pets
ASSETS_ROOT: Path = PROJECT_ROOT / "assets" / "pets"

#: 数据库目录：<project_root>/database
DATABASE_DIR: Path = PROJECT_ROOT / "database"

#: SQLite 数据库文件
DATABASE_PATH: Path = DATABASE_DIR / "pet_live.db"

#: 建表脚本
SCHEMA_PATH: Path = DATABASE_DIR / "schema.sql"

#: 对外暴露的素材 URL 前缀（供 Phase 4 播放层使用）
ASSET_URL_PREFIX: str = "/assets/pets"

# ---------------------------------------------------------------------------
# 动作常量
# ---------------------------------------------------------------------------
#: Phase 1 支持的动作集合（以 Step 1 指令为准）
ALLOWED_ACTIONS: tuple[str, ...] = ("idle", "heart", "happy", "sad", "surprise")

#: 动作素材文件扩展名（兼容基线：mp4 / H.264，无 alpha 通道）
ACTION_ASSET_SUFFIX: str = ".mp4"

#: alpha 素材文件扩展名（**CR-9** 新增：WebM / VP9，`alpha_mode=1` 带外 alpha）。
#: 说明：仅提供常量本身，**不做任何自动探测/回退** ——
#: 具体哪些「角色 + 动作」使用 alpha 素材由显式映射决定
#: （见 `backend/scripts/init_assets.py` 的 `ALPHA_ACTIONS`）。
ALPHA_ASSET_SUFFIX: str = ".webm"

# 说明（Step 1.1）：素材时长不再使用硬编码常量。
# duration 一律由 backend/app/services/asset_duration.py 通过 ffprobe
# 从素材文件真实读取，统一写入 assets.duration。

# ---------------------------------------------------------------------------
# 资产表字段
# ---------------------------------------------------------------------------
TABLE_ASSETS: str = "assets"

#: asset_id 格式模板：{pet_type}_action_{action}
ASSET_ID_TEMPLATE: str = "{pet_type}_action_{action}"
