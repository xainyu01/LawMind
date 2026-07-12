"""单元测试 - LLM 生成模块"""

from unittest.mock import patch


class TestChitchatResponses:
    """测试闲聊回复"""

    def test_known_patterns(self):
        """测试已知闲聊模式"""
        from app.rag.generator import CHITCHAT_RESPONSES
        assert "你好" in CHITCHAT_RESPONSES
        assert "你是谁" in CHITCHAT_RESPONSES
        assert "谢谢" in CHITCHAT_RESPONSES

    @patch("app.rag.generator.OpenAI")
    @patch("app.rag.generator._classify_intent_with_llm")
    def test_chitchat_direct_return(self, mock_classify, mock_openai):
        """测试闲聊直接返回（不调用 LLM）"""
        from app.rag.generator import LegalGenerator
        mock_classify.return_value = "chitchat"

        gen = LegalGenerator()
        result = gen.generate("你好", [])
        assert result["intent"] == "chitchat"
        assert "您好" in result["answer"]
        assert result["sources"] == []

    @patch("app.rag.generator.OpenAI")
    @patch("app.rag.generator._classify_intent_with_llm")
    def test_unknown_chitchat(self, mock_classify, mock_openai):
        """测试未知闲聊（兜底回复）"""
        from app.rag.generator import LegalGenerator
        mock_classify.return_value = "chitchat"

        gen = LegalGenerator()
        result = gen.generate("今天天气不错", [])
        assert result["intent"] == "chitchat"
        assert "法律问题" in result["answer"]


class TestBuildContextText:
    """测试上下文文本构建"""

    def test_single_context(self):
        from app.rag.generator import _build_context_text
        contexts = [{"content": "测试内容", "metadata": {"source": "test.txt"}}]
        result = _build_context_text(contexts)
        assert "参考法条 1" in result
        assert "test.txt" in result
        assert "测试内容" in result

    def test_missing_source(self):
        from app.rag.generator import _build_context_text
        contexts = [{"content": "内容", "metadata": {}}]
        result = _build_context_text(contexts)
        assert "未知来源" in result

    def test_multiple_contexts(self):
        from app.rag.generator import _build_context_text
        contexts = [
            {"content": "A", "metadata": {"source": "a.txt"}},
            {"content": "B", "metadata": {"source": "b.txt"}},
            {"content": "C", "metadata": {"source": "c.txt"}},
        ]
        result = _build_context_text(contexts)
        assert "参考法条 1" in result
        assert "参考法条 2" in result
        assert "参考法条 3" in result
