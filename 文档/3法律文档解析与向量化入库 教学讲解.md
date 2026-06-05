# 法律文档解析与向量化入库 教学讲解

## 1. 整体概览与目标

本阶段是整个法律智能系统的**数据底座构建环节**。在系统架构中，它位于最底层，负责把非结构化的法律文档（如《民法典》PDF、法院判决书、合同 Word 等）转化为计算机可检索、可计算的**向量化知识片段**，并持久化存储到向量数据库（ChromaDB）中。

- **要解决的问题**：法律文本通常篇幅长、结构严谨，直接整篇喂给 LLM 会超出上下文窗口且效率低下。必须将文档拆解为适当粒度的片段，转换为向量，才能实现基于语义的快速检索。
- **输入**：放在 `data/docs/` 目录下的一个或多个法律文件，支持 `.pdf`、`.docx`、`.doc`、`.txt`。
- **处理流程**：`解析（文档加载）→ 分段 → 向量化 → 存入 ChromaDB`。
- **输出/验收标准**：运行入库命令后，能通过检索脚本根据自然语言问题找到相关的法条原文片段，且向量数据持久化保存，重启后仍可检索。
- **在更大系统中的位置**：为下一阶段的 RAG（检索增强生成）提供检索“原料”——当用户提问时，先用问题向量在库中检索最相关的法条片段，再组装成提示词送给 LLM 生成答案。

---

## 2. 环境、配置与依赖管理

### 2.1 配置模块 `app/core/config.py` 整体展示

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

这个文件实现了**全局统一配置**，所有模块通过 `from app.core.config import settings` 引用同一个配置实例，避免硬编码。

#### 2.1.1 逐段分析

- **`from dotenv import load_dotenv`**  
  `python-dotenv` 库可以从项目根目录的 `.env` 文件加载环境变量，自动注入到 `os.environ` 中。这样敏感信息（如 API Key）不用写在代码里，也方便在不同环境切换配置。

- **`load_dotenv()`**  
  必须在读取配置之前调用，通常放在模块顶部。执行后会寻找 `.env` 文件（默认当前工作目录），将里面的 `KEY=VALUE` 行加载为环境变量。

- **`class Settings`**  
  使用类属性而非全局变量，便于类型提示、文档化和 IDE 自动补全。这里直接写在类体内，相当于定义类级别的默认值，并通过 `os.getenv` 从环境变量覆盖。

- **LLM 配置**  
  - `DEEPSEEK_API_KEY`：深度求索 API 的鉴权密钥，默认空字符串。空字符串意味着如果未在 `.env` 中设置，后续调用会失败，这是一种“显式失败”设计，提醒开发者必须配置。  
  - `DEEPSEEK_BASE_URL`：API 服务地址，默认为官方地址。如需使用代理或私有化部署，可在 `.env` 中改为其他 URL。  
  - `LLM_MODEL`：指定要调用的具体模型名称，默认为 `deepseek-chat`。保留此配置是为后续问答阶段准备，本阶段尚未使用。

  **工程要点**：虽然当前第二阶段不涉及 LLM 调用，但配置超前定义是常见做法。整个项目的配置集中管理，后续阶段无需再改配置模块。

- **Embedding 配置**  
  - `EMBEDDING_MODEL_NAME`：嵌入模型名称，默认 `BAAI/bge-small-zh`。这是智源研究院（BAAI）发布的中文小模型，在中文语义任务上表现优异，体积小（约 100MB 级别），适合在个人显卡上快速推理。  
    **扩展**：BGE（BAAI General Embedding）系列模型专门为文本嵌入优化，支持中英文。`bge-small-zh` 参数量少，推理速度快；如果对精度要求更高，可替换为 `bge-base-zh` 甚至 `bge-large-zh`，但需要更多显存。之所以在这里选择 SentenceTransformer 而不是直接调用 API 的嵌入模型（如 `text-embedding-ada-002`），是为了**离线**可用、**零成本**、**低延迟**，并且数据不离开本机（数据安全）。  
  - `EMBEDDING_DEVICE`：硬编码为 `"cuda"`，基于作者的 RTX 5060 显卡。如果想自动检测，可改为 `"cuda" if torch.cuda.is_available() else "cpu"`，但当前直接指定避免了引入 torch 依赖的顺序问题（后续在 embedding.py 中加载模型时，SentenceTransformer 内部使用 PyTorch，会自动使用 cuda）。如果环境没有 GPU，运行时会报错，此时需手动改为 `"cpu"`。

