"""单元测试 - 认证模块"""

import pytest
import jwt
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta, timezone


class TestPasswordUtils:
    """测试密码工具函数"""

    def test_hash_and_verify(self):
        """测试密码哈希和验证"""
        from app.core.auth import hash_password, verify_password
        password = "test123456"
        hashed = hash_password(password)
        assert hashed != password
        assert verify_password(password, hashed) is True
        assert verify_password("wrong", hashed) is False

    def test_hash_different_each_time(self):
        """测试每次哈希结果不同（salt 随机）"""
        from app.core.auth import hash_password
        h1 = hash_password("test123")
        h2 = hash_password("test123")
        assert h1 != h2


class TestAccessToken:
    """测试 Access Token"""

    def test_create_and_verify(self):
        """测试创建和验证 Access Token"""
        from app.core.auth import create_access_token, verify_access_token
        token = create_access_token(user_id=1, username="test", role="user")
        payload = verify_access_token(token)
        assert payload["sub"] == "1"
        assert payload["username"] == "test"
        assert payload["role"] == "user"
        assert payload["type"] == "access"

    def test_expired_token(self):
        """测试过期 Token"""
        from app.core.auth import verify_access_token
        from app.core.config import settings
        # 创建一个已过期的 token
        payload = {
            "sub": "1",
            "username": "test",
            "role": "user",
            "type": "access",
            "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
        }
        token = jwt.encode(payload, settings.JWT_ACCESS_SECRET, algorithm="HS256")
        with pytest.raises(Exception) as exc_info:
            verify_access_token(token)
        assert "expired" in str(exc_info.value.detail).lower()

    def test_wrong_type_token(self):
        """测试错误类型的 Token"""
        from app.core.auth import verify_access_token
        from app.core.config import settings
        payload = {
            "sub": "1",
            "type": "refresh",  # 错误类型
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }
        token = jwt.encode(payload, settings.JWT_ACCESS_SECRET, algorithm="HS256")
        with pytest.raises(Exception) as exc_info:
            verify_access_token(token)
        assert "Invalid token type" in str(exc_info.value.detail)


class TestIntentClassification:
    """测试意图分类（关键词回退）"""

    def test_chitchat(self):
        """测试闲聊识别"""
        from app.rag.generator import _classify_intent_keyword
        assert _classify_intent_keyword("你好") == "chitchat"
        assert _classify_intent_keyword("你是谁") == "chitchat"

    def test_statute_lookup(self):
        """测试法条查询识别"""
        from app.rag.generator import _classify_intent_keyword
        assert _classify_intent_keyword("民法典第1043条规定了什么") == "statute_lookup"
        assert _classify_intent_keyword("刑法条文") == "statute_lookup"

    def test_case_analysis(self):
        """测试案例分析识别"""
        from app.rag.generator import _classify_intent_keyword
        assert _classify_intent_keyword("这个案例的判决结果") == "case_analysis"

    def test_contract_review(self):
        """测试合同审查识别"""
        from app.rag.generator import _classify_intent_keyword
        assert _classify_intent_keyword("帮我审查这份合同") == "contract_review"

    def test_legal_qa_fallback(self):
        """测试法律问答兜底"""
        from app.rag.generator import _classify_intent_keyword
        assert _classify_intent_keyword("什么是正当防卫") == "legal_qa"


class TestContextBuilder:
    """测试上下文构建"""

    def test_build_context_text(self):
        """测试构建上下文文本"""
        from app.rag.generator import _build_context_text
        contexts = [
            {"content": "第一条内容", "metadata": {"source": "民法典.txt"}},
            {"content": "第二条内容", "metadata": {"source": "刑法.txt"}},
        ]
        result = _build_context_text(contexts)
        assert "参考法条 1" in result
        assert "参考法条 2" in result
        assert "民法典.txt" in result
        assert "刑法.txt" in result
        assert "第一条内容" in result
        assert "第二条内容" in result
