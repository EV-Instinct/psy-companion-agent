"""对话接口：POST /api/chat（SSE 流式）+ 安全管线编排。"""

import asyncio
import json
import logging
import time
import uuid
from collections import defaultdict, deque

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse, Response, StreamingResponse

from app.config import build_llm_service, get_settings, settings_with_overrides
from app.core import prompts
from app.core.audit import log_event, session_fingerprint
from app.core.safety import OutputGuard, assess_risk, friendly_error
from app.core.sessions import get_store
from app.knowledge.retriever import get_knowledge_base
from app.models import AsrRequest, ChatMessage, ChatRequest, LLMConfig, RiskAssessment, TtsRequest
from app.services.asr import decode_audio, effective_asr_settings, transcribe
from app.services.llm import LLMService
from app.services.tts import effective_tts_settings, synthesize

logger = logging.getLogger(__name__)
router = APIRouter()

_RATE_BUCKETS: dict[str, deque] = defaultdict(deque)

_llm: LLMService | None = None


def get_llm() -> LLMService:
    """服务端默认 LLM 服务（懒加载单例）。"""
    global _llm
    if _llm is None:
        _llm = LLMService(get_settings())
    return _llm


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _rate_limited(session_id: str) -> bool:
    limit = get_settings().rate_limit_per_minute
    now = time.time()
    bucket = _RATE_BUCKETS[session_id]
    while bucket and now - bucket[0] > 60:
        bucket.popleft()
    if len(bucket) >= limit:
        return True
    bucket.append(now)
    return False


def _chunk_text(text: str, size: int = 22) -> list[str]:
    return [text[i: i + size] for i in range(0, len(text), size)]


def _user_content(message: ChatMessage):
    """图片消息走多模态 content；文字/语音消息是纯文本。"""
    if message.type == "image" and message.image_data_url:
        return [
            {"type": "text", "text": message.content},
            {"type": "image_url", "image_url": {"url": message.image_data_url}},
        ]
    return message.content


def _build_messages(session_id: str, message: ChatMessage, level: str, reasons: list[str]) -> list[dict]:
    settings = get_settings()
    store = get_store(settings.session_ttl_seconds, settings.context_max_turns, settings.context_max_chars)

    messages: list[dict] = [{"role": "system", "content": prompts.SYSTEM_PROMPT}]

    if message.type == "image":
        messages.append({"role": "system", "content": prompts.IMAGE_GUIDE_PROMPT})

    # 知识库检索：只对文字/语音做（图片走视觉理解）
    if message.type != "image":
        try:
            docs = get_knowledge_base().search(message.content, top_k=2)
        except Exception as exc:  # noqa: BLE001 - 检索失败不能阻塞对话
            logger.warning("knowledge search failed: %s", exc)
            docs = []
        if docs:
            context = "\n\n".join(f"【{d['title']}】{d['snippet']}" for d in docs)
            messages.append({
                "role": "system",
                "content": prompts.KNOWLEDGE_INJECT_TEMPLATE.format(context=context),
            })

    if level == "yellow":
        messages.append({
            "role": "system",
            "content": prompts.YELLOW_HINT_TEMPLATE.format(reasons="、".join(reasons) or "情绪困扰"),
        })

    messages.extend(store.history(session_id))
    messages.append({"role": "user", "content": _user_content(message)})
    return messages


