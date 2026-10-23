"""语音合成（TTS）：支持阿里云百炼 qwen3-tts-flash 与硅基流动 CosyVoice2。"""

import asyncio
import base64
import json
import logging
import urllib.error
import urllib.request

from openai import AsyncOpenAI

from app.config import Settings, settings_with_overrides, with_voice_provider

logger = logging.getLogger(__name__)

_DASHSCOPE_TTS_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"


def effective_tts_settings(config=None) -> Settings:
    """TTS 用的生效配置：本机 Key 优先，否则走语音独立 provider（voice_*）。"""
    if config is not None and config.api_key.strip():
        return settings_with_overrides(
            llm_mode="auto",
            llm_api_key=config.api_key.strip(),
            llm_base_url=config.base_url.strip(),
            tts_model=config.tts_model.strip(),
            tts_voice=config.tts_voice.strip(),
        )
    return with_voice_provider(settings_with_overrides())


def _synthesize_dashscope_sync(text: str, settings: Settings) -> bytes:
    """调用阿里云百炼 multimodal-generation 语音合成接口并取回音频字节。"""
    voice = (settings.tts_voice or "Cherry").split(":")[-1].strip() or "Cherry"
    model = (settings.tts_model or "qwen3-tts-flash").strip()
    if "/" in model:
        model = "qwen3-tts-flash"
    payload = json.dumps({
        "model": model,
        "input": {"text": text, "voice": voice},
    }).encode("utf-8")
    req = urllib.request.Request(
        _DASHSCOPE_TTS_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {settings.llm_api_key}",
            "Content-Type": "application/json",
        },
    )
    timeout = min(settings.tts_timeout_seconds, 30.0)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"百炼合成失败 {exc.code}：{exc.read().decode('utf-8', 'ignore')[:160]}") from exc
    audio_info = (body.get("output") or {}).get("audio") or {}
    if audio_info.get("data"):
        return base64.b64decode(audio_info["data"])
    url = audio_info.get("url")
    if not url:
        raise RuntimeError(f"TTS 未返回音频地址: {str(body)[:120]}")
    with urllib.request.urlopen(url, timeout=timeout) as audio_resp:
        return audio_resp.read()


async def synthesize(text: str, settings: Settings) -> bytes:
    """把文本合成为音频字节（百炼走 multimodal-generation，其余走 /v1/audio/speech）。"""
    base = (settings.llm_base_url or "").lower()
    if "dashscope" in base or (settings.tts_model or "").startswith("qwen"):
        return await asyncio.to_thread(_synthesize_dashscope_sync, text, settings)

    client = AsyncOpenAI(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        timeout=settings.tts_timeout_seconds,
    )
    audio = await client.audio.speech.create(
        model=settings.tts_model,
        voice=settings.tts_voice,
        input=text,
        response_format="mp3",
        speed=settings.tts_speed,
    )
    return audio.read()
