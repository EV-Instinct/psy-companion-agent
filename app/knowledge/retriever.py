"""知识库：Markdown 文档 + jieba 分词 + BM25 内存检索。

为什么不用向量 RAG：知识库仅 50 篇左右且内容稳定，BM25 零依赖、零成本、
结果可解释可审计；等规模上来再换 embedding 方案。
"""

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import jieba

_STOPWORDS = {
    "的", "了", "是", "在", "我", "你", "他", "她", "它", "们", "和", "与", "就",
    "也", "都", "而", "及", "或", "一个", "什么", "怎么", "可以", "这个", "那个",
    "自己", "我们", "你们", "他们", "但是", "因为", "所以", "如果", "还是",
}
_PUNCT_RE = re.compile(r"[\s，。！？、；：“”‘’（）《》【】…—\-·,.!?;:\"'()\[\]{}<>/\\|@#$%^&*+=~`]+")


@dataclass
class Document:
    doc_id: str
    title: str
    content: str
    tokens: list[str] = field(default_factory=list)
    length: int = 0


def tokenize(text: str) -> list[str]:
    """中文分词 + 清洗：去掉标点、停用词与单字噪声。"""
    cleaned = _PUNCT_RE.sub(" ", text.lower())
    tokens = []
    for word in jieba.lcut(cleaned):
        word = word.strip()
        if not word or word in _STOPWORDS:
            continue
        if len(word) == 1 and not word.isascii():
            continue
        tokens.append(word)
    return tokens


class BM25Index:
    """标准 BM25（k1=1.5, b=0.75），文档量级 50+，内存检索毫秒级。"""

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.docs: list[Document] = []
        self._df: Counter = Counter()
        self._avg_len: float = 0.0

    def add(self, doc: Document) -> None:
        doc.tokens = tokenize(f"{doc.title} {doc.content}")
        doc.length = len(doc.tokens)
        self.docs.append(doc)
        for term in set(doc.tokens):
            self._df[term] += 1
        total = sum(d.length for d in self.docs)
        self._avg_len = total / len(self.docs) if self.docs else 0.0

    def search(self, query: str, top_k: int = 3, min_score: float = 0.8) -> list[tuple[Document, float]]:
        if not self.docs:
            return []
        q_tokens = tokenize(query)
        if not q_tokens:
            return []
        n = len(self.docs)
        scores: list[tuple[Document, float]] = []
        for doc in self.docs:
            tf = Counter(doc.tokens)
            score = 0.0
            for term in q_tokens:
                if term not in tf:
                    continue
                df = self._df.get(term, 0)
                if df == 0:
                    continue
                idf = math.log(1 + (n - df + 0.5) / (df + 0.5))
                freq = tf[term]
                denom = freq + self.k1 * (1 - self.b + self.b * doc.length / max(self._avg_len, 1e-6))
                score += idf * freq * (self.k1 + 1) / denom
            if score >= min_score:
                scores.append((doc, score))
        scores.sort(key=lambda item: item[1], reverse=True)
        return scores[:top_k]


class KnowledgeBase:
    def __init__(self, docs_dir: Path):
        self.docs_dir = Path(docs_dir)
        self.index = BM25Index()
        self._load()

    def _load(self) -> None:
        if not self.docs_dir.exists():
            return
        for path in sorted(self.docs_dir.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            title, body = _split_title(text, path.stem)
            self.index.add(Document(doc_id=path.stem, title=title, content=body))

    @property
    def size(self) -> int:
        return len(self.index.docs)

    def search(self, query: str, top_k: int = 3) -> list[dict]:
        results = []
        for doc, score in self.index.search(query, top_k=top_k):
            snippet = re.sub(r"\s+", " ", doc.content).strip()[:260]
            results.append({
                "id": doc.doc_id,
                "title": doc.title,
                "snippet": snippet,
                "score": round(score, 3),
            })
        return results


def _split_title(text: str, fallback: str) -> tuple[str, str]:
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip(), text.replace(line, "", 1).strip()
    return fallback, text.strip()


_kb: KnowledgeBase | None = None


def get_knowledge_base() -> KnowledgeBase:
    global _kb
    if _kb is None:
        from app.config import BASE_DIR

        _kb = KnowledgeBase(BASE_DIR / "app" / "knowledge" / "docs")
    return _kb
