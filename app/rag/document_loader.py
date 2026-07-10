import re
from pathlib import Path
from typing import List

from langchain_community.document_loaders import (
    PyPDFLoader,
    Docx2txtLoader,
    TextLoader,
)
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

from app.core.config import settings


def load_document(file_path: str) -> List[Document]:
    ext = Path(file_path).suffix.lower()
    if ext == ".pdf":
        loader = PyPDFLoader(file_path)
    elif ext in (".docx", ".doc"):
        loader = Docx2txtLoader(file_path)
    elif ext == ".txt":
        loader = TextLoader(file_path, encoding="utf-8")
    else:
        raise ValueError(f"不支持的文件格式: {ext}")
    return loader.load()


def split_documents(documents: List[Document]) -> List[Document]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.CHUNK_SIZE,
        chunk_overlap=settings.CHUNK_OVERLAP,
        separators=["\n\n", "\n", "。", "；", "，", " "],
    )
    return splitter.split_documents(documents)


def split_legal_document(text: str, doc_type: str = "law") -> List[dict]:
    """法律文档结构化分段。

    Args:
        text: 文档全文
        doc_type: 文档类型 (law/judgment/contract)

    Returns:
        分段结果列表，每项包含 text 和 metadata
    """
    chunks = []

    if doc_type == "law":
        # 按"第X条"分段，支持中文数字和阿拉伯数字
        pattern = r'(第[一二三四五六七八九十百千零\d]+条)'
        parts = re.split(pattern, text)

        current_article = ""
        article_num = ""
        for part in parts:
            if re.match(pattern, part):
                # 保存上一条
                if current_article.strip():
                    chunks.append({
                        "text": current_article.strip(),
                        "article": article_num,
                        "doc_type": "law",
                    })
                article_num = part
                current_article = part
            else:
                current_article += part

        # 保存最后一条
        if current_article.strip():
            chunks.append({
                "text": current_article.strip(),
                "article": article_num,
                "doc_type": "law",
            })

    elif doc_type == "judgment":
        # 判决书按段落分段（通常以"本院认为"、"判决如下"等为界）
        sections = re.split(r'(?=本院认为|判决如下|如不服本判决|依照)', text)
        for i, section in enumerate(sections):
            if section.strip():
                chunks.append({
                    "text": section.strip(),
                    "section_index": i,
                    "doc_type": "judgment",
                })

    elif doc_type == "contract":
        # 合同按"第X条"分段
        pattern = r'(第[一二三四五六七八九十百千零\d]+条)'
        parts = re.split(pattern, text)

        current_clause = ""
        clause_num = ""
        for part in parts:
            if re.match(pattern, part):
                if current_clause.strip():
                    chunks.append({
                        "text": current_clause.strip(),
                        "clause": clause_num,
                        "doc_type": "contract",
                    })
                clause_num = part
                current_clause = part
            else:
                current_clause += part

        if current_clause.strip():
            chunks.append({
                "text": current_clause.strip(),
                "clause": clause_num,
                "doc_type": "contract",
            })
    else:
        # 未知类型，按段落分段
        paragraphs = text.split("\n\n")
        for i, para in enumerate(paragraphs):
            if para.strip():
                chunks.append({
                    "text": para.strip(),
                    "section_index": i,
                    "doc_type": "unknown",
                })

    return chunks


def load_and_split(file_path: str, split_mode: str = "default") -> List[Document]:
    docs = load_document(file_path)
    file_name = Path(file_path).name

    if split_mode == "legal":
        # 法律结构化分段
        all_chunks = []
        for doc in docs:
            # 根据文件名推断文档类型
            doc_type = _infer_doc_type(file_name)
            chunks = split_legal_document(doc.page_content, doc_type)
            for i, chunk in enumerate(chunks):
                metadata = {**doc.metadata, **chunk}
                metadata["source"] = file_name
                metadata["chunk_index"] = i
                all_chunks.append(Document(page_content=chunk["text"], metadata=metadata))
        return all_chunks
    else:
        # 默认分段模式
        for i, doc in enumerate(docs):
            doc.metadata.setdefault("source", file_name)
            doc.metadata.setdefault("chunk_index", i)
        return split_documents(docs)


def _infer_doc_type(filename: str) -> str:
    """根据文件名推断文档类型。"""
    filename_lower = filename.lower()
    if any(kw in filename_lower for kw in ["判决", "裁定", "调解"]):
        return "judgment"
    elif any(kw in filename_lower for kw in ["合同", "协议"]):
        return "contract"
    else:
        return "law"
