"""Pet key 归一化（canonical pet key resolver）—— **仅** HTTP 读侧使用。

契约来源：

    - ``docs/development/phase3_pet_scoped_http_api_decision.md``（v1.0 FROZEN）**MB-1 / MB-2 / MB-3**
    - ``docs/development/step4_api_query_boundary_decision.md``（v1.0 FROZEN）的 **CR-1**（新铸 **QP-6**）

职责**仅此一项**：把 HTTP 读侧收到的 ``pet_id`` 查询值折算为 **canonical 键**（``pet_id`` 形态）。

- **别名 → canonical**（A1 = Option B）：``cat → cat_001`` · ``cat_001 → cat_001``（dog / panda 同理）；
  表外键 ⇒ ``None``（由调用方折为 ``400 INVALID_REQUEST``）。
- **输入 ``None`` ⇒ 输出 ``None``**：表示「无 pet 作用域」（走默认路径，A2 = W / A3 = S-1）。
  返回值 ``None`` 同时承担「无作用域」与「未知键」两种含义 —— **区分责任在调用方**：
  本模块**不做**合法性判定，也**不**决定错误契约。
- **合法键集不归本模块**：合法集 = ``runtime_factory.known_pet_keys(settings)``（MP-1 冻结口径），
  由 API 层经 ``api/ws.py::get_ws_settings()`` 取 ``settings`` 后判定（与 ``api/ws.py`` **同一做法**）；
  本模块不读磁盘 / 不查库，只做纯映射。

⛔ **作用域硬约束（MB-2 / MB-6）**：

- 本模块**仅**被 HTTP 读侧调用。**WS 写侧**（``api/ws.py`` / ``DataManager`` / ``Runtime``）的
  ``pet_id`` 口径**逐字不变** —— ``?pet_id=cat`` 经 WS 写入时**仍写 ``cat``**，**不**被归一化。
- 本模块**不 import** 引擎（``ActionEngine`` / ``InteractionEngine`` / ``PlaybackManager``）、
  **不 import** ``repositories/**``、**不访问数据库**、**不出现 SQL**、**不持有任何可变状态**。
- 匹配口径：**精确匹配 · 大小写敏感**（``CAT`` ≠ ``cat``）；不做前缀匹配、不做模糊匹配。
  首尾空白由**调用方**按 transport 惯例处理（与 ``api/ws.py`` 的 ``pet_id.strip()`` 同口径）。
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Final, Mapping

__all__ = ["ALIAS_TO_CANONICAL", "normalize_pet_key"]

#: 别名 → canonical 键（**只读**映射，冻结表）。
#:
#: 取值与 ``assets/pets/<pet_type>/config.json`` 的 ``pet_id`` / ``pet_type`` 一一对应；
#: canonical 键恒为 ``pet_id`` 形态（``<pet_type>_001``），别名恒为 ``pet_type`` 直用形态
#: （即 ``AssetManager._resolve_pet_type`` 未命中时「按 pet_type 直用」的那一类键）。
ALIAS_TO_CANONICAL: Final[Mapping[str, str]] = MappingProxyType(
    {
        "cat": "cat_001",
        "cat_001": "cat_001",
        "dog": "dog_001",
        "dog_001": "dog_001",
        "panda": "panda_001",
        "panda_001": "panda_001",
    }
)


def normalize_pet_key(pet_id: str | None) -> str | None:
    """别名 → canonical 归一化（仅 HTTP 读侧使用）。

    Args:
        pet_id: HTTP 读侧 ``?pet_id=`` 的值（调用方**已按需** ``strip()``），或 ``None``（未提供）。

    Returns:
        canonical 键；``pet_id is None`` ⇒ ``None``；键不在别名表内 ⇒ ``None``。

    Note:
        本函数**不抛异常**：错误契约（``400 INVALID_REQUEST``）由 API 层决定。
        调用方须先判定合法性（``known_pet_keys(settings)``），再把**合法键**交给本函数；
        若合法键却取不到 canonical（未登记别名），调用方应 **fail-closed**（拒绝而非降级到默认作用域）。
    """
    if pet_id is None:
        return None
    return ALIAS_TO_CANONICAL.get(pet_id)
