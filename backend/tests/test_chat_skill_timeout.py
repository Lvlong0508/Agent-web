"""chat_stream 技能检索超时降级测试。

背景：chat_service 对技能检索加 SKILL_RETRIEVAL_TIMEOUT=2s 超时（注释声称
"超时后走降级，不阻塞聊天主流程"），但外层 asyncio.wait_for 没有 try/except，
embedding 服务偶发慢时 TimeoutError 直接冒泡，导致整条请求失败、全量测试偶发崩溃。
本测试锁定"超时必须降级为空索引，chat_stream 照常产出 SSE"。
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.auth import current_user_id
from app.services.chat_service import ChatService


@pytest.mark.asyncio
async def test_skill_retrieval_timeout_degrades_to_empty():
    """技能检索超时：chat_stream 不抛 TimeoutError，降级空索引并正常产出 SSE"""
    token = current_user_id.set("anonymous")
    try:
        conv = MagicMock()
        conv._id = "c1"
        conv.user_id = "anonymous"
        service = ChatService(MagicMock())
        service.conv_repo.get_by_id = AsyncMock(return_value=conv)
        service.msg_repo.list_by_conversation = AsyncMock(return_value=[])
        service.msg_repo.create = AsyncMock(return_value=None)
        service.agent_run_service = MagicMock()
        service.agent_run_service.create = AsyncMock(return_value=None)

        # 技能检索挂起远超 2s 超时：验证外层 wait_for 超时后能降级而非抛错
        async def slow_skills(*args, **kwargs):
            await asyncio.sleep(30)
            return ""

        # 图不真正运行：空 async 生成器捕获 graph_input（chat_stream 仍走完整生命周期）
        captured_input = {}

        async def fake_astream(input, **kwargs):
            nonlocal captured_input
            captured_input = input
            if False:
                yield

        service.graph = MagicMock()
        service.graph.astream = fake_astream

        with patch(
            "app.services.chat_service.get_relevant_skills_prompt",
            side_effect=slow_skills,
        ):
            lines = []
            async for line in service.chat_stream("c1", "你好", "ollama"):
                lines.append(line)

        # 不抛 TimeoutError，正常产出 SSE（含结束标志 [DONE]）
        assert any("[DONE]" in l for l in lines)
        # 降级后 skills_index 为空串注入图输入（非全量膨胀）
        assert captured_input["skills_index"] == ""
    finally:
        current_user_id.reset(token)