- **ChromaDB 配置**  
  - `CHROMA_PERSIST_DIR`：向量数据库持久化路径。`./data/chroma` 表示项目根目录下的 `data/chroma` 文件夹。ChromaDB 会将索引和原始文本/元数据存储在此，实现重启后数据不丢失。  
  - `CHROMA_COLLECTION_NAME`：集合（Collection）名称。ChromaDB 中一个 Collection 类似于关系数据库的一张表，存储一组向量及其相关数据。这里取名 `legal_knowledge`，明确表示法律知识库。

- **Text splitter 配置**  
  - `CHUNK_SIZE`：每个文本块（chunk）的最大字符数，默认 500。对于法律文本，500 字符大致包含 3~5 个法条，可保留较完整的一个逻辑单元。  
  - `CHUNK_OVERLAP`：相邻块之间的重叠字符数，默认 50。设置重叠是为了防止关键信息恰好在切分边界被截断，从而在检索时漏掉。对于法律条款，50 个字符的重叠可能刚好包含一个条款的结尾和下一个条款的开头，属于合理值。

- **`settings = Settings()`**  
  模块最后实例化了一个全局单例。在其他模块中导入 `settings` 即可使用，由于模块在 Python 中是单次加载，该实例在整个进程生命周期内唯一。

**为什么不用 Pydantic Settings？**  
本设计是轻量级的手动类，优点是简单透明，无需引入额外依赖。如果配置项增多、需要校验（如 URL 格式、路径存在性），可升级为 `pydantic-settings`，它提供自动校验、类型转换、从 `.env`/环境变量/命令行多源加载等高级功能。当前场景足够使用。

---

## 3. 核心模块深度拆解

### 3.1 文档加载器 `app/rag/document_loader.py`

该模块负责将多种格式的法律文档解析为 LangChain 的 `Document` 对象列表，并按法律文本的特性进行分段。

#### 3.1.1 完整代码

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

#### 3.1.2 `load_document` 函数

**功能**：根据文件扩展名分发到对应的 LangChain 加载器，返回该文档解析出的原始 `Document` 列表。注意：PDF 或 Word 文档经加载器后可能已经包含多个 `Document` 对象（例如 PDF 按页分割）。

**逐行解释**：

- `ext = Path(file_path).suffix.lower()`：提取文件扩展名并转为小写，`Path` 是 pathlib 库的现代路径处理方式，比 `os.path` 更面向对象。
- 针对 PDF：`PyPDFLoader(file_path)`  
  **PyPDFLoader** 是 LangChain 社区提供的 PDF 加载器，底层使用 `pypdf` 库，按页读取 PDF 中的文本，每页生成一个 `Document`。在消费级硬件上工作良好，但不擅长提取复杂表格或扫描件。对于法律场景中常见的双栏、含页眉页脚的 PDF，可能引入杂讯，后续可能需要清洗。替代方案有 `PyMuPDFLoader`（速度更快，可提取布局信息）或云端的文档解析服务，但会增加依赖或成本。
- 针对 Word：`Docx2txtLoader(file_path)`  
  内部使用 `docx2txt` 库，将 `.docx` 文件转换为纯文本，同时提取图片（若存在）的本地路径。值得注意的是它**不支持旧的 `.doc` 格式**，但代码中使用了 `elif ext in (".docx", ".doc")`，如果遇到 `.doc`，实际 `Docx2txtLoader` 会尝试处理但可能失败，这是一个潜在 bug。更稳健的做法是使用 `python-docx` 直接读取 `.docx`，而对于 `.doc`，需要额外工具如 `antiword` 或 `textract`。当前阶段可以先接受，但在生产环境中需明确限定仅支持 `.docx`。
