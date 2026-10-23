"""全局配置：统一从环境变量 / .env 读取。

安全约定：API Key 只允许出现在后端环境变量里，绝不进入前端代码或仓库。
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    """应用配置（.env 中同名小写变量会被自动读取）。"""

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---- 服务 ----
    app_name: str = "小树洞 · 六年级心理陪伴"
    host: str = "127.0.0.1"
    port: int = 8701
    debug: bool = False

    # ---- 模型（OpenAI 兼容端点，默认阿里云百炼）----
    llm_api_key: str = ""
    llm_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    llm_model: str = "qwen-flash"
    vlm_model: str = "qwen3-vl-plus"
    # 语音独立 provider：填了就用这套 Key/地址跑 TTS+ASR，没填则回落到上面的 llm_*
    # （例：对话走智谱 GLM，语音合成/识别走硅基流动，两个 Key 各管一段）
    voice_api_key: str = ""
    voice_base_url: str = ""
    # 生成参数：思考型模型必须给足 max_tokens，否则正文会被 reasoning 占空
    llm_max_tokens: int = 1024
    # thinking: disabled=关闭思考；low/high/max=思考档位；off=不发送该参数
    llm_thinking: str = "disabled"
    # 语音合成（TTS）：默认硅基流动 CosyVoice2（音色须带模型前缀）
    tts_model: str = "FunAudioLLM/CosyVoice2-0.5B"
    tts_voice: str = "FunAudioLLM/CosyVoice2-0.5B:claire"
    tts_max_chars: int = 300
    # 语音识别（ASR）：默认硅基流动 Qwen3-ASR，实测约 1s
    asr_model: str = "Qwen/Qwen3-ASR-1.7B"
    asr_max_bytes: int = 6_000_000
    # 语速：0.85 = 比默认慢 15%，字与字之间更松，听感更温柔（实测有效）
    tts_speed: float = 0.85
    # TTS 单独超时：与对话解耦，异步任务可等更久
    tts_timeout_seconds: float = 90.0
    # auto: 有 Key 走真实模型，无 Key 自动降级 mock（便于离线自测与演示）
    llm_mode: str = "auto"  # auto | real | mock
    llm_timeout_seconds: float = 45.0

    # ---- 会话与上下文 ----
    session_ttl_seconds: int = 3600
    context_max_turns: int = 12
    context_max_chars: int = 6000

    # ---- 限流 ----
    rate_limit_per_minute: int = 20

    # ---- 日志与审计 ----
    log_dir: str = "logs"
    audit_log_file: str = "logs/audit.jsonl"

    @property
    def use_mock(self) -> bool:
        """是否使用 mock 模型（无 Key 时保证全链路可跑通）。"""
        if self.llm_mode == "mock":
            return True
        if self.llm_mode == "real":
            return False
        return not bool(self.llm_api_key.strip())

    @property
    def logs_path(self) -> Path:
        path = BASE_DIR / self.log_dir
        path.mkdir(parents=True, exist_ok=True)
        return path


@lru_cache
def get_settings() -> Settings:
    return Settings()


def settings_with_overrides(**overrides) -> Settings:
    """基于当前配置生成副本并覆盖指定字段（供前端「本机 Key」使用）。

    空值字段不覆盖，避免把服务端已有配置清掉。
    """
    base = get_settings()
    updates = {key: value for key, value in overrides.items() if value not in (None, "")}
    return base.model_copy(update=updates) if updates else base


def with_voice_provider(settings: Settings) -> Settings:
    """把语音（TTS/ASR）切到独立 provider：未配置 voice_* 时原样返回。

    典型用法：对话走智谱 GLM，语音走硅基流动，两个 Key 各管一段。
    """
    key = (settings.voice_api_key or "").strip()
    if not key:
        return settings
    updates = {"llm_api_key": key, "llm_mode": "auto"}
    base_url = (settings.voice_base_url or "").strip()
    if base_url:
        updates["llm_base_url"] = base_url
    return settings.model_copy(update=updates)


def build_llm_service(config):
    """按前端配置构建一次性 LLMService；无有效 Key 时返回 None（用服务端默认）。

    用户显式填了 Key 就以它为准（llm_mode 置 auto），不再受服务端演示模式影响。
    """
    from app.services.llm import LLMService

    if config is None or not config.api_key.strip():
        return None
    return LLMService(settings_with_overrides(
        llm_mode="auto",
        llm_api_key=config.api_key.strip(),
        llm_base_url=config.base_url.strip(),
        llm_model=config.model.strip(),
        vlm_model=config.vlm_model.strip(),
        llm_thinking=config.thinking.strip(),
    ))
