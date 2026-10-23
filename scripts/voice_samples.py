# -*- coding: utf-8 -*-
"""生成不同音色的试听样本（不改工程配置，只产出 mp3 供人耳挑选）。"""

import pathlib
import time

from openai import OpenAI

ENV = pathlib.Path(".env").read_text(encoding="utf-8")
kv = {}
for line in ENV.splitlines():
    if "=" in line and not line.strip().startswith("#"):
        k, v = line.split("=", 1)
        kv[k.strip()] = v.strip()

KEY = kv["LLM_API_KEY"]
BASE = kv.get("LLM_BASE_URL", "https://api.siliconflow.cn/v1/")
MODEL = "FunAudioLLM/CosyVoice2-0.5B"
TEXT = "我在这儿呢，你慢慢说，不着急。"
OUT = pathlib.Path("logs/voice-samples")
OUT.mkdir(parents=True, exist_ok=True)

client = OpenAI(api_key=KEY, base_url=BASE, timeout=180)

# (文件名, 音色, 语速)
JOBS = [
    ("claire", "claire", 1.0),      # 当前在用
    ("anna", "anna", 1.0),          # 沉稳女声
    ("bella", "bella", 1.0),        # 激情女声
    ("diana", "diana", 1.0),        # 欢快女声
    ("claire-slow", "claire", 0.85),  # 温柔女声 + 放慢
]

for name, voice, speed in JOBS:
    t0 = time.time()
    try:
        kwargs = dict(model=MODEL, voice=f"{MODEL}:{voice}", input=TEXT, response_format="mp3")
        if speed != 1.0:
            kwargs["speed"] = speed
        audio = client.audio.speech.create(**kwargs)
        data = audio.read()
        path = OUT / f"{name}.mp3"
        path.write_bytes(data)
        print(f"[OK] {name:12s} voice={voice:8s} speed={speed} bytes={len(data):6d} {time.time()-t0:.1f}s")
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] {name:12s} voice={voice:8s} speed={speed} {type(exc).__name__}: {str(exc)[:120]}")
