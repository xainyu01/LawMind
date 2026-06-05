# 第二阶段：法律文档解析与向量化入库

本阶段目标：把一个法律文档（PDF/Word/TXT）扔进 `data/docs/`，运行一条命令，自动完成 解析→分段→向量化→存入ChromaDB 全流程，并能在向量库里搜到结果。

---

## 1. 写配置模块 `app/core/config.py`

```python
import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # LLM
    DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
    DEEPSEEK_BASE_URL: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "deepseek-chat")

    # Embedding
    EMBEDDING_MODEL_NAME: str = os.getenv("EMBEDDING_MODEL_NAME", "BAAI/bge-small-zh")
    EMBEDDING_DEVICE: str = "cuda"  # RTX 5060

    # ChromaDB
    CHROMA_PERSIST_DIR: str = "./data/chroma"
    CHROMA_COLLECTION_NAME: str = "legal_knowledge"

    # Text splitter
    CHUNK_SIZE: int = 500
    CHUNK_OVERLAP: int = 50


settings = Settings()
```

> 全部从 `.env` 和默认值加载，后面各模块统一 `from app.core.config import settings`。

---

## 2. 写文档加载器 `app/rag/document_loader.py`

支持三种法律文档格式：

| 格式 | 库 | 说明 |
|------|-----|------|
| PDF | PyPDF2 | 法律法规、判决书最常见格式 |
| Word | python-docx | 合同、法律意见书 |
| TXT | 内置 | 纯文本法条、标化数据集 |

```python
import os
from pathlib import Path
from typing import List

from langchain_community.document_loaders import (
    PyPDFLoader,
    Docx2txtLoader,
    TextLoader,
)
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain.schema import Document

from app.core.config import settings


def load_document(file_path: str) -> List[Document]:
    """根据扩展名选择解析器，返回 LangChain Document 列表"""
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
    """法律文本按条款粒度分段"""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.CHUNK_SIZE,
        chunk_overlap=settings.CHUNK_OVERLAP,
        separators=["\n\n", "\n", "。", "；", "，", " "],
        # 法律文本以段落、法条号为自然边界
    )
    return splitter.split_documents(documents)


def load_and_split(file_path: str) -> List[Document]:
    """一步完成：加载 + 分段"""
    docs = load_document(file_path)
    file_name = Path(file_path).name

    # 给每个chunk打上来源元数据
    for i, doc in enumerate(docs):
        doc.metadata.setdefault("source", file_name)
        doc.metadata.setdefault("chunk_index", i)

    return split_documents(docs)
```

---

## 3. 写嵌入模块 `app/rag/embedding.py`

加载本地 BGE 模型，提供 `embed_documents` 和 `embed_query` 两个接口（ChromaDB 要求的协议）。

```python
from typing import List

from sentence_transformers import SentenceTransformer

from app.core.config import settings


class BgeEmbedding:
    """封装 sentence-transformers，提供与 LangChain 兼容的嵌入接口"""

    def __init__(self):
        self.model = SentenceTransformer(
            settings.EMBEDDING_MODEL_NAME,
            device=settings.EMBEDDING_DEVICE,
            cache_folder="./models",
        )

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """批量嵌入文档（入库用）"""
        embeddings = self.model.encode(
            texts,
            normalize_embeddings=True,  # 余弦相似度需归一化
            show_progress_bar=True,
        )
        return embeddings.tolist()

    def embed_query(self, text: str) -> List[float]:
        """嵌入单个查询"""
        embedding = self.model.encode(
            text,
            normalize_embeddings=True,
        )
        return embedding.tolist()
```

> `normalize_embeddings=True` 后，ChromaDB 用默认的 L2 距离就等于余弦距离。

---

## 4. 写向量库模块 `app/rag/vector_store.py`

封装 ChromaDB 的增删查。

```python
import os
from typing import List, Optional

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.core.config import settings
from app.rag.embedding import BgeEmbedding


# 全局单例
_embedding: Optional[BgeEmbedding] = None
_client: Optional[chromadb.PersistentClient] = None
_collection: Optional[chromadb.Collection] = None


def _get_embedding() -> BgeEmbedding:
    global _embedding
    if _embedding is None:
        _embedding = BgeEmbedding()
    return _embedding


def _get_collection() -> chromadb.Collection:
    global _client, _collection
    if _client is None:
        os.makedirs(settings.CHROMA_PERSIST_DIR, exist_ok=True)
        _client = chromadb.PersistentClient(
            path=settings.CHROMA_PERSIST_DIR,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
    if _collection is None:
        _collection = _client.get_or_create_collection(
            name=settings.CHROMA_COLLECTION_NAME,
        )
    return _collection


def add_documents(docs) -> None:
    """将分段后的文档写入向量库"""
    collection = _get_collection()
    embedder = _get_embedding()

    texts = [doc.page_content for doc in docs]
    metadatas = [doc.metadata for doc in docs]
    ids = [f"{doc.metadata.get('source', 'unk')}_{doc.metadata.get('chunk_index', i)}"
           for i, doc in enumerate(docs)]

    embeddings = embedder.embed_documents(texts)

    collection.add(
        ids=ids,
        embeddings=embeddings,
        documents=texts,
        metadatas=metadatas,
    )


def search(query: str, top_k: int = 5) -> List[dict]:
    """向量检索，返回 top_k 结果"""
    collection = _get_collection()
    embedder = _get_embedding()

    query_embedding = embedder.embed_query(query)

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
    )

    # 把 ChromaDB 的返回格式整理成易用的 dict 列表
    hits = []
    if results["ids"] and results["ids"][0]:
        for i in range(len(results["ids"][0])):
            hits.append({
                "id": results["ids"][0][i],
                "content": results["documents"][0][i],
                "metadata": results["metadatas"][0][i],
                "distance": results["distances"][0][i],
            })
    return hits


def clear_collection() -> None:
    """清空向量库（调试用）"""
    global _collection
    client = _get_collection()
    _client.delete_collection(settings.CHROMA_COLLECTION_NAME)
    _collection = None
```