- 针对 TXT：`TextLoader(file_path, encoding="utf-8")`  
  LangChain 的 `TextLoader` 读取纯文本文件，返回单个 `Document`。这里指定了编码为 UTF-8。然而，中国法院公开的许多裁判文书采用 **GB2312/GBK** 编码，直接使用 UTF-8 会抛出 `UnicodeDecodeError`。文档结尾的“注意事项”也提到了这一点，需做 encoding fallback 处理，但当前代码未实现。生产化时建议加入类似 `try: ... except UnicodeDecodeError: loader = TextLoader(file_path, encoding='gbk')` 的逻辑，或使用 `chardet` 自动检测编码。
- 最后调用 `loader.load()`，返回 `List[Document]`。每个 `Document` 包含 `page_content`（文本内容）和 `metadata`（如页码等）。

#### 3.1.3 `split_documents` 函数

**功能**：将单个或多个 `Document` 对象进一步切分为更小的文本块，以适应嵌入模型的输入长度限制，同时保证检索的细粒度。

**核心工具**：`RecursiveCharacterTextSplitter`  
- **定义**：LangChain 提供的文本分割器，它采用“递归”方式尝试按指定分隔符列表依次分割文本，直到每个块大小小于 `chunk_size`。  
- **与普通固定长度分割的对比**：普通 `CharacterTextSplitter` 仅按单个分隔符切分，容易切断句子。而递归版本优先使用更“强”的分隔符（如段落换行），尽量保持语义单元完整。这正是法律文本所需：法律以“条”为基本单位，段落和句号为自然边界，不应将一条法条从中间切开。

**参数详解**：

- `chunk_size=settings.CHUNK_SIZE`：500 字符。这是最终块的最大长度。注意，如果某一段落本身超过 500 字符且没有更细的分隔符可用（列表中的分隔符都尝试后仍无法切分），分割器会强制在 500 字符处截断，这可能导致一条法条被截断。这也是文档后面建议“按法条长度微调”的原因。
- `chunk_overlap=settings.CHUNK_OVERLAP`：50 字符。相邻块之间共享 50 个字符的重叠区域。这有助于在检索时，如果用户查询的关键信息正好在切分点附近，它可能同时出现在两个块中，提高召回率。
- `separators` 列表：  
  ```python
  ["\n\n", "\n", "。", "；", "，", " "]
  ```
  分隔符按优先级从高到低排列。分割器将尝试先用 `\n\n`（两个换行，即段落分隔）切分，如果切出的块仍大于 `chunk_size`，则用 `\n`（单换行），接着中文句号“。”、分号“；”、逗号“，”、空格“ ”。这确保了切分粒度越来越细，尽量不破坏语法结构。  
  **法律文本特化**：加入中文标点非常关键，因为法条内部常以“；”分隔款项，以“，”分隔条件。如果换成英文文本，列表可能改为 `["\n\n", "\n", ".", ";", ",", " "]`。

#### 3.1.4 `load_and_split` 函数

这是一个便捷组合函数，完成了“加载 → 补充元数据 → 分段”的完整流程。

- 调用 `load_document` 获得初步的文档对象列表（例如 PDF 每页一个）。
- 提取文件名（不含路径），用于标识来源。
- **元数据注入**：  
  ```python
  doc.metadata.setdefault("source", file_name)
  doc.metadata.setdefault("chunk_index", i)
  ```
  `setdefault` 方法：如果原 metadata 中已有该键（如 PDF 加载器可能已经设置了 `source`），则保留原值；否则设为指定默认值。这避免了覆盖加载器提供的更精确的来源信息。  
  `chunk_index` 记录了当前 Document 在原始解析列表中的顺序，虽然分段后这个索引会被重组，但这里预埋的元数据可在后续用于追踪原始文件内的位置。
- 最后调用 `split_documents(docs)` 并返回分段后的列表。**注意**：分段后每个 chunk 仍是 `Document` 对象，但其 `metadata` 会继承自父 Document（LangChain 的 splitter 会复制 metadata）。

