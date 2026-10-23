# -*- coding: utf-8 -*-
"""定位 GLM 文本模型 content 为空的原因：思考 token / max_tokens / thinking 开关。"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from openai import OpenAI  # noqa: E402

KEY = "80ebaefc8fe84f47ad8534c6c9ceb7a9.VPFzL2V8U3MgEZuj"
BASE = "https://open.bigmodel.cn/api/paas/v4/"
client = OpenAI(api_key=KEY, base_url=BASE, timeout=90.0)

PROMPT = [
    {"role": "system", "content": "你是陪伴六年级学生的AI伙伴小树，语气温暖，每次回复80到180字。"},
    {"role": "user", "content": "考试前我总紧张，怎么办？"},
]


def show(tag, resp):
    msg = resp.choices[0].message
    content = (msg.content or "").strip()
    reasoning = getattr(msg, "reasoning_content", None) or ""
    usage = resp.usage
    print(f"--- {tag}")
    print(f"    content({len(content)}): {content[:70]!r}")
    print(f"    reasoning({len(reasoning)}): {reasoning[:50]!r}")
    print(f"    finish={resp.choices[0].finish_reason} usage={usage.completion_tokens if usage else '?'} tok")


def main() -> None:
    print("== A. 默认 max_tokens=200 ==")
    t0 = time.time()
    show("glm-5.3-flash default", client.chat.completions.create(model="glm-5.3-flash", messages=PROMPT, max_tokens=200))
    print(f"    ({time.time() - t0:.1f}s)")

    print("\n== B. max_tokens=2048 ==")
    t0 = time.time()
    show("glm-5.3-flash 2048", client.chat.completions.create(model="glm-5.3-flash", messages=PROMPT, max_tokens=2048))
    print(f"    ({time.time() - t0:.1f}s)")

    print("\n== C. 关闭思考 thinking=disabled ==")
    for model in ["glm-5.3-flash", "glm-5.3", "glm-5", "glm-4.6", "glm-4.5-air"]:
        try:
            t0 = time.time()
            resp = client.chat.completions.create(
                model=model,
                messages=PROMPT,
                max_tokens=1024,
                extra_body={"thinking": {"type": "disabled"}},
            )
            show(f"{model} thinking-off", resp)
            print(f"    ({time.time() - t0:.1f}s)")
        except Exception as exc:  # noqa: BLE001
            print(f"--- {model} thinking-off FAIL: {str(exc)[:150]}")


if __name__ == "__main__":
    main()
