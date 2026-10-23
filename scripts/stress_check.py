# -*- coding: utf-8 -*-
"""并发 / SSE 中断 / 稳定性检查（第二轮边界场景）。"""
import json
import sys
import threading
import time
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8701"
RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append({"name": name, "ok": bool(ok), "detail": str(detail)[:160]})
    print(("[PASS] " if ok else "[FAIL] ") + name + (f"  <- {detail}" if detail else ""))


def post(payload, timeout=30):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        BASE + "/api/chat", data=data,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.read().decode("utf-8", "replace")


def main():
    # 1) 同一会话 3 个并发请求
    sid = f"concurrent-{uuid.uuid4().hex[:8]}"
    codes = []
    errors = []

    def worker():
        try:
            status, _ = post({"session_id": sid, "message": {"type": "text", "content": "并发测试"}})
            codes.append(status)
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))

    threads = [threading.Thread(target=worker) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    check("同会话 3 并发全部 200", sorted(codes) == [200, 200, 200] and not errors, f"{codes} {errors}")

    # 2) 10 个独立会话顺序请求
    ok = 0
    for _ in range(10):
        status, _ = post({"session_id": f"seq-{uuid.uuid4().hex[:8]}", "message": {"type": "text", "content": "你好"}})
        ok += 1 if status == 200 else 0
    check("10 个独立会话全部 200", ok == 10, ok)

    # 3) SSE 中断：1 秒后主动断开，服务不应崩溃
    sid = f"abort-{uuid.uuid4().hex[:8]}"
    payload = json.dumps({"session_id": sid, "message": {"type": "text", "content": "说点长的"}}).encode()
    req = urllib.request.Request(BASE + "/api/chat", data=payload, headers={"Content-Type": "application/json"}, method="POST")
    try:
        urllib.request.urlopen(req, timeout=1).read(200)
    except Exception:  # noqa: BLE001 - 超时即视为主动断开
        pass
    time.sleep(0.5)
    with urllib.request.urlopen(BASE + "/api/health", timeout=10) as resp:
        check("中断后服务仍健康", resp.status == 200 and b"ok" in resp.read())

    # 4) 中断后的会话可继续使用
    status, body = post({"session_id": sid, "message": {"type": "text", "content": "继续聊"}})
    check("中断会话可继续", status == 200 and "event: done" in body)

    # 5) 服务日志无 Traceback / 500
    logs = sorted((ROOT / "logs").glob("check*.log"))
    check("找到服务日志", bool(logs), [p.name for p in logs])
    traceback_hits = []
    for log in logs:
        text = log.read_text(encoding="utf-8", errors="ignore")
        if "Traceback" in text:
            traceback_hits.append(log.name)
        if " 500 " in text:
            traceback_hits.append(f"{log.name}:500")
    check("服务日志无 Traceback / 500", not traceback_hits, traceback_hits)

    failed = [r for r in RESULTS if not r["ok"]]
    print("\n===== SUMMARY =====")
    print(json.dumps({"total": len(RESULTS), "passed": len(RESULTS) - len(failed), "failed": len(failed)}, ensure_ascii=False))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
