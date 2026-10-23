"""审计日志：危机事件与安全违规落盘（不记录原始对话，保护未成年人隐私）。"""

import hashlib
import json
import threading
import time
from pathlib import Path

from app.config import BASE_DIR

_LOCK = threading.Lock()
_AUDIT_FILE = BASE_DIR / "logs" / "audit.jsonl"


def session_fingerprint(session_id: str) -> str:
    """会话指纹：审计时用于关联，不可反推原始会话 ID。"""
    return hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:12]


def log_event(event: str, **fields) -> None:
    """追加一条审计事件（JSONL）。绝不写入对话原文。"""
    record = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "event": event,
        **fields,
    }
    try:
        with _LOCK:
            _AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)
            with _AUDIT_FILE.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        # 审计失败不能影响对话主流程
        pass
