from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict
import re # 正则表达式，切分markdown文档

from sklearn.feature_extraction.text import TfidfVectorizer # 文本向量化
from sklearn.metrics.pairwise import cosine_similarity # 余弦相似度

from .config import POLICY_DIR


@dataclass
class DocumentChunk: # 文档片段
    source: str # 来源文件名 RAG里的”可溯源“
    text: str


class PolicyKnowledgeBase:
    """
    本地轻量 RAG。
    修复点：
    1. 使用 char n-gram，适合中文无空格文本。
    2. 对退款、物流、售后问题做简单查询扩展。
    """

    def __init__(self, policy_dir: Path = POLICY_DIR):
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
            for chunk in self._split_markdown(text):
                self.chunks.append(DocumentChunk(source=file.name, text=chunk))

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
    def search(self, query: str, top_k: int = 3) -> List[Dict]:
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
                "source": chunk.source,
                "text": chunk.text,
                "score": round(score, 4)
            })

        return results
    
# 1. rag.py 负责从政策知识库里检索相关文档
# 2. data/policies 里的 .md 文件就是知识库
# 3. DocumentChunk 表示一个文档片段
# 4. _split_markdown() 负责切分文档
# 5. _load() 负责读取文档并建立索引
# 6. search() 负责根据用户问题返回最相关片段
# 7. 当前版本用 TF-IDF，不是真正的大模型语义检索
# 8. 后面可以升级成 LangChain + Embedding + Chroma