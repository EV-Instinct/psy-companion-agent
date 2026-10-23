# -*- coding: utf-8 -*-
"""GLM（智谱）连通性探测：验证 Key、文本模型、视觉模型，输出可选模型清单。"""
import base64
import io
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from openai import OpenAI  # noqa: E402

KEY = "80ebaefc8fe84f47ad8534c6c9ceb7a9.VPFzL2V8U3MgEZuj"
BASE = "https://open.bigmodel.cn/api/paas/v4/"

client = OpenAI(api_key=KEY, base_url=BASE, timeout=60.0)


def probe_text(model: str) -> tuple[bool, str]:
    try:
        t0 = time.time()
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "你是陪伴六年级学生的AI伙伴小树。"},
                {"role": "user", "content": "考试前我总紧张，怎么办？"},
            ],
            temperature=0.7,
            max_tokens=200,
        )
        text = (resp.choices[0].message.content or "").strip()
        return True, f"{time.time() - t0:.1f}s | {text[:60]}"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)[:160]


def probe_vision(model: str) -> tuple[bool, str]:
    # 生成一张 100x60 的模拟试卷小图
    try:
        from PIL import Image, ImageDraw

        img = Image.new("RGB", (320, 200), "#FFFDF8")
        d = ImageDraw.Draw(img)
        d.rectangle([10, 10, 310, 40], outline="#2C2723")
        d.text((16, 16), "数学卷 78分", fill="#2C2723")
        d.text((16, 60), "1. 3/4 + 1/8 = ___", fill="#333")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        data_url = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception as exc:  # noqa: BLE001
        return False, f"造图失败: {exc}"

    try:
        t0 = time.time()
        resp = client.chat.completions.create(
            model=model,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": "描述这张图片，并用一句话关心这个学生。"},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }],
            temperature=0.5,
            max_tokens=150,
        )
        text = (resp.choices[0].message.content or "").strip()
        return True, f"{time.time() - t0:.1f}s | {text[:70]}"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)[:200]


def probe_stream(model: str) -> tuple[bool, str]:
    try:
        chunks = 0
        stream = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "说一句话"}],
            stream=True,
            max_tokens=50,
        )
        for event in stream:
            if event.choices and event.choices[0].delta.content:
                chunks += 1
        return chunks > 0, f"{chunks} chunks"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)[:160]


def main() -> None:
    print("== 文本模型 ==")
    for model in ["glm-5.3-flash", "glm-5.3", "glm-5", "glm-4.6"]:
        ok, detail = probe_text(model)
        print(f"[{'OK' if ok else 'FAIL'}] {model}: {detail}")

    print("\n== 流式 ==")
    ok, detail = probe_stream("glm-5.3-flash")
    print(f"[{'OK' if ok else 'FAIL'}] glm-5.3-flash stream: {detail}")

    print("\n== 视觉模型 ==")
    for model in ["glm-4v-plus", "glm-4.5v", "glm-4.1v-thinking", "glm-4v"]:
        ok, detail = probe_vision(model)
        print(f"[{'OK' if ok else 'FAIL'}] {model}: {detail}")


if __name__ == "__main__":
    main()
