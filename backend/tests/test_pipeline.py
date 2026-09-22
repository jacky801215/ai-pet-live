"""组合根拆分测试（Step 4.3-B-2-L4 / **AS-4**）。

契约来源：``docs/development/step4_api_stability_decision.md``（v1.0 FROZEN）**AS-4**。

覆盖：

    ① **兼容导出**：``PlaybackSnapshot`` 仍可从 ``app.services.pipeline`` import（硬要求）；
    ② **Runtime 装配**：``build_runtime`` 产出编排层所需的全部依赖，``Runtime`` 不可变；
    ③ **播放窗口**：``PlaybackClock`` 的 arm / is_due / disarm / deadline 语义与拆分前一致；
    ④ **行为零变化**：``playing`` → ``idle``（轮询驱动到期）链路逐条一致；
    ⑤ **结构守卫**：``playback_state`` 零 service import；引擎 import 仅限组合根两模块；
    ⑥ **结构守卫**：AS-4 三模块各 < 300 行（``PROJECT_RULES`` §一.1 硬规则）；
    ⑦ **Phase 3.2-A1**：``pet_id`` 为**显式构造参数**；``__new__`` 手工绑定与
       **构造后属性补写**均已消失（AST 结构守卫 + 行为覆盖）。

隔离：临时 ``project_root`` + 临时 SQLite + 真实 DDL（``constants.SCHEMA_PATH``），
**绝不触碰**真实 ``database/pet_live.db`` 与真实素材目录。
"""

from __future__ import annotations

import ast
import dataclasses
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.config.settings import Settings
from app.core import constants
from app.repositories.asset_repository import AssetRepository
from app.repositories.db import Database
from app.repositories.event_repository import EventRepository
from app.repositories.stat_repository import StatRepository
from app.services.action_engine import ActionEngine
from app.services.asset_manager import AssetManager
from app.services.data_manager import DataManager
from app.services.event_gateway import EventGateway
from app.services.interaction_engine import InteractionEngine
from app.services.pipeline import (
    PlaybackSnapshot,
    SimulationPipeline,
    get_pipeline,
)
from app.services.playback_manager import PlaybackManager
from app.services.playback_state import PlaybackClock
from app.services.runtime_factory import Runtime, build_runtime
from tests.conftest import make_action_file, register_asset

# ---------------------------------------------------------------------------
# 常量 / 夹具
# ---------------------------------------------------------------------------

APP_DIR = Path(__file__).resolve().parents[1] / "app"
SERVICES_DIR = APP_DIR / "services"

#: 测试宠物已登记的动作（时长 1s，便于验证播放窗口）
ACTIONS: tuple[str, ...] = ("idle", "heart", "happy")
ASSET_DURATION_MS: int = 1000

#: 命中规则的事件：``gift`` + ``小心心`` → ``heart``
GIFT_HEART: dict = {
    "event_type": "gift",
    "payload": {"gift_name": "小心心", "gift_count": 1},
}

#: Web 侧引擎**类名**（AS-4：import 归属只允许组合根两模块）
ENGINE_NAMES: frozenset[str] = frozenset(
    {"ActionEngine", "InteractionEngine", "PlaybackManager"}
)
#: 引擎模块名（仅供 ``api/**`` 的模块级守卫使用）
ENGINE_MODULES: frozenset[str] = frozenset(
    {"action_engine", "interaction_engine", "playback_manager"}
)
#: 组合根三模块（AS-4）
COMPOSITION_ROOT_MODULES: tuple[str, ...] = (
    "pipeline.py",
    "playback_state.py",
    "runtime_factory.py",
)


class FakeClock:
    """可控单调时钟（秒）—— 让「轮询驱动到期」可被确定性地验证。"""

    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture()
def env(tmp_path: Path) -> SimpleNamespace:
    """隔离环境：临时素材目录（含 ``cat_001`` 映射）+ 临时库 + 已登记动作。"""
    assets_root = tmp_path / "assets" / "pets"
    cat_dir = assets_root / "cat"
    cat_dir.mkdir(parents=True, exist_ok=True)
    (cat_dir / "config.json").write_text(
        json.dumps({"pet_id": "cat_001", "pet_type": "cat"}, ensure_ascii=False),
        encoding="utf-8",
    )

    settings = Settings(
        project_root=tmp_path,
        assets_root=assets_root,
        database_path=tmp_path / "pipeline_test.db",
        # 复用真实建表脚本，确保测试覆盖实际 DDL
        schema_path=constants.SCHEMA_PATH,
        strict_file_check=True,
    )
    database = Database(settings.database_path, settings.schema_path)
    database.initialize()

    manager = AssetManager(AssetRepository(database), settings)
    for action in ACTIONS:
        make_action_file(tmp_path, "cat", action)
        register_asset(manager, "cat", action, duration=ASSET_DURATION_MS)

    return SimpleNamespace(
        settings=settings,
        database=database,
        project_root=tmp_path,
        assets_root=assets_root,
    )


