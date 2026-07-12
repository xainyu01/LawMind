"""单元测试 - 对话记忆模块"""

import json
import pytest
from unittest.mock import patch, MagicMock


class TestConversationMemory:
    """测试对话记忆"""

    @patch("app.db.memory.get_backend")
    def test_save_turn(self, mock_get_backend):
        """测试保存对话轮次"""
        from app.db.memory import ConversationMemory
        mock_backend = MagicMock()
        mock_backend.hgetall.return_value = {}
        mock_get_backend.return_value = mock_backend

        mem = ConversationMemory()
        mem.save_turn(
            session_id="test",
            user_msg="你好",
            assistant_msg="您好",
            intent="chitchat",
            sources=[],
        )

        mock_backend.lpush.assert_called_once()
        mock_backend.ltrim.assert_called_once()
        mock_backend.expire.assert_called()

    @patch("app.db.memory.get_backend")
    def test_get_history(self, mock_get_backend):
        """测试获取对话历史"""
        from app.db.memory import ConversationMemory
        mock_backend = MagicMock()
        mock_backend.lrange.return_value = [
            json.dumps({"role": "assistant", "content": "回答"}, ensure_ascii=False),
            json.dumps({"role": "user", "content": "问题"}, ensure_ascii=False),
        ]
        mock_get_backend.return_value = mock_backend

        mem = ConversationMemory()
        history = mem.get_history("test")
        assert len(history) == 2
        # 应该按时间顺序（反转后）
        assert history[0]["role"] == "user"
        assert history[1]["role"] == "assistant"

    @patch("app.db.memory.get_backend")
    def test_get_context_for_prompt(self, mock_get_backend):
        """测试获取上下文文本"""
        from app.db.memory import ConversationMemory
        mock_backend = MagicMock()
        mock_backend.lrange.return_value = [
            json.dumps({"role": "user", "content": "问题"}, ensure_ascii=False),
        ]
        mock_backend.hgetall.return_value = {
            "law_domains": "民法",
            "cited_statutes": "第1043条",
            "user_facts": "关于夫妻义务",
        }
        mock_get_backend.return_value = mock_backend

        mem = ConversationMemory()
        context = mem.get_context_for_prompt("test")
        assert "民法" in context
        assert "第1043条" in context


class TestSemanticCache:
    """测试语义缓存"""

    @patch("app.db.cache.get_backend")
    def test_cache_key_generation(self, mock_get_backend):
        """测试缓存 key 生成"""
        from app.db.cache import SemanticCache
        mock_get_backend.return_value = MagicMock()

        cache = SemanticCache()
        key1 = cache._cache_key("测试查询")
        key2 = cache._cache_key("测试查询")
        key3 = cache._cache_key("其他查询")
        assert key1 == key2
        assert key1 != key3

    @patch("app.db.cache.get_backend")
    def test_chitchat_not_cached(self, mock_get_backend):
        """测试闲聊不缓存"""
        from app.db.cache import SemanticCache
        import numpy as np
        mock_backend = MagicMock()
        mock_get_backend.return_value = mock_backend

        cache = SemanticCache()
        cache.store(
            query_embedding=np.array([0.1] * 512),
            answer_data={"query": "你好", "answer": "您好"},
            intent="chitchat",
        )
        mock_backend.set.assert_not_called()

    @patch("app.db.cache.get_backend")
    def test_cache_miss(self, mock_get_backend):
        """测试缓存未命中"""
        from app.db.cache import SemanticCache
        import numpy as np
        mock_backend = MagicMock()
        mock_backend.get.return_value = None
        mock_get_backend.return_value = mock_backend

        cache = SemanticCache()
        result = cache.lookup_by_embedding(np.array([0.1] * 512))
        assert result is None
