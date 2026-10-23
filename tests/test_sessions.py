"""会话管理测试：上下文裁剪、TTL 行为。"""

from app.core.sessions import SessionStore


def test_trim_by_turns():
    store = SessionStore(ttl_seconds=3600, max_turns=2, max_chars=100000)
    sid = "session-0001"
    store.get_or_create(sid)
    for i in range(5):
        store.append(sid, "user", f"问题{i}")
        store.append(sid, "assistant", f"回答{i}")
    history = store.history(sid)
    assert len(history) == 4
    assert history[0]["content"] == "问题3"
    assert history[-1]["content"] == "回答4"


def test_trim_by_chars():
    store = SessionStore(ttl_seconds=3600, max_turns=10, max_chars=10)
    sid = "session-0002"
    store.get_or_create(sid)
    store.append(sid, "user", "一" * 6)
    store.append(sid, "assistant", "二" * 6)
    store.append(sid, "user", "三" * 6)
    history = store.history(sid)
    # 字符预算 10：只能容纳最近一条
    assert len(history) == 1
    assert history[0]["content"] == "三" * 6


def test_expired_session_removed():
    store = SessionStore(ttl_seconds=0, max_turns=5, max_chars=1000)
    sid = "session-0003"
    store.get_or_create(sid)
    store.append(sid, "user", "你好")
    # ttl=0，下一次访问即过期重建
    session = store.get_or_create(sid)
    assert session.turns == 0 or len(session.turns) == 0
