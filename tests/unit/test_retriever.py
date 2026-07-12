"""单元测试 - 检索模块"""

import pytest
from unittest.mock import patch


class TestMMRRerank:
    """测试 MMR 去重算法"""

    def test_empty_candidates(self):
        """测试空候选列表"""
        from app.rag.retriever import mmr_rerank
        result = mmr_rerank([0.1] * 512, [], lambda_param=0.5, top_k=5)
        assert result == []

    def test_single_candidate(self):
        """测试单个候选"""
        from app.rag.retriever import mmr_rerank
        candidates = [{"id": "1", "content": "test", "rrf_score": 0.5}]
        result = mmr_rerank([0.1] * 512, candidates, lambda_param=0.5, top_k=5)
        assert len(result) == 1

    def test_mmr_selects_diverse(self):
        """测试 MMR 选择多样性结果"""
        from app.rag.retriever import mmr_rerank
        # 创建有 embedding 的候选，相关性相同但 embedding 不同
        candidates = [
            {"id": "1", "content": "A", "rrf_score": 0.5, "embedding": [1.0, 0.0, 0.0]},
            {"id": "2", "content": "B", "rrf_score": 0.5, "embedding": [0.0, 1.0, 0.0]},
            {"id": "3", "content": "C", "rrf_score": 0.5, "embedding": [0.0, 0.0, 1.0]},
        ]
        result = mmr_rerank([1.0, 0.0, 0.0], candidates, lambda_param=0.5, top_k=2)
        assert len(result) == 2
        # 第一个应该是最相关的（id=1），第二个应该是最不相似的（id=2 或 id=3）
        assert result[0]["id"] == "1"

    def test_top_k_limits_results(self):
        """测试 top_k 限制结果数量"""
        from app.rag.retriever import mmr_rerank
        candidates = [
            {"id": str(i), "content": f"doc{i}", "rrf_score": 0.5 - i * 0.01}
            for i in range(10)
        ]
        result = mmr_rerank([0.1] * 512, candidates, lambda_param=0.5, top_k=3)
        assert len(result) == 3


class TestCosineSimilarity:
    """测试余弦相似度计算"""

    def test_identical_vectors(self):
        from app.rag.retriever import _cosine_similarity
        assert _cosine_similarity([1, 0, 0], [1, 0, 0]) == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        from app.rag.retriever import _cosine_similarity
        assert _cosine_similarity([1, 0, 0], [0, 1, 0]) == pytest.approx(0.0)

    def test_opposite_vectors(self):
        from app.rag.retriever import _cosine_similarity
        assert _cosine_similarity([1, 0], [-1, 0]) == pytest.approx(-1.0)

    def test_zero_vector(self):
        from app.rag.retriever import _cosine_similarity
        assert _cosine_similarity([0, 0], [1, 0]) == 0.0


class TestHybridRetriever:
    """测试混合检索器"""

    def test_needs_rebuild(self):
        """测试是否需要重建索引"""
        from app.rag.retriever import HybridRetriever
        retriever = HybridRetriever()
        # _bm25 is None -> needs rebuild
        assert retriever._needs_rebuild() is True
        # 模拟已加载
        retriever._bm25 = True  # 非 None
        with patch("app.rag.retriever.vector_store") as mock_vs:
            mock_vs.get_collection_count.return_value = 100
            retriever._doc_count = 100
            assert retriever._needs_rebuild() is False
            retriever._doc_count = 50
            assert retriever._needs_rebuild() is True

    @patch("app.rag.retriever.vector_store")
    def test_build_bm25_empty(self, mock_vs):
        """测试空集合构建 BM25"""
        from app.rag.retriever import HybridRetriever
        retriever = HybridRetriever()
        mock_vs.get_all_documents.return_value = {"ids": [], "documents": [], "metadatas": []}
        retriever._build_bm25()
        assert retriever._bm25 is None
        assert retriever._doc_count == 0
