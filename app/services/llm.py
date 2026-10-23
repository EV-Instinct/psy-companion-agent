"""LLM 服务：阿里云百炼（OpenAI 兼容端点）+ mock 模式。

- 真实模式：openai.AsyncOpenAI 指向 compatible-mode 端点（漏掉 compatible-mode 会 404）；
- mock 模式：无 Key 时保证全链路可跑通，输出确定性、安全、可测试的话术。
"""

import asyncio
import json
import logging
import random
import re
from typing import AsyncIterator

from openai import AsyncOpenAI

from app.config import Settings
from app.core.prompts import RISK_CLASSIFIER_PROMPT
from app.models import RiskAssessment

logger = logging.getLogger(__name__)

_MOCK_TEMPLATES: dict[str, list[str]] = {
    "exam": [
        "听起来这次考试让你挺紧张的。其实很多六年级同学在考前都会这样，心跳快、脑子乱，这不是你不够好。要不要先做个小尝试：把最担心的一件事写在纸上，写完再看看，它是不是真的那么可怕？",
        "考试前的紧张，说明你很在乎这件事。紧张本身不是敌人，它只是身体在提醒你“这很重要”。要不要试试：现在把手放在肚子上，慢慢吸气四秒、呼气六秒，做三轮，看看身体有没有松一点？",
    ],
    "score": [
        "成绩出来的时候，心里一下子沉下去，这种感觉我懂。分数只是这一张卷子的结果，不是你的全部。要不要先做件小事：把这次最想弄明白的一道错题圈出来，其他的先放一放？",
        "考砸了会难受，也会怕被说，这都很正常。我们先不急着分析对错，你先告诉我：看到分数的那一刻，你心里最先冒出来的话是什么？",
    ],
    "upgrade": [
        "一想到要上初中，心里没底是很正常的。新的学校、新的同学、更难的课，谁都会有点慌。要不我们把它拆小一点：你现在最担心初中的哪一件事？只挑一件说就行。",
        "怕上初中跟不上，说明你在认真对待自己的未来。不过“跟不上”是一个很大的词，我们先把它变成具体的问题：是怕数学难，还是怕交不到朋友？",
    ],
    "parents": [
        "被爸妈说的时候，心里又委屈又生气，还可能有口难辩。这些感受都很真实。要不要先不急着反驳，等情绪降一点，再挑一句最想让他们明白的话，试着说一次？",
        "和爸妈闹别扭，往往是因为双方都在着急。你愿意的话，可以跟我说说：他们说的哪句话最让你难受？",
    ],
    "peer": [
        "和同学闹别扭，会让人觉得孤单，甚至不想去学校。这种难受很真实。你愿意说说发生了什么吗？从你的角度讲就好。",
        "朋友之间的小矛盾，有时候比考试还让人心烦。我们先不判断谁对谁错，你现在最希望这件事变成什么样？",
    ],
    "sleep": [
        "睡不着的时候，脑子往往停不下来，越想睡越清醒。要不要试试：躺下后把注意力放在脚趾上，慢慢往上挪到小腿、大腿，一路放松上去，不想别的？",
        "睡不好会让人第二天更烦躁，这很正常。你最近是躺着睡不着，还是睡着了容易醒？",
    ],
    "refuse": [
        "不想上学，说明你现在真的挺累的，可能是身体累，也可能是心里累。我们先不急着讲道理，你能说说，是一想到学校就难受，还是到了学校才难受？",
        "厌学不是懒，很多时候是压力堆太久了。要不要先找一件学校里你还能接受的小事，比如见某个同学、上某一节课？",
    ],
    "default": [
        "谢谢你愿意跟我说这些。听起来这件事在你心里放了有一阵子了。你愿意多说说吗？从最让你难受的那一部分开始就好。",
        "我在听。你不用一次说清楚，想到哪说到哪都可以。最近这件事，最常在你什么时候冒出来？",
    ],
    "graduation": [
        "快毕业了，一想到要和相处六年的同学分开，心里空落落的，这说明你很重感情。要不要做一件小事：给最舍不得的那个同学写几句话，或者约一次毕业前的见面？",
        "舍不得，是因为这六年真的很重要。我们可以好好告别，也可以把友谊续约——留个联系方式，约好上初中后互相说说新学校的事。",
    ],
}

_TOPIC_PATTERNS = [
    ("graduation", re.compile(r"毕业|分开|舍不得|告别|见不到")),
    ("sleep", re.compile(r"睡不着|失眠|做噩梦|睡不好")),
    ("refuse", re.compile(r"不想上学|厌学|逃学|不想去学校")),
    ("score", re.compile(r"成绩|分数|考砸|没考好|排名|不及格|错题")),
    ("upgrade", re.compile(r"升初中|升学|上初中|初中|分班|摇号|择校")),
    ("parents", re.compile(r"爸妈|父母|爸爸|妈妈|家长|家里")),
    ("peer", re.compile(r"同学|朋友|同桌|孤立|闹别扭|吵架")),
    ("exam", re.compile(r"考试|测验|模拟考|期末|期中考|月考|考前")),
]