# ---------------------------------------------------------------------------
# ① 兼容导出（AS-4 硬要求）
# ---------------------------------------------------------------------------


def test_playback_snapshot_is_reexported_from_pipeline() -> None:
    """``from app.services.pipeline import PlaybackSnapshot`` 必须成立且指向同一对象。"""
    from app.services import pipeline as pipeline_module
    from app.services.playback_state import PlaybackSnapshot as canonical

    assert PlaybackSnapshot is canonical
    assert pipeline_module.PlaybackSnapshot is canonical
    assert "PlaybackSnapshot" in pipeline_module.__all__


def test_playback_snapshot_keeps_six_contract_fields() -> None:
    """API-2 六字段**零变化**（AS-4：拆分不得改动快照形状）。"""
    assert [f.name for f in dataclasses.fields(PlaybackSnapshot)] == [
        "pet_id",
        "state",
        "action",
        "asset_path",
        "queue_size",
        "last_event",
    ]


def test_pipeline_public_surface_is_unchanged(env: SimpleNamespace) -> None:
    """``api/**`` 依赖的公开面零变化（属性 + 编排入口），保证 import 路径不改。"""
    pipeline = SimulationPipeline(settings=env.settings, clock=FakeClock())

    assert isinstance(pipeline.pet_id, str)
    assert isinstance(pipeline.event_repository, EventRepository)
    assert isinstance(pipeline.stat_repository, StatRepository)
    assert callable(pipeline.simulate)
    assert callable(pipeline.snapshot)
    assert callable(get_pipeline)


# ---------------------------------------------------------------------------
# ② Runtime 装配（runtime_factory）
# ---------------------------------------------------------------------------


def test_build_runtime_assembles_all_dependencies(env: SimpleNamespace) -> None:
    """``build_runtime`` 产出编排层所需的**全部**依赖（装配职责回归）。"""
    clock = FakeClock()
    runtime = build_runtime(env.settings, clock=clock)

    assert isinstance(runtime, Runtime)
    assert runtime.settings is env.settings
    assert runtime.clock is clock
    assert runtime.pet_id == "cat_001"  # 由 AssetManager.pet_ids() 派生，非硬编码
    assert isinstance(runtime.database, Database)
    assert isinstance(runtime.asset_manager, AssetManager)
    assert isinstance(runtime.playback_manager, PlaybackManager)
    assert isinstance(runtime.action_engine, ActionEngine)
    assert isinstance(runtime.interaction_engine, InteractionEngine)
    assert isinstance(runtime.gateway, EventGateway)
    assert isinstance(runtime.data_manager, DataManager)
    assert isinstance(runtime.event_repository, EventRepository)
    assert isinstance(runtime.stat_repository, StatRepository)


def test_build_runtime_defaults_clock_to_monotonic(env: SimpleNamespace) -> None:
    """``clock`` 省略 / 传 ``None`` 时回落 ``time.monotonic``（装配默认值不变量）。

    注意：刻意传入临时 ``settings`` —— **不得**让测试走到 ``Settings.default()``
    的真实路径（那会触碰仓库真实数据库与素材目录）。
    """
    import time

    runtime = build_runtime(env.settings, clock=None)

    assert runtime.clock is time.monotonic


def test_runtime_is_frozen(env: SimpleNamespace) -> None:
    """``Runtime`` 必须是 ``frozen`` dataclass（AS-4），防止编排层就地改写依赖。"""
    runtime = build_runtime(env.settings, clock=FakeClock())

    with pytest.raises(dataclasses.FrozenInstanceError):
        runtime.pet_id = "ghost_999"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ③ 播放窗口（playback_state.PlaybackClock）
# ---------------------------------------------------------------------------


def test_playback_clock_semantics_unchanged() -> None:
    """拆分前 ``_playing_until`` 的三条语义逐条等价（None / 未到期 / 已到期）。"""
    clock = FakeClock()
    window = PlaybackClock(clock)

    assert window.deadline() is None
    assert window.is_due() is False  # 未备窗口 ≠ 到期（旧：`is not None and …`）

    window.arm(1.0)
    assert window.deadline() == clock.now + 1.0
    assert window.is_due() is False  # now < deadline

    clock.advance(1.0)
    assert window.is_due() is True  # now >= deadline（边界相等即到期）

    window.disarm()
    assert window.deadline() is None
    assert window.is_due() is False
    window.disarm()  # 幂等：重复 disarm 无副作用