**为何在分段前而不是分段后设置元数据？**  
因为在 split 之前，我们还能拿到原始的“页级”或“文件级” Document，`source` 和 `chunk_index`（这里指页面索引）对每个块有意义。分段后，每个 chunk 会自动继承这些元数据，无需再逐个设置，代码更简洁。

---

### 3.2 嵌入模块 `app/rag/embedding.py`

嵌入模块负责将文本转换为固定长度的向量，是整个 RAG 系统的核心。

#### 3.2.1 完整代码

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

#### 3.2.2 模型加载与 SentenceTransformer

- **`SentenceTransformer`**：是一个专门用于文本嵌入的库，基于 PyTorch 和 Transformers。它提供了简洁的 API，能轻松加载 HuggingFace 上大量的预训练嵌入模型。  
- **模型标识** `settings.EMBEDDING_MODEL_NAME` 即 `"BAAI/bge-small-zh"`，这是 huggingface 上的模型 ID。首次运行时会自动下载模型文件到 `cache_folder` 指定的目录 `./models`，避免污染系统缓存。指定 `cache_folder` 是一个好习惯，可使项目依赖自包含，删除项目即可彻底清除模型。
- **设备选择**：`device=settings.EMBEDDING_DEVICE` 即 `"cuda"`。SentenceTransformer 会将模型加载到指定设备。如果 GPU 不可用，会抛出异常。生产环境的工程化写法建议：`device="cuda" if torch.cuda.is_available() else "cpu"`，但当前作为教学阶段，直接指定提示了硬件环境是 RTX 5060。  
- **模型原理简介（扩展）**：BGE 模型基于 BERT 架构，在大量中文语料上经过对比学习（contrastive learning）微调，使得语义相似的句子在向量空间中距离更近。它的输入是文本，输出是一个固定维度的稠密向量（例如 512 维）。`bge-small-zh` 的输出维度通常为 512。

#### 3.2.3 归一化与距离度量

- **`normalize_embeddings=True`**：对输出向量进行 L2 归一化，使每个向量的模长为 1。  
  **为什么需要归一化？**  
  原始向量点积与向量长度有关，归一化后点积就等于余弦相似度。ChromaDB 默认采用 L2 距离（欧氏距离）进行相似度搜索。对于归一化向量，**欧氏距离和余弦相似度成反比**（精确关系：L2 距离平方 = 2 - 2×余弦相似度），因此使用 L2 距离等价于使用余弦相似度。  
  **不归一化的影响**：如果未归一化，某些文本段可能因为长度（内积值大）而非语义相关性被排到前面。归一化消除了向量长度的影响，只关注方向，即纯语义比较。这尤其适合法律检索，因为法条长度不一，我们关心的是内容含义而非文本长度。
- **返回值处理**：`.tolist()` 将 numpy 数组转换为 Python 列表，ChromaDB 可以接受这种格式。

#### 3.2.4 两个接口的设计意图

- `embed_documents(self, texts: List[str]) -> List[List[float]]`：用于离线批量处理文档入库，允许一次传入多个文本，内部 `self.model.encode` 可充分利用 GPU 批量并行加速。`show_progress_bar=True` 显示进度条，处理大规模文档时非常友好。  
- `embed_query(self, text: str) -> List[float]`：用于在线查询，单个文本，输出一个向量。

这个接口设计与 LangChain 的 `Embeddings` 抽象基类完全兼容：LangChain 的向量存储组件期望嵌入类实现 `embed_documents` 和 `embed_query` 两个方法。因此我们的 `BgeEmbedding` 可以直接用作 LangChain 管道的嵌入组件，无需额外适配。目前我们没有使用 LangChain 的向量存储，而是直接封装 ChromaDB，但保留此兼容性对未来扩展有益。

---

### 3.3 向量库模块 `app/rag/vector_store.py`

该模块封装 ChromaDB 的客户端、集合管理以及增删查操作，向上层提供简洁的 API。