FIRST_TURN_INTRO = "你好，我是小树，一个愿意听你说话的小伙伴。先说清楚：我是 AI，不是真人，也不能代替心理老师；聊天内容会保密，但如果涉及安全，我会建议你告诉信任的大人。"


class LLMService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._client: AsyncOpenAI | None = None
        if not settings.use_mock:
            self._client = AsyncOpenAI(
                api_key=settings.llm_api_key,
                base_url=settings.llm_base_url,
                timeout=settings.llm_timeout_seconds,
            )

    @property
    def is_mock(self) -> bool:
        return self._client is None

    def _extra_body(self) -> dict | None:
        """思考开关：仅当配置了档位时才下发，避免不支持的端点报错。"""
        mode = (self.settings.llm_thinking or "").strip()
        if not mode or mode == "off":
            return None
        if mode == "disabled":
            base = (self.settings.llm_base_url or "").lower()
            if "dashscope" in base or "siliconflow" in base:
                return {"enable_thinking": False}
            return {"thinking": {"type": "disabled"}}
        return {"thinking": {"type": mode}}

    async def stream_chat(
        self,
        messages: list[dict],
        temperature: float = 0.75,
        model: str | None = None,
    ) -> AsyncIterator[str]:
        """流式生成回复（图片消息传 model=vlm_model）。"""
        if self._client is None:
            async for chunk in self._mock_stream(messages):
                yield chunk
            return

        stream = await self._client.chat.completions.create(
            model=model or self.settings.llm_model,
            messages=messages,
            temperature=temperature,
            max_tokens=self.settings.llm_max_tokens,
            extra_body=self._extra_body(),
            stream=True,
        )
        async for event in stream:
            if not event.choices:
                continue
            delta = event.choices[0].delta.content
            if delta:
                yield delta

    async def classify(self, text: str) -> RiskAssessment | None:
        """LLM 三级风险分级；失败返回 None（由调用方回退到关键词结果）。"""
        if self._client is None:
            return None
        try:
            resp = await self._client.chat.completions.create(
                model=self.settings.llm_model,
                messages=[
                    {"role": "system", "content": RISK_CLASSIFIER_PROMPT},
                    {"role": "user", "content": text[:1500]},
                ],
                temperature=0.0,
                max_tokens=300,
                extra_body=self._extra_body(),
            )
            raw = (resp.choices[0].message.content or "").strip()
            return _parse_risk_json(raw)
        except Exception as exc:  # noqa: BLE001 - 分级失败不能阻塞对话
            logger.warning("risk classify failed: %s", exc)
            return None

    # ---- mock 实现（仅用于离线自测/无 Key 演示）----
    async def _mock_stream(self, messages: list[dict]) -> AsyncIterator[str]:
        user_text = ""
        user_count = 0
        for msg in messages:
            if msg["role"] != "user":
                continue
            user_count += 1
            content = msg["content"]
            if isinstance(content, list):
                # 图片消息是多模态数组：只取文本部分用于挑选 mock 话术
                user_text = " ".join(
                    part.get("text", "")
                    for part in content
                    if isinstance(part, dict) and part.get("type") == "text"
                )
            else:
                user_text = str(content)
        reply = self._mock_reply(user_text)
        if user_count <= 1:
            reply = f"{FIRST_TURN_INTRO}\n\n{reply}"
        for piece in re.findall(r"[^，。！？\n]{1,12}[，。！？\n]?", reply):
            yield piece
            await asyncio.sleep(0.02)

    def _mock_reply(self, text: str) -> str:
        topic = "default"
        for name, pattern in _TOPIC_PATTERNS:
            if pattern.search(text):
                topic = name
                break
        rng = random.Random(hash(text) & 0xFFFFFFFF)
        return rng.choice(_MOCK_TEMPLATES[topic])


def _parse_risk_json(raw: str) -> RiskAssessment | None:
    """从模型输出里提取 JSON（容忍 ```json 包裹和多余文字）。"""
    match = re.search(r"\{.*\}", raw, re.S)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    level = str(data.get("level", "")).lower()
    if level not in {"green", "yellow", "red"}:
        return None
    reasons = data.get("reasons") or []
    if not isinstance(reasons, list):
        reasons = [str(reasons)]
    return RiskAssessment(level=level, reasons=[str(r) for r in reasons][:5], source="llm")
