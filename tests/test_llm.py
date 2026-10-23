"""LLM 服务测试：mock 模式的多模态兼容与首轮自我介绍。"""

import asyncio

from app.config import Settings
from app.services.llm import LLMService


def _collect(llm: LLMService, messages: list[dict]) -> str:
    async def run() -> str:
        parts = []
        async for chunk in llm.stream_chat(messages):
            parts.append(chunk)
        return "".join(parts)

    return asyncio.run(run())


def test_mock_text_reply():
    llm = LLMService(Settings(llm_mode="mock"))
    text = _collect(llm, [{"role": "user", "content": "这次考试没考好"}])
    assert "小树" in text
    assert len(text) > 40


def test_mock_image_message_no_error():
    llm = LLMService(Settings(llm_mode="mock"))
    messages = [{
        "role": "user",
        "content": [
            {"type": "text", "text": "帮我看看这张试卷"},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,AAAA"}},
        ],
    }]
    text = _collect(llm, messages)
    assert len(text) > 20


def test_mock_classify_returns_none():
    llm = LLMService(Settings(llm_mode="mock"))
    assert asyncio.run(llm.classify("我不想活了")) is None