def test_playback_clock_arm_overwrites_previous_window() -> None:
    """``arm`` 覆盖既有窗口（旧实现同样是直接赋值，非累加）。"""
    clock = FakeClock()
    window = PlaybackClock(clock)

    window.arm(5.0)
    window.arm(2.0)

    assert window.deadline() == clock.now + 2.0


# ---------------------------------------------------------------------------
# ④ 行为零变化（编排层 playing → idle）
# ---------------------------------------------------------------------------


def test_pipeline_playing_then_falls_back_to_idle(env: SimpleNamespace) -> None:
    """命中动作 → ``playing``；窗口过后再查询 → ``idle``（轮询驱动到期）。"""
    clock = FakeClock()
    pipeline = SimulationPipeline(settings=env.settings, clock=clock)

    playing = pipeline.simulate(GIFT_HEART)
    assert playing.pet_id == "cat_001"
    assert playing.state == "playing"
    assert playing.action == "heart"
    assert playing.asset_path == "assets/pets/cat/actions/heart/heart.mp4"
    assert playing.queue_size == 0
    assert playing.last_event == "gift"

    clock.advance(ASSET_DURATION_MS / 1000 + 1)

    idle = pipeline.snapshot()
    assert idle.state == "idle"
    assert idle.action is None
    assert idle.asset_path is None
    assert idle.queue_size == 0
    assert idle.last_event == "gift"  # 纯投影：播放结束后仍保留


def test_pipeline_writes_identity_columns_via_runtime(env: SimpleNamespace) -> None:
    """装配搬迁后写库口径不变：``events`` 九字段仍完整落库（AS-2 / L-2）。"""
    pipeline = SimulationPipeline(settings=env.settings, clock=FakeClock())
    pipeline.simulate(
        {"event_type": "gift", "user_id": "u_1", "user_name": "Tom",
         "payload": {"gift_name": "小心心", "gift_count": 1}}
    )

    row = pipeline.event_repository.list_recent(limit=1)[0]
    assert row["user_id"] == "u_1"
    assert row["user_name"] == "Tom"
    assert row["pet_id"] == "cat_001"
    assert row["action_name"] == "heart"
    assert row["platform"] == "simulator"


# ---------------------------------------------------------------------------
# ⑤/⑥ 结构守卫
# ---------------------------------------------------------------------------


def _imported_names(path: Path) -> set[str]:
    """收集 ``import`` / ``from … import`` 引入的**名字**与模块名（AST）。"""
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
                names.add(alias.name.rsplit(".", 1)[-1])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module)
                names.add(node.module.rsplit(".", 1)[-1])
            names.update(alias.name for alias in node.names)
    return names


def test_playback_state_imports_no_service_module() -> None:
    """AS-4②：``playback_state`` 是纯值对象 / 纯时间逻辑模块 —— 零 service、零仓储。"""
    imported = _imported_names(SERVICES_DIR / "playback_state.py")

    assert not [n for n in imported if n.startswith("app.")], imported
    assert not (imported & ENGINE_NAMES), imported


def test_engine_imports_are_confined_to_composition_root() -> None:
    """AS-4：Web 侧引擎 import 只允许出现在 ``runtime_factory`` / ``pipeline`` 两模块。

    判据用**引擎类名**（与既有 ``test_api_layer_never_imports_engines`` 同一口径）——
    ``rule_loader.py`` 只从 ``interaction_engine`` 取常量 ``SUPPORTED_OPERATORS``，
    不属引擎依赖（该取用已由其自身 docstring 明文冻结）。
    """
    allowed = {"services/runtime_factory.py", "services/pipeline.py"}
    importers: set[str] = set()

    for path in sorted(APP_DIR.rglob("*.py")):
        if _imported_names(path) & ENGINE_NAMES:
            importers.add(path.relative_to(APP_DIR).as_posix())

    assert importers <= allowed, f"引擎 import 越界：{sorted(importers - allowed)}"
    assert not [p for p in importers if p.startswith("api/")], "api/** 不得 import 引擎"


def test_composition_root_modules_stay_under_three_hundred_lines() -> None:
    """AS-4 / ``PROJECT_RULES`` §一.1：组合根三模块**各 < 300 行**（硬规则）。"""
    sizes = {
        name: len((SERVICES_DIR / name).read_text(encoding="utf-8").splitlines())
        for name in COMPOSITION_ROOT_MODULES
    }

    over = {name: size for name, size in sizes.items() if size >= 300}
    assert not over, f"超过 300 行：{over}（实际：{sizes}）"


# ---------------------------------------------------------------------------
# ⑦ Phase 3.2-A1：显式 pet_id 构造路径（构造期定值 / 无后置补写 / 无 __new__）
# ---------------------------------------------------------------------------


def _source_ast(name: str) -> ast.Module:
    """解析 ``app/services/<name>`` 源码为 AST（结构守卫用；docstring 不计入判据）。"""
    return ast.parse((SERVICES_DIR / name).read_text(encoding="utf-8"))