@router.post("/api/chat")
async def chat(req: ChatRequest):
    settings = get_settings()
    session_id = req.session_id
    if _rate_limited(session_id):
        raise HTTPException(status_code=429, detail="说得有点快啦，让系统歇口气，过一会儿再聊。")

    store = get_store(settings.session_ttl_seconds, settings.context_max_turns, settings.context_max_chars)
    store.get_or_create(session_id)
    message = req.message

    # 「本机 Key」：请求里带了有效 Key 就用它（一次性服务），否则用服务端默认
    llm = build_llm_service(message.llm_config) or get_llm()
    if message.llm_config and message.llm_config.api_key.strip():
        settings = settings_with_overrides(
            llm_model=message.llm_config.model.strip(),
            vlm_model=message.llm_config.vlm_model.strip(),
        )
    session_fp = session_fingerprint(session_id)

    async def event_stream():
        message_id = uuid.uuid4().hex[:12]
        yield _sse("meta", {"session_id": session_id, "message_id": message_id, "mode": "mock" if llm.is_mock else "real"})

        # 1) 安全分级
        try:
            assessment = await assess_risk(message.content, llm, session_fp)
        except Exception as exc:  # noqa: BLE001 - 分级异常按黄线保守处理
            logger.warning("assess_risk failed: %s", exc)
            assessment = RiskAssessment(level="yellow", reasons=["安全分级异常，保守处理"], source="fallback")

        store.set_risk(session_id, assessment.level)
        yield _sse("risk", {
            "level": assessment.level,
            "reasons": assessment.reasons,
            "source": assessment.source,
        })

        # 2) 红线：固定安全脚本，不交给生成模型自由发挥
        if assessment.level == "red":
            log_event("crisis_red", session=session_fp, reasons=assessment.reasons)
            store.append(session_id, "user", message.content, message.type)
            for piece in _chunk_text(prompts.CRISIS_SCRIPT):
                yield _sse("delta", {"text": piece})
                await asyncio.sleep(0.02)
            yield _sse("suggestions", {"cards": prompts.CRISIS_RESOURCE_CARDS})
            store.append(session_id, "assistant", prompts.CRISIS_SCRIPT)
            yield _sse("done", {"message_id": message_id, "risk": "red", "crisis": True})
            return

        # 3) 常规对话：流式 + 句级输出护栏（未吐出内容前遇超时/5xx 自动重试一次）
        messages = _build_messages(session_id, message, assessment.level, assessment.reasons)
        model = settings.vlm_model if message.type == "image" else settings.llm_model
        guard = OutputGuard(session_fp=session_fp)
        full_text = ""
        failed = False
        last_error = ""

        for attempt in (1, 2):
            try:
                async for delta in llm.stream_chat(messages, model=model):
                    for piece in guard.feed(delta):
                        full_text += piece
                        yield _sse("delta", {"text": piece})
                for piece in guard.flush():
                    full_text += piece
                    yield _sse("delta", {"text": piece})
                break
            except Exception as exc:  # noqa: BLE001 - 模型故障必须有兜底话术
                last_error = str(exc)
                logger.warning("llm stream failed (attempt %s): %s", attempt, exc)
                if attempt == 2 or full_text:
                    failed = True
                    break
                # 一个字符都还没吐出：重试一次，应对偶发超时 / 5xx
                await asyncio.sleep(0.5)

        if failed:
            log_event("llm_error", session=session_fp, error=last_error[:200])
            fallback = friendly_error(Exception(last_error))
            full_text += fallback
            yield _sse("delta", {"text": fallback})

        # 思考型模型可能把 token 全用在推理上导致正文为空——必须兜底，不能存空消息
        if not full_text.strip():
            empty_fallback = "我刚刚走了下神，没接住你的话。能再跟我说一遍吗？"
            full_text += empty_fallback
            yield _sse("delta", {"text": empty_fallback})
            log_event("empty_reply", session=session_fp)

        store.append(session_id, "user", message.content, message.type)
        store.append(session_id, "assistant", full_text)
        yield _sse("done", {"message_id": message_id, "risk": assessment.level, "failed": failed})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/api/history")
async def history(session_id: str):
    """读取会话历史（刷新页面后可恢复最近对话）。"""
    settings = get_settings()
    store = get_store(settings.session_ttl_seconds, settings.context_max_turns, settings.context_max_chars)
    return {"session_id": session_id, "messages": store.history(session_id)}


@router.post("/api/ping")
async def ping(config: LLMConfig):
    """用给定配置做一次最小模型调用，验证 Key / 模型是否可用。

    不写会话、不落日志，只返回连通性结果。
    """
    if not config.api_key.strip():
        raise HTTPException(status_code=400, detail="请先填写 API Key")
    llm = build_llm_service(config)
    if llm is None or llm.is_mock:
        raise HTTPException(status_code=400, detail="配置无效")

    messages = [
        {"role": "system", "content": "你是连通性测试助手，只回答两个字：正常"},
        {"role": "user", "content": "在吗"},
    ]
    try:
        text = ""
        async for delta in llm.stream_chat(messages, model=config.model.strip() or None):
            text += delta
            if len(text) > 20:
                break
    except Exception as exc:  # noqa: BLE001 - 连通性测试要把真实错误透出
        raise HTTPException(status_code=502, detail=f"连接失败：{str(exc)[:200]}") from exc

    return {"ok": True, "model": config.model.strip() or get_settings().llm_model, "reply": text.strip()[:20]}


def _audio_media_type(audio: bytes) -> str:
    return "audio/wav" if audio[:4] == b"RIFF" else "audio/mpeg"


