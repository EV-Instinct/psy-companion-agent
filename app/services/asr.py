"""语音识别（ASR）：把录音转成文字，支持阿里云百炼 qwen3-asr-flash 与硅基流动 Qwen3-ASR。"""

import asyncio
import base64
import binascii
import json
import logging
import re
import urllib.error
import urllib.request

from openai import AsyncOpenAI

from app.config import Settings, settings_with_overrides, with_voice_provider

logger = logging.getLogger(__name__)

_DATA_URL = re.compile(r"^data:([^;]+);base64,(.+)$", re.S)
_DASHSCOPE_ASR_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"


def effective_asr_settings(config=None) -> Settings:
    """ASR 用的生效配置：本机 Key 优先，否则走语音独立 provider（voice_*）。"""
    if config is not None and config.api_key.strip():
        return settings_with_overrides(
            llm_mode="auto",
            llm_api_key=config.api_key.strip(),
            llm_base_url=config.base_url.strip(),
        )
    return with_voice_provider(settings_with_overrides())


def decode_audio(data_url: str) -> tuple[bytes, str]:
    """解析 data:audio/...;base64,... → (音频字节, mime)。"""
    match = _DATA_URL.match((data_url or "").strip())
    if not match:
        raise ValueError("音频格式不正确，请重新录音")
    mime = match.group(1)
    try:
        audio = base64.b64decode(match.group(2))
    except (binascii.Error, ValueError) as exc:
        raise ValueError("音频解码失败，请重新录音") from exc
    return audio, mime


def _filename(mime: str) -> str:
    if "webm" in mime:
        return "voice.webm"
    if "mp4" in mime or "aac" in mime or "m4a" in mime:
        return "voice.mp4"
    if "ogg" in mime:
        return "voice.ogg"
    if "mpeg" in mime or "mp3" in mime:
        return "voice.mp3"
    return "voice.wav"


def _transcribe_dashscope_sync(audio: bytes, mime: str, settings: Settings) -> str:
    """调用阿里云百炼 qwen3-asr-flash 语音识别。"""
    clean_mime = mime.split(";")[0].strip() or "audio/webm"
    data_url = f"data:{clean_mime};base64,{base64.b64encode(audio).decode('ascii')}"
    model = (settings.asr_model or "qwen3-asr-flash").strip()
    if "/" in model:
        model = "qwen3-asr-flash"
    payload = json.dumps({
        "model": model,
        "input": {
            "messages": [{
                "role": "user",
                "content": [{"audio": data_url}],
            }],
        },
    }).encode("utf-8")
    req = urllib.request.Request(
        _DASHSCOPE_ASR_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {settings.llm_api_key}",
            "Content-Type": "application/json",
        },
    )
    timeout = min(settings.llm_timeout_seconds, 30.0)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"百炼识别失败 {exc.code}：{exc.read().decode('utf-8', 'ignore')[:160]}") from exc
    choices = (body.get("output") or {}).get("choices") or []
    if not choices:
        return ""
    content = (choices[0].get("message") or {}).get("content") or []
    parts = [item.get("text", "") for item in content if isinstance(item, dict) and item.get("text")]
    return "".join(parts).strip()


async def transcribe(audio: bytes, mime: str, settings: Settings) -> str:
    """调用语音识别模型，返回识别文本。"""
    base = (settings.llm_base_url or "").lower()
    if "dashscope" in base or (settings.asr_model or "").startswith("qwen3-asr"):
        return await asyncio.to_thread(_transcribe_dashscope_sync, audio, mime, settings)

    client = AsyncOpenAI(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        timeout=settings.llm_timeout_seconds,
    )
    result = await client.audio.transcriptions.create(
        model=settings.asr_model,
        file=(_filename(mime), audio, mime),
    )
    return (getattr(result, "text", "") or "").strip()