def test_init_takes_pet_id_as_explicit_keyword_only_parameter() -> None:
    """Phase 3.2-A1①：``__init__`` **显式接收** ``pet_id``，默认 ``None``（= 兼容派生语义）。"""
    init = next(
        node
        for node in ast.walk(_source_ast("pipeline.py"))
        if isinstance(node, ast.FunctionDef) and node.name == "__init__"
    )

    assert [a.arg for a in init.args.args] == ["self", "settings"]
    kwonly = [a.arg for a in init.args.kwonlyargs]
    assert kwonly == ["clock", "pet_id"], kwonly
    defaults = dict(zip(kwonly, init.args.kw_defaults))
    assert ast.unparse(defaults["pet_id"]) == "None"


def test_init_passes_pet_id_into_runtime_assembly() -> None:
    """Phase 3.2-A1②：``pet_id`` 在**构造阶段**即透传给 ``build_runtime``（定值于此）。"""
    init = next(
        node
        for node in ast.walk(_source_ast("pipeline.py"))
        if isinstance(node, ast.FunctionDef) and node.name == "__init__"
    )
    assembly = next(
        node
        for node in ast.walk(init)
        if isinstance(node, ast.Call) and ast.unparse(node.func) == "build_runtime"
    )

    keywords = {kw.arg: ast.unparse(kw.value) for kw in assembly.keywords}
    assert keywords.get("pet_id") == "pet_id", keywords


def test_build_pipeline_for_pet_uses_no_new_and_no_post_construction_injection() -> None:
    """Phase 3.2-A1③：``__new__`` 手工绑定与构造后属性补写**均已消失**。

    判据用 AST（非文本匹配）——docstring 中的 ``__new__`` 字样不构成违规，
    真正要禁的是**代码里**再出现属性访问 / 属性赋值。
    """
    factory = _source_ast("runtime_factory.py")

    bypass = [
        ast.unparse(node)
        for node in ast.walk(factory)
        if isinstance(node, ast.Attribute) and node.attr == "__new__"
    ]
    assert not bypass, f"runtime_factory 仍以 __new__ 绕过构造函数：{bypass}"

    injected = [
        ast.unparse(target)
        for node in ast.walk(factory)
        if isinstance(node, ast.Assign)
        for target in node.targets
        if ast.unparse(target).startswith("pipeline.")
    ]
    assert not injected, f"仍存在构造后属性补写：{injected}"


def test_pet_id_is_never_assigned_after_construction() -> None:
    """Phase 3.2-A1④：``pet_id`` 只由构造期 ``Runtime`` 定值 —— 禁止任何后置赋值。"""
    pipeline_mod = _source_ast("pipeline.py")

    assigned = [
        ast.unparse(target)
        for node in ast.walk(pipeline_mod)
        if isinstance(node, ast.Assign)
        for target in node.targets
        if ast.unparse(target) in ("self.pet_id", "pipeline.pet_id")
    ]
    assert not assigned, f"pet_id 出现后置赋值：{assigned}"


def test_no_new_construction_bypass_anywhere_in_app() -> None:
    """Phase 3.2-A1⑤：``app/**`` **全域**禁止以 ``__new__`` 绕过构造函数。"""
    offenders: list[str] = []

    for path in sorted(APP_DIR.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if any(
            isinstance(node, ast.Attribute) and node.attr == "__new__"
            for node in ast.walk(tree)
        ):
            offenders.append(path.relative_to(APP_DIR).as_posix())

    assert not offenders, f"仍存在 __new__ 手工构造：{offenders}"


def test_explicit_pet_id_wins_over_derived_default(env: SimpleNamespace) -> None:
    """行为覆盖：显式 ``pet_id`` 生效，且**构造完立刻**可读（构造期定值）。

    （合法键校验归 MP-1 / ``api/ws.py``；构造函数只做装配，故此处可用任意 key，
    以证明「显式值优先于派生值」这一唯一来源关系。）
    """
    pipeline = SimulationPipeline(
        settings=env.settings, clock=FakeClock(), pet_id="ghost_123"
    )

    assert pipeline.pet_id == "ghost_123"  # ≠ 派生值 cat_001
    assert pipeline.snapshot().pet_id == "ghost_123"


def test_default_construction_still_derives_pet_id(env: SimpleNamespace) -> None:
    """行为覆盖：``pet_id=None``（默认）**保持** Phase 1 兼容语义 —— 主键仍由派生而来。"""
    pipeline = SimulationPipeline(settings=env.settings, clock=FakeClock())

    assert pipeline.pet_id == "cat_001"  # 派生自 config.json，非硬编码（红线 C3）
    assert pipeline.simulate(GIFT_HEART).pet_id == "cat_001"
