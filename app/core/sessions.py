"""会话与上下文窗口管理。

MVP 用进程内存储（演示够用）；生产环境换 Postgres，接口保持不变。
"""

import threading
import time
from collections import deque
from dataclasses import dataclass, field


@dataclass
class Turn:
    role: str  # user / assistant
    content: str
    msg_type: str = "text"
    ts: float = field(default_factory=time.time)


@dataclass
class Session:
    session_id: str
    turns: deque[Turn] = field(default_factory=deque)
    risk_level: str = "green"
    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)
    turn_count: int = 0


class SessionStore:
    """内存会话仓库：TTL 过期 + 上下文按轮次/字符预算裁剪。"""

    def __init__(self, ttl_seconds: int = 3600, max_turns: int = 12, max_chars: int = 6000):
        self._ttl = ttl_seconds
        self._max_turns = max_turns
        self._max_chars = max_chars
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()

    def get_or_create(self, session_id: str) -> Session:
        now = time.time()
        with self._lock:
            self._cleanup_locked(now)
            session = self._sessions.get(session_id)
            if session is None:
                session = Session(session_id=session_id)
                self._sessions[session_id] = session
            session.last_active = now
            return session

    def append(self, session_id: str, role: str, content: str, msg_type: str = "text") -> None:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return
            session.turns.append(Turn(role=role, content=content, msg_type=msg_type))
            session.last_active = time.time()
            if role == "user":
                session.turn_count += 1
            # 先按轮次裁剪
            max_messages = self._max_turns * 2
            while len(session.turns) > max_messages:
                session.turns.popleft()

    def history(self, session_id: str) -> list[dict]:
        """返回可直接喂给模型的上下文（已按字符预算裁剪，保留最近的消息）。"""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return []
            messages: list[dict] = []
            total = 0
            for turn in reversed(session.turns):
                cost = len(turn.content)
                if messages and total + cost > self._max_chars:
                    break
                messages.append({"role": turn.role, "content": turn.content})
                total += cost
            messages.reverse()
            return messages

    def set_risk(self, session_id: str, level: str) -> None:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is not None:
                session.risk_level = level

    def _cleanup_locked(self, now: float) -> None:
        expired = [sid for sid, s in self._sessions.items() if now - s.last_active > self._ttl]
        for sid in expired:
            del self._sessions[sid]


_store: SessionStore | None = None


def get_store(ttl_seconds: int, max_turns: int, max_chars: int) -> SessionStore:
    global _store
    if _store is None:
        _store = SessionStore(ttl_seconds, max_turns, max_chars)
    return _store