---

## 5. 写入库脚本 `scripts/ingest.py`

把上面的模块串起来，一个命令完成入库。

```python
"""
法律文档入库脚本

用法：
    uv run python scripts/ingest.py data/docs/民法典.pdf
    uv run python scripts/ingest.py data/docs/劳动法.txt
    uv run python scripts/ingest.py data/docs/              # 整目录入库
"""

import sys
import os
from pathlib import Path

from app.rag.document_loader import load_and_split
from app.rag.vector_store import add_documents


def ingest_path(path: str) -> int:
    """入库单个文件或整个目录，返回入库的 chunk 数"""
    p = Path(path)
    if p.is_file():
        files = [str(p)]
    elif p.is_dir():
        files = [str(f) for f in p.glob("*") if f.suffix.lower() in (".pdf", ".docx", ".doc", ".txt")]
    else:
        print(f"路径不存在: {path}")
        return 0

    total = 0
    for file_path in files:
        print(f"正在处理: {file_path}")
        try:
            docs = load_and_split(file_path)
            add_documents(docs)
            print(f"  入库 {len(docs)} 个片段")
            total += len(docs)
        except Exception as e:
            print(f"  失败: {e}")

    return total


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: uv run python scripts/ingest.py <文件或目录路径>")
        sys.exit(1)

    count = ingest_path(sys.argv[1])
    print(f"\n总计入库 {count} 个片段")
```

---

## 6. 验证：端到端跑通

### 6.1 准备测试文档

在 `data/docs/` 下放一个测试用的 txt 文件，内容随便写几条假法条：

```text
第二百零五条 本法自2021年1月1日起施行。

第一百四十三条 具备下列条件的民事法律行为有效：
（一）行为人具有相应的民事行为能力；
（二）意思表示真实；
（三）不违反法律、行政法规的强制性规定，不违背公序良俗。

第一千零四十三条 家庭应当树立优良家风，弘扬家庭美德，重视家庭文明建设。
夫妻应当互相忠实，互相尊重，互相关爱；家庭成员应当敬老爱幼，互相帮助，维护平等、和睦、文明的婚姻家庭关系。
```

保存为 `data/docs/民法典节选.txt`。

### 6.2 运行入库

```bash
uv run python scripts/ingest.py data/docs/民法典节选.txt
```

期望输出：
```
正在处理: data/docs/民法典节选.txt
  入库 4 个片段

总计入库 4 个片段
```

### 6.3 检索验证

新建 `scripts/search_test.py`：

```python
"""快速检索测试"""
import sys
from app.rag.vector_store import search

if __name__ == "__main__":
    query = sys.argv[1] if len(sys.argv) > 1 else "夫妻之间有什么义务"
    results = search(query, top_k=3)
    for i, hit in enumerate(results):
        print(f"\n--- 结果 {i+1} (距离: {hit['distance']:.4f}) ---")
        print(f"来源: {hit['metadata'].get('source', 'unknown')}")
        print(hit["content"][:200])
```

运行：
```bash
uv run python scripts/search_test.py "民事法律行为有效的条件"
```

期望看到你刚才入库的法条。

---

## 7. 阶段检查清单

- [ ] `app/core/config.py` 可正常加载 `.env`
- [ ] `app/rag/document_loader.py` 支持 PDF / Word / TXT
- [ ] `app/rag/embedding.py` 成功加载本地 BGE 模型到 GPU
- [ ] `app/rag/vector_store.py` 可增删查 ChromaDB
- [ ] `uv run python scripts/ingest.py data/docs/民法典节选.txt` 入库成功
- [ ] `uv run python scripts/search_test.py "xxx"`能返回相关片段
- [ ] 向量数据持久化到 `data/chroma/`，重启后仍可检索

---

## 注意事项（法律 RAG 特有）

1. **分段粒度**：`chunk_size=500` 是初始值。法律条文推荐实际跑一批数据后按法条长度微调，避免一条法条被切两半。
2. **元数据保留**：后续如果接入真实法律数据，要在 `load_and_split` 里提取法条编号（如"第143条"）写进 metadata，方便最终答案溯源。
3. **编码问题**：法院公开文书很多是 GB2312 编码，`TextLoader` 要做 encoding fallback 处理。

---

**下一阶段预告：第三阶段——RAG 检索与 LLM 生成（问答接口、混合检索、重排序）。**
