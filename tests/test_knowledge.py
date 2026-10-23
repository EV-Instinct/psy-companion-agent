"""知识库测试：文档规模、检索命中、空库兜底。"""

import pytest

from app.knowledge.retriever import KnowledgeBase, get_knowledge_base


@pytest.fixture(scope="module")
def kb():
    return get_knowledge_base()


def test_docs_at_least_50(kb):
    assert kb.size >= 50


@pytest.mark.parametrize(
    "query, expected_id",
    [
        ("考试前睡不着怎么办", "exam-02-考前一晚睡不着"),
        ("怕上初中跟不上", "upgrade-02-怕初中跟不上"),
        ("被同学孤立了", "peer-01-被同学孤立"),
        ("作业一拖再拖", "study-03-作业拖拉"),
        ("朋友说不想活了", "crisis-02-朋友说不想活了"),
        ("网课好孤单", "pandemic-01-网课孤单"),
    ],
)
def test_retrieval_top1(kb, query, expected_id):
    hits = kb.search(query, top_k=3)
    assert hits, f"no hits for {query}"
    assert hits[0]["id"] == expected_id, f"{query} -> {hits[0]['id']}"


def test_retrieval_has_snippet(kb):
    hits = kb.search("考试紧张", top_k=1)
    assert hits and hits[0]["snippet"]


def test_empty_dir_returns_no_hits(tmp_path):
    empty = KnowledgeBase(tmp_path)
    assert empty.size == 0
    assert empty.search("考试") == []
