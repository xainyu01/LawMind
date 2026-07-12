"""单元测试 - 向量存储模块（使用 mock）"""

import pytest
from unittest.mock import patch, MagicMock


class TestVectorStore:
    """测试向量存储函数（mock ChromaDB）"""

    @patch("app.rag.vector_store._get_collection")
    @patch("app.rag.vector_store._get_embedding")
    def test_search_basic(self, mock_get_emb, mock_get_col):
        """测试基本搜索"""
        from app.rag.vector_store import search

        mock_emb = MagicMock()
        mock_emb.embed_query.return_value = [0.1] * 512
        mock_get_emb.return_value = mock_emb

        mock_col = MagicMock()
        mock_col.query.return_value = {
            "ids": [["doc1", "doc2"]],
            "documents": [["内容1", "内容2"]],
            "metadatas": [[{"source": "a.txt"}, {"source": "b.txt"}]],
            "distances": [[0.1, 0.2]],
        }
        mock_get_col.return_value = mock_col

        results = search("测试查询", top_k=2)
        assert len(results) == 2
        assert results[0]["id"] == "doc1"
        assert results[0]["content"] == "内容1"
        assert results[0]["distance"] == 0.1

    @patch("app.rag.vector_store._get_collection")
    @patch("app.rag.vector_store._get_embedding")
    def test_search_with_where(self, mock_get_emb, mock_get_col):
        """测试带 where 过滤的搜索"""
        from app.rag.vector_store import search

        mock_emb = MagicMock()
        mock_emb.embed_query.return_value = [0.1] * 512
        mock_get_emb.return_value = mock_emb

        mock_col = MagicMock()
        mock_col.query.return_value = {
            "ids": [["doc1"]],
            "documents": [["内容1"]],
            "metadatas": [[{"source": "a.txt", "status": "active"}]],
            "distances": [[0.1]],
        }
        mock_get_col.return_value = mock_col

        results = search("测试", where={"status": {"$ne": "repealed"}})
        mock_col.query.assert_called_once()
        call_kwargs = mock_col.query.call_args[1]
        assert "where" in call_kwargs

    @patch("app.rag.vector_store._get_collection")
    @patch("app.rag.vector_store._get_embedding")
    def test_search_empty_results(self, mock_get_emb, mock_get_col):
        """测试空结果"""
        from app.rag.vector_store import search

        mock_emb = MagicMock()
        mock_emb.embed_query.return_value = [0.1] * 512
        mock_get_emb.return_value = mock_emb

        mock_col = MagicMock()
        mock_col.query.return_value = {
            "ids": [[]],
            "documents": [[]],
            "metadatas": [[]],
            "distances": [[]],
        }
        mock_get_col.return_value = mock_col

        results = search("不存在的查询")
        assert results == []

    @patch("app.rag.vector_store._get_collection")
    def test_get_collection_count(self, mock_get_col):
        """测试获取集合数量"""
        from app.rag.vector_store import get_collection_count
        mock_col = MagicMock()
        mock_col.count.return_value = 1000
        mock_get_col.return_value = mock_col
        assert get_collection_count() == 1000

    @patch("app.rag.vector_store._get_collection")
    @patch("app.rag.vector_store._get_embedding")
    def test_add_documents(self, mock_get_emb, mock_get_col):
        """测试添加文档"""
        from app.rag.vector_store import add_documents
        from langchain_core.documents import Document

        mock_emb = MagicMock()
        mock_emb.embed_documents.return_value = [[0.1] * 512, [0.2] * 512]
        mock_get_emb.return_value = mock_emb

        mock_col = MagicMock()
        mock_get_col.return_value = mock_col

        docs = [
            Document(page_content="内容1", metadata={"source": "a.txt", "chunk_index": 0}),
            Document(page_content="内容2", metadata={"source": "a.txt", "chunk_index": 1}),
        ]
        add_documents(docs)
        mock_col.add.assert_called_once()