#### 3.3.1 完整代码

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
    client = _get_collection()  # 注意：这里接收返回值但未使用，目的是确保_client已初始化
    _client.delete_collection(settings.CHROMA_COLLECTION_NAME)
    _collection = None
```

#### 3.3.2 ChromaDB 简介与选型理由

**ChromaDB** 是一个开源的向量数据库，专为构建 AI 应用设计。它提供了以下关键特性：
- 支持文档存储、向量存储、元数据过滤。
- 内置多种距离度量（L2，IP，cosine）。
- 提供两种模式：`EphemeralClient`（内存模式）和 `PersistentClient`（持久化模式）。
- 轻量级，无需额外服务，直接嵌入 Python 进程。

**为什么在这个场景选择 ChromaDB？**
- **开发便捷性**：对比 Milvus、Qdrant、Weaviate 等，ChromaDB 安装简单（`pip install chromadb`），无需 Docker，适合本地快速原型验证。
- **持久化能力**：`PersistentClient` 将索引和元数据存储在磁盘上，满足“重启后仍可检索”的要求，而 FAISS 等纯向量索引库需要自己实现序列化/元数据管理。
- **成本**：免费、离线可用，符合法律数据隐私要求。
- **局限性**：当数据量超过百万级时，性能可能不如 Milvus 等分布式向量库，且元数据过滤仅支持等值查询，不支持复杂条件。若未来需扩展到海量法律文书，应考虑迁移到 Qdrant（支持过滤和标量量化）或 Milvus。

#### 3.3.3 全局单例设计

模块使用模块级别的变量 `_embedding`、`_client`、`_collection` 实现懒加载单例：
- **懒加载**：只有当真正调用 `add_documents` 或 `search` 时，才初始化嵌入模型和数据库连接。这在脚本运行时能加快导入速度，且允许在未用到向量库时避免加载大模型。
- **单例保证**：通过检查变量是否为 `None`，若是则创建并赋值，保证进程中只有一个模型实例（节约显存）和一个数据库客户端。
- **线程安全吗？**：在当前脚本使用场景下是单线程的，没问题。若未来用 FastAPI 等服务化，需要考虑加锁，因为全局变量在多线程下有竞争条件。简单的改进是使用 `threading.Lock` 保护初始化过程。

#### 3.3.4 `add_documents` 详细流程

1. **获取 collection 和 embedder**。
2. **准备数据**：
   - `texts`：从 `doc.page_content` 提取文本列表。
   - `metadatas`：每个文档的元数据字典，包括 `source`、`chunk_index` 等。
   - `ids`：每个 chunk 的唯一标识。这里构造规则为 `{文件名}_{chunk_index}`。  
     **注意**：`chunk_index` 是在 `load_and_split` 中分段后自然继承下来的吗？看 `load_and_split` 函数，它在分段前给原始 doc 列表设置了 `chunk_index`（其实此时是原始加载器的页码索引），但分段时 `RecursiveCharacterTextSplitter.split_documents` 会为每个产生的 chunk 复制父文档的 metadata。这样，`chunk_index` 可能多个 chunk 相同（例如来自同一页的多个 chunk）。更好的做法是在分段后重新遍历生成新的 `chunk_index`。代码中的 `ids` 使用 `enumerate(docs)` 中的 `i` 作为 fallback，但无法区分同一文件的不同 chunk。不过由于 id 要求唯一，如果出现重复 id，ChromaDB 的 `add` 会怎样？默认行为是 `upsert`（如果 id 已存在则更新），这可能覆盖之前的片段，导致数据丢失。因此我们必须在 `load_and_split` 之后重新设置 `chunk_index` 来保证 id 唯一。文档中未显式处理这个问题，但在验证时文件小且分段少，可能碰巧未重复。这是生产环境必须要修复的隐患。
3. **生成向量**：`embedder.embed_documents(texts)` 返回嵌入列表。
4. **存入 collection**：  
   `collection.add(ids=..., embeddings=..., documents=..., metadatas=...)` 一次批量插入，ChromaDB 负责索引和持久化。如果集合中已有相同 id 的数据，默认会覆盖（upsert），所以要注意 id 唯一性。

#### 3.3.5 `search` 函数与返回格式

- 调用 `embedder.embed_query(query)` 得到查询向量（一维列表）。
- `collection.query(query_embeddings=[query_embedding], n_results=top_k)`：ChromaDB 的 query 期望 `query_embeddings` 是二维列表（可一次查询多个向量），因此用列表包裹。返回结果的结构是一个字典，每个字段都是列表的列表（外层是查询个数，内层是每个查询的结果列表）。例如：
  ```python
  {
      "ids": [["id1", "id2", ...]],
      "documents": [["文本1", "文本2", ...]],
      "metadatas": [[{...}, {...}]],
      "distances": [[0.123, 0.456, ...]]
  }
  ```
- **结果重组**：代码通过遍历 `results["ids"][0]` 的长度，将原始格式转为更直观的 dict 列表。每个 hit 包含 `id`、`content`（原文）、`metadata`、`distance`。  
  **距离**：`distance` 是基于 L2 的欧氏距离，由于我们在嵌入时做了归一化，距离越小表示语义越相似。

#### 3.3.6 `clear_collection` 调试辅助

该函数清空整个 collection，便于多次测试。实现细节：
- 先调用 `_get_collection()` 但将其返回值赋给了 `client` 变量，这段代码本意是确保 `_client` 已初始化（因为 `_get_collection` 内部会创建 client 和 collection）。但实际上直接使用 `_client` 即可，无需接收返回值。这是一个小笔误，但不影响功能，因为 `_client` 已经是模块变量。
- 调用 `_client.delete_collection(name)` 删除集合。
- 将 `_collection` 置 `None`，下次获取时重新创建空集合。

**注意**：如果数据库中有重要数据，`delete_collection` 操作不可逆，所有向量和元数据将被物理删除。生产环境应提供确认机制或删除前备份。

---

### 3.4 入库脚本 `scripts/ingest.py`

该脚本是端到端的入口，将文档加载、分段、向量化、入库串联起来。

#### 3.4.1 完整代码

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

#### 3.4.2 逐段解析

- **文件头注释**：清楚地说明了用法，包括单文件、整目录。`uv run` 是使用 Astral 的 `uv` 包管理工具运行脚本，可保证依赖环境正确。
- **`ingest_path(path: str) -> int`**：
  - 参数 `path` 是命令行传入的路径字符串。
  - 使用 `Path` 对象判断是文件还是目录。
  - 若为目录，使用 `p.glob("*")` 遍历目录下所有文件，并通过后缀名过滤支持的格式。**注意**：`glob("*")` 只匹配直接子文件，不递归子目录；如果文档存放在多层子目录下（如 `data/docs/民法典/`），这些文件不会被处理。生产上可改为 `p.rglob("*")` 以递归遍历。
  - 对每个文件调用 `load_and_split` → `add_documents`，并统计 chunk 总数。
  - 异常处理：捕获所有异常并打印错误信息，这样单个文件失败不会中断其他文件处理。但简单的打印可能不足以满足生产监控，建议后续集成 logging 模块。
- **主入口**：检查命令行参数，如果未提供路径，打印用法并退出。`sys.argv[1]` 获取第一个参数。

**工程考量**：脚本中未显式清空旧数据，如果重复运行同一个文件，会导致相同 id 的 chunk 覆盖（upsert），但不会自动删除不再存在的旧文档。对于简单的全量重建场景，可先调用 `clear_collection` 清空库再导入。另外，没有处理路径中的相对路径与绝对路径问题，当前假定从项目根目录运行。

---

### 3.5 验证脚本 `scripts/search_test.py`

#### 3.5.1 完整代码

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

#### 3.5.2 检索结果解读

- 如果没有提供命令行参数，默认查询“夫妻之间有什么义务”，这正好对应我们测试文档中“第一千零四十三条”的内容，能快速验证。
- `search(query, top_k=3)` 调用向量库检索，返回最相关的前 3 个片段。
- 对每个结果打印：
  - **距离**：如 `0.3456`，越小越相似。由于归一化，距离范围理论上在 0 到 2 之间（0 表示完全相同，2 表示完全相反）。但实际情况中，相似文本的距离通常在 0.3~0.7 之间，具体取决于模型和语料。
  - **来源**：显示文件名，便于追踪。
  - **内容**：只打印前 200 个字符，避免过长。如果法条较短，整条都会显示。

**验证的核心目的**：确保入库的文档确实可被语义检索到，而不仅是关键词匹配。

---

## 4. 端到端验证流程

详细步骤与期望输出已在文档第 6 节给出。作为讲师，我们拆解每一步的预期结果和可能变数：

1. **准备测试文档**：按文档内容创建 `data/docs/民法典节选.txt`，注意保存为 UTF-8 编码。
2. **运行入库命令**：
   ```bash
   uv run python scripts/ingest.py data/docs/民法典节选.txt
   ```
   期望输出：
   ```
   正在处理: data/docs/民法典节选.txt
     入库 4 个片段
   总计入库 4 个片段
   ```
   **为什么是 4 个片段？**  
   原文约 300 多字符，加上几段话，切分时可能按 `\n\n` 分成 3~4 块。`RecursiveCharacterTextSplitter` 会尽量保持段落完整，但受 chunk_size 500 影响，可能合并短段落。具体数量由实际切分决定，文档给出 4 是一个合理估计。
3. **检索测试**：
   ```bash
   uv run python scripts/search_test.py "民事法律行为有效的条件"
   ```
   应该能看到包含“第一百四十三条”的片段排在前面。如果使用默认查询，会看到“夫妻应当互相忠实...”的内容。

若结果不符合预期，应检查：
- 文档是否被正确加载（可通过打印 docs 数量确认）。
- 嵌入模型是否下载成功、是否在 GPU 上正常运行。
- ChromaDB 持久化目录 `data/chroma` 是否生成，且包含文件。

---

## 5. 检查清单与最佳实践扩展

根据文档第 7 节及工程经验补充：

- [x] **`app/core/config.py` 可正常加载 `.env`**  
  确保 `.env` 文件在项目根目录，且 `load_dotenv()` 在导入配置模块时执行。可添加打印验证，但不建议打印 API Key。
- [x] **`app/rag/document_loader.py` 支持 PDF / Word / TXT**  
  验证时建议每种格式都测试一个小文件，特别注意 `.doc` 的支持情况。
- [x] **`app/rag/embedding.py` 成功加载本地 BGE 模型到 GPU**  
  首次运行需下载模型，观察控制台输出确认设备为 `cuda`。如果 `cuda` 不可用，将报错，此时可临时改 `EMBEDDING_DEVICE` 为 `cpu` 测试。
- [x] **`app/rag/vector_store.py` 可增删查 ChromaDB**  
  运行入库后，尝试用检索脚本获取结果。
- [x] **入库脚本运行成功**  
  确保工作目录正确，否则 `data/docs/` 路径可能找不到。
- [x] **检索脚本返回相关片段**  
  验证语义相关性，不是简单关键词匹配。可尝试改写查询词测试鲁棒性，例如“夫妻应承担什么责任”仍应找到相关法条。
- [x] **向量数据持久化**  
  重启 Python 进程或新开终端运行检索脚本，无需重新入库也能得到结果。

### 法律 RAG 特有的最佳实践

1. **分段粒度优化**：  
   `chunk_size=500` 是起点，需基于实际法律文本特征微调。例如《民法典》每条法条平均约 100~200 字符，500 可能包含多条，适合更全面的上下文，但也会降低检索精准度。可按“条款”作为基本单元，通过法条编号的正则表达式（如 `第[一二三四五六七八九十百千]+条`）先分割再嵌入，每条单独向量化，结合元数据中标注法条编号，既精确又可溯源。  
   若保留现有分割器，可调整 `separators` 把法条编号模式作为最高优先级分隔符，但代码较复杂。

2. **元数据增强**：  
   文档注意事项指出提取法条编号。实现时可在 `load_and_split` 中遍历每个 chunk，用正则提取“第X条”写入 `metadata["article"]`，这样最终生成答案时可附上引用，大幅提升可信度。注意法条编号可能有中文数字，需编写转换函数。

3. **编码处理**：  
   `TextLoader` 固定 UTF-8 是不够的。最佳实践是读取文件的前几个字节用 `chardet` 检测编码，或使用 `try-except` 回退尝试多种常见编码（UTF-8, GBK, GB2312, GB18030）。同时建议在入库前统一转成 UTF-8 存储。

4. **全局单例线程安全**：  
   如果后续封装为 Web 服务（如 FastAPI），需使用 `threading.Lock` 或懒加载模块如 `@lru_cache` 装饰器保护模型加载和客户端初始化，避免多线程重复加载模型导致显存溢出（OOM）。

5. **模型下载与离线环境**：  
   `cache_folder="./models"` 指定本地缓存，方便将模型文件纳入版本控制或打包。在不能访问 HuggingFace 的生产环境，可预先下载模型放置于此目录。还需设置 `local_files_only=True` 防止意外连网。

6. **ChromaDB 性能调优**：  
   - 元数据字段如果经常用于过滤，可开启 `hnsw:space` 配置，但 ChromaDB 默认已使用 HNSW 索引。  
   - 当集合中数据量达数十万时，可考虑启用量化（Quantization）减少内存占用，但 ChromaDB 尚未支持，届时需考虑迁移到 Milvus 等。

---

## 6. 常见问题与排错指南

### 问题 1：`load_dotenv()` 没有找到 `.env` 文件，但程序未报错
- **现象**：所有配置值均为默认值，API Key 为空。
- **原因**：`load_dotenv()` 默认寻找当前工作目录的 `.env`，若从不同目录运行脚本可能找不到。
- **解决**：显式指定路径：`load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")`，或在运行时确保在项目根目录。

