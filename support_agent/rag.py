from __future__ import annotations

from dataclasses import dataclass, asdict
import hashlib
import time
from pathlib import Path
from typing import List, Dict
import re # 正则表达式，切分markdown文档

from sklearn.feature_extraction.text import TfidfVectorizer # 文本向量化
from sklearn.metrics.pairwise import cosine_similarity # 余弦相似度

from .config import POLICY_DIR
from .rag_config import RagSettings, EmbeddingSettings
from .embedding_client import EmbeddingClient, EmbeddingError, EmbeddingLedger
from .model_runtime import ModelConfigError
from .rag_index import DenseIndex, SPLIT_VERSION, digest
from .dense_retriever import DenseRetriever
from .hybrid_retriever import HybridRetriever


@dataclass
class DocumentChunk: # 文档片段
    source: str # 来源文件名 RAG里的”可溯源“
    text: str
    chunk_id: str = ""
    heading: str = ""
    content_hash: str = ""
    chunk_index: int = 0
    document_hash: str = ""

    def record(self):
        return asdict(self)


class PolicyKnowledgeBase:
    """
    本地轻量 RAG。
    修复点：
    1. 使用 char n-gram，适合中文无空格文本。
    2. 对退款、物流、售后问题做简单查询扩展。
    """

    def __init__(self, policy_dir: Path = POLICY_DIR, *, settings=None, embedding_settings=None, dense=None):
        self.settings = settings or RagSettings.read()
        self.embedding_settings = embedding_settings
        self._dense = dense
        self.policy_dir = Path(policy_dir)
        self.chunks: List[DocumentChunk] = [] # 创建一个空列表，后面每读到一个文档片段，就放进去。

        # 中文没有天然空格，不能用默认英文 token 方式
        # char ngram 会把“退款政策”“超过7天”等切成字符片段来匹配
        self.vectorizer = TfidfVectorizer(
            analyzer="char", # 按字符切分文本
            ngram_range=(1, 4), # 取 1 到 4 个连续字符作为特征
            lowercase=False
        )

        self.matrix = None
        self._load() # 加载知识库

    # 切分文档
    def _split_markdown(self, text: str) -> List[str]:
        blocks = re.split(r"\n(?=## )|\n\n+", text) # 以##开头切分文档
        chunks = []

        for block in blocks:  # 遍历每个文档块 
            block = block.strip() # 去除空格和换行
            if not block:
                continue

            if len(block) > 600:
                for i in range(0, len(block), 500):
                    chunks.append(block[i:i + 500])
            else:
                chunks.append(block)

        return chunks

    # 加载政策文档并建立索引
    def _load(self): 
        self.chunks = [] # 清空旧数据 

        for file in sorted(self.policy_dir.glob("*.md")):
            text = file.read_text(encoding="utf-8")
            document_hash = hashlib.sha256(file.read_bytes()).hexdigest()
            heading = ""
            for index, chunk in enumerate(self._split_markdown(text)):
                match = re.match(r"^#{1,6}\s+([^\n]+)", chunk)
                if match:
                    heading = match.group(1)
                self.chunks.append(DocumentChunk(source=file.name, text=chunk,
                    chunk_id=digest([SPLIT_VERSION, file.name, index, chunk]), heading=heading,
                    content_hash=hashlib.sha256(chunk.encode()).hexdigest(), chunk_index=index,
                    document_hash=document_hash))

        if not self.chunks:
            raise RuntimeError(f"未找到知识库文档：{self.policy_dir}")

        texts = [chunk.text for chunk in self.chunks]
        self.matrix = self.vectorizer.fit_transform(texts) # 计算文档向量矩阵

    def _expand_query(self, query: str) -> str:
        """
        简单查询扩展。
        真实项目里可以用 LLM 做 query rewrite。
        """
        expanded = query

        if any(w in query for w in ["退", "退款", "退货", "无理由", "七天", "7天"]):
            expanded += " 退款 退货 7天无理由 签收超过7天 质量问题 售后检测"

        if any(w in query for w in ["物流", "快递", "发货", "没到", "配送", "单号"]):
            expanded += " 物流 发货 快递 配送 物流异常 修改地址"

        if any(w in query for w in ["坏", "坏了", "维修", "售后", "少件", "错发", "破损"]):
            expanded += " 售后 维修 商品损坏 少件 错发 工单 人工客服"

        if any(w in query for w in ["投诉", "人工", "赔偿", "生气"]):
            expanded += " 投诉 人工转接 高优先级 工单 人工客服"

        return expanded

    #最核心的检索函数
    def _tfidf_search(self, query: str, top_k: int = 3) -> List[Dict]:
        query = self._expand_query(query) # 查询扩展

        query_vec = self.vectorizer.transform([query]) # 计算查询向量
        sims = cosine_similarity(query_vec, self.matrix).ravel() # 计算相似度

        ranked_idx = sims.argsort()[::-1][:top_k] # 取相似度最高的top_k个片段
            # ims.argsort():得到从小到大的索引
            # [::-1]：反转列表
            # [:top_k]：取前top_k个元素
        results = []
        for idx in ranked_idx: # 遍历每个片段
            score = float(sims[idx])

            # 分数太低就不返回
            if score <= 0.01:
                continue

            chunk = self.chunks[idx] # 获取片段
            results.append({
                **chunk.record(), "score": round(score, 4),
                "score_type": "tfidf_cosine", "retrieval_mode": "tfidf",
                "tfidf_rank": len(results) + 1
            })

        return results

    def _refresh(self):
        current = {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in self.policy_dir.glob("*.md")}
        loaded = {c.source: c.document_hash for c in self.chunks}
        if current != loaded:
            self._load()
            self._dense = None

    def _dense_search(self, query, top_k, ledger):
        if not self.settings.enabled:
            raise EmbeddingError("embedding_disabled")
        if self._dense is None:
            settings = self.embedding_settings or EmbeddingSettings.read()
            self.embedding_settings = settings
            index = DenseIndex.load(self.settings.cache_dir / "policy_index.json", self.chunks, settings)
            self._dense = DenseRetriever(index, self.chunks, EmbeddingClient(settings), remote_query=self.settings.remote_query)
        return self._dense.search(query, top_k, ledger)

    def search_with_trace(self, query: str, top_k: int = 3, *, ledger=None):
        if type(top_k) is not int or not 1 <= top_k <= 1000:
            raise ValueError("top_k must be an integer in 1..1000")
        started = time.perf_counter()
        self._refresh()
        mode, reason = self.settings.mode, None
        ledger = ledger or EmbeddingLedger(self.settings.query_budget)
        before_calls = len(ledger.calls)
        if mode == "tfidf":
            hits = self._tfidf_search(query, top_k)
        else:
            try:
                size = max(top_k, self.settings.candidates)
                dense = self._dense_search(query, size, ledger)
                hits = dense[:top_k] if mode == "dense" else HybridRetriever(self.settings.rrf_k).search(
                    self._tfidf_search(query, size), dense, top_k)
            except Exception as exc:
                # Boundary defense: a broken vector backend must not break business routes.
                reason = exc.code if isinstance(exc, EmbeddingError) else "configuration_error" if isinstance(exc, ModelConfigError) else "dense_unavailable"
                mode, hits = "tfidf", self._tfidf_search(query, top_k)
        trace = {"configured_mode": self.settings.mode, "actual_mode": mode, "fallback_reason": reason,
                 "embedding_model": self.embedding_settings.model if self.embedding_settings else None,
                 "retrieval_latency_ms": (time.perf_counter() - started) * 1000,
                 "embedding_attempts_this_search": len(ledger.calls) - before_calls,
                 "embedding_calls": ledger.summary()}
        return {"data": hits, "retrieval": trace}

    def search(self, query: str, top_k: int = 3) -> List[Dict]:
        """Backward compatible list result. Tool wrappers also expose explicit trace."""
        return self.search_with_trace(query, top_k)["data"]
    
# 1. rag.py 负责从政策知识库里检索相关文档
# 2. data/policies 里的 .md 文件就是知识库
# 3. DocumentChunk 表示一个文档片段
# 4. _split_markdown() 负责切分文档
# 5. _load() 负责读取文档并建立索引
# 6. search() 负责根据用户问题返回最相关片段
# 7. 默认TF-IDF；Dense/Hybrid必须显式配置，索引缺失不自动联网构建。
