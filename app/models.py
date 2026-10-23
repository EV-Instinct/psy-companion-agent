"""API 数据模型（Pydantic）。"""

from typing import Literal, Optional

from pydantic import BaseModel, Field

MsgType = Literal["text", "voice", "image"]
RiskLevel = Literal["green", "yellow", "red"]


class LLMConfig(BaseModel):
    """前端传入的模型配置（可选）：存在则覆盖服务端 .env，即「本机 Key」模式。"""

    api_key: str = Field(default="", max_length=500)
    base_url: str = Field(default="", max_length=300)
    model: str = Field(default="", max_length=100)
    vlm_model: str = Field(default="", max_length=100)
    thinking: str = Field(default="", max_length=20)
    tts_model: str = Field(default="", max_length=100)
    tts_voice: str = Field(default="", max_length=120)


class ChatMessage(BaseModel):
    """一条用户输入。三个入口（文字 / 语音 / 图片）统一成同一种消息结构。"""

    type: MsgType = "text"
    content: str = Field(min_length=1, max_length=4000)
    # 图片消息：data:image/...;base64,...（仅 type=image 时存在）
    image_data_url: Optional[str] = Field(default=None, max_length=8_000_000)
    # 可选：本机模型配置，覆盖服务端 .env
    llm_config: Optional[LLMConfig] = None


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=8, max_length=64)
    message: ChatMessage


class TtsRequest(BaseModel):
    """语音合成请求：朗读一段文本（可选带本机模型配置）。"""

    text: str = Field(min_length=1, max_length=2000)
    llm_config: Optional[LLMConfig] = None


class AsrRequest(BaseModel):
    """语音识别请求：前端录音的 data URL（可选带本机模型配置）。"""

    audio: str = Field(min_length=32, max_length=12_000_000)
    llm_config: Optional[LLMConfig] = None


class RiskAssessment(BaseModel):
    level: RiskLevel = "green"
    reasons: list[str] = Field(default_factory=list)
    source: Literal["keyword", "llm", "fallback"] = "keyword"


class ResourceCard(BaseModel):
    """对话内展示的资源卡片（危机热线 / 微行动建议）。"""

    kind: Literal["hotline", "action", "referral"]
    title: str
    detail: str = ""
    action_text: str = ""
