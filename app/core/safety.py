"""安全子系统：输入三级分级 + 输出四不护栏。

分工：
- 输入：关键词快筛（毫秒级）→ LLM 语义分级（兜住变体）→ 取更高等级；
- 输出：句级护栏。提示词是软约束，这里是硬约束（模型被越狱或幻觉时兜底）；
- 审计：危机与违规事件落盘，不写对话原文。
"""

import re

from app.core.audit import log_event
from app.core.lexicon import merge_level, quick_screen
from app.models import RiskAssessment
from app.services.llm import LLMService

def friendly_error(exc: Exception) -> str:
    """把模型侧错误翻译成用户能看懂的话：欠费 / Key 失效不能被当成「网络不好」。"""
    low = str(exc).lower()
    if "arrearage" in low or "overdue-payment" in low or "in good standing" in low:
        return "小树暂时联系不上（模型账户需要充值），请让老师处理一下。我在这儿等你，过一会儿再来找我好吗？"
    if "invalid api key" in low or "incorrect api key" in low or "unauthorized" in low or "401" in low:
        return "小树暂时联系不上（模型 Key 配置有问题），请让老师检查一下。"
    if "timeout" in low or "timed out" in low:
        return "小树想得有点慢，刚才没接上。你歇一口，过一会儿再跟我说一遍好吗？"
    return "我这边网络好像不太好，试了两次都没接上。你先别急，喝口水休息一下，过一会儿再跟我说，我一直在。"


# ---- 输入分级 ----
async def assess_risk(text: str, llm: LLMService, session_fp: str = "") -> RiskAssessment:
    """关键词快筛 + LLM 语义分级，取更高等级（宁可高估，不可低估）。"""
    screen = quick_screen(text)
    if screen.assessment.level == "red":
        return screen.assessment
    # 已命中口语习语且无红黄关键词（如“笑死我了”“想死你了”），不再调 LLM，既省 1 次调用又避免误判
    if screen.assessment.level == "green" and screen.cleaned_text != text:
        return screen.assessment

    llm_result = await llm.classify(screen.cleaned_text)
    if llm_result is None:
        return screen.assessment

    level = merge_level(screen.assessment.level, llm_result.level)
    reasons = _dedupe(screen.assessment.reasons + llm_result.reasons)
    if level == "red":
        log_event("risk_escalated_by_llm", session=session_fp, reasons=reasons)
    return RiskAssessment(level=level, reasons=reasons, source="llm")


# ---- 输出护栏 ----
# 严重违规：整句丢弃，用固定安全话术兜底（诊断/药物建议属于红线）
_SEVERE_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"你(得|患|有)了?(抑郁|焦虑|强迫|双相|精神)(症|障碍)"), "疑似诊断"),
    (re.compile(r"确诊|你这是(心理|精神)(病|问题)"), "疑似诊断"),
    (re.compile(r"(吃|服用|吃点|喝点)[^。，！？]{0,8}(药|片|剂)"), "药物建议"),
    (re.compile(r"剂量|药量|毫克|\bmg\b"), "药物建议"),
]

# 一般违规：短语替换为安全表达（绝对化承诺 / 否定感受 / 评判家长老师）
_SOFT_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"别想太多|不要想太多|想开点|没什么大不了|这有什么好(难过|哭|怕)的"), "这些感受值得被认真对待"),
    (re.compile(r"你一定能考上|肯定能考上|保证能考上|绝对没问题"), "尽力就好"),
    (re.compile(r"你(爸|妈|父母|老师)(太|真)(过分|不对|有毛病|变态)"), "这件事让你很难受"),
]

FALLBACK_SENTENCE = (
    "我不是医生，没办法判断你是什么情况，也不想随便给你下结论，"
    "但你的感受很重要，值得被认真对待。"
)


def guard_output(text: str) -> tuple[str, list[str], bool]:
    """对一段文本做后置护栏。

    返回 (安全文本, 违规类型列表, 是否触发严重违规)。
    严重违规时文本替换为固定安全句，避免把诊断/用药建议发给学生。
    """
    violations: list[str] = []
    for pattern, label in _SEVERE_RULES:
        if pattern.search(text):
            violations.append(label)
    if violations:
        return FALLBACK_SENTENCE, violations, True

    safe = text
    for pattern, replacement in _SOFT_RULES:
        if pattern.search(safe):
            violations.append("绝对化/否定式表达")
            safe = pattern.sub(replacement, safe)
    return safe, _dedupe(violations), False


class OutputGuard:
    """流式输出的句级护栏：凑满一句就过一遍过滤再放行。"""

    def __init__(self, session_fp: str = "", max_buffer: int = 90):
        self._buffer = ""
        self._max_buffer = max_buffer
        self._fallback_emitted = False
        self._session_fp = session_fp

    def feed(self, delta: str) -> list[str]:
        """喂入模型增量，返回可以安全下发的片段列表。"""
        self._buffer += delta
        out: list[str] = []
        while True:
            match = re.search(r"[。！？!?；;\n]", self._buffer)
            if match:
                sentence = self._buffer[: match.end()]
                self._buffer = self._buffer[match.end():]
                piece = self._apply(sentence)
                if piece:
                    out.append(piece)
                continue
            if len(self._buffer) >= self._max_buffer:
                sentence = self._buffer[: self._max_buffer]
                self._buffer = self._buffer[self._max_buffer:]
                piece = self._apply(sentence)
                if piece:
                    out.append(piece)
                continue
            break
        return out

    def flush(self) -> list[str]:
        if not self._buffer:
            return []
        sentence = self._buffer
        self._buffer = ""
        piece = self._apply(sentence)
        return [piece] if piece else []

    def _apply(self, sentence: str) -> str:
        safe, violations, severe = guard_output(sentence)
        if not violations:
            return safe
        log_event(
            "output_violation",
            session=self._session_fp,
            violations=violations,
            severe=severe,
        )
        if severe:
            if self._fallback_emitted:
                return ""
            self._fallback_emitted = True
        return safe


def _dedupe(items: list[str]) -> list[str]:
    seen: list[str] = []
    for item in items:
        if item not in seen:
            seen.append(item)
    return seen
