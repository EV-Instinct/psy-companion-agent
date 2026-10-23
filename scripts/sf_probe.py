# -*- coding: utf-8 -*-
"""硅基流动 SiliconFlow 探测：Key、模型清单、文本、视觉、语音合成（TTS）。"""
import io
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from openai import OpenAI  # noqa: E402

KEY = "sk-xxpnolzertyibpjxelvlfvyywfcxiesadnijxgnutxbdlslj"
BASE = "https://api.siliconflow.cn/v1"
client = OpenAI(api_key=KEY, base_url=BASE, timeout=90.0)


def list_models():
    try:
        resp = client.models.list()
        ids = sorted(m.id for m in resp.data)
        print(f"可用模型 {len(ids)} 个：")
        for mid in ids:
            print("  -", mid)
        return ids
    except Exception as exc:  # noqa: BLE001
        print("模型列表获取失败:", str(exc)[:200])
        return []


def probe_text(model):
    try:
        t0 = time.time()
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "你是陪伴六年级学生的AI伙伴小树，语气温暖。"},
                {"role": "user", "content": "考试前我总紧张，怎么办？"},
            ],
            max_tokens=200,
            temperature=0.7,
        )
        text = (resp.choices[0].message.content or "").strip()
        return True, f"{time.time() - t0:.1f}s | {text[:60]}"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)[:160]


def probe_vision(model):
    try:
        from PIL import Image, ImageDraw
        img = Image.new("RGB", (320, 200), "#FFFDF8")
        d = ImageDraw.Draw(img)
        d.text((16, 16), "数学卷 78分", fill="#2C2723")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        data_url = "data:image/png;base64," + __import__("base64").b64encode(buf.getvalue()).decode()
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": [
                {"type": "text", "text": "描述这张图片并用一句话关心学生"},
                {"type": "image_url", "image_url": {"url": data_url}},
            ]}],
            max_tokens=150,
        )
        return True, (resp.choices[0].message.content or "").strip()[:70]
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)[:160]


def probe_tts(model, voice=None):
    try:
        kwargs = {"model": model, "input": "你好，我是小树，愿意听你说话。", "response_format": "mp3"}
        if voice:
            kwargs["voice"] = voice
        t0 = time.time()
        audio = client.audio.speech.create(**kwargs)
        size = len(audio.read())
        return True, f"{time.time() - t0:.1f}s | {size // 1024} KB mp3"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)[:180]


def main():
    ids = list_models()
    print("\n== 文本模型 ==")
    for model in ["Qwen/Qwen2.5-7B-Instruct", "deepseek-ai/DeepSeek-V3", "Qwen/Qwen3-8B", "THUDM/GLM-4-9B-0414"]:
        if ids and model not in ids:
            print(f"[SKIP] {model}: 不在清单")
            continue
        ok, detail = probe_text(model)
        print(f"[{'OK' if ok else 'FAIL'}] {model}: {detail}")

    print("\n== 视觉模型 ==")
    for model in ["Qwen/Qwen2.5-VL-7B-Instruct", "Qwen/Qwen2-VL-7B-Instruct", "deepseek-ai/deepseek-vl2"]:
        if ids and model not in ids:
            print(f"[SKIP] {model}: 不在清单")
            continue
        ok, detail = probe_vision(model)
        print(f"[{'OK' if ok else 'FAIL'}] {model}: {detail}")

    print("\n== 语音合成 TTS ==")
    for model, voice in [
        ("FunAudioLLM/CosyVoice2-0.5B", "alex"),
        ("fishaudio/fish-speech-1.5", None),
        ("FunAudioLLM/CosyVoice2-0.5B", None),
    ]:
        if ids and model not in ids:
            print(f"[SKIP] {model}: 不在清单")
            continue
        ok, detail = probe_tts(model, voice)
        print(f"[{'OK' if ok else 'FAIL'}] {model} voice={voice}: {detail}")


if __name__ == "__main__":
    main()
