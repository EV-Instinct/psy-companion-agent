"""API 集成测试：SSE 事件序列、危机分流、限流。"""

import json
import uuid

import pytest
from starlette.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _sid() -> str:
    return f"test-{uuid.uuid4().hex[:12]}"


def _parse_sse(text: str) -> list[tuple[str, dict]]:
    events = []
    for block in text.strip().split("\n\n"):
        lines = [line for line in block.splitlines() if line.strip()]
        event = next((line[7:].strip() for line in lines if line.startswith("event:")), None)
        data = next((line[6:].strip() for line in lines if line.startswith("data:")), None)
        if event:
            events.append((event, json.loads(data) if data else {}))
    return events


def test_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["mode"] in {"mock", "real"}


def test_chat_stream_green(client):
    resp = client.post(
        "/api/chat",
        json={"session_id": _sid(), "message": {"type": "text", "content": "这次考试我有点紧张"}},
    )
    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    names = [name for name, _ in events]
    assert names[0] == "meta"
    assert "risk" in names
    assert "delta" in names
    assert names[-1] == "done"
    risk = dict(events)["risk"]
    assert risk["level"] in {"green", "yellow"}
    full_text = "".join(payload["text"] for name, payload in events if name == "delta")
    assert len(full_text) > 20


def test_chat_red_line(client):
    resp = client.post(
        "/api/chat",
        json={"session_id": _sid(), "message": {"type": "text", "content": "我真的不想活了"}},
    )
    events = _parse_sse(resp.text)
    named = dict(events)
    assert named["risk"]["level"] == "red"
    assert named["done"]["crisis"] is True
    cards = named["suggestions"]["cards"]
    assert any("12355" in c["title"] for c in cards)
    assert any("12356" in c["title"] for c in cards)
    text = "".join(payload["text"] for name, payload in events if name == "delta")
    assert "12355" in text and "12356" in text
    assert "信任的大人" in text


def test_chat_yellow(client):
    resp = client.post(
        "/api/chat",
        json={"session_id": _sid(), "message": {"type": "text", "content": "我最近天天睡不着"}},
    )
    events = dict(_parse_sse(resp.text))
    assert events["risk"]["level"] == "yellow"


def test_history_after_chat(client):
    sid = _sid()
    client.post(
        "/api/chat",
        json={"session_id": sid, "message": {"type": "text", "content": "你好"}},
    )
    resp = client.get("/api/history", params={"session_id": sid})
    assert resp.status_code == 200
    messages = resp.json()["messages"]
    assert len(messages) >= 2
    assert messages[0]["role"] == "user"


def test_invalid_payload(client):
    resp = client.post("/api/chat", json={"session_id": "x", "message": {"content": "hi"}})
    assert resp.status_code == 422


def test_image_message_builds_multimodal():
    from app.api.chat import _build_messages
    from app.models import ChatMessage

    messages = _build_messages(
        "test-session-image",
        ChatMessage(type="image", content="帮我看看这张卷子", image_data_url="data:image/jpeg;base64,AAAA"),
        "green",
        [],
    )
    last = messages[-1]
    assert isinstance(last["content"], list)
    kinds = [part["type"] for part in last["content"]]
    assert "text" in kinds and "image_url" in kinds
    image_part = next(part for part in last["content"] if part["type"] == "image_url")
    assert image_part["image_url"]["url"].startswith("data:image/jpeg")


def test_llm_config_override_switches_to_real():
    """请求里带有效 Key 时，即使服务端无 Key 也必须走真实模式。"""
    from app.config import build_llm_service
    from app.models import LLMConfig

    service = build_llm_service(LLMConfig(
        api_key="test-key-1234567890",
        base_url="https://example.invalid/v1",
        model="test-model",
        vlm_model="test-vlm",
    ))
    assert service is not None
    assert service.is_mock is False
    assert service.settings.llm_model == "test-model"
    assert service.settings.vlm_model == "test-vlm"


def test_llm_config_without_key_falls_back():
    from app.config import build_llm_service
    from app.models import LLMConfig

    assert build_llm_service(None) is None
    assert build_llm_service(LLMConfig(api_key="")) is None


def test_ping_requires_key(client):
    resp = client.post("/api/ping", json={"api_key": "", "model": "glm-5"})
    assert resp.status_code == 400


def test_ping_with_bad_key_returns_502(client):
    resp = client.post(
        "/api/ping",
        json={"api_key": "invalid-key-for-test", "base_url": "https://open.bigmodel.cn/api/paas/v4/", "model": "glm-5"},
    )
    assert resp.status_code == 502
    assert "连接失败" in resp.json()["detail"]
