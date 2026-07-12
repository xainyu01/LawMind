"""单元测试 - 配置模块"""

import os
from unittest.mock import patch


class TestSettings:
    """测试 Settings 类"""

    def test_default_values(self):
        """测试默认配置值"""
        with patch.dict(os.environ, {}, clear=False):
            from app.core.config import Settings
            s = Settings()
            assert s.EMBEDDING_MODEL_NAME == "BAAI/bge-small-zh"
            assert s.EMBEDDING_DEVICE == "cuda"
            assert s.CHROMA_PERSIST_DIR == "./data/chroma"
            assert s.CHROMA_COLLECTION_NAME == "legal_knowledge"
            assert s.CHUNK_SIZE == 500
            assert s.CHUNK_OVERLAP == 50
            assert s.LLM_TEMPERATURE == 0.1
            assert s.LLM_MAX_TOKENS == 2048
            assert s.MAX_MEMORY_TURNS == 10
            assert s.SESSION_TTL == 3600
            assert s.SEMANTIC_CACHE_THRESHOLD == 0.92

    def test_env_override(self):
        """测试 .env 文件中的环境变量被正确加载"""
        from app.core.config import Settings as SettingsClass
        # Settings 类属性在类定义时通过 os.getenv 求值
        # .env 中 LLM_MODEL=deepseek-v4-flash 会被 load_dotenv() 加载
        # 验证 .env 中的值已被正确读取（非默认值 "deepseek-chat"）
        assert SettingsClass.LLM_MODEL != "deepseek-chat", "LLM_MODEL 应从 .env 加载"
        assert SettingsClass.LLM_MODEL == os.getenv("LLM_MODEL")

    def test_parse_api_keys_json(self):
        """测试解析 JSON 格式的 API_KEYS"""
        from app.core.config import _parse_api_keys
        result = _parse_api_keys('["key1", "key2"]')
        assert result == ["key1", "key2"]

    def test_parse_api_keys_comma(self):
        """测试解析逗号分隔的 API_KEYS"""
        from app.core.config import _parse_api_keys
        result = _parse_api_keys("key1, key2, key3")
        assert result == ["key1", "key2", "key3"]

    def test_parse_api_keys_empty(self):
        """测试空 API_KEYS"""
        from app.core.config import _parse_api_keys
        assert _parse_api_keys("") == []
        assert _parse_api_keys(None) == []
