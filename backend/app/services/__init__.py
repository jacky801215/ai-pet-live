"""``app.services`` 包导出。

只导出 Event Gateway —— 其余服务模块（AssetManager 等）保持按模块路径导入，
避免包级导出面在后续 Step 中无约束膨胀。
"""

from __future__ import annotations

from .event_gateway import EventGateway

__all__ = ["EventGateway"]
