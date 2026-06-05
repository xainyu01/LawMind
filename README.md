# 智能客服 RAG 系统

## 项目结构

```
RAG/
├── main.py                       # FastAPI 入口
│
├── app/
│   ├── __init__.py
│   ├── core/
│   │   ├── __init__.py
│   │   └── config.py             # 统一配置，读取 .env
│   │
│   ├── rag/
│   │   ├── __init__.py
│   │   ├── document_loader.py    # 文档加载与切分
│   │   ├── embedding.py          # bge 本地嵌入模型封装
│   │   └── vector_store.py       # Chroma 向量库操作（入库、检索）
│   │
│   ├── api/                      # 预留：API 路由目录
│   └── db/                       # 预留：数据库操作（Redis 等）
│
├── models/                       # 下载的本地模型（如 bge-small-zh）
│   └── BAAI/
│       └── bge-small-zh/
│
├── data/
│   ├── docs/                     # 上传的原始文档（PDF/Word/TXT）
│   │   └── test.txt              # 测试文件
│   └── chroma/                   # Chroma 持久化向量库文件
│       └── ...                   # 运行 ingest.py 后自动生成
│
├── scripts/
│   ├── download_model.py         # 模型下载脚本
│   └── ingest.py                 # 一键文档入库脚本
│
└── logs/                         # 日志目录
```

## 技术栈

| 层次 | 技术 |
| ---- | ---- |
| Web 框架 | FastAPI + Uvicorn |
| LLM | DeepSeek (openai SDK 兼容调用) |
| 嵌入模型 | BAAI/bge-small-zh (sentence-transformers) |
| 向量数据库 | ChromaDB |
| 文档解析 | Unstructured / PyPDF2 / python-docx |
| 关键词检索 | bm25s |
| 缓存/会话 | Redis |
| LLM 编排 | LangChain |

## 快速开始

```bash
# 安装依赖
uv sync

# 启动服务
uv run python main.py
```
