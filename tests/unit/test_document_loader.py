"""单元测试 - 文档加载与分段模块"""

import os
import tempfile
import pytest
from unittest.mock import patch, MagicMock


class TestSplitLegalDocument:
    """测试法律文档结构化分段"""

    def test_split_law(self):
        """测试法律条文分段"""
        from app.rag.document_loader import split_legal_document
        text = """第一条 为了保护民事主体的合法权益。
第二条 民法调整平等主体的自然人、法人和非法人组织之间的人身关系和财产关系。
第三条 民事主体的人身权利、财产权利以及其他合法权益受法律保护。"""
        chunks = split_legal_document(text, doc_type="law")
        assert len(chunks) == 3
        assert chunks[0]["article"] == "第一条"
        assert chunks[1]["article"] == "第二条"
        assert chunks[2]["article"] == "第三条"
        assert chunks[0]["doc_type"] == "law"
        assert "保护民事主体" in chunks[0]["text"]

    def test_split_judgment(self):
        """测试判决书分段"""
        from app.rag.document_loader import split_legal_document
        text = """原告张三诉被告李四借款合同纠纷一案。
本院认为，原被告之间的借款合同合法有效。
判决如下：被告应偿还原告借款10万元。
如不服本判决，可在判决书送达之日起十五日内上诉。"""
        chunks = split_legal_document(text, doc_type="judgment")
        assert len(chunks) >= 2
        assert any("本院认为" in c["text"] for c in chunks)
        assert any("判决如下" in c["text"] for c in chunks)

    def test_split_contract(self):
        """测试合同分段"""
        from app.rag.document_loader import split_legal_document
        text = """第一条 甲方将房屋出租给乙方使用。
第二条 租期为一年，自2026年1月1日起。"""
        chunks = split_legal_document(text, doc_type="contract")
        assert len(chunks) == 2
        assert chunks[0]["clause"] == "第一条"
        assert chunks[0]["doc_type"] == "contract"

    def test_split_unknown(self):
        """测试未知类型分段"""
        from app.rag.document_loader import split_legal_document
        text = "第一段内容\n\n第二段内容\n\n第三段内容"
        chunks = split_legal_document(text, doc_type="unknown")
        assert len(chunks) == 3
        assert chunks[0]["doc_type"] == "unknown"


class TestInferDocType:
    """测试文档类型推断"""

    def test_judgment(self):
        from app.rag.document_loader import _infer_doc_type
        assert _infer_doc_type("张三诉李四判决书.txt") == "judgment"
        assert _infer_doc_type("民事裁定书.pdf") == "judgment"

    def test_contract(self):
        from app.rag.document_loader import _infer_doc_type
        assert _infer_doc_type("房屋买卖合同.docx") == "contract"
        assert _infer_doc_type("租赁协议.pdf") == "contract"

    def test_law_default(self):
        from app.rag.document_loader import _infer_doc_type
        assert _infer_doc_type("民法典.txt") == "law"
        assert _infer_doc_type("刑法修正案.pdf") == "law"


class TestLoadDocument:
    """测试文档加载"""

    def test_load_txt(self):
        """测试加载 TXT 文件"""
        from app.rag.document_loader import load_document
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8")
        tmp.write("测试内容\n第二行")
        tmp.close()
        try:
            docs = load_document(tmp.name)
            assert len(docs) >= 1
            assert "测试内容" in docs[0].page_content
        finally:
            try:
                os.unlink(tmp.name)
            except PermissionError:
                pass

    def test_unsupported_format(self):
        """测试不支持的文件格式"""
        from app.rag.document_loader import load_document
        with pytest.raises(ValueError, match="不支持的文件格式"):
            load_document("test.xyz")


class TestSplitDocuments:
    """测试默认分段"""

    def test_split_basic(self):
        """测试基本分段功能"""
        from app.rag.document_loader import split_documents
        from langchain_core.documents import Document
        # 使用包含分隔符的文本，确保能被正确分段
        text = "第一段内容。\n\n第二段内容。\n\n第三段" + "B" * 400 + "\n\n第四段" + "C" * 400
        docs = [Document(page_content=text, metadata={"source": "test.txt"})]
        chunks = split_documents(docs)
        assert len(chunks) > 1