### 问题 2：PyPDFLoader 读取 PDF 中文乱码
- **原因**：某些 PDF 使用非标准编码或内嵌字体，PyPDF2 提取文本时可能乱码。
- **解决**：尝试改用 `PyMuPDFLoader` (fitz)，或对提取出的文本进行编码修复；若扫描件 PDF，需要引入 OCR（如 pytesseract），但这已超出纯文本解析范畴。

### 问题 3：入库时 ID 重复导致数据覆盖
- **现象**：再次运行入库脚本，新文档可能覆盖旧文档，且某些 chunk 丢失。
- **原因**：`chunk_index` 未在分段后重新设置，导致 id 重复；或两次入库使用相同 `source` 和 `chunk_index`。
- **解决**：在 `add_documents` 中生成 id 时，加入文件路径哈希或 UUID 以确保全局唯一；或者每次入库前调用 `clear_collection` 全量重建。

### 问题 4：GPU 内存不足（CUDA out of memory）
- **现象**：嵌入模型加载或编码时报错。
- **可能**：模型过大（例如误用 `bge-large-zh`）或同时运行了其他占用显存的程序。
- **解决**：换小模型或改用 CPU；如果是并发嵌入，减小 batch size。SentenceTransformer 的 `encode` 默认 batch_size 为 32，可在参数中调小。

### 问题 5：检索结果不相关或全是相同片段
- **诊断**：
  1. 检查 `normalize_embeddings` 是否为 True。
  2. 打印几个 embedding 向量，确认它们不是全零或 NaN。
  3. 查询向量和文档向量是否用同一模型生成。
  4. 分段是否过粗（chunk 太大），导致包含过多无关内容。
- **解决**：调整 chunk_size，检查模型一致性，必要时微调模型。

### 问题 6：`ModuleNotFoundError: No module named 'chromadb'` 等
- 确保使用 `uv` 或 `pip` 安装了所有依赖。建议提供 `requirements.txt` 或 `pyproject.toml`。

---

**下一阶段预告**：第三阶段将基于本阶段构建的向量库，实现 RAG 检索与 LLM 生成的问答接口，包括混合检索、重排序等技术，进一步提升法律问答的准确度。

