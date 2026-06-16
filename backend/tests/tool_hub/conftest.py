"""tool_hub 测试 fixture。"""
from __future__ import annotations

import pytest

from app.platform.database import engine
from app.tool_hub.bootstrap import ensure_tool_hub_startup


@pytest.fixture(autouse=True)
def _seed_tool_hub():
  """每个用例前确保预置工具与表结构就绪。"""
  ensure_tool_hub_startup(engine)
