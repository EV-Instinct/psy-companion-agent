"""危机词库与关键词快筛规则。

设计原则：
1. 只做“快筛”——毫秒级、零成本、可审计，命中即升级，不追求语义完备；
2. 语义变体（如“想消失”“撑不下去了”）交给 LLM 分级兜底；
3. 必须处理口语误报（“笑死我了”“累死我了”“死党”）——先剔除习语再匹配。
"""

import re
from dataclasses import dataclass

from app.models import RiskAssessment

# 口语习语：匹配前先替换掉，避免“笑死我了”触发“死”类规则
_IDIOM_PATTERNS = [
    r"笑死", r"累死", r"困死", r"热死", r"冷死", r"饿死", r"烦死", r"气死",
    r"吓死", r"尴尬死", r"忙死", r"急死", r"愁死", r"美死", r"爽死",
    r"死党", r"死机", r"卡死", r"死循环", r"死记硬背", r"作死",
    r"想死你", r"想死我(了)?你", r"拼命(学习|刷题)?",
]
_IDIOM_RE = re.compile("|".join(_IDIOM_PATTERNS))

# 红线：自伤/自杀/他伤/虐待/性侵——命中即进入危机模式，不交给生成模型自由发挥
RED_RULES: list[tuple[str, str]] = [
    (r"自杀|轻生|自尽|结束(自己|我的)?生命", "出现自杀相关表达"),
    (r"想死|去死|死了算了|还不如死|活着没(意思|意义)|不想活|活不下去", "出现轻生念头表达"),
    (r"自残|自伤|割腕|划手腕|割手|伤害自己|弄伤自己", "出现自我伤害行为表达"),
    (r"跳楼|跳河|跳桥|上吊|跳(下去|下来)|喝农药|吞药|吃安眠药", "出现具体自杀方式表达"),
    (r"遗书|自杀计划|写好(了)?告别", "出现告别/计划表达"),
    (r"杀(了)?(他|她|你)|杀人|捅死|弄死(他|她)", "出现伤害他人表达"),
    (r"猥亵|性侵|强奸|脱我衣服|摸我(的)?(隐私|下面|身体)", "出现性侵害相关表达"),
    (r"家暴|虐待|用皮带抽|被打得(很|好)惨", "出现虐待/家暴相关表达"),
]

# 黄线：明显痛苦信号——温柔探询 + 视情况建议转介
YELLOW_RULES: list[tuple[str, str]] = [
    (r"崩溃|绝望|撑不住|撑不下去|受不了了|扛不住|熬不下去", "出现强烈痛苦表达"),
    (r"我是废物|我没用|我好笨|我很差劲|讨厌自己|没人喜欢我|没人爱我|我是多余的", "出现明显自我否定"),
    (r"被欺负|欺负我|霸凌|校园欺凌|孤立我|排挤我|没人跟我玩", "出现被欺凌/被孤立表达"),
    (r"睡不着|失眠|做噩梦|整夜(睡|醒)|不想睡觉", "出现睡眠困扰"),
    (r"不想上学|厌学|逃学|不想去学校", "出现厌学表达"),
    (r"不想回家|离家出走|不敢回家", "出现家庭安全困扰"),
    (r"爸妈(吵架|离婚|打我|骂我)|父母(吵架|离婚|打我|骂我)|家里(吵|闹)", "出现家庭冲突表达"),
    (r"害怕考试|怕考不好|考砸了|不想考试|怕考不上|不想升学|怕上初中", "出现考试/升学焦虑"),
]

_RED_COMPILED = [(re.compile(p), label) for p, label in RED_RULES]
_YELLOW_COMPILED = [(re.compile(p), label) for p, label in YELLOW_RULES]


@dataclass
class ScreenResult:
    assessment: RiskAssessment
    cleaned_text: str


def _strip_idioms(text: str) -> str:
    """把习语替换成占位符（不改变长度，避免影响后续位置计算）。"""
    return _IDIOM_RE.sub(lambda m: "□" * len(m.group(0)), text)


def quick_screen(text: str) -> ScreenResult:
    """关键词快筛：返回风险等级与命中原因（红 > 黄 > 绿）。"""
    cleaned = _strip_idioms(text)
    red_hits: list[str] = []
    yellow_hits: list[str] = []

    for pattern, label in _RED_COMPILED:
        if pattern.search(cleaned):
            red_hits.append(label)
    if red_hits:
        return ScreenResult(
            assessment=RiskAssessment(level="red", reasons=red_hits, source="keyword"),
            cleaned_text=cleaned,
        )

    for pattern, label in _YELLOW_COMPILED:
        if pattern.search(cleaned):
            yellow_hits.append(label)

    level = "yellow" if yellow_hits else "green"
    return ScreenResult(
        assessment=RiskAssessment(level=level, reasons=yellow_hits, source="keyword"),
        cleaned_text=cleaned,
    )


def merge_level(a: str, b: str) -> str:
    """合并两个风险等级，取更高者。"""
    order = {"green": 0, "yellow": 1, "red": 2}
    return a if order[a] >= order[b] else b