@router.post("/api/tts")
async def tts(payload: TtsRequest):
    """语音合成（同步）：把文本读出来。本地/短文本用；线上慢模型建议用任务接口。"""
    settings = get_settings()
    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="没有要朗读的内容")
    if len(text) > settings.tts_max_chars:
        text = text[: settings.tts_max_chars]

    tts_settings = effective_tts_settings(payload.llm_config)
    if not tts_settings.llm_api_key.strip():
        raise HTTPException(status_code=400, detail="尚未配置模型 Key，无法朗读")

    try:
        audio = await synthesize(text, tts_settings)
    except Exception as exc:  # noqa: BLE001 - TTS 失败要给前端明确提示
        logger.warning("tts failed: %s", exc)
        raise HTTPException(status_code=502, detail=friendly_error(exc)) from exc

    return Response(content=audio, media_type=_audio_media_type(audio))


# 合成任务表：{job_id: {status, audio, error, created}}
_TTS_JOBS: dict[str, dict] = {}
_TTS_JOB_TTL = 300.0


def _gc_jobs() -> None:
    now = time.time()
    for job_id in [k for k, v in _TTS_JOBS.items() if now - v["created"] > _TTS_JOB_TTL]:
        _TTS_JOBS.pop(job_id, None)


async def _run_tts_job(job_id: str, text: str, settings) -> None:
    try:
        audio = await synthesize(text, settings)
        _TTS_JOBS.setdefault(job_id, {})["audio"] = audio
        _TTS_JOBS[job_id]["status"] = "done"
    except Exception as exc:  # noqa: BLE001 - 任务失败要落状态
        logger.warning("tts job failed: %s", exc)
        job = _TTS_JOBS.setdefault(job_id, {})
        job["status"] = "error"
        job["error"] = str(exc)[:160]


@router.post("/api/tts/jobs")
async def create_tts_job(payload: TtsRequest, background: BackgroundTasks):
    """语音合成（异步）：立即返回 job_id，前端轮询取音频。

    部署环境的网关有 15 秒上限，模型的 TTS 可能更慢，必须异步化。
    """
    settings = get_settings()
    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="没有要朗读的内容")
    if len(text) > settings.tts_max_chars:
        text = text[: settings.tts_max_chars]

    tts_settings = effective_tts_settings(payload.llm_config)
    if not tts_settings.llm_api_key.strip():
        raise HTTPException(status_code=400, detail="尚未配置模型 Key，无法朗读")

    _gc_jobs()
    job_id = uuid.uuid4().hex
    _TTS_JOBS[job_id] = {"status": "pending", "audio": None, "error": None, "created": time.time()}
    background.add_task(_run_tts_job, job_id, text, tts_settings)
    return {"job_id": job_id, "status": "pending"}


@router.get("/api/tts/jobs/{job_id}")
async def get_tts_job(job_id: str):
    """查询合成任务：202=生成中，200=音频就绪，502=失败。"""
    job = _TTS_JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="朗读任务不存在或已过期")
    status = job.get("status")
    if status == "done":
        audio = job.get("audio") or b""
        _TTS_JOBS.pop(job_id, None)
        return Response(content=audio, media_type=_audio_media_type(audio))
    if status == "error":
        detail = job.get("error") or "朗读失败"
        _TTS_JOBS.pop(job_id, None)
        raise HTTPException(status_code=502, detail=friendly_error(Exception(detail)))
    return JSONResponse({"status": status}, status_code=202)


@router.post("/api/asr")
async def asr(payload: AsrRequest):
    """语音识别：把前端录音转成文字（硅基流动 Qwen3-ASR）。"""
    settings = get_settings()
    try:
        audio, mime = decode_audio(payload.audio)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not audio:
        raise HTTPException(status_code=400, detail="没有录到声音，请重新录音")
    if len(audio) > settings.asr_max_bytes:
        raise HTTPException(status_code=413, detail="录音太长啦，说短一点再试")

    asr_settings = effective_asr_settings(payload.llm_config)
    if not asr_settings.llm_api_key.strip():
        raise HTTPException(status_code=400, detail="尚未配置模型 Key，无法识别语音")

    try:
        text = await transcribe(audio, mime, asr_settings)
    except Exception as exc:  # noqa: BLE001 - 识别失败要让前端明确提示
        logger.warning("asr failed: %s", exc)
        raise HTTPException(status_code=502, detail=friendly_error(exc)) from exc

    if not text:
        raise HTTPException(status_code=422, detail="没有听清，再说一次吧")
    return {"text": text}
