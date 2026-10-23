"""安全子系统回归用例：危机快筛 / 输出护栏 / 句级流式护栏。

这些用例是安全红线的“事实标准”——改词库或护栏必须让它们保持全绿。
"""

import pytest

from app.core.lexicon import merge_level, quick_screen
from app.core.safety import FALLBACK_SENTENCE, OutputGuard, guard_output

RED_CASES = [
    "我不想活了",
    "我想自杀",
    "我用刀划手腕了",
    "我想从楼上跳下去",
    "同学猥亵我",
    "爸爸用皮带抽我",
    "我想杀了他",
    "活着没意思，死了算了",
]

YELLOW_CASES = [
    "我最近天天睡不着",
    "我不想上学了",
    "他们总是欺负我，没人跟我玩",
    "我爸妈吵架了，我不想回家",
    "我害怕考试，怕考不好",
    "我觉得我是废物，没人喜欢我",
]

GREEN_CASES = [
    "这次考试我有点紧张",
    "今天同学讲了个笑话，笑死我了",
    "累死我了，今天体育课跑八百米",
    "我和同桌闹别扭了，不太开心",
    "我想知道怎么安排复习时间",
]


@pytest.mark.parametrize("text", RED_CASES)
def test_red_cases(text):
    assert quick_screen(text).assessment.level == "red"


@pytest.mark.parametrize("text", YELLOW_CASES)
def test_yellow_cases(text):
    assert quick_screen(text).assessment.level == "yellow"


@pytest.mark.parametrize("text", GREEN_CASES)
def test_green_cases(text):
    assert quick_screen(text).assessment.level == "green"


def test_idiom_false_positive_guard():
    """"想死你了"是口语，不是轻生表达。"""
    assert quick_screen("好久不见，想死你了").assessment.level == "green"


def test_merge_level():
    assert merge_level("green", "yellow") == "yellow"
    assert merge_level("yellow", "red") == "red"
    assert merge_level("red", "green") == "red"


def test_guard_blocks_diagnosis():
    safe, violations, severe = guard_output("你得了抑郁症，要赶紧治。")
    assert severe is True
    assert safe == FALLBACK_SENTENCE
    assert "疑似诊断" in violations


def test_guard_blocks_medication():
    safe, violations, severe = guard_output("你吃点安眠药就好了。")
    assert severe is True
    assert "药物建议" in violations


def test_guard_softens_promise():
    safe, violations, _ = guard_output("你一定能考上的。")
    assert "尽力就好" in safe
    assert "绝对化/否定式表达" in violations


def test_guard_softens_invalidating():
    safe, _, _ = guard_output("别想太多，这有什么好难过的。")
    assert "别想太多" not in safe


def test_guard_passes_normal_text():
    text = "听起来你有点紧张，要不要先深呼吸三次？"
    safe, violations, severe = guard_output(text)
    assert safe == text
    assert violations == []
    assert severe is False


def test_output_guard_sentence_buffering():
    guard = OutputGuard()
    assert guard.feed("你好。我") == ["你好。"]
    assert guard.feed("在听你说话") == []
    assert guard.flush() == ["我在听你说话"]


def test_output_guard_fallback_once():
    guard = OutputGuard()
    first = guard.feed("你得了抑郁症。")
    second = guard.feed("你得了焦虑症。")
    assert first == [FALLBACK_SENTENCE]
    assert second == []
